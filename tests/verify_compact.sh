#!/usr/bin/env bash
# verify_compact.sh — proves the autonomous-compact machinery end to end.
# It drives tmux and spawns background processes (fine from a shell or an agent):
#     bash <package>/tests/verify_compact.sh
#
# Covers:
#   1. request_compact.py — queues into ~/.claude/autoresearch/ (HOME is a temp
#                           dir here) from any cwd, falls back into the repo when
#                           HOME is unwritable, refuses non-allowlisted commands,
#                           no tmux, no agent_notes/
#   2. tmux_deliver.py    — waits out the 2.1 spinner, types text THEN Enter
#                           (fake tmux shim), gives up after max-wait
#   3. Stop hook          — consumes the request, spawns a detached worker that
#                           outlives the hook (fake tmux shim); stale requests
#                           are set aside
#   4. live               — request -> Stop hook -> real tmux pane running a fake TUI
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
SCRIPTS="$PKG/skill/autoresearch/scripts"
HOOK="$PKG/skill/autoresearch/hooks/context_watch.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/verify_compact.XXXXXX")"
export HOME="$T/home"; mkdir -p "$HOME"          # request dir + deliver.log live under $HOME
REQ="$HOME/.claude/autoresearch"
export TG_CONF=/nonexistent/telegram.env   # failure paths must not ping Telegram
pass=0; fail=0
ck() { if eval "$2"; then echo "PASS: $1"; pass=$((pass+1)); else echo "FAIL: $1"; fail=$((fail+1)); fi; }
have_tmux=1; command -v tmux >/dev/null 2>&1 || have_tmux=0
chmod +x "$HERE/helpers/faketmux/tmux"

echo '=== 1. request_compact.py (agent-side queue) ==='
REPO="$T/repo"; mkdir -p "$REPO/agent_notes" "$REPO/sub"; mkdir -p "$REPO/agent_notes/tasks/2026-10-05_08-00_t1"; : > "$REPO/agent_notes/tasks/2026-10-05_08-00_t1/STATE.md"
( cd "$REPO" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact keep project ctx, details in notes' >/dev/null )
J="$REQ/compact_request_p7.json"
ck "request written into ~/.claude/autoresearch/, keyed by pane" "[ -f '$J' ] && grep -q '/compact keep project ctx' '$J'"
ck "request records the task's STATE.md for the restore hook" "grep -q '\"task_state\": \"$REPO/agent_notes/tasks/2026-10-05_08-00_t1/STATE.md\"' '$J'"
( cd "$REPO" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" '/compact no task' >/dev/null 2>&1 ); RC=$?
ck "/compact without --task refused (nonzero)" "[ $RC -ne 0 ]"
( cd "$REPO" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" --task nope '/compact y' >/dev/null 2>&1 ); RC=$?
ck "--task without a STATE.md refused (nonzero)" "[ $RC -ne 0 ]"
( cd "$REPO/sub" && TMUX_PANE='%9' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact from a subdir' >/dev/null )
ck "queued from a subdirectory (agent cd'd): same location, shell cwd recorded" "grep -q '/compact from a subdir' '$REQ/compact_request_p9.json' && grep -q '\"shell_cwd\": \"$REPO/sub\"' '$REQ/compact_request_p9.json'"
( cd "$REPO" && HOME=/nonexistent_home_xyz TMUX_PANE='%9' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact fallback' >/dev/null 2>&1 ); RC=$?
ck "HOME unwritable (sandbox): falls back into <cwd>/.claude/autoresearch/" "[ $RC -eq 0 ] && grep -q '/compact fallback' '$REPO/.claude/autoresearch/compact_request_p9.json'"
( cd "$REPO" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" 'rm -rf /tmp/x' >/dev/null 2>&1 ); RC=$?
ck "non-allowlisted command refused (nonzero)" "[ $RC -ne 0 ]"
( cd "$REPO" && unset TMUX_PANE && python3 "$SCRIPTS/request_compact.py" --task t1 '/compact y' >/dev/null 2>&1 ); RC=$?
ck "missing \$TMUX_PANE refused (nonzero)" "[ $RC -ne 0 ]"
mkdir -p "$T/plain"
( cd "$T/plain" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact y' >/dev/null 2>&1 ); RC=$?
ck "no agent_notes/ in cwd or above refused (nonzero)" "[ $RC -ne 0 ]"
( cd "$REPO" && TMUX_PANE='%8' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact keep z' --then '' >/dev/null )
J8="$REQ/compact_request_p8.json"
ck "--then after the command: '' means no follow-up, flag not leaked into the message" "grep -q '\"then\": \"\"' '$J8' && grep -q '\"command\": \"/compact keep z\"' '$J8'"
( cd "$REPO" && TMUX_PANE='%8' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact keep z' --then 'go on' >/dev/null )
ck "--then after the command: custom follow-up recorded" "grep -q '\"then\": \"go on\"' '$J8'"
LONGMSG="/compact $(printf 'word %.0s' $(seq 1 200))"
( cd "$REPO" && TMUX_PANE='%8' python3 "$SCRIPTS/request_compact.py" "$LONGMSG" >/dev/null 2>&1 ); RC=$?
ck "line over 800 chars refused (nonzero)" "[ $RC -ne 0 ]"

echo '=== 2. tmux_deliver.py logic (fake tmux shim) ==='
FTLOG="$T/ft2.log"
( export PATH="$HERE/helpers/faketmux:$PATH" FT_LOG="$FTLOG" FT_STATE="$T/ft2.state" FT_BUSY_CALLS=2 DELIVER_LOG="$T/d2.log"
  : > "$FT_LOG"; : > "$FT_STATE"
  python3 "$SCRIPTS/tmux_deliver.py" --now --pane sess --delay 0 --max-wait 20 -- '/compact keep ctx; details in notes' )
TEXTLINE=$(grep -n '^-l$' "$FTLOG" | tail -1 | cut -d: -f1)
ENTERLINE=$(grep -n '^Enter$' "$FTLOG" | tail -1 | cut -d: -f1)
ck "spinner recognised as busy: 2 busy polls + 1 idle poll" "[ \$(grep -c '^capture-pane$' '$FTLOG') -eq 3 ]"
ck "text precedes Enter" "[ -n \"$TEXTLINE\" ] && [ -n \"$ENTERLINE\" ] && [ \"$TEXTLINE\" -lt \"$ENTERLINE\" ]"
ck "literal text sent verbatim" "grep -q 'keep ctx' '$FTLOG'"
ck "Enter sent exactly once" "[ \$(grep -c '^Enter$' '$FTLOG') -eq 1 ]"
FTLOG2E="$T/ft2e.log"
LONG2E="/compact $(printf 'w%.0s' $(seq 1 690))"
( export PATH="$HERE/helpers/faketmux:$PATH" FT_LOG="$FTLOG2E" FT_STATE="$T/ft2e.state" FT_BUSY_CALLS=0 DELIVER_LOG="$T/d2e.log"
  : > "$FT_LOG"; : > "$FT_STATE"
  python3 "$SCRIPTS/tmux_deliver.py" --now --pane sess --delay 0 --max-wait 20 -- "$LONG2E" )
ck "699-char line typed in 4 pieces (<=200 chars each), Enter once" "[ \$(grep -c '^-l$' '$FTLOG2E') -eq 4 ] && [ \$(grep -c '^Enter$' '$FTLOG2E') -eq 1 ] && [ \$(awk 'length > 200' '$FTLOG2E' | wc -l) -eq 0 ]"
( export PATH="$HERE/helpers/faketmux:$PATH" FT_LOG="$T/ft2b.log" FT_STATE="$T/ft2b.state" FT_BUSY_CALLS=9999 DELIVER_LOG="$T/d2b.log"
  : > "$FT_LOG"; : > "$FT_STATE"
  python3 "$SCRIPTS/tmux_deliver.py" --now --pane sess --delay 0 --max-wait 4 -- '/compact x' >/dev/null 2>&1 ); RC=$?
ck "stays busy past max-wait -> no Enter, nonzero exit" "! grep -q '^Enter$' '$T/ft2b.log' && [ $RC -ne 0 ]"
( python3 "$SCRIPTS/tmux_deliver.py" --now --pane sess -- 'echo hi' >/dev/null 2>&1 ); RC=$?
ck "non-allowlisted text refused (nonzero)" "[ $RC -ne 0 ]"
FTLOG3="$T/ft2c.log"
( export PATH="$HERE/helpers/faketmux:$PATH" FT_LOG="$FTLOG3" FT_STATE="$T/ft2c.state" FT_BUSY_CALLS=0 DELIVER_LOG="$T/d2c.log"
  : > "$FT_LOG"; : > "$FT_STATE"
  python3 "$SCRIPTS/tmux_deliver.py" --now --pane sess --delay 0 --max-wait 20 --then 'continue' -- '/compact keep ctx' )
CMDLINE=$(grep -n '^/compact keep ctx$' "$FTLOG3" | tail -1 | cut -d: -f1)
FOLLOWLINE=$(grep -n '^continue$' "$FTLOG3" | tail -1 | cut -d: -f1)
ck "--then: follow-up typed after the command, Enter sent twice" "[ -n \"$CMDLINE\" ] && [ -n \"$FOLLOWLINE\" ] && [ \"$CMDLINE\" -lt \"$FOLLOWLINE\" ] && [ \$(grep -c '^Enter$' '$FTLOG3') -eq 2 ]"
( python3 "$SCRIPTS/tmux_deliver.py" --now --pane sess --then '/clear' -- '/compact x' >/dev/null 2>&1 ); RC=$?
ck "--then with a slash command refused (nonzero)" "[ $RC -ne 0 ]"
ck "--then: follow-up typed without further polling (queued by the TUI)" "[ \$(grep -c '^capture-pane$' '$FTLOG3') -eq 1 ]"

echo '=== 3. Stop hook consumes request + detached worker (fake tmux shim) ==='
REPO3="$T/repo3"; mkdir -p "$REPO3/agent_notes"; mkdir -p "$REPO3/agent_notes/tasks/2026-10-05_08-00_t1"; : > "$REPO3/agent_notes/tasks/2026-10-05_08-00_t1/STATE.md"
( cd "$REPO3" && TMUX_PANE='%3' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact hook path works' >/dev/null )
( export PATH="$HERE/helpers/faketmux:$PATH" FT_LOG="$T/ft3.log" FT_STATE="$T/ft3.state" FT_BUSY_CALLS=1
  : > "$FT_LOG"; : > "$FT_STATE"
  START=$(date +%s)
  printf '{"cwd":"%s","hook_event_name":"Stop","stop_hook_active":true}' "$REPO3" \
    | TMUX_PANE='%3' python3 "$HOOK" > "$T/hook3.out" 2>&1
  echo $(( $(date +%s) - START )) > "$T/hook3.secs" )
ck "hook returned fast (did not wait for delivery)" "[ \$(cat '$T/hook3.secs') -lt 5 ]"
ck "request consumed -> last_compact_request_p3.json" "[ ! -f '$REQ/compact_request_p3.json' ] && [ -f '$REQ/last_compact_request_p3.json' ]"
ck "hook emitted no output (no nudge)" "[ ! -s '$T/hook3.out' ]"
for _ in $(seq 1 40); do grep -q '^Enter$' "$T/ft3.log" 2>/dev/null && break; sleep 0.5; done
ck "detached worker typed after the hook exited" "grep -q 'hook path works' '$T/ft3.log' && grep -q '^Enter$' '$T/ft3.log'"
for _ in $(seq 1 30); do grep -q '^continue$' "$T/ft3.log" 2>/dev/null && break; sleep 0.5; done
ck "default follow-up 'continue task <task_id>' typed after the command" "grep -q '^continue task 2026-10-05_08-00_t1$' '$T/ft3.log'"
ck "deliver.log records the delivery" "grep -q 'typed into %3' '$REQ/deliver.log'"
( cd "$REPO3" && TMUX_PANE='%3' python3 "$SCRIPTS/request_compact.py" --task t1 '/compact stale one' >/dev/null )
sleep 1
( export PATH="$HERE/helpers/faketmux:$PATH" FT_LOG="$T/ft3s.log" FT_STATE="$T/ft3s.state" FT_BUSY_CALLS=0 AUTORESEARCH_REQUEST_TTL=0
  : > "$FT_LOG"; : > "$FT_STATE"
  printf '{"cwd":"%s","hook_event_name":"Stop"}' "$REPO3" | TMUX_PANE='%3' python3 "$HOOK" >/dev/null 2>&1 )
ck "request older than the TTL is set aside as stale, nothing typed" "[ -f '$REQ/stale_compact_request_p3.json' ] && grep -q 'SKIPPED stale' '$REQ/deliver.log' && [ ! -s '$T/ft3s.log' ]"

echo '=== 4. live: request -> Stop hook -> real tmux pane ==='
if [ "$have_tmux" -eq 0 ]; then echo 'SKIP: tmux not installed'; else
  REPO4="$T/repo4"; mkdir -p "$REPO4/agent_notes"; mkdir -p "$REPO4/agent_notes/tasks/2026-10-05_08-00_t1"; : > "$REPO4/agent_notes/tasks/2026-10-05_08-00_t1/STATE.md"
  OUT4="$T/recv4.txt"; SESS4="verify_$$"
  tmux new-session -d -s "$SESS4" -x 120 -y 30 "python3 '$HERE/helpers/tui_stub.py' '$OUT4' 6 2"
  sleep 1
  ( cd "$REPO4" && TMUX_PANE="$SESS4" python3 "$SCRIPTS/request_compact.py" --task t1 --then 'go on' '/compact live hook delivery works' >/dev/null )
  printf '{"cwd":"%s","hook_event_name":"Stop"}' "$REPO4" | TMUX_PANE="$SESS4" python3 "$HOOK"
  for _ in $(seq 1 60); do grep -q '^go on$' "$OUT4" 2>/dev/null && break; sleep 0.5; done
  ck "live: line submitted into the real pane" "grep -q '^/compact live hook delivery works$' '$OUT4' 2>/dev/null"
  ck "live: worker waited for the spinner to clear" "grep -Eq 'typed into $SESS4 after [1-9][0-9]*s idle-wait' '$REQ/deliver.log'"
  ck "live: follow-up typed during the fake compaction is read afterwards (queued)" "grep -q '^go on$' '$OUT4' 2>/dev/null && grep -q 'typed follow-up into $SESS4' '$REQ/deliver.log'"
  tmux kill-session -t "$SESS4" 2>/dev/null || true
fi

echo; echo "$pass passed, $fail failed  (workdir: $T)"
[ "$fail" -eq 0 ]
