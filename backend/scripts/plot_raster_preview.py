#!/usr/bin/env python3
"""裁剪结果预览：统一走 invoke_qgis_map（与全流程同一版式）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from invoke_qgis_map import invoke_qgis_map  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="裁剪结果预览")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"输入不存在: {args.input}")
    invoke_qgis_map(args.input, args.output, title=args.title, mode="auto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
