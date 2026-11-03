import json, os, urllib.request, urllib.error, time

KEY=os.environ['ZOTERO']
BASE='https://api.zotero.org/groups/2412036/items/'
INCOMING='V4WXTY8M'
PODCASTED='6P2KVFKQ'

manifest=json.load(open('/data/.openclaw/workspace/media/zotero-podcast/pipeline/manifest.json'))
SOURCES=[]
for episode in manifest['episodes'].values():
 if episode.get('status') == 'published_pending_zotero_move':
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
