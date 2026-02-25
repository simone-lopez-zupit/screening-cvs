import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel

from web.commands import COMMANDS, COMMANDS_BY_ID
from web.db import init_db, create_run, list_runs, get_run
from web.runner import run_script, stop_run, register_ws, unregister_ws

app = FastAPI()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

EMAILS_DIR = Path(__file__).resolve().parent.parent / "emails_body"


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/commands")
async def api_commands():
    return COMMANDS


@app.get("/api/runs")
async def api_runs():
    return list_runs()


@app.get("/api/runs/{run_id}")
async def api_run_detail(run_id: int):
    run = get_run(run_id)
    if run is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return run


@app.get("/api/emails")
async def api_emails():
    files = sorted(EMAILS_DIR.glob("*.txt"))
    return [{"filename": f.name, "content": f.read_text(encoding="utf-8")} for f in files]


class EmailUpdate(BaseModel):
    content: str


@app.put("/api/emails/{filename}")
async def api_update_email(filename: str, body: EmailUpdate):
    path = EMAILS_DIR / filename
    if not path.exists() or not path.suffix == ".txt":
        return JSONResponse({"error": "not found"}, status_code=404)
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True}


class RunRequest(BaseModel):
    command_id: str
    params: dict = {}


@app.post("/api/runs")
async def api_start_run(req: RunRequest):
    if req.command_id not in COMMANDS_BY_ID:
        return JSONResponse({"error": "unknown command"}, status_code=400)
    run_id = create_run(req.command_id, req.params)
    asyncio.create_task(run_script(run_id, req.command_id, req.params))
    return {"run_id": run_id}


@app.post("/api/runs/{run_id}/stop")
async def api_stop_run(run_id: int):
    if stop_run(run_id):
        return {"ok": True}
    return JSONResponse({"error": "run not active"}, status_code=404)


@app.websocket("/ws/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: int):
    await websocket.accept()
    register_ws(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        unregister_ws(run_id, websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
