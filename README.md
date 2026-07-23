# EcoInvest / 自然资源调查数据分析评估系统

前后端分离的自然语言驱动分析平台：输入一句话（如「分析安吉县2023年生境质量」），由智能体完成需求解析、数据匹配、GIS 处理与 InVEST 模型分析，并在网页中展示进度与地图结果。

| 目录 | 技术 |
|------|------|
| `frontend/` | React 18 + Vite + Mapbox |
| `backend/` | FastAPI + SQLite +（可选）SAGA / InVEST / QGIS |

---

## 仓库里有什么 / 没有什么

**会进 GitHub 的：** 前后端源码、依赖清单、`catalog.json` 等小配置、文档。

**不会进仓库（体积大或含密钥）：**

| 内容 | 大约体积 | 建议存放位置 |
|------|----------|--------------|
| `backend/data/CLCD/` 等栅格与边界 | ~4 GB+ | 网盘 / 实验室服务器 / 对象存储 |
| `frontend/public/*.mp4` 演示视频 | ~300 MB | 同上（可选，不影响主流程） |
| `backend/runs/` | 运行产生 | 本地即可，勿提交 |
| `backend/.venv/`、`frontend/node_modules/` | 依赖环境 | 按下文重新安装 |
| `backend/.env`、`frontend/.env` | 密钥 | 只提交 `.env.example` |

### 大数据文件（请维护者填写）

将数据包下载后解压到 `backend/data/`，结构说明见 [`backend/data/README.md`](backend/data/README.md)。

- **GIS 数据包下载：** （在此填写百度网盘 / 阿里云盘 / 服务器地址）
- **演示视频（可选）：** 放到 `frontend/public/` 下同名 mp4 文件

没有数据包时，请使用下方的 **mock 演示模式**，仍可启动整站。

---

## 环境要求

- **Windows**（当前脚本与路径以 Windows 为主）
- **Python 3.10+**
- **Node.js 18+**（含 npm）
- 浏览器访问本机端口

可选（仅真实流水线 `PIPELINE_MODE=real`）：

- [DeepSeek](https://platform.deepseek.com/) 等 OpenAI 兼容 API Key
- [Mapbox](https://account.mapbox.com/access-tokens/) Token（智能体地图）
- SAGA GIS、InVEST、QGIS（按本机安装路径写入 `.env`）

---

## 快速启动（推荐：mock 演示）

打开两个终端，分别启动后端与前端。

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt

copy .env.example .env
# 用记事本编辑 .env：至少保持 PIPELINE_MODE=mock
# 若要用大模型解析需求，填写 LLM_API_KEY（DeepSeek 等）

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

若 PowerShell 禁止执行脚本，可先运行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

或不用激活，直接：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. 前端

```powershell
cd frontend
npm install

copy .env.example .env
# 编辑 .env，填入 VITE_MAPBOX_TOKEN（地图需要；不填则智能体页地图不可用，其它页面仍可打开）

npm run dev
```

浏览器打开：<http://127.0.0.1:5173>

### 3. 试一试

进入 **AI 智能体** 页面，例如输入：

- `分析安吉县2023年生境质量`
- `分析安吉县2023年碳储量`

`mock` 模式下不会真正调用 SAGA/InVEST，但会走通会话、阶段进度与页面交互。

---

## 真实流水线（PIPELINE_MODE=real）

在已能 mock 跑通的基础上：

1. 按「大数据文件」下载并解压 GIS 数据到 `backend/data/`。
2. 编辑 `backend/.env`：
   - `PIPELINE_MODE=real`
   - `LLM_API_KEY=你的密钥`
   - `SAGA_CMD`、`QGIS_PYTHON_BAT`、`INVEST_WORK_DIR` 改为本机真实路径
3. 重启后端，再在智能体页发起分析。

更多流程说明：[`backend/docs/WORKFLOW.md`](backend/docs/WORKFLOW.md)、[`backend/docs/START_HERE.md`](backend/docs/START_HERE.md)。

---

## 常见问题

**Q: 克隆后没有视频 / 首页视频空白？**  
A: 正常。大 mp4 未进仓库，不影响分析流程；需要时自行放到 `frontend/public/`。

**Q: 地图不显示？**  
A: 检查 `frontend/.env` 中的 `VITE_MAPBOX_TOKEN`，改完后需重启 `npm run dev`。

**Q: 后端跨域 / 前端连不上 API？**  
A: 确认后端在 `127.0.0.1:8000`，前端 `.env` 里 `VITE_API_BASE=http://127.0.0.1:8000`。

**Q: 没有 LLM Key 能不能用？**  
A: `mock` 下可演示；部分解析可能走规则兜底（例如安吉县示例）。真实分析请配置 Key。

---

## 安全提醒

- 不要把 `backend/.env` / `frontend/.env` 提交到 GitHub。
- 若密钥曾出现在本地或聊天记录中，请到对应平台**轮换新 Key**。

---

## 目录一览

```text
zrzy/
  README.md                 # 本文件
  .gitignore
  backend/
    app/                    # FastAPI 应用
    gis/                    # SAGA / 制图脚本与表
    invest/                 # InVEST 调用脚本
    data/                   # 数据（大文件需自备）
    docs/
    requirements.txt
    .env.example
  frontend/
    src/
    public/                 # 静态资源（大视频需自备）
    package.json
    .env.example
```
