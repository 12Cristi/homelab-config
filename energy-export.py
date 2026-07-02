#!/usr/bin/env python3
"""Export energie lunar/anual din HA statistics DB."""
import sqlite3
import csv
from datetime import datetime, timedelta, date
import os

DB = '/home/cristi/server/homeassistant/home-assistant_v2.db'
OUT_CSV = '/home/cristi/exports/energie-lunar.csv'

# Tarife RON
RON_IMPORT = 1.156  # cumpărare
RON_EXPORT = 0.45  # vânzare

# Data start prosumator
PROSUMATOR_START = date(2026, 6, 12)

SENSORS = {
    'productie': 'sensor.deye_total_production',
    'consum': 'sensor.deye_total_load_consumption',
    'import': 'sensor.deye_total_energy_import',
    'export': 'sensor.deye_total_energy_export',
}

def get_value_at(conn, sensor_id, target_ts, direction='start'):
    """Get state at specific timestamp.
    direction='start': first value >= target_ts (period start)
    direction='end': last value <= target_ts (period end)
    """
    c = conn.cursor()
    if direction == 'start':
        c.execute("""
            SELECT s.state, s.sum
            FROM statistics_meta sm
            JOIN statistics s ON s.metadata_id = sm.id
            WHERE sm.statistic_id = ? AND s.start_ts >= ?
            ORDER BY s.start_ts ASC LIMIT 1
        """, (sensor_id, target_ts))
    else:  # end
        c.execute("""
            SELECT s.state, s.sum
            FROM statistics_meta sm
            JOIN statistics s ON s.metadata_id = sm.id
            WHERE sm.statistic_id = ? AND s.start_ts <= ?
            ORDER BY s.start_ts DESC LIMIT 1
        """, (sensor_id, target_ts))
    row = c.fetchone()
    return row[0] if row else None

def month_range(year, month, start_override=None):
    """First and last day of month, as datetimes."""
    if start_override and start_override.year == year and start_override.month == month:
        start = datetime.combine(start_override, datetime.min.time())
    else:
        start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end

def main():
    conn = sqlite3.connect(DB)
    today = date.today()
    
    rows = []
    nr = 1
    
    # Iterate from prosumator start month to current month
    cur = date(PROSUMATOR_START.year, PROSUMATOR_START.month, 1)
    while cur <= today:
        year, month = cur.year, cur.month
        start_dt, end_dt = month_range(year, month, PROSUMATOR_START)
        
        # Don't go beyond today for current month
        if end_dt > datetime.combine(today, datetime.max.time()):
            end_dt = datetime.now()
        
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()
        
        values = {}
        for name, sensor_id in SENSORS.items():
            v_start = get_value_at(conn, sensor_id, start_ts, 'start') or 0
            v_end = get_value_at(conn, sensor_id, end_ts, 'end') or v_start
            values[name] = round(v_end - v_start, 2)
        
        cost = round(values['import'] * RON_IMPORT - values['export'] * RON_EXPORT, 2)
        
        # Etichetă perioadă
        luna = cur.strftime('%b')
        an = cur.strftime('%Y')
        
        rows.append({
            'nr': nr,
            'luna': luna,
            'an': an,
            'productie': values['productie'],
            'consum': values['consum'],
            'import': values['import'],
            'export': values['export'],
            'cost_ron': cost,
        })
        nr += 1
        
        # Next month
        if month == 12:
            cur = date(year + 1, 1, 1)
        else:
            cur = date(year, month + 1, 1)
    
    # Total an current
    if rows:
        year_current = today.year
        year_rows = [r for r in rows if str(year_current) in r.get('an', '')]
        if year_rows:
            totals = {
                'nr': '',
                'luna': 'TOTAL',
                'an': str(year_current),
                'productie': round(sum(r['productie'] for r in year_rows), 2),
                'consum': round(sum(r['consum'] for r in year_rows), 2),
                'import': round(sum(r['import'] for r in year_rows), 2),
                'export': round(sum(r['export'] for r in year_rows), 2),
                'cost_ron': round(sum(r['cost_ron'] for r in year_rows), 2),
            }
            rows.append(totals)
    
    # Write CSV
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['nr', 'luna', 'an', 'productie', 'consum', 'import', 'export', 'cost_ron'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    
    # Write JSON for HA
    import json
    OUT_JSON = '/home/cristi/server/homeassistant/www/energy-export.json'
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json_data = {
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'rows': rows
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # Copy CSV to multiple locations
    import shutil
    os.makedirs('/home/cristi/server/exports', exist_ok=True)
    shutil.copy(OUT_CSV, '/home/cristi/server/exports/energie-lunar.csv')
    shutil.copy(OUT_CSV, '/home/cristi/server/homeassistant/www/energie-lunar.csv')
    conn.close()
    print(f"Exported {len(rows)} rows to {OUT_CSV}")
    print(f"Last update: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Show summary
    print("\n=== Summary ===")
    for r in rows:
        print(f"  {r['nr']:>3} {r.get('luna',''):8s} {r.get('an',''):6s} Prod={r['productie']:>8.2f} Cons={r['consum']:>8.2f} Imp={r['import']:>6.2f} Exp={r['export']:>8.2f} Cost={r['cost_ron']:>+8.2f} RON")

if __name__ == '__main__':
    main()
