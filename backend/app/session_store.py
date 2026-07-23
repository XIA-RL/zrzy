from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .db import connect
from .models import (
    ChatMessage,
    PartialPlan,
    Session,
    SessionArtifacts,
    SessionState,
)


# ── 内部工具函数 ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串，SQLite 里统一用字符串存时间。"""
    return datetime.utcnow().isoformat()


def _row_to_session(row) -> Session:
    """把 SQLite 查询结果的一行（sqlite3.Row）转换成 Session 对象。

    这是"反序列化"：从数据库字符串 → Python 对象。
    每个 _json 字段都要先 json.loads，再用 Pydantic 的 model_validate 还原。
    """
    messages_raw = json.loads(row["messages_json"] or "[]")
    plan_raw = json.loads(row["plan_json"] or "{}")
    artifacts_raw = json.loads(row["artifacts_json"] or "{}")
    prefill_raw = json.loads(row["prefill_json"] or "{}")

    return Session(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        state=row["state"],
        messages=[ChatMessage.model_validate(m) for m in messages_raw],
        plan=PartialPlan.model_validate(plan_raw),
        artifacts=SessionArtifacts.model_validate(artifacts_raw),
        job_id=row["job_id"],
        prefill=PartialPlan.model_validate(prefill_raw),
    )


# ── 公开 CRUD 函数 ────────────────────────────────────────────────────────────

def create_session(
    db_path: Path,
    *,
    initial_state: SessionState = "GREETING",
    prefill: PartialPlan | None = None,
) -> Session:
    """创建一个新的会话，写入数据库并返回 Session 对象。

    参数：
        db_path:       SQLite 数据库文件路径
        initial_state: 初始状态，默认 GREETING；技术方案页传入 prefill 时会跳到 ASK_REGION
        prefill:       技术方案页带入的预填参数（如已知模型）
    """
    session_id = uuid.uuid4().hex
    now = _now_iso()
    prefill_obj = prefill or PartialPlan()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions
              (id, created_at, updated_at, state, messages_json,
               plan_json, artifacts_json, job_id, prefill_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                now,
                now,
                initial_state,
                "[]",
                "{}",
                "{}",
                None,
                prefill_obj.model_dump_json(),
            ),
        )
        conn.commit()

    return Session(
        id=session_id,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
        state=initial_state,
        messages=[],
        plan=PartialPlan(),
        artifacts=SessionArtifacts(),
        job_id=None,
        prefill=prefill_obj,
    )


def get_session(db_path: Path, session_id: str) -> Session:
    """根据 id 读取会话，不存在时抛出 KeyError。"""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

    if row is None:
        raise KeyError(f"session not found: {session_id}")

    return _row_to_session(row)


def update_session(
    db_path: Path,
    session_id: str,
    *,
    state: SessionState | None = None,
    messages: list[ChatMessage] | None = None,
    plan: PartialPlan | None = None,
    artifacts: SessionArtifacts | None = None,
    job_id: str | None = ...,  # type: ignore[assignment]
) -> Session:
    """更新会话的一个或多个字段，只传入需要修改的字段。

    job_id 用哨兵值 ... (Ellipsis) 区分"不传（不改）"和"传 None（清空）"。
    """
    session = get_session(db_path, session_id)
    now = _now_iso()

    new_state = state if state is not None else session.state
    new_messages = messages if messages is not None else session.messages
    new_plan = plan if plan is not None else session.plan
    new_artifacts = artifacts if artifacts is not None else session.artifacts
    # job_id 的特殊处理：Ellipsis 表示不改，None 表示清空，字符串表示设置新值
    new_job_id = session.job_id if job_id is ... else job_id  # type: ignore[comparison-overlap]

    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE sessions
            SET updated_at    = ?,
                state         = ?,
                messages_json = ?,
                plan_json     = ?,
                artifacts_json= ?,
                job_id        = ?
            WHERE id = ?
            """,
            (
                now,
                new_state,
                json.dumps(
                    [m.model_dump(mode="json") for m in new_messages],
                    ensure_ascii=False,
                ),
                new_plan.model_dump_json(),
                new_artifacts.model_dump_json(),
                new_job_id,
                session_id,
            ),
        )
        conn.commit()

    return Session(
        id=session_id,
        created_at=session.created_at,
        updated_at=datetime.fromisoformat(now),
        state=new_state,
        messages=new_messages,
        plan=new_plan,
        artifacts=new_artifacts,
        job_id=new_job_id,
        prefill=session.prefill,
    )


def append_messages(
    db_path: Path,
    session_id: str,
    new_messages: list[ChatMessage],
) -> Session:
    """向会话追加新消息，是 update_session 的快捷封装。

    追加而不是覆盖：先读出已有消息列表，再拼接新消息，再写回去。
    """
    session = get_session(db_path, session_id)
    return update_session(
        db_path,
        session_id,
        messages=session.messages + new_messages,
    )
