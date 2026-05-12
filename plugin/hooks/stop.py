#!/usr/bin/env python3
"""Stop hook: publish a transcript checkpoint to the current room.

Reads the transcript from Claude Code's transcript_path field on the
hook input (when available), keeps the tail, and publishes it as a
transcript_chunk event. Degrades to no-op if the path isn't present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _shared import current_room, log_error, run_publisher  # type: ignore


TAIL_BYTES = 32 * 1024  # last 32KB of transcript


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        tpath = data.get("transcript_path") or data.get("transcriptPath")
        if not tpath:
            return 0
        p = Path(tpath).expanduser()
        if not p.exists():
            return 0

        size = p.stat().st_size
        offset = max(0, size - TAIL_BYTES)
        with p.open("rb") as f:
            f.seek(offset)
            tail = f.read().decode("utf-8", errors="replace")

        # Write tail to a tmp file and pass via --content-file (the
        # publisher CLI is set up for files, not stdin payloads).
        from connector import db  # noqa
        db.ensure_root()
        tmp = db.ROOT / "_transcript_tail.txt"
        tmp.write_text(tail)
        run_publisher("transcript", "--content-file", str(tmp), "--room", current_room())
        return 0
    except Exception as exc:
        log_error("stop", exc)
        return 0


if __name__ == "__main__":
    sys.exit(main())
