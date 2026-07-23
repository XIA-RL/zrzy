#!/usr/bin/env python3
"""安吉县 5 类 LULC 制图：统一走 invoke_qgis_map（与全流程同一版式）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "backend" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from invoke_qgis_map import invoke_qgis_map  # noqa: E402


def plot_map(raster_path: Path, output_path: Path, title: str) -> None:
    invoke_qgis_map(raster_path, output_path, title=title, mode="lulc")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parent / "CLCD_2023_Anji_5class.tif",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "CLCD_2023_Anji_5class_map.png",
    )
    parser.add_argument("--title", default="安吉县土地利用分类")
    args = parser.parse_args()
    if not args.input.exists():
        raise SystemExit(f"Raster not found: {args.input}")
    plot_map(args.input, args.output, args.title)


if __name__ == "__main__":
    main()
