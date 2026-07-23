from __future__ import annotations

"""智能体流程成果图统一规范。"""

import os
import subprocess
from pathlib import Path
from typing import Literal

from .data_catalog import load_catalog

MapKind = Literal["clip", "lulc", "habitat", "carbon"]

KIND_TO_MODE: dict[str, str] = {
    "clip": "auto",
    "lulc": "lulc",
    "habitat": "habitat",
    "carbon": "carbon",
}


def legend_title(kind: MapKind | str, region: str, year: int) -> str:
    y = f"{year}年"
    if kind == "clip":
        return f"{region}{y}LULC"
    if kind == "lulc":
        return f"{region}{y}土地利用"
    if kind == "habitat":
        return f"{region}{y}生境质量"
    if kind == "carbon":
        return f"{region}{y}总碳储量"
    return f"{region}{y}分析结果"


def inject_qgis_env(
    env: dict[str, str] | None,
    qgis_python_bat: str | None,
) -> dict[str, str]:
    out = dict(env) if env is not None else os.environ.copy()
    if qgis_python_bat:
        out["QGIS_PYTHON_BAT"] = qgis_python_bat
    return out


def _resolve_standard_plot(project_root: Path, catalog_path: Path) -> Path:
    catalog = load_catalog(catalog_path)
    rel = catalog.get("scripts", {}).get("plot_standard_map_py")
    candidates: list[Path] = []

    if rel:
        path = Path(rel)
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend([
                project_root / path,
                project_root / "backend" / path,
                catalog_path.parents[1] / path,
            ])

    candidates.extend([
        project_root / "scripts" / "plot_standard_map.py",
        project_root / "backend" / "scripts" / "plot_standard_map.py",
        catalog_path.parents[1] / "scripts" / "plot_standard_map.py",
    ])

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    checked = ", ".join(str(p.resolve()) for p in candidates)
    raise FileNotFoundError(f"未找到 plot_standard_map.py，已检查: {checked}")


def render_product_map(
    *,
    python_exe: str,
    project_root: Path,
    catalog_path: Path,
    input_tif: Path,
    output_png: Path,
    kind: MapKind | str,
    region: str,
    year: int,
    env: dict[str, str] | None = None,
    qgis_python_bat: str | None = None,
) -> None:
    mode = KIND_TO_MODE[kind]
    script = _resolve_standard_plot(project_root, catalog_path)
    run_env = inject_qgis_env(env, qgis_python_bat)
    enc = "gbk" if os.name == "nt" else "utf-8"
    cmd = [
        python_exe,
        str(script),
        "--input",
        str(input_tif),
        "--output",
        str(output_png),
        "--mode",
        mode,
        "--title",
        legend_title(kind, region, year),
    ]
    proc = subprocess.run(
        cmd,
        env=run_env,
        capture_output=True,
        text=True,
        encoding=enc,
        errors="replace",
    )
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        raise RuntimeError(detail[-2000:] or f"制图失败: {' '.join(cmd)}")
