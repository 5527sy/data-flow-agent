"""DataFlow Agent · FastAPI 应用（M1）

端点：
    GET  /                    → 卡片式向导前端
    POST /api/chat            → 提交需求（新建 run），图跑到 interrupt 暂停
    POST /api/confirm         → 卡片上的拍板动作（confirm / reroute），续跑图
    GET  /api/state/{run_id}  → 查询当前卡片状态
    GET  /health
"""
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel

from .graph import flow

app = FastAPI(title="DataFlow Agent", version="0.1.0-m1")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class ChatReq(BaseModel):
    message: str
    run_id: str | None = None


class ConfirmReq(BaseModel):
    run_id: str
    action: str                # confirm | reroute
    message: str = ""


def _snapshot(run_id: str) -> dict:
    """把图当前状态整理成前端卡片要的样子"""
    snap = flow.get_state({"configurable": {"thread_id": run_id}})
    vals = snap.values or {}
    return {
        "run_id": run_id,
        "step": vals.get("step", 1),
        "decision": vals.get("decision"),
        "card2_note": vals.get("card2_note", ""),
        "user_request": vals.get("user_request", ""),
        "paused": bool(snap.next),         # 图暂停中 = 有卡片等待拍板
        "next_node": list(snap.next),
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/chat")
def chat(req: ChatReq):
    run_id = req.run_id or f"run_{uuid.uuid4().hex[:8]}"
    cfg = {"configurable": {"thread_id": run_id}}
    flow.invoke({"run_id": run_id, "user_request": req.message, "step": 1}, cfg)
    return _snapshot(run_id)


@app.post("/api/confirm")
def confirm(req: ConfirmReq):
    cfg = {"configurable": {"thread_id": req.run_id}}
    payload = ({"action": "confirm"} if req.action == "confirm"
               else {"action": "reroute", "message": req.message})
    flow.invoke(Command(resume=payload), cfg)      # 续跑：图从 interrupt 处继续
    return _snapshot(req.run_id)


@app.get("/api/state/{run_id}")
def state(run_id: str):
    return _snapshot(run_id)


@app.get("/health")
def health():
    return {"status": "ok", "app": "data-flow-agent", "milestone": "M1"}
