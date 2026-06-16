#!/usr/bin/env python3
"""Audiobookshelf stats collector for Homepage widget."""
import os, json, ssl, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TOKEN = None
with open('/home/cristi/server/.env') as f:
    for line in f:
        if line.startswith('ABS_API_TOKEN='):
            TOKEN = line.split('=', 1)[1].strip()
            break

if not TOKEN:
    print("ERROR: ABS_API_TOKEN not found"); exit(1)

BASE = "https://audiobooks.stoica-homepc.duckdns.org"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

def api_get(path):
    req = urllib.request.Request(BASE + path, headers=HEADERS)
    with urllib.request.urlopen(req, context=CTX) as r:
        return json.loads(r.read())

def get_title(item):
    """Try multiple sources for the real book title."""
    # 1. Try metadata.title (often the author due to scanner bug)
    md = item.get('media', {}).get('metadata', {})
    
    # 2. Try path-based extraction: /books/Author/Author - Title
    path = item.get('path', '') or item.get('relPath', '')
    last_folder = path.rstrip('/').split('/')[-1]
    if ' - ' in last_folder:
        return last_folder.split(' - ', 1)[1]
    
    # 3. Fallback to metadata title
    return md.get('title') or 'Unknown'

users_resp = api_get("/api/users")
users = users_resp.get('users', users_resp) if isinstance(users_resp, dict) else users_resp

stats = []
for u in users:
    uid = u['id']; uname = u['username']
    detail = api_get(f"/api/users/{uid}")
    progress = detail.get('mediaProgress', [])
    
    active = [p for p in progress 
              if not p.get('isFinished') 
              and not p.get('hideFromContinueListening')
              and ((p.get('progress', 0) or 0) > 0 or (p.get('ebookProgress', 0) or 0) > 0)]
    finished = [p for p in progress if p.get('isFinished')]
    
    active_books = []
    for p in sorted(active, key=lambda x: x.get('lastUpdate', 0), reverse=True)[:3]:
        try:
            item = api_get(f"/api/items/{p['libraryItemId']}")
            title = get_title(item)
            pct_val = p.get('ebookProgress') if (p.get('ebookProgress') or 0) > 0 else p.get('progress', 0)
            prog_pct = round((pct_val or 0) * 100, 1)
            last = datetime.fromtimestamp(p['lastUpdate']/1000, tz=ZoneInfo('Europe/Bucharest')).strftime('%Y-%m-%d %H:%M')
            active_books.append({'title': title, 'progress': prog_pct, 'lastUpdate': last})
        except Exception as e:
            pass
    
    stats.append({
        'username': uname,
        'active_count': len(active),
        'finished_count': len(finished),
        'active_books': active_books,
    })

output = {
    'updated': datetime.now(ZoneInfo('Europe/Bucharest')).strftime('%Y-%m-%d %H:%M:%S'),
    'users': stats
}

# Write to both locations
import os
OUTPUTS = [
    '/home/cristi/server/homepage/config/custom-stats/abs.json',
    '/home/cristi/server/homeassistant/www/abs-stats.json',
]
for OUT in OUTPUTS:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Wrote stats for {len(stats)} users to {OUT}")
