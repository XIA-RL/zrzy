from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Region:
    region_code: str
    region_name: str
    lulc_2023_path: Path | None = None
    aoi_path: Path | None = None


def load_region(registry_dir: Path, region_code: str) -> Region:
    path = registry_dir / f"{region_code}.json"
    if not path.exists():
        raise FileNotFoundError(f"region not registered: {region_code} ({path})")

    data = json.loads(path.read_text(encoding="utf-8"))

    def to_path(value: str | None) -> Path | None:
        if not value:
            return None
        p = Path(value)
        return p

    return Region(
        region_code=data["region_code"],
        region_name=data["region_name"],
        lulc_2023_path=to_path(data.get("lulc_2023_path")),
        aoi_path=to_path(data.get("aoi_path")),
    )
