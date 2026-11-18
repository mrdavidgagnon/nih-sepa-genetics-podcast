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
python3 pipeline/robust_pipeline.py registry
python3 pipeline/robust_pipeline.py feedsync
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

`registry` is the read-only companion to `coverage`, and the two answer
different questions. `coverage` proves an episode the registries call
published actually reached the feed; `registry` proves `state.json` and
`manifest.json` agree it exists at all. They are written by independent paths
-- the ledger by the state machine, the manifest at registration -- so a slice
that stops early leaves them disagreeing with nothing to notice. **Run it
alongside `coverage` as the opening audit of every slice.** It replaces the
hand-rolled manifest-vs-ledger one-liner this document used to ask each run to
paste.

`feedsync` is the third read-only opening audit, and it asks the one question
the other two cannot: does the **committed** `feed-site/` still equal what
`publish_feed.py` **generates right now** from the current registries?

Every file in `feed-site/` is derived -- `feed.xml`, each `<base>-notes.md` and
`index.html` all come from `manifest.json` (`title`, `description`, `number`,
`kind`), `read-episodes.json` (`verified`, `coverage`, `source_words`,
`citation`, `title`), `state.json` (the production timestamps `<pubDate>` is
formatted from) and each episode's `episode-notes.md`. Editing any of those
without re-running publish leaves the committed bytes stale, and **every other
audit still passes**, because none of them compares the commit to the
generator:

- `coverage` asks whether every published episode has a feed item and whether
  each enclosure exists at its advertised length -- about the committed feed
  only.
- `registry` asks whether `state.json` and `manifest.json` agree, and never
  reads `feed-site/` at all.
- `verify` scores the committed document against itself and against disk. It
  reads every advertised field, but its expectations come from those same
  committed bytes, so a stale title is perfectly self-consistent.
- `reconcile` compares each `episodes/NNN` directory to its ledger record and
  never reads the feed.
- `drift` compares the **live** bytes to the **local** bytes -- so once a
  stale commit has been deployed, live equals local and the audit passes.

Proven by perturbation against the real catalogue (run 076): a manifest title
edit, a manifest description edit, a stale committed notes body and a rewritten
episode title inside `index.html` each left `coverage`, `registry`, `verify`
and `reconcile` at `ok: true` with **empty issue lists**. `verify_feed()`'s
`index_page` check is the near miss worth knowing -- it reads the page's
`<title>`/`<h1>`, its local hrefs and its `episode-NNN` number set, so it
catches an **omitted** episode and a wrong show name, but not a rewritten
episode title in a list entry, which is a value only the generator knows.

The notes arm matters most: a notes-body edit leaves `feed.xml`
**byte-identical** whenever the numbered citation entries are untouched, and
the notes are a published deliverable carrying the unabridged disclosure, the
evidence boundaries and every Zotero link.

`.mp3` enclosures are excluded deliberately -- they are already audited for
presence and advertised length by `coverage` and actually decoded by the
run-058 duration check, and hashing them every run would make the command
unaffordable.

It renders into a private temporary directory, so `feed-site/` is never
touched; it writes nothing, grants nothing, and is **not** a publication gate
(`publish_local()` and `push_to_remote()` do not call it). `ok: false` with a
populated `diff_sample` means: run `publish --episode NNN` to regenerate,
inspect the diff, and deploy. Healthy state here is `ok: true` with
`notes_checked: 3`, `site_text_checked: 1` and the committed and regenerated
md5s equal.

Three findings, ordered by severity:

- `missing_from_manifest` -- published in the ledger, no manifest entry. The
  dangerous one: the manifest is what `publish_feed.py`'s item derivation and
  `move_verified_sources.py`'s ownership logic read, so the episode is
  invisible to both while the ledger insists it shipped.
- `missing_from_ledger` -- the manifest knows an episode the ledger does not,
  so `status`, the watchdog and the attempt ledger are all blind to it. Worse
  than silence here: `reconcile --write` runs every slice and silently
  **recreates** the record as a `planned` stub, destroying the published
  status rather than reporting the gap.
- `status_divergence` -- both registries know it and disagree about how far it
  got. A ledger `published` against a manifest `published_and_moved` is the
  ordinary Zotero-move lag, reported separately under `benign_move_lag`, and
  does **not** fail the audit. The reverse direction does: a manifest behind
  the ledger means a registration never landed.

Source ownership is checked through `lane_ownership()`, not a bare `sources`
sweep, so one interview plus one reading of the same paper stays legal while
two readings of it are a conflict. A reading **is** required in both
registries here, because `read_lane.sync_durable_state()` mirrors it into both
by design; its registry of record is still `read-episodes.json`. The audit
writes nothing and is **not** a publication gate -- it grants nothing and does
not replace `preflight`/`review_gate`/`fidelity_gate`/`verify_feed`.

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
`published*` family (it needs `ZOTERO_API_KEY` exported). Run it with
`--dry-run` to print the plan without writing anything.

### Only the episode's OWN intake lane is stripped

This is the mover's load-bearing invariant and it is easy to undo by accident.
The intake collection is derived from the **field** the key is registered
under -- `sources` means the key arrived through Summarize, `read_source` means
it arrived through Read -- which is the same discriminator `lane_ownership()`
uses. Each plan entry therefore removes exactly one collection membership.

Until run 054 the mover held a single tuple of both intake keys and removed
**both** from every key it touched. One interview plus one reading of the same
paper is legal in this tree by design (that is precisely why ownership is keyed
on the field name), so publishing the interview of a dual-use paper deleted the
Read membership that was the only durable record David wanted a reading of it,
and publishing the reading deleted a pending Summarize membership the same way.
The affected lane simply went quiet: a Zotero collection edit raises no
deletion event, so the loss is indistinguishable from David unfiling the item,
which is this show's documented signal that he cleared the queue on purpose.

A dual-use key published in both lanes yields **two** plan entries and leaves
each intake exactly once. Every other membership, including the parent
`YF84AUZK`, is preserved and no item is ever deleted.

Two further properties worth not regressing:

- Selection accepts the whole `published*` family from `state.json`, not the
  literal `published_pending_zotero_move` the sibling tree uses. A narrower
  test silently skipped this tree's documented end state `published_and_moved`,
  so re-running the mover after a status bump moved nothing and still exited 0
  (run 011; the same gate-string class as the run-005 `interview_episodes()`
  fix).
- A reading additionally requires `verified: true` in `read-episodes.json`, so
  a source whose fidelity gate failed cannot be filed as produced. The mover
  grants no gate of its own.

`tests/test_move_verified_sources.py` pins all of the above. The version guard
is asserted against the **outgoing `Request` object**, not against a value
handed to an injected fake `put()` -- a mutant that deleted the
`If-Unmodified-Since-Version` header survived the fake-based assertion, because
a fake never exercises the header-building code at all.

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

**Zero declared source keys is refused in BOTH lanes (run 050).** The citation
apparatus in `preflight()` — duplicate ownership, manifest-key-in-notes, and the
numbered-entry / year / metadata-length / Zotero-link loop — iterates
`expected_keys`, drawn from `read_source` for a reading and `sources` for an
interview. Every one of those is an all-of loop, so at **cardinality zero** they
return no findings and `preflight` reported `ok: true` with an empty issue list:
a reading with no citation apparatus whatsoever passed the only episode-level
check `publish_local()` runs. Run 049 guarded the interview half inside the
interview-only quoted-span block; the apparatus itself is lane-shared, so the
reading half stayed open one run longer. Both are now refused, each naming its
own field and registry.

The read lane's reachability was the **stronger** of the two. An interview's
`sources` is hand-written, so an empty list means somebody wrote one. A reading's
`read_source` is *derived* by `read_lane.sync_durable_state()` as
`[item_key] if item_key else []`, with `item_key` itself read as
`entry.get("item_key", "")` — so a registry entry that never recorded an item key
silently becomes `read_source: []` and took the free pass with no hand-editing
anywhere. Harnesses: `/opt/data/tmp/mm_read_sources_waiver_repro_run050.py`
(26 against unmodified code) and `mm_read_sources_waiver_proof_run050.py` (40,
exactly one function changed with 45 byte-identical).

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

Both are **monitoring, not gates**. They grant nothing: `preflight()`,
`review_gate()`, `verify_feed()` and the read lane's `fidelity_gate()` are the
publication gates and none of them consults `status()`.

### `healthy` was pinned False by construction (fixed run 059)

`status()` ran a **deliverables** preflight against every ledger record, so a
`planned` stub was failed for having no `script.md` -- which is what `planned`
*means*. Episode 501 had done exactly that for 53 attempts and was the sole
reason this tree could never report healthy, which made the signal worthless to
the scheduler and to `watchdog()`, which inherits the verdict.

Each episode is now judged by the rules that apply to it, and the inapplicable
findings are **preserved, not discarded** -- under `planned_audit_issues` /
`read_audit_issues`, mirroring the long-standing `legacy_audit_issues`
treatment. Healthy state here is `healthy: true` with 501 reporting
`kind: read`, `preflight_ok: true` and its six findings under
`read_audit_issues`.

Detection is preserved and **extended**:

- `failed`/`blocked`/`rendering` still pin unhealthy regardless of preflight.
- an interview in any production or published state still has to pass
  `preflight()`.
- the run-037 three-part legacy waiver is untouched -- the status literal
  `published` alone still does not confer it.
- **new:** a reading recorded as published whose fidelity gate is not
  `verified: true` in `pipeline/read-episodes.json` is now unhealthy, naming the
  registry. That is the sibling tree's run-422 live-but-unrecorded class, which
  the old classifier was structurally blind to because `status()` calls
  preflight with `enforce_review=False` and so never reached either gate. A
  missing or corrupt registry entry is a **refusal, not a waiver**.

Two ordering constraints worth preserving:

- the reading test comes **first**. The legacy arm keys on the exact status
  `published`, so a reading carrying that status instead of
  `published_and_moved` would be classified as a legacy *interview* and skip
  its fidelity gate. A reading can never be legacy -- the lane postdates every
  episode in this tree.
- this tree's `preflight()` has been lane-aware since run 029, so unlike the
  sibling show a correctly-registered reading already passes the
  interview-rule half. Do **not** port the sibling's reading-waiver branch; it
  fixes a defect this tree does not have.

Covered by 26 tests in `tests/test_status_health.py`.

## Deploy drift (`drift`) -- the live-vs-local byte audit

```sh
python3 pipeline/robust_pipeline.py drift
python3 pipeline/robust_pipeline.py drift --text-only     # doc/manifest-only change
```

Read-only, grants nothing, writes nothing, and is **not** a publication gate:
it does not replace `preflight`, `review_gate`, `verify_feed`, `feed_coverage`
or the read lane's fidelity gate. `verify --remote` asks whether the live feed
parses and its enclosures are fetchable; `drift` asks the strictly different
question of whether the **live bytes equal the local bytes**.

Ported from the sibling show in run 061, after the run-053 census rule (a census
closes as of a date, not forever -- re-check the sibling's *subcommand list*,
not its file line counts).

### Why the existing remote probes could not catch this

Every remote probe in `verify_feed()` is an **existence** probe:

- show notes, cover art and the landing page: HTTP 200 plus a few bytes;
- enclosures: `Content-Range` total only, i.e. deployed byte **length**;
- the deployed feed (run 056): compared to local by **GUID set**, both
  directions.

So a deploy whose notes, cover art, landing page or feed **text** was rewritten
-- or whose enclosure bytes were swapped at the same byte length -- returned
`ok: true` with an **empty issue list**. That verdict is what `publish_local()`
refuses on and what `push_to_remote()`'s wait loop **breaks on** to declare a
deploy live. Proved on real code in run 061: five independent drift classes
passed, with the run-038 and run-056 detectors shown still firing as controls.

`drift` compares text files (`.xml`, `.md`, `.svg`, `.txt`, `.html`, `.json`)
by **md5 over a full GET**, and binaries by deployed byte length from a one-byte
range probe -- so the audit costs kilobytes, not tens of megabytes. A
same-length binary byte swap is therefore still outside its reach; that is a
documented limit of the range probe, not an oversight, and `preflight`'s
`checks.audio.sha256` comparison (run 045) is what covers audio provenance.

### The one retarget this tree needed

`feed-site/` here holds two **gitignored** files the sibling's does not:
`cover.png.bak-run004` and `cover.svg.bak-run004`. `push_to_remote()` copies
every file in `feed-site/` into the clone and then runs `git add -A`, which
**respects `.gitignore`** -- so those two are copied but never committed, and
they correctly 404 live. A verbatim port iterating every file would report two
**permanent false issues** against a perfectly clean deploy.

`_deployable_site_files()` therefore asks `git check-ignore` which files the
deploy would actually publish, deriving the answer from the same mechanism the
deploy obeys rather than duplicating `.gitignore` in a pattern list that could
drift from it. Excluded files are reported under `not_deployed_by_design`, so
the exclusion is visible rather than silent. It is an exclusion for **ignored**
files only: a non-ignored file missing from the live site is still an issue.

This is run 053's rule again -- read the sibling's **assumptions** against this
tree's behaviour, not just its code.

### The converse sweep: what is DEPLOYED that we no longer produce (run 079)

Everything above compares a **local** file to its deployed copy. Every remote
probe in `verify_feed()` does the same: it iterates files that exist here and
asks whether the remote has them. Nothing asked the opposite question -- what
does the remote HAVE that this tree no longer produces?

`push_to_remote()` copies `feed-site/*` into the clone and stages with
`git add -A`, which records additions and modifications and **can never delete
a path the local tree stopped producing**. So anything ever deployed stays
deployed, served to subscribers, forever. Proved on real code against the
unmodified module: a retired episode's enclosure and notes, a stale
alternate-name `feed-old.xml`, a retired `episodes/004/script.md`, a stray
`pipeline/old_publish_feed.py`, and a root page naming the **sibling show** all
returned `ok: true` with an **empty issue list** -- a verdict byte-identical to
a clean deploy, and the verdict `push_to_remote()`'s wait loop breaks on to
declare a deploy live.

`drift` now enumerates the deploy branch with `list_remote_tree()` (git tree
API, not an HTTP crawl -- an orphan is by definition a file no local listing
and no feed reference will ever name, so there is nothing to crawl from) and
reports anything unaccounted under **`remote_only`**, one issue each, plus
`remote_blobs` and an `orphan_audit` status.

**The retarget that matters, if you ever port from the sibling tree.** The
sibling's repo contains only its feed-site payload, so it accounts for a
deployed path by flat basename against `feed-site/`. **This** repo deploys the
whole project -- `episodes/`, `pipeline/`, `tests/`, `README.md`,
`style_guide.md`, `production-log.md`: 77 blobs, 63 of them nested. Copying
that predicate verbatim reports 67 legitimate paths as orphans and makes
`push` permanently red. Here a deployed path is accounted for when the local
tree has that **exact repo-relative path**, or when it is a **flat** path that
`feed-site/` produces (push copies those into the clone root, so they arrive
without their directory). Keyed on the full path and never the basename alone,
so a stale `stale/feed.xml` is not excused by the real flat one. Run 053's
rule again: read the sibling's assumptions against *this* tree's behaviour,
not its code.

`DRIFT_ALLOWED_REMOTE_ONLY` is **empty**, and that emptiness is the finding:
every one of the 77 deployed blobs is a file this tree still produces. Add an
entry only with a reason -- an exemption is a gate with the sign flipped
(run 036). An **un-enumerable** remote is an issue, never a pass. The sweep is
attempted only when the remote is the deploy site, since the site-to-repo
mapping is unknown for any other host; `orphans=True/False` overrides that.

Healthy state here: `remote_blobs: 77`, `remote_only: []`,
`orphan_audit: "completed"`.

**Lesson.** When an audit relates local artifacts to deployed ones, ask which
side it ITERATES. A check that iterates the local set can never see a deployed
file the local set omits -- and a deploy mechanism that only ever adds makes
that blind spot permanent rather than transient. This is run 041's
"a check that validates what is present cannot validate what is absent" with
the direction reversed: here the extra element is on the *remote*, so no local
enumeration can reach it.

Covered by 20 tests in `tests/test_remote_orphan_gate.py`. Reverting to the
pre-fix backup is a **weak** proof for this one (the old module has no
`remote_only_paths` attribute, so all 20 error and that proves only that the
file changed) -- the real proof is a single-fault mutant sweep on the new
structure, 12/12 caught. One mutant initially **survived**: every sweep test
passed `orphans=True`, so hardcoding `attempt = False` left the sweep dead on
the exact path `push` uses while the suite stayed green. Test the
**auto-detect** branch, not only the explicit one.

Covered by 22 tests in `tests/test_deploy_drift.py`, including that neither
`publish_local()` nor `verify_feed()` calls it (it must stay a non-gate).

### `push` now asserts the deployed bytes too (run 077)

`drift` is still **not** an episode gate -- `publish_local()` and
`verify_feed()` continue not to call it -- but it *is* now part of the shipping
command's liveness criterion.

`push_to_remote()` used to declare a deploy live on `verify_feed(..., remote=)`
alone, and every remote probe there is an **existence** probe (the list above).
So a deploy whose `feed.xml` text, show notes, cover art or landing page was
rewritten -- or whose enclosure bytes were swapped at the same byte length --
satisfied the wait loop with an **empty issue list** and was reported live. The
comparator that catches exactly those classes already existed and was
**CLI-only**, so no gate and no shipping command could reach it; the operator's
own live-vs-local md5 habit was the only cover, one slice late.

The wait loop now breaks only when `verify_feed` **and** `deploy_drift` both
pass, and the final `ok` accounts for both. The drift verdict is reported under
its own top-level **`drift`** key -- never folded into `verify_feed`'s dict -- and
its issues are appended to `push`'s issue list.

`_deploy_drift_verdict()` is deliberately **fail-open** on an exception (run
055's rule for a helper on the publish path: a comparator that could raise would
make every deploy impossible, which is worse than the class it guards). A
*definite* `ok: false` is a refusal and is never downgraded.

The same-length binary byte swap remains outside the range probe's reach -- a
documented limit, with `preflight`'s `checks.audio.sha256` (run 045) covering
audio provenance.

Lesson: this is run 041's ("when a read-only audit detects a class the gates do
not, wire it into the gate") combined with run 045's ("ask whether the reader is
reachable from the command the operator runs to **ship**, not merely whether a
reader exists"). `tests/test_deploy_drift.py` pinned that `publish_local` and
`verify_feed` do not call the comparator -- correctly -- but `push_to_remote`
was a **third caller it never named**, and that unnamed third caller was the
defect. When a test enumerates the callers a function must *not* have, ask which
callers it *should*.

Covered by 13 tests in `tests/test_push_deploy_drift_gate.py` (load-bearing: 10
failures/errors against the pre-fix module).

## Tests

```sh
python3 -m py_compile pipeline/*.py
python3 -m unittest discover -s tests
python3 pipeline/robust_pipeline.py coverage
python3 pipeline/robust_pipeline.py registry
python3 pipeline/robust_pipeline.py feedsync
```

This tree **does** have a `tests/` directory -- **473 tests** across twenty-seven
modules, run with `unittest` (there is no `pytest` in either venv). The count
grows with every gate; a figure in this document is a snapshot, so trust
`unittest discover` over the number written here. The older
note claiming no suite exists, and that `unittest discover` failing with
*Start directory is not importable* is expected here, is **obsolete**: a real
failure must be read as a real failure.

Run `coverage`, `registry` and `feedsync` as the opening audit of every slice.
All three are read-only and grant nothing; healthy state is `coverage`
`ok: true` at 3 items / 3 published, `registry` `ok: true` with
`ledger_episodes: 4, manifest_episodes: 3` -- the asymmetry is the 501 no-work
ledger stub, correctly not demanded in the manifest because its status is
outside the published family -- and `feedsync` `ok: true` with the committed
and regenerated feed md5s equal, `notes_checked: 3` and `site_text_checked: 1`.

Run `drift` alongside them whenever the last slice deployed. It is the
read-only live-vs-local byte audit described under *Deploy drift* below;
healthy state is `ok: true` with 10 files `identical` and the two gitignored
cover backups listed under `not_deployed_by_design`.

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

No gate could see it **before run 064**. `preflight()` greps `script.md` and
`episode-notes.md`; `feed_coverage()` matches GUIDs and enclosure byte lengths;
`verify_feed()` reached into `<content:encoded>` but **only to pull `notes.md`
hrefs and confirm the file exists** — never to read the disclosure prose. So
`preflight ok: true`, `coverage ok: true` and `verify ok: true` were all accurate
and all blind, and the episode's own notes file on disk is correct, which made
the defect feed-only. Run 064 added the `disclosure` check to `verify_feed()`,
which reads that prose and is lane-aware; see *The advertised written disclosure
had no reader* below.

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
rather than claiming the string is absent. As of run 064 that narrowing is
itself historical — `verify_feed()` now reads the disclosure prose as well as
the hrefs.

## The remote check never noticed a STALE DEPLOYED feed (fixed run 056)

`verify_feed()`'s remote branch asserted only **"HTTP 200 and at least one RSS
item"** on the deployed `feed.xml`. Every other remote probe — enclosure
byte-range, notes — iterates the items the **local** feed contains and resolves
each asset by filename, so a deploy in which the mp3s and notes landed while
`feed.xml` did not (a partial push, or the documented stale-repo-root trap where
`feed-site/` is updated and the root copy is not) returned **`ok: true` with an
empty issue list**. The assets verified green precisely because they were probed
from the local feed rather than from the one actually serving subscribers.

That verdict is `push_to_remote()`'s success criterion: its wait loop breaks on
`result["ok"]` and the deploy is reported from it, so the one check standing
between a half-finished push and "live" could not see the half that was missing.

Now the deployed item set is compared against the local one by GUID, in **both**
directions: `missing_from_remote` (an episode listeners cannot see) and
`only_on_remote` (the live site is ahead of this tree). Both are issues, both
name the GUID, and the `remote_feed` check records `local_items` /
`remote_items` alongside them. An intact deploy yields two empty sets and the
previous verdict stands unchanged, so this grants nothing and only adds
refusals.

The detector already existed as **operator discipline** — the live-vs-local
`feed.xml` md5 comparison every slice logs. Run 061 wired the byte
comparison itself into the `drift` subcommand, so it is no longer a habit —
see *Deploy drift* below. That is run 041's lesson again: when
a read-only audit catches a class the gates do not, wire it into the gate rather
than leaving it to a habit. Generalizable form: **a remote check that resolves
what to probe from the LOCAL artifact cannot detect that the remote artifact is
stale** — it is verifying this tree's intentions against the remote's assets,
not the remote's own index.

Healthy state here: `verify --remote` reports `local_items: 3, remote_items: 3`
with both drift lists empty.

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

## The read lane's audio provenance never reached `reconcile()` (fixed run 046)

`read_lane.sync_durable_state()` mirrors a reading into `state.json` and
`manifest.json` so it is visible to `status`, the watchdog and duplicate
detection (run 009). It mirrored the **text** artifacts -- `script`, `notes`,
`source_pdf` -- and omitted the audio entirely. `reconcile()` compares
`artifacts.audio_sha256` against the mp3 on disk and reports *"the mp3 was
replaced after it was gated"*; with nothing ever written to that key for a
reading, the catalogue's **post-publication** drift detector was structurally
dead for the entire read lane.

The interview lane has had it all along: `render_episode()` writes
`artifacts.audio_sha256`, and run 043 made `reconcile()` stop destroying it. So
the identical audio swap was caught for an interview and silent for a reading,
in the same tree, by the same function.

Fixed by mirroring `audio_sha256`, the audio path and `audio_bytes` out of the
read registry record `record_verdict()` already populates (run 040). The digest
existed in `read-episodes.json` the whole time -- the evidence was on disk and
simply never reached the registry `reconcile()` reads.

Note this is **not** a duplicate of run 042. `fidelity_gate()` checks the same
property on the **publish path**; `reconcile()` is the out-of-band audit that
notices a swap *after* publication, which no publish-path gate re-runs. Two
readers of one source of truth, covering different moments.

It grants nothing: a record predating run 040 carries no digest, so nothing is
mirrored and `reconcile()` does not refuse it -- the same
absent-is-acceptable/present-and-wrong-refuses policy `reconcile()` and
`preflight()` already apply to 001-003, which lost their digests to the run-043
bug. `fidelity_gate()` still refuses that record on the publish path, unchanged.

Two lessons:

- **A write-side mirror must carry every field its readers gate on.** Run 030
  taught that adding a mirror creates read-side debt; this is the inverse
  omission -- the mirror existed and under-reported, so a reader that was
  working fine went blind for one lane. When mirroring a record, diff the key
  set against what every consumer reads, not against what the lane itself needs.
- **Lane asymmetry recurs on the same axis in a new direction (runs 032/045).**
  Run 045 asked whether a lane's reader is reachable from the publish command;
  this asks whether a lane's *writer* populates what the shared auditor reads.
  Diff the two lanes' state writes, not just their gates.

Latent in the now-familiar way -- no reading has ever registered here, so
`coverage` 3/3, `verify ok: true` and three `reconcile --write` passes at 0/0/0
were all accurate and all blind. It would have fired on the first re-render or
file swap of a real reading.

Harnesses `/opt/data/tmp/mm_read_reconcile_prov_repro_run046.py` (23/23 against
the **unmodified** module, including the interview-lane **control** that proves
the detector works and the missing mirror field was the whole difference) and
`mm_read_reconcile_prov_proof_run046.py` (45/45: pre-fix backup still
reproduces; post-fix the swap is caught, persisted and de-duplicated across
three write passes; nothing granted -- a digest-less record is mirrored empty
and still refused by `fidelity_gate`, truncated/deleted audio and a deleted
`source.txt` still refused, a dropped source sentence and injected commentary
still refused by `read_lane.verify`, a `published*` status never downgraded and
`attempt_log`/`errors`/prior artifact keys preserved; exactly one function
changed with 32 byte-identical and `robust_pipeline.py` untouched).

Harness note: the fixture's spoken disclosure must be the exact
`robust_pipeline.REQUIRED_DISCLOSURE` constant (it is **not** defined in
`read_lane.py`, whose own `DISCLOSURE` is the spoken intro template). Also,
word-fidelity tampering belongs to `read_lane.verify()`, which recomputes
coverage; `fidelity_gate()` reads the **recorded** verdict by design, so
asserting text tampering against it is a harness bug, not a weakened gate.

## The quoted-span gate (run 047)

`pipeline/quoted_span_gate.py` asserts that every `"..."` span in a deliverable
appears in the episode's extracted source text. Ported byte-identical from the
sibling tree (its run 488, a file created after this tree's clone date, so the
run-009/010 line-count census could not have found it) with 20 tests, plus three
regression tests pinning this tree's own catalogue.

    python3 pipeline/quoted_span_gate.py --source episodes/NNN/source-KEY.txt \
        [--source episodes/NNN/source-OTHER.txt ...] \
        --check episodes/NNN/script.md --check episodes/NNN/episode-notes.md \
        --whitelist "a known-benign span"

**Pass `--source` once per paper.** An episode may group several sources (001
has five, 002 has four) and a span is verified if it appears in ANY of them.
Before run 052 `--source` was a plain argparse store, so a repeated flag was
**silently discarded down to the last path** -- no warning, no usage error --
and every span quoted from the other papers reported `SOURCE 0`. On episode 001
that was four real quotations reading exactly like fabrications, which is the
most dangerous false positive this gate has. The whitelist is **not** read from
the manifest by the CLI, so pass the episode's recorded
`quoted_span_whitelist` entries explicitly or its benign own-speech spans show
up as residuals.

Each source is scored independently and the residual sets are intersected --
the same semantics `preflight()` uses on the publish path, so the
operator-facing command and the publication gate agree by construction. The
sources are deliberately **not** concatenated into one haystack: a span
straddling the boundary between two joined papers matches the join while
existing in no single paper (on 001's real extracts, `"Child Study 6d MIT Open
Access"` spans the tail of `source-4UDPRQZR` and the head of
`source-BGWWIUWC`), which would be a quiet weakening of the gate.

Exit 0 = every span verified, exit 1 = at least one span absent from the source.
It **is** now a publication gate, and it grants nothing: `preflight()` runs it for every interview
episode (run 048), reporting under `checks.quoted_spans`, so
`publish --episode NNN` cannot skip it. Before run 048 it had **zero callers**
and was reachable only as the hand-typed command above -- which is how a
misquote inside quotation marks passed a three-reviewer panel and every
deterministic gate in two published episodes.

Three semantics to know:

* **Union-of-sources.** An episode may group several papers, so a span verifies
  if it appears in ANY of the episode's `source-KEY.txt` files. The CLI takes a
  single `--source`, so a bare CLI run on a multi-source episode reports spans
  quoted from the other papers as missing -- expect exit 1 there and trust
  `preflight` instead.
* **Whitelists live in `manifest.json`** per episode, under
  `quoted_span_whitelist`, so the waiver is durable and reviewable rather than
  retyped each slice. Justify every entry in the production log; a waiver is a
  gate with the sign flipped.
* **A missing `source-KEY.txt` is an issue, not a waiver.** The extracts are
  gitignored (verbatim copyrighted text, public repo) and regenerable from
  Zotero `items/<key>/children` -> `items/<attachkey>/file`, or from the
  preprint the episode actually read -- 003's text is arXiv `1803.07170v2`.

Readings are exempt: the read lane's fidelity gate compares the whole script to
`source.txt` word by word, which strictly subsumes a quoted-span check. Run it **before** writing `script.md`, and match each deliverable
against the **source**, never against the other deliverable -- the sibling's
run-474 defect was the notes dropping two words inside quotation marks while the
script was correct, which a script-vs-notes comparison cannot see.

### Its input did not exist here, which is why porting the tool was half the job

No interview episode in this tree had ever retained its extracted source text,
so the gate was unusable the moment it landed -- run 010's lesson (verifying the
stages around a stage is not verifying the stage) applied to an imported tool:
check that each stage's **inputs are obtainable by the actor that will run it**.
The 10 source parents of 001-003 were re-fetched from Zotero
(`items/<key>/children` -> `items/<attachkey>/file`, extracted with the sibling
venv's `pypdf`); 9 of 10 succeeded. `EIUADNKU` (003's only source) has **no
stored PDF attachment** -- consistent with the production log, which records it
as read from the arXiv preprint `1803.07170v2` -- so 003's spans remain
unverifiable until a PDF is attached.

### `source-*.txt` is gitignored and must stay that way

Those files are verbatim copyrighted paper text and this repository is
**public**. They are regenerable verification inputs, not deliverables. The
pattern `source-*.txt` was added to `.gitignore` in the same slice that created
them; do not commit them and do not "fix" that ignore rule.

### What the first real run found

Episode 001's script quoted a scale label as `"good for other people to have"`
while Awad/Bonnefon's text reads *"a good **algorithm** for other people to
have"* -- a word dropped inside quotation marks, on a **published** episode,
past a three-reviewer panel and every deterministic gate. Corrected to the
source's exact words (script only; the notes never carried the span -- verified
by per-file count, not assumed). The other four source-0 hits were the benign
classes the sibling skill documents: the Host's own rhetorical framing
(`"most people feel this way"` / `"the machine shall do this"`), a dismissive
paraphrase the script itself coins (`"aggregation is hard."`), and a
bibliographic title the notes quote in their own reference list. Only an
**author-attributed** span with source 0 is the blocking class -- triage every
hit before filing it, and prefer `--whitelist` to loosening the checker.

Lesson: the reviewer panel and `preflight` both read the script against the
*citation record*, never against the *source text*, so a misquote inside
quotation marks was invisible to every gate this pipeline had. A gate that
derives both sides of its comparison from the deliverables cannot see fidelity
to the paper.

## `publish` gated only the episodes you NAMED, not the ones it ships (fixed run 055)

`publish_local()` preflights its `selected` set -- the `--episode` arguments, or
every manifest episode for a bare `publish`. That set controls which ledger
records transition, and that is all it ever controlled. It does **not** bound
the blast radius: `publish_feed.main()` rebuilds the **whole feed** from its own
derivation (`interview_episodes()` plus `read_episodes()`) and re-copies every
emitted episode's audio and notes into `feed-site/` for the next `push` to
deploy.

So `publish --episode 001` re-shipped every other episode with **no check run
against it**. Proven on real code in both lanes, each returning `ok: true` with
an empty issue list:

- an interview whose `review-panel.md` was missing (`preflight` refuses it
  individually) stayed in the rebuilt feed and had its audio re-copied;
- a **reading whose audio was swapped** after its verdict -- the run-042
  provenance refusal -- shipped the wrong paper's bytes to
  `feed-site/episode-990-reading.mp3`.

The reading case is the sharper one: `read_episodes()` emits on the registry's
`verified` flag alone, and nothing on the publish path re-derived it. A bare
`publish` covered the interview lane only by the accident of the manifest and
the feed derivation agreeing, and never covered the read lane at all, since a
reading's registry of record is `read-episodes.json`.

Fixed by gating `sorted(set(selected) | _emitted_episode_numbers())`. The new
helper reads **publish_feed's own derivation** rather than re-implementing it,
so the gate's scope cannot drift from what actually gets emitted; it is
deliberately **fail-open** (an unimportable derivation returns the empty set and
the previous selection-only behaviour stands), because a helper that could raise
would make every publish impossible instead of degrading. Legacy exemptions are
unchanged and a non-emitted `planned` stub is still not demanded.

This is run 041's erasure check with the sign flipped: that one asks whether the
feed **lost** an episode it should carry, this asks whether it **carries** one
nothing gated.

**Lesson that generalizes: a gate's scope must match its command's blast
radius.** When a function takes a selection argument, ask whether that argument
actually limits the side effects -- here `selected` named which *records moved*
while the *whole feed and every enclosure* were rewritten regardless. Runs
029/045 asked whether a gate is *reached* by the command the operator runs;
this asks the converse, whether everything that command *touches* is gated.

Harnesses `/opt/data/tmp/mm_read_publish_gate_repro_run055.py` (13/13 against
the unmodified module) and `mm_publish_scope_proof_run055.py` (38/38: pre-fix
reproduces both lanes; post-fix refuses both with `feed.xml` unchanged and the
bytes never reaching `feed-site/`; nothing granted -- the healthy catalogue
still publishes, a gate-clean reading still ships and is itself gated now, a
planned stub is not demanded, the helper is fail-open; exactly one pre-existing
function changed with `preflight`/`review_gate`/`fidelity_gate`/`verify_feed`/
`feed_coverage`/`registry_audit`/`reconcile`/`push_to_remote` byte-identical).
Regression tests in `tests/test_publish_scope_gate.py` (suite 64 -> 72), proven
load-bearing: 6 failures against the pre-fix module.

**Harness trap, a harness bug not a code defect (run 029's rule).** A stale HITL
`publish_feed.py` has sat in `/opt/data/tmp` since Oct 24, and `publish_local()`
imports `publish_feed` by **bare name** -- so leaving `/opt/data/tmp` on
`sys.path` runs the **sibling show's** feed builder against this tree. It
presents as a `FileNotFoundError` deep inside `atomic_copy` pointing at
`/opt/data/feed-site/`, nothing like an import error. Drop the scratch dir from
`sys.path` after importing a helper from it, put each scratch tree's `pipeline/`
at the front, and `sys.modules.pop("publish_feed")` between trees or every later
tree silently reuses the first one's builder.

## The cover art the feed advertises is gated (run 057)

`verify_feed()` checks the artwork, not just the enclosures and notes. The feed
names `cover.png` in **five** slots -- the channel `<itunes:image href>`, the
channel `<image><url>`, and one `<itunes:image href>` per item -- and until run
057 **nothing read any of them**. Reported under `checks.cover_art` with the
advertised hrefs, the deployed byte count, and the root/deployed sha256 pair.

Four refusals, no waiver (an advertised file that 404s is a defect for an import
too -- run 036's "a waiver is a gate with the sign flipped"):

- `missing local cover art <name>` -- the file the feed points at is absent
- `local cover art <name> is empty`
- `cover art <name> differs between the tree root and feed-site/` -- naming both
  digests, because `publish_feed.py` has **no copy site for the cover**: unlike
  every episode mp3 and notes file, the two copies are hand-kept in sync, so
  editing one and forgetting the other deploys artwork nobody approved
- `remote cover art check failed for <url>` -- the deployed cover must answer 200

An **absent tree-root copy** is deliberately *not* an issue: the feed never
references it, so only a present-and-different root copy is drift.

Why it mattered: `verify_feed()` is what `publish_local()` consults before
shipping and its `ok` flag is `push_to_remote()`'s success criterion, so a
deploy whose artwork never landed reported itself live while every podcast
client showed a broken image.

### ...and it is now DECODED, not merely measured (run 074)

Run 057's four refusals above are all **existence** refusals: present,
non-empty, root copy equal to the deployed copy, remote 200. Every one of them
is satisfied by garbage of the right length. Run 058 found the identical shape
one asset over -- "enclosures are verified by byte length, which garbage at the
right size satisfies" -- and closed it for **audio** by decoding the mp3. The
artwork stayed on the measured-but-never-decoded side of that line, and
`cover_art` recorded no format, width or height at all.

Proved against the unmodified module: **five single-fault covers each shipped
`ok: true` with an EMPTY issue list**, and an intact cover was
*indistinguishable* from all five.

- a file of pure NUL bytes at exactly the right length -- `local_bytes` reports
  healthy and `site_sha256 == root_sha256` **because both copies are garbage**
- a **truncated** PNG, which keeps the `\x89PNG` signature, so any magic-byte
  sniff passes and only a real decode catches it
- a **CRC-corrupt** PNG at *identical byte length* with signature, IHDR, IDAT
  and IEND all intact -- the case neither a sniff nor a size comparison can
  structurally see
- a **JPEG** saved as `cover.png`, which decodes fine, so a decode-only check
  is not enough: all five slots advertise a `.png`, so the **format** must be
  read
- a valid, decodable **200x120** PNG -- a directory rejects the whole show for
  a non-square or undersized cover, and nothing here read width or height

`decode_png()` is a real decode: signature, every chunk walked at its declared
length, **each chunk's CRC-32 verified**, IHDR's width/height/bit-depth/colour
type read, IDAT required, IEND required, and the concatenated IDAT payload
zlib-decompressed. It never raises -- a bad cover must become an issue, not
crash the audit -- and it **names the container it actually found** (`file is a
jpeg, not a PNG`), which is what makes the issue actionable.

New refusals, no waiver (run 036 again -- an asset a client cannot render is a
defect for an import too):

- `cover art <name> is not renderable: <reason>`
- `cover art <name> is WxH, which is not square`
- `cover art <name> is WxH, below the 1400x1400 minimum`
- `cover art <name> is WxH, above the 3000x3000 maximum`

`checks.cover_art` now also reports `decoded`, `format`, `width` and `height`.
Dimensions are reported **even when the decode fails**, so the issue carries
what the operator needs.

**Stdlib only, deliberately.** This tree's interpreter is 3.14, where `imghdr`
was *removed*, and PIL is not a dependency -- so the gate is a `zlib`+`struct`
chunk walk and adds no install surface. A test pins that no PIL/imghdr import
appears.

Why no other audit covered it (scoped by control, run 073's rule):
`feed_coverage()` audits enclosures; `registry_audit()` relates ledger to
manifest; `deploy_drift()` compares **local bytes to remote bytes**, so
identical garbage on both sides is "no drift"; and `publish_feed.py` has no
copy site for the cover, which is *exactly why* a bad export lands in both
copies at once and the root/deployed digest pair agrees. An **empty** file is
the control that bounds the claim: run 057's size arm already refused that one,
so the unread classes are all **right size, wrong bytes**.

Two lessons:

- **Run 058's question had one asset left.** 058 established that a probe must
  *decode* rather than *measure*, and applied it to audio only. When a fix
  answers a general question in one place, sweep every artifact the same
  question reaches -- the census axis here is not the field level (071) or
  per-element-vs-aggregate (072) but **measured vs decoded**.
- **Completing a fixture is not relaxing a gate.** Twelve pre-existing suites
  wrote a cover of `PNG signature + filler` -- a file `publish_feed.py` and any
  real export are incapable of producing, with no IHDR, IDAT, IEND or CRCs.
  They were asserting on feeds that cannot exist, so they gained a real
  `_make_fixture_png()` (the direct analogue of run 058's `_make_fixture_mp3()`,
  added for the same reason). 27 failures were fixture incompleteness, not a
  gate finding.

Harnesses `/opt/data/tmp/mm_cover_decode_repro_run074.py` (38/38 against the
**unmodified** module) and `mm_cover_decode_proof_run074.py` (59/59: pre-fix
still reproduces; each class refused and named; **nothing granted** -- the real
live feed's verdict is byte-identical pre/post, the 1400/2048/3000 boundary
sizes still pass, an absent root copy still waives, and run 057's
missing/empty/drift arms plus 066/073/058/038 all still bite; exactly one
pre-existing function changed with 65 byte-identical incl.
`preflight`/`review_gate`/`fidelity_gate`/`feed_coverage`/`publish_local`/
`push_to_remote`/`deploy_drift`; 3x `verify_feed` mutates zero bytes). A
**mutant sweep** on the new decoder (run 054's rule: reverting to a backup is a
weak proof -- mutate the new structure to test the tests) found two arms decide
the **message** rather than the verdict: the chunk walk refuses a JPEG with or
without the signature check, and `zlib.decompress(b"")` raises, so the IDAT arm
refuses a pixel-less file either way. Both were first read as surviving
mutants; both are naming arms, which is a finding about the arms rather than a
weakness. Tests `tests/test_cover_decode_gate.py` (24), suite 395 -> **419**,
load-bearing: 29 failures/errors against the pre-fix module.

## The advertised `<itunes:duration>` is gated (run 058)

`verify_feed()` checks the duration every item advertises against the **decoded**
audio. Each item carries an `<itunes:duration>` that `publish_feed.py` derives
from `duration()`, which parses ffmpeg stderr and returns the literal string
`00:00:00` whenever no `Duration:` line is found -- and until run 058 **nothing
read the emitted value**. Reported under `checks` as `name: "duration"` with the
advertised string, its parsed seconds and the real decoded seconds.

Four refusals, no waiver (run 036 -- a client that reads `00:00:00` renders an
unplayable episode for an import too):

- `feed item for episode <N> has no <itunes:duration>`
- `... has a malformed <itunes:duration> <value>; expected HH:MM:SS`
- `... advertises <itunes:duration> 00:00:00, which is publish_feed.duration()'s
  failure sentinel for an mp3 it could not decode`
- `enclosure <name> ... could not be decoded, so its advertised duration
  describes nothing; the file is the right byte length but is not playable audio`
- `duration mismatch for <name>: the feed advertises <X> but the audio decodes
  to <Y>s` (tolerance `DURATION_TOLERANCE_SECONDS = 2.0`, since
  `publish_feed.duration()` rounds to whole seconds)

A **missing local enclosure** is already its own issue, so the duration block
stays silent there rather than double-reporting.

Why it mattered: enclosures are checked by **byte length**, which a file of
garbage at the right size satisfies, and `preflight()` sizes and hashes the audio
**without ever decoding it**. So this is the only check in the pipeline that
proves an enclosure is real, playable audio rather than bytes of the right
length. `verify_feed()` is what `publish_local()` consults before shipping and
its `ok` flag is `push_to_remote()`'s success criterion.

This is the run-042/045/057 axis once more: an advertised per-item field with
zero readers. The cover art (057) and the deployed item set (056) were the
previous two; the `<pubDate>` followed in run 062 below. A field's **value**
was a further dimension: every advertised URL was only ever read for its final
path segment, gated in run 063, and the `<guid>` value in run 065. Run 066
then found the enumeration had been scoped to *items* the whole time -- the
**channel's own identity**, the show's name, was unread in all four slots.
**Enumerate every field the artifact advertises and confirm each is probed --
then ask whether the probe reads the whole value, and whether the enumeration
covered the channel as well as the items
Run 074 adds the axis that closes 058's own question: ask whether the probe
**decodes** the asset or merely **measures** it -- the cover art was existence-
checked from 057 to 074 while every byte of it could be garbage.**


## The advertised `<pubDate>` is gated (run 062)

`verify_feed()` checks the publication date every item advertises against the
**production event the durable registries record**. Reported under `checks` as
`name: "pubdate"` with the advertised string, the evidence source it was
compared against, and the drift in seconds.

Until run 062 **nothing read it**: `pubDate` appeared zero times in
`robust_pipeline.py` and in no test. `publish_feed.py` derives an interview's
value from `production_dates()`, which mines `state.json` for the `rendered`
transition (falling back to `published`), and falls back to the
`LEGACY_PUB_DATE` constant `'Wed, 26 Aug 2026 03:45:00 +0000'` whenever no such
event is found; a reading falls back to the same constant on an unparseable
`built_at`. **That constant is a failure sentinel** in exactly the sense
`duration()`'s `00:00:00` is -- it means "no production date was available" --
and a fully-produced episode shipping it advertises itself as ~2.5 months
older than it is.

The consequence is not cosmetic. **A feed is ordered by this field**, so a
sentinel date buries a new episode below the whole back catalogue in every
date-sorted client, and a future date pins an item to the top forever. Neither
is visible anywhere else: the enclosure, duration, cover, landing-page and
deployed-item-set checks all pass on an item whose date is wrong.

Four refusals:

- `feed item for episode <N> has no <pubDate>`
- `... has a malformed <pubDate> <value>; expected an RFC 2822 date`
- `... advertises a <pubDate> <X> that is <N> days in the future, which pins it
  to the top of every date-sorted client` (allowance
  `PUBDATE_FUTURE_ALLOWANCE_SECONDS = 86400`, for clock skew, not scheduling)
- `pubDate mismatch for episode <N>: the feed advertises <X> but the <source>
  records <Y> (<N> days apart); re-publish so the date reflects production`
  (tolerance `PUBDATE_TOLERANCE_SECONDS = 120`, absorbing formatting and
  timezone rounding only)

Like the duration check, **the advertised value is never its own evidence**.
`_expected_pubdate_epoch()` re-derives the expected moment from the same data
`publish_feed.py` mines -- the ledger's `rendered`/`published` transition for an
interview, `read-episodes.json`'s `built_at` for a reading -- so the comparison
rests on the registries rather than on the feed.

**No waiver for a legacy import** (run 036 -- a waiver is a gate with the sign
flipped). A genuine import is accommodated by **evidence** instead: the
registries hold no dated production event for it, which is precisely why
`publish_feed.py` emits the sentinel for it, so there is nothing to compare and
the check says so (`expected_source: "none: no production event in the
registries"`). An import with an **absent or malformed** date is still refused.

Two things worth keeping:

- **Three existing test fixtures were incomplete, not findings.** Making
  `pubDate` a gated field exposed `test_cover_art_gate`, `test_duration_gate`
  and `test_index_page_gate` as carrying item fixtures with no `pubDate` --
  run 058's own lesson about its 67 bytes of ID3 padding, recurring. They were
  completed (and given their own scratch ledger, since they had been reading
  the real `pipeline/state.json`), never the new gate relaxed.
- **A fixture must advertise what `publish_feed.py` would actually emit.** The
  proof harness's first "genuine import" fixture carried a *dated* `published`
  transition, which `production_dates()` mines -- so publish_feed would emit
  that real date and the sentinel genuinely was wrong. The gate was right and
  the fixture was dishonest (run 029's rule).

Harnesses `/opt/data/tmp/mm_pubdate_repro_run062.py` (17/17 against the
**unmodified** module, with the duration and cover detectors shown still firing
as controls) and `mm_pubdate_proof_run062.py` (47/47: pre-fix still reproduces;
nothing granted -- intact feed passes with a verdict identical pre/post,
`pubdate` the only added check name, timezone-equivalent and sub-tolerance dates
tolerated, and the run-038/057/058/060 plus enclosure-length and
missing-enclosure gates all still bite; exactly one pre-existing function
changed, 56 byte-identical incl. `preflight`/`review_gate`/`fidelity_gate`/
`feed_coverage`/`publish_local`/`reconcile`/`registry_audit`/`push_to_remote`/
`status`/`deploy_drift`). Tests `tests/test_pubdate_gate.py` (suite 168 ->
**187**), load-bearing: 15 of 19 fail against the pre-fix module.


## The advertised written disclosure had no reader (fixed run 064)

`<content:encoded>` is a **published deliverable** — a podcast client renders it
as the episode description — and it carries the show's mandated **written**
disclosures. `publish_feed.py` builds it independently of the episode's files,
via `notes_html()` / `read_notes_html()`, branching on `preproduced_episodes()`
and the read manifest. So the disclosures `preflight()` approves in `script.md`
and `episode-notes.md` are **not** the ones subscribers receive, and a wrong
branch was invisible to every check: `robust_pipeline.py` mentioned
`content:encoded` exactly twice, both inside the block that pulls `notes.md`
hrefs out of it. The hrefs were probed; the prose around them was not.

`preproduced_episodes()` said so in its own docstring — *"No gate inspects
`<content:encoded>`, so preflight/verify/coverage all stay green on it"* — which
documented the hole instead of closing it (run 042's lesson: when a fix names a
property no gate reads, wire a reader in the same slice).

Four reachable classes, each returning **`ok: true` with an EMPTY issue list**
from `verify_feed` local *and* `--remote`, plus `coverage` and `preflight` — the
verdict `publish_local()` refuses on and `push_to_remote()`'s wait loop breaks on
to call a deploy live:

- an interview advertising the **pre-produced provenance** (claims David supplied
  the audio and that nobody reviewed it, while **losing both** the
  fictional-correspondent and AI-generated disclosures)
- an interview advertising the **reading** disclosure (tells listeners Rowan does
  not appear, in an episode built on Host/Rowan dialogue)
- a reading advertising the **synthetic-interview** disclosure (names Rowan in a
  verbatim reading — exactly what `read_notes_html()` exists to prevent)
- the block **emptied or absent** entirely (every written disclosure gone)

Fixed with a lane-aware `disclosure` check in `verify_feed()`'s per-item loop,
reported under `checks` with the lane, char count and any missing phrases. Lane
comes from the same discriminators the rest of the pipeline uses — `is_reading()`
for the read lane, and the manifest `preproduced` flag for supplied audio, a
property of the **record** and never of the episode number (run 036). **No legacy
waiver**: an empty disclosure is a defect for an import too. Required phrases are
verbatim substrings of the corresponding `publish_feed.py` branch, kept to
phrases rather than whole paragraphs so ordinary editorial rewording does not
false-fail.

This is the **run-042/045/056/057/058/062/063 axis** once more — an advertised
field with zero readers. 056 was the deployed item set, 057 the cover art, 058
the duration, 062 the `pubDate`, 063 the URL prefix, 065 the GUID, 066 the
show's own name; this is the
one field whose
**content is a compliance statement**, so the failure mode is not a broken asset
but a false or missing legal disclosure shipped under a green gate. The
generalizable move stands: enumerate every field and URL class the artifact
advertises and confirm each is probed — and for a field whose *value* is prose,
ask whether anything reads the prose or only the markup inside it.

Latent as always: `coverage` 3/3, `registry` ok, `verify --remote` ok, `drift` ok
and 3× `reconcile` 0/0/0 were all accurate and all blind.

Harnesses `/opt/data/tmp/mm_encoded_disclosure_repro_run064.py` (35/35 against
the **unmodified** module, with the run-058 duration, run-057 cover and run-038
empty-description detectors shown still firing as controls) and
`mm_encoded_disclosure_proof_run064.py` (54/54: pre-fix still reproduces; all
four classes refused and named; nothing granted — intact tree and intact deploy
pass with a verdict identical pre/post, `disclosure` the only added check name, a
*genuine* `preproduced` record still accepted while a declared one missing the
statement is refused, and run-038/057/058/063/enclosure/run-036/unparseable gates
all still bite; exactly one pre-existing function changed, 60 byte-identical incl.
`preflight`, `review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `reconcile`, `registry_audit`, `status`, `deploy_drift`;
`publish_feed.py` untouched). Tests `tests/test_disclosure_gate.py` (suite
202 → **220**), load-bearing: 17 of 18 fail against the pre-fix module.

**Twelve pre-existing tests failed on first run — incomplete fixtures, not
findings** (the run-058 class). Five fixture feeds carried **no
`<content:encoded>` at all** and one carried a block holding only a notes href
with no disclosure prose. Completed them rather than relaxing the gate. Trap
worth copying: the first completion inserted a block advertising
`episode-001-notes.md`, which the **pre-existing** href probe then demanded on
disk — six tests failed with *missing local notes file*. That is the older gate
working correctly on a fixture now advertising an asset it never had; the right
block carries the disclosures and no href, except in
`test_advertised_base_gate.py` where the href is load-bearing for run 063 and
the disclosures were added **alongside** it.

## The advertised URL PREFIX had no reader (fixed run 063)

`verify_feed()` now gates the scheme, host and directory every absolute URL in
the feed points at, reported under `checks` as `name: "advertised_base"` with
the advertised URLs, the distinct bases they resolve under, and any
non-absolute URL found.

Until run 063 **nothing read it.** Every check reduced an advertised URL to
`Path(urlparse(url).path).name` and then rebuilt the URL it actually probed
from `FEED_BASE`/`remote` -- enclosures, cover art and show notes alike. So the
checks verified this tree's *intentions* against this tree's *own* base and
were structurally unable to notice that the published feed points somewhere
else. `publish_feed.py` carries its own hardcoded `BASE_URL` and
`robust_pipeline.py` carries `FEED_BASE`; the two constants were never related
by any reader, and `netloc` appeared nowhere in the pipeline.

Proved on real code, each returning `ok: true` with an **empty issue list** from
`verify_feed` local *and* `--remote`, from `deploy_drift` and from `coverage` --
the verdict `publish_local()` refuses on and `push_to_remote()`'s wait loop
breaks on to call a deploy live:

- every asset repointed at the **sibling show**, which would hand Moral Machines
  subscribers Human in the Loop's audio -- the GUID collision this show's docs
  call a hard bug, arriving through the URL instead;
- a **one-character** wrong repo slug (`...-podcasts`);
- an entirely **foreign host**;
- a **relative** enclosure URL, which is invalid in RSS and unresolvable for
  every client.

Four refusals now: a URL under no expected base, a URL carrying a forbidden
cross-show substring, a non-absolute enclosure/artwork URL, and a feed
advertising no absolute URL at all. Deliberately **not** keyed on `remote` --
where the feed sends subscribers is a property of the published bytes, the same
whether or not this run probes a deployment -- and with **no legacy waiver**
(run 036): an imported episode's enclosure must still resolve.

**A prefix test needs a path boundary.** My first implementation used a bare
`startswith`, which accepts `.../nih-sepa-genetics-podcasts` because this
show's base is a string prefix of it. `_under_advertised_base()` requires the
next character to be `/` or nothing. The proof harness caught this in my own
fix, which is the argument for writing the wrong-slug case before believing the
gate.

**Fixtures completed, not gate relaxed.** Twelve pre-existing tests failed once
the prefix became gated: five fixture files advertised a placeholder
`https://example.invalid` host. That is run 058's trap exactly -- making a
deliverable gated exposes an **incomplete fixture, not a finding** -- so each
fixture now advertises the real base, verified as a pure host swap with no other
line touched.

Blast radius: exactly **one** pre-existing function changed (`verify_feed`), one
added (`_under_advertised_base`), **59 byte-identical** including
`preflight`/`review_gate`/`fidelity_gate`/`feed_coverage`/`publish_local`/
`push_to_remote`/`reconcile`/`registry_audit`/`status`/`deploy_drift`.
`publish_feed.py` untouched. Harnesses
`/opt/data/tmp/mm_advertised_base_repro_run063.py` (30/31 against the
**unmodified** module, with the run-057 cover and run-058 duration detectors as
controls still firing; the one failure was a harness bug -- `publish_local`
raises on `result["issues"]` rather than reading an `ok` key) and
`mm_advertised_base_proof_run063.py` (48/48). Tests
`tests/test_advertised_base_gate.py`, 15 tests, suite **187 -> 202**, proven
load-bearing: **13 of 15 fail** against the pre-fix backup.

One of its tests closes the original hole directly:
`test_the_expected_base_matches_publish_feeds_own_constant` asserts the two
hardcoded base constants agree, which nothing had ever checked.

## The advertised `<guid>` value had no reader (fixed run 065)

A GUID is the subscriber's **permanent identity** for an episode: a podcast
client keys its played / downloaded / queued state on it, so a changed GUID
re-delivers an old episode as new and a **colliding** GUID makes one episode
shadow another. This show's docs call a cross-show GUID collision *a hard bug*.

Until run 065 **nothing read the value**. Every consumer reduced it to
something else:

- `_feed_item_number()` — `re.findall(r"episode-(\d+)", guid) or ... url`
- `verify_feed()` — local vs remote GUID **sets** (run 056)
- `verify_feed()` — `len(guids) != len(set(guids))`, duplicates only
- `feed_coverage()` — the same `episode-(\d+)` derivation

So the **prefix** was unread, the lane **suffix** was unread, and the GUID's
episode number was never compared against the enclosure's — the `or`
short-circuits, so once the GUID yields digits the URL is never consulted.
`robust_pipeline.py` did not contain the string `moral-machines` at all.

Four classes each returned **`ok: true` with an EMPTY issue list** from
`verify_feed` (the verdict `publish_local()` refuses on and `push_to_remote()`'s
wait loop breaks on): a **cross-show prefix** (`human-in-the-loop-episode-001`),
a GUID with **no show prefix**, an interview carrying the read lane's
`-reading` marker, and a GUID whose episode number **disagrees with its
enclosure**.

**The sharpest part: run 063 already had the guard.**
`FORBIDDEN_ADVERTISED_SUBSTRINGS = ("human-in-the-loop",)` was added for exactly
this cross-show hazard but scoped to advertised **URLs** — one field away from
the field the docs name as the hard bug. The repro keeps that as a control: the
identical substring in an enclosure URL **is** refused while the same substring
in the GUID ships green.

Fixed with a lane-aware `guid` check in `verify_feed()`'s per-item loop,
reported under `checks` with the lane, the GUID, `prefix_ok` and both derived
numbers. Lane comes from `is_reading()`, a property of the **record** and never
of the episode number (run 036). **No legacy waiver** — an import's GUID is the
subscriber's identity just the same.

Two lessons:

- **A guard installed for a hazard is not a guard on every field that hazard
  reaches.** Run 063 correctly identified the cross-show risk and covered the
  URL; the GUID is the *other* field a retargeting slip corrupts, and it is the
  one the docs single out. When you add a guard against a named hazard,
  enumerate every field that hazard can appear in.
- **A fallback chain hides the thing it recovers.** `guid or url` makes the
  number robust and makes the GUID's own conformance untestable — a tokenless
  GUID still yields the right number, so `coverage` is right to stay green while
  the published identity has silently stopped following the scheme. When a
  derivation has a fallback, ask what the fallback is covering for.

Latent as always: `coverage` 3/3, `registry` ok, `verify --remote` ok, `drift`
ok and 3× `reconcile` 0/0/0 were all accurate and all blind.

Harnesses `/opt/data/tmp/mm_guid_repro_run065.py` (39/39 against the
**unmodified** module, with the run-063 URL guard and run-064 disclosure gate
shown still firing as controls) and `mm_guid_proof_run065.py` (54/54: pre-fix
still reproduces; all classes refused and named; nothing granted — intact tree
passes with a verdict identical pre/post, `guid` the only added check name, a
genuine reading GUID accepted, and
run-038/057/063/064/058/enclosure/run-036/unparseable gates all still bite;
exactly one pre-existing function changed, 60 byte-identical incl. `preflight`,
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `reconcile`, `registry_audit`, `status`, `deploy_drift`,
`_feed_item_number`). Tests `tests/test_guid_gate.py` (suite 220 → **232**),
load-bearing: 11 of 12 fail against the pre-fix module.

**One pre-existing test failed — an incomplete fixture, not a finding** (the
run-058 class again). `test_disclosure_gate.py` hardcoded one
interview-shaped GUID in its `FEED_TEMPLATE` and reused it for the **501
reading** cases, while `read_lane.register()` writes
`episode-NNN-reading-<itemkey>`. Gave the fixture a lane-correct GUID rather
than relaxing the new gate.

Two harness bugs, neither a code defect (run 029's rule): a case asserting the
GUID/enclosure disagreement "passes" was wrong — the class **is** refused, but
only **incidentally**, by the landing-page cross-check noticing the
episode-number set moved, with no issue naming the GUID; and a case expecting
`coverage` to miss a tokenless GUID was wrong because the `or` URL fallback
recovers the number. Both were corrected to claim only what is true, which is
what makes the finding precise: the defect is that no issue ever **names** the
GUID.

## The channel's own identity -- the show name -- is gated (run 066)

`verify_feed()` checks the show's name in all four slots `publish_feed.py`
writes it to, reported under `checks` as `name: "show_identity"` (channel title
and artwork caption) and as `page_title` / `page_h1` on the existing
`index_page` check:

```
<channel><title>            the show's name in every podcast client
<channel><image><title>     the artwork's caption
index.html <title>          the deployed landing page's name
index.html <h1>             the landing page's heading
```

Until run 066 **nothing read any of them**. Runs 056-065 enumerated and gated
every advertised **per-item** field (deployed item set, cover art, duration,
`pubDate`, URL base, written disclosure, GUID) and the channel's **assets**
(the artwork href, the image url, `index.html`'s existence and its episode
list) -- the enumeration was scoped to items and assets, and the channel's
identity *text* fell outside it. `robust_pipeline.py` mentioned both show names
only in prose (one comment, one docstring) and held no test on either.

Those four slots are the **exact ones run 004** found still reading *"Human in
the Loop: Moral Machine Edition"* after this tree was cloned from the sibling
show, and retargeted **by hand**. Nothing has held them since, so a retargeting
slip, a bad merge from the sibling tree, or an edit to `publish_feed.py`'s
hardcoded strings re-ships the sibling show's name to subscribers. Classes
proved reachable, each `ok: true` with an **empty issue list** from
`verify_feed` -- `publish_local()`'s gate and `push_to_remote()`'s success
criterion:

- the channel `<title>` set to the sibling show (the run-004 regression)
- the channel `<title>` emptied entirely (a nameless feed)
- the `<image><title>` drifting from the channel title
- `index.html` naming the sibling show while the feed is correct

**Run 063's guard was one field away and in the wrong form.**
`FORBIDDEN_ADVERTISED_SUBSTRINGS` was installed for exactly this cross-show
hazard, but scoped to advertised URLs *and* expressed as a slug
(`"human-in-the-loop"`), which cannot match the sibling show's prose name
(`"Human in the Loop"`) even where it is applied. Hence a separate
`FORBIDDEN_SHOW_TITLES` beside `SHOW_TITLE`. No legacy waiver (run 036): a feed
with the wrong name or no name is wrong for an import too. Surrounding
whitespace is stripped; a wrong-case name is refused, because an identity is
exact.

The lesson that generalizes: **a guard's form must match the field's form.**
Run 065 taught that a guard installed for a named hazard is not a guard on
every field that hazard reaches; this adds that the same hazard can need a
different *representation* per field -- a slug in a URL, prose in a title. And
when enumerating "every advertised field", check that the enumeration covered
the **channel** and not only the items.

Latent as always: `coverage` 3/3, `registry` ok, `verify --remote` ok, `drift`
ok and 3x `reconcile` 0/0/0 were all accurate and all blind.

Harnesses `/opt/data/tmp/mm_show_identity_repro_run066.py` (34/34 against the
**unmodified** module, with the run-065 GUID, run-038 empty-description,
run-057 cover and run-060 index-page detectors shown still firing as controls)
and `mm_show_identity_proof_run066.py` (54/54: pre-fix still reproduces; all
six classes refused and named; nothing granted -- intact tree and intact deploy
pass with a verdict identical pre/post, `show_identity` the only added check
name, and run-065/063/038/058/057/060/unparseable gates all still bite; exactly
one pre-existing function changed, 59 byte-identical incl. `preflight`,
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `reconcile`, `registry_audit`, `status`, `deploy_drift`,
`_feed_item_number`, `_legacy_episode_numbers`; `publish_feed.py` untouched).
Tests `tests/test_show_identity_gate.py` (suite 232 -> **249**), load-bearing:
15 of 17 fail against the pre-fix module.

Two harness bugs, neither a code defect (run 029's rule): a module copied to a
temp dir resolves `ROOT` from **its own** location, so the relocated pre-fix
module died at the first manifest read and returned a truncated check list --
point every path constant back at the real tree. And run 058's function-slicer
trap recurred in a new form: a pop-from-the-end loop is stopped by trailing
**blank** lines, so a module constant block added after a function was still
attributed to it; cut at the first unindented line after the `def` instead.

### Two metrics shared the name `source_words` (fixed run 067)

`read_lane.record_verdict()` did
`record["source_words"] = verification.get("source_words", ...)`, letting the
gate's count overwrite build's. They are **different measurements**:

| written by | value | meaning |
|---|---|---|
| `build()`/`register()` | `extraction["words"]` = `len(text.split())` | build-time fact: words in the pypdf body-text extraction |
| `verify()` | `len(normalize_words(source))` = count of `[a-z0-9]+` runs | gate metric: normalized tokens of `source.txt` |

They disagree by a few percent on any real paper -- hyphenated compounds,
parenthesised statistics and numerals tokenize differently. On the sibling
tree's real reading 501 it is **13602 vs 13985**.

The build-time figure is a **published deliverable**, not bookkeeping:
`publish_feed.read_notes_html()` prints it verbatim into the feed's
`<content:encoded>` ("... of the N extracted body words are present in the
reading, in source order"), and `read_lane.write_notes()` prints the same
number into `episodes/NNN/episode-notes.md`. So the documented operator flow --
`render`, then `verify --episode NNN` (run 040) -- silently **rewrote a
sentence in the published show notes**, leaving the deployed notes file and the
feed item disagreeing about the same paper.

No gate can see it. The fidelity gate compares `script.md` against
`source.txt`, both written in the same breath, so coverage reads 1.0; it
*reports* this field (`result["source_words"] = record.get("source_words")`)
without comparing it to anything; and the notes file is checked for existence,
never for agreement with the feed. `coverage` 3/3, `registry ok`, `verify ok`
and `preflight` 001-003 ok were all accurate and all blind.

`record_verdict()` now persists only what the gate owns -- `verified`,
`coverage`, `audio_words`, `audio_seconds`, `gate_issues`, `verified_at`, the
run-040/042 audio digest -- with its own counts under **`gate_source_words`**
and **`gate_spoken_words`**. The ambiguous `spoken_words` key is no longer
written. Nothing is lost: the gate metrics stay auditable beside the verdict,
and the build-time fact the deliverables quote is left exactly as `build()`
wrote it.

**Nothing granted.** A failing gate still writes `verified: false` with its
issue list and is still refused by `fidelity_gate()`; truncated audio, dropped
source text and injected commentary are each still refused; `record_verdict`
still raises rather than invent an entry `build()` never made; `verify()` the
function is still side-effect free; and the run-009 durable-state mirror still
writes `state.json`/`manifest.json` with this show's GUID prefix only.

**Lessons.** *Never let two measurements share a name across a build/verify
boundary* -- when a field is written by two stages, ask whether both stages mean
the same thing by it, and give the later one its own name if not. And this is
the write-side twin of runs 042/045: those found advertised fields with **zero
readers**; this is a field with a reader that is a *published sentence*, which
makes an overwrite a silent edit to a live deliverable rather than a stale
record. When a registry field is quoted in output a subscriber sees, treat it
as immutable after the write that owns it.

Harnesses `/opt/data/tmp/mm_source_words_repro_run067.py` (32/32 against the
**unmodified** module: the two counts proved unequal on a fixture *and* on the
sibling's real reading 501, the gate passing, the overwrite, the published
sentence moving, and the notes file left disagreeing) and
`mm_source_words_proof_run067.py` (67/67: pre-fix backup still reproduces;
post-fix the build count survives and the two deliverables agree across ten
re-verifies; 17 nothing-granted assertions; exactly **one** function changed
with 32 byte-identical incl. `verify`, `build`, `register`, `render_episode`,
`sync_durable_state`, `occupied_numbers`, `next_number` and `write_notes`).
Tests `tests/test_read_verdict_provenance.py` (suite 249 -> **269**),
load-bearing: **7 of 20 fail** against the pre-fix module.

Harness note: a one-sentence omission out of twelve identical paragraphs is
only ~0.5% of the words, which the **0.995 coverage floor tolerates by
design** -- the gate catches it with the *order* check instead. A proof that
asserts "dropped text is a coverage refusal" therefore false-fails on its own
fixture; drop a whole paragraph to exercise the floor, and keep both cases,
since they are two distinct real refusals.

## The channel's own BLURB had no reader (fixed run 068)

`<channel><description>` -- the show's self-description, which every podcast
client renders beside the artwork -- had **zero readers** in `verify_feed()`.
The field name appeared on exactly **one** code line in the whole function, and
that line is run 038's **item**-level loop: so the identical field name was
gated one level down and ungated at the channel. Run 032's lane-asymmetry axis
rotated onto the feed's two levels.

It is the **fifth slot run 004 retargeted off the sibling show by hand**. Run
066 gated the four show-*name* slots and closed "the channel's identity text";
the blurb was retargeted in the same breath and nothing has held it since.

Four classes were reachable, each returning `ok: true` with an **empty issue
list** -- the verdict `publish_local()` refuses on and `push_to_remote()`'s wait
loop breaks on to declare a deploy live:

- the **sibling show's blurb** (the run-004 clone regression, re-shippable today)
- an **empty** channel description
- the `<description>` element **removed entirely**
- unfilled **placeholder** text (`TODO`, `TBD`, `lorem ipsum`, ...)

**Neither existing guard reaches it, and that is the sharp part.**
`FORBIDDEN_SHOW_TITLES` is applied only to the title fields;
`FORBIDDEN_ADVERTISED_SUBSTRINGS` is slug-form and scoped to advertised URLs.
Worse, the sibling show's blurb **names neither show**, so even applying both
guards here unscoped would still ship it green. Run 066 taught that a guard's
*form* must match the field's form (a slug in a URL, prose in a title); this
adds that the same hazard can need a **third representation** -- a guard on the
field's own *content*, because an identity defect in a blurb may mention no
identity at all.

**Form chosen to match the field, and this is where the first draft was
wrong.** A title is exact, so run 066 compares it exactly. A blurb is editorial
prose that gets legitimately reworded, so the gate tests only what is *wrong*:
present and non-empty, no sibling-blurb phrasing, no sibling show name, no
placeholder sentinel. An earlier draft also demanded a project anchor
("NIH SEPA") be *present* -- and **16 pre-existing fixtures in four other gate
suites failed on it**. That was the evidence the arm mandated editorial
**content** rather than detecting a defect, so the arm was removed, not the
fixtures. Run 029's rule at its most useful: when a suite fails, establish
which side is wrong before editing either -- here the suites were right and my
new gate was overreaching.

The verdict folds into the existing `show_identity` check (one identity, one
owner) and records `channel_description_chars`, so the field now has a reader
that is visible in the output. **No legacy waiver** (run 036): a show with no
description, or with another show's description, is wrong for an import too.

**Nothing granted.** The intact tree and the real live feed still pass with an
identical verdict; a topic-only blurb that names no grant is accepted; an
ordinary editorial rewording is accepted; and the run-066 title, run-038 item
description, run-065/063 GUID, run-057 cover, run-060 index-page, run-058
duration and unparseable-feed gates all still bite.

Harnesses `/opt/data/tmp/mm_channel_desc_repro_run068.py` (26/26 against the
**unmodified** module: zero readers proved by code inspection, all four classes
green, the intact feed proved **indistinguishable** from the regression, and
the run-066 title / run-038 item-description detectors kept as controls to show
the machinery works and only this field was unread) and
`mm_channel_desc_proof_run068.py` (48/48: pre-fix backup still reproduces; all
classes refused and named; 15 nothing-granted assertions; exactly **one**
pre-existing function changed with **60** byte-identical incl. `preflight`,
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `reconcile`, `registry_audit`, `status` and `deploy_drift`;
`publish_feed.py` untouched; additive only, 0 removed lines). Tests
`tests/test_channel_description_gate.py` (suite 269 -> **288**), load-bearing:
**10 of 19** fail against the pre-fix module (restored md5-identical).

Harness note: scoring a modified feed from a bare temp dir makes every asset
probe (cover, enclosures, notes, index) report a missing file and swamp the
verdict -- which reads exactly like the new gate false-failing. Symlink the real
`feed-site` assets beside the scratch `feed.xml`, and filter the issue list to
the field under test.


## The advertised ORDINAL and KIND had no reader (fixed run 069)

`<itunes:episode>` and `<itunes:episodeType>` -- the number every podcast
client sorts the feed by and prints beside the title, and the label that tells
a client whether an item is a `full` episode, a `trailer` or `bonus` -- had
**zero readers** in `verify_feed()`. `publish_feed.py` emits both on every
item, in both lanes (`<itunes:episode>{int(num)}</itunes:episode>` and a
hardcoded `full`).

**The sharp part is that this field HAD a reader and run 036 removed it.** The
legacy waiver run 036 fixed was keyed on `<itunes:episode> == "1"`, which is
not what the field means; run 036 was right to delete that use and re-key the
waiver on the durable ledger. Nothing replaced the read. So the field went from
*misread* to *unread*, and has been ungated since -- while the run-036 comment
explaining its removal remained in the file, which is exactly what made a grep
for the field look like it had a reader.

Five classes were reachable, each returning `ok: true` with an **empty issue
list** -- the verdict `publish_local()` refuses on and `push_to_remote()`'s
wait loop breaks on to declare a deploy live:

- an ordinal disagreeing with the item's own GUID (`7` on episode 001)
- an ordinal that is absent, empty, zero, or non-numeric (`one`, `1.5`, `-3`)
- `episodeType: trailer` or `bonus` on a fully gated interview, which in Apple
  Podcasts pins the item **outside the numbered run** a listener follows
- a wrong-case `FULL`, invalid per the spec
- the element missing entirely

The intact feed was proved **indistinguishable** from every one of them: same
check-name list, same verdict.

**Scored against the GUID, not against the feed's ordering.** The GUID is this
show's durable identity for an episode (run 065) and `_feed_item_number()`
already derives the number from it, so the check is a cross-field **agreement**
test rather than a second opinion about what the ordinal should be. Recorded
under a new `episode_number` check (`advertised`, `episode`, `episode_type`,
`lane`). No legacy waiver (run 036): an import's advertised ordinal is what a
subscriber's client sorts it by just the same.

**A first draft carried an arm that could never fire.** It also refused "two
items advertise one ordinal", and the proof harness showed the condition is
unreachable past the checks above: two items sharing an ordinal either disagree
with their GUIDs (caught by the agreement arm) or carry the same GUID number,
which the pre-existing duplicate-GUID check already refuses. **The dead arm was
removed rather than the claim weakened**, and a test now pins that no
`advertised_ordinals` machinery survives. Run 068's lesson in a new shape: a
guard you cannot prove bites is not a guard.

**Fixtures completed, not gate relaxed.** 16 pre-existing tests failed once the
fields became gated, in seven suites whose item fixtures carried
`<itunes:episode>` but **no `<itunes:episodeType>` at all** -- run 058's trap
exactly, an incomplete fixture rather than a finding, since `publish_feed.py`
emits the element on every item it writes. A 17th was sharper: the disclosure
suite hardcoded `<itunes:episode>1</itunes:episode>` while parameterising the
episode number everywhere else, so its **reading 501** fixture advertised
ordinal `1`. `publish_feed.py` emits `{int(num)}`, so a real reading advertises
`501`; the fixture was parameterised to match the code.

**Blast radius.** Exactly **one** pre-existing function changed
(`verify_feed`), **60 byte-identical** including `preflight`/`review_gate`/
`fidelity_gate`/`feed_coverage`/`publish_local`/`push_to_remote`/`reconcile`/
`registry_audit`/`status`/`deploy_drift`. `publish_feed.py` untouched.
Additive only: 111 lines added, **0 removed**.

**Harnesses.** `/opt/data/tmp/mm_itunes_episode_repro_run069.py` **30/30**
against the **unmodified** module (zero readers by code inspection, all five
classes green, indistinguishability, with the run-058 duration and run-065
GUID detectors kept as controls). `mm_itunes_episode_proof_run069.py`
**54/54**: the pre-fix backup still reproduces; every class refused and named;
14 nothing-granted checks -- the real live feed keeps an identical verdict
pre/post, and the run-038/057/058/060/065/066 detectors all still bite.

**Tests.** `tests/test_episode_ordinal_gate.py`, 22 tests, suite
**288 -> 310**. Proven load-bearing: **18 of 22 fail** against the
`.bak-run069` module; restored and confirmed md5-identical with all 310 green.

**Lesson that generalizes: when a fix REMOVES a reader, it leaves the field
unread.** Runs 056-068 hunted fields that *never* had a reader. This one is the
opposite history and is harder to see, because the removal was correct and its
explanatory comment stays behind -- so `grep -n '<field>'` returns a hit and the
field reads as covered. When auditing coverage, strip comments before counting
readers, and treat any field whose only mention is a comment about a *past*
reader as ungated.

## The channel's attribution/classification block is gated (run 070)

`verify_feed()` scores the six channel-level fields `publish_feed.py` writes on
every feed, reported under the `channel_attribution` check:

- `<language>` — compared exactly against `SHOW_LANGUAGE` (`en-us`); a
  wrong-case tag is refused separately, because some directories match the
  language tag literally.
- `<copyright>` — must be non-empty and must name `SHOW_COPYRIGHT_HOLDER`
  (`Field Day Lab`) as a case-insensitive substring, and must not name the
  sibling show. Deliberately **not** an exact match: a rights line is prose and
  is legitimately reworded, so `Copyright 2026, Field Day Lab. All rights
  reserved.` passes.
- `<itunes:author>` — same prose treatment against `SHOW_ITUNES_AUTHOR`, **plus
  run 066's `FORBIDDEN_SHOW_TITLES` identity guard**, which had never been
  applied to this slot.
- `<itunes:type>` — must be `episodic`. `serial` makes a client present the
  catalogue **oldest-first**, silently reordering every episode.
- `<itunes:category>` — the value is an **attribute** (`text="Education"`), not
  element text, which is why an element-text sweep never saw this field. An
  additional category alongside `Education` is legal.
- channel `<itunes:explicit>` — must be `false`; only `true`/`false` are
  accepted spellings. The item-level element of the same name is a different
  field and is not mistaken for this one.

**No legacy waiver** (run 036): these are channel fields, not a property of any
one episode, so no ledger status can excuse them.

Before this run all six had **zero readers and zero tests**, so each shipped
`ok: true` with an **empty issue list** — the verdict `publish_local()` refuses
on and `push_to_remote()`'s wait loop breaks on to declare a deploy live. The
sharpest class: the sibling show's prose name in `<itunes:author>` passed
green, because run 063's guard is slug-form scoped to advertised URLs and run
066's is scoped to the title fields.

Tests: `tests/test_channel_attribution_gate.py` (30 tests, suite 310 -> 340).

## The SYNDICATION ENVELOPE had no reader (fixed run 071)

Runs 042/045/056/057/058/062/063/064/065/069/070 each closed one advertised
field with zero readers, and run 070 declared the channel's attribution block
the last of them. All of those asked **"is each advertised value correct?"**.
The unread question sat one level above: **"is this document still an RSS 2.0
podcast feed, and can a client read those fields at all?"**

Five fields carry that answer and `robust_pipeline.py` read none of them. The
strings `audio/mpeg`, `isPermaLink` and `xmlns` appeared on **no code line**
(comment- and docstring-stripped); the two namespace URIs appeared only as
`ET` lookup helpers, never as a value compared against what the feed declares.

| field | what it decides | cost of a defect |
|---|---|---|
| `<rss version="2.0">` | the syndication format | a strict client rejects the whole feed; every episode disappears at once |
| `xmlns:itunes` | binds every `itunes:` field | all iTunes metadata unbound |
| `xmlns:content` | binds `<content:encoded>` | the show notes — a published deliverable carrying both mandated disclosures — invisible to every client |
| `<enclosure type>` | the audio MIME type | the item is listed and **unplayable** |
| `<guid isPermaLink>` | identity vs URL | the GUID is resolved as a relative URL, re-delivering or shadowing the episode |

Eight single-fault classes each shipped `ok: true` with an **empty issue
list** — the verdict `publish_local()` refuses on and `push_to_remote()`'s
wait loop breaks on to declare a deploy live — and the intact feed was proved
**indistinguishable** from every one of them (identical check-name list,
identical verdict).

**Sharpest part: a portability fallback masked the namespace defect exactly.**
Run 064's gate finds the notes element with
`next((x for x in item if x.tag.endswith("encoded")), None)`, which matches
**whatever namespace the tag resolved into**. So binding `xmlns:content` to a
foreign URI leaves run 064 green while a real client reading the content
module sees no notes at all. A fallback written for robustness is a reader
that cannot detect the thing it is reading around.

By contrast a **removed** `xmlns` is already detected — ElementTree refuses
the document with *unbound prefix* — and a **wrong** `xmlns:itunes` is caught
only **incidentally**, by run 068's arm reporting the attribution fields as
*absent* when they are present under the wrong namespace: a true refusal with
a misleading message. Both are now named at the binding.

Fixed with a `syndication_envelope` check after `feed_parse`, **form matched
per field** (runs 066/068/070): all five are enumerated values from a closed
set, so each is compared exactly and a wrong-case variant is refused
**separately and named as a case defect** — an envelope is machine-read, so
`AUDIO/MPEG` is not a copy edit, it is a different string to a parser. The
declared bindings are read from the **raw feed bytes**, because ElementTree
discards the prefix→URI map and because the question is what the published
feed tells a client, not what this tree's helpers resolve. **No legacy waiver**
(run 036): the envelope is a property of the syndication format, not of any
episode, so no episode's provenance can exempt it.

Healthy state here is `rss_version: "2.0"`, both namespaces exact, and
`audio/mpeg` / `false` for all three items.

**Lesson.** Runs 063/066/070 taught that a guard's coverage is the product of
its *form* and its *scope*. This adds the **level**: an enumeration of
"every field the artifact advertises" is still bounded by the layer you
enumerated at. Before calling such a census closed, ask what the artifact
declares about **itself** — its format, its version, its namespace bindings —
because those fields are not values a client renders, they are the
preconditions for reading any of the others. And when a reader uses a
tolerant fallback (`endswith`, a regex, a casefold) to find a field, that
reader is structurally unable to gate the property the fallback tolerates;
grep for tolerant lookups and gate what they ignore.

Harnesses `/opt/data/tmp/mm_envelope_repro_run071.py` (43/47 against the
**unmodified** module — the four non-passes were **harness bugs, not code
defects** (run 029): a removed `xmlns` is a genuine parse refusal and a wrong
`xmlns:itunes` is caught incidentally, both confirmed by direct ElementTree
probes) and `mm_envelope_proof_run071.py` (83/83: pre-fix still reproduces all
eight classes and all eight indistinguishability pairs; every class refused and
named; three case variants named as case; nothing granted — the real live feed's
verdict is **identical** pre/post, runs 069/065/038/063/066/068/058/057 all
still bite, a ledger-`published` import is still refused, and three
`verify_feed` passes mutate zero bytes; exactly **one** pre-existing function
changed with **60** byte-identical including `preflight`, `review_gate`,
`fidelity_gate`, `feed_coverage`, `publish_local`, `push_to_remote`,
`reconcile`, `registry_audit` and `status`; `publish_feed.py` untouched;
additive only +187/-0).

Tests `tests/test_syndication_envelope_gate.py` (18 tests, suite 340 → **358**),
load-bearing: **16 of 18 fail** against the pre-fix module, which was then
restored md5-identical.

**Two fixture traps, both the fixture's fault (run 029 again).** The first
draft's mp3 was magic bytes plus zeros, which run 058's duration gate correctly
refuses as *"the right byte length but not playable audio"* — the fixture built
a feed this pipeline cannot produce; reuse `test_duration_gate.py`'s
`_make_mp3()` helper instead. And the proof harness initially reported the
pre-fix module **refusing** six classes: a module copied into scratch resolves
`ROOT` from **its own** location (run 066's trap), so every registry read died
and `verify_feed` returned a truncated check list that reads exactly like "the
fix added checks". Repoint `ROOT`/`PIPELINE`/`LEDGER_PATH`/`MANIFEST_PATH`/
`READ_MANIFEST_PATH` at the real tree after loading a relocated copy.

## Each item's OWN artwork and rating had no reader (fixed run 072)

`publish_feed.py` emits **two per-item fields on every item it writes, in both
lanes** — `<itunes:explicit>false</itunes:explicit>` and
`<itunes:image href="{BASE_URL}/cover.png"/>` — and until run 072 nothing read
either value. Ten single-fault classes each shipped `ok: true` with an **empty
issue list** and were proven **indistinguishable** from an intact feed: the
artwork reference removed from one item, from all items, or from the whole
document; the href emptied; the item naming artwork the channel does not; the
rating removed from one item or all; emptied; set to `true`; set outside the
vocabulary; and wrong-case `False`. That verdict is what `publish_local()`
refuses on and what `push_to_remote()`'s wait loop breaks on to declare a
deploy live.

**Why three existing guards all stop short, which is the finding.**

- **Run 057 gated cover art** — but `cover_art` is a document-wide **set union**
  over every image reference, resolved to **filenames** and probed for
  existence. It answers *"do the referenced files exist"*, not *"does each item
  advertise artwork"*. Delete the reference from every item and the surviving
  `<image><url>` text node repopulates the union; the check still reports
  `files: ['cover.png']` and passes. Its only absence arm is `not cover_refs`,
  which an aggregate can satisfy while every item is bare.
- **Run 063 gated an advertised URL's base and absoluteness** — a *missing* URL
  advertises nothing and is outside that guard by construction.
- **Run 070 gated the CHANNEL's `<itunes:explicit>`** — the item field of the
  same name had no reader. Run 032's lane-asymmetry axis on the feed's two
  levels, exactly as run 067 found for `<description>`.

**Scope, established by control rather than asserted.** A *repointed* href
naming a file that does **not** exist is already refused pre-fix, incidentally,
because a new filename enters run 057's union and its existence probe fires.
The genuinely unreadable classes are therefore a reference that is **absent**,
one that is **empty**, and one that **disagrees while naming a file that
exists** — which is why the agreement test is checked against artwork present
on disk, so the existence probe cannot be what refuses it.

**Fix.** An `item_artwork_rating` check immediately after `episode_number` in
`verify_feed()`'s per-item loop, **form matched per field** (runs 066/068/070):
artwork is an asset *reference*, so it must be present, non-empty, and agree
with the channel's (both are written from one `BASE_URL` constant, so a
disagreement means a hand-edit or partial write); the rating is an *enumerated*
value, so it is compared exactly against the closed set with a wrong **case**
refused separately and named as case, because a rating is machine-read. No
legacy waiver (run 036). A consistent artwork **rename** applied to channel and
items together still passes, so ordinary edits do not false-fail.

Proof: repro **71/71** against the unmodified module (zero readers by
comment-stripped inspection, ten mutation classes green, indistinguishability,
and runs 057/063/070 kept as **controls**); proof **68/68** (pre-fix still
reproduces; every class refused and **named**; nothing granted — the real live
feed's verdict identical pre/post, the consistent rename still passes, no legacy
waiver, and runs 071/070/069/066/065/063/058/038 all still bite). Exactly **1**
pre-existing function changed, **69 byte-identical** including `preflight`,
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `reconcile`, `registry_audit`, `status` and `deploy_drift`;
`publish_feed.py` untouched; additive **+139/-0** non-blank lines. Tests
`tests/test_item_artwork_gate.py` 19 tests, suite **358 -> 377**, load-bearing
(**15/19 fail** against the pre-fix module; module restored md5-identical).

**FIXTURES COMPLETED, NOT GATE RELAXED** (runs 058/070's trap). 18 pre-existing
tests across **eight** suites built an item carrying duration, ordinal,
episodeType and an artwork href but **no `<itunes:explicit>`** — a feed
`publish_feed.py` cannot produce. Completed with exactly the value it emits,
each edit asserting its anchor count and that every original non-blank line
survives in its extended form. Two suites needed a separate pass because their
templates interpolate `{encoded}` / `{item_cover}` placeholders rather than a
literal artwork tag.

**Lesson: an aggregate check cannot gate a per-element requirement.** Run 057's
census recorded cover art as *gated*, and it is — as a set of files. The
question it cannot answer is whether each item carries the reference, because
unioning the references is precisely what discards which element supplied them.
When a check collects a property across a document and then validates the
collection, ask what it would say if exactly one contributor went missing. Pair
run 071's "ask what level you enumerated at" with "ask whether the check is
**per-element or aggregate**" — the same field name can be gated at one
granularity and unread at the other.

**Harness note (run 029's rule, five times in one slice).** Five of this
slice's first-run failures were the harness's fault, none a code defect: two
substring censuses over `tests/` matched fixture lines that *emit* the tag and
function *names* containing it (containing a field is not asserting on it —
census the assertion); an artwork mutation using a bare `replace(..., 1)` hit
the **channel's** `<itunes:image>`, the first in the document, instead of an
item's (anchor on `</item>`); a "pre-fix is silent" case was already caught
incidentally by run 057's existence probe; and a `cover_art.advertised == []`
assertion ignored the `<image><url>` fallback that repopulates the union.

## The channel's navigation and artwork container had no reader (run 073)

`verify_feed()` now carries a `channel_navigation` check over the four fields
`publish_feed.py` writes from its one `BASE_URL` constant and nothing read:

    <channel><link>{BASE_URL}/</link>
    <channel><image><url>{BASE_URL}/cover.png</url>
                    <link>{BASE_URL}/</link></image>

These are not prose a client renders; they are how a subscriber **leaves** the
feed. `<channel><link>` is the show's homepage -- every client's "visit
website" affordance and the canonical page a directory submission records.
`<image><url>` is the RSS 2.0 artwork a non-iTunes client renders, and
`<image><link>` is where that artwork clicks through to.

Nine single-fault classes each shipped `ok: true` with an **empty issue list**
-- the verdict `publish_local()` refuses on and `push_to_remote()`'s wait loop
breaks on to declare a deploy live -- and an intact feed was
**indistinguishable** from all nine.

Why three nearby guards stopped short:

- `cover_art` (run 057) is a document-wide **set union** over image refs,
  reduced to `Path(urlparse(h).path).name` and probed for existence. A removed
  or emptied `<image><url>` is repopulated by the surviving per-item
  `<itunes:image href>`, so the union still reports `files=['cover.png']`.
- `show_identity` (run 066) guards its whole artwork arm behind
  `if channel_image is not None`, so a wholly **absent** `<image>` block skips
  every artwork check rather than failing one.
- `advertised_base` (run 063) checks an advertised URL's **host and
  directory**. A `<link>` repointed at this show's own `episode-001.mp3` is
  under the expected base and passes; an absent `<link>` advertises nothing
  and is outside that guard by construction.

**Scope by control.** Two nearby mutations are *already* refused pre-fix and
the tests record which guard does it: a wrong-**case** host by run 063's base
check, and an `<image><url>` naming a file that does not exist by run 057's
existence probe. So the genuinely unreadable classes are absent / empty /
disagrees-while-naming-a-file-that-**exists** -- which is why the agreement
test writes a second real artwork file first.

Form matched per field (runs 066/068/070/071): a URL is compared as a URL with
the trailing slash normalized (no client distinguishes the two forms), and a
wrong-case homepage is refused separately and **named as case**, because a
homepage is machine-read by every directory. No legacy waiver (run 036): a
dead homepage and missing RSS artwork are wrong for an import too.

Backup `pipeline/robust_pipeline.py.bak-run073`; exactly one pre-existing
function changed (`verify_feed`), 63 byte-identical including `preflight`,
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `reconcile`, `registry_audit` and `status`;
`publish_feed.py` untouched; additive only +142/-0. Tests
`tests/test_channel_navigation_gate.py` 18 tests, suite 377 -> **395**,
load-bearing (14/18 fail against the pre-fix module, then restored
md5-identical).

Seven pre-existing fixtures across seven suites declared no channel `<link>`
and/or no `<image><link>` -- feeds `publish_feed.py` cannot produce. Those
were **completed, not the gate relaxed** (the run-058/070 trap), and one of
them had the wrong homepage form (`{base}/index.html`).

**Lesson.** This is run 072's per-element-vs-aggregate finding with the
granularity **inverted**. Run 072 found a field gated in aggregate and unread
per element; here the per-element arm **exists** and is skipped by its own
presence guard, while the aggregate arm is satisfied by a *different*
element's contribution. A presence guard written to avoid a crash is
structurally unable to gate presence -- so when a check is wrapped in
`if X is not None`, ask what reports X being None.

### The advertised show-notes link (`show_notes_link`)

`verify_feed()` scores every item's show-notes href — the
`<a href="episode-NNN-notes.md">` inside `<content:encoded>` that
`publish_feed.py`'s `notes_html()` / `read_notes_html()` emit on every item in
both lanes. The notes are a **published deliverable**: they carry the
unabridged disclosure, the evidence boundaries and every numbered citation with
its Zotero link, and this href is a listener's only route to them from a podcast
client.

Three refusals, each naming the episode and the offending value:

- the href resolves to **another episode's** notes
- the item advertises **no** show-notes link at all
- the href carries a **cross-show substring** or sits outside this show's
  advertised base

Scored against the item's **GUID-derived number**, so it is a cross-field
agreement test. A reading may use either `episode-NNN-reading-notes.md` or
`episode-NNN-notes.md`. There is **no legacy waiver** — an imported episode's
notes are reached by the same link in the same client.

Note what this does *not* duplicate: the older probe asks whether the file the
href names **exists** (locally, and HTTP 200 live). That arm is unchanged and
still catches a nonexistent target. Existence was never evidence of
**correctness** — the wrong episode's notes file exists too.

## The tree-root mirror of every deployed deliverable (run 078)

GitHub Pages serves the **repository root**, and `push` copies `feed-site/*`
into the clone's root — so the root *is* the live site. This tree also keeps a
second, **git-tracked** copy of every deployed deliverable at its own root
(`feed.xml`, `index.html`, each `episode-NNN.mp3`, each
`episode-NNN-notes.md`, `cover.png`, `cover.svg`). `publish_feed.py` writes
`feed-site/` only and has **no copy site for the root**, so the two sets are
**hand-kept in sync — edit both.**

`verify_feed()`'s `root_mirror` check enforces that rule for every deliverable,
by digest. Run 057 had closed it for the two cover files only. An **absent**
root copy waives (the feed references `feed-site/`); only present-and-different
refuses. `README.md`, `production-log.md` and `style_guide.md` are exempt by
exact name.

Healthy state here is ten mirrored files with an empty `no_root_copy`.
