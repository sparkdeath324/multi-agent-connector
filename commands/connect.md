---
description: Join (and create if missing) a peer-rendezvous room. Sets it as this session's current room.
allowed-tools: ["Bash"]
argument-hint: <room-name>
---

# Connect to a Connector Room

Argument: `$ARGUMENTS` — the room name to join. If empty, default to `default`.

## Steps

1. If `$ARGUMENTS` is empty, set ROOM to `default`. Otherwise set ROOM to the trimmed first word of `$ARGUMENTS`.

2. Run the publisher CLI to join the room:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/connector-publish" join --room "$ROOM"
   ```

3. Print the active peers:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/connector-publish" set-room "$ROOM"
   python3 -c "import sys, os; sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT']); from connector import db
   with db.connect() as c:
       cur = db.current_session(c)
       peers = db.active_peers(c, '$ROOM', exclude_session=cur['id'] if cur else None)
       print(f\"Connected to room '$ROOM' — {len(peers)} peer(s) active\")
       for p in peers:
           print(f\"  - session {p['id']} (pid {p['pid']}) in {p['cwd']} | last seen {p['last_seen']}\")
   "
   ```

4. Report back to the user: room name, peer count, and a one-line reminder that `/feed` shows recent events from peers.
