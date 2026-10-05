<!-- Paste this into each research repo's CLAUDE.md to make skill invocation
     deterministic there (description-matching alone is good but not 100%). -->

## Research workflow

Any research task in this repo — experiments, training runs, ablations, method
work, analysis, reports — MUST follow the `autoresearch` skill: invoke it
before starting work. Artifacts follow the `agent_notes/` discipline from that
skill. After any compact, re-read your task's
`agent_notes/tasks/<task_id>/STATE.md` first; the task index is
`$(git rev-parse --git-common-dir)/autoresearch/STATE.md`.
