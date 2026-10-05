<h1 align="center">MARS</h1>
<p align="center"><b>M</b>achine Learning <b>A</b>uto<b>R</b>esearch <b>S</b>kill</p>
<p align="center"><i>A Claude Code skill that lets an agent run ML research in our repos for days.</i></p>

MARS is a skill, three hooks, a few scripts and three subagent definitions.
The agent plans, runs experiments on shared GPUs, writes reports, survives its
own context limit, and pings us on Telegram only when it matters. The skill
itself is still invoked as `autoresearch`; the subagents are `mars_*`.

## Why this exists

An agent left alone in a research repo drifts: notes pile up in three places,
GPUs get taken from colleagues, the context fills up and the agent forgets what
it was doing, and we get a Telegram message every time it waits for anything.
This package is the set of rules and mechanisms we settled on against that.

**Entropy must not grow.** Every artifact has exactly one home. A task is one
folder (`agent_notes/tasks/<date>_<time>_<name>/`) that starts with `PLAN.md`
and ends with `REPORT.md`. Durable docs are updated in place, never forked.
Nothing is deleted, it is moved to `trash/`. Code stays minimal and carries no
notes; notes live in `agent_notes/` and are committed, generated artifacts are
not.

**Files are the source of truth, not the conversation.** The conversation will
be compacted. Whatever the agent would need afterwards must already be in a
file: `PLAN.md`, notes, `REPORT.md`, and a short `STATE.md` per task with the
pointers (status, running jobs, next steps, open assumptions). The compact
itself is then nearly lossless and the agent issues it without a human.

**Decide with the human once, then run.** The intake interview happens at
task start, while we are present: metrics, baseline, deliverable, data paths.
After that the agent does not wait for us. Outside working hours it makes the
conservative choice, writes it down and keeps going.

**Shared GPUs are a social problem.** The agent takes a GPU only after watching
it for a while, never one that someone's job is using, and may share one whose
tenant is long-idle.

**Parallel agents must not step on each other.** One task per agent, per
worktree, per branch. Shared state is one tiny index file; everything else is
per task.

**Model and effort are pinned, not hoped for.** Subagents are spawned from
definitions that fix model, effort and tools.

**Nothing is ground truth.** Not prior agents' notes, not our own conclusions.
Verify from raw metrics and the actual execution path.

## What it does

The **skill** (`skill/autoresearch/SKILL.md` + `references/`) is the rule
book: task lifecycle, artifact discipline, experiment naming, git policy,
subagent playbook, Telegram etiquette, GPU rules, cleanup, compact protocol.
It loads when a research task starts (paste `claude_md_snippet.md` into a
repo's `CLAUDE.md` to make that deterministic).

The **hooks** make the rules hold without the agent remembering them. They are
inert outside research repos (no `agent_notes/`):

- `context_watch.py` (Stop, PostToolUse): measures real context from the
  transcript; above 350k tokens it tells the agent to finish its stopping
  point and run the compact protocol (re-nudges every +40k). It also tracks the
  task folder the agent last touched and, at Stop, delivers a queued compact.
  Subagents above 350k are told to write their state down and hand off.
- `post_compact_state.py` (SessionStart on compact): puts the task's
  `STATE.md` back into context, whole sections within 6000 bytes, plus one
  recovery sentence. Nothing else: the compact summary carries the narrative.
- `notification_tg.py` (Notification): forwards approval prompts and
  "waiting for you" to Telegram, except when the agent is only waiting on its
  own background jobs.

The **self-issued compact**: the agent updates `STATE.md`, queues
`request_compact.py --task <id> "/compact <1-2 sentence message>"` and ends
its turn. The Stop hook types `/compact ...` into the agent's tmux pane, the
restore hook brings `STATE.md` back, the worker types `continue task <id>`.
No keystroke from us. Claude Code's built-in auto-compact (~967k on a 1M
model) stays as a safety net; if it ever fires, the hook still knows the task.

The **scripts**:

- `gpu_free.py --top K --need-gb N`: samples nvidia-smi for 15 s and
  classifies each GPU as `FREE`, `PRACTICALLY_FREE (util N%)` (someone's
  processes, all older than 30 min, avg util ≤ 25 %, enough VRAM left),
  `PRACTICALLY_FREE_NO_VRAM` or `BUSY`. With K GPUs `FREE` it returns at once;
  otherwise it watches shared candidates for 60 s before trusting them.
  `--share-util 50` for light jobs; timing measurements use `FREE` only.
- `tg_notify.sh [--html] "msg"`: Telegram ping with a bold host header; silent
  (no sound) outside 10:00–22:00 Asia/Dubai; falls back to plain text if
  Telegram rejects the HTML. Credentials in `~/.config/autoresearch/telegram.env`.
- `trash.py PATH...`: move to `<repo>/trash/`, never overwrite, never delete.
- `request_compact.py`, `tmux_deliver.py`: the compact machinery above.

The **agents** (`agents/mars_*.md`, installed to `~/.claude/agents/`):
`mars_top` (session model, xhigh) for anything that needs thinking or must
produce artifacts, at most one at a time because fable is scarce, with
`mars_top_opus` (Opus 5.5) for every further concurrent worker; `mars_aux`
(Opus 5.5, xhigh, no file edits) for read-only
discovery and adversarial cross-checks, a clean-context second opinion;
`mars_light` (Sonnet, xhigh) for mechanical work such as log digests and
greps, so the main context pays for the summary, not the log. Up to six
Opus/Sonnet agents may run in parallel. Codex is off; the playbook keeps it as
an opt-in mode.

## Layout

```
skill/autoresearch/        → ~/.claude/skills/autoresearch/
  SKILL.md                 the rules
  references/              intake checklist, subagent playbook, compact protocol, self-compact
  hooks/                   context_watch.py, post_compact_state.py, notification_tg.py
  scripts/                 gpu_free.py, tg_notify.sh, trash.py, request_compact.py, tmux_deliver.py
agents/mars_*.md           → ~/.claude/agents/
install.sh                 copies the above, merges hook entries into ~/.claude/settings.json
merge_settings.py          the merge (idempotent, backs up settings.json, drops retired hooks)
claude_md_snippet.md       paste into each research repo's CLAUDE.md
telegram.env.template      → ~/.config/autoresearch/telegram.env
tests/                     test_core.py (59 checks), verify_compact.sh (32, incl. a live tmux pane)
```

Per-repo state: `agent_notes/tasks/<task_id>/` (committed; `vis/` and
`artifacts/` inside it gitignored), the task index at
`$(git rev-parse --git-common-dir)/autoresearch/STATE.md` (one line per active
task, shared by all worktrees, never in git), `trash/` and `.claude/`
(gitignored). Per-machine state: `~/.claude/autoresearch/` (compact requests,
per-pane task records, `deliver.log`).

## Install

On each machine (from a shell or from an agent, it is idempotent):

```
git clone git@github.com:ramazan793/autoresearch_skill.git && cd autoresearch_skill
bash install.sh
# edit ~/.config/autoresearch/telegram.env, then
bash ~/.claude/skills/autoresearch/scripts/tg_notify.sh "hello"
python3 tests/test_core.py && bash tests/verify_compact.sh
```

Requirements: Claude Code started inside tmux (the compact is typed into the
pane), a 1M-context model (the 350k nudge assumes it; set
`AUTORESEARCH_CTX_LIMIT` lower otherwise), `agent_notes/` in the repo.
`install.sh` copies over the installed skill without deleting; a file retired
from the package stays until you trash it (it prints a note when that applies).

Knobs (env vars): `AUTORESEARCH_CTX_LIMIT` 350000, `AUTORESEARCH_CTX_STEP`
40000, `AUTORESEARCH_SUB_CTX_LIMIT` 350000, `AUTORESEARCH_SUB_MIN_GROWTH` 5000,
`AUTORESEARCH_STATE_MAX` 6000 bytes, `AUTORESEARCH_REQUEST_TTL` 600 s.

## Changelog

**2026-10-05** (vs. 2026-09-07, `0c114e4`). State is now per task: each task
folder (`YYYY-MM-DD_HH-MM_<name>`) has its own `STATE.md`, the old global one
became a one-line-per-task index kept in the git common dir so worktrees
share it; the restore hook injects only the task's `STATE.md` (≤6000 bytes,
whole sections) and the task is tracked per pane, so even a built-in
auto-compact recovers the right one. Codex is replaced by pinned subagents
(`mars_top` / `mars_top_opus` / `mars_aux` / `mars_light`; aux = Opus 5.5
xhigh, read-only; at most one fable `mars_top` at a time, up to six Opus/Sonnet
agents in parallel; the old cap of two is gone).
Telegram: HTML messages, no compact pings (PreCompact hook retired), "waiting
for you" muted while background jobs run, works from subdirectories, plain-text
retry. `gpu_free.py`: `PRACTICALLY_FREE` statuses with util, sharing
tolerance, process ages, a 60 s confirmation that is skipped when enough GPUs
are free. Notes are committed, `vis/` and `artifacts/` are not. Installer
installs the agents and removes retired hook entries. The compact nudge moved
from 250k to 350k tokens. 19 new tests.
