import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.geo import get_region_boundary_geojson

catalog_path = ROOT / 'data' / 'catalog.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
regions = catalog['regions']

matches = []
for code, cfg in regions.items():
    if cfg.get('region_name') == '鼓楼区':
        matches.append((code, cfg.get('region_name'), cfg.get('parent_city'), cfg.get('province_name'), cfg.get('adcode')))

print('鼓楼区候选：')
for item in matches:
    print(' ', item)

for code, _, parent, _, _ in matches:
    if parent == '南京市':
        geojson = get_region_boundary_geojson(catalog_path=catalog_path, region_code=code)
        print('南京鼓楼 code:', code)
        print('features:', len(geojson.get('features', [])))
        for f in geojson.get('features', []):
            p = f.get('properties', {})
            print(' feature:', p.get('地名'), p.get('区划码'), p.get('地级'))
