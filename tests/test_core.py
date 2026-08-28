#!/usr/bin/env python3
"""End-to-end checks for the autoresearch deliverables (design-mac side)."""
import json
import os
import subprocess
import sys
import tempfile

SRC = "/Users/ramazan/claude_sessions/autoresearch_design"
SK = os.path.join(SRC, "skill/autoresearch/scripts")
HK = os.path.join(SRC, "skill/autoresearch/hooks")
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print("%s: %s %s" % ("PASS" if cond else "FAIL", name, extra))


def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, **kw)


T = tempfile.mkdtemp(prefix="autoresearch_test.", dir=os.environ.get("TMPDIR", "/tmp"))

syntax_errs = []
for py in [os.path.join(SK, "gpu_free.py"), os.path.join(SK, "trash.py"),
           os.path.join(SK, "tmux_deliver.py"), os.path.join(SK, "request_compact.py"),
           os.path.join(HK, "context_watch.py"), os.path.join(HK, "post_compact_state.py"),
           os.path.join(HK, "precompact_notify.py"), os.path.join(HK, "notification_tg.py"),
           os.path.join(SRC, "merge_settings.py")]:
    try:
        compile(open(py).read(), py, "exec")
    except SyntaxError as e:
        syntax_errs.append("%s: %s" % (os.path.basename(py), e))
check("python syntax all", not syntax_errs, "; ".join(syntax_errs))
for sh in [os.path.join(SK, "tg_notify.sh"), os.path.join(SRC, "install.sh")]:
    r = run(["bash", "-n", sh])
    check("bash -n " + os.path.basename(sh), r.returncode == 0, r.stderr.strip())

r = run([sys.executable, os.path.join(SK, "gpu_free.py"), "--help"])
check("gpu_free --help", r.returncode == 0 and "PARKED" in r.stdout)

repo = os.path.join(T, "repo")
os.makedirs(os.path.join(repo, ".git"))
os.makedirs(os.path.join(repo, "sub"))
open(os.path.join(repo, "sub/junk.txt"), "w").write("x")
open(os.path.join(repo, "junk2.txt"), "w").write("y")
os.makedirs(os.path.join(repo, "dead_dir"))
open(os.path.join(repo, "dead_dir/f"), "w").write("z")
r = run([sys.executable, os.path.join(SK, "trash.py"), "junk.txt", "../junk2.txt", "../dead_dir"],
        cwd=os.path.join(repo, "sub"))
tr = os.path.join(repo, "trash")
check("trash moves into <git root>/trash", r.returncode == 0
      and os.path.isfile(os.path.join(tr, "junk.txt"))
      and os.path.isfile(os.path.join(tr, "junk2.txt"))
      and os.path.isfile(os.path.join(tr, "dead_dir/f"))
      and not os.path.exists(os.path.join(repo, "sub/junk.txt")), r.stderr.strip())
open(os.path.join(repo, "sub/junk.txt"), "w").write("x2")
r = run([sys.executable, os.path.join(SK, "trash.py"), "junk.txt"], cwd=os.path.join(repo, "sub"))
shelved = [n for n in os.listdir(tr) if n.startswith("junk.txt_")]
check("trash shelves occupant; newest keeps clean name",
      r.returncode == 0 and len(shelved) == 1
      and open(os.path.join(tr, "junk.txt")).read() == "x2"
      and open(os.path.join(tr, shelved[0])).read() == "x", str(shelved))
open(os.path.join(repo, "sub/junk.txt"), "w").write("x3")
r = run([sys.executable, os.path.join(SK, "trash.py"), "junk.txt"], cwd=os.path.join(repo, "sub"))
shelved2 = [n for n in os.listdir(tr) if n.startswith("junk.txt_")]
check("trash shelving survives repeat (same-second counter)",
      r.returncode == 0 and len(shelved2) == 2
      and open(os.path.join(tr, "junk.txt")).read() == "x3"
      and sorted(open(os.path.join(tr, n)).read() for n in shelved2) == ["x", "x2"],
      str(shelved2))
r = run([sys.executable, os.path.join(SK, "trash.py"), os.path.join(T, "missing")])
check("trash missing -> exit 1", r.returncode == 1)

research = os.path.join(T, "research")
os.makedirs(os.path.join(research, "agent_notes"))
transcript = os.path.join(T, "transcript.jsonl")


def write_transcript(ctx_tokens):
    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
        json.dumps({"type": "assistant",
                    "message": {"model": "claude-fable-5",
                                "usage": {"input_tokens": 1000,
                                          "cache_read_input_tokens": ctx_tokens - 2000,
                                          "cache_creation_input_tokens": 1000,
                                          "output_tokens": 5}}}),
        json.dumps({"type": "assistant", "isSidechain": True,
                    "message": {"model": "claude-x",
                                "usage": {"input_tokens": 999999,
                                          "cache_read_input_tokens": 0,
                                          "cache_creation_input_tokens": 0}}}),
    ]
    open(transcript, "w").write("\n".join(lines) + "\n")


def stop_hook(ctx, cwd, active=False, sid="s1"):
    write_transcript(ctx)
    payload = {"session_id": sid, "transcript_path": transcript, "cwd": cwd,
               "hook_event_name": "Stop", "stop_hook_active": active}
    return run([sys.executable, os.path.join(HK, "context_watch.py")],
               input=json.dumps(payload))


r = stop_hook(100000, research)
check("watch: under limit silent", r.returncode == 0 and r.stdout.strip() == "", r.stdout[:100])
r = stop_hook(260000, research)
try:
    out = json.loads(r.stdout)
except ValueError:
    out = {}
check("watch: over limit blocks (skips sidechain)",
      out.get("decision") == "block" and "260k" in out.get("reason", ""), r.stdout[:120])
r = stop_hook(265000, research)
check("watch: dampener suppresses re-nudge", r.stdout.strip() == "", r.stdout[:100])
r = stop_hook(305000, research)
try:
    out2 = json.loads(r.stdout)
except ValueError:
    out2 = {}
check("watch: re-nudges after +40k growth", out2.get("decision") == "block", r.stdout[:100])
r = stop_hook(320000, research, active=True)
check("watch: stop_hook_active loop guard", r.stdout.strip() == "")
r = stop_hook(60000, research)
check("watch: silent + reset after compact", r.stdout.strip() == "")
r = stop_hook(260000, research)
try:
    out3 = json.loads(r.stdout)
except ValueError:
    out3 = {}
check("watch: re-arms after reset", out3.get("decision") == "block", r.stdout[:100])
r = stop_hook(200000, research)
check("watch: context shrank below the last nudge (compact) -> silent + re-armed", r.stdout.strip() == "")
r = stop_hook(255000, research)
try:
    out3b = json.loads(r.stdout)
except ValueError:
    out3b = {}
check("watch: first crossing after a compact nudges again without waiting +STEP",
      out3b.get("decision") == "block", r.stdout[:100])
plain = os.path.join(T, "plain")
os.makedirs(plain)
r = stop_hook(400000, plain)
check("watch: non-research repo silent", r.stdout.strip() == "")

write_transcript(400000)
r = run([sys.executable, os.path.join(HK, "context_watch.py")],
        input=json.dumps({"session_id": "s1", "transcript_path": transcript, "cwd": research,
                          "hook_event_name": "PostToolUse", "tool_name": "Bash"}))
try:
    out4 = json.loads(r.stdout)
except ValueError:
    out4 = {}
hso = out4.get("hookSpecificOutput", {})
check("watch: PostToolUse nudges mid-turn via additionalContext",
      hso.get("hookEventName") == "PostToolUse" and "[context-watch]" in hso.get("additionalContext", "")
      and "decision" not in out4, r.stdout[:100])
r = stop_hook(405000, research)
check("watch: Stop after a PostToolUse nudge is dampened", r.stdout.strip() == "")
write_transcript(900000)
r = run([sys.executable, os.path.join(HK, "context_watch.py")],
        input=json.dumps({"session_id": "s1", "transcript_path": transcript, "cwd": research,
                          "hook_event_name": "PostToolUse", "tool_name": "Bash",
                          "agent_id": "a1", "agent_type": "general-purpose"}))
check("watch: subagent without own transcript -> silent (main ctx ignored)",
      r.stdout.strip() == "", r.stdout[:80])


def sub_hook(ctx_tokens, event="PostToolUse", aid="a1", env=None):
    sub_dir = os.path.join(T, "s1", "subagents")
    os.makedirs(sub_dir, exist_ok=True)
    sub = os.path.join(sub_dir, "agent-%s.jsonl" % aid)
    open(sub, "w").write(json.dumps({"type": "assistant", "isSidechain": True, "agentId": aid,
                                     "message": {"model": "claude-fable-5",
                                                 "usage": {"input_tokens": 500,
                                                           "cache_read_input_tokens": ctx_tokens - 1000,
                                                           "cache_creation_input_tokens": 500}}}) + "\n")
    payload = {"session_id": "s1", "transcript_path": transcript, "cwd": research,
               "hook_event_name": event, "tool_name": "Bash", "agent_id": aid,
               "agent_type": "general-purpose", "stop_hook_active": False}
    return run([sys.executable, os.path.join(HK, "context_watch.py")], input=json.dumps(payload), env=env)


r = sub_hook(300000)
check("subwatch: under 350k silent", r.stdout.strip() == "", r.stdout[:80])
r = sub_hook(360000)
try:
    out5 = json.loads(r.stdout)
except ValueError:
    out5 = {}
ac5 = out5.get("hookSpecificOutput", {}).get("additionalContext", "")
check("subwatch: over 350k -> hand-off nudge via additionalContext",
      "subagent" in ac5 and "360k" in ac5 and "return to the main agent" in ac5, r.stdout[:100])
r = sub_hook(370000)
check("subwatch: dampened", r.stdout.strip() == "", r.stdout[:80])
r = sub_hook(900000, event="Stop")
check("subwatch: Stop with agent_id never blocks/delivers", r.stdout.strip() == "", r.stdout[:80])
env_low = dict(os.environ)
env_low["AUTORESEARCH_SUB_CTX_LIMIT"] = "10000"
r = sub_hook(20000, aid="a2", env=env_low)
check("subwatch: limit below the subagent's start context -> first call silent (floor)",
      r.stdout.strip() == "", r.stdout[:80])
r = sub_hook(22000, aid="a2", env=env_low)
check("subwatch: +2k growth still under the 5k floor -> silent", r.stdout.strip() == "", r.stdout[:80])
r = sub_hook(40000, aid="a2", env=env_low)
check("subwatch: grown past the floor and over the limit -> hand-off nudge",
      "return to the main agent" in r.stdout and "40k" in r.stdout, r.stdout[:80])

req_dir = os.path.join(research, ".claude", "autoresearch")
os.makedirs(req_dir, exist_ok=True)
mine = os.path.join(req_dir, "compact_request_p5.json")
other = os.path.join(req_dir, "compact_request_p6.json")
json.dump({"command": "/compact keep X"}, open(mine, "w"))
json.dump({"command": "/compact other agent"}, open(other, "w"))
env_p5 = dict(os.environ)
env_p5["TMUX_PANE"] = "%5"
env_p5["TG_CONF"] = os.path.join(T, "none.env")
env_p5["PATH"] = os.path.join(SRC, "tests/helpers/faketmux") + os.pathsep + env_p5["PATH"]
env_p5["FT_LOG"] = os.path.join(T, "ft_core.log")
env_p5["FT_STATE"] = os.path.join(T, "ft_core.state")
env_p5["FT_BUSY_CALLS"] = "0"
env_p5["DELIVER_BUSY_WAIT"] = "0"
os.chmod(os.path.join(SRC, "tests/helpers/faketmux/tmux"), 0o755)
write_transcript(500000)
r = run([sys.executable, os.path.join(HK, "context_watch.py")], env=env_p5,
        input=json.dumps({"session_id": "s1", "transcript_path": transcript, "cwd": research,
                          "hook_event_name": "Stop", "stop_hook_active": False}))
check("stop hook: consumes only its own pane's request, other agent's stays, no nudge",
      r.returncode == 0 and r.stdout.strip() == "" and not os.path.exists(mine)
      and os.path.isfile(os.path.join(req_dir, "last_compact_request_p5.json"))
      and os.path.isfile(other), r.stdout[:80] + r.stderr[:80])
r = run([sys.executable, os.path.join(HK, "context_watch.py")], env=env_p5,
        input=json.dumps({"session_id": "s1", "transcript_path": transcript, "cwd": research,
                          "hook_event_name": "PostToolUse", "tool_name": "Bash"}))
check("PostToolUse never delivers (other agent's request untouched)",
      os.path.isfile(other) and "additionalContext" in r.stdout, r.stdout[:80])

state_md = os.path.join(research, "agent_notes", "STATE.md")
open(state_md, "w").write("# STATE\n## Compact message\nKeep X.\n")
payload = {"cwd": research, "hook_event_name": "SessionStart", "source": "compact"}
r = run([sys.executable, os.path.join(HK, "post_compact_state.py")], input=json.dumps(payload))
try:
    out = json.loads(r.stdout)
except ValueError:
    out = {}
ac = out.get("hookSpecificOutput", {}).get("additionalContext", "")
check("restore: returns STATE.md + recovery text",
      "Keep X." in ac and "autoresearch" in ac
      and out.get("hookSpecificOutput", {}).get("hookEventName") == "SessionStart", r.stdout[:80])
r = run([sys.executable, os.path.join(HK, "post_compact_state.py")],
        input=json.dumps({"cwd": plain}))
check("restore: silent without STATE.md", r.stdout.strip() == "")

fake_home_env = dict(os.environ)
fake_home_env["HOME"] = os.path.join(T, "nohome")
r = run([sys.executable, os.path.join(HK, "notification_tg.py")],
        input=json.dumps({"cwd": research, "message": "needs input"}), env=fake_home_env)
check("notify hook: clean no-op when uninstalled", r.returncode == 0, r.stderr.strip())
r = run([sys.executable, os.path.join(HK, "precompact_notify.py")],
        input=json.dumps({"cwd": research, "trigger": "auto"}), env=fake_home_env)
check("precompact hook: clean no-op when uninstalled", r.returncode == 0, r.stderr.strip())

env = dict(os.environ)
env["TG_CONF"] = os.path.join(T, "none.env")
env.pop("TG_BOT_TOKEN", None)
env.pop("TG_CHAT_ID", None)
r = run(["bash", os.path.join(SK, "tg_notify.sh"), "test"], env=env)
check("tg_notify unconfigured -> exit 1", r.returncode == 1 and "not set" in r.stderr, r.stderr.strip())

fake = os.path.join(T, "fakehome")
os.makedirs(os.path.join(fake, ".claude"))
json.dump({"model": "m", "sandbox": {"enabled": True, "filesystem": {"allowWrite": ["."]}}},
          open(os.path.join(fake, ".claude", "settings.json"), "w"))
env = dict(os.environ)
env["HOME"] = fake
r1 = run([sys.executable, os.path.join(SRC, "merge_settings.py")], env=env)
s = json.load(open(os.path.join(fake, ".claude", "settings.json")))
hooks = s.get("hooks", {})
check("merge: adds 5 hook events, keeps existing keys",
      all(k in hooks for k in ["Stop", "PostToolUse", "SessionStart", "PreCompact", "Notification"])
      and s.get("model") == "m", r1.stdout.strip())
check("merge: sandbox allowlists api.telegram.org, keeps allowWrite",
      "api.telegram.org" in s["sandbox"]["network"]["allowedDomains"]
      and s["sandbox"]["filesystem"]["allowWrite"] == ["."])
check("merge: SessionStart matcher=compact",
      hooks.get("SessionStart", [{}])[0].get("matcher") == "compact")
check("merge: PreCompact matcher=auto",
      hooks.get("PreCompact", [{}])[0].get("matcher") == "auto")
r2 = run([sys.executable, os.path.join(SRC, "merge_settings.py")], env=env)
s2 = json.load(open(os.path.join(fake, ".claude", "settings.json")))
check("merge: idempotent", "already present" in r2.stdout and s2 == s)
baks = [n for n in os.listdir(os.path.join(fake, ".claude")) if n.startswith("settings.json.bak")]
check("merge: backup created", len(baks) >= 1)

print()
fails = [n for n, okk in results if not okk]
print("%d/%d passed" % (len(results) - len(fails), len(results)))
if fails:
    print("failed: " + ", ".join(fails))
sys.exit(1 if fails else 0)
