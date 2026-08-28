#!/usr/bin/env bash
# Install the autoresearch skill + hooks into ~/.claude.
# Run it YOURSELF (agents can't write into ~/.claude):  bash install.sh
# Works the same on the Mac and on Linux GPU servers — copy this whole
# folder to the server (scp/rsync/git) and run it there too.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$HOME/.claude/skills/autoresearch" "$HOME/.config/autoresearch"

cp -R "$SRC/skill/autoresearch/." "$HOME/.claude/skills/autoresearch/"

if [ ! -f "$HOME/.config/autoresearch/telegram.env" ]; then
  cp "$SRC/telegram.env.template" "$HOME/.config/autoresearch/telegram.env"
  echo "created ~/.config/autoresearch/telegram.env — put TG_BOT_TOKEN and TG_CHAT_ID there"
fi

python3 "$SRC/merge_settings.py"

echo 'done. sanity check:  bash ~/.claude/skills/autoresearch/scripts/tg_notify.sh "autoresearch installed"'
