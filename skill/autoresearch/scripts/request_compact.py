#!/usr/bin/env python3
"""Agent-side: queue a compact for the Stop hook to deliver.

    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <msg>"
    python3 ~/.claude/skills/autoresearch/scripts/request_compact.py "/compact <msg>" --then "<text>"

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
1-2 sentences, details belong in STATE.md. After the compaction finishes, the
follow-up text given by --then (default "continue") is typed so the session
resumes on its own; --then "" sends nothing. --then may appear before or
after the command. The follow-up is a plain message, it may not start with
"/". The hook discards requests older than AUTORESEARCH_REQUEST_TTL s
(default 600): end the reply right after queuing.
"""
import json
import os
import sys
import time

ALLOWED = ("/compact", "/clear")
MAX_CHARS = 800
# Shared with hooks/context_watch.py: per-pane request files + deliver.log.
REQUEST_DIR = os.path.join(os.path.expanduser("~"), ".claude", "autoresearch")


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


def write_request(directory, key, payload):
    os.makedirs(directory, exist_ok=True)
    final = os.path.join(directory, "compact_request_%s.json" % key)
    tmp = final + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, final)
    return final


def main():
    command, then = parse(sys.argv[1:])
    if not command:
        sys.exit("request_compact: usage: request_compact.py \"/compact <msg>\" [--then TEXT]")
    if command.split()[0] not in ALLOWED:
        sys.exit("request_compact: refused, command must start with one of %s"
                 % ", ".join(ALLOWED))
    if then.startswith("/"):
        sys.exit("request_compact: refused, --then must be a plain message, not a slash command")
    if len(command) > MAX_CHARS:
        sys.exit("request_compact: refused, the line is %d chars (max %d). The compact message is "
                 "1-2 sentences naming the project, the current task and where its state lives; "
                 "details belong in agent_notes/STATE.md, not here." % (len(command), MAX_CHARS))
    cwd = os.getcwd()
    if research_repo(cwd) is None:
        sys.exit("request_compact: no agent_notes/ in %s or any parent; this is not a research "
                 "repo, ask the user to run the compact" % cwd)
    pane = os.environ.get("TMUX_PANE", "").strip()
    if not pane:
        sys.exit("request_compact: $TMUX_PANE empty (Claude Code is not inside tmux); "
                 "ask the user to run the compact instead")
    key = "p" + "".join(c for c in pane if c.isalnum())

    payload = {"pane": pane, "command": command, "then": then, "shell_cwd": cwd,
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
