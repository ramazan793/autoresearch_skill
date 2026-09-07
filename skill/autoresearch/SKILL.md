---
name: autoresearch
description: >-
  ML research workflow for the user's research repos. Use for ANY research task:
  running or analyzing experiments, ablations, training runs, implementing or
  improving methods, GPU jobs, or writing research reports. Enforces the task
  intake interview, agent_notes artifact discipline (PLAN/REPORT, entropy
  control), the subagent playbook, GPU acquisition, Telegram notifications with
  working hours, and the compact protocol.
---

# Autoresearch workflow

Operating principle: **entropy must not grow.** Every artifact — code, data,
notes, experiments — has exactly one canonical home. After every task, artifacts
are either actualized or trashed. Never leave parallel half-truths lying around.

Helper scripts live in `~/.claude/skills/autoresearch/scripts/`.

## 0. Task lifecycle

intake interview → `PLAN.md` → execute → `REPORT.md` → cleanup + commit →
checkpoint `STATE.md` → (compact protocol, only at a task boundary).

## 1. Task intake — anti-lazy interview (mandatory)

Follow `references/intake_checklist.md`. Investigate the repo/notes yourself
first; then interview the user (AskUserQuestion) about every unresolved ⚠ item —
metrics, baseline, deliverable, data paths. **Do not start a task while those
are guesses.** The interview happens once, at task start, while the user is
present. Mid-task questions obey working hours (§6).

## 2. Artifacts & entropy control

- `agent_notes/tasks/<task_slug>/` — one folder per task. Starts with `PLAN.md`,
  ends with `REPORT.md`; intermediate notes as needed; subagent scratch in
  `subagents/` inside it.
- `agent_notes/docs/` — durable agent documentation. Update in place; never
  create a second doc about the same thing.
- `agent_notes/STATE.md` — rolling session checkpoint (see §9).
- Code: clean, minimal comments. Comments never turn into notes or logs — notes
  belong in `agent_notes/`. Prefer reusing code that is known to work over
  writing new code. Smallest diff that does the job.
- Tests: **do not write tests by default** — this is ML research, they are
  clutter. Exception: genuinely bug-prone primitives (CUDA kernels, tricky data
  transforms with many edge cases).
- Data: keep it where data lives on this machine (usually
  `/data*/<username>/...`). If unsure — ask the user. Never into the repo.
- Anything shown to the user (figures, tables, reports): give **full absolute
  paths**, never relative.

## 3. Experiments

- Naming consistent with the repo's existing scheme. Almost every experiment
  builds on a baseline → the name must say *what changed* relative to it.
- Report exactly the metrics agreed at intake — those are the results; nothing
  substituted, nothing omitted.
- `REPORT.md` is self-contained: what the baseline is, what each variant changes
  vs. baseline, the metric table, absolute paths to figures. The user may read
  it days later with zero context in their head.

## 4. Git

- Each task on its own branch created for it (`task/<slug>` unless the repo has
  its own scheme). Commit the finished work to that branch.
- **Never merge.** The user reviews and decides whether and how to merge.

## 5. Subagents

Follow `references/subagent_playbook.md`: model tiers, the 2-Claude parallelism
cap with codex overflow, self-contained context handoff files, adversarial
verification of important results, and the fresh-context hard rule (one
subagent = one task; never keep refining a stale subagent).

## 6. Talking to the user, Telegram, working hours

- Ping via `bash ~/.claude/skills/autoresearch/scripts/tg_notify.sh "<msg>"`
  when: (a) you need an answer from the user, (b) a task is complete or there
  are preliminary results (`REPORT.md` ready), (c) a long run finished or
  crashed, (d) you are ready to compact. Message = 1–3 lines: what happened +
  absolute path to the details.
- Working hours: **10:00–22:00 Asia/Dubai** (user may adjust per situation).
  Check with `TZ=Asia/Dubai date +%H`.
  - Inside working hours: you may ask and wait for the answer.
  - Outside: **never block on the user.** Make the conservative choice, record
    it in the task notes under `## Assumptions (made off-hours)`, TG-ping
    (script auto-silences at night), and keep working.

## 7. GPUs

- Before any GPU job:
  `python3 ~/.claude/skills/autoresearch/scripts/gpu_free.py`
  (15 s sampling window; avg util + avg VRAM + process owners).
- Take only `FREE` GPUs. Never touch `PARKED` (someone's process holds VRAM
  even at 0% util) or `BUSY`. Respect GPU constraints given at intake.
- Set `CUDA_VISIBLE_DEVICES` explicitly for every launch; state it in notes.

## 8. Cleanup (end of every task)

- Actualize: finalize `REPORT.md`, update touched docs in place.
- Stale intermediates, dead code, scratch files →
  `python3 ~/.claude/skills/autoresearch/scripts/trash.py <paths...>`
  (moves into repo `trash/`; the user empties it). Never delete — always trash.
- Ensure `.gitignore` covers `trash/` and `.claude/`. Commit the task branch.

## 9. Compact protocol

Follow `references/compact_protocol.md`. Triggers: a `[context-watch]` nudge
(context above the limit) or your own judgment at a task boundary. **Never
compact mid-task** — reach a clean stopping point first. The agent issues the
compact **itself**, autonomously: stage everything (STATE.md + the compact
message), TG-ping, then queue it with `scripts/request_compact.py "/compact
<msg>"` (a pane-keyed file under `~/.claude/autoresearch/`, so any shell cwd
works; the Stop hook types it into your tmux pane when your turn ends — see
`references/self_compact.md`). No human
keystroke; falls back to asking the user only if `request_compact.py` refuses
(not inside tmux).

## 10. Skepticism

Nothing is ground truth: not conclusions in `agent_notes/` (prior agents wrote
them), not the user's own conclusions. Sanity-check reasoning and numbers from
raw metrics and actual execution paths, not from names, defaults, or memory.
