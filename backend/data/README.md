# 数据目录说明

本目录存放 GIS 栅格、边界与数据目录索引。

## 会随仓库提交的文件

| 文件 | 说明 |
|------|------|
| `catalog.json` | 数据目录索引（地区、LULC 路径模式等） |
| `regions_national.json` | 全国区划辅助数据 |

## 需自行下载后解压到此处的内容（体积大，不进 Git）

将网盘/服务器上的数据包解压后，目录应大致如下：

```text
backend/data/
  catalog.json              # 仓库已有
  regions_national.json     # 仓库已有
  CLCD/                     # 土地利用栅格（约数 GB）
    CLCD_v01_2019_albert_province/
    ...
  boundaries/               # 行政区边界缓存
  boundary/
  xianjibd/                 # 县级边界 shapefile 等
```

具体下载地址请见仓库根目录 [README.md](../../README.md) 中的「大数据文件」一节（由仓库维护者填写网盘链接）。

`PIPELINE_MODE=mock` 时可不放栅格数据，也能跑通网页演示流程。  
`PIPELINE_MODE=real` 时需要完整数据，并配置 SAGA / InVEST / QGIS 等本地工具。
