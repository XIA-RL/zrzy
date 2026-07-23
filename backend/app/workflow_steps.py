from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .data_catalog import MatchedData, load_catalog, match_data
from .map_standard import inject_qgis_env, legend_title, render_product_map
from .geo import get_region_boundary_geojson
from .models import Plan, SessionArtifacts
from .workflow import _resolve_script, _run_cmd


def match_region_boundary_step(
    *,
    region_code: str,
    region_name: str | None,
    year: int,
    catalog_path: Path,
    project_root: Path,
) -> MatchedData:
    """根据地区和年份匹配基础数据。

    现有的 match_data 会同时匹配边界、LULC 和参数表。
    多轮对话中：
    - 地区轮主要使用 boundary_shp。
    - 年份轮继续使用 lulc_raster 和模型参数表。
    """
    plan = Plan(
        region_code=region_code,
        region_name=region_name,
        year=year,
        models=["habitat_quality", "carbon_storage"],
    )
    return match_data(catalog_path=catalog_path, plan=plan, project_root=project_root)


def prepare_lulc_year_step(
    *,
    matched: MatchedData,
    session_dir: Path,
    project_root: Path,
    catalog_path: Path,
    saga_cmd: str,
    python_exe: str,
    qgis_python_bat: str | None = None,
) -> SessionArtifacts:
    """完成年份数据准备：SAGA 裁剪、SAGA 重分类、预览图生成。

    这是多轮对话中用户回答年份后触发的后端动作。
    返回的 SessionArtifacts 会保存到 sessions 表，后续 InVEST 运行直接取用。
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    year = matched.year

    safe_region = matched.region_code
    clipped_tif = session_dir / f"CLCD_{year}_{safe_region}.tif"
    reclass_tif = session_dir / f"CLCD_{year}_{safe_region}_5class.tif"
    boundary_geojson = session_dir / f"boundary_{safe_region}.geojson"
    clip_map_png = session_dir / f"clip_{year}_preview.png"
    clip_overlay_png = session_dir / f"clip_{year}_overlay.png"
    reclass_map_png = session_dir / f"lulc_{year}_5class_map.png"
    reclass_overlay_png = session_dir / f"lulc_{year}_overlay.png"

    catalog = load_catalog(catalog_path)
    tables_rel = catalog.get("tables_dir", "gis")
    gis_dir = (project_root / tables_rel).resolve()

    env = os.environ.copy()
    if saga_cmd:
        env["SAGA_CMD"] = saga_cmd
    env = inject_qgis_env(env, qgis_python_bat)

    # 使用已按 adcode 精确提取的单地区 GeoJSON 作为裁剪边界，避免同名区县被同时选中。
    boundary_fc = get_region_boundary_geojson(catalog_path=catalog_path, region_code=matched.region_code)
    boundary_geojson.write_text(json.dumps(boundary_fc, ensure_ascii=False), encoding="utf-8")

    clip_ps1 = _resolve_script(project_root, catalog_path, "clip_ps1")
    clip_tool_index = int(catalog.get("saga", {}).get("clip_tool_index", 7))
    _run_cmd(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(clip_ps1),
            "-RasterPath", str(matched.lulc_raster),
            "-CountyShpPath", str(boundary_geojson),
            "-CountyName", matched.region_name,
            "-NameField", "region_name",
            "-OutputTif", str(clipped_tif),
            "-SagaCmd", saga_cmd,
            "-ClipToolIndex", str(clip_tool_index),
        ],
        env=env,
        cwd=gis_dir,
    )

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
    _export_mapbox_overlay(
        python_exe=python_exe,
        project_root=project_root,
        catalog_path=catalog_path,
        input_tif=clipped_tif,
        output_png=clip_overlay_png,
        mode="clip",
        env=env,
    )

    reclass_ps1 = _resolve_script(project_root, catalog_path, "reclass_ps1")
    _run_cmd(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(reclass_ps1),
            "-InputTif", str(clipped_tif),
            "-OutputTif", str(reclass_tif),
            "-SagaCmd", saga_cmd,
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
    _export_mapbox_overlay(
        python_exe=python_exe,
        project_root=project_root,
        catalog_path=catalog_path,
        input_tif=reclass_tif,
        output_png=reclass_overlay_png,
        mode="lulc5",
        env=env,
    )

    return SessionArtifacts(
        boundary_shp=str(matched.boundary_shp),
        lulc_raster=str(matched.lulc_raster),
        clipped_tif=str(clipped_tif),
        reclass_tif=str(reclass_tif),
        clip_preview=clip_map_png.name,
        reclass_preview=reclass_map_png.name,
        session_dir=str(session_dir),
    )


def run_invest_step(
    *,
    artifacts: SessionArtifacts,
    models: list[str],
    region_name: str,
    year: int,
    project_root: Path,
    catalog_path: Path,
    invest_work_dir: Path,
    invest_config: Path,
    python_exe: str,
    qgis_python_bat: str | None = None,
) -> dict[str, Any]:
    """在已有的重分类结果上直接运行 InVEST，生成成果图并返回结果字典。

    这是多轮对话中用户确认后触发的核心动作。
    与旧工作流的区别：不再重新匹配/裁剪/重分类，直接取 SessionArtifacts 里保存的路径。
    返回值会追加到 session 的 artifacts 中，并作为 llm_generate_report 的输入。
    """
    if not artifacts.reclass_tif:
        raise ValueError("SessionArtifacts 缺少 reclass_tif，无法运行 InVEST")
    if not artifacts.session_dir:
        raise ValueError("SessionArtifacts 缺少 session_dir")

    reclass_tif = Path(artifacts.reclass_tif)
    session_dir = Path(artifacts.session_dir)
    catalog = load_catalog(catalog_path)
    env = inject_qgis_env(None, qgis_python_bat)

    # 把重分类结果复制到 InVEST 工作目录
    invest_work_dir.mkdir(parents=True, exist_ok=True)
    invest_lulc_name = reclass_tif.name
    invest_lulc = invest_work_dir / invest_lulc_name
    shutil.copy2(reclass_tif, invest_lulc)

    # 把参数表也复制到 InVEST 工作目录（如果有）
    if artifacts.boundary_shp:
        boundary_dir = Path(artifacts.boundary_shp).parent
        _maybe_copy_csv(boundary_dir, invest_work_dir, "威胁")
        _maybe_copy_csv(boundary_dir, invest_work_dir, "敏感")
        _maybe_copy_csv(boundary_dir, invest_work_dir, "碳")

    # 从 catalog 中找参数表（更稳妥）
    tables_rel = catalog.get("tables_dir", "gis")
    gis_dir = (project_root / tables_rel).resolve()
    _maybe_copy_csv(gis_dir, invest_work_dir, "威胁")
    _maybe_copy_csv(gis_dir, invest_work_dir, "敏感")
    _maybe_copy_csv(gis_dir, invest_work_dir, "碳")

    from .data_catalog import resolve_invest_config_path
    carbon_config = resolve_invest_config_path(project_root, catalog, "carbon_config_json")

    def _write_hq_config() -> Path:
        base_cfg = json.loads(invest_config.read_text(encoding="utf-8"))
        base_cfg["lulc_tif"] = invest_lulc_name
        base_cfg["cropland_tif"] = f"CLCD_{year}_Anji_cropland.tif"
        base_cfg["residential_tif"] = f"CLCD_{year}_Anji_residential.tif"
        base_cfg["map_title"] = legend_title("habitat", region_name, year)

        cfg_path = session_dir / f"invest_hq_config_{year}.json"
        cfg_path.write_text(json.dumps(base_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg_path

    def _write_carbon_config() -> Path:
        base_cfg = json.loads(carbon_config.read_text(encoding="utf-8"))
        base_cfg["lulc_tif"] = invest_lulc_name
        # 找碳密度表文件名
        for f in invest_work_dir.glob("*.csv"):
            if "碳" in f.name:
                base_cfg["carbon_csv"] = f.name
                break
        base_cfg["map_title"] = legend_title("carbon", region_name, year)

        cfg_path = session_dir / f"invest_carbon_config_{year}.json"
        cfg_path.write_text(json.dumps(base_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg_path

    run_hq = "habitat_quality" in models
    run_carbon = "carbon_storage" in models
    invest_result: dict[str, Any] = {"models_run": [], "skipped": [], "output_images": []}

    if run_hq:
        hq_py = _resolve_script(project_root, catalog_path, "habitat_quality_py")
        hq_cfg = _write_hq_config()
        _run_cmd(
            [python_exe, str(hq_py), "--config", str(hq_cfg)],
            cwd=hq_py.parent,
            env=env,
        )
        invest_result["models_run"].append("habitat_quality")

        # 把生成的成果图拷贝到 session 目录；缺失时按统一规范补渲
        quality_map = invest_work_dir / "quality_map.png"
        quality_tif = invest_work_dir / "quality.tif"
        if quality_tif.is_file():
            dst_tif = session_dir / f"habitat_quality_{year}.tif"
            shutil.copy2(quality_tif, dst_tif)
            invest_result["habitat_quality_tif"] = dst_tif.name
            invest_result["habitat_quality"] = _read_hq_stats(invest_work_dir)
            dst = session_dir / f"habitat_quality_{year}_map.png"
            if quality_map.is_file():
                shutil.copy2(quality_map, dst)
            else:
                render_product_map(
                    python_exe=python_exe,
                    project_root=project_root,
                    catalog_path=catalog_path,
                    input_tif=dst_tif,
                    output_png=dst,
                    kind="habitat",
                    region=region_name,
                    year=year,
                    env=env,
                    qgis_python_bat=qgis_python_bat,
                )
            invest_result["output_images"].append(dst.name)
            _export_mapbox_overlay(
                python_exe=python_exe,
                project_root=project_root,
                catalog_path=catalog_path,
                input_tif=dst_tif,
                output_png=session_dir / f"habitat_quality_{year}_overlay.png",
                mode="habitat",
                env=env,
            )

    if run_carbon:
        carbon_py = _resolve_script(project_root, catalog_path, "carbon_storage_py")
        carbon_cfg = _write_carbon_config()
        _run_cmd(
            [python_exe, str(carbon_py), "--config", str(carbon_cfg)],
            cwd=carbon_py.parent,
            env=env,
        )
        invest_result["models_run"].append("carbon_storage")

        carbon_map = invest_work_dir / "carbon_map.png"
        carbon_tif = invest_work_dir / "carbon_tot.tif"
        if carbon_tif.is_file():
            dst_tif = session_dir / f"carbon_storage_{year}.tif"
            shutil.copy2(carbon_tif, dst_tif)
            invest_result["carbon_storage_tif"] = dst_tif.name
            invest_result["carbon_storage"] = _read_carbon_stats(invest_work_dir)
            dst = session_dir / f"carbon_storage_{year}_map.png"
            if carbon_map.is_file():
                shutil.copy2(carbon_map, dst)
            else:
                render_product_map(
                    python_exe=python_exe,
                    project_root=project_root,
                    catalog_path=catalog_path,
                    input_tif=dst_tif,
                    output_png=dst,
                    kind="carbon",
                    region=region_name,
                    year=year,
                    env=env,
                    qgis_python_bat=qgis_python_bat,
                )
            invest_result["output_images"].append(dst.name)
            _export_mapbox_overlay(
                python_exe=python_exe,
                project_root=project_root,
                catalog_path=catalog_path,
                input_tif=dst_tif,
                output_png=session_dir / f"carbon_storage_{year}_overlay.png",
                mode="carbon",
                env=env,
            )

    # 把完整结果写入 session 目录
    result_path = session_dir / "invest_result.json"
    result_path.write_text(
        json.dumps(invest_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return invest_result


# ── 内部工具 ─────────────────────────────────────────────────────────────────

def _export_mapbox_overlay(
    *,
    python_exe: str,
    project_root: Path,
    catalog_path: Path,
    input_tif: Path,
    output_png: Path,
    mode: str,
    env: dict[str, str] | None,
) -> None:
    """生成无图框的 Mapbox 叠加层 PNG。"""
    overlay_py = _resolve_script(project_root, catalog_path, "plot_overlay_py")
    _run_cmd(
        [
            python_exe,
            str(overlay_py),
            "--input",
            str(input_tif),
            "--output",
            str(output_png),
            "--mode",
            mode,
        ],
        env=env,
    )


def _maybe_copy_csv(src_dir: Path, dst_dir: Path, keyword: str) -> None:
    """在 src_dir 中找含 keyword 的第一个 CSV，复制到 dst_dir。"""
    for f in sorted(src_dir.glob("*.csv")):
        if keyword in f.name:
            shutil.copy2(f, dst_dir / f.name)
            return


def _read_hq_stats(invest_work_dir: Path) -> dict[str, Any]:
    """尝试读取生境质量统计 JSON；文件不存在时返回空字典。"""
    stats_path = invest_work_dir / "quality_stats.json"
    if stats_path.is_file():
        try:
            return json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _read_carbon_stats(invest_work_dir: Path) -> dict[str, Any]:
    """尝试读取碳储量统计 JSON；文件不存在时返回空字典。"""
    stats_path = invest_work_dir / "carbon_stats.json"
    if stats_path.is_file():
        try:
            return json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}
