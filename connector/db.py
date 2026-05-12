"""SQLite layer for multi-agent-connector.

One DB file at ~/.claude/multi-agent-connector/state.db, WAL mode so all
sessions on the machine can read/write concurrently. Stdlib only.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(os.environ.get("MAC_CONNECTOR_ROOT", Path.home() / ".claude" / "multi-agent-connector"))
DB_PATH = ROOT / "state.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    name        TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    room        TEXT NOT NULL,
    pid         INTEGER NOT NULL,
    cwd         TEXT NOT NULL,
    tty         TEXT,
    started_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    left_at     TEXT
);

CREATE INDEX IF NOT EXISTS sessions_room ON sessions(room) WHERE left_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS sessions_pid_tty ON sessions(pid, COALESCE(tty, ''));

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    room          TEXT NOT NULL,
    session_id    INTEGER NOT NULL,
    kind          TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    blob_sha      TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS events_room_time ON events(room, created_at);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind);
"""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_root() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_root()
    conn = sqlite3.connect(DB_PATH, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


def session_key() -> tuple[int, str]:
    return os.getppid(), os.environ.get("TTY", os.environ.get("TERM_SESSION_ID", ""))


def get_or_create_room(conn: sqlite3.Connection, room: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO rooms(name, created_at) VALUES (?, ?)",
        (room, now()),
    )


def upsert_session(conn: sqlite3.Connection, room: str) -> int:
    pid, tty = session_key()
    cwd = os.getcwd()
    ts = now()
    row = conn.execute(
        "SELECT id FROM sessions WHERE pid=? AND COALESCE(tty,'')=COALESCE(?, '') AND left_at IS NULL",
        (pid, tty),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE sessions SET room=?, cwd=?, last_seen=? WHERE id=?",
            (room, cwd, ts, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO sessions(room, pid, cwd, tty, started_at, last_seen) VALUES (?,?,?,?,?,?)",
        (room, pid, cwd, tty, ts, ts),
    )
    return int(cur.lastrowid)


def touch_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute("UPDATE sessions SET last_seen=? WHERE id=?", (now(), session_id))


def leave_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute("UPDATE sessions SET left_at=? WHERE id=? AND left_at IS NULL", (now(), session_id))


def active_peers(conn: sqlite3.Connection, room: str, exclude_session: int | None = None) -> list[dict]:
    sql = "SELECT id, pid, cwd, tty, started_at, last_seen FROM sessions WHERE room=? AND left_at IS NULL"
    params: list = [room]
    if exclude_session is not None:
        sql += " AND id != ?"
        params.append(exclude_session)
    sql += " ORDER BY started_at"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def current_session(conn: sqlite3.Connection) -> dict | None:
    pid, tty = session_key()
    row = conn.execute(
        "SELECT id, room FROM sessions WHERE pid=? AND COALESCE(tty,'')=COALESCE(?, '') AND left_at IS NULL ORDER BY id DESC LIMIT 1",
        (pid, tty),
    ).fetchone()
    return dict(row) if row else None


def insert_event(
    conn: sqlite3.Connection,
    room: str,
    session_id: int,
    kind: str,
    payload: dict,
    blob_sha: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO events(room, session_id, kind, payload_json, blob_sha, created_at) VALUES (?,?,?,?,?,?)",
        (room, session_id, kind, json.dumps(payload), blob_sha, now()),
    )
    touch_session(conn, session_id)
    return int(cur.lastrowid)


def query_events(
    conn: sqlite3.Connection,
    room: str,
    since: str | None = None,
    kinds: Iterable[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    sql = "SELECT id, room, session_id, kind, payload_json, blob_sha, created_at FROM events WHERE room=?"
    params: list = [room]
    if since:
        sql += " AND created_at >= ?"
        params.append(since)
    kinds_list = list(kinds) if kinds else []
    if kinds_list:
        sql += " AND kind IN (" + ",".join("?" for _ in kinds_list) + ")"
        params.extend(kinds_list)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d.pop("payload_json"))
        out.append(d)
    return list(reversed(out))


def get_event(conn: sqlite3.Connection, event_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, room, session_id, kind, payload_json, blob_sha, created_at FROM events WHERE id=?",
        (event_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json"))
    return d


def room_silent(room: str) -> bool:
    return (ROOT / "rooms" / room / "silent").exists()


def list_rooms(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT name, created_at FROM rooms ORDER BY name").fetchall()]
