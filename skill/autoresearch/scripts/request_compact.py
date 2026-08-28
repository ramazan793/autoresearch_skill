#!/usr/bin/env python3
"""Agent-side: queue a compact for the Stop hook to deliver.

    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <msg>"
    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py --then "<text>" "/compact <msg>"

Writes <cwd>/.claude/autoresearch/compact_request_<pane>.json, keyed by this
session's tmux pane ($TMUX_PANE, e.g. %3 -> p3) so several agents in the same
repo do not pick up each other's requests. When the agent's turn ends, the
Stop hook (hooks/context_watch.py) of the same pane reads the file and types
the command into that pane via tmux_deliver.py. Only /compact and /clear are
accepted. After the compaction finishes, the follow-up text given by --then
(default "continue") is typed so the session resumes on its own; --then ""
sends nothing. The follow-up is a plain message, it may not start with "/".
"""
import json
import os
import sys
import time

ALLOWED = ("/compact", "/clear")


def main():
    args = sys.argv[1:]
    then = "continue"
    if len(args) >= 2 and args[0] == "--then":
        then, args = args[1].strip(), args[2:]
    if not args or not " ".join(args).strip():
        sys.exit("request_compact: usage: request_compact.py [--then TEXT] \"/compact <msg>\"")
    command = " ".join(args).strip()
    if command.split()[0] not in ALLOWED:
        sys.exit("request_compact: refused, command must start with one of %s"
                 % ", ".join(ALLOWED))
    if then.startswith("/"):
        sys.exit("request_compact: refused, --then must be a plain message, not a slash command")
    cwd = os.getcwd()
    if not os.path.isdir(os.path.join(cwd, "agent_notes")):
        sys.exit("request_compact: no agent_notes/ in %s; the Stop hook is inactive "
                 "here, ask the user to run the compact" % cwd)
    pane = os.environ.get("TMUX_PANE", "").strip()
    if not pane:
        sys.exit("request_compact: $TMUX_PANE empty (Claude Code is not inside tmux); "
                 "ask the user to run the compact instead")
    key = "p" + "".join(c for c in pane if c.isalnum())

    d = os.path.join(cwd, ".claude", "autoresearch")
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, "compact_request_%s.json" % key)
    tmp = final + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"pane": pane, "command": command, "then": then, "created": time.time(),
                   "created_h": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    os.replace(tmp, final)
    print("compact request queued: %s" % final)
    print("End your reply now; the Stop hook delivers it into pane %s%s." % (
        pane, (", then types %r" % then) if then else ""))


if __name__ == "__main__":
    main()
