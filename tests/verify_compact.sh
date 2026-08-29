#!/usr/bin/env bash
# verify_compact.sh — proves the autonomous-compact machinery end to end.
# Run it yourself (it drives tmux and spawns background processes):
#     bash /Users/ramazan/claude_sessions/autoresearch_design/tests/verify_compact.sh
#
# Covers:
#   1. request_compact.py — queues into <repo>/.claude/autoresearch/, refuses
#                           non-allowlisted commands, no tmux, no agent_notes/
#   2. tmux_deliver.py    — waits out the 2.1 spinner, types text THEN Enter
#                           (fake tmux shim), gives up after max-wait
#   3. Stop hook          — consumes the request, spawns a detached worker that
#                           outlives the hook (fake tmux shim)
#   4. live               — request -> Stop hook -> real tmux pane running a fake TUI
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
SCRIPTS="$PKG/skill/autoresearch/scripts"
HOOK="$PKG/skill/autoresearch/hooks/context_watch.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/verify_compact.XXXXXX")"
export TG_CONF=/nonexistent/telegram.env   # failure paths must not ping Telegram
pass=0; fail=0
ck() { if eval "$2"; then echo "PASS: $1"; pass=$((pass+1)); else echo "FAIL: $1"; fail=$((fail+1)); fi; }
have_tmux=1; command -v tmux >/dev/null 2>&1 || have_tmux=0
chmod +x "$HERE/helpers/faketmux/tmux"

echo '=== 1. request_compact.py (agent-side queue) ==='
REPO="$T/repo"; mkdir -p "$REPO/agent_notes"
( cd "$REPO" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" '/compact keep project ctx, details in notes' >/dev/null )
J="$REPO/.claude/autoresearch/compact_request_p7.json"
ck "request written into <repo>/.claude/autoresearch/, keyed by pane" "[ -f '$J' ] && grep -q '/compact keep project ctx' '$J'"
( cd "$REPO" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" 'rm -rf /tmp/x' >/dev/null 2>&1 ); RC=$?
ck "non-allowlisted command refused (nonzero)" "[ $RC -ne 0 ]"
( cd "$REPO" && unset TMUX_PANE && python3 "$SCRIPTS/request_compact.py" '/compact y' >/dev/null 2>&1 ); RC=$?
ck "missing \$TMUX_PANE refused (nonzero)" "[ $RC -ne 0 ]"
mkdir -p "$T/plain"
( cd "$T/plain" && TMUX_PANE='%7' python3 "$SCRIPTS/request_compact.py" '/compact y' >/dev/null 2>&1 ); RC=$?
ck "no agent_notes/ refused (nonzero)" "[ $RC -ne 0 ]"
( cd "$REPO" && TMUX_PANE='%8' python3 "$SCRIPTS/request_compact.py" '/compact keep z' --then '' >/dev/null )
J8="$REPO/.claude/autoresearch/compact_request_p8.json"
ck "--then after the command: '' means no follow-up, flag not leaked into the message" "grep -q '\"then\": \"\"' '$J8' && grep -q '\"command\": \"/compact keep z\"' '$J8'"
( cd "$REPO" && TMUX_PANE='%8' python3 "$SCRIPTS/request_compact.py" '/compact keep z' --then 'go on' >/dev/null )
ck "--then after the command: custom follow-up recorded" "grep -q '\"then\": \"go on\"' '$J8'"

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
REPO3="$T/repo3"; mkdir -p "$REPO3/agent_notes"
( cd "$REPO3" && TMUX_PANE='%3' python3 "$SCRIPTS/request_compact.py" '/compact hook path works' >/dev/null )
( export PATH="$HERE/helpers/faketmux:$PATH" FT_LOG="$T/ft3.log" FT_STATE="$T/ft3.state" FT_BUSY_CALLS=1
  : > "$FT_LOG"; : > "$FT_STATE"
  START=$(date +%s)
  printf '{"cwd":"%s","hook_event_name":"Stop","stop_hook_active":true}' "$REPO3" \
    | TMUX_PANE='%3' python3 "$HOOK" > "$T/hook3.out" 2>&1
  echo $(( $(date +%s) - START )) > "$T/hook3.secs" )
ck "hook returned fast (did not wait for delivery)" "[ \$(cat '$T/hook3.secs') -lt 5 ]"
ck "request consumed -> last_compact_request_p3.json" "[ ! -f '$REPO3/.claude/autoresearch/compact_request_p3.json' ] && [ -f '$REPO3/.claude/autoresearch/last_compact_request_p3.json' ]"
ck "hook emitted no output (no nudge)" "[ ! -s '$T/hook3.out' ]"
for _ in $(seq 1 40); do grep -q '^Enter$' "$T/ft3.log" 2>/dev/null && break; sleep 0.5; done
ck "detached worker typed after the hook exited" "grep -q 'hook path works' '$T/ft3.log' && grep -q '^Enter$' '$T/ft3.log'"
for _ in $(seq 1 30); do grep -q '^continue$' "$T/ft3.log" 2>/dev/null && break; sleep 0.5; done
ck "default follow-up 'continue' typed after the command" "grep -q '^continue$' '$T/ft3.log'"
ck "deliver.log records the delivery" "grep -q 'typed into %3' '$REPO3/.claude/autoresearch/deliver.log'"

echo '=== 4. live: request -> Stop hook -> real tmux pane ==='
if [ "$have_tmux" -eq 0 ]; then echo 'SKIP: tmux not installed'; else
  REPO4="$T/repo4"; mkdir -p "$REPO4/agent_notes"
  OUT4="$T/recv4.txt"; SESS4="verify_$$"
  tmux new-session -d -s "$SESS4" -x 120 -y 30 "python3 '$HERE/helpers/tui_stub.py' '$OUT4' 6 2"
  sleep 1
  ( cd "$REPO4" && TMUX_PANE="$SESS4" python3 "$SCRIPTS/request_compact.py" --then 'go on' '/compact live hook delivery works' >/dev/null )
  printf '{"cwd":"%s","hook_event_name":"Stop"}' "$REPO4" | TMUX_PANE="$SESS4" python3 "$HOOK"
  for _ in $(seq 1 60); do grep -q '^go on$' "$OUT4" 2>/dev/null && break; sleep 0.5; done
  ck "live: line submitted into the real pane" "grep -q '^/compact live hook delivery works$' '$OUT4' 2>/dev/null"
  ck "live: worker waited for the spinner to clear" "grep -Eq 'typed into .* after [1-9][0-9]*s idle-wait' '$REPO4/.claude/autoresearch/deliver.log'"
  ck "live: follow-up typed during the fake compaction is read afterwards (queued)" "grep -q '^go on$' '$OUT4' 2>/dev/null && grep -q 'typed follow-up into' '$REPO4/.claude/autoresearch/deliver.log'"
  tmux kill-session -t "$SESS4" 2>/dev/null || true
fi

echo; echo "$pass passed, $fail failed  (workdir: $T)"
[ "$fail" -eq 0 ]
