# Subagent & Codex Playbook

How deep tasks get run. The main agent is the **orchestrator and integrator**:
subagents produce raw material; only the main agent writes canonical artifacts.

## Model & effort tiers

- **haiku / sonnet** — no-brainer / mechanical: file digests, greps, summaries,
  boilerplate.
- **opus** — moderate reasoning: multi-file synthesis, straightforward code.
- **top tier (session model, currently fable)** — cornerstone work: real
  thinking, design, tricky code/math, final conclusions. Spawn with the default
  (inherited) model. **Default to the top tier when unsure** — most real
  subtasks deserve it.
- Reasoning effort is inherited from the session (xhigh); the tier choice is
  the model choice.

## Parallelism

- **Cap: 2 Claude agents at once** (excluding codex). Do NOT exceed 2 unless
  the user explicitly raises the cap for the task. Send concurrent agents in
  ONE message so they run together.
- Need more parallel hands than the cap allows → spin up codex (does not count
  against the Claude cap; run as many codex jobs as useful in the background).
- Independent work → parallelize. Dependent work → chain and pass results
  forward.

## Codex = full agent (discovery + offload + adversary), within its limits

- Codex is **not just for criticism** — use it like a Claude agent for general
  read-only work: code tracing, multi-file investigation, discovery, summaries,
  offload. It's the way to scale parallelism past the 2-Claude cap, and it's
  free.
- **Best uses:** (a) general read-only discovery/tracing (especially to scale
  past the cap), (b) offload, (c) **adversarial criticism / independent
  cross-check** of important code or conclusions (its real edge — an unbiased,
  different-model second opinion).
- **Limitation — read-only.** Codex cannot write files, edit code, render
  images, or iterate run→inspect. Tasks that must *execute and produce
  artifacts* → Claude agent. Pure reading/reasoning over the tree → codex.
- **Always** `gpt-5.6-sol`, `xhigh`, `service_tier=fast`, read-only; run in the
  background and read the output file when it finishes:
  ```bash
  codex exec -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -c 'service_tier="fast"' \
    --skip-git-repo-check -C <repo> -s read-only "$(cat /tmp/<name>.txt)" </dev/null
  ```
  **`</dev/null` is mandatory when running in the background**: with a non-TTY
  open stdin, codex sits in "Reading additional input from stdin..." forever
  and never starts (no rollout file appears in `~/.codex/sessions` — that's the
  tell).
- Write the prompt to a meaningful `/tmp/<name>.txt`, capture output to
  `/tmp/<name>.out`, then read it. (Run scripts live in `/tmp` as
  `run_codex_<name>.sh`.)
- Codex doesn't see the conversation — give it **full self-contained context**
  in the prompt, same as any subagent (reuse the handoff file below).

## Context handoff = "branch version of you"

- Give every subagent **all** context it needs in the first prompt — they don't
  see this conversation.
- For non-trivial spawns, first write a handoff file capturing what the main
  agent already knows, then hand the subagent that file path. Canonical home:
  `agent_notes/tasks/<task>/subagents/context_<topic>.md` (part of the task
  record, survives reboots). `/tmp/<topic>_context.md` is acceptable for
  throwaway spawns. Reuse/extend one file across related spawns — don't fork
  five diverging context files (entropy).

## Subagent artifact contract (entropy control)

- Every brief states: the goal, the context file, the **allowed write paths**,
  and the expected return format ("≤30-line summary + file paths").
- Subagents write ONLY inside their assigned scratch area
  (`agent_notes/tasks/<task>/subagents/` or `/tmp`) — never canonical docs,
  never code paths, unless the brief explicitly assigns ownership of specific
  files. Parallel agents get **disjoint** file sets.
- Subagents return raw material; the **main agent** integrates it into
  canonical artifacts (code, REPORT.md, docs) and trashes the scratch during
  task cleanup.

## Fresh-context hard rule

- One subagent = one task. When its task is done, it dies. Do not keep a
  long-lived subagent conversation going through rounds of drift — spawn a
  fresh one with an updated context file instead.
- If a subagent's job outgrows its context, it writes findings to its scratch
  file and reports; the main agent spawns a successor pointed at that file.
  The context-watch hook enforces this: above `AUTORESEARCH_SUB_CTX_LIMIT`
  (default 350k) the subagent gets a `[context-watch]` hand-off nudge after its
  next tool call. Every handoff file must therefore name the scratch/state
  path the subagent writes to.
- The main agent's own context is governed by the compact protocol
  (`compact_protocol.md`); subagents never compact.

## Verify important things adversarially

- For any important code written OR conclusion reached: spawn subagent(s) to
  **verify / criticize / hunt bugs & corner cases**. A few rounds of
  back-and-forth arguing is good, not wasteful.
- Use a **clean-context** agent (or codex) so it isn't biased toward defending
  the main agent's own work.

## Skepticism — nothing is ground truth

- Be critical of conclusions in `agent_notes/` — they are prior agents' output;
  they can be wrong or over-stated.
- Be critical of the user's own conclusions too — sanity-check the
  reasoning/numbers rather than treating them as GT.
- Prefer logging **raw metrics + trajectory**; the user owns the final verdict.

## House rules that interact with the above

- Never delete — use
  `python3 ~/.claude/skills/autoresearch/scripts/trash.py` for cleanup moves.
- Never `pip install`; ask before destructive/irreversible ops.
- Write multi-line scripts to a meaningful `/tmp/<name>.{py,sh}` and run them —
  no `python -c` one-liners, no heredocs.
- Verify runtime values from the execution path, not defaults/names, before
  relying on them.
