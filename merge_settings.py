#!/usr/bin/env python3
"""Merge autoresearch config into ~/.claude/settings.json (idempotent).

Adds the four hook entries and, when the Bash sandbox is enabled, allowlists
api.telegram.org in sandbox.network.allowedDomains so tg_notify.sh works from
inside sessions. Backs up the existing file to settings.json.bak.<timestamp>
first. Safe to re-run; skips entries that are already present.
"""
import json
import os
import shutil
import time

SETTINGS = os.path.expanduser("~/.claude/settings.json")
HOOK_DIR = "$HOME/.claude/skills/autoresearch/hooks"
SANDBOX_DOMAINS = ["api.telegram.org"]

ENTRIES = {
    "Stop": {"matcher": None, "command": "python3 %s/context_watch.py" % HOOK_DIR},
    "PostToolUse": {"matcher": None, "command": "python3 %s/context_watch.py" % HOOK_DIR},
    "SessionStart": {"matcher": "compact", "command": "python3 %s/post_compact_state.py" % HOOK_DIR},
    "PreCompact": {"matcher": "auto", "command": "python3 %s/precompact_notify.py" % HOOK_DIR},
    "Notification": {"matcher": None, "command": "python3 %s/notification_tg.py" % HOOK_DIR},
}


def main():
    settings = {}
    if os.path.isfile(SETTINGS):
        with open(SETTINGS) as f:
            settings = json.load(f)
        shutil.copy2(SETTINGS, SETTINGS + ".bak." + time.strftime("%Y%m%d_%H%M%S"))
    hooks = settings.setdefault("hooks", {})
    changed = False
    for event, spec in ENTRIES.items():
        groups = hooks.setdefault(event, [])
        if any(spec["command"] in json.dumps(g) for g in groups):
            continue
        group = {"hooks": [{"type": "command", "command": spec["command"], "timeout": 60}]}
        if spec["matcher"]:
            group["matcher"] = spec["matcher"]
        groups.append(group)
        changed = True

    sandbox = settings.get("sandbox")
    if isinstance(sandbox, dict) and sandbox.get("enabled"):
        domains = sandbox.setdefault("network", {}).setdefault("allowedDomains", [])
        for d in SANDBOX_DOMAINS:
            if d not in domains:
                domains.append(d)
                changed = True

    if changed:
        with open(SETTINGS, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        print("settings merged into %s (backup created)" % SETTINGS)
    else:
        print("settings already present, nothing to do")


if __name__ == "__main__":
    main()
