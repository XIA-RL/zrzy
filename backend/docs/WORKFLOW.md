# 智能体工作流说明

## 流程概览

用户发送一句话后，系统自动执行以下步骤（可在前端「工作流进度」中查看）：

1. **需求解析** — DeepSeek 解析年份、地区、模型类型
2. **数据匹配** — 从数据目录匹配 LULC 栅格、边界 SHP、威胁/敏感性/碳密度表
3. **SAGA 裁剪** — `clip_anji_saga.ps1`，并生成裁剪预览图
4. **SAGA 重分类与制图** — `reclass_anji_saga.ps1` + `plot_anji_lulc_map.py`
5. **InVEST 模型分析** — `run_anji_habitat_quality.py`（生境质量）或 `run_anji_carbon_storage.py`（碳储量）
6. **成果制图** — 对应模型成果图与 Mapbox 叠加层

## 数据目录（已登记）

| 类型 | 位置 |
|------|------|
| LULC 2019–2023 | `CLCD_v01_{年}_albert_province/CLCD_v01_{年}_albert_zhejiang.tif` |
| 边界 | `**/BOUNT_poly.shp`（`边界数据/` 或 `gis/`） |
| 表格 | `gis/*.csv`（威胁、敏感性、碳密度） |

登记文件：`backend/data/catalog.json`

## 运行方式

```powershell
cd d:\zrzy\backend
.\.venv\Scripts\activate
# .env 中 PIPELINE_MODE=real 为真实流程，mock 为演示
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd d:\zrzy\frontend
npm run dev
```

访问 `http://127.0.0.1:5173/agent`，输入例如：

> 分析安吉县2023年生境质量

或：

> 分析安吉县2023年碳储量

## 环境变量（`.env`）

- `PIPELINE_MODE`：`mock` | `real`
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`：DeepSeek
- `SAGA_CMD`：saga_cmd.exe 路径
- `INVEST_WORK_DIR`：默认 `D:/invest`

## 成果图统一规范

智能体流程中所有正式地图（裁剪预览、土地利用、生境质量、碳储量）共用同一套 QGIS 版式：

| 要素 | 规范 |
|------|------|
| 页面 | A4 横版、双线图框 |
| 坐标 | EPSG:4326 经纬网，标注在双线间隙 |
| 指北针 | 右上 |
| 比例尺 | 右下，单位 Miles |
| 图例 | 左下；连续值用高/低色块，LULC 用五类色块 |
| 引擎 | `backend/scripts/qgis_render_map.py` |

业务侧统一经 `plot_standard_map.py` / `app/map_standard.py` 调用，图例标题形如「安吉县2023年总碳储量」。

Mapbox 叠加层（`*_overlay.png`）无图框，但配色与正式图一致。

## 待完善

- 非 2023 年份的威胁栅格需由 InVEST 脚本从 LULC 自动生成（依赖 `ensure_threat_rasters`）
