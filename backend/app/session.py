from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config_generator import write_session_config
from .llm import (
    llm_detect_confirm,
    llm_detect_intent,
    llm_extract_models,
    llm_extract_region,
    llm_extract_year,
    llm_generate_report,
    SUPPORTED_REGIONS,
    _call_llm,
    _strip_code_fence,
)
from .models import (
    ChatMessage,
    PartialPlan,
    SendMessageResponse,
    Session,
    SessionArtifacts,
    SessionState,
)
from .session_store import create_session, get_session, update_session
from .workflow_steps import match_region_boundary_step, prepare_lulc_year_step, run_invest_step


@dataclass(frozen=True)
class SessionRuntime:
    """状态机运行所需的外部配置，由 main.py 的 Settings 构造后注入。"""
    db_path: Path
    runs_dir: Path
    project_root: Path
    catalog_path: Path
    saga_cmd: str
    python_exe: str
    invest_work_dir: Path
    invest_config: Path
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    qgis_python_bat: str = r"D:\download\QGIS\bin\python-qgis-ltr.bat"


MODEL_LABELS = {"habitat_quality": "生境质量", "carbon_storage": "碳储量"}


def model_labels(models: list[str] | None) -> str:
    if not models:
        return "未选择"
    return "、".join(MODEL_LABELS.get(m, m) for m in models)


def assistant_message(
    content: str,
    *,
    type: Literal[
        "text", "action_progress", "action_done",
        "confirm_card", "workflow_progress", "report", "config_download",
    ] = "text",
    extra: dict | None = None,
) -> ChatMessage:
    return ChatMessage(role="assistant", type=type, content=content, extra=extra or {})


def user_message(content: str) -> ChatMessage:
    return ChatMessage(role="user", content=content)


# ── 会话创建 ─────────────────────────────────────────────────────────────────

async def start_session(runtime: SessionRuntime, *, prefill: PartialPlan | None = None) -> Session:
    prefill_obj = prefill or PartialPlan()
    if prefill_obj.models:
        initial_state: SessionState = "ASK_REGION"
        initial_plan = PartialPlan(models=prefill_obj.models)
        first_reply = assistant_message(
            f"好的，您选择了{model_labels(prefill_obj.models)}模型。请问您想分析哪个地区？"
        )
    else:
        initial_state = "INTENT"
        initial_plan = PartialPlan()
        first_reply = assistant_message("您好，我是EcoInvest-GPT智能分析助手")
    session = create_session(runtime.db_path, initial_state=initial_state, prefill=prefill_obj)
    return update_session(runtime.db_path, session.id, messages=[first_reply], plan=initial_plan)


# ── 状态机主入口 ─────────────────────────────────────────────────────────────

async def handle_user_message(
    runtime: SessionRuntime, *, session_id: str, text: str,
) -> SendMessageResponse:
    session = get_session(runtime.db_path, session_id)
    messages = session.messages + [user_message(text)]

    if session.state == "INTENT":
        session, new_messages, pending = await _handle_intent(runtime, session, text)
    elif session.state == "ASK_REGION":
        session, new_messages, pending = await _handle_region(runtime, session, text)
    elif session.state == "ASK_YEAR":
        session, new_messages, pending = await _handle_year(runtime, session, text)
    elif session.state == "ASK_MODEL":
        session, new_messages, pending = await _handle_model(runtime, session, text)
    elif session.state == "CONFIRM":
        session, new_messages, pending = await _handle_confirm(runtime, session, text)
    elif session.state == "RUNNING":
        new_messages = [assistant_message("当前任务正在运行中，请稍候。")]
        pending = False
    elif session.state == "DONE":
        session, new_messages, pending = await _handle_done(runtime, session, text)
    elif session.state == "ERROR":
        new_messages = [assistant_message("当前会话已出错，请新建会话后重试。")]
        pending = False
    else:
        new_messages = [assistant_message("我暂时无法理解当前状态，请新建会话后重试。")]
        pending = False

    updated = update_session(
        runtime.db_path, session.id,
        state=session.state, messages=messages + new_messages,
        plan=session.plan, artifacts=session.artifacts,
        job_id=session.job_id if session.job_id is not None else ...,
    )
    return SendMessageResponse(
        session_id=updated.id, state=updated.state,
        new_messages=new_messages, plan=updated.plan, pending_action=pending,
    )

# ── InVEST 后台任务 ───────────────────────────────────────────────────────────

async def run_invest_background(runtime: SessionRuntime, *, session_id: str) -> None:
    """后台异步执行 InVEST，完成后更新会话状态并追加报告消息。

    由 FastAPI BackgroundTasks 调用：HTTP 响应已发出后才开始执行。
    前端轮询 GET /api/sessions/{id} 感知 RUNNING → DONE 的状态变化。
    """
    session = get_session(runtime.db_path, session_id)
    plan = session.plan

    if not plan.is_complete():
        _append_error(runtime, session, "参数不完整，无法运行 InVEST。")
        return
    if not plan.models:
        _append_error(runtime, session, "未选择模型，无法运行 InVEST。")
        return

    update_session(
        runtime.db_path, session_id,
        state="RUNNING",
        messages=session.messages,
    )

    try:
        # asyncio.to_thread 把同步的 InVEST 执行放到线程池，不阻塞事件循环
        invest_result = await asyncio.to_thread(
            run_invest_step,
            artifacts=session.artifacts,
            models=plan.models,
            region_name=plan.region_name or plan.region_code or "",
            year=plan.year or 2023,
            project_root=runtime.project_root,
            catalog_path=runtime.catalog_path,
            invest_work_dir=runtime.invest_work_dir,
            invest_config=runtime.invest_config,
            python_exe=runtime.python_exe,
            qgis_python_bat=runtime.qgis_python_bat,
        )
    except Exception as exc:
        _append_error(runtime, session, f"InVEST 运行失败：{str(exc)[:500]}")
        return

    fresh_session = get_session(runtime.db_path, session_id)
    output_images = invest_result.get("output_images", [])

    done_msg = assistant_message(
        f"InVEST {model_labels(plan.models)}模块运行已完成。",
        type="action_done",
        extra={
            "images": output_images,
            "invest_result": invest_result,
            "year": plan.year or "",
            "region_name": plan.region_name or "",
            "parent_city": plan.parent_city or "",
        },
    )

    output_dir = (
        Path(session.artifacts.session_dir)
        if session.artifacts.session_dir
        else runtime.runs_dir / "sessions" / session_id
    )
    config_path = write_session_config(session, output_dir)
    config_msg = assistant_message(
        "已生成本次分析的可复用配置文件：session_config.json。",
        type="config_download",
        extra={"filename": config_path.name, "path": str(config_path)},
    )

    update_session(
        runtime.db_path, session_id,
        state="DONE",
        messages=fresh_session.messages + [done_msg, config_msg],
    )


def _append_error(runtime: SessionRuntime, session: Session, text: str) -> None:
    fresh = get_session(runtime.db_path, session.id)
    update_session(
        runtime.db_path, session.id,
        state="ERROR",
        messages=fresh.messages + [assistant_message(text)],
    )


# ── 各状态处理函数 ────────────────────────────────────────────────────────────

async def _handle_done(runtime: SessionRuntime, session: Session, text: str) -> tuple[Session, list[ChatMessage], bool]:
    report_keywords = r"报告|分析|结果|总结|说明|解读|评估|查看|给我|生成"
    wants_report = bool(re.search(report_keywords, text))

    if not wants_report and runtime.llm_api_key:
        system = "判断用户是否在请求查看分析报告或结果说明。只输出 JSON：{\"wants_report\": true} 或 {\"wants_report\": false}。"
        try:
            content = await _call_llm(
                base_url=runtime.llm_base_url, api_key=runtime.llm_api_key,
                model=runtime.llm_model, system=system, user=f"用户输入：{text}",
            )
            parsed = json.loads(_strip_code_fence(content))
            wants_report = bool(parsed.get("wants_report", False))
        except Exception:
            pass

    if not wants_report:
        return (
            session,
            [assistant_message("模型已运行完成。如需查看分析报告，请告诉我。")],
            False,
        )

    invest_result = {}
    for msg in reversed(session.messages):
        if msg.type == "action_done" and msg.extra.get("invest_result"):
            invest_result = msg.extra["invest_result"]
            break

    report_text = await llm_generate_report(
        invest_result, session.plan,
        base_url=runtime.llm_base_url,
        api_key=runtime.llm_api_key,
        model=runtime.llm_model,
    )
    return (
        session,
        [assistant_message(report_text, type="report")],
        False,
    )


async def _handle_intent(runtime: SessionRuntime, session: Session, text: str) -> tuple[Session, list[ChatMessage], bool]:
    intent = await llm_detect_intent(
        text, base_url=runtime.llm_base_url, api_key=runtime.llm_api_key, model=runtime.llm_model,
    )
    if intent != "invest_analysis":
        return (
            session.model_copy(update={"state": "INTENT"}),
            [assistant_message("我目前主要支持 InVEST 生态模型智能化分析。您可以说：我想进行 InVEST 模型分析。")],
            False,
        )
    return (
        session.model_copy(update={"state": "ASK_REGION"}),
        [assistant_message("好的，请问您想分析哪个地区？")],
        False,
    )


async def _handle_region(runtime: SessionRuntime, session: Session, text: str) -> tuple[Session, list[ChatMessage], bool]:
    extracted = await llm_extract_region(
        text, base_url=runtime.llm_base_url, api_key=runtime.llm_api_key, model=runtime.llm_model,
    )
    if not extracted:
        return (
            session.model_copy(update={"state": "ASK_REGION"}),
            [assistant_message("暂时没有识别到支持的地区，请重新输入地区名称（如：安吉县、杭州市、南京市等）。")],
            False,
        )
    region_code, region_name = extracted
    # 从 catalog 中补充上级城市信息，用于前端展示
    parent_city = SUPPORTED_REGIONS.get(region_code, {}).get("parent_city", "")
    next_plan = session.plan.model_copy(update={
        "region_code": region_code,
        "region_name": region_name,
        "parent_city": parent_city,
    })
    return (
        session.model_copy(update={"state": "ASK_YEAR", "plan": next_plan}),
        [assistant_message(f"好的，请问您需要哪一年的基础数据？")],
        False,
    )


async def _handle_year(runtime: SessionRuntime, session: Session, text: str) -> tuple[Session, list[ChatMessage], bool]:
    year = await llm_extract_year(
        text, base_url=runtime.llm_base_url, api_key=runtime.llm_api_key, model=runtime.llm_model,
    )
    if year is None:
        return (
            session.model_copy(update={"state": "ASK_YEAR"}),
            [assistant_message("没有识别到有效年份。请输入 2019、2020、2021、2022 或 2023。")],
            False,
        )
    if not session.plan.region_code:
        return (
            session.model_copy(update={"state": "ASK_REGION"}),
            [assistant_message("还没有识别地区，请先告诉我想分析哪个地区。")],
            False,
        )

    next_plan = session.plan.model_copy(update={"year": year})
    session_dir = runtime.runs_dir / "sessions" / session.id
    try:
        matched = match_region_boundary_step(
            region_code=session.plan.region_code, region_name=session.plan.region_name,
            year=year, catalog_path=runtime.catalog_path, project_root=runtime.project_root,
        )
        artifacts = prepare_lulc_year_step(
            matched=matched, session_dir=session_dir,
            project_root=runtime.project_root, catalog_path=runtime.catalog_path,
            saga_cmd=runtime.saga_cmd, python_exe=runtime.python_exe,
            qgis_python_bat=runtime.qgis_python_bat,
        )
    except Exception as exc:
        return (
            session.model_copy(update={"state": "ERROR"}),
            [assistant_message(f"年份数据准备失败：{str(exc)[:500]}")],
            False,
        )

    parent_city = next_plan.parent_city or ""
    full_region = f"{parent_city}{next_plan.region_name or ''}"
    action_done = assistant_message(
        f"已为您匹配 {year} 年{full_region}土地利用数据，并完成裁剪与重分类。",
        type="action_done",
        extra={
            "images": [p for p in [artifacts.clip_preview, artifacts.reclass_preview] if p],
            "files": [artifacts.boundary_shp, artifacts.lulc_raster, artifacts.clipped_tif, artifacts.reclass_tif],
            "year": year,
            "region_name": next_plan.region_name or "",
            "parent_city": parent_city,
        },
    )
    if next_plan.models:
        return (
            session.model_copy(update={"state": "CONFIRM", "plan": next_plan, "artifacts": artifacts}),
            [action_done, _build_confirm_message(next_plan, artifacts)],
            False,
        )
    return (
        session.model_copy(update={"state": "ASK_MODEL", "plan": next_plan, "artifacts": artifacts}),
        [action_done, assistant_message("请问您想运行哪个模块？")],
        False,
    )


async def _handle_model(runtime: SessionRuntime, session: Session, text: str) -> tuple[Session, list[ChatMessage], bool]:
    models = await llm_extract_models(
        text, base_url=runtime.llm_base_url, api_key=runtime.llm_api_key, model=runtime.llm_model,
    )
    if not models:
        return (
            session.model_copy(update={"state": "ASK_MODEL"}),
            [assistant_message("没有识别到模型。请输入：生境质量、碳储量，或两个都要。")],
            False,
        )
    next_plan = session.plan.model_copy(update={"models": models})
    return (
        session.model_copy(update={"state": "CONFIRM", "plan": next_plan}),
        [_build_confirm_message(next_plan, session.artifacts)],
        False,
    )


async def _handle_confirm(runtime: SessionRuntime, session: Session, text: str) -> tuple[Session, list[ChatMessage], bool]:
    confirmed = await llm_detect_confirm(
        text, base_url=runtime.llm_base_url, api_key=runtime.llm_api_key, model=runtime.llm_model,
    )
    if not confirmed:
        reset_plan = PartialPlan(models=session.prefill.models)
        return (
            session.model_copy(update={"state": "ASK_REGION", "plan": reset_plan, "artifacts": SessionArtifacts()}),
            [assistant_message("好的，我们重新填写参数。请问您想分析哪个地区？")],
            False,
        )
    if not session.plan.is_complete():
        return (
            session.model_copy(update={"state": "ERROR"}),
            [assistant_message("参数还没有收集完整，无法开始运行。请新建会话后重试。")],
            False,
        )

    next_session = session.model_copy(update={"state": "RUNNING"})

    return (
        next_session,
        [
            assistant_message(
                f"已确认参数，正在运行 InVEST {model_labels(session.plan.models)}模块，请稍候…"
            ),
        ],
        True,
    )


def _build_confirm_message(plan: PartialPlan, artifacts: SessionArtifacts) -> ChatMessage:
    parent_city = plan.parent_city or ""
    region = f"{parent_city}{plan.region_name or plan.region_code or '未识别'}"
    year = plan.year or "未识别"
    models = model_labels(plan.models)
    content = (
        "请确认以下分析参数：\n"
        f"地区：{region}\n年份：{year}\n模型：{models}\n"
        "确认后将使用已匹配/处理的数据开始运行模型。"
    )
    return assistant_message(
        content,
        type="confirm_card",
        extra={"region": region, "year": year, "models": plan.models or [], "artifacts": artifacts.model_dump()},
    )
