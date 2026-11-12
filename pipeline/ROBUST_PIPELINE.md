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
and (with `--audio`) exactly one non-empty MP3 whose sha256 matches the digest
`render_episode()` recorded in `state.json` (`artifacts.audio_sha256`). An
absent digest is accepted; a digest that is present and different is refused.

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

Neither defect is visible to the *word* half of any gate. The read lane's
fidelity gate compares the new `script.md` against the new `source.txt` and
checks duration against the new word count; the interview lane's
`preflight`/`verify_feed` check structure, disclosures, enclosure sizes and feed
shape. None of those can tell what the audio was rendered from. For the read
lane that hole is now closed downstream: run 042 made `fidelity_gate()` compare
the recorded `audio_sha256` against the mp3 on disk, so a stale or swapped
render is refused even when the plan guard was bypassed. As of run 043 the
interview lane no longer relies on `parts/render-plan.json` alone either:
`reconcile()` compares the ledger's recorded `audio_sha256` against the mp3 on
disk and refuses a mismatch (see the run-043 section below).

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

## `verify_feed()`'s legacy exemption fired on episode 001 (fixed run 036)

The notes-file checks in `verify_feed()` -- local **and** live -- demoted a
missing `episode-NNN-notes.md` from an `issue` to a `warning` for any item the
function judged "legacy", and that judgement was keyed on the feed's own
`<itunes:episode>` value being the literal string `"1"`:

```python
legacy_item = item.findtext("{...}episode") == "1"      # pre-fix
```

`publish_feed.py` emits `<itunes:episode>{int(num)}</itunes:episode>`, so
**episode 001 of this show always renders as `1`** -- and 001 here is a fully
gated interview (43 dialogue turns, three-reviewer panel passed, rendered and
published through this pipeline), not imported history. The exemption meant for
pre-pipeline imports therefore landed permanently on a current episode: delete
`feed-site/episode-001-notes.md`, or let the live copy 404, and `verify` returns
**`ok: true` with an empty issue list**. Since `publish_local()` raises only when
`verify_feed()` is not ok, that is the gate declining to stop a deploy whose
notes file is missing. Episodes 002 and 003 were caught correctly, which is the
tell: the detector worked and the episode *number* was the whole difference.

Fixed by keying the exemption on the **durable ledger** instead of the feed:
`_legacy_episode_numbers()` returns episodes whose ledger status is the literal
`published`, which is exactly the discriminator `status()` already uses for
"legacy published episodes predate checked-in scripts/review panels". The
`published*` family this tree's real episodes use (`published_and_moved`,
`published_pending_zotero_move`) is **not** exempt, and `_feed_item_number()`
derives the number from the GUID the way `feed_coverage()` does. `verify_feed()`
now also reports `legacy_exempt_episodes`, which is `[]` in this tree -- an
empty list is the healthy state, and a non-empty one should name a genuine
import.

Lessons:

- **This is run 035's class in a second location.** Run 035 found the
  pre-produced-audio disclosure keyed on episode numbers (`'033'`, `'034'`)
  borrowed from the sibling show; this is an exemption keyed on the number `1`.
  An episode number is never a property of the record -- when a branch grants a
  waiver, ask what makes the waiver true and store *that*.
- **A waiver is a gate with the sign flipped.** The audit habit of asking "which
  status strings does this gate accept?" (runs 005/031) has a mirror image: ask
  which records a branch *exempts*, because an over-broad exemption is invisible
  in every green check. `coverage` 3/3 and `verify ok: true` were both accurate
  and both blind to this.
- Latent, as usual: all three notes files are present locally and return 200
  live, so nothing in the real tree ever exercised the demotion.

Prove on real code both sides, on scratch feed-site copies (symlink the mp3s --
a scratch tree on another filesystem makes `os.link` fail with
`Invalid cross-device link`). Harnesses
`/opt/data/tmp/mm_legacy_exempt_repro_run036.py` (**23/23 against the unmodified
module**, with the 002 control proving the detector works) and
`mm_legacy_exempt_proof_run036.py` (**39/39**: the pre-fix backup still
reproduces; post-fix 001 is caught as an issue; nothing granted -- 002/003 still
caught and an intact feed's verdict is identical pre/post; a genuine ledger
status `published` is still exempted and named; all five of
`published_and_moved`/`published_pending_zotero_move`/`PUBLISHED`/`verified`/
`rendered` are refused the waiver; only `verify_feed` changed, with 42 functions
byte-identical and `preflight`/`review_gate`/`fidelity_gate`/`feed_coverage`/
`publish_local` untouched).

## Run 036's own waiver status is one the pipeline writes (fixed run 037)

Run 036 moved the notes waiver off the feed's `<itunes:episode> == "1"` and onto
the **ledger status literal `published`**, documented as "pre-pipeline imports".
That status is not evidence of an import. `publish_local()` writes it itself --
`if record.get("status") == "verified": transition(ledger, number, "published",
...)` -- and `load_ledger()`'s bootstrap maps manifest `published_and_moved` ->
`published`. So:

- **Every episode produced here sits at the waived status** for the whole window
  between `publish` and the Zotero move, which is exactly when its notes file is
  newly deployed and most likely to be missing.
- **A ledger rebuilt from `manifest.json`** (delete `state.json`, any fresh
  clone) puts **all three** of 001-003 at `published` at once, waiving the entire
  catalogue in one step.

Proved on the unmodified module: with `episode-001-notes.md` deleted and 001 at
`published`, `verify_feed` returned **`ok: true`, `issues: []`**, the loss
demoted to a warning and `legacy_exempt_episodes: ['001']`. The control -- the
*identical* loss with 001 at `published_and_moved` -- was correctly refused
`ok: false`, proving the detector works and the status string was the whole
difference. `publish_local()` raises only when `verify_feed()` is not ok, so
this was again the gate declining to stop a deploy with a missing notes file.

Fixed by requiring **positive evidence that the episode was never produced
here**. `_legacy_episode_numbers()` now grants the waiver only when all three
hold: the literal status `published` (run 036's test, kept), **no** in-pipeline
production transition (`rendering`/`rendered`/`review_pending`/`reviewed`/
`verified`, via the new `_produced_in_pipeline()`), and **no**
`episodes/NNN/script.md` on disk. The disk test is what still holds when a
rebuilt ledger has erased the transition history. `status()` was pointed at the
same helper so there is one definition of legacy. The set can only **shrink**
relative to run 036, so the waiver cannot be widened by this change.

Lessons:

- **A waiver must rest on evidence of the thing it waives, and a status your own
  code writes is not evidence.** Run 036 correctly stopped keying the waiver on
  an episode *number*, then keyed it on a status string the publish path
  assigns. The right question is not "which status means legacy?" but "what
  observable fact distinguishes an import from our own output?" -- here, the
  absence of production transitions and of a script on disk.
- **Check whether a discriminator you borrow is *written* by the pipeline.**
  `status()` had used this test for a while, which is what made it look
  authoritative; reusing it propagated the flaw rather than validating it.
  `grep -n 'transition(ledger' pipeline/robust_pipeline.py` lists every status
  the code can author -- none of those can stand alone as proof of provenance.
- Latent in the usual way: all three notes files are present locally and 200
  live, so `coverage` 3/3 and `verify ok: true` were accurate and blind.

Harnesses `/opt/data/tmp/mm_legacy_status_repro_run037.py` (**19/19 against the
unmodified module**: the two writers of `published`, all three episodes' real
production transitions, the hidden notes loss, the `published_and_moved`
control, and the rebuilt-ledger case waiving all three at once) and
`mm_legacy_status_proof_run037.py` (**43/43**: the pre-fix backup still
reproduces; post-fix 001 is caught; each of the five production transitions
independently blocks the waiver; a script on disk alone blocks it; **nothing
granted** -- a genuine import is still exempted *and still named*, all six of
`published_and_moved`/`published_pending_zotero_move`/`PUBLISHED`/`Published`/
`verified`/`rendered` are refused, an intact feed's verdict is identical
pre/post, and 002/003 are still caught; only `_legacy_episode_numbers` and
`status` changed, with `_produced_in_pipeline` added and **49 functions
byte-identical** including `preflight`/`review_gate`/`fidelity_gate`/
`feed_coverage`/`publish_local`/`reconcile`/`verify_feed`).

## The publication gate kept its OWN copy of the legacy waiver (fixed run 044)

Runs 036 and 037 fixed the "is this episode imported history?" test twice -- in
`verify_feed()`, then properly in `_legacy_episode_numbers()`. Both left
`publish_local()` alone, and run 037's own proof records it: *49 functions
byte-identical including ... `publish_local`*. But `publish_local()` was never
calling that helper. It carried a **separate, one-part copy** of the discarded
test, inline, in the publication gate itself:

```python
record = ledger.get("episodes", {}).get(number, {})
if record.get("status") != "published":            # pre-fix
    check = preflight(number, require_audio=True, enforce_review=True)
```

So an episode at the literal status `published` skipped `preflight` **entirely**:
the three-reviewer gate, the fictional-correspondent and AI-summary disclosures,
the Zotero-links disclosure, every citation check, and the audio check, all at
once. That status is not rare and is not imported history -- run 037 established
both: `publish_local()` *itself* writes it (`verified -> published`), so every
episode produced here occupies it between publish and the Zotero move to
`published_and_moved`, and `load_ledger()`'s bootstrap maps
`published_and_moved -> "published"`, putting the **whole catalogue** at the
waived status at once whenever the ledger is rebuilt from `manifest.json`.

It is worse than a missed check, because `publish_feed.main()` re-copies each
episode's notes and audio from `episodes/NNN/` to `feed-site/` on every run: a
corrupted or substituted deliverable is **actively propagated** to the staging
directory the next `push` deploys. Proved on real code -- substituted notes
reached `feed-site/episode-001-notes.md`, and 001's audio swapped for 002's was
accepted -- while `publish` returned `ok: true`, `verify_feed` ok, and
`feed_coverage` ok, because all three inspect the feed's structure and none of
them re-runs the episode gate.

Fixed by deleting the inline copy and deferring to `_legacy_episode_numbers()`,
the three-part test that already exists in this file (literal status
`published`, **no** in-pipeline production transition, **no** `script.md` on
disk). That set can only ever be narrower than the status literal, so the change
adds refusals and grants nothing. All three real episodes are now preflighted by
a bare `publish` where previously they could be waived; all three pass, and
`feed.xml` is byte-identical.

Lessons:

- **A fix is not finished while a second copy of the defect is still inline
  somewhere.** Runs 036 and 037 centralized the right answer into a helper and
  verified the helper exhaustively, but centralizing is only half the job --
  the open-coded duplicates have to be *migrated to it*. After extracting a
  predicate into a function, grep for the literal it replaced
  (`grep -n 'status.*== "published"' pipeline/robust_pipeline.py`) and confirm
  every site now calls the helper.
- **A byte-identical function in a proof is evidence of scope, not of
  correctness.** Run 037 listed `publish_local` as untouched to show the blast
  radius was small; read the other way, that line was the open defect in plain
  sight for seven runs. When a no-weakening proof names a gate as unchanged, ask
  whether it *should* have changed.
- Latent in the now-familiar way: 001-003 all sit at `published_and_moved`, not
  the waived literal, so `coverage` 3/3, `verify ok: true` and three
  `reconcile --write` passes at 0 issues were all accurate and all blind. It
  would have fired on the next episode during its publish-to-move window, or on
  any slice that rebuilt the ledger.

Harnesses `/opt/data/tmp/mm_publish_waiver_repro_run044.py` (**37/37 against the
unmodified module**: the control refusing at `published_and_moved`, the same
episode shipping at `published`, substituted notes reaching `feed-site`, swapped
audio accepted, and the rebuilt-ledger case waiving all three episodes at once)
and `mm_publish_waiver_proof_run044.py` (**51/51**: the pre-fix backup still
reproduces; post-fix the ungated episode is refused at all five of
`published`/`published_and_moved`/`published_pending_zotero_move`/`rendered`/
`verified`; **nothing granted** -- a genuine import is still exempt and the
exemption is revoked the moment it shows a production transition, a healthy
publish still succeeds with all three preflighted and the feed byte-identical,
and a missing panel, missing audio, missing AI-summary disclosure, missing
Zotero-links disclosure, a dropped citation entry, a failed reviewer verdict and
an empty mp3 are each still refused; only `publish_local` changed, **48
functions byte-identical** including `preflight`/`review_gate`/`fidelity_gate`/
`verify_feed`/`feed_coverage`/`_legacy_episode_numbers`/`reconcile`).

Harness note: the repro's first draft deleted `episodes/001/episode-notes.md` to
simulate an ungated episode, which `publish_feed.main()` atomic-copies on every
run -- so `publish` refused on a crash in the feed build, not on the gate, and
five assertions false-failed. Isolate the gate with a defect `publish_feed` does
not touch (delete `review-panel.md`). Separately, a synthetic legacy fixture
with no manifest entry is refused by run 041's coverage assertion rather than
preflight; that is correct, and the pre-fix module raises the identical error,
which is what proves it is not a regression. Both were harness bugs, not code
defects (run 029's rule).

## Required item fields are gated (run 038)

`verify_feed()` requires every feed item to carry a non-empty `<title>` and
`<description>`, reported as an issue naming the episode and the field. There is
no waiver: an empty field is a defect for an imported episode too.

`publish_feed.py` reads an interview item's title and description off
`pipeline/manifest.json` and defaults description to `''`, so **an episode
registered without a `description` key used to ship a live item with an empty
`<description>`** (this happened to episode 002) while `publish` and `verify`
both returned `ok: true`. When registering an episode, write `description` and
`number` into the manifest alongside `title`/`sources`.

### The fidelity-gate verdict is persisted by `verify` (fixed run 040)

`read_lane.py register()` is called from exactly one place -- `build()` --
which necessarily runs **before** any audio exists. So the verdict it stored
was always the pre-render one: `verified: false` in `read-episodes.json` and
status `built` in `state.json`/`manifest.json`, with the single gate issue
`no audio rendered yet`.

Nothing afterwards rewrote it. `render` returns a dict and writes no registry;
`verify` computed the verdict, printed it and exited 0/1. A reading that
genuinely **passed** the gate after rendering therefore stayed recorded as
unverified forever, and both consumers of that flag refused it:

- `robust_pipeline.fidelity_gate()` reports *automated fidelity gate has not
  passed* (it reads `record["verified"]`), so `publish --episode NNN` aborts.
- `publish_feed.read_episodes()` emits an item only for `verified: true`, so
  the reading never reaches the feed.

The only route that ever flipped the flag was re-running `build()` **after**
the render -- i.e. `--force`, the rebuild-in-place path whose entire hazard
(run 032) is shipping the previous paper's audio under a new script. So the
sole workaround for an unpublishable reading was the documented hazard.

Fixed by adding `record_verdict(number, verification)`, called from the CLI
`verify` branch. `verify()` the *function* stays side-effect free, so a harness
can score a tree without mutating its registries; the operator-facing command
is what persists. It also records `audio_sha256`/`audio_bytes` beside the
verdict. As of run 042 `fidelity_gate()` **does** inspect that provenance:
it re-hashes `episodes/NNN/episode-NNN.mp3` and refuses when the bytes are not
the ones the verdict was earned on (see the section below).

It grants nothing: a failing verdict is stored as failing with its issue list,
`fidelity_gate()` still refuses it, and `record_verdict` raises rather than
invent a registry entry `build()` never created.

**Operator note:** after `read_lane.py render --episode NNN`, run
`read_lane.py verify --episode NNN`. That single command now both gates and
records; there is no hand-written registry step and no `--force` rebuild.
### The read verdict is bound to its audio (fixed run 042)

Run 040 recorded `audio_sha256`/`audio_bytes` beside the read verdict and called
them provenance the gate never inspects. Nothing read them, so they documented a
hazard without gating it -- and the hazard is reachable by an ordinary operator
sequence, because `read_lane.render_episode()` writes
`episodes/NNN/episode-NNN.mp3` and writes **no registry**, while
`record_verdict()` runs only from the CLI `verify` branch:

```
verify --episode NNN      # verdict + digest stored, verified: true
build --item OTHER --force  # script.md + source.txt now a different paper
render --episode NNN      # mp3 replaced; registry untouched
```

The reading is then `verified: true` beside a digest of the **previous** audio,
and `publish_feed.read_episodes()` ships on that flag alone. The word checks
cannot see it: `verify()` compares the new script against the new `source.txt`,
both written in the same breath, so coverage reads 1.0 (run 030/032's lesson --
a gate deriving both sides of its comparison from the same write validates
internal consistency, not provenance).

`fidelity_gate()` now re-hashes the mp3 and refuses on any mismatch, naming both
digests and telling the operator to re-run `verify`. It is checked there rather
than in a new gate so the read lane keeps exactly one verdict with one owner.
It grants nothing: a **missing** `audio_sha256` is a refusal, not a waiver (an
entry predating run 040 must be re-verified), and missing audio is refused too.

Harnesses: `/opt/data/tmp/mm_audio_provenance_repro_run042.py` (19/19 against
the unmodified module) and `mm_audio_provenance_proof_run042.py` (39/39:
pre-fix backup still reproduces; nothing granted -- `verified: false`, coverage
below the floor, a missing coverage figure, a missing digest, stale
`audio_bytes`, deleted audio and a missing `source.txt` are each still refused;
exactly one function changed with 45 byte-identical, including `preflight`,
`review_gate`, `verify_feed`, `feed_coverage` and `publish_local`).

Lesson: **recording provenance is not checking it.** When a fix stores a field
precisely because a gate is blind to that property, wire a reader in the same
slice or the field becomes documentation of an open hole.


Harnesses: `/opt/data/tmp/mm_verified_persist_repro_run040.py` (29/29 against
the unmodified module) and `mm_verified_persist_proof_run040.py` (56/56:
pre-fix backup still reproduces; post-fix records and unblocks; truncated
audio, dropped source text and injected commentary all still refused and
stored as failures; `verify()` still side-effect free; only `main()` changed
with 30+ functions byte-identical).

## `publish` could ERASE a published episode and still report ok (fixed run 041)

`publish_local()` built the feed, validated it with `verify_feed()`, and
transitioned the ledger. But `verify_feed()` only inspects the items the feed
**contains** -- it iterates `root.findall(".//item")` -- so it is structurally
unable to notice an episode that is no longer there. The feed is rebuilt from
`manifest.json` plus the ledger status on every publish, so anything that drops
an episode out of `interview_episodes()` silently removes a **live** episode
from the feed while `publish` returns `ok: true` with an empty issue list.

Two reachable routes, both proved on real code against episodes 001-003:

- a lost or hand-edited `manifest.json` entry (the manifest is also
  `publish_local()`'s default selection source, so the episode is not even
  preflighted -- it simply ceases to exist for the publish path); and
- a ledger status moved outside the `published*` family.

The detector already existed. `feed_coverage()` asserts exactly this -- every
episode any registry records as published still has a feed item, with each
enclosure on disk at its advertised byte length -- but it was read-only,
CLI-only, and **called by nothing in the publish path**. The documentation told
the operator to run `coverage` as the first command of every slice, which
catches the erasure on the *next* slice, after a push has already taken the
episode off the live feed.

`publish_local()` now asserts it in-band, after `verify_feed()` and **before any
ledger transition**, so a publish that would erase the catalogue leaves no state
behind. The verdict is reported under a `coverage` key beside `verification`.

It grants nothing: it cannot pass an episode `verify_feed()` failed (that
refusal still fires first, with its own message), a non-published episode is
still not owed an item, and the read lane's `verified: true` gate is untouched.

**This is the erasure half of the run-005 silent-skip class.** Runs 005/013/031
each fixed a selector that wrongly *dropped* a record; the gap here was that no
publication gate ever asked whether the resulting feed was *missing* anything.
A check that validates what is present cannot validate what is absent -- when a
gate iterates a collection, ask what it would say about an element that is no
longer in it.

Latent in the now-familiar way: 001-003 are all `published_and_moved` with their
audio on disk, so `coverage` 3/3, `verify ok: true` and `publish ok: true` were
all accurate and all blind. A real republish after the fix is byte-identical
(`feed.xml` md5 unchanged, 3 items, live md5 == local).

Harnesses `/opt/data/tmp/mm_publish_erasure_repro_run041.py` (29/29 against the
unmodified module: `publish ok: true` on a feed that just lost 003,
`verify_feed` ok with an empty issue list, `feed_coverage` catching it on both
routes, and `publish_local` proved not to reference it) and
`mm_publish_erasure_proof_run041.py` (39/39: pre-fix backup still reproduces;
post-fix both routes refused with the episode named and the ledger unmoved;
nothing granted -- healthy publish still passes, a run-038 empty-`<description>`
defect still refuses as *verification* not coverage, a `planned` episode is not
owed an item, both lane selectors unchanged; only `publish_local` differs with
47 functions byte-identical).

Harness notes. Deleting `feed-site/episode-NNN-notes.md` does **not** simulate a
`verify_feed` defect: `publish_feed.main()` re-copies notes and audio from
`episodes/NNN/` on every run, so the damage is repaired before the gate sees it
-- use a defect publish cannot self-heal, such as a missing manifest
`description`. And `feed_coverage()` unions the published set from **both**
`state.json` and `manifest.json`, so it catches a status-route erasure too; an
expectation that it would be blind there was a harness bug, not a code defect.

## The interview gate hashed the audio and compared it to nothing (fixed run 045)

`preflight()` is the interview lane's deterministic publication gate and the
only episode-level check `publish_local()` runs. With `--audio` it computed
`sha256(audio[0])`, stored it in `checks.audio.sha256` -- and compared it to
**nothing**. Every other check it runs scores `script.md` and
`episode-notes.md`: the reviewer panel, both spoken disclosures, the citation
and evidence-boundary checks. None of those can tell which episode's audio sits
in the directory.

The reader already existed in the wrong place. `render_episode()` records the
rendered bytes' digest at `state.json` -> `artifacts.audio_sha256`, and
`reconcile()` compares it (run 043 restored that field after an
artifacts-overwrite bug destroyed it) -- but `reconcile` is **not in the publish
path**. `publish_local()` runs `preflight`, `verify_feed` and `feed_coverage`,
and the latter two inspect feed *structure*. So a swapped mp3 passed the
publication gate with an **empty issue list**, and `publish_feed.main()`
re-copied it into `feed-site/` for the next `push` to deploy.

Proved on real code: with 001's audio replaced by 002's, the pre-fix
`preflight` returned `ok: true` / `issues: []`, the real
`publish --episode 001` exited 0 with `ok: true`, and the swapped bytes reached
`feed-site/episode-001.mp3` -- while `reconcile` on the identical tree returned
`ok: false` naming the digest mismatch. That control is what makes it a finding
rather than a guess: the detector worked and the gate simply never called it.

`preflight` now compares the two. It grants nothing: an **absent** digest stays
acceptable (001-003 lost theirs once to the run-043 bug and are genuinely
published, so refusing a record that predates provenance would be a false
failure -- the same policy `reconcile()` applies), and only a digest that is
present and wrong is refused.

Two lessons:

- **This is run 042's fix, which landed in the read lane only.** Run 042 wired
  `fidelity_gate()` to re-hash a reading's mp3 after run 040 stored a digest no
  reader consumed. The interview lane's gate had the same shape and was never
  revisited, because the digest *did* have a reader -- just not one on the
  publish path. Run 032's lane-asymmetry axis therefore extends again: ask not
  only "does the other lane hold a guard this lane lacks?" but "is this lane's
  reader reachable from the **command the operator runs to ship**?"
- **A field with a reader is not a field with a gate.** `grep -n audio_sha256`
  returned hits in `reconcile` and looked healthy; the question that exposed
  this was which of those hits `publish_local()` can reach.

Harnesses `/opt/data/tmp/mm_interview_provenance_repro_run045.py` (26/26 against
the **unmodified** module, including the `reconcile` control and the
propagation-to-`feed-site` step) and `mm_interview_provenance_proof_run045.py`
(50/50: pre-fix backup still reproduces; post-fix the swap is refused by
`preflight` *and* by the real `publish`, and the corrupted bytes never reach
`feed-site`; nothing granted -- 001-003 still pass with digests matching, a bare
`publish` still preflights all three, an absent digest is accepted yet waives
nothing else, and a truncated mp3, a missing panel and missing audio are each
still refused; exactly **one** function changed with 47 byte-identical incl.
`reconcile`, `publish_local`, `verify_feed`, `feed_coverage`, `review_gate`,
`fidelity_gate` and `render_episode`).

Two harness bugs failed first and neither was a code defect (run 029's rule):
`publish` prints a human summary line before its JSON, so `json.loads(stdout)`
raises -- parse from the first brace; and `publish --episode NNN` selects
**one** episode, so asserting three preflights requires a **bare** `publish`.

## `reconcile()` DELETED the interview lane's audio provenance (fixed run 043)

`render_episode()` records the rendered audio's provenance into the ledger:

    record["artifacts"] = {"audio": ..., "audio_sha256": sha256(output),
                           "turns": len(turns)}

`reconcile()` then rebuilt a `{notes, audio}` dict from disk and **assigned it
over the top**:

    artifacts = {"notes": ..., "audio": [...]}
    rec["artifacts"] = artifacts

`reconcile --write` runs every slice, so the digest and the turn count were
destroyed on the first reconcile after any render, permanently and silently --
nothing re-derives them and `reconcile` still returned `ok: true`. All three
published episodes in this tree carried the fingerprint: a
`rendering -> rendered` transition reading *atomic render complete* (so a digest
was definitely written) beside `artifacts` holding only `{audio, notes}`.

Fixed by **merging** the freshly-derived fields into the existing dict instead
of replacing it, and -- in the same slice -- wiring a reader: `reconcile()`
already has the audio in hand, so it re-hashes it and reports a mismatch as an
issue naming both digests. An **absent** digest is deliberately silent rather
than an issue: 001-003 had already lost theirs to this bug and are genuinely
published, so refusing them would be a false failure. Their digests were
backfilled on evidence (in-pipeline render transition, episode-dir and
feed-site audio byte-identical at the advertised enclosure length, local feed
byte-identical to live, `preflight --audio` passing with a matching digest).

Two lessons:

- **This is run 042's class with the sign flipped.** There the read lane
  *stored* `audio_sha256` and nothing read it; here the interview lane stored it
  and another function *deleted* it. Same field, same tree, opposite failure --
  so when you add a provenance field, grep for both its readers **and** every
  writer of the structure that holds it (`grep -n 'artifacts' pipeline/*.py`).
- **A whole-dict assignment is a silent deleter.** `rec[x] = {...}` discards
  keys another stage owns, and no gate notices because the result is
  structurally valid. Prefer merge semantics for any record more than one
  function writes.

Latent in the now-familiar way: `coverage` 3/3, `verify ok: true` and 3x
`reconcile --write` at 0/0/0 were all accurate and all blind, because the field
they would have checked was the field being destroyed.

Harnesses `/opt/data/tmp/mm_artifacts_clobber_repro_run043.py` (28/28 against
the **unmodified** module: the digest present, destroyed by one reconcile, never
restored, and a swapped mp3 then passing `preflight` and `reconcile` with
nothing left to contradict it) and `mm_artifacts_clobber_proof_run043.py` (39/39:
pre-fix backup still reproduces; post-fix the digest survives three passes and a
swap is refused; nothing granted -- an absent digest stays silent, the run-031
missing-audio refusal, missing notes, the run-008 dedupe at [1,1,1], a `planned`
exemption and the read lane are all unchanged; exactly **one** function changed
with 48 byte-identical incl. `preflight`/`review_gate`/`fidelity_gate`/
`verify_feed`/`feed_coverage`/`publish_local`).

Harness note: the backfill script's integrity assertion false-failed on a
**shallow** `dict()` snapshot, which shares the `transitions` list so appending
mutated both sides. The guard was right and the snapshot was wrong -- deep-copy
the before-state. Nothing had been written when it fired.
