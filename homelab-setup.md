# Homelab Setup — homepc

Document de referință pentru serverul Ubuntu cu Docker stack.
Ultima actualizare: **19 mai 2026**.

## Hardware

| | |
|---|---|
| **CPU** | Intel Pentium 3558U @ 1.70GHz (2 cores, Haswell, 2014) |
| **RAM** | 3.7 GB |
| **Storage** | Samsung SSD 860 EVO 500GB (wear 3%, 0 sectoare realocate, ~19k ore) |
| **OS** | Ubuntu 24.04.4 LTS (Noble) |
| **Hostname** | homepc |
| **IP LAN** | 192.168.68.200 |
| **IP Tailscale** | 100.113.68.25 |
| **Tailscale FQDN** | homepc.tail1b235c.ts.net |

Verdict utilizare: ~7% CPU, ~38% RAM, 27% disk. Multă rezervă pentru viitor.

## Containere Docker (15)

| Container | Imagine | Port | Hostname local | Acces |
|---|---|---|---|---|
| **homepage** | ghcr.io/gethomepage/homepage:latest | 3000 | `home.lan` | Dashboard principal |
| **jellyfin** | jellyfin/jellyfin | (host network) 8096 | `jellyfin.lan` | Media streaming |
| **pihole** | pihole/pihole:latest | 53, 8082 | `pihole.lan` | DNS + adblocking |
| **qbittorrent** | linuxserver/qbittorrent | 8080 | `torrent.lan` | Torrent client |
| **filebrowser** | filebrowser/filebrowser:latest | 8090 | `files.lan` | Browser fișiere |
| **audiobookshelf** | ghcr.io/advplyr/audiobookshelf:latest | 13378 | `books.lan` | Audiobooks/podcasts |
| **changedetection** | dgtlmoon/changedetection.io | 5000 | `watch.lan` | Monitor websites |
| **prowlarr** | lscr.io/linuxserver/prowlarr:latest | 9696 | `prowlarr.lan` | Indexer manager |
| **sonarr** | lscr.io/linuxserver/sonarr:latest | 8989 | `sonarr.lan` | TV automation |
| **radarr** | lscr.io/linuxserver/radarr:latest | 7878 | `radarr.lan` | Movie automation |
| **cups-airprint** | jdrtronix/cups-hplip:latest | (host network) 631 | `print.lan` | Print server |

| **homeassistant** | ghcr.io/home-assistant/home-assistant:stable | (host network) 8123 | `ha.lan` | Home automation + monitorizare solară |
| **mosquitto** | eclipse-mosquitto:2 | 1883, 9001 | — | MQTT broker (intern, pentru HA + integrări) |
| **bazarr** | lscr.io/linuxserver/bazarr | 6767 | `bazarr.lan` | Subtitle automation |
| **dockerproxy** | ghcr.io/tecnativa/docker-socket-proxy:latest | 2375 (intern) | — | Acces sigur la Docker socket pentru homepage |

Imprimanta configurată: **HP LaserJet M101-M106** (queue: `HP_LaserJet_M101-M106`, driver hpcups).

## Structură foldere

```
/home/cristi/server/
├── docker-compose.yml          # Stack definition
├── system-cleanup.sh           # Cleanup mensual (rulat via cron)
├── cleanup.log                 # Log cleanup
├── homepage/config/            # services.yaml, widgets.yaml, settings.yaml
├── pihole/etc-pihole/          # Pi-hole config + blocklists + history
├── pihole/etc-dnsmasq.d/
├── jellyfin/                   # Library metadata, users, history
├── qb-config/                  # qBittorrent settings + torrent states
├── prowlarr/, sonarr/, radarr/ # Config *arr suite
├── abs/config/                 # Audiobookshelf config
├── abs/metadata/               # Audiobookshelf metadata
├── changedetection_data/       # Watch-uri configurate
├── cups/, cups-config/         # CUPS config
├── filebrowser.db              # Filebrowser users
├── downloads/                  # Torrent downloads (~27 GB)
├── movies/                     # Filme (~67 GB)
├── series/                     # Seriale
├── books/                      # Cărți pentru audiobookshelf (~2 GB)
└── Carti/                      # Cărți (~2.6 GB)

/home/cristi/backups/
├── backup-docker.sh            # Script backup săptămânal
├── backup.log                  # Log backup
└── docker-config-*.tar.gz      # Backup-uri (ultimele 4)

/home/cristi/scripts/
├── pihole-sid-refresh.sh       # Refresh SID Pi-hole pentru widget homepage
└── pihole-sid.log              # Log refresh SID
```

## Tailscale

- **Cont**: legat de Google (stoica.cristian81@...)
- **Tailnet**: tail1b235c.ts.net
- **MagicDNS**: activ
- **Subnet routing**: 192.168.68.0/24 (aprobat în admin)
- **Override DNS**: activ — toate device-urile Tailscale folosesc Pi-hole-ul (100.113.68.25)
- **Pi-hole listening mode**: ALL (acceptă query-uri din toate interfețele)

### Configurare reapelată

IP forwarding setat permanent în `/etc/sysctl.d/99-tailscale.conf`:
```
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
```

UDP GRO optimization persistentă via `/etc/systemd/system/tailscale-tune.service`.

## DNS Local (Pi-hole)

Setat prin `pihole-FTL --config dns.hosts`. Toate hostname-urile pointează la 192.168.68.200:

```
homepc, home.lan, jellyfin.lan, pihole.lan,
torrent.lan, books.lan, files.lan, watch.lan,
prowlarr.lan, sonarr.lan, radarr.lan, print.lan,
bazarr.lan, ha.lan
```

## Docker daemon config

`/etc/docker/daemon.json`:
```json
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "dns": ["192.168.68.200", "1.1.1.1"]
}
```

Log rotation: max 30 MB per container (10 MB × 3 fișiere).
DNS: Pi-hole primary, Cloudflare fallback.

## Automatizări (cron)

User crontab (`crontab -l`):
```cron
# Cleanup sistem (apt, journal, kernels vechi, docker dangling)
0 4 1 * * /home/cristi/server/system-cleanup.sh >> /home/cristi/server/cleanup.log 2>&1

# Backup săptămânal config Docker
0 3 * * 0 /home/cristi/backups/backup-docker.sh

# Refresh SID Pi-hole pentru widget homepage (înainte de expirare la 30 min)
*/25 * * * * /home/cristi/scripts/pihole-sid-refresh.sh
```

Servicii systemd:
- `smartmontools.service` — monitoring SSD permanent
- `tailscale-tune.service` — UDP GRO optimization la boot

## Pi-hole — particularități

- **Versiune**: 6.4.2
- **Listening mode**: ALL (Tailscale + LAN + Docker)
- **Max sessions API**: 64
- **Session timeout**: 300 sec
- **App password hash**: setat în `webserver.api.app_pwhash`

Widget homepage folosește `customapi` cu SID auto-regenerat la 25 min via cron.
Motiv: bug-ul în homepage 1.12.3 + Pi-hole 6.4.2 — widget-ul nativ pierde sesiunea după ~16 request-uri.
Când va apărea fix în homepage, se poate reveni la widget native.


## Home Assistant + monitorizare solară

**Adăugat 19 mai 2026.** Stack: Home Assistant Core + Mosquitto MQTT + integrare Solarman pentru invertor Deye SUN-12K-SG04LP3.

### Hardware fotovoltaic

| | |
|---|---|
| **Invertor** | Deye SUN-12K-SG04LP3 (12 kW hybrid) |
| **Logger** | LSW-5 (Solarman WiFi stick) la `192.168.68.101:8899` |
| **Locație** | Garaj |

### Integrare

Instalată via HACS: `custom_components/solarman/` (StephanJoubert/home_assistant_solarman).

Config entry: host=`192.168.68.101`, port=`8899`, profile=Deye Hybrid.
Rezultat: ~90 senzori reali cu prefix `sensor.deye_*`.

### Senzori critici pentru Energy Dashboard

| Senzor | Unitate | Rol |
|---|---|---|
| `sensor.deye_today_production` | kWh | Solar production |
| `sensor.deye_today_energy_import` | kWh | Grid consumption |
| `sensor.deye_today_energy_export` | kWh | Return to grid |
| `sensor.deye_today_battery_charge` | kWh | Battery IN |
| `sensor.deye_today_battery_discharge` | kWh | Battery OUT |
| `sensor.deye_pv_power` | W | Producție live |
| `sensor.deye_battery` | % | SOC live |
| `sensor.deye_load_power` | W | Consum casă live |
| `sensor.deye_grid_power` | W | Negativ=import, pozitiv=export |
| `sensor.deye_battery_power` | W | Negativ=charge, pozitiv=discharge |

### Template sensors (în `configuration.yaml`)

Convertesc senzorii cu semn în senzori unidirecționali, pentru dashboard-uri și widget homepage:
- `sensor.grid_import_power`, `sensor.grid_export_power` (din `deye_grid_power`)
- `sensor.battery_charging_power`, `sensor.battery_discharging_power` (din `deye_battery_power`)

### Recorder configurat cu globs

```yaml
recorder:
  purge_keep_days: 90
  include:
    entity_globs:
      - sensor.deye_*
    entities:
      - sensor.grid_import_power
      - sensor.grid_export_power
      - sensor.battery_charging_power
      - sensor.battery_discharging_power
```

### Energy Dashboard mapping

La `http://192.168.68.200:8123/config/energy`:
- **Grid consumption**: `sensor.deye_today_energy_import`
- **Return to grid**: `sensor.deye_today_energy_export`
- **Solar production**: `sensor.deye_today_production`
- **Battery IN**: `sensor.deye_today_battery_charge`
- **Battery OUT**: `sensor.deye_today_battery_discharge`

### Widget pe homepage

În `services.yaml` sub categoria `- Solar:`, type=`homeassistant`, cu `key:` (long-lived access token) și custom states pentru: PV power, baterie SOC, consum casă, producție azi.

### Economii & ROI tracking

**Tarife configurate (în `configuration.yaml`):**
- Consum: `1.10 RON/kWh` (preț final cu TVA, distribuție, taxe)
- Export (feed-in prosumer): `0.40 RON/kWh`

**Senzori cost zilnic (template sensors):**

| Senzor | Calcul | Rol |
|---|---|---|
| `sensor.cost_evitat_azi` | `(production - export) × 1.10` | Cât NU plătești pentru consum direct din PV |
| `sensor.castig_export_azi` | `export × 0.40` | Câștig din vânzarea surplusului |
| `sensor.economie_totala_azi` | suma celor doi | Economie totală zilnică |

**Utility Meter (agregare lunară/anuală/lifetime):**

```yaml
utility_meter:
  productie_lunara:   { source: sensor.deye_today_production, cycle: monthly }
  productie_anuala:   { source: sensor.deye_today_production, cycle: yearly }
  consum_lunar:       { source: sensor.deye_today_load_consumption, cycle: monthly }
  consum_anual:       { source: sensor.deye_today_load_consumption, cycle: yearly }
  import_lunar:       { source: sensor.deye_today_energy_import, cycle: monthly }
  export_lunar:       { source: sensor.deye_today_energy_export, cycle: monthly }
  export_anual:       { source: sensor.deye_today_energy_export, cycle: yearly }
  recuperat_total:    { source: sensor.economie_totala_azi, cycle: yearly }  # cumulator economii
```

⚠️ **Cunoscut:** utility_meter contorizează doar de la momentul creării, nu istoric. Pentru calibrare (după prima zi), folosește API call:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "sensor.recuperat_lifetime", "value": "40"}' \
  http://192.168.68.200:8123/api/services/utility_meter/calibrate
```

### ROI tracker

Sistemul fotovoltaic a costat **42.000 RON** (panouri + invertor Deye 12kW + baterie 15kWh + montaj).

**Template sensors pentru amortizare:**

| Senzor | Formula | Valoare inițială (19 mai) |
|---|---|---|
| `sensor.investitie_initiala` | constantă | 42.000 RON |
| `sensor.recuperat_lifetime` | utility_meter cu cycle yearly | calibrat la 40 RON |
| `sensor.ramas_de_recuperat` | investitie - recuperat | 41.960 RON |
| `sensor.procent_amortizat` | recuperat / investitie × 100 | 0.1% |
| `sensor.economie_medie_zilnica` | recuperat / (days since 18.05.2026) | ~25 RON/zi |
| `sensor.zile_pana_amortizare` | ramas / medie_zilnica | ~1670 zile |
| `sensor.ani_pana_amortizare` | zile / 365 | **~4.6 ani** 🎯 |
| `sensor.viata_baterie_ramasa` | (6000 - cicluri) / 6000 × 100 | 100% (rating 6000 cicluri) |

⚠️ Estimările sunt imprecise primele 2-3 săptămâni. Apoi `economie_medie_zilnica` converge spre realitate (~25-35 RON/zi medie anuală, în funcție de sezoane).

### Dashboard "Solar" (Lovelace)

Dashboard nou creat la `http://192.168.68.200:8123/solar`. Sections mode cu carduri:

1. **Economii Solar** — economie azi, lună, an, cost evitat, câștig export
2. **Producție & Consum** — kWh produs/consumat/exportat luna și anul
3. **Live acum** — glance card cu PV (W), Baterie (%), Consum (W), Grid (W), Bat (W)
4. **ROI - Amortizare** — investiție, recuperat, rămas, % amortizat, medie zilnică, ani până amortizare, viață baterie

### Istoric — mock removed (15-19 mai 2026)

Între 15-19 mai a existat un setup mock în `/home/cristi/server/deye-mock/` care simula invertorul pe MQTT cu container Docker `deye-mock` și script Python `mock_logger.py`. Eliminat complet pe 19 mai după ce logger-ul fizic LSW-5 a sosit:

- Container Docker oprit și șters
- Folder `deye-mock/` arhivat la `/home/cristi/deye-mock-backup-20260519.tar.gz` și șters
- Retained MQTT messages curățate (homeassistant/sensor/deye_mock/*, deye/sensor/*)
- Device-ul `Deye 12kW Invertor` (MQTT Discovery) șters din HA UI
- Statistici contaminate șterse din DB (~5060 puncte, ~5 MB recuperați)
- `configuration.yaml` refactorizat de pe `sensor.deye_12kw_invertor_*` (mock) pe `sensor.deye_*` (real)

**Important**: senzorii `sensor.deye_12kw_invertor_*` NU mai există. Toate referințele trebuie să folosească prefixul `sensor.deye_*`.

## Backup

**Script**: `/home/cristi/backups/backup-docker.sh`

Excludere automată:
- `server/downloads`, `server/movies`, `server/series`, `server/books`, `server/Carti` (media)
- `server/jellyfin/cache`, `server/jellyfin/transcodes`, `server/jellyfin/log`
- `server/abs/metadata/cache`
- `server/qb-config/qBittorrent/logs`

Mărime arhivă: ~290 MB. Păstrează ultimele 4 backup-uri.

⚠️ **Limitare cunoscută**: backup-urile sunt pe ACELAȘI SSD cu serverul. Recomandat backup off-site (TODO).

## Restore pe alt PC

```bash
# Pe noul PC
sudo apt install docker.io docker-compose-plugin smartmontools
sudo usermod -aG docker cristi

# Asigură UID 1000 pentru cristi (PUID în compose)
id cristi   # trebuie să afișeze uid=1000

# Copiezi arhiva și extragi
cd /home/cristi
sudo tar xzpf docker-config-DATE.tar.gz
sudo chown -R 1000:1000 server/

# Pornești
cd server && docker compose up -d

# Reinstalezi Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --advertise-routes=192.168.68.0/24 --accept-dns=false
```

⚠️ Atenție:
- IP-ul 192.168.68.200 trebuie păstrat (DHCP reservation pe router) — multe servicii îl au hardcodat
- Path USB pentru CUPS poate diferi (`lsusb` → update în compose)
- Tailscale: aprobă din nou ruta în admin panel + verifică că DNS Pi-hole e setat

## Decizii de securitate

Setup-ul e **LAN + Tailscale**. Decizii conștiente:

✅ **Acceptat**:
- Parole simple (qbittorrent admin/admin123, pi-hole `fancy`) — LAN privat, nu expus internet
- Servicii fără HTTPS — Tailscale criptează traficul oricum
- Pi-hole `Permit all origins` — necesar pentru Tailscale
- IP hardcodat în config-uri — DHCP reservation rezolvă

❌ **Nu se face**:
- Reverse proxy + SSL cert — overkill pentru LAN/Tailscale
- Authelia/Authentik — same
- Port forwarding pe router — totul prin Tailscale

🟡 **Pe roadmap** (când va fi cazul):
- Backup off-site (Backblaze B2 sau disk extern)
- 2FA pe contul Google + "Require 2FA" în Tailscale admin
- Watchtower pentru update-uri automate containere

## Comenzi utile pentru debug

### Status general
```bash
docker compose ps                                       # Status containere
docker stats --no-stream                                # CPU/RAM per container
sudo systemctl status smartmontools                     # SMART monitoring
sudo crontab -l                                         # Job-uri cron root
crontab -l                                              # Job-uri cron user
tailscale status                                        # Status Tailscale
```

### Pi-hole
```bash
docker exec pihole pihole -v                            # Versiune
docker exec pihole pihole-FTL --config dns.listeningMode # Listen mode
docker exec pihole pihole-FTL --config dns.hosts        # Mapări DNS local
docker exec pihole pihole -q --partial DOMAIN           # Verifică dacă blocat

# Test login API
curl -s -X POST http://192.168.68.200:8082/api/auth \
  -H "Content-Type: application/json" \
  -d '{"password":"fancy"}'
```

### Backup manual
```bash
~/backups/backup-docker.sh                              # Rulează backup
ls -lh ~/backups/                                       # Vezi backup-uri
cat ~/backups/backup.log                                # Log
```

### Cleanup manual
```bash
~/server/system-cleanup.sh                              # Cere confirmare interactiv
```

### SMART manual
```bash
sudo smartctl -a /dev/sda | grep -E "Reallocated|Pending|Power_On_Hours|Wear"
```

### Refresh SID Pi-hole manual
```bash
~/scripts/pihole-sid-refresh.sh                         # Refresh + restart homepage
cat ~/scripts/pihole-sid.log                            # Vezi istoric
```

## Logs interesante

| Component | Cale |
|---|---|
| Backup | `~/backups/backup.log` |
| Cleanup sistem | `~/server/cleanup.log` |
| Refresh SID Pi-hole | `~/scripts/pihole-sid.log` |
| Container logs | `docker logs <container_name>` |
| SMART | `sudo journalctl -u smartmontools` |
| Tailscale | `sudo journalctl -u tailscaled` |

## Optimizări nefăcute (pentru viitor)

În ordinea utilității:

1. **Watchtower** — update-uri automate containere (10 min)
2. **Intel Quick Sync pe Jellyfin** — hardware acceleration video (10 min)
3. **Backup off-site** — disk extern sau Backblaze B2 (15-30 min)
4. **Health monitoring** — Uptime Kuma cu notificări (15 min)
5. **Pi-hole DHCP** — în loc de router, pentru nume de host în Query Log (5 min)
6. **Migrate cgroup v1 → v2** — deadline 2029 (planificat)

## Probleme cunoscute / quirks

1. **Homepage Pi-hole widget** — folosește customapi cu SID refresh automat în loc de widget native (bug homepage 1.12.3 + Pi-hole v6.4.2)
2. **AirPrint nu trece prin Tailscale** — limitare mDNS, normal. Acasă merge automat, în concediu trebuie adăugare manuală
3. **iPhone nu vede AirPrint prin Tailscale** — necesită app plătit (Printer Pro $7) sau alt workaround
4. **systemd "Failed to connect to API bus"** la boot — bug cosmetic Ubuntu 24.04, ignorat
5. **CGroup v1 deprecation warning** — Docker, deadline 2029
6. **Bluetooth scanner errors în HA** — `hci0 Failed to force stop scanner` apare repetat în logs. Bug cunoscut `habluetooth` pe adapter Foxconn integrat în homepc. Dezactivează din Settings → Devices & Services → Bluetooth dacă nu folosești BT
7. **Mock solar removed** — senzorii vechi `sensor.deye_12kw_invertor_*` nu mai există (vezi secțiunea Home Assistant)

## Acces servicii — quick reference

### De pe LAN acasă
```
http://home.lan:3000        # Homepage
http://jellyfin.lan:8096    # Jellyfin
http://pihole.lan:8082/admin # Pi-hole
http://torrent.lan:8080     # qBittorrent
http://books.lan:13378      # Audiobookshelf
http://files.lan:8090       # Filebrowser
http://watch.lan:5000       # Changedetection
http://prowlarr.lan:9696    # Prowlarr
http://sonarr.lan:8989      # Sonarr
http://radarr.lan:7878      # Radarr
http://print.lan:631        # CUPS
http://ha.lan:8123          # Home Assistant (solar monitoring)
http://bazarr.lan:6767      # Bazarr
```

### Prin Tailscale (oriunde)
Aceleași URL-uri (DNS Pi-hole rezolvă prin Tailscale) sau direct cu IP:
```
http://homepc:3000          # via MagicDNS
http://192.168.68.200:3000  # via subnet routing
http://100.113.68.25:3000   # IP Tailscale direct
```

### Login credențiale (pentru tine, nu pentru repo)
- **Pi-hole**: `fancy`
- **Home Assistant**: cont creat la primul login UI; long-lived token salvat în homepage `services.yaml`
- **qBittorrent**: `admin / admin123`
- **CUPS admin**: `admin / YourStrongPassword123!`
- **Filebrowser**: vezi `filebrowser.db` sau crează nou prin CLI
- **Jellyfin/Audiobookshelf**: management în UI per app

---

**Document creat după sesiunea de configurare 28 aprilie 2026.**
**Actualizat 19 mai 2026** — adăugat Home Assistant, Mosquitto, integrare Solarman pentru invertor Deye 12kW, plus containere Bazarr și Docker socket proxy. Sesiune extinsă: template sensors pentru economii (1.10 RON/kWh consum, 0.40 RON/kWh export), utility_meter pentru agregare lunară/anuală, ROI tracker cu estimare 4.6 ani amortizare, dashboard "Solar" cu 4 carduri Lovelace.

Pentru actualizări viitoare, modifică acest fișier.
