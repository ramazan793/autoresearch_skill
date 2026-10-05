#!/usr/bin/env python3
"""Agent-side: queue a compact for the Stop hook to deliver.

    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py --task <task_id> "/compact <msg>"
    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py --task <task_id> "/compact <msg>" --then "<text>"

Writes ~/.claude/autoresearch/compact_request_<pane>.json, keyed by this
session's tmux pane ($TMUX_PANE, e.g. %3 -> p3). When the agent's turn ends,
the Stop hook (hooks/context_watch.py) of the same pane reads the file and
types the command into that pane via tmux_deliver.py. The file is keyed by
pane and kept under $HOME, not in the repo, because the hook's cwd is Claude
Code's tracked shell cwd, which matches neither this script's cwd nor the
process cwd once the agent works in a worktree or subdirectory (see
references/self_compact.md). If $HOME is not writable (Bash sandbox), falls
back to <cwd>/.claude/autoresearch/ with a warning. Only /compact and /clear
are accepted, and the line is capped at MAX_CHARS: the compact message is
1-2 sentences, details belong in the task's STATE.md. --task names the task
for /compact: its folder name under agent_notes/tasks/ (YYYY-MM-DD_HH-MM_<name>),
a path ending in one, or a bare <name> matching exactly one task (old undated
tasks/<name>/ folders too); omitted, it defaults to the task folder this pane
last touched (task_<pane>.json, kept by hooks/context_watch.py). Its STATE.md
must exist and stay under AUTORESEARCH_STATE_MAX bytes (default 6000, it is a
pointer file), and the SessionStart(compact) hook restores it after the compaction
(hooks/post_compact_state.py). After the compaction finishes, the
follow-up text given by --then (default "continue task <task_id>") is typed so
the session resumes on its own; --then "" sends nothing. --then may appear before or
after the command. The follow-up is a plain message, it may not start with
"/". The hook discards requests older than AUTORESEARCH_REQUEST_TTL s
(default 600): end the reply right after queuing.
"""
import glob
import json
import os
import sys
import time

ALLOWED = ("/compact", "/clear")
MAX_CHARS = 800
STATE_MAX = int(os.environ.get("AUTORESEARCH_STATE_MAX", "6000"))
# Shared with hooks/context_watch.py: per-pane request files + deliver.log.
REQUEST_DIR = os.path.join(os.path.expanduser("~"), ".claude", "autoresearch")


def parse(argv):
    """Return (command, then, task). --then TEXT and --task SLUG are accepted
    anywhere; everything else is joined into the command."""
    opts, rest = {"--then": None, "--task": ""}, []
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            if i + 1 >= len(argv):
                sys.exit("request_compact: %s needs a value" % argv[i])
            opts[argv[i]] = argv[i + 1].strip()
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return " ".join(rest).strip(), opts["--then"], opts["--task"]


def research_repo(start):
    """First directory from `start` upwards that has agent_notes/, or None."""
    d = os.path.realpath(start)
    while True:
        if os.path.isdir(os.path.join(d, "agent_notes")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def resolve_task(repo, task):
    """The task's STATE.md path, or None if missing or ambiguous."""
    tasks = os.path.join(repo, "agent_notes", "tasks")
    tid = task.strip().rstrip("/").split("agent_notes/tasks/")[-1]
    if not tid or "/" in tid or tid in (".", ".."):
        return None
    hits = [os.path.join(tasks, tid, "STATE.md")]
    hits += glob.glob(os.path.join(tasks, "????-??-??_??-??_" + glob.escape(tid), "STATE.md"))
    hits = sorted({h for h in hits if os.path.isfile(h)})
    return hits[0] if len(hits) == 1 else None


def write_request(directory, key, payload):
    os.makedirs(directory, exist_ok=True)
    final = os.path.join(directory, "compact_request_%s.json" % key)
    tmp = final + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, final)
    return final


def last_task(key):
    """Task folder the main agent of this pane last touched (hooks/context_watch.py)."""
    try:
        with open(os.path.join(REQUEST_DIR, "task_%s.json" % key)) as f:
            return json.load(f).get("task") or ""
    except (OSError, ValueError):
        return ""


def main():
    command, then, task = parse(sys.argv[1:])
    if not command:
        sys.exit("request_compact: usage: request_compact.py [--task <task_id>] \"/compact <msg>\" "
                 "[--then TEXT]")
    if command.split()[0] not in ALLOWED:
        sys.exit("request_compact: refused, command must start with one of %s"
                 % ", ".join(ALLOWED))
    if then is not None and then.startswith("/"):
        sys.exit("request_compact: refused, --then must be a plain message, not a slash command")
    if len(command) > MAX_CHARS:
        sys.exit("request_compact: refused, the line is %d chars (max %d). The compact message is "
                 "1-2 sentences naming the project, the current task and where its state lives; "
                 "details belong in the task's STATE.md, not here." % (len(command), MAX_CHARS))
    cwd = os.getcwd()
    repo = research_repo(cwd)
    if repo is None:
        sys.exit("request_compact: no agent_notes/ in %s or any parent; this is not a research "
                 "repo, ask the user to run the compact" % cwd)
    pane = os.environ.get("TMUX_PANE", "").strip()
    if not pane:
        sys.exit("request_compact: $TMUX_PANE empty (Claude Code is not inside tmux); "
                 "ask the user to run the compact instead")
    key = "p" + "".join(c for c in pane if c.isalnum())

    task_state = None
    if command.split()[0] == "/compact":
        if not task:
            task = last_task(key)
            if task:
                print("request_compact: --task omitted, using the task you last touched: %s" % task)
        if not task:
            sys.exit("request_compact: refused, --task <task_id> is required (the folder under "
                     "agent_notes/tasks/ whose STATE.md the post-compact hook restores) and no "
                     "task folder has been touched in this pane yet")
        task_state = resolve_task(repo, task)
        if task_state is None:
            sys.exit("request_compact: refused, --task %r matches no single "
                     "%s/agent_notes/tasks/<task_id>/STATE.md; pass the full task id and "
                     "write the task's STATE.md first (references/compact_protocol.md)"
                     % (task, repo))
        size = os.path.getsize(task_state)
        if size > STATE_MAX:
            sys.exit("request_compact: refused, %s is %d bytes (max %d, AUTORESEARCH_STATE_MAX). "
                     "STATE.md is a pointer file: move details into PLAN.md/notes, keep Task "
                     "status / Pointers / Running jobs / Next steps / Assumptions, then re-queue."
                     % (task_state, size, STATE_MAX))
    task_id = os.path.basename(os.path.dirname(task_state)) if task_state else ""
    if then is None:
        then = ("continue task %s" % task_id) if task_id else "continue"

    payload = {"pane": pane, "command": command, "then": then, "shell_cwd": cwd,
               "repo": repo, "task": task_id, "task_state": task_state,
               "created": time.time(), "created_h": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        final = write_request(REQUEST_DIR, key, payload)
    except OSError as e:
        print("request_compact: warning: cannot write %s (%s; Bash sandbox?). Falling back to "
              "the shell cwd; this only works if this shell did not cd within the current "
              "command." % (REQUEST_DIR, e), file=sys.stderr)
        final = write_request(os.path.join(cwd, ".claude", "autoresearch"), key, payload)
    print("compact request queued: %s" % final)
    print("End your reply now; the Stop hook delivers it into pane %s%s." % (
        pane, (", then types %r" % then) if then else ", no follow-up"))


if __name__ == "__main__":
    main()
