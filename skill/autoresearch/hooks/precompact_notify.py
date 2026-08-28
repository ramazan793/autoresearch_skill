#!/usr/bin/env python3
"""PreCompact(auto) hook: if the built-in auto-compact fires, the 250k watcher
was overrun — warn the user via Telegram. Inert outside research repos.
"""
import json
import os
import subprocess
import sys


def main():
    data = json.load(sys.stdin)
    cwd = data.get("cwd") or os.getcwd()
    if not os.path.isdir(os.path.join(cwd, "agent_notes")):
        return
    script = os.path.expanduser("~/.claude/skills/autoresearch/scripts/tg_notify.sh")
    if os.path.isfile(script):
        subprocess.run(
            ["bash", script,
             "WARNING: built-in auto-compact fired in %s (context watcher was "
             "overrun); check agent_notes/STATE.md freshness" % cwd],
            timeout=20)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("precompact_notify: %s" % e, file=sys.stderr)
    sys.exit(0)
