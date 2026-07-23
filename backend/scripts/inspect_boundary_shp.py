#!/usr/bin/env python3
"""临时脚本：查看 BOUNT_poly.shp 的字段和前几条记录，确认字段结构。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHP = ROOT / "gis" / "boundary" / "BOUNT_poly.shp"

try:
    import shapefile
except ImportError:
    print("请先安装 pyshp: pip install pyshp")
    sys.exit(1)

sf = shapefile.Reader(str(SHP), encoding="gbk")
fields = [f[0] for f in sf.fields[1:]]
print("字段列表:", fields)
print()
for i, rec in enumerate(sf.records()[:10]):
    print(f"[{i}]", rec.as_dict())
