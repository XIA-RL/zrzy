from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .data_catalog import MatchedData, load_catalog, match_data, resolve_invest_config_path
from .jobs import update_job
from .map_standard import inject_qgis_env, legend_title, render_product_map
from .models import Plan, SessionArtifacts, WorkflowStep


WORKFLOW_STEPS: list[tuple[str, str]] = [
    ("parse", "需求解析"),
    ("data_match", "数据匹配"),
    ("clip", "SAGA 裁剪"),
    ("reclass", "SAGA 重分类与制图"),
    ("invest", "InVEST 模型分析"),
    ("final_map", "成果制图"),
]


def initial_steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(id=sid, title=title, status="pending")
        for sid, title in WORKFLOW_STEPS
    ]


def _step_index(steps: list[WorkflowStep], step_id: str) -> int:
    for i, s in enumerate(steps):
        if s.id == step_id:
            return i
    raise KeyError(step_id)


def _persist_steps(db_path: Path, job_id: str, steps: list[WorkflowStep]) -> None:
    update_job(db_path, job_id, steps=steps)


def _set_step(
    db_path: Path,
    job_id: str,
    steps: list[WorkflowStep],
    step_id: str,
    *,
    status: str,
    message: str | None = None,
    files: list[str] | None = None,
    images: list[str] | None = None,
) -> list[WorkflowStep]:
    idx = _step_index(steps, step_id)
    cur = steps[idx]
    steps[idx] = cur.model_copy(
        update={
            "status": status,
            "message": message if message is not None else cur.message,
            "files": files if files is not None else cur.files,
            "images": images if images is not None else cur.images,
        }
    )
    _persist_steps(db_path, job_id, steps)
    return steps


def _run_cmd(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    # Windows 下 PowerShell 输出多为 GBK，用 utf-8 解码会变成乱码
    enc = "gbk" if os.name == "nt" else "utf-8"

    # 确保 GDAL/PROJ 数据目录被传入子进程
    # conda 环境激活时会设置这些变量，但以子进程方式调用时可能丢失
    if env is None:
        env = os.environ.copy()
    _inject_gdal_env(env, cmd)

    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        encoding=enc,
        errors="replace",
    )
    if proc.returncode != 0:
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        detail = (stderr + "\n" + stdout).strip()
        tail = detail[-2000:] if len(detail) > 2000 else detail
        raise RuntimeError(tail or f"命令失败: {' '.join(cmd)}")


def _inject_gdal_env(env: dict[str, str], cmd: list[str]) -> None:
    """根据调用的 python_exe 推断 conda 环境根目录，自动补全 GDAL_DATA / PROJ_DATA。

    只在这两个变量未设置时才注入，避免覆盖用户已有的配置。
    """
    if env.get("GDAL_DATA") and env.get("PROJ_DATA"):
        return

    # 从命令里找 python.exe 路径，推断 conda env prefix
    python_exe = next(
        (Path(p) for p in cmd if p.lower().endswith("python.exe") or p.lower().endswith("python")),
        None,
    )
    if python_exe is None:
        return

    # conda env prefix 通常是 python.exe 的父目录
    prefix = python_exe.parent
    # Windows conda env 结构：{prefix}\python.exe 或 {prefix}\Scripts\python.exe
    if prefix.name.lower() == "scripts":
        prefix = prefix.parent

    gdal_data = prefix / "Library" / "share" / "gdal"
    proj_data = prefix / "Library" / "share" / "proj"
    lib_bin   = prefix / "Library" / "bin"

    if gdal_data.is_dir() and not env.get("GDAL_DATA"):
        env["GDAL_DATA"] = str(gdal_data)
    if proj_data.is_dir() and not env.get("PROJ_DATA"):
        env["PROJ_DATA"] = str(proj_data)
    # rasterio/GDAL 的动态库在 Library/bin，必须在 PATH 最前面
    if lib_bin.is_dir():
        existing_path = env.get("PATH", "")
        lib_bin_str = str(lib_bin)
        if lib_bin_str not in existing_path:
            env["PATH"] = lib_bin_str + os.pathsep + existing_path


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if src.is_file():
        shutil.copy2(src, dst)
        return True
    return False


def _resolve_script(project_root: Path, catalog_path: Path, key: str) -> Path:
    catalog = load_catalog(catalog_path)
    rel = catalog["scripts"][key]
    rel_path = Path(rel)
    normalized = Path(*[part for part in rel_path.parts if part != ".."])
    candidates = [
        (project_root / rel_path).resolve(),
        (project_root / normalized).resolve(),
        (project_root.parent / normalized).resolve(),
    ]
    if normalized.parts and normalized.parts[0] == "backend":
        candidates.append((project_root / Path(*normalized.parts[1:])).resolve())

    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"脚本不存在: {rel}（project_root={project_root}，已检查: "
        + ", ".join(str(p) for p in candidates)
        + "）"
    )


def _job_artifacts(job_dir: Path) -> list[str]:
    names = []
    for p in sorted(job_dir.iterdir()):
        if p.is_file():
            names.append(p.name)
    return names


def run_real_workflow_sync(
    *,
    job_id: str,
    input_text: str,
    plan: Plan,
    db_path: Path,
    job_dir: Path,
    project_root: Path,
    catalog_path: Path,
    saga_cmd: str,
    python_exe: str,
    invest_work_dir: Path,
    invest_config: Path,
    qgis_python_bat: str | None = None,
) -> dict[str, Any]:
    steps = initial_steps()
    _persist_steps(db_path, job_id, steps)
    artifacts: list[str] = []

    # --- 1. 需求解析 ---
    steps = _set_step(
        db_path,
        job_id,
        steps,
        "parse",
        status="running",
    )
    plan_payload = plan.model_dump()
    (job_dir / "plan.json").write_text(
        json.dumps(plan_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    model_labels = []
    if "habitat_quality" in plan.models:
        model_labels.append("生境质量")
    if "carbon_storage" in plan.models:
        model_labels.append("碳储量")
    parse_msg = (
        f"地区：{plan.region_name or plan.region_code}；"
        f"年份：{plan.year}；"
        f"模型：{'、'.join(model_labels) or '未指定'}"
    )
    steps = _set_step(db_path, job_id, steps, "parse", status="done", message=parse_msg)
    artifacts.append("plan.json")

    # --- 2. 数据匹配 ---
    steps = _set_step(db_path, job_id, steps, "data_match", status="running")
    matched: MatchedData = match_data(
        catalog_path=catalog_path, plan=plan, project_root=project_root
    )
    match_info = {
        "year": matched.year,
        "region": matched.region_name,
        "files": {
            "lulc_raster": str(matched.lulc_raster),
            "boundary_shp": str(matched.boundary_shp),
            "threats_csv": str(matched.threats_csv),
            "sensitivity_csv": str(matched.sensitivity_csv),
            "carbon_csv": str(matched.carbon_csv),
        },
    }
    (job_dir / "data_match.json").write_text(
        json.dumps(match_info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    match_models: list[str] = []
    if "habitat_quality" in plan.models:
        match_models.append("生境质量")
    if "carbon_storage" in plan.models:
        match_models.append("碳储量")
    match_model_text = "、".join(match_models) if match_models else "相关"
    steps = _set_step(
        db_path,
        job_id,
        steps,
        "data_match",
        status="done",
        message=(
            f"已匹配浙江省{matched.year}年LULC数据、安吉县边界数据"
            f"与{match_model_text}模型参数"
        ),
        files=matched.display_files(),
    )
    artifacts.append("data_match.json")

    year = matched.year
    clipped_tif = job_dir / f"CLCD_{year}_Anji.tif"
    reclass_tif = job_dir / f"CLCD_{year}_Anji_5class.tif"
    clip_map_png = job_dir / f"clip_{year}_preview.png"
    clip_overlay_png = job_dir / f"clip_{year}_overlay.png"
    reclass_map_png = job_dir / f"lulc_{year}_5class_map.png"
    reclass_overlay_png = job_dir / f"lulc_{year}_overlay.png"
    overlay_py = _resolve_script(project_root, catalog_path, "plot_overlay_py")

    env = os.environ.copy()
    if saga_cmd:
        env["SAGA_CMD"] = saga_cmd
    env = inject_qgis_env(env, qgis_python_bat)

    # --- 3. SAGA 裁剪 ---
    steps = _set_step(db_path, job_id, steps, "clip", status="running", message="正在裁剪…")
    catalog = load_catalog(catalog_path)
    tables_rel = catalog.get("tables_dir", "gis")
    gis_dir = (project_root / tables_rel).resolve()
    clip_ps1 = _resolve_script(project_root, catalog_path, "clip_ps1")
    clip_tool_index = int(catalog.get("saga", {}).get("clip_tool_index", 7))
    (job_dir / "clip_cmd.txt").write_text(
        f"script={clip_ps1}\noutput={clipped_tif}\n",
        encoding="utf-8",
    )
    try:
        _run_cmd(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(clip_ps1),
                "-RasterPath",
                str(matched.lulc_raster),
                "-CountyShpPath",
                str(matched.boundary_shp),
                "-OutputTif",
                str(clipped_tif),
                "-SagaCmd",
                saga_cmd,
                "-ClipToolIndex",
                str(clip_tool_index),
            ],
            env=env,
            cwd=gis_dir,
        )
    except RuntimeError as exc:
        (job_dir / "clip_error.log").write_text(str(exc), encoding="utf-8")
        raise RuntimeError(f"SAGA 裁剪失败: {exc}") from exc
    render_product_map(
        python_exe=python_exe,
        project_root=project_root,
        catalog_path=catalog_path,
        input_tif=clipped_tif,
        output_png=clip_map_png,
        kind="clip",
        region=matched.region_name,
        year=year,
        env=env,
        qgis_python_bat=qgis_python_bat,
    )
    _run_cmd(
        [
            python_exe,
            str(overlay_py),
            "--input",
            str(clipped_tif),
            "--output",
            str(clip_overlay_png),
            "--mode",
            "clip",
        ],
        env=env,
    )
    steps = _set_step(
        db_path,
        job_id,
        steps,
        "clip",
        status="done",
        message=f"裁剪完成：{clipped_tif.name}",
        images=[clip_map_png.name],
    )
    artifacts.extend([clipped_tif.name, clip_map_png.name, clip_overlay_png.name])

    # --- 4. SAGA 重分类与制图 ---
    steps = _set_step(db_path, job_id, steps, "reclass", status="running", message="正在重分类…")
    reclass_ps1 = _resolve_script(project_root, catalog_path, "reclass_ps1")
    _run_cmd(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(reclass_ps1),
            "-InputTif",
            str(clipped_tif),
            "-OutputTif",
            str(reclass_tif),
            "-SagaCmd",
            saga_cmd,
        ],
        env=env,
        cwd=gis_dir,
    )
    render_product_map(
        python_exe=python_exe,
        project_root=project_root,
        catalog_path=catalog_path,
        input_tif=reclass_tif,
        output_png=reclass_map_png,
        kind="lulc",
        region=matched.region_name,
        year=year,
        env=env,
        qgis_python_bat=qgis_python_bat,
    )
    _run_cmd(
        [
            python_exe,
            str(overlay_py),
            "--input",
            str(reclass_tif),
            "--output",
            str(reclass_overlay_png),
            "--mode",
            "lulc5",
        ],
        env=env,
    )
    steps = _set_step(
        db_path,
        job_id,
        steps,
        "reclass",
        status="done",
        message=f"重分类完成：{reclass_tif.name}",
        images=[reclass_map_png.name],
    )
    artifacts.extend([reclass_tif.name, reclass_map_png.name, reclass_overlay_png.name])

    # 同步到 InVEST 工作目录
    invest_work_dir.mkdir(parents=True, exist_ok=True)
    invest_lulc_name = reclass_tif.name
    invest_lulc = invest_work_dir / invest_lulc_name
    shutil.copy2(reclass_tif, invest_lulc)
    if "habitat_quality" in plan.models:
        shutil.copy2(matched.threats_csv, invest_work_dir / matched.threats_csv.name)
        shutil.copy2(matched.sensitivity_csv, invest_work_dir / matched.sensitivity_csv.name)
    if "carbon_storage" in plan.models:
        shutil.copy2(matched.carbon_csv, invest_work_dir / matched.carbon_csv.name)

    invest_result: dict[str, Any] = {"models_run": [], "skipped": []}
    final_images: list[str] = []

    carbon_config = resolve_invest_config_path(project_root, catalog, "carbon_config_json")

    def _write_job_hq_config() -> Path:
        base_cfg = json.loads(invest_config.read_text(encoding="utf-8"))
        base_cfg["workspace_dir"] = str(invest_work_dir)
        base_cfg["work_dir"] = str(invest_work_dir)
        base_cfg["lulc_tif"] = invest_lulc_name
        base_cfg["threats_table_path"] = matched.threats_csv.name
        base_cfg["sensitivity_table_path"] = matched.sensitivity_csv.name
        base_cfg["threats_csv"] = matched.threats_csv.name
        base_cfg["sensitivity_csv"] = matched.sensitivity_csv.name
        base_cfg["cropland_tif"] = f"CLCD_{year}_Anji_cropland.tif"
        base_cfg["residential_tif"] = f"CLCD_{year}_Anji_residential.tif"
        base_cfg["map_title"] = legend_title("habitat", matched.region_name, year)

        job_cfg = job_dir / f"invest_hq_config_{year}.json"
        job_cfg.write_text(json.dumps(base_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return job_cfg

    def _write_job_carbon_config() -> Path:
        base_cfg = json.loads(carbon_config.read_text(encoding="utf-8"))
        base_cfg["workspace_dir"] = str(invest_work_dir)
        base_cfg["lulc_tif"] = invest_lulc_name
        base_cfg["carbon_csv"] = matched.carbon_csv.name
        base_cfg["map_title"] = legend_title("carbon", matched.region_name, year)

        job_cfg = job_dir / f"invest_carbon_config_{year}.json"
        job_cfg.write_text(json.dumps(base_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return job_cfg

    run_hq = "habitat_quality" in plan.models
    run_carbon = "carbon_storage" in plan.models

    # --- 5 & 6. InVEST + 成果图 ---
    if run_hq or run_carbon:
        invest_labels: list[str] = []
        if run_hq:
            invest_labels.append("生境质量")
        if run_carbon:
            invest_labels.append("碳储量")
        steps = _set_step(
            db_path,
            job_id,
            steps,
            "invest",
            status="running",
            message=f"正在运行 InVEST {'、'.join(invest_labels)} 模型…",
        )

    if run_hq:
        hq_py = _resolve_script(project_root, catalog_path, "habitat_quality_py")
        job_hq_cfg = _write_job_hq_config()
        _run_cmd(
            [python_exe, str(hq_py), "--config", str(job_hq_cfg)],
            cwd=hq_py.parent,
            env=env,
        )

        invest_result["models_run"].append("habitat_quality")

        quality_map = invest_work_dir / "quality_map.png"
        quality_tif = invest_work_dir / "quality.tif"
        if quality_tif.is_file():
            dst_tif = job_dir / f"habitat_quality_{year}.tif"
            shutil.copy2(quality_tif, dst_tif)
            artifacts.append(dst_tif.name)
            dst_map = job_dir / f"habitat_quality_{year}_map.png"
            if quality_map.is_file():
                shutil.copy2(quality_map, dst_map)
            else:
                render_product_map(
                    python_exe=python_exe,
                    project_root=project_root,
                    catalog_path=catalog_path,
                    input_tif=dst_tif,
                    output_png=dst_map,
                    kind="habitat",
                    region=matched.region_name,
                    year=year,
                    env=env,
                    qgis_python_bat=qgis_python_bat,
                )
            final_images.append(dst_map.name)
            artifacts.append(dst_map.name)
            hq_overlay_png = job_dir / f"habitat_quality_{year}_overlay.png"
            _run_cmd(
                [
                    python_exe,
                    str(overlay_py),
                    "--input",
                    str(dst_tif),
                    "--output",
                    str(hq_overlay_png),
                    "--mode",
                    "habitat",
                ],
                env=env,
            )
            artifacts.append(hq_overlay_png.name)

    if run_carbon:
        carbon_py = _resolve_script(project_root, catalog_path, "carbon_storage_py")
        job_carbon_cfg = _write_job_carbon_config()
        _run_cmd(
            [python_exe, str(carbon_py), "--config", str(job_carbon_cfg)],
            cwd=carbon_py.parent,
            env=env,
        )

        invest_result["models_run"].append("carbon_storage")

        carbon_map = invest_work_dir / "carbon_map.png"
        carbon_tif = invest_work_dir / "carbon_tot.tif"
        if carbon_tif.is_file():
            dst_tif = job_dir / f"carbon_storage_{year}.tif"
            shutil.copy2(carbon_tif, dst_tif)
            artifacts.append(dst_tif.name)
            dst_map = job_dir / f"carbon_storage_{year}_map.png"
            if carbon_map.is_file():
                shutil.copy2(carbon_map, dst_map)
            else:
                render_product_map(
                    python_exe=python_exe,
                    project_root=project_root,
                    catalog_path=catalog_path,
                    input_tif=dst_tif,
                    output_png=dst_map,
                    kind="carbon",
                    region=matched.region_name,
                    year=year,
                    env=env,
                    qgis_python_bat=qgis_python_bat,
                )
            final_images.append(dst_map.name)
            artifacts.append(dst_map.name)
            carbon_overlay_png = job_dir / f"carbon_storage_{year}_overlay.png"
            _run_cmd(
                [
                    python_exe,
                    str(overlay_py),
                    "--input",
                    str(dst_tif),
                    "--output",
                    str(carbon_overlay_png),
                    "--mode",
                    "carbon",
                ],
                env=env,
            )
            artifacts.append(carbon_overlay_png.name)

    if run_hq or run_carbon:
        done_labels: list[str] = []
        if run_hq:
            done_labels.append("生境质量")
        if run_carbon:
            done_labels.append("碳储量")
        steps = _set_step(
            db_path,
            job_id,
            steps,
            "invest",
            status="done",
            message=f"InVEST {'、'.join(done_labels)} 分析完成",
        )
    else:
        steps = _set_step(
            db_path,
            job_id,
            steps,
            "invest",
            status="skipped",
            message="本次未选择 InVEST 模型",
        )

    if final_images:
        steps = _set_step(
            db_path,
            job_id,
            steps,
            "final_map",
            status="done",
            message="成果图已生成",
            images=final_images,
        )
    else:
        steps = _set_step(
            db_path,
            job_id,
            steps,
            "final_map",
            status="skipped",
            message="无成果图输出（可能未运行 InVEST 模型或制图失败）",
        )

    result = {
        "mode": "real",
        "region": {"code": matched.region_code, "name": matched.region_name},
        "year": year,
        "models": plan.models,
        "matched_files": matched.display_files(),
        "invest": invest_result,
        "outputs": {
            "clip_raster": clipped_tif.name,
            "clip_map": clip_map_png.name,
            "reclass_raster": reclass_tif.name,
            "reclass_map": reclass_map_png.name,
            "final_maps": final_images,
        },
    }
    (job_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts.append("result.json")
    artifacts = sorted(set(artifacts + _job_artifacts(job_dir)))

    return result, artifacts, steps
