---
description: List active peer sessions in the current connector room.
allowed-tools: ["Bash"]
---

# List Peers

Run:

```
python3 -c "import sys, os; sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT']); from connector import db
with db.connect() as c:
    cur = db.current_session(c)
    if not cur:
        print('Not connected to any room. Use /connect <room>.')
    else:
        peers = db.active_peers(c, cur['room'], exclude_session=cur['id'])
        print(f\"Room '{cur['room']}' — you are session {cur['id']}. Peers ({len(peers)}):\")
        for p in peers:
            print(f\"  - session {p['id']} | pid {p['pid']} | cwd {p['cwd']} | last seen {p['last_seen']}\")
"
```

Then summarize: which peers are active, their working directories, and how recently they were seen.
