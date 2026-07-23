import json
with open('data/regions_national.json', encoding='utf-8') as f:
    r = json.load(f)
print(f"total: {len(r)}")
nanjing = [(k, v['region_name'], v.get('adcode','')) for k, v in r.items() if '\u5357\u4eac' in v.get('region_name','')]
gulou = [(k, v['region_name'], v.get('adcode','')) for k, v in r.items() if '\u9f13\u697c' in v.get('region_name','')]
print("nanjing related:", nanjing[:10])
print("gulou related:", gulou[:10])
jiangsu = [(k, v['region_name'], v.get('adcode','')) for k, v in r.items() if v.get('province') == 'jiangsu']
print("jiangsu count:", len(jiangsu))
print("jiangsu sample:", jiangsu[:5])
