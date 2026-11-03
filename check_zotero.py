import json, urllib.request
key = "XOjtqZGpXK7SiW7kduV1eTWD"
group_id = "2412036"
url = f"https://api.zotero.org/groups/{group_id}/collections/V4WXTY8M/items?format=json&limit=25"
req = urllib.request.Request(url)
req.add_header("Zotero-API-Key", key)
resp = urllib.request.urlopen(req, timeout=30)
total = int(resp.headers.get("X-Zotero-TotalResults", "0"))
lmv = resp.headers.get("Last-Modified-Version", "?")
data = json.loads(resp.read())
print(f"V4WXTY8M (Summerize): total={total} LMV={lmv}")
if isinstance(data, list) and data:
    for item in data:
        d = item.get("data", {})
        print(f"  KEY={item['key']} type={d.get('itemType')} title={repr(d.get('title','')[:80])}")
        print(f"    date={d.get('date','')} doi={d.get('DOI','')} url={d.get('url','')[:60]}")
else:
    print("  (no items)")
