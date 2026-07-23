#!/usr/bin/env python3
"""Export registered region boundaries to backend/data/boundaries/*.geojson."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.geo import boundary_bounds, get_region_boundary_geojson  # noqa: E402


def main() -> int:
    catalog_path = ROOT / "data" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    out_dir = ROOT / "data" / "boundaries"
    out_dir.mkdir(parents=True, exist_ok=True)

    for code in catalog.get("regions", {}):
        geojson = get_region_boundary_geojson(catalog_path=catalog_path, region_code=code)
        bounds = boundary_bounds(geojson)
        out_path = out_dir / f"{code}.geojson"
        out_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] {out_path} bounds={bounds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
