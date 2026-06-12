#!/bin/bash
# qBittorrent ClamAV watcher (v2 - foloseste clamd resident container)
WATCH_DIR="/home/cristi/server/downloads/complete"
QUARANTINE="/home/cristi/server/downloads/quarantine"
LOG="/home/cristi/qbit-scan.log"

mkdir -p "$WATCH_DIR" "$QUARANTINE"
echo "[$(date)] Watcher started on $WATCH_DIR (clamd mode)" >> "$LOG"

inotifywait -m -e moved_to,create --format '%f' "$WATCH_DIR" | \
while read NEW_ITEM; do
    [ -z "$NEW_ITEM" ] && continue
    ITEM_PATH="$WATCH_DIR/$NEW_ITEM"
    [ ! -e "$ITEM_PATH" ] && continue
    sleep 5

    echo "[$(date)] Scan: $NEW_ITEM" >> "$LOG"
    SCAN_PATH="/scan/complete/$NEW_ITEM"

    # clamdscan via container resident — instant, fara spawn
    RESULT=$(docker exec clamav clamdscan --no-summary --infected "$SCAN_PATH" 2>&1)
    EXIT=$?

    case $EXIT in
      0) echo "[$(date)] CLEAN: $NEW_ITEM" >> "$LOG" ;;
      1)
        echo "[$(date)] INFECTED: $NEW_ITEM" >> "$LOG"
        echo "$RESULT" >> "$LOG"
        [ -e "$ITEM_PATH" ] && mv "$ITEM_PATH" "$QUARANTINE/" 2>>"$LOG" \
          && echo "[$(date)] Quarantined -> $QUARANTINE/$NEW_ITEM" >> "$LOG"
        ;;
      *) echo "[$(date)] ERROR ($EXIT): $NEW_ITEM" >> "$LOG"; echo "$RESULT" >> "$LOG" ;;
    esac
done
