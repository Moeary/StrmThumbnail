import asyncio
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import AppDatabase
from scheduler import TaskScheduler
from scraper import ThumbnailScraper


class ConfigPayload(BaseModel):
    media_path: str = Field(default="/media")
    threads: int = Field(default=2, ge=1, le=32)
    generate_poster: bool = True
    generate_fanart: bool = True
    generate_nfo: bool = False
    poster_percent: int = Field(default=10, ge=1, le=99)
    fanart_percent: int = Field(default=50, ge=1, le=99)
    cron: str = "0 2 * * *"
    overwrite: bool = False


class StartTaskPayload(BaseModel):
    mode: Literal["full", "incremental"] = "full"


class ConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.connections.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.connections.discard(websocket)

    async def broadcast(self, data: dict[str, Any]):
        async with self._lock:
            sockets = list(self.connections)
        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception:
                await self.disconnect(ws)


class TaskRuntime:
    def __init__(self, db: AppDatabase, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.db = db
        self.queue = queue
        self.loop = loop
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.status = "idle"
        self.latest_progress = {"current": 0, "total": 0, "status": "idle"}

    def _push(self, payload: dict[str, Any]) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)

    def _log(self, message: str) -> None:
        self._push({"type": "log", "message": message, "ts": datetime.now().isoformat()})

    def _progress(self, current: int, total: int, status: str) -> None:
        data = {"current": current, "total": total, "status": status}
        self.latest_progress = data
        self._push({"type": "progress", **data})

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, config: dict[str, Any], mode: str = "full") -> bool:
        if self.is_running():
            return False

        self.stop_event.clear()

        def target() -> None:
            self.status = "running"
            started_at = datetime.now().isoformat()
            start_time = time.time()
            self._log(f"任务开始，模式: {mode}")

            scraper = ThumbnailScraper(config=config)
            result = scraper.run(
                mode=mode,
                stop_event=self.stop_event,
                log_callback=self._log,
                progress_callback=self._progress,
            )

            ended_at = datetime.now().isoformat()
            duration = time.time() - start_time
            final_status = "stopped" if self.stop_event.is_set() else "completed"

            stats = {
                "started_at": started_at,
                "ended_at": ended_at,
                "status": final_status,
                "mode": mode,
                "success_count": result.success_count,
                "failed_count": result.failed_count,
                "skipped_count": result.skipped_count,
                "total_files": result.total_files,
                "duration_seconds": round(duration, 3),
            }
            self.db.save_task_stats(stats)
            self.status = "idle"
            self.latest_progress = {"current": 0, "total": 0, "status": "idle"}
            self._push({"type": "stats", **stats})
            self._log(f"任务结束，状态: {final_status}")

        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()
        return True

    def stop(self) -> bool:
        if not self.is_running():
            return False
        self.stop_event.set()
        return True


app = FastAPI(title="StrmThumbnail API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
STATIC_DIR = Path(os.getenv("STATIC_DIR", "./static"))
DB_PATH = DATA_DIR / "app.db"


manager = ConnectionManager()
queue: asyncio.Queue = asyncio.Queue()
db = AppDatabase(DB_PATH)
scheduler = TaskScheduler()
runtime: TaskRuntime | None = None
broadcast_worker: asyncio.Task | None = None


async def scheduled_run() -> None:
    config = db.get_config()
    if runtime and not runtime.is_running():
        runtime.start(config=config, mode="incremental")


@app.on_event("startup")
async def startup_event() -> None:
    global runtime, broadcast_worker
    loop = asyncio.get_running_loop()
    runtime = TaskRuntime(db=db, queue=queue, loop=loop)

    scheduler.start()
    config = db.get_config()
    scheduler.update_cron(config.get("cron", "0 2 * * *"), scheduled_run)

    async def broadcaster() -> None:
        while True:
            payload = await queue.get()
            await manager.broadcast(payload)

    broadcast_worker = asyncio.create_task(broadcaster())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    scheduler.shutdown()
    if broadcast_worker:
        broadcast_worker.cancel()
    if runtime:
        runtime.stop()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return db.get_config()


@app.post("/api/config")
def set_config(payload: ConfigPayload) -> dict[str, Any]:
    saved = db.save_config(payload.model_dump())
    cron = saved.get("cron", "0 2 * * *")
    try:
        scheduler.update_cron(cron, scheduled_run)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cron 表达式无效: {exc}") from exc
    return saved


@app.post("/api/task/start")
def start_task(payload: StartTaskPayload) -> dict[str, Any]:
    if runtime is None:
        raise HTTPException(status_code=500, detail="Runtime not ready")
    config = db.get_config()
    if not runtime.start(config=config, mode=payload.mode):
        raise HTTPException(status_code=409, detail="任务已在运行")
    return {"ok": True, "status": "running", "mode": payload.mode}


@app.post("/api/task/stop")
def stop_task() -> dict[str, Any]:
    if runtime is None:
        raise HTTPException(status_code=500, detail="Runtime not ready")
    stopped = runtime.stop()
    if not stopped:
        raise HTTPException(status_code=409, detail="当前没有运行中的任务")
    return {"ok": True, "status": "stopping"}


@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    latest = db.get_latest_stats()
    if runtime:
        latest["runtime_status"] = "running" if runtime.is_running() else "idle"
        latest["progress"] = runtime.latest_progress
    return latest


@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


@app.get("/")
def root() -> Any:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "StrmThumbnail backend is running", "static": False}
