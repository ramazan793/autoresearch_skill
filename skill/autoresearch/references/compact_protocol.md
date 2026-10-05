# Compact protocol

Context is an artifact too — a bloated context is entropy. The rule set below
keeps compaction (a) timed at task boundaries, (b) guided by the user's compact
guidelines, (c) near-lossless, because durable state lives in files, not in the
conversation.

## Triggers

- A `[context-watch]` nudge appears (the Stop hook fires when session context
  exceeds the limit, default 350k tokens), OR
- your own judgment at a task boundary: the current task is done and context is
  already fat — don't start the next task on top of it.
- **Never mid-task.** If the nudge arrives mid-task, first bring the task to a
  clean stopping point (or a parked state with everything written down), then
  run the protocol.

## The protocol

1. **Park or finish the task cleanly.** Long-running experiments keep running —
   record how to monitor them (tmux session, PID, log paths, expected finish)
   in the task's `STATE.md`.
2. **Actualize artifacts** — the normal end-of-task cleanup: `REPORT.md`
   finalized (or intermediate notes current), docs updated, junk trashed,
   branch committed.
3. **Update the task's `agent_notes/tasks/<task_id>/STATE.md`** (template
   below — a pointer file, under 6000 bytes; `request_compact.py` refuses a
   bigger one) and your line in the index (your line only — see SKILL.md §2).
4. **Self-issue the compact** (autonomous — see `self_compact.md`). Compose the
   1–2 sentence compact message per the guidelines below, then queue it:
   ```bash
   python3 ~/.claude/skills/autoresearch/scripts/request_compact.py --task <task_id> "/compact <the compact message>"
   ```
   `--task` names the task whose `STATE.md` is restored after the compact; it
   defaults to the task folder you last touched (recorded per tmux pane by the
   hooks), and the script refuses if that `STATE.md` is missing or over 6000
   bytes.
   This writes `~/.claude/autoresearch/compact_request_<pane>.json`, keyed by
   your tmux pane, so any shell cwd — a worktree or subdirectory included — is
   fine (never hand-place the file elsewhere); when your
   turn ends, the Stop hook types `/compact <msg>` into your tmux pane — the
   message steers the summarizer, no human keystroke — and, once the compact
   has finished, types `continue task <task_id>` so you resume (`--then
   "<text>"` for a different follow-up, `--then ""` for none). Then **end your
   reply.**
   - If it refuses (neither inside tmux nor a background session, or no
     `agent_notes/`), fall back: end your
     reply asking the user to paste the `/compact <msg>` line, and TG-ping
     that exact line (the only compact-related ping — routine compacts are
     silent).
5. **After compact**, a SessionStart hook puts your task's `STATE.md` (whole
   sections, within 6000 bytes) and one recovery sentence back into context —
   nothing else: the compact summary already carries the narrative, and the
   index is other agents' business. Then the follow-up message arrives. First
   actions: re-invoke the `autoresearch` skill if not loaded, read the files
   `STATE.md` points to (task folder, key docs), resume from "Next steps".

If a compact ever fires WITHOUT this protocol (built-in auto-compact at the
far end of the window), the hook still knows your task — the folder you last
touched — and restores its `STATE.md`. Only if no task folder was touched at
all does it inject the index instead, and you find your task there.

## Task STATE.md template (`agent_notes/tasks/<task_id>/STATE.md`)

```markdown
# STATE — <repo> / <task_id> (updated YYYY-MM-DD HH:MM)

## Pointers
- Task status: PLAN.md <status>, REPORT.md <status>
- Key docs: <absolute paths>

## Running jobs
- <tmux session / PID / log path / expected finish>, or "none"

## Next steps
- <1–3 bullets>

## Assumptions pending user confirmation
- <or "none">
```

Pointers and one-liners only — details live in PLAN.md, notes and docs. The
compact message is not stored here: it is composed at compact time (step 4)
and kept in the request record (`~/.claude/autoresearch/restored_compact_request_<pane>.json`).
After a compact the hook injects these sections whole, in order, within 6000
bytes (`AUTORESEARCH_STATE_MAX`); a section that does not fit is named, not
dumped — keep the file small so nothing is ever left out.

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
