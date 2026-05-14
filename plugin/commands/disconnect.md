---
description: Leave the current connector room. This session stops appearing as an active peer and stops publishing events.
allowed-tools: ["Bash"]
---

# Disconnect from the Connector Room

## Steps

1. Resolve the current room and leave it:

   ```
   python3 -c "import sys, os; sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT']); from connector import db
   with db.connect() as c:
       cur = db.current_session(c)
       if not cur:
           print('NOT_CONNECTED')
       else:
           print(cur['room'])
   "
   ```

2. If the previous step printed `NOT_CONNECTED`, tell the user there is no active room to leave and stop.

3. Otherwise, mark this session as left:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/connector-publish" leave
   ```

4. Clear the cached current-room pointer so future hooks fall back to `default` rather than re-publishing into the room you just left:

   ```
   python3 -c "import sys, os; sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT']); from connector import db
   p = db.ROOT / 'current_room'
   if p.exists(): p.unlink()
   "
   ```

5. Report back to the user: which room was left, and a one-line reminder that `/connect <room>` re-joins (or joins a different room).
