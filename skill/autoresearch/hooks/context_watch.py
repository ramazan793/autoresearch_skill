#!/usr/bin/env python3
"""Stop + PostToolUse hook, two jobs. Files live in <cwd>/.claude/autoresearch/
and are keyed by this session's tmux pane ($TMUX_PANE, e.g. %3 -> p3), so
several agents in the same repo do not touch each other's state.

1. Compact delivery (Stop only): if the agent queued compact_request_<pane>.json
   (via scripts/request_compact.py), consume it and spawn
   scripts/tmux_deliver.py, which types the command into this pane once the
   TUI is idle.
2. Context watch (Stop and PostToolUse): nudge the agent to run the compact
   protocol when session context exceeds AUTORESEARCH_CTX_LIMIT tokens
   (default 250000). Stop: blocks the stop with the nudge as reason.
   PostToolUse: injects the nudge as additionalContext mid-turn. One nudge per
   threshold crossing; re-nudges after AUTORESEARCH_CTX_STEP tokens of
   further growth. The dampener resets as soon as the context shrinks (a
   compact or /clear happened). State in ctx_<pane>.json.
3. Subagent watch (PostToolUse with agent_id in the hook input): reads the
   subagent's own transcript; above AUTORESEARCH_SUB_CTX_LIMIT (default
   350000) tells it to write its state to its handoff file and return, so the
   main agent spawns a fresh successor (state in ctx_sub_<agent_id>.json).
   A subagent starts at ~20k (system prompt + tools) and is never nudged before
   it has grown AUTORESEARCH_SUB_MIN_GROWTH tokens (default 5000) past its
   first measurement, so a limit below the floor cannot livelock successors.
   Subagents never compact and never deliver.

Active only in repos that have an agent_notes/ dir. Fails open on any error.
"""
import json
import os
import subprocess
import sys

LIMIT = int(os.environ.get("AUTORESEARCH_CTX_LIMIT", 250000))
SUB_LIMIT = int(os.environ.get("AUTORESEARCH_SUB_CTX_LIMIT", 350000))
SUB_MIN_GROWTH = int(os.environ.get("AUTORESEARCH_SUB_MIN_GROWTH", 5000))
STEP = int(os.environ.get("AUTORESEARCH_CTX_STEP", 40000))
TAIL_BYTES = 8 * 1024 * 1024
ALLOWED = ("/compact", "/clear")
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")

NUDGE = (
    "[context-watch] Session context is ~{ctx}k tokens (limit {limit}k). Do not "
    "start anything new. If you are mid-task, bring the current task to a clean "
    "stopping point first. Then run the autoresearch compact protocol "
    "(~/.claude/skills/autoresearch/references/compact_protocol.md): actualize "
    "artifacts, update agent_notes/STATE.md incl. the 1-2 sentence compact "
    "message, TG-ping 'ready to compact', then queue the compact with "
    "scripts/request_compact.py and end your reply. Fall back to asking the user "
    "to run it only if request_compact.py refuses."
)

SUB_NUDGE = (
    "[context-watch] Your context (subagent) is ~{ctx}k tokens (limit {limit}k). "
    "Do not start anything new. Write everything you have so far (results, "
    "state, what remains) to your handoff/scratch file (the path given in your "
    "task; otherwise agent_notes/tasks/<task>/subagents/<your_name>_state.md), "
    "then return to the main agent now with a short summary and that path. The "
    "main agent spawns a fresh successor from the file. Subagents never compact."
)


def pane_key():
    pane = os.environ.get("TMUX_PANE", "").strip()
    return "p" + "".join(c for c in pane if c.isalnum()) if pane else ""


def deliver_request(cwd, path, pane):
    consumed = os.path.join(os.path.dirname(path), "last_compact_request_%s.json" % pane_key())
    os.replace(path, consumed)
    try:
        with open(consumed) as f:
            req = json.load(f)
    except (OSError, ValueError):
        return
    command = (req.get("command") or "").strip()
    then = (req.get("then") or "").strip()
    if not command or command.split()[0] not in ALLOWED or then.startswith("/"):
        return
    env = dict(os.environ)
    env["DELIVER_LOG"] = os.path.join(cwd, ".claude", "autoresearch", "deliver.log")
    args = [sys.executable, os.path.join(SCRIPTS, "tmux_deliver.py"), "--pane", pane]
    if then:
        args += ["--then", then]
    subprocess.run(args + ["--", command], cwd=cwd, env=env, timeout=30,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def context_tokens(transcript_path, sidechain=False):
    """Context of the last assistant turn. Main transcript: skip sidechain
    records (subagents). Subagent transcript (sidechain=True): all records are
    sidechain."""
    with open(transcript_path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        tail = f.read().decode("utf-8", "replace")
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("isSidechain") and not sidechain:
            continue
        msg = obj.get("message") or {}
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if obj.get("type") == "assistant" and isinstance(usage, dict):
            if (msg.get("model") or "").startswith("<"):
                continue
            return (usage.get("input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0))
    return None


def load_state(path, session_id):
    """State dict for this session; empty if the file belongs to another one."""
    try:
        with open(path) as f:
            state = json.load(f)
    except Exception:
        return {}
    return state if state.get("session_id") == session_id else {}


def save_state(path, session_id, **fields):
    state = load_state(path, session_id)
    state.update(fields, session_id=session_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def nudge_once(state_path, sid, ctx, limit):
    """True if a nudge is due now: first crossing of `limit`, or +STEP since
    the last nudge. Context only shrinks when a compact (or /clear) happened,
    so a measurement below the last nudge point re-arms the watch."""
    last = load_state(state_path, sid).get("last_nudge_ctx", 0)
    if last and ctx < last:
        save_state(state_path, sid, last_nudge_ctx=0)
        last = 0
    if ctx > limit and ctx >= last + (STEP if last else 0):
        save_state(state_path, sid, last_nudge_ctx=ctx)
        return True
    return False


def watch_subagent(data, state_dir):
    """Subagent tool call: read the subagent's own transcript
    (<transcript dir>/<session_id>/subagents/agent-<id>.jsonl); above
    SUB_LIMIT tell it to hand off and return. Subagents never compact."""
    transcript, sid, aid = data.get("transcript_path"), data.get("session_id", ""), data["agent_id"]
    if not transcript:
        return
    sub = os.path.join(os.path.dirname(transcript), sid, "subagents", "agent-%s.jsonl" % aid)
    if not os.path.isfile(sub):
        return
    ctx = context_tokens(sub, sidechain=True)
    if ctx is None:
        return
    state_path = os.path.join(state_dir, "ctx_sub_%s.json" % aid)
    first = load_state(state_path, sid).get("first_ctx")
    if first is None:
        save_state(state_path, sid, first_ctx=ctx)
        first = ctx
    if ctx < first + SUB_MIN_GROWTH:
        return
    if nudge_once(state_path, sid, ctx, SUB_LIMIT):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": data.get("hook_event_name") or "PostToolUse",
            "additionalContext": SUB_NUDGE.format(ctx=ctx // 1000, limit=SUB_LIMIT // 1000)}}))


def main():
    data = json.load(sys.stdin)
    cwd = data.get("cwd") or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, "agent_notes")):
        return
    state_dir = os.path.join(cwd, ".claude", "autoresearch")
    if data.get("agent_id"):
        if data.get("hook_event_name") == "PostToolUse":
            watch_subagent(data, state_dir)
        return
    event = data.get("hook_event_name") or "Stop"
    pane = os.environ.get("TMUX_PANE", "").strip()
    key = pane_key() or "nopane"

    if event == "Stop":
        request = os.path.join(state_dir, "compact_request_%s.json" % key)
        if pane and os.path.isfile(request):
            deliver_request(cwd, request, pane)
            return
        if data.get("stop_hook_active"):
            return

    transcript = data.get("transcript_path")
    if not transcript or not os.path.isfile(transcript):
        return
    ctx = context_tokens(transcript)
    if ctx is None:
        return

    if nudge_once(os.path.join(state_dir, "ctx_%s.json" % key), data.get("session_id", ""), ctx, LIMIT):
        nudge = NUDGE.format(ctx=ctx // 1000, limit=LIMIT // 1000)
        if event == "Stop":
            # decision/reason emitted both top-level and under hookSpecificOutput:
            # docs and observed behavior disagree on the shape; parsers ignore
            # whichever variant they don't know.
            print(json.dumps({
                "decision": "block", "reason": nudge,
                "hookSpecificOutput": {"hookEventName": "Stop",
                                       "decision": "block", "reason": nudge}}))
        else:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": event, "additionalContext": nudge}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("context_watch: %s" % e, file=sys.stderr)
    sys.exit(0)
