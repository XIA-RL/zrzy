#!/usr/bin/env python3
"""将 GeoTIFF 导出为 Mapbox 用透明 PNG（无图例、标题、坐标轴、留白）。

配色与 qgis_render_map.py 正式图保持一致，仅输出透明栅格层。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

# 与 qgis_render_map.LULC_CLASSES 一致
LULC_CLASS_COLORS: dict[int, tuple[int, int, int]] = {
    1: (0xC4, 0xA5, 0x74),
    2: (0x2E, 0x8B, 0x2E),
    3: (0x90, 0xEE, 0x90),
    4: (0x1E, 0x6F, 0xD9),
    5: (0xE0, 0x20, 0x20),
}

# 与 qgis_render_map.RDYLGN 一致（连续插值）
HABITAT_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.0, (0xD7, 0x30, 0x27)),
    (0.25, (0xFC, 0x8D, 0x59)),
    (0.5, (0xFF, 0xFF, 0xBF)),
    (0.75, (0x91, 0xCF, 0x60)),
    (1.0, (0x1A, 0x98, 0x50)),
]

# 与 qgis_render_map.CARBON_REF 一致
CARBON_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.0, (0xFF, 0xFF, 0x00)),
    (0.35, (0xFD, 0x8D, 0x3C)),
    (0.7, (0xF0, 0x3B, 0x20)),
    (1.0, (0xBD, 0x00, 0x26)),
]

# 与 qgis_render_map.VIRIDIS 一致（裁剪预览）
VIRIDIS_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.0, (0x44, 0x01, 0x54)),
    (0.25, (0x31, 0x68, 0x8E)),
    (0.5, (0x35, 0xB7, 0x79)),
    (0.75, (0x90, 0xD7, 0x43)),
    (1.0, (0xFD, 0xE7, 0x25)),
]


def _valid_mask(data: np.ndarray, nodata: float | None) -> np.ndarray:
    mask = np.isfinite(data)
    if nodata is not None:
        mask &= data != nodata
    return mask


def _apply_stops(
    stops: list[tuple[float, tuple[int, int, int]]],
    norm: np.ndarray,
) -> np.ndarray:
    """norm: float array 0-1 → RGB uint8。"""
    t = np.clip(norm.astype(np.float64), 0.0, 1.0)
    rgb = np.zeros(t.shape + (3,), dtype=np.float64)
    ratios = [s[0] for s in stops]
    colors = np.array([s[1] for s in stops], dtype=np.float64)
    for ch in range(3):
        rgb[..., ch] = np.interp(t, ratios, colors[:, ch])
    return np.round(rgb).astype(np.uint8)


def _rgba_lulc5(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    h, w = data.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rounded = np.round(data).astype(np.int32)
    for cls, rgb in LULC_CLASS_COLORS.items():
        m = valid & (rounded == cls)
        rgba[m, 0] = rgb[0]
        rgba[m, 1] = rgb[1]
        rgba[m, 2] = rgb[2]
        rgba[m, 3] = 255
    return rgba


def _rgba_continuous(
    data: np.ndarray,
    valid: np.ndarray,
    stops: list[tuple[float, tuple[int, int, int]]],
    *,
    vmin: float | None = None,
    vmax: float | None = None,
    pct: tuple[float, float] | None = (2, 98),
) -> np.ndarray:
    h, w = data.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    if not np.any(valid):
        return rgba
    vals = data[valid].astype(np.float64)
    if vmin is None or vmax is None:
        if pct is not None:
            lo, hi = np.percentile(vals, list(pct))
        else:
            lo, hi = float(np.min(vals)), float(np.nanmax(vals))
        if vmin is None:
            vmin = lo
        if vmax is None:
            vmax = hi
    if vmax <= vmin:
        vmax = vmin + 1.0
    norm = (data.astype(np.float64) - vmin) / (vmax - vmin)
    rgb = _apply_stops(stops, norm)
    rgba[valid, :3] = rgb[valid]
    rgba[valid, 3] = 255
    return rgba


def _rgba_habitat(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    return _rgba_continuous(data, valid, HABITAT_STOPS, vmin=0.0, vmax=1.0, pct=None)


def _rgba_carbon(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    return _rgba_continuous(data, valid, CARBON_STOPS, vmin=0.0, pct=(0, 98))


def _rgba_clip(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    return _rgba_continuous(data, valid, VIRIDIS_STOPS)


def export_overlay(input_path: Path, output_path: Path, mode: str) -> None:
    with rasterio.open(input_path) as src:
        data = src.read(1).astype(np.float32)
        nodata = src.nodata

    valid = _valid_mask(data, nodata)
    if mode == "lulc5":
        rgba = _rgba_lulc5(data, valid)
    elif mode == "habitat":
        rgba = _rgba_habitat(data, valid)
    elif mode == "carbon":
        rgba = _rgba_carbon(data, valid)
    else:
        rgba = _rgba_clip(data, valid)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(output_path, optimize=True)
    print(f"[OK] overlay {output_path} ({rgba.shape[1]}x{rgba.shape[0]})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--mode",
        choices=["clip", "lulc5", "habitat", "carbon"],
        default="clip",
        help="clip=裁剪栅格; lulc5=五类土地利用; habitat=生境质量; carbon=碳储量",
    )
    args = parser.parse_args()
    inp = Path(args.input)
    out = Path(args.output)
    if not inp.is_file():
        raise SystemExit(f"输入不存在: {inp}")
    export_overlay(inp, out, args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
