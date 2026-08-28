#!/usr/bin/env python3
"""SessionStart(compact) hook: after a compact, restore agent_notes/STATE.md
plus recovery instructions into context. Inert if the cwd has no
agent_notes/STATE.md.
"""
import json
import os
import sys


def main():
    data = json.load(sys.stdin)
    cwd = data.get("cwd") or os.getcwd()
    path = os.path.join(cwd, "agent_notes", "STATE.md")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        state = f.read()[:20000]
    ctx = (
        "A compact just happened. Recovery protocol: re-invoke the `autoresearch` "
        "skill, re-read the files referenced in STATE.md below (current task "
        "folder PLAN.md/notes, key docs) before continuing, then resume from "
        "'Next steps'. Do not trust vague memories of pre-compact details — "
        "the files are the source of truth.\n\n"
        "--- agent_notes/STATE.md ---\n" + state
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": ctx}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("post_compact_state: %s" % e, file=sys.stderr)
    sys.exit(0)
