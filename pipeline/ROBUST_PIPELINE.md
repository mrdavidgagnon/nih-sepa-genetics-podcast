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
python3 pipeline/robust_pipeline.py coverage
python3 pipeline/robust_pipeline.py push --episode 007 --wait 240
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

`coverage` is a read-only audit that every episode the project records as
published actually reaches the feed, plus the enclosure file existing on disk
at exactly its advertised byte length. It exists because the publish path and
the bookkeeping can disagree silently: an episode missing from a registry is
skipped while `publish` still returns `ok: true`, and read-lane artifacts are
published as `episode-NNN-reading.mp3`, so an audit that constructs the bare
`episode-NNN.mp3` name reports a **false 404** for a reading that is in fact
live. Matching is done on the episode number in each item's GUID, which is
stable across the interview scheme and the `-reading` suffix. A reading counts
as required only when its `read-episodes.json` entry is `verified: true` -- the
audit never inverts that gate into a publication requirement. `coverage`
writes nothing and declares no gate satisfied; it only reports disagreement
between the registries and the feed. **Run it as the first command of every
slice**, and after any publish or push.

`push --episode NNN --wait 240` is the only correct way to ship: it clones the
repo, copies `feed-site/*` to the repo root, commits, pushes `main`, then
polls the live feed until the remote checks pass. A manual `git push` updates
`feed-site/` locally but leaves the **repo-root feed stale**, so Pages builds
fine while every new asset 404s. `ok: false` with `pushed: true` is a
successful deploy (the in-push live-verify window is shorter than the
1-3 minute GitHub Pages lag); re-probe separately instead of re-pushing.

## Intake lanes and sinks (Zotero group 2412036)

Episodes do not originate in this repo; they originate in the Field Day group
library, under the parent collection `YF84AUZK` ("2026 NIH SEPA"). There are
two intake collections and one sink:

- **Summarize** `V4WXTY8M` -- feeds two-voice interview episodes, numbered
  from **001**.
- **Read** `DV6F4ILX` -- feeds single-voice verbatim readings, numbered from
  **501**.
- **Produced** `6P2KVFKQ` -- the sink. A source parent is moved here only
  after every publication check passes, preserving all other collection
  memberships. Items are never deleted.

Both lanes are read on every production run. Readings are preferred when any
item waits in Read, because a reading is cheaper than an interview. Items
sitting directly in the parent `YF84AUZK` are invisible to both lanes; filing
one into Summarize or Read is David's call (lane assignment decides
interview-versus-verbatim treatment).

The version-guarded move is **not** a `robust_pipeline.py` subcommand; it lives
in `pipeline/move_verified_sources.py`, which moves the `sources` and
`read_source` keys of every manifest episode whose ledger status is in the
`published*` family (it needs `ZOTERO_API_KEY` exported).

## The Read lane

A Read item is not summarized or interviewed -- it is read aloud verbatim in the
main voice by `pipeline/read_lane.py`. Readings bypass the three-reviewer gate
described below and are governed by an automated fidelity gate instead.

```sh
python3 pipeline/read_lane.py zotero-read
python3 pipeline/read_lane.py build --item KEY
python3 pipeline/read_lane.py build --item KEY --pdf PATH
python3 pipeline/read_lane.py render --episode 501
python3 pipeline/read_lane.py verify --episode 501
```

`--pdf` is optional: without it `build` downloads the item's stored Zotero PDF
attachment itself (linked-URL attachments are skipped, not downloaded). `render`
runs single-voice Edge TTS (Host Ava, locked rate).

**Fidelity gate (replaces the reviewer panel).** Verbatim text carries no
paraphrase risk, so the gate targets silent omission instead: >=99.5% of
extracted body words present, in source order, no added words, and audio
duration within 0.65-1.45x of the spoken word count (baselined on
intro+reading+outro, not the reading block alone). `verify` can report word
coverage 1.0 with `ok: false` while no audio exists -- word fidelity passing is
never the episode passing. `publish_feed.py` emits only readings whose
`pipeline/read-episodes.json` entry has `verified: true`; set that flag only
from a `verify` run that exits 0.

**Scope.** Body text only. Front matter, running heads, page numbers, figures,
tables and captions, equations, acknowledgements, funding, appendices and
references are excluded, and the gap is disclosed rather than filled -- a figure
or table is never described or summarized to cover it. The fictional
correspondent never appears in a reading and the synthetic-interview disclosure
is never applied to one; `publish_feed.py` emits a separate reading disclosure.

**Bookkeeping.** `register()` calls `sync_durable_state()`, which writes
`state.json` and `manifest.json` alongside `read-episodes.json`; a reading is
therefore visible to `status`, the watchdog and duplicate detection. A
reading's Zotero key is registered under a `read_source` field, never
`sources`: `preflight()` derives source ownership from `sources` and a paper
with both an interview and a reading otherwise reports a false
`source assigned to multiple episodes` conflict. The feed description of a
reading is synthesized from the citation by `publish_feed.py`, not read off a
manifest field.

**Open issue (escalated, latent here).** `preflight()` and `status` score
readings against interview-only rules (Host/Rowan turns, correspondent
disclosure, AI-summary disclosure) and would fail a reading for correctly
following the style guide, which also holds `status.healthy` at false. No
reading has been published in this tree yet, so it is latent; the first real
reading will trip it. The fix is a `kind == "read"` branch that defers to the
fidelity gate, mirroring the existing read-notes branch in
`publish_feed.py`. `preflight()` is a publication gate, so this is escalated
rather than silenced.

**Blast radius, proven on real code (run 027).** The collision is wider than
"a reading fails preflight", because `publish_local()` gates on
`record.get("status") != "published"` and sends everything else to
`preflight(require_audio=True, enforce_review=True)`:

- `publish --episode NNN` on a gate-passed reading **raises** and cannot ship
  it. The refusal cites `no Host/Rowan turns`, both interview disclosures and
  `review gate: review panel is missing` — it never mentions the fidelity gate
  the reading actually passed, so the error text points at the wrong contract.
- Since run 009 `sync_durable_state()` writes the reading into `manifest.json`,
  so a **bare `publish`** selects it alongside 001-003 and **aborts the whole
  run**. One registered reading therefore blocks publication of every healthy
  interview episode: 001/002/003 each return `preflight ok: true` individually
  while the batch refuses. Run 009's durable-state fix is correct and must not
  be reverted; it is what makes this reachable.
- `read_lane.py` has **no `publish` subcommand** (`extract`, `build`, `render`,
  `verify`, `zotero-read`, `next-number`), so there is no read-lane route around
  the interview gate.
- `publish_local()` statuses that trigger it: `built` and `verified` — exactly
  the two `sync_durable_state()` assigns. Only the literal `published` is exempt,
  which a reading cannot reach without publishing first.

Interim route that touches no gate, for the first real reading: run
`publish_feed.py`'s `main()` directly (it already honours `verified: true` and
has the run-013 `kind == 'read'` guard), then `verify` the feed, then
`push --episode NNN --wait 240`. This is how runs 007/012/013 exercised the read
lane, which is why the collision stayed invisible — those harnesses never called
`robust_pipeline.py publish`. Verifying a lane with a harness that skips the
mandated command does not verify the mandated command.

Why it was invisible to every green check: `coverage` 3/3, `verify ok: true` and
`publish ok: true` are all accurate while no reading is registered. Same shape as
runs 008 and 013 — a clean state proves nothing about a class that needs a record
no registry holds yet. Harnesses: `/opt/data/tmp/mm_read_publish_gate_run027.py`
(18 assertions, real `preflight()` against a real `build_script()` reading) and
`mm_read_publish_blast_run027.py` (19 assertions, real `publish_local()` against
scratch registry copies; real `state.json`/`manifest.json`/`read-episodes.json`/
`feed.xml` asserted md5-identical throughout).

## Review and preflight contract

This contract governs **interview** episodes only; verbatim readings are gated
by the fidelity check described above.

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
python3 -m py_compile pipeline/*.py
python3 pipeline/robust_pipeline.py coverage
```

This tree has **no `tests/` directory** (the sibling show's suite is
HITL-only); `python3 -m unittest discover -s tests` dies with
*Start directory is not importable*, which is expected here, not breakage.
`py_compile` plus the read-only `coverage` audit are the standing sanity
checks.

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

## `push` has a size-aware timeout, and a timeout is not a failure (run 028)

`push_to_remote()` used a hardcoded **300s** `subprocess` timeout on the `git
push` itself, and `subprocess.TimeoutExpired` fell into the broad
`except Exception` handler that reports `remote deploy failed`. That made a slow
upload **byte-for-byte indistinguishable** from a credential rejection: same
`pushed: false`, same key set, same generic prefix. The sibling HITL tree hit
exactly this on its 66 MB reading 501 and misdiagnosed it as an auth problem.

At 300s the ceiling bites a 66 MB enclosure at any upload rate below
**~225 KB/s**. Interview episodes here are 11-20 MB (128 kbps CBR) and never
come close; a long verbatim **reading** is the only episode class in the risk
band, and no reading has shipped from this tree yet - so this was latent.

What changed (deploy path only, no publication gate touched):

- `push_timeout: int | None = None` parameter, plus a `--push-timeout` CLI flag.
- When unset, the window is derived from the **bytes actually staged** at a
  deliberately pessimistic 120 KB/s assumed floor, `+120s` slack, with **300s
  kept as a hard floor** - so the change can only ever grant more time than
  before, never less. A 66 MB reading gets 683s; a 20 MB interview still gets
  exactly 300s.
- `TimeoutExpired` is now caught **before** the broad handler and reported as
  `timed_out: true`, `remote_state: "indeterminate"`, with the staged byte count
  and an instruction to run `git ls-remote origin main` before retrying. **A
  timed-out push means unknown, not failed** - the remote may already have the
  commit, so a blind retry risks a non-fast-forward rejection.

A timeout still returns `ok: false`; the push still runs with `check=True`; the
live-verify loop is unchanged. `preflight()`, `review_gate()`, `verify_feed()`,
`feed_coverage()`, `reconcile()`, `publish_local()` and `parse_turns()` are all
byte-identical to the pre-fix file, and the set of `published*` status literals
is unchanged.

Harnesses: `/opt/data/tmp/mm_push_timeout_repro_run028.py` (17 assertions,
pre-fix reproduction) and `mm_push_timeout_proof_run028.py` (32 assertions: A
pre-fix reproduces, B post-fix distinguishes + scales, C seven gate functions
byte-identical, D live registries unmoved).

**Harness pitfall, cost a false result once here:** a module copied into scratch
resolves `ROOT` relative to **its own** location, so the relocated pre-fix copy
had `ROOT=/opt/data/cache` and died on a missing `feed-site/` before reaching the
push - section A reported a confident FAIL while proving nothing. Pin `m.ROOT`
(and `m.EPISODES`) to the real tree after loading a relocated module, or the
"pre-fix reproduction" half of a both-sides proof is vacuous.
