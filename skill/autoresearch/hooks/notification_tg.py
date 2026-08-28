#!/usr/bin/env python3
"""Notification hook: forward Claude Code notifications (approval prompts,
idle waiting-for-input) to Telegram. Inert outside research repos.
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
    msg = data.get("message") or "Claude Code needs attention"
    script = os.path.expanduser("~/.claude/skills/autoresearch/scripts/tg_notify.sh")
    if os.path.isfile(script):
        subprocess.run(
            ["bash", script, "claude: %s (in %s)" % (msg, os.path.basename(cwd))],
            timeout=20)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("notification_tg: %s" % e, file=sys.stderr)
    sys.exit(0)
