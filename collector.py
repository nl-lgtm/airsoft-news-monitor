import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / 'data' / 'news.json'
SOURCES = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
NOW = datetime.now(timezone.utc)
state = json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else {}
state.setdefault('news', [])
state.setdefault('checks', {})
seen = {n['id'] for n in state['news'] if 'id' in n}
new_count = 0
headers = {'User-Agent': 'Mozilla/5.0 (compatible; AirsoftNewsMonitor/0.4)'}

for source in SOURCES:
    name = source['name']
    previous = state['checks'].get(name, {})
    prior_success = previous.get('last_success')
    try:
        since = datetime.fromisoformat(prior_success.replace('Z', '+00:00')).astimezone(timezone.utc) - timedelta(hours=12) if prior_success else NOW - timedelta(days=7)
    except (ValueError, TypeError):
        since = NOW - timedelta(days=7)
    # Search the exact brand as well as the word airsoft to reduce false matches.
    query = f'"{name}" airsoft'
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read(3_000_000)
        root = ET.fromstring(raw)
        items = root.findall('./channel/item')
        added = 0
        old = 0
        malformed = 0
        duplicate = 0
        for item in items:
            title = (item.findtext('title') or '').strip()
            link = (item.findtext('link') or '').strip()
            published = (item.findtext('pubDate') or '').strip()
            if not title or not link or not published:
                malformed += 1
                continue
            try:
                date = parsedate_to_datetime(published).astimezone(timezone.utc)
            except (ValueError, TypeError):
                malformed += 1
                continue
            if date < since or date > NOW + timedelta(days=1):
                old += 1
                continue
            uid = hashlib.sha256(link.encode('utf-8')).hexdigest()[:20]
            if uid in seen:
                duplicate += 1
                continue
            seen.add(uid)
            state['news'].append({'id': uid, 'brand': name, 'title': title, 'url': link, 'published': date.isoformat(), 'discovered': NOW.isoformat(), 'status': 'new'})
            added += 1
            new_count += 1
        # An empty feed is not proof of successful coverage. Keep the old checkpoint.
        if items:
            state['checks'][name] = {'last_success': NOW.isoformat(), 'last_count': added, 'rss_items': len(items), 'error': None}
        else:
            state['checks'][name] = {'last_success': prior_success, 'last_count': 0, 'rss_items': 0, 'error': 'RSS returned 0 items; checkpoint preserved'}
        print(f'{name}: RSS={len(items)}, added={added}, old={old}, duplicates={duplicate}, invalid={malformed}', flush=True)
    except Exception as exc:
        state['checks'][name] = {'last_success': prior_success, 'last_count': 0, 'error': str(exc)[:250]}
        print(f'{name}: ERROR {exc}', flush=True)
    time.sleep(0.3)

state['news'] = sorted(state['news'], key=lambda n: n.get('published', ''), reverse=True)[:2500]
state['last_run'] = NOW.isoformat()
DATA.parent.mkdir(parents=True, exist_ok=True)
DATA.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'New: {new_count}; total: {len(state["news"])}', flush=True)
