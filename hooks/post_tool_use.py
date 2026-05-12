#!/usr/bin/env python3
"""PostToolUse hook: auto-publish plan/memory/artifact writes to the current room.

Triggers only on Write/Edit/MultiEdit. Routes by path:
  ~/.claude/plans/**            -> plan event
  **/memory/**.md               -> memory_note event
  *.png, *.jpg, *.jpeg, *.gif   -> artifact event (if <=2MB)
Anything else is ignored.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _shared import current_room, log_error, run_publisher  # type: ignore


PLAN_DIR = Path.home() / ".claude" / "plans"
ARTIFACT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_BYTES = 2 * 1024 * 1024


def classify(path: Path) -> str | None:
    try:
        path = path.resolve()
    except Exception:
        return None
    if PLAN_DIR in path.parents or path.parent == PLAN_DIR:
        return "plan"
    if "memory" in path.parts and path.suffix.lower() == ".md":
        return "memory"
    if path.suffix.lower() in ARTIFACT_EXTS:
        return "artifact"
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        tool = data.get("tool_name") or data.get("tool") or ""
        if tool not in ("Write", "Edit", "MultiEdit"):
            return 0

        tool_input = data.get("tool_input") or data.get("toolInput") or {}
        path_str = tool_input.get("file_path") or tool_input.get("path")
        if not path_str:
            return 0

        path = Path(path_str).expanduser()
        if not path.exists():
            return 0

        kind = classify(path)
        if kind is None:
            return 0

        room = current_room()

        if kind == "plan":
            run_publisher("plan", "--path", str(path.resolve()), "--room", room)
        elif kind == "memory":
            run_publisher("memory", "--name", path.name, "--content-file", str(path.resolve()), "--room", room)
        elif kind == "artifact":
            try:
                size = path.stat().st_size
            except OSError:
                return 0
            if size > MAX_BYTES:
                return 0
            run_publisher("artifact", "--path", str(path.resolve()), "--room", room)

        return 0
    except Exception as exc:
        log_error("post_tool_use", exc)
        return 0


if __name__ == "__main__":
    sys.exit(main())
