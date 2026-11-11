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

**Read-lane publication: RESOLVED (run 029).** `preflight()` is lane-aware. It
branches on manifest `kind == "read"` — the same discriminator `publish_feed.py`
has used since run 013 — and on that branch asserts the ABSENCE of the
synthetic-interview disclosure and of Dr. Rowan Field (both of which the style
guide forbids in a reading), requires the reading's own verbatim and
text-to-speech disclosures, resolves source keys from `read_source` rather than
`sources`, and defers to `fidelity_gate()` instead of the three-reviewer panel.
`fidelity_gate()` *reads* the verdict `read_lane.py verify` recorded in
`read-episodes.json`, so there is one gate and one verdict, not a
re-implementation.

Interviews carry no `kind` key, so anything not explicitly a reading takes the
interview path unchanged (nine interview gate functions were proved
byte-identical against the pre-fix file).

The read branch grants nothing. Each of these is still refused: `verified:
false`, coverage under the 0.995 floor, a missing coverage figure, no registry
entry, a missing `source.txt`, Rowan appearing in a reading, a missing
verbatim/TTS disclosure, the Zotero-links disclosure absent from **both** script
and notes, no `**Reader:**` turns, an empty MP3, and a citation with no year. A
`kind` of `"READ"` in the wrong case does not unlock the read branch.

Consequently the historical advice to prefer Summerize over Read is **lifted**:
prefer Read items when any wait, since a reading is cheaper than an interview and
`build` pulls its own Zotero PDF (run 010). Ship a reading with the mandated
`publish --episode NNN` then `push --episode NNN --wait 240` — there is no
interim route and none is needed. Harnesses:
`/opt/data/tmp/mm_read_preflight_repro_run029.py` (13 pre-fix, 11 post-fix) and
`mm_read_preflight_proof_run029.py` (34 assertions).

The lesson from how long this took to close: runs 007/012/013 exercised the read
lane by calling `publish_feed.py` directly and never called
`robust_pipeline.py publish`, the mandated deploy command, so the collision stayed
invisible behind `coverage` 3/3 and `publish ok: true`. Verifying a lane with a
harness that skips the mandated command does not verify the mandated command.

**`reconcile()` checks the published FAMILY, not three literal statuses
(run 031).** The audio-integrity check gated on the literal set
`{"rendered", "verified", "published"}`, which omits the two documented
published end states — `published_and_moved` (001-003's convention in this
tree) and `published_pending_zotero_move`. Every shipped episode here sits at
`published_and_moved`, so the check was **dead for the entire published
catalogue**: an episode's MP3 could vanish and `reconcile` would report
`ok: true` with no issue. It now tests `status.startswith("published")`, the
way `feed_coverage()` already did. Non-published statuses stay exempt, a
wrong-case status does not unlock it, and the run-008 de-duplicating extend is
unaffected. Same class as run 005's `interview_episodes()` filter: when a status
string is a gate, test it against **every** status the docs tell you to write.
Harnesses `/opt/data/tmp/mm_reconcile_status_repro_run031.py` (15, against the
unmodified module) and `mm_reconcile_status_proof_run031.py` (45, including the
pre-fix backup still reproducing and 40 functions byte-identical).


### The TTS parts cache is keyed on the script, not just the piece index

`read_lane.py render` caches each synthesized chunk at `episodes/NNN/parts-read/NNNNN.mp3`
and skips any part that already exists at >=500 bytes. That index-only key meant a
**rebuilt script silently inherited the previous script's audio**: `build --force`
(the sanctioned rebuild-in-place path added run 030) rewrites `script.md` and
`source.txt` for a different paper, every cached part still exists, so a plain
`render` re-synthesized nothing and the episode kept the old paper's voice.

The fidelity gate **cannot** detect this. `verify()` compares the new `script.md`
against the new `source.txt` — both written in the same breath, so coverage reads
1.0 — and checks duration against the new word count. Neither side of that
comparison is the audio's provenance, so the gate returned `ok: true` and
`register()` wrote `verified: true` for a reading whose mp3 was a different paper.

Fixed run 032 by mirroring the interview lane: `render_episode()` writes
`parts-read/render-plan.json` recording `script_sha256`, the chunk count, a hash of
the chunk sequence, and the locked `voice`/`rate`. Any mismatch (or an unreadable
plan) deletes the cached parts and forces a full re-render; the plan is written
only **after** ffmpeg succeeds, so a crashed render never leaves a trusted cache.
Genuine resumability is unchanged — an unchanged script still reuses its parts, and
deleting two parts re-synthesizes exactly those two.

Operational notes:

- A voice or rate change now invalidates the cache automatically. Deleting
  `parts-read/` by hand is no longer required after a script correction.
- The gate was **not** edited. Truncated audio, dropped source text and injected
  commentary are all still refused, and a reading with no audio still fails while
  reporting word coverage 1.0.
- This is the run-030 lesson in a second location: a gate that derives both sides
  of its comparison from the same write validates internal consistency, not
  provenance. When a gate passes, ask which artifact it never looked at.

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

## Source ownership is lane-aware (run 033)

The two lanes record a Zotero key under different manifest fields --
interviews under `sources`, readings under `read_source` -- and that split is
load-bearing: it is what lets one paper legitimately have both an interview and
a verbatim reading without looking like a duplicate-ownership conflict.

Every ownership map here used to be built from `sources` alone, which meant
**readings were in no duplicate-detection map at all**. Two readings of the same
paper collided in silence in `inventory()`, `reconcile()` and `preflight()` --
even though `read_lane.sync_durable_state()` mirrors a reading into
`manifest.json` specifically so duplicate detection can see it. `preflight()`
was the sharpest case: since run 029 it resolves a reading's expected key from
`read_source` (correct) and then looked that key up in an interview-only map, so
the owner count was 0 or 1 forever and no number of readings of one paper could
trip the check.

`lane_ownership(episodes)` now returns `(interview_owners, read_owners)` keyed on
the field name -- the same discriminator `move_verified_sources.py` uses -- and
`duplicate_owners(*maps)` reports collisions **within** a lane. So:

- two interviews sharing a key: conflict (unchanged)
- two readings sharing a key: conflict (new)
- one interview + one reading of the same paper: legal (unchanged, run-029 intent)

`source_ownership` keeps its exact interview-only meaning and shape for existing
consumers; `read_source_ownership` is added alongside it in both the
`inventory()` report and the `reconcile()` report.

Latent when fixed -- no reading has ever been registered here, so three
`reconcile --write` passes showed 0 issues before and after. Reproduce on scratch
manifests, and keep the control: the identical collision expressed under
`sources` is flagged, which proves the detector works and the field name was the
whole difference. Harnesses `/opt/data/tmp/mm_read_ownership_repro_run033.py`
(21/21 against the unmodified module) and `mm_lane_ownership_proof_run033.py`
(37/37: pre-fix backup still reproduces, all three sites now catch it, interview
detection and cross-lane sharing unchanged, the read gate still refuses a missing
script / Rowan / a missing verbatim disclosure / a yearless citation / a missing
mp3 / wrong-case `kind`, and 15 untouched functions byte-identical).

**The general lesson: when you add a second field to express the same concept,
grep every reader of the first one.** This is the run-030 lesson (a write-side
mirror creates read-side debt) with the axis rotated: run 030 was one registry of
three, this is one field of two.

## `preflight()` is lane-aware (run 029)

`preflight()` scores an episode against one of two non-interchangeable
contracts, selected from the manifest `kind` key - the same discriminator
`publish_feed.py` uses. Interview episodes carry no `kind`, so anything not
explicitly `"read"` takes the interview path.

| | interview | reading (`kind: "read"`) |
|---|---|---|
| dialogue | `**Host:**` / `**Rowan:**` turns | single `**Reader:**` voice |
| Rowan | required | **forbidden** |
| disclosures | fictional-correspondent + AI-summary | verbatim-reading + automated-TTS |
| gate | three-reviewer panel (`review_gate`) | automated word fidelity (`fidelity_gate`) |
| source key | manifest `sources` | manifest `read_source` |

Shared by both lanes and unchanged: the Zotero-links disclosure (script **or**
notes), numbered citations with a year and a direct Zotero link, duplicate-link
detection, and the single-non-empty-mp3 audio check.

`fidelity_gate(episode)` does not re-implement the fidelity check. It reads the
verdict `read_lane.py verify` recorded in `pipeline/read-episodes.json` and
refuses on `verified: false`, a coverage figure below `READ_COVERAGE_FLOOR`
(0.995), a missing coverage figure, a missing registry entry, or a missing
`source.txt`/`script.md` (which would make the verdict unreproducible). One gate,
one verdict: a second implementation could disagree with the lane's own.

Why this mattered: before run 029, a reading that **passed** the fidelity gate
could not be published at all, and because `sync_durable_state()` registers a
reading in `manifest.json` (run 009), a bare `publish` selected it and aborted
publication of every healthy interview episode. Do not "simplify" the branch
back into one path.

## The render-plan cache key must cover every TTS input (run 034)

Both lanes cache synthesized audio under `parts-*/` and skip any part already
present, keyed on the **render plan**. The guard only works if the plan
contains every input that changes the audio -- and each lane was missing a
different one:

- **Read lane:** the plan recorded `script_sha256`, the chunk plan, `voice` and
  `rate`, but not the version of `spoken_text()`, the transform applied to every
  piece immediately before synthesis. Correcting that transform re-synthesized
  **nothing**; the episode kept audio built from the old transform. Fixed with
  `RENDER_TEXT_VERSION` in the plan (bump the constant when `spoken_text()`
  changes what reaches TTS).
- **Interview lane:** the plan recorded `script_sha256` and
  `render_text_version`, but not the voices or rates used. A voice or rate change
  -- the exact edit the voice-change procedure prescribes -- left every cached
  part valid, so the episode shipped the **previous** voice under the new
  configuration. Fixed by hoisting the `voices`/`rates` maps above the plan
  comparison and recording them as `voices` (`<voice>@<rate>` per role).

Neither defect is visible to any gate. The read lane's fidelity gate compares
the new `script.md` against the new `source.txt` and checks duration against the
new word count; the interview lane's `preflight`/`verify_feed` check structure,
disclosures, enclosure sizes and feed shape. **No gate inspects what the audio
was rendered from**, and the plan is the only provenance record there is.

A third instance surfaced in the same pass: the interview lane read its plan with
a bare `json.loads`, so a truncated plan -- what a killed background render
leaves behind -- aborted every later `render NNN` with `JSONDecodeError` instead
of rebuilding. The read lane had been tolerant since run 032. Now both treat an
unreadable plan as no plan and force a full re-render.

Lesson: when a cache key is a provenance record, enumerate the inputs of the
step it guards and check each one is in the key -- and when one lane holds a
guard, diff the other lane's equivalent path rather than assuming symmetry.

## Episode-provenance disclosure was keyed on a sibling show's numbers (run 035)

`publish_feed.py`'s `notes_html()` branched on the literal tuple
`num in ('033','034')` and emitted the **pre-produced-audio** disclosure for
those two numbers: *"Pre-recorded audio provided by David Gagnon ... was not
reviewed or transcribed."* That is true in Human in the Loop, where 033/034 are
finished MP3s David supplied. **Moral Machines numbers its interviews from 001**,
so 033 and 034 are ordinary future episodes here. A normal scripted, reviewed,
TTS-rendered interview reaching either number would have shipped a **false
provenance statement** in its feed notes while **losing both mandated
disclosures** — the fictional-correspondent paragraph and the AI-generated
caveat — on the one episode whose notes claim no human checked it.

No gate can see it. `preflight()` greps `script.md` and `episode-notes.md`;
`feed_coverage()` matches GUIDs and enclosure byte lengths; `verify_feed()` does
reach into `<content:encoded>` but **only to pull `notes.md` hrefs and confirm
the file exists** — never to read the disclosure prose. So `preflight ok: true`,
`coverage ok: true` and `verify ok: true` are all accurate and all blind, and the
episode's own notes file on disk is correct, which makes the defect feed-only.

Fixed by making provenance a property of the **record** rather than of the
number: `preproduced_episodes()` reads manifest `preproduced: true`, and only the
literal boolean unlocks the branch (a truthy string and `false` both do not; a
corrupt manifest degrades to the empty set rather than raising). No episode sets
the flag today, so the branch is dormant until one legitimately needs it. The two
dead `num == '036'` filename overrides were removed in the same pass — HITL needed
them because 036's on-disk name differed; here `interview_episodes()` already
derives `episode-{num}.mp3`, so they were inherited no-ops.

Two lessons:

- **A cloned special case keyed on an episode number is a time bomb set to the
  other show's calendar.** Runs 004-010 audited this tree for sibling-show
  *strings* (titles, GUIDs, cover art, spoken show name). A hardcoded *number*
  survives every one of those greps and fires only when this show's numbering
  reaches it — latent for 30+ runs with 001-003 shipped, and reachable in 30
  episodes. Grep retargeted modules for episode-number literals, not just names.
- **This is the lane-shaped-gate class with the discriminator rotated to
  identity.** Runs 005/009/013 were lane strings; this is the same error with an
  episode *number* standing in for a property of the record. When a branch
  selects behaviour by identity, ask what makes it true, and store that instead.

Prove on real code both sides, scratch trees, silent `anullsrc` mp3s (no TTS
spend). `/opt/data/tmp/mm_preproduced_repro_run035.py` (**27/27 against the
unmodified module**, with the control that makes it a finding: a neighbouring
episode 032 built identically gets both correct disclosures, so the number was
the whole difference) and `mm_preproduced_proof_run035.py` (**43/43**: the
pre-fix backup still reproduces; post-fix 032/033/034 all carry both
disclosures; the branch still fires on a real `preproduced: true` record and
refuses `'yes'`/`false`/corrupt input; 036 still publishes with the overrides
gone; the read lane, the run-013 duplicate-item guard and the
`moral-machines-` GUID prefix are intact; 7 untouched functions byte-identical).

Two harness bugs were fixed as harness bugs, not by relaxing a check (run 029's
rule): this tree carries **two** `036` overrides where HITL has three, and
`verify_feed` *does* mention `content:encoded`, so the "no gate reads the feed
notes" assertion had to be narrowed to what that code actually does with it
rather than claiming the string is absent.
