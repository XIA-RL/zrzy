#!/usr/bin/env python3
"""连续值 GeoTIFF 制图：统一走 invoke_qgis_map（与全流程同一版式）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from invoke_qgis_map import invoke_qgis_map  # noqa: E402


def plot_map(raster_path: Path, output_path: Path, title: str, mode: str = "auto") -> None:
    invoke_qgis_map(raster_path, output_path, title=title, mode=mode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="分析结果")
    parser.add_argument(
        "--mode",
        default="auto",
        choices=["habitat", "carbon", "auto"],
    )
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(f"输入文件不存在: {args.input}")
    plot_map(args.input, args.output, args.title, args.mode)


if __name__ == "__main__":
    main()
