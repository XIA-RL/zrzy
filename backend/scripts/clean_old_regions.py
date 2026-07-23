#!/usr/bin/env python3
"""
清理 catalog.json：
- 删除 boundary_glob 指向旧 BOUNT_poly.shp 的所有条目
- 只保留指向新 xianjibd/县级.shp 的条目 + 手动维护的 anji
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog.json"


def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    regions = catalog.get("regions", {})

    before = len(regions)

    # 保留条件：boundary_glob 包含 县级.shp，或者是手动维护的 anji
    kept = {
        code: cfg
        for code, cfg in regions.items()
        if "\u53bf\u7ea7.shp" in cfg.get("boundary_glob", "")   # 县级.shp
        or code == "anji"
    }

    removed = before - len(kept)

    # 备份
    backup = CATALOG_PATH.with_suffix(
        f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.json"
    )
    shutil.copy2(CATALOG_PATH, backup)
    print(f"[BACKUP] {backup}")

    catalog["regions"] = kept
    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[DONE] regions: {before} -> {len(kept)} (removed {removed} old BOUNT_poly entries)")
    print(f"[SAVE] {CATALOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
