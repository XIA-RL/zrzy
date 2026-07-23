import shapefile
import re
from collections import Counter

import os
shp_dir = r'd:\zrzy\backend\data\xianjibd'
shp_files = [f for f in os.listdir(shp_dir) if f.endswith('.shp')]
print("找到 shp 文件:", shp_files)
shp_path = os.path.join(shp_dir, shp_files[0])
for enc in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']:
    try:
        sf = shapefile.Reader(shp_path, encoding=enc)
        sf.records()[:1]
        print(f"编码成功: {enc}")
        break
    except Exception as e:
        print(f"编码 {enc} 失败: {e}")
else:
    print("所有编码均失败")
    exit(1)
fields = [f[0] for f in sf.fields[1:]]
print("字段列表:", fields)
print(f"记录总数: {len(sf.records())}")
print("\n前5条记录:")
for rec in sf.records()[:5]:
    print("  ", rec.as_dict())

suffixes = Counter()
for rec in sf.records():
    for fname in fields:
        val = str(rec.as_dict().get(fname, ''))
        m = re.search(r'[\u5e02\u53bf\u533a\u65d7\u5dde\u76df]$', val)
        if m:
            suffixes[fname + ':' + m.group()] += 1
            break

print("\n名称字段后缀分布 (top10):")
for k, v in sorted(suffixes.items(), key=lambda x: -x[1])[:10]:
    print(f"  {k}: {v}")
