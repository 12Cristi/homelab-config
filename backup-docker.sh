#!/bin/bash
# Backup config Docker - exclude media files
# Ruleaza saptamanal via cron

BACKUP_DIR="/home/cristi/backups"
DATE=$(date +%F_%H-%M)
LOG_FILE="$BACKUP_DIR/backup.log"
KEEP_BACKUPS=4

echo "=== Backup pornit la $(date) ===" >> "$LOG_FILE"

# Mergi in folderul parent
cd /home/cristi || exit 1

# Creeaza arhiva, exclude folderele mari/inutile
sudo tar czpf "$BACKUP_DIR/docker-config-$DATE.tar.gz" \
  --exclude='server/downloads' \
  --exclude='server/movies' \
  --exclude='server/series' \
  --exclude='server/books' \
  --exclude='server/Carti' \
  --exclude='server/jellyfin/cache' \
  --exclude='server/jellyfin/transcodes' \
  --exclude='server/jellyfin/log' \
  --exclude='server/jellyfin/data/transcodes' \
  --exclude='server/abs/metadata/cache' \
  --exclude='server/qb-config/qBittorrent/logs' \
  server/ 2>> "$LOG_FILE"
sudo chown cristi:cristi "$BACKUP_DIR/docker-config-$DATE.tar.gz"

if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_DIR/docker-config-$DATE.tar.gz" | cut -f1)
    echo "✓ Backup OK: docker-config-$DATE.tar.gz ($SIZE)" >> "$LOG_FILE"
else
    echo "✗ EROARE la backup!" >> "$LOG_FILE"
    exit 1
fi

# Sterge backup-urile mai vechi, pastreaza ultimele $KEEP_BACKUPS
cd "$BACKUP_DIR" || exit 1
ls -t docker-config-*.tar.gz 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | while read old; do
    rm "$old"
    echo "  Sters backup vechi: $old" >> "$LOG_FILE"
done

echo "=== Backup terminat la $(date) ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
