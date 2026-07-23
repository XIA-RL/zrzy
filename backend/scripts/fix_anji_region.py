#!/usr/bin/env python3
"""将 catalog 中旧 anji 条目替换为新版 县级.shp 中的安吉县配置。"""
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog.json"


def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    regions = catalog.get("regions", {})

    anji_new = None
    anji_code = None
    for code, cfg in regions.items():
        if cfg.get("region_name") == "安吉县" and "县级.shp" in cfg.get("boundary_glob", ""):
            anji_new = dict(cfg)
            anji_code = code
            break

    if not anji_new:
        print("[ERROR] 未在新版 regions 中找到安吉县")
        return 1

    backup = CATALOG_PATH.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.json")
    shutil.copy2(CATALOG_PATH, backup)
    print(f"[BACKUP] {backup}")

    regions["anji"] = anji_new
    catalog["regions"] = regions
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DONE] anji -> copied from {anji_code}: {anji_new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
