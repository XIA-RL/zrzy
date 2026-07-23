from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import load_settings
from .db import init_db
from .geo import (
    boundary_bounds,
    get_region_boundary_geojson,
    raster_bounds_wgs84,
    raster_image_coordinates,
)
from .jobs import create_job, get_job
from .models import CreateJobRequest, CreateSessionRequest, Job, SendMessageRequest, SendMessageResponse, Session
from .pipeline import run_job_pipeline
from .session import SessionRuntime, handle_user_message, run_invest_background, start_session
from .session_store import get_session


settings = load_settings()
init_db(settings.db_path)
settings.runs_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="zrzy-agent-backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    clip_ps1 = (settings.project_root / "gis" / "clip_anji_saga.ps1").resolve()
    if not clip_ps1.is_file():
        legacy_clip_ps1 = (settings.project_root.parent / "gis" / "clip_anji_saga.ps1").resolve()
        if legacy_clip_ps1.is_file():
            clip_ps1 = legacy_clip_ps1
    return {
        "ok": True,
        "mode": settings.pipeline_mode,
        "project_root": str(settings.project_root),
        "clip_script": str(clip_ps1),
        "clip_script_exists": clip_ps1.is_file(),
    }


def _session_runtime() -> SessionRuntime:
    return SessionRuntime(
        db_path=settings.db_path,
        runs_dir=settings.runs_dir,
        project_root=settings.project_root,
        catalog_path=settings.catalog_path,
        saga_cmd=settings.saga_cmd,
        python_exe=settings.python_exe,
        invest_work_dir=settings.invest_work_dir,
        invest_config=settings.invest_config,
        llm_base_url=settings.llm_base_url,
        llm_api_key=settings.llm_api_key,
        llm_model=settings.llm_model,
        qgis_python_bat=settings.qgis_python_bat,
    )


# ── Session API ───────────────────────────────────────────────────────────────

@app.post("/api/sessions", response_model=Session)
async def api_create_session(req: CreateSessionRequest) -> Session:
    return await start_session(_session_runtime(), prefill=req.prefill)


@app.get("/api/sessions/{session_id}", response_model=Session)
def api_get_session(session_id: str) -> Session:
    try:
        return get_session(settings.db_path, session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")


@app.post("/api/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def api_send_session_message(
    session_id: str,
    req: SendMessageRequest,
    background: BackgroundTasks,
) -> SendMessageResponse:
    """处理用户消息；pending_action=True 时自动启动 InVEST 后台任务。"""
    try:
        runtime = _session_runtime()
        result = await handle_user_message(runtime, session_id=session_id, text=req.text)
        if result.pending_action:
            background.add_task(run_invest_background, runtime, session_id=session_id)
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")


@app.get("/api/sessions/{session_id}/config")
def api_get_session_config(session_id: str) -> FileResponse:
    try:
        session = get_session(settings.db_path, session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    if not session.artifacts.session_dir:
        raise HTTPException(status_code=404, detail="session config not generated yet")
    path = (Path(session.artifacts.session_dir) / "session_config.json").resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="session config not found")
    return FileResponse(path, filename="session_config.json")


@app.get("/api/sessions/{session_id}/artifacts/{filename}/bounds")
def api_session_artifact_bounds(session_id: str, filename: str) -> dict:
    try:
        session = get_session(settings.db_path, session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    if not session.artifacts.session_dir:
        raise HTTPException(status_code=404, detail="session has no artifacts directory")
    session_dir = Path(session.artifacts.session_dir).resolve()
    return _artifact_bounds_payload(session_dir, filename)


@app.get("/api/sessions/{session_id}/artifacts/{filename}")
def api_get_session_artifact(session_id: str, filename: str) -> FileResponse:
    """提供 session 产物文件（裁剪图、重分类图、InVEST 成果图等）。"""
    try:
        session = get_session(settings.db_path, session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    if not session.artifacts.session_dir:
        raise HTTPException(status_code=404, detail="session has no artifacts directory")
    session_dir = Path(session.artifacts.session_dir).resolve()
    path = (session_dir / filename).resolve()
    if path.parent != session_dir:
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path)


def _artifact_bounds_payload(artifact_dir: Path, filename: str) -> dict:
    """根据产物目录中的文件（及配套 GeoTIFF）计算 Mapbox image 叠加所需 bounds。"""
    path = (artifact_dir / filename).resolve()
    if artifact_dir.resolve() not in path.parents and path.parent != artifact_dir.resolve():
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    suffix = path.suffix.lower()
    if suffix not in {".tif", ".tiff", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=400, detail="unsupported file type for bounds")
    try:
        if suffix in {".tif", ".tiff"}:
            tif_path = path
        else:
            name = path.name
            tif_candidates: list[Path] = [path.with_suffix(".tif")]
            if name.startswith("clip_") and name.endswith("_preview.png"):
                year = name[len("clip_"):-len("_preview.png")]
                tif_candidates.append(artifact_dir / f"CLCD_{year}_Anji.tif")
            elif name.startswith("lulc_") and name.endswith("_5class_map.png"):
                year = name[len("lulc_"):-len("_5class_map.png")]
                tif_candidates.append(artifact_dir / f"CLCD_{year}_Anji_5class.tif")
            elif name.startswith("habitat_quality_") and name.endswith("_map.png"):
                year = name[len("habitat_quality_"):-len("_map.png")]
                tif_candidates.append(artifact_dir / f"habitat_quality_{year}.tif")
            elif name.startswith("carbon_storage_") and name.endswith("_map.png"):
                year = name[len("carbon_storage_"):-len("_map.png")]
                tif_candidates.append(artifact_dir / f"carbon_storage_{year}.tif")
            elif name.endswith("_overlay.png"):
                for prefix, glob_pattern in [
                    ("clip_", "CLCD_{y}_*.tif"),
                    ("lulc_", "CLCD_{y}_*_5class.tif"),
                    ("habitat_quality_", "habitat_quality_{y}.tif"),
                    ("carbon_storage_", "carbon_storage_{y}.tif"),
                ]:
                    if name.startswith(prefix):
                        year = name[len(prefix):-len("_overlay.png")]
                        pattern = glob_pattern.format(y=year)
                        matches = sorted(artifact_dir.glob(pattern))
                        if matches:
                            tif_candidates.append(matches[0])
                        break
            tif_path = next((p for p in tif_candidates if p.is_file()), None)
            if not tif_path:
                raise FileNotFoundError("no companion GeoTIFF for bounds")
        coordinates = raster_image_coordinates(tif_path)
        bounds = raster_bounds_wgs84(tif_path)
        return {"filename": filename, "bounds": bounds, "coordinates": coordinates}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Job API ───────────────────────────────────────────────────────────────────

@app.post("/api/jobs", response_model=Job)
async def api_create_job(req: CreateJobRequest, background: BackgroundTasks) -> Job:
    job = create_job(settings.db_path, req.text)
    background.add_task(
        run_job_pipeline,
        job_id=job.id,
        input_text=req.text,
        db_path=settings.db_path,
        registry_dir=settings.region_registry_dir,
        runs_dir=settings.runs_dir,
        pipeline_mode=settings.pipeline_mode,
        llm_base_url=settings.llm_base_url,
        llm_api_key=settings.llm_api_key,
        llm_model=settings.llm_model,
        catalog_path=settings.catalog_path,
        project_root=settings.project_root,
        saga_cmd=settings.saga_cmd,
        python_exe=settings.python_exe,
        invest_work_dir=settings.invest_work_dir,
        invest_config=settings.invest_config,
        qgis_python_bat=settings.qgis_python_bat,
    )
    return job


@app.get("/api/jobs/{job_id}", response_model=Job)
def api_get_job(job_id: str) -> Job:
    try:
        return get_job(settings.db_path, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")


@app.get("/api/regions/{region_code}/boundary")
def api_region_boundary(region_code: str) -> dict:
    try:
        geojson = get_region_boundary_geojson(
            catalog_path=settings.catalog_path,
            region_code=region_code,
        )
        return {"region_code": region_code, "geojson": geojson, "bounds": boundary_bounds(geojson)}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/artifacts/{filename}/bounds")
def api_artifact_bounds(job_id: str, filename: str) -> dict:
    job_dir = (settings.runs_dir / job_id).resolve()
    return _artifact_bounds_payload(job_dir, filename)


@app.get("/api/jobs/{job_id}/artifacts/{filename}")
def api_get_artifact(job_id: str, filename: str) -> FileResponse:
    job_dir = settings.runs_dir / job_id
    path = (job_dir / filename).resolve()
    if job_dir.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path)

@app.get("/")
def root() -> dict:
    return {
        "service": "zrzy-agent-backend",
        "docs": "/docs",
        "health": "/health",
        "frontend": "http://127.0.0.1:5173",
    }
