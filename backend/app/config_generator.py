from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Session


CONFIG_VERSION = "1.0"


MODEL_LABELS = {
    "habitat_quality": "生境质量",
    "carbon_storage": "碳储量",
}


def build_session_config(session: Session) -> dict[str, Any]:
    """把一个 Session 转换成可复用的配置字典。

    这个 config 的意义：
    - 记录用户在多轮对话中选择的所有参数。
    - 记录后端每一步产生的数据文件路径。
    - 其他人拿到 config 后，不需要重新问答，可以直接复现或继续运行。
    """
    models = session.plan.models or []
    return {
        "version": CONFIG_VERSION,
        "created_at": datetime.utcnow().isoformat(),
        "session_id": session.id,
        "state": session.state,
        "region": {
            "code": session.plan.region_code,
            "name": session.plan.region_name,
        },
        "year": session.plan.year,
        "models": [
            {"id": model_id, "label": MODEL_LABELS.get(model_id, model_id)}
            for model_id in models
        ],
        "data": {
            "boundary_shp": session.artifacts.boundary_shp,
            "lulc_raster": session.artifacts.lulc_raster,
            "clipped_tif": session.artifacts.clipped_tif,
            "reclass_tif": session.artifacts.reclass_tif,
            "clip_preview": session.artifacts.clip_preview,
            "reclass_preview": session.artifacts.reclass_preview,
            "session_dir": session.artifacts.session_dir,
        },
        "job": {
            "job_id": session.job_id,
        },
        "reuse_notes": [
            "本配置文件记录了本次多轮问答确定的地区、年份、模型和中间数据产物。",
            "如需复用，可在后续接口 /api/sessions/from-config 中传入该 JSON。",
            "如果文件路径移动或数据被删除，需要重新执行数据匹配、裁剪和重分类步骤。",
        ],
    }


def write_session_config(session: Session, output_dir: Path) -> Path:
    """生成 session_config.json，并返回文件路径。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "session_config.json"
    payload = build_session_config(session)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
