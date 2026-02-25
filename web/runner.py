import asyncio
import json
import sys
from pathlib import Path

from web.commands import COMMANDS_BY_ID
from web.db import append_output, finish_run

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Active WebSocket connections per run_id
_ws_clients: dict[int, set] = {}


def register_ws(run_id: int, ws):
    _ws_clients.setdefault(run_id, set()).add(ws)


def unregister_ws(run_id: int, ws):
    if run_id in _ws_clients:
        _ws_clients[run_id].discard(ws)
        if not _ws_clients[run_id]:
            del _ws_clients[run_id]


async def _broadcast(run_id: int, message: dict):
    clients = _ws_clients.get(run_id, set()).copy()
    for ws in clients:
        try:
            await ws.send_json(message)
        except Exception:
            unregister_ws(run_id, ws)


async def run_script(run_id: int, command_id: str, params: dict) -> None:
    cmd = COMMANDS_BY_ID.get(command_id)
    if cmd is None:
        append_output(run_id, f"Unknown command: {command_id}\n")
        finish_run(run_id, 1)
        await _broadcast(run_id, {"type": "finished", "exit_code": 1})
        return

    script_path = PROJECT_ROOT / cmd["script"]

    env_overrides = {}
    for key, value in params.items():
        if isinstance(value, (list, dict)):
            env_overrides[f"SCREENING_PARAM_{key}"] = json.dumps(value)
        elif isinstance(value, bool):
            env_overrides[f"SCREENING_PARAM_{key}"] = str(value).lower()
        else:
            env_overrides[f"SCREENING_PARAM_{key}"] = str(value)

    import os

    env = {**os.environ, **env_overrides}

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
    except Exception as e:
        msg = f"Failed to start: {e}\n"
        append_output(run_id, msg)
        finish_run(run_id, 1)
        await _broadcast(run_id, {"type": "output", "data": msg})
        await _broadcast(run_id, {"type": "finished", "exit_code": 1})
        return

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace")
        append_output(run_id, text)
        await _broadcast(run_id, {"type": "output", "data": text})

    exit_code = await proc.wait()
    finish_run(run_id, exit_code)
    await _broadcast(run_id, {"type": "finished", "exit_code": exit_code})
