import shapefile, json

sf = shapefile.Reader(r'd:\zrzy\backend\data\boundary\BOUNT_poly.shp', encoding='gbk')
fields = [f[0] for f in sf.fields[1:]]
print("fields:", fields)

# 找出所有江苏的记录
jiangsu = []
for rec in sf.records():
    d = rec.as_dict()
    sh2 = str(d.get('SH2', ''))
    if sh2 == '32':  # 江苏省代码
        jiangsu.append(d)

print(f"\n江苏共 {len(jiangsu)} 条记录")
print("\n前15条：")
for r in jiangsu[:15]:
    print(f"  NAME99={r.get('NAME99','')!r:20s}  ADCODE99={r.get('ADCODE99','')}")

# 统计NAME99后缀分布
from collections import Counter
import re
suffixes = Counter()
for rec in sf.records():
    name = str(rec.as_dict().get('NAME99', ''))
    m = re.search(r'[\u5e02\u53bf\u533a\u65d7\u5dde\u76df]$', name)
    if m:
        suffixes[m.group()] += 1
    else:
        suffixes['其他'] += 1

print("\n全国NAME99后缀分布：")
for k, v in sorted(suffixes.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")
