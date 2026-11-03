import json, os, urllib.request, urllib.error, time

KEY=os.environ.get('ZOTERO') or os.environ['ZOTERO_API_KEY']
BASE='https://api.zotero.org/groups/2412036/items/'
INCOMING='V4WXTY8M'
PODCASTED='6P2KVFKQ'

import pathlib
ROOT=pathlib.Path(__file__).resolve().parent
manifest=json.load(open(ROOT/'manifest.json'))
state=json.load(open(ROOT/'state.json'))
SOURCES=[]
for num, episode in manifest['episodes'].items():
 # The durable ledger, not the manifest, records whether the episode shipped.
 if state.get('episodes', {}).get(num, {}).get('status') == 'published':
  SOURCES.extend(episode.get('sources', []))
def get(k):
 req=urllib.request.Request(BASE+k,headers={'Zotero-API-Key':KEY})
 with urllib.request.urlopen(req) as r: return json.load(r)
def put(k, obj, version):
 body=json.dumps(obj['data']).encode()
 req=urllib.request.Request(BASE+k,data=body,method='PUT',headers={'Zotero-API-Key':KEY,'Content-Type':'application/json','If-Unmodified-Since-Version':str(version)})
 with urllib.request.urlopen(req) as r: return r.status, r.headers.get('Zotero-Library-Version')
results=[]
for k in SOURCES:
 for attempt in range(4):
  obj=get(k); d=obj['data']; old=list(d.get('collections') or [])
  new=[c for c in old if c!=INCOMING]
  if PODCASTED not in new: new.append(PODCASTED)
  if new==old:
   results.append({'key':k,'status':'already-moved','version':obj['version'],'collections':old}); break
  d['collections']=new
  try:
   status,ver=put(k,obj,obj['version']); results.append({'key':k,'status':'moved','from_version':obj['version'],'to_version':ver,'collections':new}); break
  except urllib.error.HTTPError as e:
   if e.code in (409,412):
    if attempt==3: raise
    time.sleep(1+attempt); continue
   raise
print(json.dumps(results,indent=2))
open('/data/.openclaw/workspace/media/zotero-podcast/pipeline/move-results.json','w').write(json.dumps(results,indent=2)+'\n')
