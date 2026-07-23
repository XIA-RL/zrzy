#!/usr/bin/env python3
"""
将 data/regions_national.json 合并到 data/catalog.json 的 regions 字段。
同时更新 lulc_file_pattern 为多省结构。

用法：
    cd d:\\zrzy\\backend
    .venv\\Scripts\\python.exe scripts\\merge_regions_to_catalog.py
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog.json"
REGIONS_JSON = ROOT / "data" / "regions_national.json"


def main() -> int:
    if not REGIONS_JSON.is_file():
        print(f"[ERROR] 找不到 {REGIONS_JSON}")
        print("请先运行: python scripts/gen_national_regions.py")
        return 1

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    new_regions: dict = json.loads(REGIONS_JSON.read_text(encoding="utf-8"))

    # 备份原 catalog
    backup = CATALOG_PATH.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.json")
    shutil.copy2(CATALOG_PATH, backup)
    print(f"[BACKUP] {backup}")

    old_count = len(catalog.get("regions", {}))

    # 保留原有 anji 条目（已经有完整配置），新条目不覆盖已有的
    existing = catalog.get("regions", {})
    merged = {**new_regions, **existing}  # existing 优先级更高
    catalog["regions"] = merged

    # 更新 lulc 配置为多省结构
    catalog["lulc_dir_pattern"] = "CLCD/CLCD_v01_{year}_albert_province"
    catalog["lulc_file_pattern"] = "CLCD_v01_{year}_albert_{province}.tif"

    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    new_count = len(merged)
    print(f"[DONE] regions: {old_count} → {new_count} 个地区")
    print(f"[SAVE] → {CATALOG_PATH}")
    print()
    print("下一步：")
    print("  python scripts/export_region_boundary.py   # 批量生成 GeoJSON 缓存（耗时较长）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
