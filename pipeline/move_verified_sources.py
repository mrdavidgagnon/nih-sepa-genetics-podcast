import json, os, urllib.request, urllib.error, time

KEY=os.environ.get('ZOTERO') or os.environ['ZOTERO_API_KEY']
BASE='https://api.zotero.org/groups/2412036/items/'
INCOMING='V4WXTY8M'
READ='DV6F4ILX'
PODCASTED='6P2KVFKQ'
# Both intake lanes are stripped on a move. A reading's source key lives in
# Read, not Summerize; leaving that membership in place makes `read_lane.py
# zotero-read` re-offer a paper that has already been published as a reading.
LANES=(INCOMING, READ)

import pathlib
ROOT=pathlib.Path(__file__).resolve().parent
manifest=json.load(open(ROOT/'manifest.json'))
state=json.load(open(ROOT/'state.json'))
SOURCES=[]
for num, episode in manifest['episodes'].items():
 # The durable ledger, not the manifest, records whether the episode shipped.
 # Accept the whole published* family: 'published', the pre-move
 # 'published_pending_zotero_move' and the documented end state
 # 'published_and_moved'. A literal == 'published' silently skipped the last
 # two, so re-running the mover after a status bump moved nothing and still
 # exited 0 (same gate-string class as the run-005 interview_episodes() fix).
 if not str(state.get('episodes', {}).get(num, {}).get('status', '')).startswith('published'):
  continue
 # Interviews register their Zotero keys under 'sources'; read_lane.py
 # registers a reading's key under 'read_source' so preflight()'s interview
 # source-ownership model does not report a false duplicate. Reading only
 # 'sources' meant a published reading's source never reached Produced.
 for key in list(episode.get('sources', [])) + list(episode.get('read_source', [])):
  if key and key not in SOURCES:
   SOURCES.append(key)
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
  new=[c for c in old if c not in LANES]
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
open(ROOT/'move-results.json','w').write(json.dumps(results,indent=2)+'\n')
