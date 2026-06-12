# Homelab Setup — homepc (v6)

**Owner:** cristi
**Last updated:** 2026-06-12
**Host:** Ubuntu 24.04 LTS, kernel 6.8.0-124-generic
**Hardware:** HP EliteDesk 600 G2 Tiny — Intel i5-6500T (4C/4T, 2.5GHz, QuickSync HD 530), **16 GB RAM**, 457GB SSD migrat din homepc vechi
**Hostname:** homepc
**LAN IP:** 192.168.68.200 (static via netplan pe `eno1`)
**Tailscale IP:** 100.113.68.25
**Tailnet:** tail1b235c.ts.net
**Tailscale FQDN:** homepc.tail1b235c.ts.net

> **Schimbare majoră 12 iunie 2026:** Migrare hardware completă de pe homepc vechi (4GB RAM, USB defect) pe HP EliteDesk 600 G2 Tiny (16GB RAM, hardware sănătos). SSD-ul existent mutat fizic, fără reinstalare OS. Toate workaround-urile USB / reboot zilnic eliminate. Vezi secțiunea **Migrare** și lecțiile #44-50.

---

## Arhitectură rețea

```
ISP NextPower (1024 Mbps)
        │
        ↓
      ONT
        │
        ↓
    M4R principal (NAT + WiFi + DHCP)  ← bottleneck ~360 Mbps NAT
        │
        ├── switch ──→ server (homepc HP 600 G2, cablu Cat6)
        │         ──→ M4R satelit interior (backhaul cablu — scos din switch!)
        │         ──→ M4R satelit exterior (cablu direct, 920 Mbps)
        │
        └── M4R satelit interior (wireless backhaul după modificare)

LAN: 192.168.68.0/24
Gateway: 192.168.68.1 (M4R principal)
DHCP: M4R principal (rezervare scoasă pentru homepc — IP fix prin netplan)
DNS: Pi-hole (192.168.68.200) cu fallback 1.1.1.1
```

### Notă importantă M4R

M4R din 2018 limitează NAT throughput la **~360 Mbps sustained** (~650 burst). Planul de viitor: Opțiunea 2 ISP — ONT nou cu Wi-Fi 6 integrat + M4R în Access Point mode.

---

## Servicii Docker (19 containere active)

Toate în `/home/cristi/server/docker-compose.yml`. Toate cu `restart: always`.

| Container | Port | Funcție |
|-----------|------|---------|
| pihole | 8082 (UI), 53 (DNS) | DNS filtering ad-blocking |
| jellyfin | host network | Media streaming (filme, seriale, audiobooks) |
| **jellyseerr** | **5055** | **Request UI pentru Sonarr+Radarr (adăugat 12 iun)** |
| sonarr | 8989 | Tracking seriale (auth: Forms, Disabled for Local) |
| radarr | 7878 | Tracking filme (auth: Forms, Disabled for Local) |
| bazarr | 6767 | Subtitrări automat |
| prowlarr | 9696 | Indexer aggregator |
| qbittorrent | 8080, 6881 | Torrent client |
| audiobookshelf | 13378 | Server audiobooks |
| filebrowser | **8091** | Web file manager (auth: noauth) — mutat de pe 8090 (conflict airsaned) |
| changedetection | 5000 | Monitor schimbări website-uri |
| cups-airprint | host network (631) | Print + AirScan iPhone via airsaned:8090 |
| homepage | 3000 | Dashboard centralizat |
| dockerproxy | 127.0.0.1:2375 | Docker API read-only proxy pentru homepage |
| mosquitto | 1883 (MQTT) | MQTT broker pentru stack solar + Zigbee2MQTT |
| homeassistant | host network (8123) | Home Assistant Core — monitoring solar |
| portainer | 9000 | Docker management UI |
| zigbee2mqtt | 8099 (UI) | Zigbee coordinator (Sonoff MG24) — **REACTIVAT 12 iun** |
| **clamav** | **socket clamd** | **Antivirus resident (înlocuiește on-demand) — adăugat 12 iun** |

---

## Migrare HP 600 G2 Tiny (12 iunie 2026)

### De ce migrare

Hardware-ul vechi homepc avea:
- Doar 4GB RAM (bottleneck pentru ClamAV, HA recorder, Jellyfin transcoding)
- USB porturi spate defecte permanent (over-current events)
- Workaround-uri necesare: `pci=noaer usbcore.autosuspend=-1` în GRUB + reboot zilnic 04:30

HP 600 G2 Tiny (~300 RON second-hand) aduce: 16GB RAM, USB toate funcționale, i5-6500T 35W TDP cu QuickSync HD 530 pentru transcoding hardware.

### Pași migrare (rezumat)

1. **Pe homepc vechi:** backup safety + git push + `docker compose down` + shutdown
2. **Mutare SSD fizic** în HP 600 G2 (slot SATA 2.5" intern)
3. **BIOS HP 600 G2 (F10 la boot):**
   - Secure Boot: **Disable** (cu confirmare cod 4 cifre la next boot — vezi lecția #48)
   - Legacy Support: Disable (SSD UEFI valid)
   - Boot order: SSD primul
   - After Power Loss: Power On
   - Wake On LAN: Enabled
   - VT-x + VT-d: Enabled
4. **Primul boot Ubuntu:** funcționează direct, dar:
   - Interfața de rețea schimbată: `enp2s0` → `eno1` (vezi lecția #47)
   - Tailscale `tailscale-tune.service` failed (referă vechiul nume — vezi lecția #49)
5. **Fix netplan static:**
   ```yaml
   network:
     version: 2
     ethernets:
       eno1:
         dhcp4: no
         addresses:
           - 192.168.68.200/24
         routes:
           - to: default
             via: 192.168.68.1
         nameservers:
           addresses:
             - 127.0.0.1
             - 1.1.1.1
   ```
6. **Fix tailscale-tune:** `sudo sed -i 's/enp2s0/eno1/g' /etc/systemd/system/tailscale-tune.service`
7. **Docker stack:** `docker compose up -d` → toate 18 containere up imediat
8. **Cleanup workaround-uri:**
   - GRUB: `GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"` (scos `pci=noaer usbcore.autosuspend=-1`)
   - Cron: scos linia `30 4 * * * /sbin/shutdown -r now`

### Probleme întâmpinate

- **Filebrowser conflict cu airsaned pe port 8090** (airsaned rulează în containerul cups-airprint cu `network_mode: host`, port hardcoded). Fix: mutat filebrowser pe 8091.
- **Filebrowser `database.db` mount stricat** — bind mount către fișier inexistent → Docker creează director gol. Fix: `touch` fișierul gol + `chown 1000:1000` ÎNAINTE de prima pornire.
- **Zigbee2MQTT lipsea `devices:` în docker-compose** — pe vechiul setup mergea probabil prin alt config. Adăugat mapping explicit: `/dev/serial/by-id/usb-SONOFF_...-port0:/dev/ttyUSB0`. Zigbee network restaurat fără re-pairing (mesaj `[INIT TC] Adapter network matches config`).

### Status post-migrare

```
✓ 19/19 containere UP
✓ IP static 192.168.68.200 via netplan eno1
✓ 0 over-current USB events
✓ 15Gi RAM available (vs 4 anterior)
✓ Disk 93% (problemă veche, nu cauzată de migrare)
✓ systemd: running
✓ ClamAV resident: 9ms scan time (vs 28-90s on-demand)
✓ Jellyseerr operațional, integrare Sonarr/Radarr OK
```

---

## ClamAV — antivirus RESIDENT (refactor 12 iunie)

**Schimbare majoră vs v5:** ClamAV nu mai e on-demand cu `docker run --rm`. Acum e container persistent cu clamd socket — scan instant prin `docker exec`.

### Arhitectură nouă

```
qBittorrent termină download
        ↓ move din incomplete/ în complete/
   /home/cristi/server/downloads/complete/
        ↓ inotifywait moved_to,create
   systemd unit qbit-watch.service (runs as cristi)
        ↓ docker exec clamav clamdscan --no-summary --infected
   clamav container (resident, DB in RAM)
        ↓ exit code
   ┌─────────────┴─────────────┐
   CLEAN (exit 0)        INFECTED (exit 1)
        │                       │
   log doar              mv în quarantine/
                         /home/cristi/server/downloads/quarantine/
```

### docker-compose entry

```yaml
  clamav:
    image: clamav/clamav:stable
    container_name: clamav
    restart: always
    volumes:
      - /home/cristi/server/clamav/db:/var/lib/clamav
      - /home/cristi/server/downloads:/scan:ro
    environment:
      - TZ=Europe/Bucharest
      - CLAMAV_NO_MILTERD=true
      - CLAMAV_NO_FRESHCLAMD=false
      - FRESHCLAM_CHECKS=2
    healthcheck:
      test: ["CMD", "/usr/local/bin/clamdcheck.sh"]
      interval: 60s
      retries: 3
      start_period: 5m
```

**Notă:** `CLAMAV_NO_FRESHCLAMD=false` + `FRESHCLAM_CHECKS=2` = container update DB de 2× pe zi. **Cron-ul vechi `freshclam` ZILNIC ELIMINAT.**

### Resurse consumate

- **Resident:** ~970 MB RAM constant (DB în memorie)
- **Scan:** instant, <300ms pentru fișiere mici, <1s pentru arhive medii
- **Disk DB:** ~108 MB în `/home/cristi/server/clamav/db/`
- **DB version:** auto-update, fresh în <12h

### qbit-watch.sh (v2 — clamdscan mode)

```bash
#!/bin/bash
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
```

### Test EICAR validation

Test rulat 12 iun 16:14:27 — detecție + carantină în **<1 secundă** (5s sleep + 9ms scan + mv).

---

## Jellyseerr (adăugat 12 iunie)

Request UI pentru familia care folosește Jellyfin. Înlocuiește interfața Sonarr/Radarr directă pentru utilizatori non-tech.

### docker-compose entry

```yaml
  jellyseerr:
    image: fallenbagel/jellyseerr:latest
    container_name: jellyseerr
    restart: always
    ports:
      - "5055:5055"
    environment:
      - TZ=Europe/Bucharest
      - LOG_LEVEL=info
    volumes:
      - /home/cristi/server/jellyseerr/config:/app/config
```

### Setup wizard (cca 15 min)

1. **Sign in cu Jellyfin:** URL `http://192.168.68.200:8096` + admin credentials
2. **Libraries:** bifează Movies + Series (Jellyseerr scan în background)
3. **Radarr:**
   - Hostname `192.168.68.200`, port `7878`
   - API key din `docker exec radarr cat /config/config.xml | grep ApiKey`
   - Quality Profile + Root Folder `/movies`
4. **Sonarr:**
   - Hostname `192.168.68.200`, port `8989`
   - API key din `docker exec sonarr cat /config/config.xml | grep ApiKey`
   - Quality Profile + Root Folder `/series`

### Flow utilizator

Familia → http://192.168.68.200:5055 → caută film/serial → "Request" → Jellyseerr trimite la Radarr/Sonarr → Prowlarr search → qBittorrent download → Jellyfin scan automat. End-to-end 0 intervenție manuală.

---

## Pi-hole — blocklists finale (Tier 1+2+3)

Block rate stabilizat ~15-20%. Vezi v5 pentru lista completă blocklists (neschimbat).

---

## Stack solar (funcțional din 19 mai 2026)

**Status:** Stack neschimbat de la v5. Vezi v5 docs pentru:
- Configurație Deye 12kW + LSW-5 logger
- Solarman HACS integration
- Template sensors + utility meters
- Dashboard 3 coloane Sections view
- Forecast.Solar calibrare 11500W (în monitoring)
- Lecții solar #29-39 (templates, recorder, apex charts, etc.)

### Acțiuni rămase legate solar

- [ ] Recalibrare Forecast.Solar (10 iunie zi senină: estimat 60.5 vs real 50.2 = -17% supraestimare). Plan: monitorizare 7+ zile cu meteo variabil, posibil ajustare la ~10500W.
- [ ] Tarife în Energy Dashboard (1.10 RON import / 0.40 RON export)

---

## Configurare critică

### netplan `/etc/netplan/50-cloud-init.yaml`

```yaml
network:
  version: 2
  ethernets:
    eno1:
      dhcp4: no
      addresses:
        - 192.168.68.200/24
      routes:
        - to: default
          via: 192.168.68.1
      nameservers:
        addresses:
          - 127.0.0.1
          - 1.1.1.1
```

Permisiuni: `chmod 600`.

### Docker daemon (`/etc/docker/daemon.json`)

```json
{
  "exec-opts": ["native.cgroupdriver=cgroupfs"],
  "dns": ["192.168.68.200", "1.1.1.1"]
}
```

### GRUB cmdline (`/etc/default/grub`) — CURĂȚAT

```
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
```

Workaround-urile `pci=noaer usbcore.autosuspend=-1` au fost **eliminate** pe hardware nou.

### systemd-resolved drop-in (neschimbat)

```ini
[Resolve]
DNS=192.168.68.200
FallbackDNS=1.1.1.1 1.0.0.1
DNSStubListener=yes
```

---

## Cron jobs (CURĂȚATE)

```cron
0 4 1 * *  /home/cristi/scripts/system-cleanup.sh >> /home/cristi/scripts/cleanup.log 2>&1
0 3 * * 0  /home/cristi/scripts/backup-docker.sh
0 5 * * 0  /home/cristi/scripts/git-backup-config.sh
```

**Eliminate vs v5:**
- ~~`0 4 * * * docker run ... freshclam`~~ (redundant — container clamav face update intern)
- ~~`30 4 * * * /sbin/shutdown -r now`~~ (reboot zilnic — workaround USB inutil pe hardware nou)

---

## Homepage dashboard (rafinat 12 iunie)

URL: http://192.168.68.200:3000

### Layout final v6

```
Smart Home (1 coloană)
└── Solar live (HA widget — Putere/Baterie/Grid/Stare)

Utility (4 coloane)
├── Pi-hole (queries/blocked/blocked%)
├── qBittorrent (down/seed/up)
├── FileBrowser (port 8091)
└── CUPS (Print & AirScan)

Media (3 coloane)
├── Jellyfin
├── Jellyseerr (NEW)
└── Audiobookshelf

Monitorizare Spital (column)
└── Change Detection (3 diffs)

Management (2 coloane)
├── Zigbee2MQTT (Coordinator activ)
└── Portainer (Docker management)
```

**Scoase din v5:** grupul Automation complet (Sonarr / Radarr / Prowlarr / Bazarr) — utilizatorii folosesc Jellyseerr; *arr-urile rămân running, doar widget-urile UI dispar.

---

## Lecții acumulate (1-50)

**Lecțiile 1-43:** vezi v5. Esențiale: cgroup driver, restart always, USB symlinks by-id, Forecast.Solar calibrare, template sensors `| int(0)`, recorder include, apex group_by, etc.

### Lecții noi v6 (migrare HP 600 G2 + clamd refactor)

**44. `airsaned` din container `cups-airprint` folosește port 8090 pe host network**
Când containerul `jdrtronix/cups-hplip` rulează cu `network_mode: host`, lansează `airsaned --listen-port=8090` pentru AirScan (eSCL). Conflict direct cu orice alt serviciu care vrea 8090 (filebrowser). Fix: mută celălalt serviciu pe alt port. **NU** dezactiva airsaned dacă vrei scanare AirPrint pe iPhone — funcția AirScan trece prin port 8090.

**45. Filebrowser bind mount: dacă fișierul DB nu există pe host, Docker creează DIRECTOR gol**
Compose `volume: ./filebrowser.db:/database.db` — dacă `filebrowser.db` lipsește, Docker creează un DIRECTOR cu acel nume → eroare `is a directory`. Fix: `touch /path/filebrowser.db` + `chown 1000:1000` ÎNAINTE de prima `docker compose up`. Aplicabil oricărui bind mount fișier-la-fișier.

**46. `docker start` reutilizează config-ul cached, nu re-citește compose**
După modificare `docker-compose.yml` (ex. `sed` pe port mapping), `docker start filebrowser` rulează cu vechiul config. Trebuie `docker rm filebrowser && docker compose up -d filebrowser` pentru a aplica modificările. La fel pentru `devices:` adăugat ulterior — necesită recreate, nu doar start.

**47. Numele interfeței de rețea se schimbă cu hardware-ul**
Pe homepc (vechi) era `enp2s0`, pe HP 600 G2 Tiny e `eno1`. Schema `predictable network interface names` Ubuntu se bazează pe location PCI/BIOS, deci se schimbă la orice change de motherboard. Netplan + orice service systemd care referă interfața (ex `tailscale-tune.service`) trebuie editat. Fallback DHCP la sistem când netplan nu match-uiește interfața = noroc, nu feature.

**48. HP 600 G2 BIOS: "selected boot image did not authenticate" = Secure Boot activ**
Chiar cu Legacy disabled + UEFI mode + SSD UEFI valid (Ubuntu cu `/boot/efi/`), Secure Boot blochează bootloader-ul GRUB unsigned al Ubuntu. Fix: BIOS → Security → Secure Boot Configuration → Disable + Clear keys. La next boot HP cere confirmare cu cod 4 cifre afișat pe ecran (anti-tampering). Tastezi codul + Enter, boot reușit.

**49. `tailscale-tune.service` referă vechea interfață după migrare**
Service-ul generat de Tailscale (`/etc/systemd/system/tailscale-tune.service`) hardcodează numele NIC (ex. `enp2s0`) la setup inițial. După migrare hardware → `netlink error: no device matches name`. Fix one-liner: `sudo sed -i 's/enp2s0/eno1/g' /etc/systemd/system/tailscale-tune.service && sudo systemctl daemon-reload && sudo systemctl restart tailscale-tune`. Tailscale-ul în sine merge OK fără tune, doar fix-uri minore UDP buffers.

**50. ClamAV daemon resident >>> on-demand pe hardware cu RAM**
Pe 4GB RAM (homepc vechi) on-demand era singura variantă viabilă (0 idle / 1.1GB peak). Pe 16GB RAM (HP 600 G2), resident: 970MB constant, **9ms scan** (vs 28-90s on-demand). DB rămâne în memorie, no spawn overhead, healthcheck built-in, freshclamd intern (cron extern devine redundant). Atunci când ai RAM, întotdeauna resident.

---

## Comenzi utile

### Migrare / hardware

```bash
# Vezi interfața de rețea curentă
ip -br link show

# Verifică boot mode (UEFI vs Legacy)
ls /boot/efi/ 2>/dev/null && echo "UEFI" || echo "Legacy"

# Logs Tailscale
sudo journalctl -u tailscaled --since "1h ago" --no-pager | tail -30
sudo systemctl status tailscale-tune --no-pager

# USB sănătate
sudo journalctl --since "1 day ago" | grep -ciE "over-current"
lsusb -t
```

### ClamAV

```bash
# Status container clamav
docker ps | grep clamav
docker inspect --format='{{.State.Health.Status}}' clamav

# Test scan
docker exec clamav clamdscan --version
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' \
  > /tmp/eicar.txt
docker cp /tmp/eicar.txt clamav:/tmp/eicar.txt
docker exec clamav clamdscan /tmp/eicar.txt

# Update manual DB
docker exec clamav freshclam

# Test EICAR end-to-end
mkdir -p /home/cristi/server/downloads/incomplete/testav
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' \
  > /home/cristi/server/downloads/incomplete/testav/v.txt
mv /home/cristi/server/downloads/incomplete/testav \
   /home/cristi/server/downloads/complete/
sleep 10 && tail -10 /home/cristi/qbit-scan.log
```

### Jellyseerr

```bash
# Logs
docker logs --tail 30 jellyseerr

# Config persistent
ls /home/cristi/server/jellyseerr/config/

# API keys Sonarr/Radarr pentru setup
docker exec sonarr cat /config/config.xml | grep ApiKey
docker exec radarr cat /config/config.xml | grep ApiKey
```

### Stack general

```bash
sudo systemctl is-system-running
docker ps --format 'table {{.Names}}\t{{.Status}}'
df -h / && free -h && uptime

# Verifică DNS Pi-hole
dig @192.168.68.200 google.com +short
dig @192.168.68.200 doubleclick.net +short  # trebuie 0.0.0.0
```

### Solar / HA (neschimbat)

Vezi v5 pentru lista completă comenzi (HA logs, validare config, fix templates, sqlite queries pe recorder DB, etc).

---

## Action items pending

### Înalt prioritate
- [ ] **Disk 92-93%** — adaugă HDD 2TB second-hand pentru media (downloads + series + movies = 373GB / 401GB used). Cea mai mare problemă rămasă post-migrare.
- [ ] Monitorizare 7+ zile recalibrare Forecast.Solar (11500W → posibil 10500W)
- [ ] Tarife în HA Energy Dashboard (1.10 RON import / 0.40 RON export)

### Mediu
- [ ] Backup zilnic HA programat în Settings → System → Backups
- [ ] Tailscale exit node pentru iPhone (Pi-hole filtering pe 4G/5G)
- [ ] Investigare Sonarr indexers (nu mai găsește seriale cerute — Prowlarr)

### Quality of life
- [ ] Split DNS Tailscale pentru `.lan`
- [ ] ACLs Tailscale izolare iPhone vs PC
- [ ] UPS 600-900VA (~400-600 RON) pentru protecție pene curent
- [ ] Hardware transcoding Jellyfin Intel QuickSync HD 530 (acum posibil cu i5-6500T)

### Done în v6
- [x] Upgrade hardware (HP 600 G2 Tiny) ✅
- [x] Reactivare Zigbee2MQTT (USB sănătos) ✅
- [x] ClamAV resident (RAM disponibilă) ✅
- [x] Jellyseerr (request UI familie) ✅
- [x] Cleanup homepage (eliminat Automation group) ✅
- [x] Eliminat workaround USB (GRUB curat) ✅
- [x] Eliminat reboot zilnic ✅
- [x] Eliminat cron freshclam (redundant cu container) ✅

---

## Plan upgrade hardware viitor

**Done 12 iun 2026:** Migrare pe HP EliteDesk 600 G2 Tiny (i5-6500T, 16GB RAM). Cost ~300 RON second-hand.

**Next:**
- **HDD 2TB second-hand** (~150 RON) pentru media tier — rezolvă disk 93% permanent
- **UPS 600-900VA** (~400-600 RON) — protecție pene curent + shutdown grațios
- **Router upgrade** (M4R → Mikrotik hAP ax³ / GL.iNet Flint 2, ~500-700 RON) pentru viteza completă 1Gbps + VLAN-uri

---

## Contact / referințe

- **GitHub backup repo:** github.com:12Cristi/homelab-config (privat)
- **Pi-hole admin:** http://192.168.68.200:8082
- **Homepage:** http://192.168.68.200:3000
- **Portainer:** http://192.168.68.200:9000
- **Home Assistant:** http://192.168.68.200:8123
- **HA Solar dashboard:** http://192.168.68.200:8123/dashboard-solar/0
- **HA Energy Dashboard:** http://192.168.68.200:8123/energy
- **Jellyseerr:** http://192.168.68.200:5055
- **Jellyfin:** http://192.168.68.200:8096
- **Zigbee2MQTT:** http://192.168.68.200:8099
- **Filebrowser:** http://192.168.68.200:8091 (noauth, mutat de pe 8090)
- **qBittorrent:** http://192.168.68.200:8080
- **Logger LSW-5 admin:** http://192.168.68.101
- **Tailscale admin:** https://login.tailscale.com/admin

---

## Changelog

*19 mai 2026: Logger fizic LSW-5 conectat, integrare Solarman HACS funcțională. Stack solar complet operațional.*

*22 mai 2026: Pi-hole fără parolă + widget homepage nativ. Stack Zigbee adăugat.*

*1 iunie 2026: Auth cleanup (Filebrowser noauth, Sonarr/Radarr Disabled for Local). Pi-hole blocklists Tier 1+2+3. ClamAV antivirus stack operațional (on-demand). Zigbee oprit temporar din cauza USB defect.*

*5 iunie 2026: Recorder extins, template sensors financiar, utility meters, Forecast.Solar integration.*

*6 iunie 2026: Dashboard solar v2 complet — 9 carduri. Helpers redenumite. Automation 07:00/23:55.*

*8 iunie 2026: Protecție valori 0 cu `numeric_state above: 1`. Automation Forecast.Solar reload orar.*

*9 iunie 2026: Calibrare empirică Forecast.Solar 9000W → 11500W după 5 zile observații.*

*10 iunie 2026: Dashboard rafinat — layout 3 coloane Sections view. Card "Situația actuală" consolidat. Documentație v4.*

*11 iunie 2026: Portainer adăugat + widget homepage. Reordonare homepage. Calibrare Forecast.Solar -17% pe zi senină. Documentație v5.*

*12 iunie 2026: **MIGRARE HARDWARE HP 600 G2 Tiny.** SSD mutat fizic, post-boot fixes pentru netplan (`eno1`) + tailscale-tune. Eliminat workaround-uri USB defect (GRUB curat, reboot zilnic scos). **ClamAV refactor** la container resident — scan 9ms vs 28-90s. **Jellyseerr adăugat** pentru request UI familie. **Filebrowser** mutat 8090 → 8091 (conflict airsaned). **Zigbee2MQTT reactivat** cu network preservat. **Homepage** curățat (grupul Automation scos, Media cu 3 carduri). Stack final: 19 containere active, 0 failed services, 15Gi RAM disponibil. Lecții noi #44-50. Documentație v6.*
