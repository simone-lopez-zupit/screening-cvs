import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "runs.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            command_id  TEXT    NOT NULL,
            params      TEXT    NOT NULL DEFAULT '{}',
            status      TEXT    NOT NULL DEFAULT 'pending',
            output      TEXT    NOT NULL DEFAULT '',
            started_at  TEXT,
            finished_at TEXT,
            exit_code   INTEGER,
            pid         INTEGER
        )
        """
    )
    # Add pid column if missing (migration for existing DBs)
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN pid INTEGER")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()


def create_run(command_id: str, params: dict) -> int:
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO runs (command_id, params, status, started_at) VALUES (?, ?, 'running', ?)",
        (command_id, json.dumps(params), datetime.now(timezone.utc).isoformat()),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def set_run_pid(run_id: int, pid: int) -> None:
    conn = _connect()
    conn.execute("UPDATE runs SET pid = ? WHERE id = ?", (pid, run_id))
    conn.commit()
    conn.close()


def get_run_pid(run_id: int) -> int | None:
    conn = _connect()
    row = conn.execute("SELECT pid FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return row["pid"] if row else None


def append_output(run_id: int, text: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE runs SET output = output || ? WHERE id = ?",
        (text, run_id),
    )
    conn.commit()
    conn.close()


def finish_run(run_id: int, exit_code: int) -> None:
    status = "completed" if exit_code == 0 else "failed"
    conn = _connect()
    conn.execute(
        "UPDATE runs SET status = ?, exit_code = ?, finished_at = ? WHERE id = ?",
        (status, exit_code, datetime.now(timezone.utc).isoformat(), run_id),
    )
    conn.commit()
    conn.close()


def list_runs() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, command_id, status, started_at, finished_at, exit_code FROM runs ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["params"] = json.loads(d["params"])
    return d
