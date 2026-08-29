# Autoresearch — skill + hooks package

A persistent ML-research workflow for Claude Code: one personal **skill
package** carrying the workflow brain, its **hooks**, and the helper scripts.
Credentials never live in this repo (`~/.config/autoresearch/telegram.env`).

```
skill/autoresearch/               → installs as ONE unit to ~/.claude/skills/autoresearch/
  SKILL.md                        the workflow: lifecycle, artifacts, experiments,
                                  git, comms, GPUs, cleanup, compact, skepticism
  references/intake_checklist.md  anti-lazy interview (10 items, ⚠ = never assume)
  references/subagent_playbook.md refined playbook (tiers, 2-cap, codex, contracts)
  references/compact_protocol.md  compact triggers/steps + STATE.md template
                                  + your compact guidelines embedded verbatim
  references/self_compact.md      autonomous /compact: request file → Stop hook → pane
  scripts/gpu_free.py             GPU acquisition advisor (runs on the GPU box)
  scripts/tg_notify.sh            Telegram micro-notifier (working-hours aware)
  scripts/trash.py                move-to-trash (never deletes, never overwrites)
  scripts/request_compact.py      agent-side: queue "/compact <msg>" (file in the repo)
  scripts/tmux_deliver.py         types the queued line + Enter into the pane once idle
  hooks/context_watch.py          Stop + PostToolUse hook: >250k → "run the compact
                                  protocol"; at Stop also delivers a queued compact
  hooks/post_compact_state.py     SessionStart(compact): restore STATE.md
  hooks/precompact_notify.py      PreCompact(auto): TG warning (watcher overrun)
  hooks/notification_tg.py        Notification → TG (approval/idle prompts)
install.sh + merge_settings.py    installer (idempotent, backs up settings.json)
telegram.env.template             → ~/.config/autoresearch/telegram.env
claude_md_snippet.md              paste into each research repo's CLAUDE.md
tests/test_core.py                core suite
tests/verify_compact.sh           compact path: queue → hook → worker → live pane
```

Hook *scripts* ship inside the skill folder, so the package is one directory.
Hook *registration* lives in `~/.claude/settings.json` — Claude Code reads hook
config only from settings files — which is what `merge_settings.py` wires up
(commands point into `$HOME/.claude/skills/autoresearch/hooks/`). The hooks
self-gate on `agent_notes/` in the cwd, i.e. they act only in repos where the
autoresearch workflow is used.

## Q1 — Persistence: is a skill the right vehicle? Yes.

- A personal skill at `~/.claude/skills/autoresearch/SKILL.md` **persists across
  sessions and applies in every project**. Each session Claude sees only its
  name + description (a few tokens); the full body + references load on demand.
- Auto-invocation works by matching the description against your task — good
  but probabilistic. Two ways to make it deterministic:
  1. paste `claude_md_snippet.md` into each research repo's `CLAUDE.md`
     ("any research task MUST follow the autoresearch skill") — CLAUDE.md is
     always loaded and reloaded from disk after compaction;
  2. type `/autoresearch` yourself when starting a task.
- Division of labor: CLAUDE.md = short always-on pointers; the skill = the full
  procedure, loaded when working. Don't duplicate content between them.

## Q2 — Autonomous compact (no human keystroke)

`/compact <msg>` typed into the session's terminal triggers compaction, and the
`<msg>` steers the summarizer. Claude Code runs in a tmux pane, so the command
is typed into that pane with tmux. The typing is done by the Stop hook, which
runs outside the Bash sandbox and holds the pane id in `$TMUX_PANE`.

```
after every tool call (PostToolUse) and at every turn end (Stop):
            context_watch.py reads real context from the transcript (last
            main-chain assistant usage: input + cache_read + cache_creation;
            subagent sidechains excluded); >250k? nudge once: "finish the task,
            then run the compact protocol" (PostToolUse: additionalContext
            mid-turn; Stop: block with reason; re-nudges every +40k if ignored)
agent     → finishes task → actualizes artifacts → writes agent_notes/STATE.md
            (incl. the 1–2 sentence compact message per your guidelines)
          → tg_notify "ready to compact"
          → request_compact.py "/compact <msg>"
            (writes .claude/autoresearch/compact_request_<pane>.json)
          → ends its reply
turn ends → Stop hook of the same pane consumes the request file, spawns
            tmux_deliver.py detached, exits
worker    → tmux_deliver.py waits for the TUI to go idle (no spinner line),
            types "/compact <msg>", 0.5 s, Enter
harness   → compacts with the agent's instructions; SessionStart(compact) hook
            restores STATE.md + recovery text into the fresh context
worker    → waits for the compacting spinner to clear, types "continue", Enter
agent     → re-reads the files STATE.md points to, resumes from "Next steps"
```

Two layers of losslessness: the `/compact <msg>` steers the summary, AND durable
state lives in files whose restoration is done by the hook — independent of
what the summarizer kept. Built-in auto-compact (far end of the ~1M window)
stays a safety net; if it ever fires, `precompact_notify` TG-warns you and
recovery is identical: read `STATE.md`.

`request_compact.py`, the hook and `tmux_deliver.py` accept only `/compact`
and `/clear`.

**Requirements**: Claude Code started inside tmux; the repo has `agent_notes/`.
**Several agents on one machine**: request and watcher-state files are keyed
by `$TMUX_PANE`, so agents sharing a repo dir never consume each other's
requests; each hook only types into its own pane.
**Fallback**: `request_compact.py` refuses (not inside tmux) → the agent ends
its reply asking you to paste the `/compact <msg>` line (also in the TG ping).
**Delivery log**: `<repo>/.claude/autoresearch/deliver.log`; a failed delivery
also TG-pings the line to paste.

Verify the compact path on each machine:
`bash /Users/ramazan/claude_sessions/autoresearch_design/tests/verify_compact.sh`

**Subagents** cannot be compacted (`/compact` is a session command; a subagent
has no pane). The hook watches each subagent's own transcript instead
(`<session>/subagents/agent-<id>.jsonl`): above `AUTORESEARCH_SUB_CTX_LIMIT`
(default 350000) it tells the subagent to write its state to its handoff file
and return, so the main agent spawns a fresh successor (the playbook's
fresh-context rule, enforced by the hook). A subagent starts at ~20k tokens
(system prompt + tools; measured on 2.1.251) and is never nudged before it has
grown `AUTORESEARCH_SUB_MIN_GROWTH` (default 5000) past its first measurement,
so a limit below its start context cannot livelock the successor chain.

**After the compact** the session would sit at the prompt (the SessionStart
hook only injects STATE.md, it does not start a turn), so 2 s after `/compact`
the worker types a follow-up — `continue` by default,
`request_compact.py --then "<text>"` to change it, `--then ""` for none.
Claude Code queues input typed during compaction and runs it as the next
turn, so no spinner detection is involved. The follow-up is a plain message;
slash commands are refused there.

Knobs: `AUTORESEARCH_CTX_LIMIT` (default 250000), `AUTORESEARCH_SUB_CTX_LIMIT`
(default 350000), `AUTORESEARCH_SUB_MIN_GROWTH` (default 5000),
`AUTORESEARCH_CTX_STEP` (re-nudge step, default 40000; the dampener re-arms as
soon as the context shrinks, i.e. after any compact or `/clear`) — env vars. The watcher and the notification
hooks are inert outside research repos (they require an `agent_notes/` dir in
the cwd), so ordinary sessions never get nudged or pinged.

## The scripts

**`gpu_free.py`** (per the design doc: 15 s window, avg util + avg VRAM):
```
python3 ~/.claude/skills/autoresearch/scripts/gpu_free.py            # table
python3 ~/.claude/skills/autoresearch/scripts/gpu_free.py --json     # for agents
```
Also lists compute processes with owners, because avg util alone
misclassifies: a GPU at 0% util with 40 GB parked by someone's process is
**PARKED**, not FREE. Statuses: FREE / PARKED / BUSY; prints an
`export CUDA_VISIBLE_DEVICES=...` recommendation; exit 0 iff ≥1 FREE.
Smoke-test on a real GPU box: `--window 5`.

**`tg_notify.sh "message"`** — Telegram sendMessage.
- Credentials: `TG_BOT_TOKEN` and `TG_CHAT_ID` in
  `~/.config/autoresearch/telegram.env` (install creates the template).
- Exit 0 only when Telegram answers `"ok":true`; otherwise the API error goes
  to stderr and exit 1.
- Working hours 10:00–22:00 Asia/Dubai: outside them delivery is silent (no
  sound, message still arrives). Hostname prefix so multiple servers are
  distinguishable.
- Two notification layers: the skill has the agent send pings (question for
  you, REPORT.md ready, run crashed, ready-to-compact), and the Notification
  hook forwards harness-level prompts (approval/idle) in research repos.
- If the Bash sandbox is enabled, `merge_settings.py` allowlists
  `api.telegram.org` in `sandbox.network.allowedDomains`; without it the
  agent's own `curl` is blocked (hooks are not sandboxed).

**`trash.py PATH...`** — moves paths into `<git root>/trash/` instead of
deleting. Nothing in trash/ is ever overwritten: on a name collision the
existing trash entry is first shelved under a timestamp suffix and the incoming
file takes the clean name (newest = clean name). The skill's cleanup step uses
it; you empty `trash/` manually.

**Compact delivery** (see Q2 + `references/self_compact.md`):
- `request_compact.py "/compact <msg>"` — agent-side; writes
  `<repo>/.claude/autoresearch/compact_request_<pane>.json`; refuses without
  `$TMUX_PANE` or `agent_notes/`.
- `tmux_deliver.py [--pane P] [--delay S] [--max-wait S] [--then TEXT] [--now] -- TEXT`
  — spawned by the Stop hook (detached); busy while the pane shows a spinner
  line (`…(Ns` / `Compacting conversation` in Claude Code 2.1, `esc to
  interrupt` in older builds); `--then` types the follow-up 2 s after the
  command (the TUI queues it behind the compaction).

## Install

On this Mac, from a Claude Code session (the `!` prefix runs it as you):

```
! bash /Users/ramazan/claude_sessions/autoresearch_design/install.sh
```

On each GPU server: copy this folder over (scp/rsync/git) and run
`bash install.sh` there too. Then everywhere:

1. edit `~/.config/autoresearch/telegram.env`;
2. test: `bash ~/.claude/skills/autoresearch/scripts/tg_notify.sh "hello"`;
3. verify the compact path:
   `bash /Users/ramazan/claude_sessions/autoresearch_design/tests/verify_compact.sh`;
4. run Claude Code inside tmux in research repos;
5. paste `claude_md_snippet.md` into each research repo's `CLAUDE.md`.

The installer is idempotent and backs up `settings.json` before merging the
five hook entries (and the Telegram domain allowlist if the sandbox is
enabled). Existing settings are preserved. `install.sh` copies over the
installed skill dir without deleting; files removed from the package must be
trashed from `~/.claude/skills/autoresearch/` by hand.

## Changes vs. your drafts (so you can review)

- **subagent_playbook**: session-dir version taken as base (2-agent cap,
  `gpt-5.6-sol`, `</dev/null` gotcha — all kept). Updated model tiers to the
  current lineup (top tier = session model, currently fable; per-subagent
  reasoning effort can't be set via the Task tool — it inherits the session's
  xhigh, so tier choice = model choice). Handoff files moved from `/tmp` to
  `agent_notes/tasks/<task>/subagents/` (persistent, part of the task record;
  `/tmp` still OK for throwaway). Added the **subagent artifact contract**
  (allowed write paths, disjoint files, main agent integrates) and the
  **fresh-context hard rule** — both implementing design-doc bullets.
- **compact_guidelines**: embedded verbatim inside `compact_protocol.md`, plus
  the trigger rules, the step list, and the STATE.md template around them.
- **design doc**: every numbered item is mapped into SKILL.md §1–§10; the
  anti-lazy interview became `intake_checklist.md` with explicit
  hallucination hot-spots (paths, metric definitions, baseline configs).

## Notes / limitations

- 250k as a threshold assumes a `[1m]` model — your default is
  `claude-fable-5[1m]`. If a server session runs a 200k model, lower
  `AUTORESEARCH_CTX_LIMIT` (e.g. 150000).
- Verified live on Claude Code 2.1.251 (2026-08-28): Stop-hook block+reason,
  SessionStart(compact) `additionalContext` restores STATE.md, `/compact <msg>`
  typed into the pane compacts, hooks run unsandboxed with `$TMUX_PANE` set.
- `agent_notes/` is meant to be committed (it's the knowledge base);
  `trash/` and `.claude/` belong in `.gitignore` (skill §8 enforces).
- Tests:
  - `tests/test_core.py` — watcher state machine, request consumption,
    STATE.md restore hook, trash shelve-don't-overwrite, merger, syntax.
  - `tests/verify_compact.sh` — queue → hook → detached worker → live tmux
    pane (fake TUI showing the 2.1 spinner). Run it yourself.
  - `gpu_free` sampling path needs a real GPU box for its smoke test.
