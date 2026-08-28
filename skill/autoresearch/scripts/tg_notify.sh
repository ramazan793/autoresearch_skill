#!/usr/bin/env bash
# tg_notify.sh "message" — Telegram ping to the user.
# Config: ~/.config/autoresearch/telegram.env  (TG_BOT_TOKEN, TG_CHAT_ID)
# Outside working hours (10:00-22:00 Asia/Dubai) delivery is silent (no sound).
set -euo pipefail

CONF="${TG_CONF:-$HOME/.config/autoresearch/telegram.env}"
[ -f "$CONF" ] && . "$CONF"
if [ -z "${TG_BOT_TOKEN:-}" ] || [ -z "${TG_CHAT_ID:-}" ]; then
  echo "tg_notify: TG_BOT_TOKEN / TG_CHAT_ID not set (edit $CONF)" >&2
  exit 1
fi

MSG="[$(hostname -s)] ${1:-ping}"
MSG="${MSG:0:3800}"

HOUR=$(TZ=Asia/Dubai date +%H); HOUR=${HOUR#0}
SILENT=true
if [ "${HOUR:-0}" -ge 10 ] && [ "${HOUR:-0}" -lt 22 ]; then SILENT=false; fi

RESP=$(curl -sS --max-time 10 -X POST \
  "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TG_CHAT_ID}" \
  --data-urlencode "text=${MSG}" \
  --data-urlencode "disable_notification=${SILENT}") || {
  echo "tg_notify: curl failed (network?)" >&2; exit 1; }
case "$RESP" in
  *'"ok":true'*) exit 0 ;;
  *) echo "tg_notify: Telegram rejected the message: ${RESP:0:300}" >&2; exit 1 ;;
esac
