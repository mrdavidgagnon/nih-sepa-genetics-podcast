"""Move published source parents out of their intake lane into Produced.

Version-guarded Zotero collection move covering BOTH production lanes of the
Moral Machines show:

  * interview episodes -- manifest ``sources``,     leaving Summerize (V4WXTY8M)
  * verbatim readings  -- manifest ``read_source``, leaving Read      (DV6F4ILX)

Both land in Produced (6P2KVFKQ).

ONLY THE EPISODE'S OWN INTAKE COLLECTION IS STRIPPED. This is load-bearing and
was the run-054 defect: the previous version held a single tuple of both intake
collection keys and removed both from every key it touched, with no notion of
which lane the episode came from. One interview plus one reading of the same
paper is LEGAL in this tree by design -- ``lane_ownership()`` keys ownership on
the field name
(``sources`` vs ``read_source``) precisely so the pairing is not a false
duplicate (run 033). So publishing the interview of a dual-use paper deleted the
Read membership that was the only durable record David wanted a reading of it,
de-queueing the reading before it was ever produced; and publishing the reading
deleted the pending Summerize membership the same way. Nothing reported it, and
a Zotero collection edit raises no deletion event, so the loss is
indistinguishable from David unfiling the item -- which is this show's
documented signal that he cleared the queue on purpose.

A dual-use key published in both lanes therefore yields two plan entries and
leaves each intake exactly once; every other collection membership, including
the parent ``YF84AUZK``, is preserved and no item is ever deleted.

Selection comes from the durable ledger (``state.json``) and accepts the whole
``published*`` family: ``published``, the pre-move
``published_pending_zotero_move`` and the documented end state
``published_and_moved``. A literal ``== 'published'`` silently skipped the last
two, so re-running the mover after a status bump moved nothing and still exited
0 -- the same gate-string class as the run-005 ``interview_episodes()`` fix
(run 011). Do not narrow this to the sibling tree's single pending status.

A reading must additionally be marked ``verified`` in
``pipeline/read-episodes.json``, so a source whose fidelity gate failed cannot
be moved. This script grants no gate of its own; it is the bookkeeping step that
runs after every publication check has already passed.

Usage::

    python3 pipeline/move_verified_sources.py            # perform the move
    python3 pipeline/move_verified_sources.py --dry-run   # report the plan only

The API key comes from ``ZOTERO``/``ZOTERO_API_KEY``, falling back to
``check_zotero.py`` then ``/opt/data/.env``. It is never printed.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://api.zotero.org/groups/2412036/items/'

SUMMERIZE = 'V4WXTY8M'   # interview intake
READ = 'DV6F4ILX'        # reading intake
PRODUCED = '6P2KVFKQ'    # publication sink

MANIFEST_PATH = ROOT / 'pipeline' / 'manifest.json'
STATE_PATH = ROOT / 'pipeline' / 'state.json'
READ_MANIFEST_PATH = ROOT / 'pipeline' / 'read-episodes.json'
# Run 004: this file belongs in THIS tree's root, not the sibling show's tree
# and not the pipeline/ subdir. The script's visible action worked while its
# bookkeeping went elsewhere.
RESULTS_PATH = ROOT / 'move-results.json'


def resolve_key():
    """Zotero API key, from the environment or the local key files."""
    for var in ('ZOTERO', 'ZOTERO_API_KEY'):
        if os.environ.get(var):
            return os.environ[var]
    key_file = ROOT / 'check_zotero.py'
    if key_file.exists():
        match = re.search(r'^\s*key\s*=\s*["\']([^"\']+)["\']',
                          key_file.read_text(), re.M)
        if match:
            return match.group(1)
    env_file = Path('/opt/data/.env')
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            for var in ('ZOTERO_API_KEY', 'ZOTERO'):
                if line.startswith(var + '='):
                    value = line.split('=', 1)[1].strip()
                    if value:
                        return value
    raise SystemExit('no Zotero API key found (export ZOTERO_API_KEY)')


def _load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return default


def _published(state, number):
    """True while the durable ledger records this episode in the published family."""
    record = (state or {}).get('episodes', {}).get(number, {})
    return str(record.get('status', '')).startswith('published')


def build_plan(manifest, state, read_manifest):
    """One entry per (source key, intake collection) awaiting a move.

    The intake is derived from the FIELD the key is registered under, which is
    the same discriminator ``lane_ownership()`` uses: ``read_source`` means the
    key arrived through Read, ``sources`` means Summerize. Each entry therefore
    strips exactly one lane, and a dual-use key published in both lanes
    produces two entries rather than one entry that strips both.
    """
    plan = []
    seen = set()
    for number, episode in sorted((manifest or {}).get('episodes', {}).items()):
        if not _published(state, number):
            continue
        is_read = str(episode.get('kind', '')) == 'read'
        if is_read:
            entry = (read_manifest or {}).get('episodes', {}).get(number, {})
            if not entry.get('verified'):
                # The fidelity gate is the read lane's publication gate; a
                # source whose gate did not pass must not be filed as produced.
                continue
            keys, intake, kind = episode.get('read_source') or [], READ, 'read'
        else:
            keys, intake, kind = episode.get('sources') or [], SUMMERIZE, 'interview'
        for key in keys:
            if not key or (key, intake) in seen:
                continue
            seen.add((key, intake))
            plan.append({'episode': number, 'key': key,
                         'kind': kind, 'intake': intake})
    return plan


def make_client(key):
    def get(item_key):
        request = urllib.request.Request(BASE + item_key,
                                         headers={'Zotero-API-Key': key})
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def put(item_key, obj, version):
        body = json.dumps(obj['data']).encode()
        request = urllib.request.Request(
            BASE + item_key, data=body, method='PUT',
            headers={'Zotero-API-Key': key,
                     'Content-Type': 'application/json',
                     'If-Unmodified-Since-Version': str(version)})
        with urllib.request.urlopen(request) as response:
            return response.status, response.headers.get('Zotero-Library-Version')

    return get, put


def move_one(item, get, put):
    """Strip ONE intake collection and add Produced, preserving every other."""
    intake = item['intake']
    for attempt in range(4):
        obj = get(item['key'])
        data = obj['data']
        old = list(data.get('collections') or [])
        # Exactly one membership is removed: this episode's own intake lane.
        new = [c for c in old if c != intake]
        if PRODUCED not in new:
            new.append(PRODUCED)
        if new == old:
            return {'key': item['key'], 'episode': item['episode'],
                    'kind': item['kind'], 'intake': intake,
                    'status': 'already-moved',
                    'version': obj['version'], 'collections': old}
        data['collections'] = new
        try:
            _status, version = put(item['key'], obj, obj['version'])
        except urllib.error.HTTPError as error:
            if error.code in (409, 412):
                if attempt == 3:
                    raise
                time.sleep(1 + attempt)
                continue
            raise
        return {'key': item['key'], 'episode': item['episode'],
                'kind': item['kind'], 'intake': intake, 'status': 'moved',
                'from_version': obj['version'], 'to_version': version,
                'collections': new}
    raise RuntimeError('unreachable: retry loop exhausted without a verdict')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = '--dry-run' in argv
    plan = build_plan(_load(MANIFEST_PATH, {}),
                      _load(STATE_PATH, {}),
                      _load(READ_MANIFEST_PATH, {}))
    if dry_run:
        print(json.dumps({'dry_run': True, 'plan': plan}, indent=2))
        return 0
    get, put = make_client(resolve_key())
    results = [move_one(item, get, put) for item in plan]
    print(json.dumps(results, indent=2))
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + '\n')
    return 0


# runpy.run_path() does not set __name__ to "__main__", and the historical
# wrapper scripts invoke this file that way, so guarding on __main__ alone
# would silently turn the mover into a no-op. Tests set the env var instead.
if os.environ.get('MOVE_VERIFIED_SOURCES_IMPORT_ONLY') != '1':
    raise SystemExit(main())
