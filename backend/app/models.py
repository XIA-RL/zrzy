from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Session 状态机的所有合法状态 ──────────────────────────────────────────────
# Literal 枚举：赋予非法值时 Pydantic 直接报错，比用裸字符串更安全
SessionState = Literal[
    "GREETING",    # 初始问候，LM 说欢迎语
    "INTENT",      # 识别用户意图（是否要跑 InVEST 分析）
    "ASK_REGION",  # 询问地区
    "ASK_YEAR",    # 询问年份（同时触发 SAGA 裁剪/重分类）
    "ASK_MODEL",   # 询问模型（生境质量/碳储量/两个都要）
    "CONFIRM",     # 展示确认卡片，等用户确认
    "RUNNING",     # InVEST 后台运行中
    "DONE",        # 全部完成，输出报告
    "ERROR",       # 流程出错
]

# 消息类型：决定前端用哪种组件渲染这条消息
MessageType = Literal[
    "text",              # 普通文字气泡（默认）
    "action_progress",   # 后端正在执行（SAGA 裁剪中…）
    "action_done",       # 后端执行完成，附带缩略图
    "confirm_card",      # 参数确认卡片，有"确认"/"重填"按钮
    "workflow_progress", # InVEST 工作流步骤时间线
    "report",            # LM 生成的自然语言分析报告
    "config_download",   # session_config.json 下载链接
]


# ── 现有 Job 相关模型（保持不变）─────────────────────────────────────────────

JobStatus = Literal["queued", "running", "done", "failed"]


class CreateJobRequest(BaseModel):
    text: str = Field(min_length=1, description="用户的一句话")


class Plan(BaseModel):
    region_code: str
    region_name: str | None = None
    year: int = 2023
    models: list[Literal["habitat_quality", "carbon_storage"]] = Field(default_factory=list)
    notes: str | None = None


StepStatus = Literal["pending", "running", "done", "failed", "skipped"]


class WorkflowStep(BaseModel):
    id: str
    title: str
    status: StepStatus = "pending"
    message: str | None = None
    files: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)


class Job(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: JobStatus
    stage: str
    input_text: str
    plan: Plan | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[str] = Field(default_factory=list)


# ── Session 相关模型 ───────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """对话里的一条消息。"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    role: Literal["user", "assistant"]
    type: MessageType = "text"
    content: str
    # 附加数据，不同 type 携带不同内容：
    #   action_done     → {"images": [...], "files": [...]}
    #   confirm_card    → {"region": ..., "year": ..., "models": [...]}
    #   config_download → {"filename": "session_config.json"}
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PartialPlan(BaseModel):
    """逐步收集中的分析参数，所有字段可选（None = 尚未收集到）。"""
    region_code: str | None = None
    region_name: str | None = None
    parent_city: str | None = None   # 上级城市，如"常州市"
    year: int | None = None
    models: list[Literal["habitat_quality", "carbon_storage"]] | None = None

    def is_complete(self) -> bool:
        """判断参数是否已全部收集齐。"""
        return (
            self.region_code is not None
            and self.year is not None
            and self.models is not None
            and len(self.models) > 0
        )

    def to_plan(self) -> Plan:
        """参数收集完毕后转换成正式的 Plan 对象，调用前应先确认 is_complete()。"""
        return Plan(
            region_code=self.region_code or "",
            region_name=self.region_name,
            year=self.year or 2023,
            models=self.models or [],
        )


class SessionArtifacts(BaseModel):
    """每个对话步骤产生的后端产物路径，供后续步骤直接取用。"""
    boundary_shp: str | None = None    # 地区边界 shp 路径（ASK_REGION 完成后保存）
    lulc_raster: str | None = None     # 原始 LULC 栅格路径（ASK_YEAR 完成后保存）
    clipped_tif: str | None = None     # SAGA 裁剪结果（ASK_YEAR 完成后保存）
    reclass_tif: str | None = None     # SAGA 重分类结果（ASK_YEAR 完成后保存）
    clip_preview: str | None = None    # 裁剪预览图文件名（用于前端展示）
    reclass_preview: str | None = None # 重分类预览图文件名
    session_dir: str | None = None     # 本会话的工作目录路径


class Session(BaseModel):
    """完整的对话会话对象。"""
    id: str
    created_at: datetime
    updated_at: datetime
    state: SessionState
    messages: list[ChatMessage] = Field(default_factory=list)
    plan: PartialPlan = Field(default_factory=PartialPlan)
    artifacts: SessionArtifacts = Field(default_factory=SessionArtifacts)
    job_id: str | None = None         # 确认执行后关联的 Job id
    prefill: PartialPlan = Field(default_factory=PartialPlan)  # 技术方案页带入的预填参数


# ── Session API 请求/响应模型 ─────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """POST /api/sessions 的请求体。"""
    # prefill 是可选的，技术方案页点击"运行模型"时传入
    prefill: PartialPlan | None = None


class SendMessageRequest(BaseModel):
    """POST /api/sessions/{id}/messages 的请求体。"""
    text: str = Field(min_length=1, description="用户输入的消息文字")


class SendMessageResponse(BaseModel):
    """POST /api/sessions/{id}/messages 的响应体。"""
    session_id: str
    state: SessionState
    # 本轮新增的 assistant 消息（可能有多条）
    new_messages: list[ChatMessage]
    # 当前收集到的参数（前端可用来更新进度提示）
    plan: PartialPlan
    # 是否有耗时后端动作正在异步执行（True 时前端需轮询 GET /api/sessions/{id}）
    pending_action: bool = False
