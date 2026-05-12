# multi-agent-connector

> Two Claude Code windows on the same laptop, blind to each other. One is planning the migration. The other is halfway through implementing it. They don't know they're working on the same thing until you copy-paste between them — and by then it's already wrong.

When I'm working with Claude Code, I almost always have two or three sessions open at once: one to plan, one to implement, one watching a long build. Today each of those is a completely isolated agent. There is no way for the planning session to hand its plan to the implementation session, no way for the implementation session to drop a screenshot for the reviewing session to look at, no way for any of them to know what the others are doing without me being the manual bus between them.

**multi-agent-connector is the fix.** It is a Claude Code plugin that gives same-machine sessions a shared, append-only event log keyed by **room name**. Two terminals join `/connect demo`. From that moment, every plan one of them writes, every memory note, every screenshot, every transcript checkpoint at the end of a turn — auto-publishes into the room. The other terminal runs `/feed` and sees it. Runs `/pull <id>` and the artifact lands in its working directory.

No cloud. No daemon you have to remember to start. No auth, no encryption, no cross-host sync. One SQLite file in `~/.claude/multi-agent-connector/`, a publisher CLI, three hooks, five slash commands, one subagent. ~700 lines of stdlib-only Python.

**Who this is for:**

- Anyone running 2+ Claude Code windows on one machine and wishing they could talk
- Plan-in-one-window, implement-in-another workflows
- Long-running QA/review/build sessions you want to "watch" from a second window
- Pair-style handoffs where one session finishes a plan and another picks it up

## Quick start

1. Install the plugin (one command — see below)
2. Open two terminals. In each, run `/connect demo`
3. In window A, write or edit a plan under `~/.claude/plans/` — it auto-publishes
4. In window B, run `/feed` — you'll see A's plan
5. In window B, run `/pull <event-id>` — the plan lands in B's cwd

That's the whole loop. Everything else is convenience on top of those five steps.

## Install — one paste

**Requirements:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Python 3.10+, `git`. Zero pip installs required.

```bash
git clone --depth 1 https://github.com/sparkdeath324/multi-agent-connector.git \
  ~/.claude/plugins/multi-agent-connector && \
  ~/.claude/plugins/multi-agent-connector/setup
```

Or, even faster, the curl|bash bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/sparkdeath324/multi-agent-connector/main/install.sh | bash
```

That single command:

1. Clones the plugin directly into `~/.claude/plugins/multi-agent-connector/` — where Claude Code auto-discovers it.
2. Runs the plugin's `setup` script, which:
   - Marks `bin/connector-publish` and `setup` executable.
   - Idempotently inserts an `mcpServers.multi-agent-connector` entry into `~/.claude/settings.json` — preserves every other key, atomic write.
   - Runs a publish + subscribe smoke test against a throwaway DB to prove the install actually works. The install fails loudly if the smoke test fails.

Restart Claude Code afterwards so it picks up the new plugin and MCP server.

**Updating to a newer version:**

```bash
cd ~/.claude/plugins/multi-agent-connector && git pull && ./setup
```

`setup` is idempotent — safe to re-run any time. It detects that the plugin is already in place, only re-wires settings if the entry has drifted, and re-runs the smoke test.

**Uninstalling:**

```bash
~/.claude/plugins/multi-agent-connector/setup --uninstall && \
  rm -rf ~/.claude/plugins/multi-agent-connector ~/.claude/multi-agent-connector
```

The first command removes the `mcpServers.multi-agent-connector` entry from settings.json. The second deletes the plugin and its runtime state directory.

**Setup options:**

| Flag | What it does |
|------|--------------|
| (none) | Wire `~/.claude/settings.json`, mark scripts executable, run smoke test. Copies the plugin to `~/.claude/plugins/multi-agent-connector/` if it isn't already there. |
| `--dry-run` | Print every change without writing a thing. Run this first if you want to see exactly what `setup` will do. |
| `--uninstall` | Remove the `mcpServers.multi-agent-connector` entry from settings.json. Leaves plugin files alone — `rm -rf` them yourself for a clean wipe. |
| `--here` | Skip the copy. Wire settings.json to point at the plugin's current location. Useful for development. |
| `--install-dir PATH` | Override the install destination. |

### Confirm it's live

In any Claude Code terminal:

```
/connect demo
/peers
```

`/peers` should list your own session in room `demo`. Open a second terminal, run `/connect demo` there, then `/peers` again in either — both sessions show up.

## See it work

```
Window A (planning):

You:    /connect refactor
Claude: Connected to room 'refactor' — 0 peers active.

You:    Help me plan the auth middleware rewrite.
Claude: [enters plan mode, writes ~/.claude/plans/auth-rewrite-2026-05-12.md]
        [PostToolUse hook auto-publishes the plan to room 'refactor']

You:    /handoff "auth rewrite plan ready — start with token storage"
Claude: Published plan and handoff note to room 'refactor'.


Window B (implementing, opened a moment later):

You:    /connect refactor
Claude: Connected to room 'refactor' — 1 peer active (pid 4821 in ~/proj/api).

You:    /feed --since 10m
Claude: Room 'refactor' — 3 event(s):
          [12] 12:04:11Z ← session_join from session 1
          [13] 12:04:48Z ← plan         from session 1
              path: ~/.claude/plans/auth-rewrite-2026-05-12.md
              The auth middleware currently stores session tokens in...
          [14] 12:04:52Z ← note         from session 1
              handoff: auth rewrite plan ready — start with token storage

You:    /pull 13 ./plan.md
Claude: Pulled plan from session 1 into ./plan.md. Want me to read it?

You:    Yes — then start implementing.
Claude: [reads plan, opens token storage module, begins TDD]
```

Two windows. One plan. Zero copy-paste. The plan event is in window B's feed within milliseconds of window A saving the file, because the `PostToolUse` hook fires the moment the `Write` tool completes.

## The connector

Each slash command is a small role in a peer-handoff workflow:

| Command | Role | What it does |
|---------|------|--------------|
| `/connect <room>` | **Join** | Joins (creates if missing) a named room. Sets it as this session's current room. Every subsequent auto-publish flows into it. |
| `/peers` | **See who's around** | Lists every active peer session in the current room — pid, cwd, last-seen time. |
| `/feed [--since 10m] [--kinds plan,memory,artifact]` | **Read the room** | Shows recent events from peers (and you). Plans show a path + snippet, artifacts show a name + size, notes show their text. |
| `/handoff "note"` | **Pass the baton** | Publishes the latest plan from `~/.claude/plans/` plus a free-form handoff note. The receiving session sees both in `/feed`. |
| `/pull <event-id> [dst]` | **Fetch** | Copies a plan, memory note, transcript snippet, or artifact from a peer's event into your current working directory. |

Plus a subagent for "summarize without polluting my context":

| Subagent | Role | What it does |
|----------|------|--------------|
| `connector-courier` | **Digest reader** | Reads the last N events in the current room, groups by peer session, and returns a concise digest. Useful before a handoff: "what have my other windows done in the last hour?" |

## What auto-publishes (hooks)

The point of the connector is that *you don't have to remember to share*. Three hooks watch for events that are obviously worth broadcasting and publish them silently. All three fail open — any error goes to `~/.claude/multi-agent-connector/debug.log` and never blocks the host session.

| Hook | Trigger | Event kind |
|------|---------|------------|
| `SessionStart` | Every Claude Code session start | `session_join` (and prints a "joined room X — N peers" systemMessage) |
| `PostToolUse` | `Write`/`Edit`/`MultiEdit` to a file under `~/.claude/plans/` | `plan` |
| `PostToolUse` | `Write`/`Edit`/`MultiEdit` to `**/memory/**.md` | `memory_note` |
| `PostToolUse` | `Write`/`Edit`/`MultiEdit` to `*.png`/`*.jpg`/`*.gif` ≤ 2 MB | `artifact` |
| `Stop` | End of an assistant turn (if Claude Code provides `transcript_path`) | `transcript_chunk` (last 32 KB) |

## Privacy / opt-out

A session can be in a room as a read-only observer. Drop a sentinel file:

```bash
touch ~/.claude/multi-agent-connector/rooms/<room>/silent
```

The publisher CLI checks this before every write and exits cleanly when present. You'll still see peer events via `/feed` — you just won't broadcast your own.

## What it deliberately doesn't do

- **Cross-machine sync.** Same user, same machine only. Auth and encryption are out of scope.
- **Multi-user team rooms.** Not a collaboration product. One human, multiple windows.
- **Live push/streaming between sessions.** Pull-only via `/feed` and the courier subagent. Sessions check when they want to check.
- **Edits to peers' files.** The connector only carries data. The receiving session decides what to do with a plan or artifact.
- **Conflict resolution.** Events are append-only. If two sessions publish the same plan path, both versions are stored with timestamps; you pick.

## Architecture

```
multi-agent-connector/
├── install.sh                     # curl|bash bootstrap (clones repo + runs setup)
├── setup                          # one-shot installer (Python, stdlib only)
├── .claude-plugin/plugin.json     # plugin manifest
├── connector/
│   ├── server.py                  # MCP stdio server (FastMCP w/ JSON-RPC fallback)
│   ├── db.py                      # SQLite schema + helpers (WAL mode)
│   ├── blobs.py                   # Content-addressed artifact storage (flock-guarded)
│   └── config.example.json        # template for your mcpServers settings
├── bin/connector-publish          # Fast stdlib-only CLI invoked by hooks
├── hooks/
│   ├── hooks.json                 # SessionStart / PostToolUse / Stop registration
│   ├── _shared.py                 # log_error, current_room, in-process publisher loader
│   ├── session_start.py
│   ├── post_tool_use.py
│   └── stop.py
├── commands/                      # /connect /peers /feed /handoff /pull
└── agents/connector-courier.md    # digest subagent (Haiku)
```

All storage lives under `~/.claude/multi-agent-connector/`:

```
~/.claude/multi-agent-connector/
├── state.db              # SQLite (WAL): rooms, sessions, events
├── current_room          # plain-text "current room" pointer for this user
├── debug.log             # hook errors (rotated by hand)
└── rooms/
    └── <room>/
        ├── .lock         # flock for blob writes
        ├── silent        # opt-out sentinel (optional)
        └── blobs/        # content-addressed artifact store
            └── <sha256>
```

## Limits

- Artifacts capped at 2 MB.
- Plan / memory / transcript payloads truncated to 256 KB.
- Events are append-only. No edit, no delete — only newer events.
- One terminal session = one row in `sessions`, keyed by `(pid, tty)`. Closing the terminal leaves a stale row until the next `/connect`; that's intentional (you may want history) and harmless.

## License

MIT.
