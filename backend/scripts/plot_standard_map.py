#!/usr/bin/env python3
"""智能体流程正式地图的唯一 CLI 入口。

所有 mode 共用 qgis_render_map.py 版式，仅图例与配色不同。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from invoke_qgis_map import invoke_qgis_map  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="统一版式制图")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="分析结果")
    parser.add_argument(
        "--mode",
        default="auto",
        choices=["lulc", "habitat", "carbon", "auto"],
    )
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(f"输入文件不存在: {args.input}")
    invoke_qgis_map(args.input, args.output, title=args.title, mode=args.mode)


if __name__ == "__main__":
    main()
