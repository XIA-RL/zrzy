#!/usr/bin/env python3
"""
根据新版 县级.shp 生成全国区县级 catalog.json regions 条目。
新 shp 字段：地名、区划码、县级、县级码、县级类、地级、地级码、省级、省级码 等

用法：
    cd d:\\zrzy\\backend
    .venv\\Scripts\\python.exe scripts\\gen_national_regions.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHP_PATH = ROOT / "data" / "xianjibd" / "县级.shp"
OUT_REGIONS_JSON = ROOT / "data" / "regions_national.json"

# 新 shp 字段名
NAME_FIELD = "地名"
ADCODE_FIELD = "区划码"
PARENT_FIELD = "地级"
PROVINCE_FIELD = "省级"
PROVINCE_CODE_FIELD = "省级码"

# 省级码（前2位）→ CLCD 文件名省份标识
PROVINCE_CODE_MAP: dict[str, str] = {
    "11": "beijing",     "12": "tianjin",     "13": "hebei",
    "14": "shanxi",      "15": "neimeng",      "21": "niaoning",
    "22": "jining",      "23": "heilongjiang", "31": "shanghai",
    "32": "jiangsu",     "33": "zhejiang",     "34": "anhui",
    "35": "fujian",      "36": "jiangxi",      "37": "shandong",
    "41": "henan",       "42": "hubei",        "43": "hunan",
    "44": "guangzhou",   "45": "guangxi",      "46": "hainan",
    "50": "chongqing",   "51": "sichuang",     "52": "guizhou",
    "53": "yunnan",      "54": "xizang",       "61": "shaanxi",
    "62": "ganshu",      "63": "qinghai",      "64": "ningxia",
    "65": "xinjiang",    "71": "taiwan",       "81": "hongkong",
    "82": "macao",
}


def province_from_code(province_code_str: str) -> str:
    code = str(province_code_str).strip()
    prefix = code[:2] if len(code) >= 6 else code[:2]
    return PROVINCE_CODE_MAP.get(prefix, "unknown")


def to_region_code(name: str, adcode: str) -> str:
    """中文地名转 region_code，优先用拼音，失败用 adcode。"""
    simplified = re.sub(r"[市县区旗州盟镇]$", "", name.strip())
    try:
        from pypinyin import lazy_pinyin
        pinyin = "".join(lazy_pinyin(simplified))
        return re.sub(r"[^a-z0-9]", "_", pinyin.lower()).strip("_")
    except ImportError:
        pass
    if adcode and adcode.isdigit():
        return f"r{adcode}"
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"region_{h}"


def main() -> int:
    if not SHP_PATH.is_file():
        print(f"[ERROR] 找不到新 shp: {SHP_PATH}", file=sys.stderr)
        return 1

    try:
        import shapefile
    except ImportError:
        print("[ERROR] 缺少 pyshp: pip install pyshp", file=sys.stderr)
        return 1

    sf = shapefile.Reader(str(SHP_PATH), encoding="utf-8")
    fields = [f[0] for f in sf.fields[1:]]
    all_records = sf.records()
    print(f"[INFO] shp 字段: {fields}")
    print(f"[INFO] 记录总数: {len(all_records)}")

    regions: dict[str, dict] = {}
    seen_codes: dict[str, int] = {}
    unknown_prov = 0

    for rec in all_records:
        props = rec.as_dict()
        county_name = str(props.get(NAME_FIELD, "")).strip()
        if not county_name:
            continue

        adcode = str(props.get(ADCODE_FIELD, "")).strip()
        province_code_raw = str(props.get(PROVINCE_CODE_FIELD, "")).strip()
        province = province_from_code(province_code_raw)
        if province == "unknown":
            unknown_prov += 1

        parent_city = str(props.get(PARENT_FIELD, "")).strip()
        province_name = str(props.get(PROVINCE_FIELD, "")).strip()

        base_code = to_region_code(county_name, adcode)
        # adcode 唯一，优先直接用 adcode 作 region_code 避免重名
        region_code = f"r{adcode}" if adcode.isdigit() and len(adcode) == 6 else base_code
        if region_code in seen_codes:
            seen_codes[region_code] += 1
            region_code = f"{region_code}_{seen_codes[region_code]}"
        else:
            seen_codes[region_code] = 0

        regions[region_code] = {
            "region_name": county_name,
            "province": province,
            "adcode": adcode,
            "parent_city": parent_city,
            "province_name": province_name,
            "county_name": county_name,
            "name_field": NAME_FIELD,
            "boundary_glob": "**/县级.shp",
        }

    print(f"\n[DONE] 共生成 {len(regions)} 个地区条目")
    if unknown_prov:
        print(f"[WARN] 有 {unknown_prov} 条未能匹配省份 (province=unknown)")

    OUT_REGIONS_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_REGIONS_JSON.write_text(
        json.dumps(regions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[SAVE] → {OUT_REGIONS_JSON}")
    print()
    print("后续步骤：")
    print("  python scripts/merge_regions_to_catalog.py   # 合并到 catalog.json")
    print("  python scripts/export_region_boundary.py     # 批量生成 GeoJSON 缓存")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
