"""
run_anji_habitat_quality.py
用法：python run_anji_habitat_quality.py --config path/to/config.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from invoke_qgis_map import invoke_qgis_map  # noqa: E402


def _make_threat_layer(lulc_tif: Path, class_value: int, out_tif: Path) -> None:
    try:
        import numpy as np
        import rasterio
        with rasterio.open(lulc_tif) as src:
            data = src.read(1)
            profile = src.profile.copy()
        out = (data == class_value).astype("uint8")
        profile.update(dtype="uint8", nodata=255)
        with rasterio.open(out_tif, "w", **profile) as dst:
            dst.write(out, 1)
        return
    except ImportError:
        pass
    from osgeo import gdal
    import numpy as np
    ds = gdal.Open(str(lulc_tif))
    data = ds.GetRasterBand(1).ReadAsArray()
    out = (data == class_value).astype("uint8")
    drv = gdal.GetDriverByName("GTiff")
    od = drv.Create(str(out_tif), ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte)
    od.SetGeoTransform(ds.GetGeoTransform())
    od.SetProjection(ds.GetProjection())
    od.GetRasterBand(1).WriteArray(out)
    od.GetRasterBand(1).SetNoDataValue(255)
    od.GetRasterBand(1).FlushCache()
    od = ds = None


def _write_threats_with_abspaths(original_csv: Path, work_dir: Path, output_csv: Path) -> None:
    rows = []
    with original_csv.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            if not any(row.values()):
                continue
            cur = row.get("cur_path", "").strip()
            if cur and not Path(cur).is_absolute():
                row["cur_path"] = str((work_dir / cur).resolve())
            rows.append(row)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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

    cropland_tif = work_dir / cfg.get("cropland_tif", "cropland.tif")
    residential_tif = work_dir / cfg.get("residential_tif", "residential.tif")
    if not cropland_tif.is_file():
        print(f"  生成威胁图层: {cropland_tif.name}")
        _make_threat_layer(lulc_tif, 1, cropland_tif)
    if not residential_tif.is_file():
        print(f"  生成威胁图层: {residential_tif.name}")
        _make_threat_layer(lulc_tif, 5, residential_tif)

    threats_csv_name = cfg.get("threats_table_path") or cfg.get("threats_csv")
    if not threats_csv_name:
        raise KeyError("threats_table_path")
    threats_csv_orig = work_dir / threats_csv_name
    if not threats_csv_orig.is_file():
        raise FileNotFoundError(f"威胁表格不存在: {threats_csv_orig}")

    sensitivity_csv_name = cfg.get("sensitivity_table_path") or cfg.get("sensitivity_csv")
    if not sensitivity_csv_name:
        raise KeyError("sensitivity_table_path")
    sensitivity_csv = work_dir / sensitivity_csv_name
    if not sensitivity_csv.is_file():
        raise FileNotFoundError(f"敏感性表格不存在: {sensitivity_csv}")

    threats_csv_abs = work_dir / "_threats_abspath.csv"
    _write_threats_with_abspaths(threats_csv_orig, work_dir, threats_csv_abs)

    try:
        import natcap.invest.habitat_quality as hq
    except ImportError as e:
        raise ImportError("未找到 natcap.invest，请执行：pip install natcap.invest") from e

    hq.execute({
        "workspace_dir": str(work_dir),
        "lulc_cur_path": str(lulc_tif),
        "threats_table_path": str(threats_csv_abs),
        "sensitivity_table_path": str(sensitivity_csv),
        "half_saturation_constant": float(cfg.get("half_saturation_constant", 0.5)),
        "results_suffix": cfg.get("results_suffix", ""),
        "n_workers": -1,
    })

    candidates = [
        work_dir / "output" / "quality_c.tif",
        work_dir / "quality_c.tif",
        work_dir / "output" / "habitat_quality.tif",
    ]
    quality_tif_src = next((p for p in candidates if p.is_file()), None)
    if quality_tif_src is None:
        raise FileNotFoundError(
            f"InVEST 未生成预期 TIF，搜索路径：{[str(p) for p in candidates]}"
        )

    quality_tif_dst = work_dir / "quality.tif"
    shutil.copy2(quality_tif_src, quality_tif_dst)
    print(f"  输出: {quality_tif_dst}")

    _make_map(quality_tif_dst, work_dir / "quality_map.png", cfg.get("map_title", "生境质量"), "habitat")
    _write_stats(quality_tif_dst, work_dir / "quality_stats.json")


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
            "mean": round(float(np.mean(vals)), 4),
            "max": round(float(np.max(vals)), 4),
            "min": round(float(np.min(vals)), 4),
            "std": round(float(np.std(vals)), 4),
        }
        stats_json.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"  [警告] 统计写入失败: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    run(Path(args.config))
