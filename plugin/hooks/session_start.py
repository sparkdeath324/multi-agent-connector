#!/usr/bin/env python3
"""SessionStart hook: register this session in the current room and print peers."""

from __future__ import annotations

import json
import sys

from _shared import current_room, log_error, run_publisher  # type: ignore


def main() -> int:
    try:
        # Hook input is on stdin (JSON). We don't strictly need it here.
        try:
            sys.stdin.read()
        except Exception:
            pass

        room = current_room()
        if room is None:
            print(json.dumps({"systemMessage": "multi-agent-connector: not connected to any room. Use `/connect <room>` to join."}))
            return 0

        run_publisher("join", "--room", room)

        # Surface peer info to Claude via stdout (visible as systemMessage).
        from connector import db  # noqa
        with db.connect() as conn:
            cur = db.current_session(conn)
            peers = db.active_peers(conn, room, exclude_session=cur["id"] if cur else None)

        if peers:
            summary = f"multi-agent-connector: joined room `{room}` — {len(peers)} peer(s) active: " + \
                ", ".join(f"pid {p['pid']} in {p['cwd']}" for p in peers)
        else:
            summary = f"multi-agent-connector: joined room `{room}` — no peers yet."
        print(json.dumps({"systemMessage": summary}))
        return 0
    except Exception as exc:
        log_error("session_start", exc)
        return 0


if __name__ == "__main__":
    sys.exit(main())
