"""Artifact storage for multi-agent-connector.

Blobs are content-addressed by sha256 and stored under
~/.claude/multi-agent-connector/rooms/<room>/blobs/<sha>. Writes hold a
flock on the room directory so two sessions can't race on the same hash.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

from .db import ROOT

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024  # 2MB cap


def room_dir(room: str) -> Path:
    d = ROOT / "rooms" / room
    d.mkdir(parents=True, exist_ok=True)
    (d / "blobs").mkdir(exist_ok=True)
    return d


@contextmanager
def room_lock(room: str):
    rd = room_dir(room)
    lock_path = rd / ".lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def store_blob(room: str, src_path: str) -> tuple[str, int]:
    """Copy src_path into the room's blob store. Returns (sha, size_bytes)."""
    src = Path(src_path).expanduser().resolve()
    size = src.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"artifact too large: {size} bytes (max {MAX_ARTIFACT_BYTES})")
    h = hashlib.sha256()
    with src.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    sha = h.hexdigest()
    with room_lock(room):
        dst = room_dir(room) / "blobs" / sha
        if not dst.exists():
            shutil.copyfile(src, dst)
    return sha, size


def blob_path(room: str, sha: str) -> Path:
    return room_dir(room) / "blobs" / sha


def fetch_blob(room: str, sha: str, dst_path: str) -> Path:
    """Copy a blob into dst_path. Returns the resolved destination."""
    src = blob_path(room, sha)
    if not src.exists():
        raise FileNotFoundError(f"blob {sha} not found in room {room}")
    dst = Path(dst_path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst
