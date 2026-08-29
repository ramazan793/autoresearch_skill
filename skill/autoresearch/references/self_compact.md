# Self-issued compact (autonomous, no human keystroke)

`/compact <msg>` typed into the session's terminal triggers compaction, and the
`<msg>` steers the summarizer. Claude Code runs inside a tmux pane, so the
command is typed into that pane with tmux. The Bash sandbox blocks the agent's
own shell from reaching tmux (and from writing outside the repo), so the typing
is done by the Stop hook, which runs outside the sandbox and holds the pane id
in `$TMUX_PANE`.

## Flow

1. Agent: `python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <msg>"`
   writes `<repo>/.claude/autoresearch/compact_request_<pane>.json` (pane =
   `$TMUX_PANE`, e.g. `%3` → `p3`; only `/compact` and `/clear` are accepted).
   The agent then ends its reply.
2. Stop hook (`hooks/context_watch.py`) of the same pane: consumes the file
   (renamed to `last_compact_request_<pane>.json`) and spawns
   `scripts/tmux_deliver.py` detached (double fork + setsid), then exits.
   Requests of other panes (other agents in the same repo) are left alone.
3. Worker: waits 3 s, polls `tmux capture-pane` until no spinner line is shown
   (`…(Ns` / `Compacting conversation` in Claude Code 2.1, `esc to interrupt`
   in older builds), types the text with `send-keys -l`, 0.5 s later sends
   Enter as a separate key event. Log: `<repo>/.claude/autoresearch/deliver.log`.
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
- The repo has `agent_notes/` (hooks are inert elsewhere).
- `.claude/` is gitignored (the request and log files live there).

## Fallback

If `request_compact.py` refuses, the agent ends its reply asking the user to
paste the `/compact <msg>` line (also included in the TG ping).

## Verify

`bash ~/claude_sessions/autoresearch_design/tests/verify_compact.sh` checks
queue → hook → worker → pane, including a live tmux pane. Run it yourself.
