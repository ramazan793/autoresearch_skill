#!/usr/bin/env bash
# Install the autoresearch skill + hooks + mars_* agents into ~/.claude.
# Usage: bash install.sh   (idempotent; fine from a shell or from an agent)
# Works the same on the Mac and on Linux GPU servers — copy this whole
# folder to the server (scp/rsync/git) and run it there too.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$HOME/.claude/skills/autoresearch" "$HOME/.config/autoresearch"

cp -R "$SRC/skill/autoresearch/." "$HOME/.claude/skills/autoresearch/"

# subagents with pinned model/effort/tools (see references/subagent_playbook.md)
mkdir -p "$HOME/.claude/agents"
cp "$SRC"/agents/mars_*.md "$HOME/.claude/agents/"

if [ -f "$HOME/.claude/skills/autoresearch/hooks/precompact_notify.py" ]; then
  echo "note: hooks/precompact_notify.py was retired (compacts are silent now); its hook"
  echo "      entry is dropped from settings.json, the file itself is inert — trash it when convenient"
fi

if [ ! -f "$HOME/.config/autoresearch/telegram.env" ]; then
  cp "$SRC/telegram.env.template" "$HOME/.config/autoresearch/telegram.env"
  echo "created ~/.config/autoresearch/telegram.env — put TG_BOT_TOKEN and TG_CHAT_ID there"
fi

python3 "$SRC/merge_settings.py"

echo 'done. sanity check:  bash ~/.claude/skills/autoresearch/scripts/tg_notify.sh "autoresearch installed"'
