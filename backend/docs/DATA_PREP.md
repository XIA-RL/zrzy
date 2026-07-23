# 数据准备（先写规范，后续照着放就能跑）

> 你目前只有安吉县数据，所以先只支持安吉县。

## 1) 建议的数据目录结构（放在 backend/data 下）

```text
backend/
  data/
    anji/
      lulc/
        lulc_2023.tif
      aoi/
        anji_boundary.shp (可选)
      tables/
        lulc_legend.csv (必需：像元值→地类名)
        invest_lulc_map.csv (必需：原始像元值→InVEST lucode)
        sensitivity.csv (可先用你文档里的表，后续再规范化)
        threats.csv
        carbon_pools.csv
```

## 2) 你需要补充的关键信息

- `lulc_legend.csv`：原始 LULC 像元值是什么意思（没有它就没法做重分类）
- `invest_lulc_map.csv`：原始像元值 → InVEST lucode（1..n）
- threats 定义：哪些 lucode 算威胁源（gd/jmyd 等），每个 threat 的 max_dist/weight/decay

## 3) 投影/分辨率约定

- 统一使用同一投影（建议米制投影），避免面积统计出错。
- 如果暂时不确定投影，也可以先把流程跑通，但结果统计会不可靠。
