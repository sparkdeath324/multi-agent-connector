---
description: Show recent events (plans, memory, transcripts, artifacts) from peers in the current room.
allowed-tools: ["Bash"]
argument-hint: [--since 10m] [--kinds plan,memory,artifact,transcript_chunk,note]
---

# Connector Feed

Argument: `$ARGUMENTS` — optional filters. Parse `--since <duration>` (e.g. `10m`, `1h`, `24h`) and `--kinds k1,k2,...`. Default to all kinds, last 50 events.

## Run

```
python3 -c "import sys, os, time, json; sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT']); from connector import db

ARGS = '''$ARGUMENTS'''.split()
since = None; kinds = None
i = 0
while i < len(ARGS):
    if ARGS[i] == '--since' and i+1 < len(ARGS):
        v = ARGS[i+1]
        units = {'s':1,'m':60,'h':3600,'d':86400}
        n = int(v[:-1]); u = units.get(v[-1], 60)
        since = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - n*u))
        i += 2
    elif ARGS[i] == '--kinds' and i+1 < len(ARGS):
        kinds = ARGS[i+1].split(','); i += 2
    else:
        i += 1

with db.connect() as c:
    cur = db.current_session(c)
    if not cur:
        print('Not connected. Use /connect <room>.')
    else:
        events = db.query_events(c, cur['room'], since=since, kinds=kinds, limit=50)
        print(f\"Room '{cur['room']}' — {len(events)} event(s):\")
        for e in events:
            sid = e['session_id']
            mark = '·' if sid == cur['id'] else '←'
            head = f\"  [{e['id']}] {e['created_at']} {mark} {e['kind']:18s} from session {sid}\"
            print(head)
            p = e['payload']
            if e['kind'] == 'plan':
                print(f\"      path: {p.get('path')}\")
                snippet = (p.get('content','') or '')[:200].replace('\\n',' ')
                print(f\"      {snippet}\")
            elif e['kind'] == 'memory_note':
                print(f\"      name: {p.get('name')}\")
                print(f\"      {(p.get('content','') or '')[:200]}\")
            elif e['kind'] == 'artifact':
                print(f\"      file: {p.get('name')} ({p.get('size')} bytes) sha={e['blob_sha'][:12]}\")
            elif e['kind'] == 'transcript_chunk':
                print(f\"      ({len(p.get('content','') or '')} bytes of transcript)\")
            elif e['kind'] == 'note':
                print(f\"      {p.get('text','')[:300]}\")
"
```

After the listing, briefly summarize for the user: how many events from peers (vs. self), the most interesting/recent items, and remind them they can run `/pull <event-id>` to fetch an artifact or plan.
