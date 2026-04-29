#!/bin/bash
# Refresh Pi-hole SID in homepage services.yaml
# Run via cron every 25 min

set -e

PIHOLE_URL="http://192.168.68.200:8082"
PIHOLE_PASS="REDACTED"
SERVICES_YAML="/home/cristi/server/homepage/config/services.yaml"
LOG="/home/cristi/scripts/pihole-sid.log"

echo "=== $(date) ===" >> "$LOG"

# Login si extrage SID
RESPONSE=$(curl -s -X POST "$PIHOLE_URL/api/auth" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"$PIHOLE_PASS\"}")

SID=$(echo "$RESPONSE" | grep -oP '"sid":"[^"]+"' | cut -d'"' -f4)

if [ -z "$SID" ]; then
    echo "EROARE: nu s-a putut obtine SID. Response: $RESPONSE" >> "$LOG"
    exit 1
fi

echo "SID obtinut: $SID" >> "$LOG"

# Inlocuieste linia X-FTL-SID din services.yaml
# Folosim | ca separator pentru ca SID poate contine /
sed -i "s|X-FTL-SID: .*|X-FTL-SID: $SID|" "$SERVICES_YAML"

# Restart homepage sa preia SID nou
docker restart homepage > /dev/null 2>&1

echo "Homepage restarted, SID actualizat" >> "$LOG"
