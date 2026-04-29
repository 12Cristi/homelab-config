#!/bin/bash
# Reusable system cleanup
# Run periodically (monthly recommended via cron, or manually)
# Auto-detects interactive vs cron mode

LOG_PREFIX="==>"
echo "$LOG_PREFIX System cleanup - $(date '+%Y-%m-%d %H:%M')"
echo "$LOG_PREFIX BEFORE"
echo "Disk: $(df -h / | tail -1 | awk '{print $3 " used, " $4 " free (" $5 " used)"}')"
echo "APT cache: $(sudo du -sh /var/cache/apt/archives/ 2>/dev/null | cut -f1)"
echo "Journal:   $(sudo journalctl --disk-usage 2>&1 | grep -oE '[0-9.]+[KMG]')"
echo ""

# Doar in mod interactiv cere confirmare; in cron, ruleaza direct
if [ -t 0 ]; then
  read -rp "Continue? [y/N]: " CONFIRM
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi
fi

echo ""
echo "$LOG_PREFIX Step 1/5: APT autoremove"
sudo apt-get autoremove --purge -y || echo "  (autoremove had errors, continuing)"

echo ""
echo "$LOG_PREFIX Step 2/5: APT clean"
sudo apt-get clean || true

echo ""
echo "$LOG_PREFIX Step 3/5: Old kernels (keeping current + 1 backup)"
CURRENT_KERNEL=$(uname -r)
echo "    Current: $CURRENT_KERNEL"

OLD_KERNELS=$(dpkg --list | grep -E '^ii\s+linux-image-[0-9]' | awk '{print $2}' | grep -v "$CURRENT_KERNEL" | head -n -1)

if [ -z "$OLD_KERNELS" ]; then
  echo "    No old kernels to remove."
else
  echo "    Removing:"
  echo "$OLD_KERNELS" | sed 's/^/      /'
  for KERNEL in $OLD_KERNELS; do
    VERSION=$(echo "$KERNEL" | sed 's/linux-image-//')
    sudo apt-get purge -y \
      "linux-image-$VERSION" \
      "linux-headers-$VERSION" \
      "linux-modules-$VERSION" \
      "linux-modules-extra-$VERSION" 2>/dev/null || true
  done
fi

echo ""
echo "$LOG_PREFIX Step 4/5: Journal logs (keeping last 7 days)"
sudo journalctl --vacuum-time=7d || true

echo ""
echo "$LOG_PREFIX Step 5/5: Docker cleanup (DANGLING images only - safe)"
# Doar imagini DANGLING (fara tag, ramase din rebuild-uri) - SAFE
docker image prune -f || true
# Volume orfane (NU sterge volumele containerelor active)
docker volume prune -f || true
# Network-uri neutilizate
docker network prune -f || true

echo ""
echo "$LOG_PREFIX AFTER"
echo "Disk: $(df -h / | tail -1 | awk '{print $3 " used, " $4 " free (" $5 " used)"}')"
echo "APT cache: $(sudo du -sh /var/cache/apt/archives/ 2>/dev/null | cut -f1)"
echo "Journal:   $(sudo journalctl --disk-usage 2>&1 | grep -oE '[0-9.]+[KMG]')"
echo ""
echo "Done."
