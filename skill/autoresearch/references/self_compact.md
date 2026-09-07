# Self-issued compact (autonomous, no human keystroke)

`/compact <msg>` typed into the session's terminal triggers compaction, and the
`<msg>` steers the summarizer. Claude Code runs inside a tmux pane, so the
command is typed into that pane with tmux. The Bash sandbox blocks the agent's
own shell from reaching tmux (and from writing outside the repo), so the typing
is done by the Stop hook, which runs outside the sandbox and holds the pane id
in `$TMUX_PANE`.

## Flow

1. Agent: `python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <msg>"`
   writes `~/.claude/autoresearch/compact_request_<pane>.json` (pane =
   `$TMUX_PANE`, e.g. `%3` → `p3`; only `/compact` and `/clear` are accepted,
   max 800 chars — the message is 1–2 sentences, details live in STATE.md).
   Any shell cwd is fine — a worktree, a subdirectory, anywhere with
   `agent_notes/` in it or above it. The agent then ends its reply.

   Why pane-keyed under `$HOME` and not a file in the repo: the Stop hook's
   cwd is Claude Code's *tracked* shell cwd — it follows the agent's `cd`
   inside the project directory and is reset to the project directory when
   the shell leaves it (worktrees). It matches neither the script's own cwd
   (`cd <worktree> && request_compact.py` sees the worktree; stranded a
   request on 2026-09-02) nor the Claude Code process cwd (the agent may work
   in a subdirectory such as `agora_m_generalization/dynaavatar`; stranded one
   on 2026-09-03). The pane id is the only thing both sides share. If `$HOME`
   is not writable (Bash sandbox on), the script falls back to
   `<cwd>/.claude/autoresearch/` with a warning.
2. Stop hook (`hooks/context_watch.py`) of the same pane: looks for
   `compact_request_<pane>.json` in `~/.claude/autoresearch/`, then in
   `<hook cwd>/.claude/autoresearch/` (sandbox fallback, hand-placed files);
   consumes it (renamed to `last_compact_request_<pane>.json`) and spawns
   `scripts/tmux_deliver.py` detached (double fork + setsid), then exits.
   Requests of other panes are left alone. A request older than
   `AUTORESEARCH_REQUEST_TTL` s (default 600) is set aside as
   `stale_compact_request_<pane>.json` and logged, never typed — a compact
   firing long after it was queued would land mid-task. This runs before the
   `agent_notes/` gate, so it also works when the tracked cwd is a
   subdirectory without `agent_notes/`.
3. Worker: waits 3 s, polls `tmux capture-pane` until no spinner line is shown
   (`…(Ns` / `Compacting conversation` in Claude Code 2.1, `esc to interrupt`
   in older builds), types the text with `send-keys -l` in 200-char pieces
   50 ms apart (one big write is taken for a paste, and a pasted `/compact`
   goes to the model as a plain message instead of running), 0.5 s later
   sends Enter as a separate key event. Log: `~/.claude/autoresearch/deliver.log`
   (one log for all panes and repos; each line names the pane, and the
   pickup line names the shell cwd, the file found and the hook cwd).
   On failure it TG-pings the line for the user to paste.
4. Compaction runs; the SessionStart(compact) hook restores `STATE.md`.
5. 2 s later the worker types the follow-up (`continue` by default;
   `request_compact.py --then "<text>"` to change it, `--then ""` for none;
   plain messages only). Claude Code queues input typed during compaction
   and runs it as the next turn (observed on 2.1.251), so the session
   resumes on its own with no spinner detection involved.

## Requirements

- Claude Code started inside tmux (`$TMUX_PANE` set); `request_compact.py`
  refuses otherwise.
- `agent_notes/` in the shell's cwd or one of its parents (`request_compact.py`
  refuses otherwise; the context-watch part of the hook is inert in repos
  without it).
- `~/.claude/autoresearch/` writable from the agent's shell (true with the
  Bash sandbox off; with it on, add that path to `sandbox.filesystem.allowWrite`
  or rely on the in-repo fallback, which only works if the shell did not `cd`
  within the same command).
- `.claude/` is gitignored (the context-watch state files live there).

## Fallback

If `request_compact.py` refuses, the agent ends its reply asking the user to
paste the `/compact <msg>` line (also included in the TG ping).

## Verify

`bash tests/verify_compact.sh` from the package checkout checks
queue → hook → worker → pane, including a live tmux pane. Run it yourself.
