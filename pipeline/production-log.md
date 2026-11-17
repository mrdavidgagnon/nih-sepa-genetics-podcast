## 2026-11-17T13:xxZ — run 071 (the syndication envelope had no reader)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; 18 items still
unfiled in the parent YF84AUZK — David's standing lane call, not re-raised).
Opening audits all healthy and all blind: `coverage` ok 3/3, `registry` ok
(ledger 4 / manifest 3, the 501 stub), `verify` local and `--remote` ok with no
issues (remote 3/3, both drift lists empty), three `reconcile --write` passes at
0/0/0, preflight 001-003 ok, `status` healthy, suite 340/340. Stale lock owner
pid 87034 dead and the advisory lock free — the normal steady state; cleared
with `unlock --force`. No production unit, so the slice closed a latent defect.

**Defect.** The feed's **syndication envelope** — the five fields that decide
what kind of document this is and whether a client can read the rest of it —
had **zero readers**. `audio/mpeg`, `isPermaLink` and `xmlns` appeared on no
code line at all (comment- and docstring-stripped); the two namespace URIs
existed only as `ET` lookup helpers, never compared against what the feed
declares. Eight single-fault classes each shipped `ok: true` with an **empty
issue list**, and the intact feed was proved indistinguishable from every one.

This is one **level above** every prior instance of the axis. Runs
042/045/056/057/058/062/063/064/065/069/070 enumerated the channel's and the
items' advertised fields and run 070 called that census closed; none asked
whether the document is still an RSS 2.0 podcast feed.

**Sharpest part.** Run 064's notes gate finds its element with an
`x.tag.endswith("encoded")` portability fallback, which matches in **any**
namespace — so binding `xmlns:content` to a foreign URI leaves that gate green
while a real client sees no show notes. A fallback written for robustness
cannot gate the property it tolerates. A *removed* `xmlns` is already caught
(ElementTree *unbound prefix*) and a wrong `xmlns:itunes` only **incidentally**,
by run 068 reporting present-but-misbound fields as absent — a true refusal
with a misleading message. Both are now named at the binding.

**Fix.** A `syndication_envelope` check after `feed_parse`, form matched per
field (runs 066/068/070): enumerated values compared exactly, wrong case
refused separately and named as case, bindings read from the raw feed bytes
since ElementTree discards the prefix map. No legacy waiver (run 036) — an
envelope is a property of the format, not of an episode. Backup
`robust_pipeline.py.bak-run071`; exactly one pre-existing function changed, 60
byte-identical incl. `preflight`/`review_gate`/`fidelity_gate`/`feed_coverage`/
`publish_local`/`push_to_remote`/`reconcile`/`registry_audit`/`status`;
`publish_feed.py` untouched; additive only +187/-0.

**Proof.** repro 43/47 vs the unmodified module (the four non-passes were
**harness bugs, not code defects** — run 029 — and both were confirmed by
direct ElementTree probes before anything was touched); proof **83/83**
(pre-fix reproduces all eight classes plus all eight indistinguishability
pairs; every class refused and named; three case variants named as case;
nothing granted — real live feed verdict **identical** pre/post, runs
069/065/038/063/066/068/058/057 all still bite, a ledger-`published` import
still refused, 3x `verify_feed` mutates zero bytes).

Tests `tests/test_syndication_envelope_gate.py` 18 tests, suite 340 → **358**,
load-bearing 16/18 fail pre-fix (module then restored md5-identical). Also
completed `test_remote_feed_drift.py`'s fixture, which declared no
`xmlns:itunes` — a feed publish_feed.py cannot produce (run 058's trap); that
test is scoped to "deployed feed" substrings so it passed either way, so this
is hygiene, not a gate relaxation.

Two fixture traps, both the fixture's fault: an mp3 of magic bytes plus zeros
is correctly refused by run 058's duration gate (use `_make_mp3()` from
`test_duration_gate.py`), and a relocated module resolves `ROOT` from its own
location so the pre-fix run looked like it *refused* six classes (run 066).

Final: `coverage` 3/3, `registry` ok, `verify` local+remote ok, preflight
001-003 ok, 3x `reconcile` 0/0/0, `status` healthy, suite **358/358**,
`feed-site/feed.xml` md5 **UNCHANGED** 9fc23235 and == live, items 3/3.

**Lesson.** Runs 063/066/070 established that a guard's coverage is the product
of its *form* and its *scope*. This adds the **level**: an enumeration of
"every advertised field" is bounded by the layer you enumerated at, so before
calling such a census closed, ask what the artifact declares about **itself**
— format, version, namespace bindings — since those are not values a client
renders but the preconditions for reading every other field. Corollary: when a
reader finds a field through a tolerant lookup (`endswith`, a regex, a
casefold), that reader is structurally unable to gate the property the
tolerance ignores.

## 2026-11-17T00:2xZ — run 068 (the channel's own BLURB had no reader)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; 18 items still
unfiled in the parent YF84AUZK, David's standing lane call — not re-raised).
Opening audits all healthy and all blind: `coverage` ok 3/3, `registry` ok
(ledger 4 / manifest 3, the 501 stub), `verify` local and `--remote` ok with no
issues, manifest and ledger agree at `published_and_moved` for 001-003, suite
269/269. Stale lock owner pid 3898579 dead and the advisory lock free — the
normal steady state; cleared with `unlock --force`. No production unit, so the
slice closed a latent defect.

**Defect.** `<channel><description>` — the show's self-description, rendered by
every podcast client beside the artwork — had **zero readers** in
`verify_feed()`. The field name appeared on exactly **one** code line in the
whole 812-line function, and that line is run 038's **item**-level loop: the
identical field name was gated one level down and ungated at the channel.

It is the **fifth slot run 004 retargeted off the sibling show by hand**. Run
066 gated the four show-*name* slots and declared "the channel's identity text"
closed; the blurb was retargeted in the same breath and nothing has held it.
Four classes shipped green with an **empty issue list** — the sibling show's
blurb (the run-004 regression, re-shippable today), an empty description, the
element removed, and placeholder text. The intact feed was proved
**indistinguishable** from the regression: same check-name list, same verdict.

**Sharpest part: neither existing guard can reach it even unscoped.**
`FORBIDDEN_SHOW_TITLES` is applied only to the title fields and
`FORBIDDEN_ADVERTISED_SUBSTRINGS` is slug-form scoped to URLs — but the
sibling's blurb **names neither show**, so applying both here would still pass
it. Run 066's "a guard's form must match the field's form" needs a **third
representation**: a guard on the field's own *content*.

**The first draft of the fix was itself wrong, and the suite caught it.** It
also demanded a project anchor ("NIH SEPA") be present, and **16 pre-existing
fixtures in four other gate suites failed** — evidence the arm mandated
editorial *content* rather than detecting a defect. The arm was removed, not
the fixtures (run 029: establish which side is wrong first). The gate now tests
only what is wrong: non-empty, no sibling-blurb phrasing, no sibling show name,
no placeholder sentinel. Folded into `show_identity` (one identity, one owner)
and records `channel_description_chars`. No legacy waiver (run 036).

Backup `robust_pipeline.py.bak-run068`; additive only (0 removed lines).
Nothing granted: intact tree and real live feed pass with an identical verdict,
a topic-only blurb and an ordinary rewording are accepted, and the run-066
title / run-038 item-description / run-065 GUID / run-057 cover / run-060
index / run-058 duration / unparseable gates all still bite.

Proof: repro **26/26** against the unmodified module (with the run-066 and
run-038 detectors kept as controls, showing the machinery works and only this
field was unread); proof **48/48**. Exactly one pre-existing function changed,
**60** byte-identical incl. `preflight`, `review_gate`, `fidelity_gate`,
`feed_coverage`, `publish_local`, `push_to_remote`, `reconcile`,
`registry_audit`, `status`, `deploy_drift`; `publish_feed.py` untouched. Tests
`tests/test_channel_description_gate.py`, suite 269 → **288**, load-bearing:
**10 of 19** fail pre-fix (module restored md5-identical).
`ROBUST_PIPELINE.md` section added (run 031's lesson).

Lesson: **when a field name is gated at one level of an artifact, check every
other level that carries it.** And a gate's *shape* must suit its field —
an exact-match guard on editorial prose is overreach, and a failing pre-existing
suite is the cheapest evidence of it.

Harness note: scoring a modified feed from a bare temp dir makes every asset
probe report a missing file and swamp the verdict, reading exactly like the new
gate false-failing. Symlink the real `feed-site` assets beside the scratch
`feed.xml` and filter the issue list to the field under test.

## 2026-11-16T20:0xZ — run 067 (two metrics shared the name `source_words`)

Both intake lanes empty (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0; the 18
unfiled items in `YF84AUZK` remain David's standing lane call and are not
re-raised). Opening audits all green: `coverage` ok 3/3, `registry` ok (ledger
4 / manifest 3), `verify` local ok with no issues, `preflight` 001-003 ok,
suite 249/249. Stale lock from run 066's own `attempt finish`, owner pid
3748808 dead and the advisory lock free — the documented steady state, cleared
with `unlock --force`. No production unit, so the slice closed a latent defect.

**Defect.** `read_lane.record_verdict()` did
`record["source_words"] = verification.get("source_words", ...)`, letting the
fidelity gate's count overwrite build's. The two are **different
measurements** under one name: `build()`/`register()` store
`extraction["words"]` = `len(text.split())` over the pypdf extraction (a
build-time fact), while `verify()` exposes `len(normalize_words(source))`, the
count of `[a-z0-9]+` runs in `source.txt` (a gate metric). They disagree by a
few percent on any real paper — hyphenated compounds, parenthesised statistics
and numerals tokenize differently. Measured **13602 vs 13985** on the sibling
tree's real reading 501, and 1164 vs 1224 on the harness fixture.

The build-time figure is a **published deliverable**, not bookkeeping:
`publish_feed.read_notes_html()` prints it verbatim into the feed's
`<content:encoded>` ("... of the N extracted body words are present in the
reading, in source order") and `read_lane.write_notes()` prints the same number
into `episodes/NNN/episode-notes.md`. So the documented operator flow — render,
then `verify --episode NNN` (run 040) — **silently rewrote a sentence in the
published show notes**, leaving the deployed notes file and the feed item
disagreeing about the same paper.

Structurally invisible: the fidelity gate compares `script.md` against
`source.txt`, both written in the same breath, so coverage reads 1.0; it
*reports* the field without comparing it to anything; and the notes file is
checked for existence, never for agreement with the feed. This is the sibling's
run-500 finding, never ported here — the run-053 rule again (a census closes as
of a date, not forever), and run 032's lane/tree-asymmetry axis.

**Fix.** `record_verdict()` persists only what the gate owns — `verified`,
`coverage`, `audio_words`, `audio_seconds`, `gate_issues`, `verified_at`, the
run-040/042 audio digest — with its own counts under `gate_source_words` /
`gate_spoken_words`. The ambiguous `spoken_words` key is no longer written.
Backup `read_lane.py.bak-run067`; exactly **one** function changed, **32
byte-identical** including `verify`, `build`, `register`, `render_episode`,
`sync_durable_state`, `occupied_numbers`, `next_number`, `write_notes`,
`normalize_words` and `fetch_pdf_attachment`. `publish_feed.py` and
`robust_pipeline.py` untouched.

**Nothing granted.** A failing gate still writes `verified: false` with its
issue list and is still refused by `fidelity_gate()`; truncated audio, a
dropped source paragraph and 20 words of injected commentary are each still
refused; no audio at all is refused **while coverage reads 1.0** (word fidelity
passing is never the episode passing); `record_verdict` still raises rather
than invent an entry `build()` never made; `verify()` the function is still
side-effect free; the run-009 durable mirror still writes both registries with
this show's GUID prefix only.

Latent in the now-familiar way (runs 008/013/031/033/036/040/042/045): no
reading has ever registered here, so every green check was accurate and blind.
It fires on the first real Read item's first `verify`.

Proof: repro **32/32** against the unmodified module (the two counts proved
unequal on a fixture *and* on the sibling's real reading 501, the gate passing,
the overwrite, the published sentence moving 1164 -> 1224, and the notes file
left disagreeing), fix proof **67/67** (pre-fix backup still reproduces;
post-fix the build count survives across ten re-verifies and the two
deliverables agree; 17 nothing-granted assertions; blast radius). Tests
`tests/test_read_verdict_provenance.py`, suite **249 -> 269**, load-bearing:
**7 of 20** fail against the pre-fix module.

Also added the section to `ROBUST_PIPELINE.md` (run 031's lesson — the cron
reads it every run): 74 lines added, **0 removed**.

Two harness bugs, neither a code defect (run 029's rule). The repro's
"fidelity_gate never compares it" assertion counted `source_words` occurrences
and expected 1, but the single line naming the field names it **twice** (once
writing, once reading) — the sharper assertion is that the only line mentioning
it is that copy. And a one-sentence omission out of twelve identical paragraphs
is ~0.5% of the words, which the **0.995 coverage floor tolerates by design**,
so the gate catches it with the *order* check; asserting "dropped text is a
coverage refusal" false-failed on its own fixture. Both cases are kept — they
are two distinct real refusals.

**Lessons.** Never let two measurements share a name across a build/verify
boundary: when a field is written by two stages, ask whether both mean the same
thing by it. And this is the write-side twin of runs 042/045 — those found
advertised fields with **zero readers**; this is a field whose reader is a
*published sentence*, so an overwrite is a silent edit to a live deliverable
rather than a stale record. When a registry field is quoted in output a
subscriber sees, treat it as immutable after the write that owns it.

## 2026-11-15T09:50Z — run 059 (status/watchdog: healthy was unreachable)

Both intake lanes empty (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0; the 18
unfiled items in `YF84AUZK` remain David's lane call and are not re-raised).
Opening audits all green: `coverage` ok 3/3, `registry` ok (ledger 4 / manifest
3), `verify --remote` ok, `preflight` 001-003 ok, three `reconcile --write`
passes at 0/0/0. Stale lock from run 058's own `attempt finish`, owner pid
2574734 dead and the advisory lock free — the documented steady state, cleared
with `unlock --force`. No production unit, so the slice closed a latent defect.

**Defect.** `status.healthy` was pinned **False by construction** — it could not
come back true however clean the pipeline was, which makes the signal worthless
to the scheduler and to `watchdog()`, which inherits the verdict. `status()` ran
a *deliverables* `preflight()` against every ledger record, so the `planned`
stub 501 was failed for having no `script.md` — which is what `planned` *means*.
It had been doing that for 53 attempts and was the **sole** reason the tree
reported unhealthy (001-003 all pass preflight with zero issues).

Second finding, the inverse: a reading recorded as **published** whose fidelity
gate is **not** `verified` was reported **healthy**. `status()` calls preflight
with `enforce_review=False`, so neither the reviewer panel nor the fidelity gate
is ever reached, and nothing else consulted `read-episodes.json`. That is the
sibling tree's run-422 live-but-unrecorded class, undetectable here.

**Port, deliberately narrowed.** This is HITL's run 503, but two of its branches
must NOT be copied (run 053's rule — read the sibling's assumptions against this
tree's behaviour, not its code):

- HITL needed a reading waiver because its `preflight()` is interview-only.
  **This tree's `preflight()` has been lane-aware since run 029**, so a
  correctly-registered reading already passes the interview-rule half. Proved
  with a scratch reading: `checks.lane == "read"`, `ok: true`. Porting that
  branch would have "fixed" a defect this tree does not have.
- HITL's legacy arm keys on the status literal `published`. This tree has the
  run-037 **hardened three-part** `_legacy_episode_numbers()`. Kept ours.

The reading test must come **first** in the branch chain: the legacy arm keys on
the exact status `published`, so a reading carrying that instead of
`published_and_moved` would be classified as a legacy *interview* and skip its
fidelity gate. Pinned by test.

**Fix.** New `load_read_manifest()` + `is_reading()` (number range >= 500 **or**
registry presence, so an unregistered reading still classifies) and a per-class
`status()`. Inapplicable findings are **preserved**, not dropped, under
`planned_audit_issues` / `read_audit_issues`, mirroring `legacy_audit_issues`.
Helpers inserted **below** `READ_MANIFEST_PATH` so they cannot NameError at
import (run 009's lesson). Backup `robust_pipeline.py.bak-run059`; exactly
**one** pre-existing function changed, 49 byte-identical including `preflight`,
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`, `verify_feed`,
`reconcile`, `registry_audit`, `push_to_remote`, `_legacy_episode_numbers` and
`watchdog`.

`status` and `watchdog` now report **`healthy: true` / `stale: []`** for the
first time, with 501 as `kind: read`, `preflight_ok: true` and its six findings
retained under `read_audit_issues`.

**Nothing granted.** `failed`/`blocked`/`rendering` still pin unhealthy; an
interview in any production or published state still has to pass preflight; a
planned stub waives nothing for a sibling episode; the status literal
`published` alone still does not confer the legacy waiver while a genuine import
still is exempt *and named*; a published reading with a refused, missing or
corrupt gate is a **refusal, not a waiver**; wrong-case status does not unlock
the published arm.

Proof: repro **38/38** against the unmodified module (including the control that
the live tree's unhealthy verdict rests on 501 alone, and that `watchdog` returns
`healthy: false` with `stale: []` — nothing actually stuck), fix proof **65/65**
(pre-fix backup still reproduces; 10 nothing-granted classes; blast radius).
Tests `tests/test_status_health.py`, suite **108 -> 134**, load-bearing: 19 of 26
fail against the pre-fix module.

Two harness bugs, neither a code defect (run 029's rule): the scratch tree needed
**every** `pipeline/*.py` copied, since `preflight()` imports `quoted_span_gate`
by bare name; and the legacy fixture was numbered **900**, which falls in the
read range (>= 500) and so classified as a reading — a legacy interview here is
numbered 001-003. Also re-learned run 042's lesson: build read-lane fixtures by
importing `REQUIRED_DISCLOSURE`, never by retyping it.

Docs: `ROBUST_PIPELINE.md`'s Watchdog section now records the classifier and the
two ordering constraints, and its **Tests** section was badly stale — it claimed
this tree has *no `tests/` directory* and that `unittest discover` failing is
"expected here, not breakage", which would have made a future slice skip the
suite or misread a real failure. It now documents the 134-test suite.

Real tree after the slice: `coverage` ok 3/3, `registry` ok, `verify --remote`
ok, `preflight` 001-003 ok, three `reconcile --write` at 0/0/0, `feed.xml` md5
**unchanged** and byte-identical to live, 3 items.

## 2026-11-14T08:1xZ — run 053 (registry divergence had no detector here)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; the same 18
items still unfiled in the parent YF84AUZK, David's lane call). `coverage` ok
3/3, `registry` ok, `verify` ok with no issues, three `reconcile --write`
passes at 0/0/0, preflight 001-003 ok, feed md5 equal to live. No production
unit, so the slice closed a port gap.

**Defect.** HITL gained `registry_audit()` in its run 491 and this tree never
received it, so nothing here detected the two durable registries disagreeing.
`coverage` cannot: it unions the published set from BOTH registries, so an
episode missing from one is still counted via the other and the gap is masked.
`reconcile` cannot: it iterates `episodes/NNN` directories and compares each
against its own ledger record, never asking whether the two registries agree.
That silence is the documented cause of the sibling tree's worst publication
gaps (026 live-absent two months, 042 published-but-unregistered), and this
tree's docs were still asking each run to diff the two files by hand.

One finding is **sharper here than in the sibling**: for `missing_from_ledger`,
`reconcile(write=True)` — which every slice runs — does not merely stay silent,
it SILENTLY RECREATES the absent record as a `planned` stub, destroying the
published status. The repro demonstrates that, so the class is a data-loss
path here and not just an unreported disagreement.

**Fix.** Ported `registry_audit()` + the `registry` subcommand, with two
retargets this tree requires: ownership goes through `lane_ownership()` /
`duplicate_owners()` (run 033) rather than the sibling's interview-only
`sources` sweep, so two readings of one paper are a conflict while an
interview+reading pair stays legal; and a reading is NOT exempt from
`missing_from_manifest`, because `read_lane.sync_durable_state()` mirrors
readings into both registries here by design (run 009) — the sibling's comment
assumes the opposite. Read-only, writes nothing, grants nothing, not a
publication gate. Backup `robust_pipeline.py.bak-run053`; 47 functions
byte-identical including `preflight`, `review_gate`, `fidelity_gate`,
`verify_feed`, `feed_coverage`, `publish_local`, `reconcile`,
`lane_ownership`, `duplicate_owners`; only `main()` changed and only by three
CLI wiring lines, asserted individually.

Real state reads `ledger_episodes: 4, manifest_episodes: 3, ok: true` — the
asymmetry is the 501 no-work ledger stub, correctly not demanded in the
manifest because its status is not in the published family.

Proof: repro 28/28 against the unmodified module (all three classes silent,
plus the reconcile-destroys-the-record demonstration); fix proof 61/61
including pre-fix-still-reproduces and the nothing-granted sweep — the benign
move lag still passes, all six non-published statuses are not demanded in the
manifest while all three `published*` ones are, wrong-case `PUBLISHED` does not
trigger the demand, cross-lane sharing stays legal, a malformed registry is
reported rather than raised, and three consecutive audits mutate no registry
byte. Tests shown load-bearing by reverting to the backup (exit 1), then
restoring and confirming md5 identity.

Also documented `registry` in ROBUST_PIPELINE.md (command list, a prose
section beside `coverage`'s explaining what each of the two proves, the
standing-checks block) and retired the hand-diff instruction — a doc that
outlives its defect routes the next slice around the gate (run 031's lesson).

Harness note: both proof failures were harness bugs, not code defects (run
029's rule). The scratch tree copied only `feed.xml` and no `feed-site` mp3s,
so `coverage` failed on absent enclosures rather than on the injected gap —
the blindness assertion now tests `missing_from_feed` and the absence of any
"manifest" mention instead of a bare `ok` flag. And `main()` MUST change,
since it carries the CLI wiring; the assertion now bounds that change to three
registry lines rather than forbidding it.

# Production log

## 2026-11-12T09:5xZ — run 042 (read verdict bound to its audio)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; 18 items still
unfiled in the parent YF84AUZK, David's lane call). `coverage` ok 3/3, `verify`
ok with no issues, three `reconcile --write` passes at 0/0/0, preflight 001-003
ok. No production unit, so the slice closed a latent defect.

**Defect.** Run 040 recorded `audio_sha256`/`audio_bytes` beside the read
verdict and described them as provenance the gate never inspects. Nothing read
them, so they documented a hazard instead of gating it. Reachable by an ordinary
operator sequence: `render_episode()` writes the mp3 and NO registry, while
`record_verdict()` runs only from the CLI `verify` branch -- so
verify -> `build --force` for another paper -> render leaves `verified: true`
beside a digest of the PREVIOUS audio, and `publish_feed.read_episodes()` ships
on that flag alone. The word checks cannot see it: coverage reads 1.0 because
both sides of the comparison were written in the same breath.

**Fix.** `fidelity_gate()` re-hashes `episodes/NNN/episode-NNN.mp3` and refuses
on mismatch, naming both digests and pointing at `read_lane.py verify`. Checked
there so the read lane keeps one verdict with one owner. A missing digest is a
refusal, not a waiver. Backup `robust_pipeline.py.bak-run042`; exactly one
function changed, 45 byte-identical including `preflight`, `review_gate`,
`verify_feed`, `feed_coverage` and `publish_local`. Live registries and
feed.xml md5-unchanged throughout.

Also updated two now-stale `ROBUST_PIPELINE.md` passages that asserted no gate
inspects audio provenance, and added a section for the fix -- a doc that
outlives its defect routes the next slice around the gate (run 031's lesson).

Proof: repro 19/19 against unmodified code (the swap passes with an empty issue
list), fix proof 39/39 including pre-fix-still-reproduces and seven
nothing-granted refusals. Harness note: the repro's first run false-failed on
its own fixture, which paraphrased `REQUIRED_DISCLOSURE` instead of using the
exact constant -- the guard was right and the harness was wrong.

## 2026-11-12T00:53Z — run 040 (read lane: verify now persists its verdict)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0), `coverage`
ok 3/3, `verify` ok with no issues, three `reconcile --write` passes at 0/0/0.
No production unit available, so the slice closed a latent defect.

**Defect.** `register()` runs only inside `build()`, before audio exists, so a
reading was always recorded `verified: false` / status `built`. Neither
`render` nor `verify` ever rewrote that, so a reading that PASSED the fidelity
gate stayed unpublishable: `fidelity_gate()` refuses on the flag and
`publish_feed.read_episodes()` emits nothing. The only flag-flipping route was
`build --force` after rendering -- run 032's stale-audio hazard.

Latent in the now-familiar way: no reading has ever registered in this tree, so
every green check was accurate and blind. It would have fired on the first real
Read item, the exact unit runs 006-012 spent six slices preparing.

**Fix.** New `record_verdict()` called from the CLI `verify` branch; `verify()`
itself stays side-effect free. Also records `audio_sha256`/`audio_bytes` as
provenance the gate never inspects. Backup `read_lane.py.bak-run040`; only
`main()` changed, 30+ functions byte-identical; live registries and feed.xml
md5-unchanged throughout.

Proof: repro 29/29 against unmodified code, fix proof 56/56 including
pre-fix-still-reproduces and three no-weakening tampering cases.
