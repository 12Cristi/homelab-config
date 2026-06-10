# Homelab Setup — homepc

**Owner:** cristi  
**Last updated:** 2026-06-10  
**Host:** Ubuntu 24.04 LTS, kernel 6.8.0-124-generic  
**Hardware:** desktop x86_64, 4GB RAM, 457GB SSD (hardware end-of-life, vezi lecția #22)  
**Hostname:** homepc  
**LAN IP:** 192.168.68.200  
**Tailscale IP:** 100.113.68.25  
**Tailnet:** tail1b235c.ts.net  
**Tailscale FQDN:** homepc.tail1b235c.ts.net

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
        ├── switch ──→ server (homepc, cablu Cat6 NOU)
        │         ──→ M4R satelit interior (backhaul cablu — scos din switch!)
        │         ──→ M4R satelit exterior (cablu direct, 920 Mbps)
        │
        └── M4R satelit interior (wireless backhaul după modificare)

LAN: 192.168.68.0/24
Gateway: 192.168.68.1 (M4R principal)
DHCP: M4R principal
DNS: Pi-hole (192.168.68.200) cu fallback 1.1.1.1
```

### Notă importantă M4R

M4R din 2018 limitează NAT throughput la **~360 Mbps sustained** (~650 burst). Asta e limita hardware, nu un defect. Pentru viteza completă (1Gbps), planul e Opțiunea 2 ISP — ONT nou cu Wi-Fi 6 integrat + M4R în Access Point mode.

**Lecție rețea:** Satelitul interior conectat în serie cu satelitul exterior (lanț M4R→M4R) înjumătățește throughput-ul. Fix: conectează fiecare satelit direct din switch (topologie stea, nu lanț). Sateliții fără cablu fac backhaul wireless automat.

---

## Servicii Docker (15 containere active, +1 oprit)

Toate în `/home/cristi/server/docker-compose.yml`. Cu `restart: always` (excepție zigbee2mqtt oprit temporar).

| Container | Port | Funcție |
|-----------|------|---------|
| pihole | 8082 (UI), 53 (DNS) | DNS filtering ad-blocking |
| jellyfin | host network | Media streaming (filme, seriale, audiobooks) |
| sonarr | 8989 | Tracking seriale (auth: Forms, Disabled for Local) |
| radarr | 7878 | Tracking filme (auth: Forms, Disabled for Local) |
| bazarr | 6767 | Subtitrări automat |
| prowlarr | 9696 | Indexer aggregator |
| qbittorrent | 8080, 6881 | Torrent client |
| audiobookshelf | 13378 | Server audiobooks |
| filebrowser | 8090 | Web file manager (auth: noauth) |
| changedetection | 5000 | Monitor schimbări website-uri |
| cups-airprint | host network | AirPrint pentru iPhone |
| homepage | 3000 | Dashboard centralizat |
| dockerproxy | 127.0.0.1:2375 | Docker API read-only proxy pentru homepage |
| mosquitto | 1883 (MQTT) | MQTT broker pentru stack solar + Zigbee2MQTT |
| homeassistant | host network (8123) | Home Assistant Core — monitoring solar |
| zigbee2mqtt | 8099 (UI) | Zigbee coordinator (Sonoff MG24) — **OPRIT 2026-06-01** |

---

## Auth strategy (LAN intern, fără expunere externă)

| Serviciu | Auth status | Cum |
|----------|-------------|-----|
| Pi-hole | Parolă goală | `docker exec pihole pihole setpassword ""` |
| Filebrowser | noauth | `filebrowser config set --auth.method=noauth` |
| Sonarr / Radarr / Prowlarr | Forms + DisabledForLocalAddresses | edit `config.xml` |
| Bazarr | None | UI Settings → General → Authentication |
| qBittorrent | Bypass LAN/Tailscale | Settings → Web UI → Bypass for subnets: `192.168.68.0/24, 100.64.0.0/10` |
| Jellyfin | Per-user (păstrat) | Profile-uri separate, "Remember me" |
| Audiobookshelf | Auth obligatoriu (token persistent) | App-ul reține token-ul după primul login |

---

## Stack ClamAV antivirus (operațional din 2026-06-01)

### Arhitectură

```
qBittorrent termină download
        ↓ move din incomplete/ în complete/
   /home/cristi/server/downloads/complete/
        ↓ inotifywait moved_to,create
   systemd unit qbit-watch.service (runs as cristi)
        ↓ docker run --rm
   clamav/clamav:stable on-demand container
        ↓ -r --no-summary --infected
   ┌─────────────┴─────────────┐
   CLEAN (exit 0)        INFECTED (exit 1)
        │                       │
   log doar              mv în quarantine/
                         /home/cristi/server/downloads/quarantine/
```

### Resurse consumate

- **Idle:** ~5 MB (doar inotifywait rulează permanent)
- **La scan:** ~1.1-1.4 GB RAM pentru 28-90 sec (load DB + scan)
- **Disk DB signaturi:** ~108 MB în `/home/cristi/server/clamav/db/`
- **Update zilnic:** ~150 MB RAM pentru 2-3 min la 4:00 AM via cron

### Update signaturi (cron zilnic 4:00 AM)

```bash
0 4 * * * docker run --rm \
  -v /home/cristi/server/clamav/db:/var/lib/clamav \
  clamav/clamav:stable freshclam \
  >> /home/cristi/clamav-update.log 2>&1
```

### Watcher script `/usr/local/bin/qbit-watch.sh`

```bash
#!/bin/bash
WATCH_DIR="/home/cristi/server/downloads/complete"
QUARANTINE="/home/cristi/server/downloads/quarantine"
LOG="/home/cristi/qbit-scan.log"

mkdir -p "$WATCH_DIR" "$QUARANTINE"
echo "[$(date)] Watcher started on $WATCH_DIR" >> "$LOG"

inotifywait -m -e moved_to,create --format '%f' "$WATCH_DIR" | \
while read NEW_ITEM; do
    [ -z "$NEW_ITEM" ] && continue
    ITEM_PATH="$WATCH_DIR/$NEW_ITEM"
    [ ! -e "$ITEM_PATH" ] && continue
    sleep 5
    
    echo "[$(date)] Scan: $NEW_ITEM" >> "$LOG"
    SCAN_PATH="/scan/complete/$NEW_ITEM"
    
    RESULT=$(docker run --rm \
      --entrypoint clamscan \
      -v /home/cristi/server/clamav/db:/var/lib/clamav:ro \
      -v /home/cristi/server/downloads:/scan:ro \
      clamav/clamav:stable \
      -r --no-summary --infected "$SCAN_PATH" 2>&1)
    EXIT=$?
    
    case $EXIT in
      0) echo "[$(date)] CLEAN: $NEW_ITEM" >> "$LOG" ;;
      1)
        echo "[$(date)] INFECTED: $NEW_ITEM" >> "$LOG"
        echo "$RESULT" >> "$LOG"
        [ -e "$ITEM_PATH" ] && mv "$ITEM_PATH" "$QUARANTINE/" 2>>"$LOG" \
          && echo "[$(date)] Quarantined → $QUARANTINE/$NEW_ITEM" >> "$LOG"
        ;;
      *) echo "[$(date)] ERROR ($EXIT): $NEW_ITEM" >> "$LOG"; echo "$RESULT" >> "$LOG" ;;
    esac
done
```

### systemd unit `/etc/systemd/system/qbit-watch.service`

```ini
[Unit]
Description=qBittorrent downloads ClamAV watcher
After=docker.service network.target
Requires=docker.service
BindsTo=docker.service
PartOf=docker.service

[Service]
Type=simple
ExecStart=/usr/local/bin/qbit-watch.sh
Restart=always
RestartSec=10
User=cristi
Group=cristi

[Install]
WantedBy=multi-user.target
```

---

## Pi-hole — blocklists finale (Tier 1+2+3)

Block rate stabilizat ~15-20%.

### Liste active

```
# Ad-block principal
https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt
https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@main/adblock/dyndns.txt
https://raw.githubusercontent.com/hoshsadiq/adblock-nocoin-list/master/hosts.txt

# NSFW + adult
https://nsfw.oisd.nl/
https://raw.githubusercontent.com/hagezi/dns-blocklists/main/hosts/doh.txt

# Malware (Tier 1)
https://v.firebog.net/hosts/RPiList-Malware.txt
https://urlhaus.abuse.ch/downloads/hostfile/
https://phishing.army/download/phishing_army_blocklist_extended.txt

# Tier 2 — Privacy/Telemetry
https://raw.githubusercontent.com/Perflyst/PiHoleBlocklist/master/SmartTV.txt
https://raw.githubusercontent.com/crazy-max/WindowsSpyBlocker/master/data/hosts/spy.txt
https://raw.githubusercontent.com/jerryn70/GoodbyeAds/master/Hosts/GoodbyeAds.txt

# Tier 3 — EU/RO specific
https://hole.cert.pl/domains/domains.txt

# Gambling
https://blocklistproject.github.io/Lists/gambling.txt
```

---

## Stack solar (funcțional din 19 mai 2026, dashboard rafinat 10 iunie)

### Arhitectură

```
Deye 12kW invertor (SN: 2511155814)
        │ RS485
        ↓
WiFi logger LSW-5 (SN: 3597131694, IP: 192.168.68.101)
        │ SolarmanV5 protocol, port 8899
        ↓
Home Assistant Core (port 8123, host network)
  └── Integrare Solarman (HACS, davidrapan)
        │ senzori live
        ↓
  ├── Energy Dashboard HA (built-in)
  ├── Forecast.Solar integration (lat 47.1772, long 23.0722)
  ├── Template sensors (financiar, eficiență, viața bateriei)
  ├── Utility meters (zi/lună/an pentru productie/consum/import/export)
  ├── Helpers + automation tracking forecast vs real
  └── Dashboard custom apexcharts (Sections view, 3 coloane)
```

### Logger LSW-5

- **Model:** LSW-5 (IGEN Tech Co.)
- **Firmware:** LSW5_32_5406_SS_04_00.00.00.11
- **SN:** 3597131694
- **PWD:** 41515a27
- **IP LAN:** 192.168.68.101
- **Admin web:** http://192.168.68.101 (admin/admin)
- **Port Modbus:** 8899 TCP

### Integrare Solarman în HA

Configurație via HACS → integrarea `solarman` de la `davidrapan`:
- **Device name:** Deye
- **IP:** 192.168.68.101
- **Port:** 8899
- **Protocol:** TCP
- **Profile:** Auto (detectat SG0*LP3 — LV 3-Phase Hybrid Inverter)

### Senzori principali

| Senzor HA | Valoare |
|-----------|---------|
| sensor.deye_battery | % SOC |
| sensor.deye_battery_power | W (neg=charge) |
| sensor.deye_battery_voltage | V |
| sensor.deye_battery_state | charging/discharging |
| sensor.deye_battery_temperature | °C |
| sensor.deye_battery_soh | % State of Health |
| sensor.deye_pv_power | W total PV |
| sensor.deye_pv1_power / pv2_power | W per string |
| sensor.deye_grid_power | W (neg=import, poz=export) |
| sensor.deye_load_power | W consum casă |
| sensor.deye_today_production | kWh produs azi |
| sensor.deye_today_load_consumption | kWh consumat azi |
| sensor.deye_today_energy_export | kWh exportat azi |
| sensor.deye_today_battery_charge | kWh încărcat azi |
| sensor.deye_today_battery_discharge | kWh descărcat azi |
| sensor.deye_total_production | kWh lifetime |
| sensor.deye_device_state | Normal/Fault |
| sensor.deye_temperature | °C invertor |
| sensor.deye_dc_temperature | °C DC side |
| binary_sensor.deye_connection | on/off conexiune logger |
| binary_sensor.deye_battery_alarm | on/off |
| binary_sensor.deye_battery_fault | on/off |

### Forecast.Solar integration (CALIBRAT 9 iunie)

Configurare HA UI → Add Integration → Forecast.Solar:
- **Latitude:** 47.1772
- **Longitude:** 23.0722
- **Declination:** **25°** (NU 30° default — orientarea reală)
- **Azimuth:** **180°** (South, perfect)
- **Modules power:** **11500 W** ← calibrat empiric (vezi lecția #36)

**Calibrare empirică pe 5 zile (5-9 iunie 2026):**

| Zi | Estimat (cu 9000W) | Real | Eroare % |
|---|---|---|---|
| 5 iun | 20.5 | 30.2 | +47% |
| 6 iun | 23.5 | 35.4 | +51% |
| 7 iun | 42.3 | 48.3 | +14% |
| 8 iun | 31.4 | 53.4 | +70% |
| 9 iun | 45.7 | 54.9 | +20% |
| **Total** | 163.4 | 222.2 | **+36% medie** |

Concluzie: Forecast.Solar sistematic pesimist cu 36%. Calculul calibrare: `9000 × 1.28 = 11500W` (factor moderat 28%, păstrând buffer pentru zile noroase). Validare pe 9 iunie: estimat 54.6 vs real 54.9 = **0.6% diferență** (cer senin). Monitorizare 5-7 zile mai (verdict 15-16 iunie).

Senzori generați:
- `sensor.energy_production_today` — predicție kWh azi (adaptiv, update la 30 min cu meteo live)
- `sensor.energy_production_tomorrow` — predicție kWh mâine
- `sensor.power_production_now` — putere instantanee estimată
- `sensor.power_highest_peak_time_today` — ora peak

**Comportament cheie:** API recalculează continuu cu meteo live. Pentru tracking estimat-vs-real meaningful: snapshot la 07:00 (predictie inițială), real la 23:55 (vezi lecția #29).

### Template sensors în configuration.yaml

```yaml
template:
  - sensor:
      # Grid split: pozitiv=export, negativ=import
      - name: "Grid import power"
        unique_id: deye_grid_import_power
        unit_of_measurement: W
        device_class: power
        state_class: measurement
        state: >
          {% set g = states('sensor.deye_grid_power') | float(0) %}
          {{ (g * -1) if g < 0 else 0 }}
      
      - name: "Grid export power"
        unique_id: deye_grid_export_power
        state: >
          {% set g = states('sensor.deye_grid_power') | float(0) %}
          {{ g if g > 0 else 0 }}
      
      # Battery split
      - name: "Battery charging power"
        state: >
          {% set b = states('sensor.deye_battery_power') | float(0) %}
          {{ (b * -1) if b < 0 else 0 }}
      
      - name: "Battery discharging power"
        state: >
          {% set b = states('sensor.deye_battery_power') | float(0) %}
          {{ b if b > 0 else 0 }}
      
      # Financiar
      - name: "Cost evitat azi"
        unit_of_measurement: RON
        state: >
          {% set self_consumed = states('sensor.deye_today_production') | float(0) 
              - states('sensor.deye_today_energy_export') | float(0) %}
          {{ (self_consumed * 1.10) | round(2) }}
      
      - name: "Castig export azi"
        unit_of_measurement: RON
        state: >
          {{ (states('sensor.deye_today_energy_export') | float(0) * 0.40) | round(2) }}
      
      - name: "Economie totala azi"
        unit_of_measurement: RON
        state: >
          {{ ((states('sensor.cost_evitat_azi') | float(0)) 
              + (states('sensor.castig_export_azi') | float(0))) | round(2) }}
      
      # Amortizare
      - name: "Investitie initiala"
        state: 42000
      
      - name: "Ramas de recuperat"
        unit_of_measurement: RON
        state: >
          {% set total = states('sensor.investitie_initiala') | float(0) %}
          {% set rec = states('sensor.recuperat_lifetime') | float(0) %}
          {{ (total - rec) | round(2) }}
      
      - name: "Procent amortizat"
        unit_of_measurement: '%'
        state: >
          {% set total = states('sensor.investitie_initiala') | float(1) %}
          {% set rec = states('sensor.recuperat_lifetime') | float(0) %}
          {{ ((rec / total) * 100) | round(2) }}
      
      # Acuratețe forecast (după 19:00)
      - name: "Forecast accuracy azi"
        unit_of_measurement: '%'
        state: >
          {% set hour = now().hour %}
          {% set real = states('sensor.deye_today_production') | float(0) %}
          {% set estimat = states('sensor.energy_production_today') %}
          {% if estimat in ['unavailable', 'unknown', 'none'] or hour < 19 or real < 1 %}
            None
          {% else %}
            {{ ((real / (estimat | float)) * 100) | round(1) }}
          {% endif %}
      
      - name: "Forecast diferenta azi"
        unit_of_measurement: kWh
        state: >
          {% set hour = now().hour %}
          {% set real = states('sensor.deye_today_production') | float(0) %}
          {% set estimat = states('sensor.energy_production_today') %}
          {% if estimat in ['unavailable', 'unknown', 'none'] or hour < 19 or real < 1 %}
            None
          {% else %}
            {{ (real - (estimat | float)) | round(2) }}
          {% endif %}
      
      - name: "Forecast eficienta kWp"
        unit_of_measurement: kWh/kWp
        state: >
          {% set real = states('sensor.deye_today_production') | float(0) %}
          {{ (real / 8.75) | round(2) }}
```

**Important:** TOATE template sensors folosesc `| float(0)` și `| int(0)` cu default. Templates care depind de Forecast.Solar verifică `if estimat in ['unavailable', 'unknown', 'none']` pentru robustețe când API e down (vezi lecția #35).

### Utility meters (`utility_meters.yaml`)

Path: `/home/cristi/server/homeassistant/utility_meters.yaml`, incluse via `utility_meter: !include utility_meters.yaml`.

Cycles `daily/monthly/yearly` pentru:
- `productie_*` (sursă `sensor.deye_total_production`)
- `consum_*` (sursă `sensor.deye_today_load_consumption`)
- `import_grid_*` (sursă `sensor.deye_total_energy_import`)
- `export_grid_*` (sursă `sensor.deye_total_energy_export`)
- `recuperat_lifetime` (yearly cu sursă `sensor.economie_totala_azi`)

### Tracking forecast vs real

#### Helpers

| Entity ID | Friendly Name | Salvat de |
|-----------|---------------|-----------|
| `input_number.forecast_initial_al_zilei` | Forecast inițial al zilei | Automation 07:00 din `sensor.energy_production_today` |
| `input_number.productie_finala_a_zilei` | Producție finală a zilei | Automation 23:55 din `sensor.deye_today_production` |

**ATENȚIE LOGICĂ:** valorile reprezintă ziua **curentă** la momentul salvării, NU ziua precedentă.

#### Automation `📊 Salvare forecast vs real zilnic` (ID 1780645409503)

```yaml
- id: '1780645409503'
  alias: "📊 Salvare forecast vs real zilnic"
  description: Estimat dimineața (predictie pură), real seara
  triggers:
    - trigger: time
      at: "07:00:00"
      id: estimat
    - trigger: time
      at: "23:55:00"
      id: real
  actions:
    - choose:
        - conditions:
            - condition: trigger
              id: estimat
            - condition: numeric_state
              entity_id: sensor.energy_production_today
              above: 1
          sequence:
            - action: input_number.set_value
              target:
                entity_id: input_number.forecast_initial_al_zilei
              data:
                value: "{{ states('sensor.energy_production_today') | float(0) }}"
        - conditions:
            - condition: trigger
              id: real
            - condition: numeric_state
              entity_id: sensor.deye_today_production
              above: 1
          sequence:
            - action: input_number.set_value
              target:
                entity_id: input_number.productie_finala_a_zilei
              data:
                value: "{{ states('sensor.deye_today_production') | float(0) }}"
  mode: single
```

**Condition `numeric_state above: 1`** previne salvarea valorii 0 când senzorul e `unknown`/`unavailable` la trigger (ex: după reboot 04:30, înainte ca Forecast.Solar să primească date). Dacă condition nu e îndeplinită, automation skip-ează și valoarea veche rămâne în helper (vezi lecția #37).

#### Automation `🔄 Forecast.Solar reload orar` (ID 1781000000001)

```yaml
- id: '1781000000001'
  alias: 🔄 Forecast.Solar reload orar
  description: Reload integrarea Forecast.Solar la fiecare oră pentru date proaspete
  triggers:
    - trigger: time_pattern
      minutes: '5'
  actions:
    - action: homeassistant.reload_config_entry
      data:
        entry_id: 01KT5WDFBEXVBZVMJT4DYSEHDJ
  mode: single
```

Forțează reload integrare la fiecare minut 5 al orei (07:05, 08:05, ...). Recovery automat după erori network/server `api.forecast.solar` (vezi lecția #35).

#### Automation `Deye - notificare problemă` (ID 1780387870369)

Triggers:
- `binary_sensor.deye_battery_alarm` → on
- `binary_sensor.deye_battery_fault` → on
- `binary_sensor.deye_connection` → off for 5 min
- `sensor.deye_device_state` → Fault
- `sensor.deye_battery_temperature` > 50°C
- `sensor.deye_temperature` > 75°C
- `sensor.deye_battery_soh` < 85%

Action: `persistent_notification.create` cu detaliile event-ului.

### Recorder configuration

```yaml
recorder:
  purge_keep_days: 90
  commit_interval: 30
  include:
    entity_globs:
      - sensor.deye_today_*
      - sensor.deye_total_*
      - sensor.deye_pv_power
      - sensor.deye_battery
      - sensor.deye_load_power
      - sensor.deye_grid_power
      - sensor.deye_battery_power
      - sensor.energy_*
      - sensor.power_production_*
      - sensor.power_highest_*
      - sensor.forecast_*
      - sensor.productie_*
      - sensor.consum_*
      - sensor.export_grid_*
      - sensor.import_grid_*
      - sensor.economie_*
      - sensor.recuperat_*
      - sensor.ramas_de_*
      - sensor.procent_amortizat
      - sensor.viata_baterie_*
      - sensor.zile_pana_*
      - sensor.ani_pana_*
      - sensor.cost_evitat_*
      - sensor.castig_export_*
      - input_number.*
      - binary_sensor.deye_*
      - sensor.deye_device_*
    entities:
      - sensor.grid_import_power
      - sensor.grid_export_power
      - sensor.battery_charging_power
      - sensor.battery_discharging_power
```

**IMPORTANT:** pattern-ul `input_number.*` e CRITIC pentru tracking-ul forecast. Fără el, salvările automation nu apar în recorder → nu apar în grafice (vezi lecția #31).

### Dashboard solar — layout final (10 iunie)

URL: http://192.168.68.200:8123/dashboard-solar/0

**Layout 3 coloane (Sections view):**

#### Header row (4 chips)
- **Zalău** (weather, Sunny / Partly cloudy etc.)
- **PV: W** + Consum: W
- **Baterie: %** + W charging/discharging
- **Grid: W** + direction (import/export)

#### Coloana 1 (stânga, principale)

1. **Situația actuală** (card consolidat — vezi mai jos)
2. **Acuratețe forecast** (entities)
3. **Status invertor** (entities)

#### Coloana 2 (centru)

1. **Forecast vs Real — săptămâna** (apex column, 7d)
2. **Temperaturi & sănătate baterie** (entities)

#### Coloana 3 (dreapta — financiar)

1. **Energie & financiar** (card mare cu 4 subgrupuri: Astăzi, Luna curenta, An 2026, Amortizare)

#### Card "Situația actuală" — NOU 10 iunie

Consolidare 4 metrici (Producție PV, Export grid, Consum casă, Import grid) într-un singur card cu apex line chart combinat:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Situația actuală
  show_states: true
  colorize_states: true
graph_span: 24h
span:
  start: day
update_interval: 30s
yaxis:
  - id: kwh
    min: 0
    max: 70
apex_config:
  chart:
    height: 280
  stroke:
    width: 2
  legend:
    show: true
    position: bottom
series:
  - entity: sensor.deye_today_production
    name: Producție PV
    color: "#f59e0b"
    yaxis_id: kwh
    transform: "return x > 25 && new Date().getHours() < 4 ? null : x;"
  - entity: sensor.deye_today_energy_export
    name: Export grid
    color: "#3b82f6"
    yaxis_id: kwh
  - entity: sensor.deye_today_load_consumption
    name: Consum casă
    color: "#a855f7"
    yaxis_id: kwh
  - entity: sensor.deye_today_energy_import
    name: Import grid
    color: "#ef4444"
    yaxis_id: kwh
```

Avantaj vs. 2 carduri separate: economie spațiu, comparație rapidă PV vs Consum în același grafic, citire instantanee a self-sufficiency.

#### Card "Forecast vs Real — săptămâna" YAML

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: 📊 Forecast vs Real — săptămâna
  show_states: true
  colorize_states: true
graph_span: 7d
span:
  end: day
update_interval: 1m
yaxis:
  - id: kwh
    min: 0
    max: 70
    decimals: 1
apex_config:
  chart:
    height: 280
  plotOptions:
    bar:
      columnWidth: 50%
  dataLabels:
    enabled: true
    offsetY: -20
  legend:
    show: true
    position: bottom
  xaxis:
    type: datetime
    labels:
      datetimeFormatter:
        day: "dd MMM"
series:
  - entity: input_number.forecast_initial_al_zilei
    name: Estimat
    type: column
    color: "#3b82f6"
    yaxis_id: kwh
    group_by:
      func: last
      duration: 1d
    show:
      datalabels: true
  - entity: sensor.deye_today_production
    name: Real
    type: column
    color: "#f59e0b"
    yaxis_id: kwh
    group_by:
      func: last
      duration: 1d
    show:
      datalabels: true
```

#### Card "Acuratețe forecast" — SIMPLIFICAT 10 iunie

Combină toate metricile forecast într-un singur card entities, eliminând secțiunea "Mâine" separată:

```yaml
type: entities
title: 🎯 Acuratețe forecast
state_color: true
entities:
  - entity: sensor.forecast_accuracy_azi
    name: Real vs estimat
    icon: mdi:target
  - entity: sensor.forecast_diferenta_azi
    name: Diferență (kWh)
    icon: mdi:scale-balance
  - entity: sensor.forecast_eficienta_kwp
    name: Eficiență per kWp
    icon: mdi:solar-panel
  - type: divider
  - entity: sensor.deye_today_production
    name: Real produs azi
    icon: mdi:flash-outline
  - entity: sensor.energy_production_today
    name: Estimat azi
    icon: mdi:flash
  - entity: sensor.energy_production_tomorrow
    name: Estimat mâine
    icon: mdi:flash
```

Avantaj vs. variantă anterioară: un singur card, 6 entități în loc de 5+secțiune separată, mai compact, story progressive (acuratețe → valori azi → predictie mâine).

#### Card "Energie & financiar"

Card mare în coloana dreapta cu 4 subgrupuri (toate utility_meters + senzori financiar):

- **Astăzi:** Producție, Consum, Export grid, Economie totală (cu sub: Cost evitat + Câștig export)
- **Luna curenta:** Producție, Consum, Import, Export, Economie, Medie/zi
- **An 2026:** Producție, Consum, Export, Economie
- **Amortizare:** Recuperat total, Rămas de recuperat, % amortizat, Zile rămase

### Energy Dashboard built-in HA

Configurat cu:
- **Solar production:** `sensor.deye_total_production`
- **Grid consumption:** `sensor.deye_total_energy_import`
- **Return to grid:** `sensor.deye_total_energy_export`
- **Battery charge:** `sensor.deye_today_battery_charge`
- **Battery discharge:** `sensor.deye_today_battery_discharge`

Tarife (TODO ajustare):
- Consumed energy: 1.10 RON/kWh
- Returned energy: 0.40 RON/kWh

---

## Stack Zigbee (oprit temporar 2026-06-01)

**Status:** containerul `zigbee2mqtt` oprit cu `restart: no`, dongle Sonoff fizic deconectat. Motiv: hardware USB defect cauzează cascade USB→systemd. Va fi repornit după migrare pe hardware nou sau cu hub powered.

### Configurație existentă

- **Coordinator:** Sonoff Dongle Plus MG24
- **By-id symlink:** `/dev/serial/by-id/usb-SONOFF_SONOFF_Dongle_Plus_MG24_3cde9ae64ca3ef11968046bd61ce3355-if00-port0`
- **MQTT:** publică pe `zigbee2mqtt/#` în mosquitto, HA prin Discovery
- **Port frontend:** 8099

### Pentru reactivare

```bash
lsusb | grep -i sonoff
ls /dev/serial/by-id/ | grep -i sonoff
docker start zigbee2mqtt
docker update --restart=always zigbee2mqtt
docker logs --tail 30 zigbee2mqtt
```

---

## Configurare critică

### Docker daemon (`/etc/docker/daemon.json`)

```json
{
  "exec-opts": ["native.cgroupdriver=cgroupfs"],
  "dns": ["192.168.68.200", "1.1.1.1"]
}
```

### GRUB cmdline (`/etc/default/grub`)

```
GRUB_CMDLINE_LINUX_DEFAULT="pci=noaer usbcore.autosuspend=-1"
```

Apoi `sudo update-grub`. Reduce spam USB events (lecția #22).

### Pi-hole binding (`docker-compose.yml`)

```yaml
ports:
  - "192.168.68.200:53:53/tcp"
  - "100.113.68.25:53:53/tcp"
  - "192.168.68.200:53:53/udp"
  - "100.113.68.25:53:53/udp"
  - "8082:80/tcp"
```

### systemd-resolved drop-in

```ini
[Resolve]
DNS=192.168.68.200
FallbackDNS=1.1.1.1 1.0.0.1
DNSStubListener=yes
```

### HA container extra_hosts (pentru homepage widget)

```yaml
homeassistant:
  extra_hosts:
    - "host.docker.internal:host-gateway"
```

---

## Cron jobs

```cron
0 4 1 * *  /home/cristi/scripts/system-cleanup.sh >> /home/cristi/scripts/cleanup.log 2>&1
0 3 * * 0  /home/cristi/backups/backup-docker.sh
0 5 * * 0  /home/cristi/scripts/git-backup-config.sh
0 4 * * *  docker run --rm -v /home/cristi/server/clamav/db:/var/lib/clamav clamav/clamav:stable freshclam >> /home/cristi/clamav-update.log 2>&1
30 4 * * * /sbin/shutdown -r now
```

**Notă reboot zilnic:** workaround pentru D-Bus stuck cauzat de USB errors hardware (vezi lecția #22).

---

## Pi-hole

### DNS local pentru `.lan`

- `pihole.lan → 192.168.68.200`
- `ha.lan → 192.168.68.200`
- `home.lan → 192.168.68.200`
- `jellyfin.lan → 192.168.68.200`
- `homepc → 192.168.68.200`

### Widget homepage Pi-hole

```yaml
- Pi-hole:
    icon: pi-hole
    href: http://192.168.68.200:8082/admin
    server: my-docker
    container: pihole
    widget:
      type: pihole
      url: http://192.168.68.200:8082
      version: 6
```

---

## Tailscale

- homepc UP (100.113.68.25)
- MagicDNS activ
- Subnet route 192.168.68.0/24 aprobată
- iPhone Companion HA via `http://homepc:8123` sau Tailscale FQDN
- Split DNS pentru `.lan` — TODO
- ACLs pentru izolare iPhone vs PC — TODO

---

## Lecții acumulate

1. **Pi-hole nu pe `0.0.0.0:53`** — bind explicit pe IP-uri specifice.
2. **Bind mounts > Docker volumes** pentru date critice.
3. **Cabluri Ethernet vechi** pot da throughput slab chiar la Gigabit negociat.
4. **`apt purge containerd` cu Docker activ** → distruge `/var/lib/docker/`.
5. **`restart: always`** pentru auto-boot reliable după power failure.
6. **Cgroup v2 default** Ubuntu 24 — fără `systemd.unified_cgroup_hierarchy=0`.
7. **Docker `cgroupfs` driver** evită bug paralel container start.
8. **Restart ordonat: modem → router → switch → device.**
9. **SysRq fallback** când `sudo reboot` nu merge.
10. **M4R ~360 Mbps NAT sustained** — hardware limit.
11. **docker-socket-proxy** > mount direct docker.sock.
12. **mosquitto port `1883:1883` fără IP explicit** — HA cu host network se conectează via localhost.
13. **MQTT în HA modern** se configurează DOAR din UI, nu în configuration.yaml.
14. **HA Energy Dashboard** cere statistici acumulate — senzorii noi nu apar imediat în dropdown.
15. **Entity ID-urile din MQTT Discovery** pot diferi de numele topic-ului.
16. **docker compose ports cu ghilimele și IP** dă `must be a number` — folosește `- 1883:1883`.
17. **LSW-5 firmware nou** (LSW5_32_5406_SS_04) nu suportă pull Modbus local — folosește integrarea Solarman din HACS care comunică direct via SolarmanV5.
18. **Topologie mesh în serie** (M4R→M4R→M4R) înjumătățește throughput — folosește topologie stea din switch.
19. **ISP NextPower blochează porturile incoming** — port forwarding pentru qBittorrent nu funcționează.
20. **Pi-hole pe LAN intern: fără parolă > workaround SID** — `pihole setpassword ""` elimină complet nevoia de cron + SID refresh pentru widget homepage.
21. **USB dongle în docker: `/dev/ttyUSB0` e fragil** — folosește symlink stabil `/dev/serial/by-id/...`.
22. **USB porturi defecte permanent pe homepc** — porturile spate generează over-current. Workarounds: porturi front + GRUB `pci=noaer usbcore.autosuspend=-1` + cron reboot 04:30. Plan upgrade mini PC second-hand.
23. **USB hub passive ca workaround porturi defecte** — Genesys Logic chipset, consolidează device-uri în port front singur funcțional.
24. **Auth bypass pentru LAN intern (Sonarr/Radarr v4+)** — `Authentication Method: Forms` + `Authentication Required: Disabled for Local Addresses`.
25. **Filebrowser auth scoasă** — `noauth` method via CLI cu container oprit (lock pe `/database.db`).
26. **ClamAV daemon vs on-demand pe RAM scăzut** — on-demand singura opțiune viabilă pe 4GB RAM: 0 MB idle, ~1.1 GB peak pentru 28-90 sec.
27. **qBittorrent post-download hook din container nu poate apela docker pe host** — `inotifywait` pe host care monitorizează `/downloads/complete/` și apelează `docker run` direct.
28. **`sed -i` fără backup pe configuration.yaml = sinucidere config** — workflow OBLIGATORIU: `cp configuration.yaml configuration.yaml.bak-$(date +%Y%m%d-%H%M%S)` PRIMUL. Apoi `wc -l` (nu sub 200) + `docker exec homeassistant python -m homeassistant --script check_config -c /config`. Backup-urile cu nume descriptive (ex `bak-recorder-0753`) pot fi înșelătoare — verifică DIMENSIUNEA să fie similară cu originalul.
29. **Forecast.Solar e ADAPTIV (update la 30 min meteo)** — predictia zilei curente se ajustează continuu cu meteo live. Pentru tracking estimat-vs-real meaningful: salvează snapshot DIMINEAȚA (07:00, predictie INIȚIALĂ) vs REAL la 23:55.
30. **Template sensors HA: `| int` sau `| float` fără default = crash la pornire** — când entitatea sursă e `unknown` la boot HA, filtrul aruncă `ValueError`. Fix: `| int(0)` sau `| float(0)`. Pentru template-uri care depind de senzori externi care pot deveni `unavailable` (ex Forecast.Solar): verifică `if estimat in ['unavailable', 'unknown', 'none']` înainte de `| float`.
31. **HA recorder include = critic pentru grafice istorice** — entitățile NU în `recorder.include` nu sunt salvate. Pattern obligatoriu pentru solar: `input_number.*`, `sensor.deye_total_*`, `sensor.energy_*`.
32. **HA `home-assistant_v2.db` editing live = risky, oprit = OK** — pentru curățare istoric: `docker stop homeassistant`, backup DB, `sudo python3` cu sqlite3. Format timestamp UTC, convertește local→UTC manual.
33. **Apex Charts `group_by` și timezone** — `duration: 1d` face fereastra pe bază UTC, nu local. Pentru sensori cu reset zilnic la 00:00 local, folosește `func: last duration: 1d` care prinde ultima valoare înainte de reset. NU folosi `func: max` — prinde valoarea fantomă din primele minute UTC.
34. **HA entity rename păstrează istoricul recorder** — Settings → Devices → Helpers → click entitate → settings → modify entity_id. Cardurile dashboard NU se updatează automat — find-and-replace separat în `.storage/lovelace.*` cu `sudo sed`. Diacriticele românești sunt eliminate automat din entity_id la salvare.
35. **Forecast.Solar API gratuit (public, fără key) e intermitent** — `Cannot connect to host api.forecast.solar:443` și `Server disconnected` apar zilnic. API key gratuit nu mai e oferit pentru utilizatori noi. Workaround: automation HA cu `homeassistant.reload_config_entry` triggat `time_pattern minutes: '5'` (la fiecare oră) — forțează reload care reconectează API.
36. **Forecast.Solar calibrare empirică pentru match real production** — API e sistematic pesimist sau optimist în funcție de instalare. Rulează tracking 5-7 zile, calculează eroare medie, ajustează `Modules power` cu factor. Exemplu Zalău 8.75kWp: setări 9000W → real cu 36% peste estimat → ajustat la 11500W → ziua următoare diferență 0.6%. Atenție: calibrare PESTE kWp real compensează pierderile API, nu schimbarea fizică a hardware.
37. **Automation HA cu trigger.id și `choose`: nu rulează la "Trigger manually"** — când lansezi automation cu `automation.trigger` fără `skip_condition`, `trigger.id` e null și `choose` cu `condition: trigger id: X` nu match-uiește. PROTECȚIE: adaugă `condition: numeric_state above: 1` pe entitatea sursă în fiecare branch `choose` — previne salvare valori 0 când senzorul e `unknown` la trigger.
38. **Reboot zilnic 04:30 + automation 07:00 = race condition potențial** — HA pornește la 04:35 local, dar Forecast.Solar API poate să nu fi returnat încă valori la 07:00. Soluții: (a) condition `numeric_state above: 1` pe sensor (skip dacă nu e ready), (b) mută trigger la 08:00 (2h buffer), (c) adaugă automation reload integration la pornire HA. Combinația condition + reload orar previne salvarea 0 în helper-e.
39. **Dashboard cards: consolidare metrici live într-un grafic combinat e mai eficient decât 2 carduri separate** — pentru info în timp real (Producție PV, Export grid, Consum casă, Import grid în aceeași unitate kWh), un singur apex line chart cu 4 serii oferă comparație instantanee a self-sufficiency. Citirea "PV peste consum = exportăm" e mai rapidă decât scanare a 2 carduri laterale. Aplicabil când metricile sunt corelate logic (energie zilnică, putere instant, temperaturi multiple). NU recomandat pentru metrici eterogene (ex temp + voltaj + cicluri — fiecare cu altă unitate/scală).

---

## Comenzi utile

### Solar / HA

```bash
# Status containere solar
docker ps | grep -E "mosquitto|homeassistant"

# Logs HA (live)
docker logs --since 30s homeassistant
docker logs --since 5m homeassistant 2>&1 | grep -iE "error|template|forecast_solar" | tail -20

# Validare config înainte de restart
docker exec homeassistant python -m homeassistant --script check_config -c /config 2>&1 | tail -5

# Restart HA
docker restart homeassistant

# Backup OBLIGATORIU înainte de sed
cp /home/cristi/server/homeassistant/configuration.yaml \
   /home/cristi/server/homeassistant/configuration.yaml.bak-$(date +%Y%m%d-%H%M%S)

# Verifică valoarea live unei entități
TOKEN='<long-lived-token>'
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8123/api/states/input_number.forecast_initial_al_zilei | python3 -m json.tool

# Forțează reload Forecast.Solar manual
curl -X POST http://localhost:8123/api/services/automation/trigger \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "automation.forecast_solar_reload_orar"}'

# Set manual o entitate input_number
curl -X POST http://localhost:8123/api/services/input_number/set_value \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "input_number.X", "value": 23.5}'

# Verifică istoricul recorder pentru o entitate
python3 << 'EOF'
import sqlite3, datetime
conn = sqlite3.connect('/home/cristi/server/homeassistant/home-assistant_v2.db')
cur = conn.cursor()
cur.execute("""
    SELECT date(s.last_updated_ts, 'unixepoch', 'localtime') zi,
           MAX(CAST(s.state AS REAL)) max_v, COUNT(*) nr
    FROM states s
    JOIN states_meta m ON s.metadata_id = m.metadata_id
    WHERE m.entity_id = 'sensor.deye_today_production'
    AND s.state NOT IN ('unknown', 'unavailable')
    GROUP BY zi ORDER BY zi DESC LIMIT 7
""")
for row in cur.fetchall():
    print(row)
EOF

# Fix tipic template errors în dashboard
docker stop homeassistant
sudo sed -i "s#deye_pv_power') | int #deye_pv_power') | int(0) #g" \
  /home/cristi/server/homeassistant/.storage/lovelace.dashboard_solar
docker start homeassistant
```

### ClamAV / antivirus

```bash
# Status watcher
sudo systemctl status qbit-watch --no-pager

# Test EICAR
mkdir -p /home/cristi/server/downloads/incomplete/test
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' \
  > /home/cristi/server/downloads/incomplete/test/v.txt
mv /home/cristi/server/downloads/incomplete/test /home/cristi/server/downloads/complete/
tail -f /home/cristi/qbit-scan.log

# Update signaturi manual
docker run --rm -v /home/cristi/server/clamav/db:/var/lib/clamav \
  clamav/clamav:stable freshclam

# Scan ad-hoc
docker run --rm --entrypoint clamscan \
  -v /home/cristi/server/clamav/db:/var/lib/clamav:ro \
  -v /home/cristi/server/downloads:/scan:ro \
  clamav/clamav:stable -r --no-summary /scan/complete
```

### USB diagnostic

```bash
lsusb
lsusb -t
sudo journalctl --since "1 week ago" | grep -c over-current
sudo journalctl --no-pager --since "5 minutes ago" | grep -iE "usb|over-current" | tail -20
```

### General

```bash
sudo systemctl is-system-running
docker ps --format 'table {{.Names}}\t{{.Status}}'
df -h / && free -h && uptime
curl -o /dev/null http://ipv4.download.thinkbroadband.com/100MB.zip
ip -s link show enp2s0 | grep -A1 "RX:"
```

---

## Action items pending

- [ ] Monitorizare 5-7 zile calibrare Forecast.Solar (11500W) — verdict 15-16 iunie
- [ ] Tarife în Energy Dashboard (1.10 import / 0.40 export) pentru afișare RON
- [ ] Backup zilnic HA programat în Settings → System → Backups
- [ ] Investigare Sonarr (nu mai găsește seriale cerute) — verificare Prowlarr indexers
- [ ] Split DNS Tailscale pentru `.lan`
- [ ] ACLs Tailscale izolare iPhone vs PC
- [ ] Upgrade hardware mini PC second-hand (Lenovo M73 Tiny / Dell OptiPlex Micro / HP EliteDesk Mini, ~250-400 RON)
- [ ] Reactivare Zigbee2MQTT după upgrade hardware

---

## Plan upgrade hardware (în lucru)

**Opțiuni evaluate:**

- **Card PCIe USB 3.0** (~80-150 RON) — fix mediu, depinde de slot PCIe liber
- **Mini PC second-hand** (~250-400 RON) — soluție definitivă, recomandată
  - Lenovo ThinkCentre M73/M93p Tiny (Intel i5, 8-16GB RAM)
  - Dell OptiPlex 3050/5050 Micro
  - HP EliteDesk 800 G2/G3 Mini
- **Backup strategy migrare:** `rsync /home/cristi/server/` + Docker install + `docker compose up -d` ≈ 30 min

---

## Contact / referințe

- **GitHub backup repo:** github.com:12Cristi/homelab-config (privat)
- **Pi-hole admin:** http://192.168.68.200:8082
- **Homepage:** http://192.168.68.200:3000
- **Home Assistant:** http://192.168.68.200:8123
- **HA Solar dashboard:** http://192.168.68.200:8123/dashboard-solar/0
- **HA Energy Dashboard:** http://192.168.68.200:8123/energy
- **Zigbee2MQTT:** http://192.168.68.200:8099 (oprit temporar)
- **Filebrowser:** http://192.168.68.200:8090 (noauth)
- **Logger LSW-5 admin:** http://192.168.68.101
- **Tailscale admin:** https://login.tailscale.com/admin
- **Solarman HACS integration:** https://github.com/davidrapan/ha-solarman
- **Forecast.Solar API:** https://doc.forecast.solar/

---

*19 mai 2026: Logger fizic LSW-5 conectat, integrare Solarman HACS funcțională. Stack solar complet operațional.*

*22 mai 2026: Pi-hole fără parolă + widget homepage nativ. Stack Zigbee adăugat, 0 device-uri pairing încă.*

*1 iunie 2026: Auth cleanup (Filebrowser noauth, Sonarr/Radarr Disabled for Local). Pi-hole blocklists Tier 1+2+3 (block rate 30% → ~15-20%). ClamAV antivirus stack operațional. Hardware USB diagnostic — 4 porturi spate defecte permanent. Zigbee oprit temporar. Plan upgrade mini PC second-hand luna asta.*

*5 iunie 2026: Recorder extins cu pattern-uri pentru Forecast.Solar, template sensors financiar, utility meters, input_number. Forecast.Solar integration activă cu 8750W kWp inițial. Template sensors pentru acuratețe forecast (după 19:00). Apex Charts cu transform spike 00:00.*

*6 iunie 2026: Dashboard solar v2 complet — 9 carduri. Helpers redenumite cu nume corecte. Automation 07:00/23:55 cu trigger.id. Restore configuration.yaml din backup după tăiere accidentală sed. SQL cleanup manual pentru valori istorice greșite.*

*8 iunie 2026: Adăugat condition `numeric_state above: 1` pe automation pentru protecție valori 0. Fix trigger 06:00 → 07:00. Automation `Forecast.Solar reload orar` adăugată pentru workaround API intermitent.*

*9 iunie 2026: Calibrare empirică Forecast.Solar după 5 zile date — Modules power 9000W → 11500W. Validare ziua 9 iunie: estimat 54.6 vs real 54.9 (diferență 0.6%). Producție săptămânală 222.2 kWh, eficiență medie 5.08 kWh/kWp/zi. Lecții noi #35-#38.*

*10 iunie 2026: Dashboard rafinat — layout 3 coloane Sections view. Consolidare 4 metrici live într-un singur card "Situația actuală" cu apex line chart combinat (Producție PV, Export grid, Consum casă, Import grid). Card "Acuratețe forecast" simplificat (eliminat secțiunea separată "Mâine", adăugat `Estimat mâine` la sfârșit). Lecția #39 — design carduri cu metrici corelate. Documentație v4 finalizată și pushed la git.*
