"""
run_anji_carbon_storage.py
用法：python run_anji_carbon_storage.py --config path/to/config.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from invoke_qgis_map import invoke_qgis_map  # noqa: E402


def run(config_path: Path) -> None:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    # 优先级：config → 环境变量 INVEST_WORK_DIR（.env）→ 相对默认目录
    work_dir = Path(
        cfg.get("workspace_dir")
        or cfg.get("work_dir")
        or os.environ.get("INVEST_WORK_DIR")
        or (Path(__file__).resolve().parents[1] / "runs" / "invest_work")
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    lulc_tif = work_dir / cfg["lulc_tif"]
    if not lulc_tif.is_file():
        raise FileNotFoundError(f"LULC 文件不存在: {lulc_tif}")

    carbon_csv = work_dir / cfg["carbon_csv"]
    if not carbon_csv.is_file():
        raise FileNotFoundError(f"碳密度表格不存在: {carbon_csv}")

    try:
        import natcap.invest.carbon as carbon_model
    except ImportError as e:
        raise ImportError("未找到 natcap.invest，请执行：pip install natcap.invest") from e

    carbon_model.execute({
        "workspace_dir": str(work_dir),
        "lulc_bas_path": str(lulc_tif),
        "carbon_pools_path": str(carbon_csv),
        "calc_sequestration": False,
        "do_redd": False,
        "results_suffix": cfg.get("results_suffix", ""),
    })

    candidates = [
        work_dir / "c_storage_bas.tif",
        work_dir / "output" / "c_storage_bas.tif",
        work_dir / "tot_c_cur.tif",
        work_dir / "output" / "tot_c_cur.tif",
    ]
    carbon_tif_src = next((p for p in candidates if p.is_file()), None)
    if carbon_tif_src is None:
        raise FileNotFoundError(
            f"InVEST 碳储量模型未生成输出文件，搜索路径：{[str(p) for p in candidates]}"
        )

    carbon_tif_dst = work_dir / "carbon_tot.tif"
    shutil.copy2(carbon_tif_src, carbon_tif_dst)
    print(f"  输出: {carbon_tif_dst}")

    _make_map(carbon_tif_dst, work_dir / "carbon_map.png", cfg.get("map_title", "碳储量分布"), "carbon")
    _write_stats(carbon_tif_dst, work_dir / "carbon_stats.json")


def _make_map(tif_path: Path, out_png: Path, title: str, mode: str) -> None:
    """统一版式制图（与智能体流程同一规范）。"""
    try:
        invoke_qgis_map(tif_path, out_png, title=title, mode=mode)
        print(f"  地图: {out_png}")
    except Exception as exc:
        print(f"  [警告] 制图失败（不影响主流程）: {exc}")


def _write_stats(tif_path: Path, stats_json: Path) -> None:
    try:
        import numpy as np
        try:
            import rasterio
            with rasterio.open(tif_path) as src:
                data = src.read(1).astype("float32")
                nodata = src.nodata
        except ImportError:
            from osgeo import gdal
            ds = gdal.Open(str(tif_path))
            b = ds.GetRasterBand(1)
            data = b.ReadAsArray().astype("float32")
            nodata = b.GetNoDataValue()
            ds = None
        mask = np.isfinite(data)
        if nodata is not None:
            mask &= data != nodata
        vals = data[mask]
        stats = {
            "total_MgC": round(float(np.sum(vals)), 2),
            "mean_MgC_per_pixel": round(float(np.mean(vals)), 4),
            "max": round(float(np.max(vals)), 4),
        }
        stats_json.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        print(f"  [警告] 统计写入失败: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    run(Path(args.config))
