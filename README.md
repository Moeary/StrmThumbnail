# StrmThumbnail

基于 FastAPI + Vue3 的 STRM 缩略图生成服务，支持：

- 配置管理（SQLite）
- 手动全量/增量扫描
- WebSocket 实时日志与进度
- APScheduler Cron 定时任务
- 单容器部署（内置前端静态页面）

## 目录结构

- `backend/` FastAPI 后端
- `frontend/` Vue3 前端
- `Dockerfile` 多阶段构建
- `docker-compose.yml` 容器编排示例

## 本地开发

### 1) 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8090
```

### 2) 启动前端

```bash
cd frontend
npm install
npm run dev
```

开发时访问：
- 前端：`http://localhost:5173`
- 后端：`http://localhost:8090`

## Docker 启动

```bash
docker compose up -d --build
```

访问：`http://localhost:8090`

## API 概览

- `GET /api/config` 获取配置
- `POST /api/config` 保存配置
- `POST /api/task/start` 启动任务（`mode`: `full`/`incremental`）
- `POST /api/task/stop` 停止任务
- `GET /api/stats` 获取统计
- `WS /ws/stream` 实时日志与进度
