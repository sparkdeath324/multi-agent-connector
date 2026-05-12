"""multi-agent-connector MCP server (stdio).

Exposes peer-rendezvous tools to Claude Code sessions. Uses the
official `mcp` Python SDK if installed; otherwise speaks a minimal
JSON-RPC framing over stdio itself so the plugin works with zero
extra deps for users who only want hooks/CLI.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from connector import blobs, db  # noqa: E402


CURRENT_ROOM_FILE = db.ROOT / "current_room"


def _current_room_fallback() -> str:
    if CURRENT_ROOM_FILE.exists():
        return CURRENT_ROOM_FILE.read_text().strip() or "default"
    return "default"


def _resolve_room(arg_room: str | None) -> str:
    return arg_room or _current_room_fallback()


# ---------------------------------------------------------------------------
# Tool implementations (return plain dicts/strings)
# ---------------------------------------------------------------------------

def t_room_join(room: str) -> dict:
    with db.connect() as conn:
        db.get_or_create_room(conn, room)
        sid = db.upsert_session(conn, room)
        db.insert_event(conn, room, sid, "session_join", {"cwd": os.getcwd()})
        peers = db.active_peers(conn, room, exclude_session=sid)
    db.ensure_root()
    CURRENT_ROOM_FILE.write_text(room)
    return {"session_id": sid, "room": room, "peers": peers}


def t_room_leave() -> dict:
    with db.connect() as conn:
        cur = db.current_session(conn)
        if not cur:
            return {"ok": False, "reason": "no active session"}
        db.insert_event(conn, cur["room"], cur["id"], "session_leave", {})
        db.leave_session(conn, cur["id"])
        return {"ok": True, "session_id": cur["id"], "room": cur["room"]}


def t_room_list() -> dict:
    with db.connect() as conn:
        return {"rooms": db.list_rooms(conn)}


def t_peers(room: str | None = None) -> dict:
    r = _resolve_room(room)
    with db.connect() as conn:
        return {"room": r, "peers": db.active_peers(conn, r)}


def t_publish_plan(path: str, room: str | None = None) -> dict:
    r = _resolve_room(room)
    if db.room_silent(r):
        return {"ok": False, "reason": "room is silent"}
    p = Path(path).expanduser().resolve()
    content = p.read_text(errors="replace")[:256 * 1024]
    with db.connect() as conn:
        db.get_or_create_room(conn, r)
        sid = db.upsert_session(conn, r)
        eid = db.insert_event(conn, r, sid, "plan", {"path": str(p), "content": content})
    return {"ok": True, "event_id": eid}


def t_publish_memory(name: str, content: str, room: str | None = None) -> dict:
    r = _resolve_room(room)
    if db.room_silent(r):
        return {"ok": False, "reason": "room is silent"}
    with db.connect() as conn:
        db.get_or_create_room(conn, r)
        sid = db.upsert_session(conn, r)
        eid = db.insert_event(conn, r, sid, "memory_note", {"name": name, "content": content[:256 * 1024]})
    return {"ok": True, "event_id": eid}


def t_publish_transcript_chunk(text: str, room: str | None = None) -> dict:
    r = _resolve_room(room)
    if db.room_silent(r):
        return {"ok": False, "reason": "room is silent"}
    with db.connect() as conn:
        db.get_or_create_room(conn, r)
        sid = db.upsert_session(conn, r)
        eid = db.insert_event(conn, r, sid, "transcript_chunk", {"content": text[:256 * 1024]})
    return {"ok": True, "event_id": eid}


def t_publish_artifact(path: str, room: str | None = None) -> dict:
    r = _resolve_room(room)
    if db.room_silent(r):
        return {"ok": False, "reason": "room is silent"}
    sha, size = blobs.store_blob(r, path)
    p = Path(path).expanduser().resolve()
    with db.connect() as conn:
        db.get_or_create_room(conn, r)
        sid = db.upsert_session(conn, r)
        eid = db.insert_event(conn, r, sid, "artifact", {"path": str(p), "name": p.name, "size": size}, blob_sha=sha)
    return {"ok": True, "event_id": eid, "sha": sha}


def t_publish_note(text: str, room: str | None = None) -> dict:
    r = _resolve_room(room)
    if db.room_silent(r):
        return {"ok": False, "reason": "room is silent"}
    with db.connect() as conn:
        db.get_or_create_room(conn, r)
        sid = db.upsert_session(conn, r)
        eid = db.insert_event(conn, r, sid, "note", {"text": text})
    return {"ok": True, "event_id": eid}


def t_subscribe(
    room: str | None = None,
    since: str | None = None,
    kinds: list[str] | None = None,
    limit: int = 50,
) -> dict:
    r = _resolve_room(room)
    with db.connect() as conn:
        events = db.query_events(conn, r, since=since, kinds=kinds, limit=limit)
    # Truncate large content fields in list view; full content via read_event
    for e in events:
        for fld in ("content",):
            v = e["payload"].get(fld)
            if isinstance(v, str) and len(v) > 800:
                e["payload"][fld] = v[:800] + f"\n…[truncated, {len(v)} bytes total]"
    return {"room": r, "events": events}


def t_read_event(event_id: int) -> dict:
    with db.connect() as conn:
        e = db.get_event(conn, int(event_id))
        if not e:
            return {"ok": False, "reason": f"event {event_id} not found"}
        return {"ok": True, "event": e}


def t_pull_artifact(event_id: int, dst_path: str) -> dict:
    with db.connect() as conn:
        e = db.get_event(conn, int(event_id))
    if not e or e["kind"] != "artifact" or not e["blob_sha"]:
        return {"ok": False, "reason": "not an artifact event"}
    dst = blobs.fetch_blob(e["room"], e["blob_sha"], dst_path)
    return {"ok": True, "path": str(dst), "size": dst.stat().st_size}


# ---------------------------------------------------------------------------
# MCP wiring
# ---------------------------------------------------------------------------

TOOLS: dict[str, tuple[Any, dict]] = {
    "room_join": (
        t_room_join,
        {
            "description": "Join (and create if missing) a room. Sets it as the current room for this session.",
            "inputSchema": {
                "type": "object",
                "properties": {"room": {"type": "string"}},
                "required": ["room"],
            },
        },
    ),
    "room_leave": (
        t_room_leave,
        {"description": "Leave the current room.", "inputSchema": {"type": "object", "properties": {}}},
    ),
    "room_list": (
        t_room_list,
        {"description": "List all rooms.", "inputSchema": {"type": "object", "properties": {}}},
    ),
    "peers": (
        t_peers,
        {
            "description": "List active peer sessions in a room (defaults to current).",
            "inputSchema": {"type": "object", "properties": {"room": {"type": "string"}}},
        },
    ),
    "publish_plan": (
        t_publish_plan,
        {
            "description": "Publish a plan file from disk to the room.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "room": {"type": "string"}},
                "required": ["path"],
            },
        },
    ),
    "publish_memory": (
        t_publish_memory,
        {
            "description": "Publish a memory note (name + content) to the room.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "room": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        },
    ),
    "publish_transcript_chunk": (
        t_publish_transcript_chunk,
        {
            "description": "Publish a transcript snippet for handoff/review.",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "room": {"type": "string"}},
                "required": ["text"],
            },
        },
    ),
    "publish_artifact": (
        t_publish_artifact,
        {
            "description": "Publish a file (artifact) to the room. <=2MB.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "room": {"type": "string"}},
                "required": ["path"],
            },
        },
    ),
    "publish_note": (
        t_publish_note,
        {
            "description": "Publish a free-form text note to the room.",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "room": {"type": "string"}},
                "required": ["text"],
            },
        },
    ),
    "subscribe": (
        t_subscribe,
        {
            "description": "Read recent events in a room. Filter by since (ISO8601), kinds, limit.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "room": {"type": "string"},
                    "since": {"type": "string"},
                    "kinds": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer"},
                },
            },
        },
    ),
    "read_event": (
        t_read_event,
        {
            "description": "Read a full event by id (returns untruncated payload).",
            "inputSchema": {
                "type": "object",
                "properties": {"event_id": {"type": "integer"}},
                "required": ["event_id"],
            },
        },
    ),
    "pull_artifact": (
        t_pull_artifact,
        {
            "description": "Copy an artifact blob from the room into a local path.",
            "inputSchema": {
                "type": "object",
                "properties": {"event_id": {"type": "integer"}, "dst_path": {"type": "string"}},
                "required": ["event_id", "dst_path"],
            },
        },
    ),
}


# Try the official MCP SDK; otherwise fall back to a hand-rolled JSON-RPC loop.
def _serve_with_sdk() -> bool:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except Exception:
        return False
    app = FastMCP("multi-agent-connector")
    for name, (fn, meta) in TOOLS.items():
        app.tool(name=name, description=meta["description"])(fn)
    app.run()
    return True


def _serve_jsonrpc() -> None:
    """Minimal JSON-RPC line-delimited fallback (one message per line).

    Not full MCP — used only when the official SDK isn't installed. The
    publisher CLI is the primary integration in that environment.
    """
    def write(obj: dict) -> None:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    write({"jsonrpc": "2.0", "method": "ready", "params": {"tools": list(TOOLS)}})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            method = msg.get("method")
            params = msg.get("params") or {}
            rid = msg.get("id")
            if method == "tools/list":
                write({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                    {"name": n, **m} for n, (_, m) in TOOLS.items()
                ]}})
            elif method == "tools/call":
                name = params.get("name")
                args = params.get("arguments") or {}
                fn, _ = TOOLS[name]
                write({"jsonrpc": "2.0", "id": rid, "result": fn(**args)})
            else:
                write({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown method"}})
        except Exception as exc:
            write({"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                   "error": {"code": -32000, "message": str(exc)}})


def main() -> None:
    if not _serve_with_sdk():
        _serve_jsonrpc()


if __name__ == "__main__":
    main()
