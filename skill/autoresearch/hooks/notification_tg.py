#!/usr/bin/env python3
"""Notification hook: forward Claude Code notifications (approval prompts,
idle waiting-for-input) to Telegram. Inert outside research repos (no
agent_notes/ in the cwd or any parent).

An idle notification is dropped while the session still has background work
in flight (background shells, monitors, async agents): Claude is waiting on
its own tasks, not on the user. A task counts as in flight when its
tasks/<id>.output path appears in the transcript, no <task-notification> with
a terminal status has arrived for it, and the file is alive: held open by
some process, or written in the last LIVE_S seconds. A task left over from an
earlier run of a resumed session is neither, so it cannot mute the hook.
"""
import html
import json
import os
import re
import subprocess
import sys
import time

TASK_OUT = re.compile(r"(/[^\s\"'\\<>]*/tasks/([A-Za-z0-9_-]+)\.output)")
TASK_DONE = re.compile(r"<task-id>([A-Za-z0-9_-]+)</task-id>.*?<status>(\w+)</status>", re.S)
TERMINAL = {"completed", "failed", "killed", "stopped", "cancelled", "error", "timeout"}
LIVE_S = 120


def research_repo(start):
    d = os.path.realpath(start)
    while True:
        if os.path.isdir(os.path.join(d, "agent_notes")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def read_transcript(path):
    try:
        with open(path) as f:
            return f.read()
    except (OSError, TypeError):
        return ""


def open_files():
    """Targets of every fd of every process we may inspect (our own)."""
    out = set()
    for pid in os.listdir("/proc"):
        fd_dir = "/proc/%s/fd" % pid
        if not pid.isdigit():
            continue
        try:
            names = os.listdir(fd_dir)
        except OSError:
            continue
        for n in names:
            try:
                out.add(os.readlink(os.path.join(fd_dir, n)))
            except OSError:
                pass
    return out


def alive(path, opened):
    try:
        return path in opened or time.time() - os.path.getmtime(path) < LIVE_S
    except OSError:
        return False


def pending_tasks(raw):
    done = {tid for tid, st in TASK_DONE.findall(raw.replace("\\n", "\n"))
            if st.lower() in TERMINAL}
    cands = {path: tid for path, tid in TASK_OUT.findall(raw)
             if tid not in done and os.path.exists(path)}
    if not cands:
        return set()
    opened = open_files()
    return {tid for path, tid in cands.items() if alive(path, opened)}


def last_assistant_text(raw):
    for line in reversed(raw.splitlines()):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") != "assistant":
            continue
        content = rec.get("message", {}).get("content") or []
        text = " ".join(c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text").strip()
        if text:
            return text
    return ""


def main():
    data = json.load(sys.stdin)
    repo = research_repo(data.get("cwd") or os.getcwd())
    if not repo:
        return
    msg = data.get("message") or "Claude Code needs attention"
    kind = data.get("notification_type") or ""
    idle = kind == "idle_prompt" or "waiting for your input" in msg.lower()
    raw = read_transcript(data.get("transcript_path"))

    if idle:
        if pending_tasks(raw):
            return
        head = "⏳ <b>Claude is waiting for you</b>"
    elif kind == "permission_prompt" or "permission" in msg.lower():
        head = "🔐 <b>Needs your approval</b>"
    else:
        head = "🔔 <b>Claude</b>"

    parts = [head, "📁 <code>%s</code>" % html.escape(os.path.basename(repo))]
    if not idle:
        parts.append(html.escape(msg))
    last = last_assistant_text(raw)
    if last:
        if len(last) > 600:
            last = "…" + last[-600:]
        parts.append("<blockquote>%s</blockquote>" % html.escape(last))

    script = os.path.expanduser("~/.claude/skills/autoresearch/scripts/tg_notify.sh")
    if os.path.isfile(script):
        subprocess.run(["bash", script, "--html", "\n".join(parts)], timeout=20)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("notification_tg: %s" % e, file=sys.stderr)
    sys.exit(0)
