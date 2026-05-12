---
description: Fetch a plan, memory note, or artifact from a peer's event into the current working directory.
allowed-tools: ["Bash", "Write"]
argument-hint: <event-id> [destination-path]
---

# Pull Event

Argument: `$ARGUMENTS` — `<event-id> [destination-path]`. If destination is omitted, choose a sensible default in the current cwd.

## Steps

1. Parse the event id (first whitespace-separated token of `$ARGUMENTS`) and optional destination (second token).

2. Read the full event:

   ```
   python3 -c "import sys, os, json; sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT']); from connector import db
   with db.connect() as c:
       e = db.get_event(c, <event-id>)
       print(json.dumps(e, default=str))
   "
   ```

3. Branch on `e['kind']`:

   - **plan**: write `e['payload']['content']` to destination (default: `./pulled-plan-<id>.md`). Use the Write tool.
   - **memory_note**: write content to destination (default: `./pulled-memory-<id>.md`).
   - **note**: print the text inline; nothing to write.
   - **transcript_chunk**: write to destination (default: `./pulled-transcript-<id>.txt`).
   - **artifact**: shell out to fetch the blob:

     ```
     python3 -c "import sys, os; sys.path.insert(0, os.environ['CLAUDE_PLUGIN_ROOT']); from connector import blobs, db
     with db.connect() as c:
         e = db.get_event(c, <event-id>)
     blobs.fetch_blob(e['room'], e['blob_sha'], '<destination>')
     print('wrote', '<destination>')
     "
     ```

4. Report: what kind of event was pulled, source session, destination path, and any next-step hints (e.g. "review with Read" for plans, "open with your image viewer" for artifacts).
