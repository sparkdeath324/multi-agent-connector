"""Shared helpers for connector hooks.

All hooks fail open: any error is logged to debug.log and the hook
exits 0 so the host session never sees a connector failure.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

PUBLISHER = PLUGIN_ROOT / "bin" / "connector-publish"


def log_error(prefix: str, exc: BaseException) -> None:
    try:
        from connector import db  # noqa
        db.ensure_root()
        with (db.ROOT / "debug.log").open("a") as f:
            f.write(f"[{db.now()}] {prefix}: {type(exc).__name__}: {exc}\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except Exception:
        pass


def current_room() -> str:
    try:
        from connector import db
        f = db.ROOT / "current_room"
        if f.exists():
            return f.read_text().strip() or "default"
    except Exception:
        pass
    return "default"


def run_publisher(*args: str) -> None:
    """Invoke the publisher CLI in-process (no subprocess overhead).

    The publisher is extensionless so we can't rely on spec_from_file_location's
    suffix-based loader detection — use SourceFileLoader directly.
    """
    import importlib.util
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("connector_publish", str(PUBLISHER))
    spec = importlib.util.spec_from_loader("connector_publish", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    mod.main(list(args))
