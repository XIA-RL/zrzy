#!/usr/bin/env python3
"""调用 qgis_render_map.py 的唯一子进程封装。

智能体流程与 InVEST 脚本均应通过本模块出图，保证版式一致。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_QGIS_SCRIPT = Path(__file__).resolve().parent / "qgis_render_map.py"
_DEFAULT_BAT = Path(os.environ.get("QGIS_PYTHON_BAT", r"D:\download\QGIS\bin\python-qgis-ltr.bat"))


def invoke_qgis_map(
    input_tif: Path,
    output_png: Path,
    *,
    title: str,
    mode: str,
    qgis_bat: Path | None = None,
) -> None:
    """用统一版式渲染正式地图（A4 横版双线图框 / 经纬网 / 指北针 / Miles 比例尺）。"""
    if not _QGIS_SCRIPT.is_file():
        raise FileNotFoundError(f"制图脚本不存在: {_QGIS_SCRIPT}")
    bat = Path(qgis_bat) if qgis_bat else _DEFAULT_BAT
    if not bat.is_file():
        raise FileNotFoundError(f"QGIS bat 不存在: {bat}")
    if not Path(input_tif).is_file():
        raise FileNotFoundError(f"输入栅格不存在: {input_tif}")

    cmd = (
        f'"{bat}" "{_QGIS_SCRIPT}"'
        f' --input "{Path(input_tif)}"'
        f' --output "{Path(output_png)}"'
        f' --title "{title}"'
        f' --mode {mode}'
    )
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"QGIS 制图失败:\n{result.stderr or result.stdout}")
    print(f"[OK] {output_png}")
