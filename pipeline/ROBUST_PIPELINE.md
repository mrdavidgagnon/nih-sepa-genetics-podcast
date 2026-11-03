# Robust production pipeline

`robust_pipeline.py` is the safety wrapper for episode production. It uses the
existing scripts and checked-in assets, but makes the gates and side effects
explicit. It uses only the Python standard library; TTS and ffmpeg are loaded
only by `render`.

## Operating model

The durable ledger is `pipeline/state.json`; the content inventory is
`pipeline/inventory.json`. Both are written atomically. Episode states are:

`planned -> review_pending -> reviewed -> rendering -> rendered -> verified -> published`

Failures become `failed` or `blocked`, and invalid transitions are rejected.
The initial ledger is imported from `manifest.json` by the first
`reconcile --write`. Existing `published_*` manifest entries are imported as
legacy `published` history. A new episode cannot render or publish without
three passing reviewers.

Every mutating command takes `pipeline/.pipeline.lock`. It is an advisory OS
lock with a JSON owner record. The lock is never guessed stale or silently
broken; inspect it with `status`, and use `unlock --force` only after checking
that no process is running.

## Commands

Run from this directory:

```sh
python3 pipeline/robust_pipeline.py inventory
python3 pipeline/robust_pipeline.py reconcile --write
python3 pipeline/robust_pipeline.py review 007
python3 pipeline/robust_pipeline.py preflight 007
python3 pipeline/robust_pipeline.py render 007
python3 pipeline/robust_pipeline.py publish --episode 007
python3 pipeline/robust_pipeline.py verify pipeline/../feed-site/feed.xml
python3 pipeline/robust_pipeline.py status
python3 pipeline/robust_pipeline.py watchdog
python3 pipeline/robust_pipeline.py attempt start 020 --budget-seconds 1500
python3 pipeline/robust_pipeline.py attempt checkpoint 020 --stage script_drafted
python3 pipeline/robust_pipeline.py attempt finish 020 --outcome completed
python3 pipeline/robust_pipeline.py attempt status
```

`render` hashes the script and stores a render plan beside resumable dialogue
parts. Valid parts are reused; changed scripts invalidate the parts. Each TTS
request is retried at most four times with bounded backoff. The final ffmpeg
file is written under a temporary name and atomically replaced only after it
is non-empty. `--force` invalidates otherwise reusable parts.

`publish` builds the local `feed-site` using the existing feed generator,
whose asset, RSS, and HTML writes are now atomic. It then checks RSS parsing,
stable GUID uniqueness, local enclosure lengths, and (when `--remote URL` is
provided) HTTP audio range and notes responses. It never commits, pushes, or
uploads. A remote deployment is considered verified only when these explicit
checks pass.

## Review and preflight contract

`review` requires exactly three distinct reviewer sections, a pass verdict for
each, required revisions, and a revision record with no unresolved/blocking
language. `preflight` additionally checks dialogue syntax, required fictional
correspondent and AI-summary disclosures, the exact Zotero access reminder,
manifest source ownership, numbered source citations with year/metadata/link,
and (with `--audio`) exactly one non-empty MP3.

## Watchdog

`status` emits machine-readable JSON suitable for a scheduler or dashboard.
It includes each state, recent errors, deterministic preflight issues, and
whether the lock is actively held. `watchdog` marks a run unhealthy when an
episode is failed/blocked, preflight is broken, a lock is active, or a render
has exceeded the configured age (`--max-render-minutes`). The command exits
with JSON output; callers should treat `healthy: false` as an alert.

## Tests

```sh
PYTHONPATH=. python3 -m unittest discover -s tests -v
python3 -m py_compile pipeline/*.py
```

The tests cover atomic state writes, transition safety, the three-reviewer
gate, deterministic source preflight, and local enclosure verification.

## Production attempts

Episode state alone cannot describe a long-running run. A driver can research
sources, draft a script and fail twenty minutes in while the episode is still
`planned`; ten consecutive failures once left `attempts: 0` and no record of how
far any of them reached.

Each unit of work therefore opens a durable attempt: `attempt start` records the
budget for the **complete** unit including finalisation, `attempt checkpoint`
records progress as it happens rather than at the end, and `attempt finish`
closes it with an explicit `completed`, `failed`, or `stopped`.

An attempt left open is classified by its own budget and last checkpoint, never
by unrelated ledger activity: past its deadline it is `timed_out`, silent beyond
the stall window it is `stalled`, otherwise `running`. `watchdog` reports those,
and raises an alert after three consecutive failed attempts -- a run of failures
that never changes episode state is otherwise invisible.

Staleness for a rendering episode is likewise measured from that episode's own
last transition or checkpoint. It previously came from the ledger's global
`updated_at`, so a write about any other episode made a stuck render look fresh.
