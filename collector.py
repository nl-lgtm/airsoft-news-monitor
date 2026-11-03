import json, os, re, time, hashlib, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT=Path(__file__).parent
DATA=ROOT/'data'/'news.json'
SOURCES=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
now=datetime.now(timezone.utc)
state=json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else {'news':[],'checks':{}}
state.setdefault('news',[]); state.setdefault('checks',{})
seen={n['id'] for n in state['news']}
new_count=0
headers={'User-Agent':'Mozilla/5.0 (compatible; AirsoftNewsMonitor/0.3; +https://github.com/)'}
for s in SOURCES:
    name=s['name']; prev=state['checks'].get(name,{}).get('last_success')
    since=datetime.fromisoformat(prev.replace('Z','+00:00'))-timedelta(hours=12) if prev else now-timedelta(days=7)
    q=f'"{name}" (airsoft OR GBB OR AEG OR HPA OR replica OR launch OR release OR preorder)'
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'en-US','gl':'US','ceid':'US:en'})
    try:
        req=urllib.request.Request(url,headers=headers)
        with urllib.request.urlopen(req,timeout=25) as r: raw=r.read(3_000_000)
        root=ET.fromstring(raw)
        items=root.findall('./channel/item')
        count=0
        for item in items:
            title=(item.findtext('title') or '').strip()
            link=(item.findtext('link') or '').strip()
            pub=item.findtext('pubDate') or ''
            if not title or not link: continue
            try: dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
            except Exception: continue
            if dt < since or dt > now+timedelta(days=1): continue
            id=hashlib.sha256(link.encode()).hexdigest()[:20]
            if id in seen: continue
            seen.add(id)
            state['news'].append({'id':id,'brand':name,'title':title,'url':link,'published':dt.isoformat(),'discovered':now.isoformat(),'status':'new'})
            count+=1; new_count+=1
        state['checks'][name]={'last_success':now.isoformat(),'last_count':count,'error':None}
        print(f'{name}: +{count}')
    except Exception as exc:
        # Keep last_success unchanged on failures.
        state['checks'][name]={'last_success':prev,'last_count':0,'error':str(exc)[:250]}
        print(f'{name}: ERROR {exc}')
    time.sleep(0.3)
state['news']=sorted(state['news'],key=lambda n:n['published'],reverse=True)[:2500]
state['last_run']=now.isoformat()
DATA.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'New: {new_count}; total: {len(state["news"])}')
