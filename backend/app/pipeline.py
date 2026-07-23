from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .data_catalog import match_data
from .jobs import update_job
from .llm import llm_plan
from .models import Plan
from .workflow import initial_steps, run_real_workflow_sync


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


async def _run_mock_pipeline(
    *,
    job_id: str,
    plan: Plan,
    db_path: Path,
    job_dir: Path,
    registry_dir: Path,
) -> None:
    steps = initial_steps()
    update_job(db_path, job_id, steps=steps)

    from .regions import load_region

    reg = load_region(registry_dir, plan.region_code)

    async def done_step(step_id: str, message: str, **kwargs) -> None:
        nonlocal steps
        idx = next(i for i, s in enumerate(steps) if s.id == step_id)
        steps[idx] = steps[idx].model_copy(update={"status": "running", "message": message})
        update_job(db_path, job_id, steps=steps)
        await asyncio.sleep(0.5)
        steps[idx] = steps[idx].model_copy(update={"status": "done", "message": message, **kwargs})
        update_job(db_path, job_id, steps=steps)
        await asyncio.sleep(0.35)

    model_labels = []
    if "habitat_quality" in plan.models:
        model_labels.append("生境质量")
    if "carbon_storage" in plan.models:
        model_labels.append("碳储量")
    await done_step(
        "parse",
        f"地区：{plan.region_name}；年份：{plan.year}；"
        f"模型：{'、'.join(model_labels) or '未指定'}（演示）",
    )
    await done_step(
        "data_match",
        "已匹配示例数据文件（mock 模式）",
        files=[
            f"CLCD_v01_{plan.year}_albert_zhejiang.tif",
            "BOUNT_poly.shp",
            "安吉县威胁表格.csv",
            "安吉县敏感性表格.csv",
            "碳密度表格.csv",
        ],
    )
    await done_step("clip", "裁剪完成（mock）", images=[])
    await done_step("reclass", "重分类完成（mock）", images=[])
    await done_step("invest", "InVEST 分析完成（mock）")
    await done_step("final_map", "成果图已生成（mock）", images=[])

    result = {
        "mode": "mock",
        "region": {"code": reg.region_code, "name": reg.region_name},
        "year": plan.year,
        "models": plan.models,
        "summary": {
            "habitat_quality": {"mean": 0.76, "level": "较好(示例)"}
            if "habitat_quality" in plan.models
            else None,
            "carbon_storage": {"total_MgC": 19361599.27, "note": "示例值"}
            if "carbon_storage" in plan.models
            else None,
        },
        "note": "将 PIPELINE_MODE 设为 real 并配置 SAGA/InVEST 路径后可执行真实流程",
    }
    (job_dir / "plan.json").write_text(plan.model_dump_json(ensure_ascii=False, indent=2), encoding="utf-8")
    (job_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts = ["plan.json", "result.json"]
    update_job(
        db_path,
        job_id,
        status="done",
        stage="done",
        result=result,
        artifacts=artifacts,
        steps=steps,
    )


async def run_job_pipeline(
    *,
    job_id: str,
    input_text: str,
    db_path: Path,
    registry_dir: Path,
    runs_dir: Path,
    pipeline_mode: str,
    llm_base_url: str,
    llm_api_key: str,
    llm_model: str,
    catalog_path: Path,
    project_root: Path,
    saga_cmd: str,
    python_exe: str,
    invest_work_dir: Path,
    invest_config: Path,
    qgis_python_bat: str | None = None,
) -> None:
    job_dir = runs_dir / job_id
    _ensure_dir(job_dir)

    try:
        update_job(db_path, job_id, status="running", stage="parse", steps=initial_steps())

        plan: Plan = await llm_plan(
            text=input_text,
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=llm_model,
        )
        update_job(db_path, job_id, plan=plan, stage="parse")

        if pipeline_mode == "mock":
            update_job(db_path, job_id, stage="mock_run")
            await _run_mock_pipeline(
                job_id=job_id,
                plan=plan,
                db_path=db_path,
                job_dir=job_dir,
                registry_dir=registry_dir,
            )
            return

        update_job(db_path, job_id, stage="workflow")

        def _run_sync() -> tuple[dict, list[str], list]:
            return run_real_workflow_sync(
                job_id=job_id,
                input_text=input_text,
                plan=plan,
                db_path=db_path,
                job_dir=job_dir,
                project_root=project_root,
                catalog_path=catalog_path,
                saga_cmd=saga_cmd,
                python_exe=python_exe,
                invest_work_dir=invest_work_dir,
                invest_config=invest_config,
                qgis_python_bat=qgis_python_bat,
            )

        result, artifacts, steps = await asyncio.to_thread(_run_sync)
        update_job(
            db_path,
            job_id,
            status="done",
            stage="done",
            plan=plan,
            steps=steps,
            result=result,
            artifacts=artifacts,
        )

    except Exception as e:
        from .jobs import get_job

        try:
            job = get_job(db_path, job_id)
            steps = job.steps
            for i, s in enumerate(steps):
                if s.status == "running":
                    steps[i] = s.model_copy(
                        update={"status": "failed", "message": str(e)[:500]}
                    )
            update_job(db_path, job_id, status="failed", stage="failed", error=str(e), steps=steps)
        except Exception:
            update_job(db_path, job_id, status="failed", stage="failed", error=str(e))
