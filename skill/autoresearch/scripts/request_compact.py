#!/usr/bin/env python3
"""Agent-side: queue a compact for the Stop hook to deliver.

    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <msg>"
    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <msg>" --then "<text>"

Writes <cwd>/.claude/autoresearch/compact_request_<pane>.json, keyed by this
session's tmux pane ($TMUX_PANE, e.g. %3 -> p3) so several agents in the same
repo do not pick up each other's requests. When the agent's turn ends, the
Stop hook (hooks/context_watch.py) of the same pane reads the file and types
the command into that pane via tmux_deliver.py. Only /compact and /clear are
accepted. After the compaction finishes, the follow-up text given by --then
(default "continue") is typed so the session resumes on its own; --then ""
sends nothing. --then may appear before or after the command. The follow-up
is a plain message, it may not start with "/".
"""
import json
import os
import sys
import time

ALLOWED = ("/compact", "/clear")


def parse(argv):
    """Return (command, then). --then TEXT is accepted anywhere; everything
    else is joined into the command."""
    then, rest = "continue", []
    i = 0
    while i < len(argv):
        if argv[i] == "--then":
            if i + 1 >= len(argv):
                sys.exit("request_compact: --then needs a value (use --then \"\" for none)")
            then = argv[i + 1].strip()
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return " ".join(rest).strip(), then


def main():
    command, then = parse(sys.argv[1:])
    if not command:
        sys.exit("request_compact: usage: request_compact.py \"/compact <msg>\" [--then TEXT]")
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
        pane, (", then types %r" % then) if then else ", no follow-up"))


if __name__ == "__main__":
    main()
