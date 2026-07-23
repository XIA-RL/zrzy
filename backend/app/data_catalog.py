# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import Plan


@dataclass(frozen=True)
class MatchedData:
    year: int
    region_code: str
    region_name: str
    lulc_raster: Path
    boundary_shp: Path
    threats_csv: Path
    sensitivity_csv: Path
    carbon_csv: Path

    def display_files(self) -> list[str]:
        return [
            self.lulc_raster.name,
            self.boundary_shp.name,
            self.threats_csv.name,
            self.sensitivity_csv.name,
            self.carbon_csv.name,
        ]


def project_root_from_catalog(catalog_path: Path) -> Path:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    root_hint = data.get("project_root")
    if root_hint:
        return (catalog_path.parent / root_hint).resolve()
    backend_dir = catalog_path.parents[1]
    if (backend_dir / "gis").exists() or (backend_dir / "invest").exists():
        return backend_dir
    return backend_dir.parent


def _first_existing(paths: list[Path]) -> Path | None:
    return next((p.resolve() for p in paths if p.is_file()), None)


def _find_boundary(project_root: Path, glob_pattern: str) -> Path:
    patterns = [glob_pattern]

    if glob_pattern == "**/BOUNT_poly.shp":
        patterns.extend([
            "data/boundary/BOUNT_poly.shp",
            "data/boundaries/BOUNT_poly.shp",
            "gis/BOUNT_poly.shp",
        ])

    # 新版县级 shp（含区级）
    xian_shp = "\u53bf\u7ea7.shp"  # 县级.shp
    if xian_shp in glob_pattern or glob_pattern == f"**/{xian_shp}":
        patterns.extend([
            f"data/xianjibd/{xian_shp}",
        ])

    for pattern in patterns:
        matches = sorted(project_root.glob(pattern))
        if matches:
            return matches[0].resolve()
    raise FileNotFoundError(f"\u672a\u627e\u5230\u8fb9\u754c\u6587\u4ef6: {glob_pattern}")


def load_catalog(catalog_path: Path) -> dict:
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def resolve_invest_config_path(project_root: Path, catalog: dict, key: str) -> Path:
    rel = catalog.get("invest", {}).get(key)
    if not rel:
        raise KeyError(f"catalog.invest \u7f3a\u5c11 {key}")
    path = Path(rel)
    if path.is_absolute():
        return path.resolve()
    normalized = Path(*[part for part in path.parts if part != ".."])
    candidates = [
        project_root / normalized,
        project_root.parent / normalized,
    ]
    resolved = _first_existing(candidates)
    if resolved is None:
        raise FileNotFoundError(
            "\u672a\u627e\u5230 InVEST \u914d\u7f6e\uff0c\u5df2\u68c0\u67e5: "
            + ", ".join(str(p.resolve()) for p in candidates)
        )
    return resolved


def match_data(*, catalog_path: Path, plan: Plan, project_root: Path | None = None) -> MatchedData:
    catalog = load_catalog(catalog_path)
    if project_root is None:
        project_root = project_root_from_catalog(catalog_path)

    region_cfg = catalog["regions"].get(plan.region_code)
    if not region_cfg:
        raise ValueError(f"\u672a\u6ce8\u518c\u5730\u533a: {plan.region_code}")

    years: list[int] = catalog.get("lulc_years", [])
    year = plan.year
    if year not in years:
        raise ValueError(f"\u4e0d\u652f\u6301\u5e74\u4efd {year}\uff0c\u53ef\u9009: {years}")

    province = region_cfg.get("province", "")
    fmt = dict(year=year, province=province)
    lulc_rel_dir = catalog["lulc_dir_pattern"].format(**fmt)
    lulc_filename = catalog["lulc_file_pattern"].format(**fmt)
    lulc_candidates = [
        project_root / lulc_rel_dir / lulc_filename,
        project_root / "backend" / "data" / lulc_rel_dir / lulc_filename,
        project_root / "data" / lulc_rel_dir / lulc_filename,
        project_root / "data" / "CLCD" / lulc_rel_dir / lulc_filename,
        project_root / "data" / "clcd" / lulc_rel_dir / lulc_filename,
        project_root.parent / lulc_rel_dir / lulc_filename,
    ]
    lulc_file = _first_existing(lulc_candidates)
    if lulc_file is None:
        raise FileNotFoundError(
            "\u7f3a\u5c11 LULC \u6805\u683c\uff0c\u5df2\u68c0\u67e5: "
            + ", ".join(str(p.resolve()) for p in lulc_candidates)
        )

    boundary = _find_boundary(project_root, region_cfg["boundary_glob"])

    tables_rel = catalog.get("tables_dir", "gis")
    table_dirs = [
        (project_root / tables_rel).resolve(),
        (project_root.parent / tables_rel).resolve(),
    ]

    def _find_table(keyword: str) -> Path:
        for tables_dir in table_dirs:
            matches = [p for p in tables_dir.glob("*.csv") if keyword in p.name]
            if matches:
                return matches[0].resolve()
        raise FileNotFoundError(
            f"\u672a\u627e\u5230\u542b\u300c{keyword}\u300d\u7684 CSV\uff0c\u5df2\u68c0\u67e5: "
            + ", ".join(str(p) for p in table_dirs)
        )

    threats = _find_table("\u5a01\u80c1")
    sensitivity = _find_table("\u654f\u611f")
    carbon = _find_table("\u78b3")

    return MatchedData(
        year=year,
        region_code=plan.region_code,
        region_name=region_cfg.get("region_name") or plan.region_name or plan.region_code,
        lulc_raster=lulc_file,
        boundary_shp=boundary,
        threats_csv=threats,
        sensitivity_csv=sensitivity,
        carbon_csv=carbon,
    )
