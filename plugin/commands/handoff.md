---
description: Package the current session's latest plan, recent notes, and a transcript checkpoint and publish them to the room as a handoff bundle.
allowed-tools: ["Bash", "Glob", "Read"]
argument-hint: [note describing what's being handed off]
---

# Handoff

Argument: `$ARGUMENTS` — optional one-line note describing the handoff context.

## Steps

1. Find the most recent plan file in `~/.claude/plans/`:

   ```
   ls -t ~/.claude/plans/*.md 2>/dev/null | head -1
   ```

2. If a plan exists, publish it:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/connector-publish" plan --path "<plan-path>"
   ```

3. Publish a handoff note with the user's argument (defaulting to "handoff" if empty):

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/connector-publish" note --text "handoff: $ARGUMENTS"
   ```

4. Print a confirmation: which plan was shared, what the note said, and the room name. Suggest the user tell the receiving session to run `/feed` to see the handoff.
