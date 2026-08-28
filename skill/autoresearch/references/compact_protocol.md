# Compact protocol

Context is an artifact too — a bloated context is entropy. The rule set below
keeps compaction (a) timed at task boundaries, (b) guided by the user's compact
guidelines, (c) near-lossless, because durable state lives in files, not in the
conversation.

## Triggers

- A `[context-watch]` nudge appears (the Stop hook fires when session context
  exceeds the limit, default 250k tokens), OR
- your own judgment at a task boundary: the current task is done and context is
  already fat — don't start the next task on top of it.
- **Never mid-task.** If the nudge arrives mid-task, first bring the task to a
  clean stopping point (or a parked state with everything written down), then
  run the protocol.

## The protocol

1. **Park or finish the task cleanly.** Long-running experiments keep running —
   record how to monitor them (tmux session, PID, log paths, expected finish)
   in `STATE.md`.
2. **Actualize artifacts** — the normal end-of-task cleanup: `REPORT.md`
   finalized (or intermediate notes current), docs updated, junk trashed,
   branch committed.
3. **Update `agent_notes/STATE.md`** (template below), including the 1–2
   sentence compact message.
4. **TG-ping**: `bash ~/.claude/skills/autoresearch/scripts/tg_notify.sh
   "ready to compact: <task> done, report at <abs path>"`.
5. **Self-issue the compact** (autonomous — see `self_compact.md`). Compose the
   1–2 sentence compact message per the guidelines below, then queue it:
   ```bash
   python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <the compact message>"
   ```
   This writes `.claude/autoresearch/compact_request_<pane>.json`; when your
   turn ends, the Stop hook types `/compact <msg>` into your tmux pane — the
   message steers the summarizer, no human keystroke — and, once the compact
   has finished, types `continue` so you resume (`--then "<text>"` for a
   different follow-up, `--then ""` for none). Then **end your reply.**
   - If it refuses (not inside tmux, no `agent_notes/`), fall back: end your
     reply asking the user to paste the `/compact <msg>` line (put the exact
     line in the TG ping too).
6. **After compact**, a SessionStart hook restores `STATE.md` back into context
   and the follow-up message arrives. First actions: re-read the files it
   points to (current task folder, key docs), re-invoke the `autoresearch`
   skill if not loaded, resume from "Next steps".

If a compact ever fires WITHOUT this protocol (built-in auto-compact at the
far end of the window — you'll know because the recovery context is thin),
recover the same way: read `agent_notes/STATE.md` and the current task folder.

## STATE.md template

```markdown
# STATE — <repo> (updated YYYY-MM-DD HH:MM)

## Compact message
Keep the overall project context (<repo/system + end goal>), the <current
harness/architectures> being worked on, the conclusions so far (details in
<notes paths>), and the current task <task> with its state (<state>).

## Pointers
- Current task: agent_notes/tasks/<slug>/ — PLAN.md <status>, REPORT.md <status>
- Key docs: <absolute paths>
- Running jobs: <tmux/PID/log paths + expected finish, or "none">
- Next steps: <1–3 bullets>
- Assumptions pending user confirmation: <or "none">
```

## Compact-message guidelines (the user's rules — follow exactly)

The compact message is **1–2 sentences, strictly high-level**. The compact
system preserves details; the message only says which *topics* matter.

1. **No implementation details.** No flags, LRs, file:line references,
   experiment configs, or code snippets — never "C1 = X + eps 1e-15"-style
   expansions.
2. **Always name the broad context layers**, not just the current subtask:
   - the overall project (what repo, what the system is, end goal),
   - the current sub-project/harness and the architectures involved,
   - conclusions reached so far (pointer to where details are written down),
   - the current task/plan and its state (e.g. "mid-implementation").
3. **Point to files instead of restating content** — reports, notes, PLAN.md
   hold the details; the compact message just says they exist.
4. **1–2 sentences.** If it doesn't fit, it's too detailed — go up a level of
   abstraction, don't enumerate.

Good example:

> Keep the overall project context (dyn_gghead GAN generator being adapted to
> TexAvatars' texel-Gaussian overfitting harness, the architectures involved,
> and what we're trying to achieve), the batch-2 conclusions, and the agreed
> batch-3 plan with my in-progress implementation of its training knobs.

Bad example (too detailed — never do this):

> Keep the batch-3 spec (C1 B4+all-6e-4+eps1e-15+undo lr_mult = boost mapping
> fc0/fc1 group lr ×100 ...), the file map (`gancnn/generator.py` predict_raw
> stashes `_ws_syn` ...), and the smoke checklist ...

## Hard rules for context hygiene

- Main agent: compact only via this protocol, only at task boundaries.
- Subagents: **never compact, never accumulate.** One subagent = one task =
  one context. Outgrown subagent → findings to its scratch file → dies → fresh
  successor gets the file (see subagent_playbook.md).
- Don't pull huge tool outputs into context when a file path + targeted reads
  will do; don't re-read what's already summarized in notes.
