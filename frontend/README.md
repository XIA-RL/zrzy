# zrzy 前端（React + Vite）

## 快速开始

### 1) 安装依赖

```bash
cd d:\zrzy\frontend
npm install
```

### 2) 配置 Mapbox（智能体地图功能）

复制环境变量示例并填入 Mapbox Token：

```bash
copy .env.example .env
```

在 [Mapbox Access Tokens](https://account.mapbox.com/access-tokens/) 创建公开令牌，写入 `VITE_MAPBOX_TOKEN`。

### 3) 启动开发服务器

```bash
npm run dev
```

浏览器会自动打开 `http://127.0.0.1:5173`

### 4) 同时启动后端

在另一个终端：

```powershell
cd d:\zrzy\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 页面功能

- **输入框**：输入一句话描述你的需求；提交后输入框移至左下角
- **工作流进度**：左侧展示解析、裁剪、重分类、InVEST 等步骤
- **Mapbox 地图**（右侧）：
  - LLM 解析出地区后自动定位并高亮行政区边界
  - 裁剪 / 重分类 / 生境质量完成后，对应栅格预览自动叠加到地图
- **实时状态**：显示 Job 的当前阶段、进度
- **规划信息**：LLM 解析的结构化信息（地区、年份、选择的模型）
- **结果摘要**：模型运行结果（JSON 格式）
- **产物下载**：链接到后端生成的产物文件

## 打包生产版本

```bash
npm run build
```

输出在 `dist/` 目录。
