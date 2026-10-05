#!/usr/bin/env bash
# tg_notify.sh [--html] "message" — Telegram ping to the user.
# Config: ~/.config/autoresearch/telegram.env  (TG_BOT_TOKEN, TG_CHAT_ID)
# Outside working hours (10:00-22:00 Asia/Dubai) delivery is silent (no sound).
set -euo pipefail

CONF="${TG_CONF:-$HOME/.config/autoresearch/telegram.env}"
[ -f "$CONF" ] && . "$CONF"
if [ -z "${TG_BOT_TOKEN:-}" ] || [ -z "${TG_CHAT_ID:-}" ]; then
  echo "tg_notify: TG_BOT_TOKEN / TG_CHAT_ID not set (edit $CONF)" >&2
  exit 1
fi

# --html: the message is already Telegram HTML; otherwise it is escaped.
HTML=false
if [ "${1:-}" = "--html" ]; then HTML=true; shift; fi
BODY="${1:-ping}"
BODY="${BODY:0:3700}"
if ! $HTML; then
  BODY="${BODY//&/'&amp;'}"; BODY="${BODY//</'&lt;'}"; BODY="${BODY//>/'&gt;'}"
fi
HOST=$(hostname -s); HOST=${HOST%%-*}
MSG="🖥 <b>${HOST}</b>
${BODY}"

HOUR=$(TZ=Asia/Dubai date +%H); HOUR=${HOUR#0}
SILENT=true
if [ "${HOUR:-0}" -ge 10 ] && [ "${HOUR:-0}" -lt 22 ]; then SILENT=false; fi

send() {  # send TEXT [PARSE_MODE]
  curl -sS --max-time 10 -X POST \
    "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=$1" \
    ${2:+--data-urlencode "parse_mode=$2"} \
    --data-urlencode "disable_web_page_preview=true" \
    --data-urlencode "disable_notification=${SILENT}"
}
RESP=$(send "$MSG" HTML) || { echo "tg_notify: curl failed (network?)" >&2; exit 1; }
case "$RESP" in *'"ok":true'*) exit 0 ;; esac
# Telegram rejected the HTML (bad tag, cut mid-tag, ...): never lose the ping,
# resend it as plain text.
PLAIN=$(printf '%s' "$MSG" | sed -e 's/<[^>]*>//g' -e 's/&lt;/</g' -e 's/&gt;/>/g' -e 's/&amp;/\&/g')
RESP=$(send "$PLAIN") || { echo "tg_notify: curl failed (network?)" >&2; exit 1; }
case "$RESP" in
  *'"ok":true'*) echo "tg_notify: HTML rejected, sent as plain text" >&2; exit 0 ;;
  *) echo "tg_notify: Telegram rejected the message: ${RESP:0:300}" >&2; exit 1 ;;
esac
