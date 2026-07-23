from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    pipeline_mode: str

    llm_base_url: str
    llm_api_key: str
    llm_model: str

    region_registry_dir: Path
    runs_dir: Path
    db_path: Path
    catalog_path: Path
    project_root: Path

    saga_cmd: str
    python_exe: str
    qgis_python_bat: str
    invest_work_dir: Path
    invest_config: Path

    host: str
    port: int


def load_settings() -> Settings:
    load_dotenv(override=False)

    base_dir = Path(__file__).resolve().parents[1]
    workspace_root = base_dir.parent

    project_root_env = os.getenv("PROJECT_ROOT", "").strip()
    if project_root_env:
        project_root = Path(project_root_env).resolve()
    elif (base_dir / "gis").exists() or (base_dir / "invest").exists():
        project_root = base_dir
    else:
        project_root = workspace_root

    pipeline_mode = os.getenv("PIPELINE_MODE", "mock").strip().lower()

    llm_base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip()
    llm_api_key = os.getenv("LLM_API_KEY", "").strip()
    llm_model = os.getenv("LLM_MODEL", "deepseek-chat").strip()

    region_registry_dir = Path(os.getenv("REGION_REGISTRY_DIR", "regions"))
    if not region_registry_dir.is_absolute():
        region_registry_dir = (base_dir / region_registry_dir).resolve()

    runs_dir = Path(os.getenv("RUNS_DIR", "runs"))
    if not runs_dir.is_absolute():
        runs_dir = (base_dir / runs_dir).resolve()

    db_path = Path(os.getenv("DB_PATH", "app.db"))
    if not db_path.is_absolute():
        db_path = (base_dir / db_path).resolve()

    catalog_path = Path(os.getenv("DATA_CATALOG", "data/catalog.json"))
    if not catalog_path.is_absolute():
        catalog_path = (base_dir / catalog_path).resolve()

    saga_cmd = os.getenv("SAGA_CMD", r"D:\download\SAGA 9.12.0\saga_cmd.exe").strip()

    python_exe = os.getenv("PYTHON_EXE", sys.executable).strip()
    if not python_exe:
        python_exe = sys.executable
    if os.name == "nt":
        conda_py = Path(r"C:\Miniconda3\python.exe")
        if conda_py.is_file() and not Path(python_exe).is_file():
            python_exe = str(conda_py)

    qgis_python_bat = os.getenv(
        "QGIS_PYTHON_BAT",
        r"D:\download\QGIS\bin\python-qgis-ltr.bat",
    ).strip()

    invest_work_dir = Path(os.getenv("INVEST_WORK_DIR", "D:/invest"))
    invest_config_env = os.getenv("INVEST_CONFIG", "").strip()
    invest_config = Path(invest_config_env or "invest/config_anji_hq.json")
    if not invest_config.is_absolute():
        normalized = Path(*[part for part in invest_config.parts if part != ".."])
        candidates = [
            (project_root / invest_config).resolve(),
            (base_dir / invest_config).resolve(),
            (workspace_root / invest_config).resolve(),
            (project_root / normalized).resolve(),
            (base_dir / normalized).resolve(),
            (workspace_root / normalized).resolve(),
        ]
        invest_config = next((path for path in candidates if path.is_file()), candidates[0])

    host = os.getenv("HOST", "127.0.0.1").strip()
    port = int(os.getenv("PORT", "8000"))

    return Settings(
        pipeline_mode=pipeline_mode,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        region_registry_dir=region_registry_dir,
        runs_dir=runs_dir,
        db_path=db_path,
        catalog_path=catalog_path,
        project_root=project_root,
        saga_cmd=saga_cmd,
        python_exe=python_exe,
        qgis_python_bat=qgis_python_bat,
        invest_work_dir=invest_work_dir,
        invest_config=invest_config,
        host=host,
        port=port,
    )
