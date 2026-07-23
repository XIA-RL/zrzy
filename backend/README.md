# zrzy 后端（FastAPI）

这是“自然资源调查监测数据智能化分析评价”网站的后端 MVP：
- 输入一句话 → 生成一个 Job → 轮询查看阶段与结果
- 当前默认 `PIPELINE_MODE=mock`（不依赖 SAGA/InVEST/大模型，也能把网站跑通）
- 以后接入：把 `PIPELINE_MODE=real`，并补齐 SAGA/InVEST 的命令与数据路径

## 1) 启动

### 创建虚拟环境并安装依赖（Windows PowerShell）

在本目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

### 运行

```powershell
copy .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 API 文档：`http://127.0.0.1:8000/docs`

前端（React）在 `../frontend` 目录，开发时运行 `npm run dev` 后访问 `http://127.0.0.1:5173/`。

## 2) API

- `POST /api/jobs`：提交一句话创建任务
- `GET /api/jobs/{job_id}`：查看任务状态
- `GET /api/jobs/{job_id}/artifacts/{filename}`：下载产物（如有）

## 3) 下一步你需要提供/准备

见 docs：
- `docs/START_HERE.md`
- `docs/DATA_PREP.md`
