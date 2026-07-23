from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .db import connect
from .models import Job, JobStatus, Plan, WorkflowStep


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(value: str) -> datetime:
    # sqlite stores ISO string
    return datetime.fromisoformat(value)


def create_job(db_path: Path, input_text: str) -> Job:
    job_id = str(uuid4())
    now = _utcnow()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, created_at, updated_at, status, stage, input_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, _dt_to_str(now), _dt_to_str(now), "queued", "queued", input_text),
        )
        conn.commit()

    from .workflow import initial_steps

    update_job(db_path, job_id, steps=initial_steps())
    return get_job(db_path, job_id)


def update_job(
    db_path: Path,
    job_id: str,
    *,
    status: JobStatus | None = None,
    stage: str | None = None,
    plan: Plan | None = None,
    steps: list[WorkflowStep] | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    artifacts: list[str] | None = None,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [_dt_to_str(_utcnow())]

    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if stage is not None:
        fields.append("stage = ?")
        values.append(stage)
    if plan is not None:
        fields.append("plan_json = ?")
        values.append(plan.model_dump_json(ensure_ascii=False))
    if steps is not None:
        fields.append("steps_json = ?")
        values.append(
            json.dumps([s.model_dump() for s in steps], ensure_ascii=False)
        )
    if result is not None:
        fields.append("result_json = ?")
        values.append(json.dumps(result, ensure_ascii=False))
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if artifacts is not None:
        fields.append("artifacts_json = ?")
        values.append(json.dumps(artifacts, ensure_ascii=False))

    values.append(job_id)

    with connect(db_path) as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()


def get_job(db_path: Path, job_id: str) -> Job:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"job not found: {job_id}")

    plan = Plan.model_validate_json(row["plan_json"]) if row["plan_json"] else None
    steps: list[WorkflowStep] = []
    if row["steps_json"]:
        steps = [WorkflowStep.model_validate(s) for s in json.loads(row["steps_json"])]
    result = json.loads(row["result_json"]) if row["result_json"] else None
    artifacts = json.loads(row["artifacts_json"]) if row["artifacts_json"] else []

    return Job(
        id=row["id"],
        created_at=_str_to_dt(row["created_at"]),
        updated_at=_str_to_dt(row["updated_at"]),
        status=row["status"],
        stage=row["stage"],
        input_text=row["input_text"],
        plan=plan,
        steps=steps,
        result=result,
        error=row["error"],
        artifacts=artifacts,
    )
