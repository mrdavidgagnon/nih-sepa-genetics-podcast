## Run 077 (2026-11-18) — the shipping command never compared deployed bytes

Both intake lanes empty (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0; the 18
unfiled items still sit directly in `YF84AUZK` awaiting David's lane call), so
no production unit. Opening audits all green: `coverage ok` 3/3, `registry ok`
(ledger 4 / manifest 3), `feedsync ok` (committed md5 == regenerated),
`drift ok` (10 identical), `verify ok` 0 issues / 29 checks, `status healthy:
true`. Stale lock from run 076 had a dead owner pid (310383) and a free
advisory lock — the normal steady state; released with `unlock --force`.

**Defect.** `push_to_remote()` — the mandated shipping command — declared a
deploy live on `verify_feed(..., remote=FEED_BASE)` alone, and every remote
probe there is an **existence** probe: show notes, cover art and the landing
page get HTTP 200 plus a few bytes, enclosures only their `Content-Range`
total, the deployed feed only a GUID-set comparison. So a deploy whose
`feed.xml` text, notes, cover or `index.html` was rewritten satisfied the wait
loop with `ok: true` and an **empty issue list**, and `push` reported it live.

The detector already existed: `deploy_drift()` md5s deployed text against local
and checks binary deployed length, and it refuses every one of those classes.
It was **CLI-only** — `grep` shows its single call site is the argparse
dispatch — so no gate and no shipping command reached it. The operator's
live-vs-local md5 habit was the only thing covering the gap, and only on the
*next* slice.

Sharpest part: `tests/test_deploy_drift.py` deliberately pinned that
`publish_local()` and `verify_feed()` do **not** call the comparator (it must
stay a non-gate) — and that is correct. But `push_to_remote()` is a **third
caller the test never named**, and that unnamed caller was the defect. A test
enumerating the callers a function must not have does not establish which
callers it should.

**Fix.** The wait loop breaks only when `verify_feed` **and** `deploy_drift`
both pass; the final `ok` is `live_ok and drift_ok`; the drift verdict is
reported under its own top-level `drift` key (run 041: a distinct assertion
gets a distinct key, never another check's dict) with its issues appended.
`_deploy_drift_verdict()` is **fail-open** on an exception (run 055: a helper
on the publish path that could raise would make every deploy impossible), while
a definite `ok: false` is never downgraded. `deploy_drift()` stays read-only
and is still not an episode gate.

**Proof.** Repro 23/23 against the unmodified module: `push` breaks on
`verify_feed`'s ok, does not call the comparator, and a deploy with every GUID
intact but rewritten feed text / notes / index / cover is reported
`ok: true, issues: []` — with `deploy_drift` refusing the identical deploy as
the control, proving the detector worked and only the call site was missing.
Proof 48/48: pre-fix backup still reproduces; each of the four text classes now
refused and named; **nothing granted** — a clean deploy still passes with an
identical verdict pre/post, the comparator stays out of `publish_local` and
`verify_feed`, `deploy_drift` still writes nothing, a comparator fault fails
open while a refusal is passed through, and local `verify`/`coverage`/`registry`
still pass. Blast radius: exactly **one** pre-existing function changed
(`push_to_remote`), **65** byte-identical including `preflight`, `review_gate`,
`fidelity_gate`, `feed_coverage`, `publish_local`, `verify_feed`,
`registry_audit`, `reconcile`, `deploy_drift`, `feed_sync` and `status`.
Additive: 3 removals, all three the deliberately-rewritten wait-loop lines.

The same-length binary byte swap stays outside the range probe's reach — a
documented limit, with `preflight`'s `checks.audio.sha256` (run 045) covering
audio provenance.

Tests `tests/test_push_deploy_drift_gate.py` (13), suite **460 -> 473**,
load-bearing: 10 failures/errors against the pre-fix module (restored
md5-identical afterwards). `ROBUST_PIPELINE.md` documents it and its stale
460-test count is corrected to 473.

Harness trap, a harness bug not a code defect (run 029's rule): section A
false-failed on all four classes because a module copied into scratch resolves
`ROOT` from **its own** location — the relocated pre-fix module was reading
`/opt/data/profiles/joshua/cache/scratch` and returning a truncated verdict
that reads exactly like "the bug is not real". Run 066's trap recurring;
repoint every `*_PATH`/`ROOT` global at the real tree before trusting a
relocated backup.

Audits after the fix: `coverage ok` 3/3, `registry ok`, `feedsync ok`,
`drift ok`, `verify ok` (0 issues / 29 checks), `verify --remote ok`,
live-vs-local `feed.xml` md5 identical (`9fc23235fcb49ca809059092da619b54`,
unchanged all slice), 473 tests OK. No feed byte moved; nothing published.

## Run 076 (2026-11-18) — the committed feed was never compared to its generator

Both intake lanes empty (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0; the 18
items still sit unfiled in the parent `YF84AUZK` — David's standing lane call,
not re-raised). Opening audits all healthy and all blind: `coverage` ok 3/3,
`registry` ok (ledger 4 / manifest 3, the 501 stub), `verify` local ok with 0
issues / 29 checks, `verify --remote` ok (3 local / 3 remote, both drift lists
empty), three `reconcile --write` passes at 0/0/0, `status healthy: true`,
suite 435/435. Stale lock owner pid 194175 dead and the advisory lock free —
the normal steady state; cleared with `unlock --force`. No production unit, so
the slice closed a latent defect.

**Defect.** Every file in `feed-site/` is **derived** from the registries, and
nothing in this tree ever compared the **committed** bytes to what
`publish_feed.py` **generates now**. A registry edit that is never republished
was therefore invisible offline, and the next `push` deploys it. The sibling
tree gained `feed_sync()` + a `feedsync` subcommand for exactly this class; a
`--help` census (run 053's method, not run 010's line-count diff) showed both
absent here.

Proven reachable by perturbation against the real catalogue. A manifest
**title** edit, a manifest **description** edit, a stale committed **notes
body**, and a rewritten episode title inside **index.html** each left
`coverage`, `registry`, `verify` and `reconcile` at `ok: true` with **empty
issue lists** — the verdict `publish_local()` refuses on and
`push_to_remote()`'s wait loop breaks on to declare a deploy live.

**Why no existing audit covers it.** Each asks a question whose expectations
come from the artifact itself: `coverage` relates registry records to the
committed feed, `registry` relates the two registries to each other, `verify`
scores the committed document against itself and disk, `reconcile` compares
episode dirs to ledger records, and `drift` compares **live** bytes to
**local** bytes — so once a stale commit is deployed, live equals local and
drift passes. None of them holds the generator's output as the reference.

Two near misses worth recording. `verify_feed()`'s `index_page` check **does**
catch an omitted episode and a wrong show name (both controls fired), but reads
only `<title>`/`<h1>`, local hrefs and the `episode-NNN` number set — never the
link **text**, so a rewritten episode title passes. And the notes arm is the
sharpest: a notes-body edit leaves `feed.xml` **byte-identical** whenever the
numbered citation entries are untouched, and the notes are a published
deliverable carrying the unabridged disclosure, the evidence boundaries and
every Zotero link.

**Fix.** Ported `feed_sync()` + `_feed_diff_sample()` + the `feedsync`
subcommand, with three retargets this tree required (run 053's rule — read the
sibling's assumptions against *this* tree's behaviour): its docstring credits
the stale-feed class to a forgotten hardcoded `EP` append, which cannot happen
here because `interview_episodes()` derives the list (run 010), so the cause is
reworded to a registry edit; `PUBLISH_FEED_PATH` had to be added to the
constants block; and `import io` was absent. `.mp3` enclosures are excluded by
design — already audited for presence and advertised length by `coverage` and
actually decoded by the run-058 duration check. It renders into a private temp
dir, writes nothing, and is **not** a publication gate.

**Proof.** Repro 43/43 against the unmodified module (all four classes shipping
`ok: true` with empty issue lists; controls: an omitted index entry and a
deleted committed notes file are both already refused). Proof 76/76: pre-fix
backup still reproduces; each class refused and named with both digests;
nothing granted — the real tree still passes, `coverage`/`registry` verdicts
unchanged, and the run-038/057/066 gates plus preflight all still bite. Two
functions added, **only `main()` changed** among pre-existing ones (a new
subcommand legitimately changes it — bounded to 4 added lines, 3 naming the
command, and exactly 1 reworded exit-code line), with
`preflight`/`review_gate`/`fidelity_gate`/`verify_feed`/`feed_coverage`/
`publish_local`/`push_to_remote`/`registry_audit`/`reconcile`/`deploy_drift`
byte-identical. Additive: +272 lines, 1 distinct line retired.

**Mutant sweep, because reverting to the backup is a weak proof here** — the
pre-fix module has no `feed_sync` at all, so all 22 tests die on
`AttributeError`, proving only that the file changed (run 054's lesson). 18
single-fault mutants on the **new** structure: **18/18 caught**. The sweep
earned its keep twice — **M10 exposed a real test gap** (a generator raising
inside `main()` is a different branch from one raising at *import*, and the
suite tested only the import path), fixed by splitting into four generator-
failure tests; and **M16 was a bad mutant**, inserting only a comment, so its
survival was correct and the mutant was repaired rather than the code.

Tests `tests/test_feed_sync_audit.py` (25), suite **435 → 460**. One test
failed first and was **my test's wrong semantics, not a code defect** (run
029's rule): `_feed_diff_sample`'s `limit` bounds differing **runs**, not
output lines — the counter is tested once per difflib opcode, so one giant
replace run emits every line of it. Replaced with an interleaved-opcode case
asserting the bound plus an explicit test that a single differing run is
emitted in full. The helper is otherwise identical to the sibling's apart from
a deliberate `new` → `newline` rename avoiding the shadowed builtin-ish name.

**Docs (run 031's rule).** `ROBUST_PIPELINE.md` gained `feedsync` in both
command blocks and a section explaining why each of the five existing audits is
structurally unable to cover the class, and its **Tests** section was corrected
from a stale **187 tests across ten modules** to 460 across twenty-six, with a
note that a count in the doc is a snapshot and `unittest discover` is
authoritative. The stale-doc grep returns only my own replacement prose.

**Lesson.** Every audit here relates records to artifacts or artifacts to each
other; this is the first that relates an artifact to its **producer**. When a
deliverable is *generated*, ask what holds the generator's current output as the
reference — a check whose expectations are read from the artifact under test can
only ever prove self-consistency. The near-miss pattern generalizes too:
`index_page` reads the fields it can *name* (`<title>`, hrefs, the number set)
and is blind to a value only the generator knows, so "this file has a check"
and "this file's content is pinned" are different claims.

Audits after the fix: `coverage ok: true` (3/3), `registry ok: true`,
`feedsync ok: true` (committed == regenerated, notes 3, site text 1),
`verify ok: true` (0 issues / 29 checks), `verify --remote ok: true` (3 local /
3 remote, both drift lists empty), live-vs-local `feed.xml` md5 identical
(`9fc23235fcb49ca809059092da619b54`, unchanged all slice), `status healthy:
true`, `py_compile` clean, suite 460/460. No feed byte moved; nothing published
this run.

Harnesses: `/opt/data/tmp/mm_feedsync_repro_run076.py` (43),
`mm_feedsync_proof_run076.py` (76), `mm_feedsync_mutants_run076.py` (18).

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

## Run 075 (2026-11-18) — the advertised show-notes LINK had no reader

No production unit: Summerize (`V4WXTY8M`) and Read (`DV6F4ILX`) both empty on a
live read; the 18 unfiled items in the parent (`YF84AUZK`) remain David's
standing lane call, already raised. Stale lock (dead pid 68025) cleared with
`unlock --force` — the normal steady state, not an incident. Slice spent on a
durable defect.

**Defect.** `verify_feed()` pulled every item's show-notes href out of
`<content:encoded>` and reduced it to `Path(urlparse(href).path).name`, then
asked only whether that filename exists locally / returns HTTP 200 live. The
href's **value** was read by nothing, so three classes shipped with
`verify_feed()` returning `ok: true` and an **empty issue list** — the verdict
`publish_local()` refuses on and `push_to_remote()`'s wait loop breaks on to
declare a deploy live:

- **repointed at another episode** — 001 advertising `episode-003-notes.md`
  sends every listener to the wrong paper's citations, evidence boundaries and
  Zotero links. The existence probe is *satisfied*, because the file it names
  is a real published deliverable.
- **absent entirely** — with no href the loop body never executes, so the
  item's notes are probed zero times. Run 041's lesson per item: a check that
  iterates what it finds cannot see what is missing. The 064 disclosure guard
  still passes, since the mandated *phrases* are all present; only the route to
  the full notes is gone.
- **repointed at the sibling show** — the documented hard bug, and the case the
  two neighbouring guards structurally cannot reach: run 063's
  `advertised_base` iterates XML **attributes** plus `url`/`link` **element
  text**, and this href is neither (it lives inside a CDATA blob), while the
  existence probe collapses the cross-show URL to its local filename and passes
  it.

The show notes are a published deliverable — they carry the unabridged
disclosure, the evidence boundaries and every numbered citation with its Zotero
link, deliberately left in full when David shortened the *spoken* disclosure to
one sentence (2026-11-03). This href is a listener's only route to them from a
podcast client.

**Fix.** `SHOW_NOTES_LINK_REQUIRED` + a `show_notes_link` check scored against
the item's own GUID-derived number, making it a cross-field **agreement** test
rather than a second opinion about which file is correct. Both lane spellings
accepted for a reading. No legacy waiver (run 036). Scoped by control: an href
naming a file that does **not** exist was already refused by the existence arm,
so the unread classes are all right-shape/wrong-target plus outright absence.

**Proof.** Repro 34/34 against the unmodified module (all three classes
`ok: true` with empty issue lists, indistinguishable from intact; controls: a
missing target and a broken disclosure both still bite). Proof 48/48: pre-fix
backup still reproduces; each class refused and named; nothing granted — the
real feed's verdict identical pre/post, both reading spellings accepted, and the
036/038/058/063/064/066 guards all still refusing. Exactly one pre-existing
function changed (`verify_feed`), 61 byte-identical including `preflight`,
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `registry_audit` and `reconcile`. Additive: +121 lines, 0
removals. Tests `tests/test_show_notes_link_gate.py` (16), suite **419 -> 435**,
load-bearing (11 failures against the pre-fix module).

**Fixture debt paid, same class as run 074.** 12 suites wrote a
`<content:encoded>` block with the disclosure prose but no show-notes href — a
block `publish_feed.py` is *incapable* of producing, since `notes_html()` and
`read_notes_html()` both emit the link unconditionally in every lane. Those
failures were fixture incompleteness, not gate findings. Patched with the href
plus, where a suite builds a feed-site, the notes file the existence arm
already probed.

Audits: `coverage ok: true` (3/3), `registry ok: true`, `verify ok: true` (0
issues / 29 checks), `verify --remote ok: true` (3 local / 3 remote, both drift
lists empty), live-vs-local `feed.xml` md5 identical
(`9fc23235fcb49ca809059092da619b54`, unchanged all slice), `status healthy:
true`. No feed byte moved; nothing published this run.


## Run 088 — the read fidelity verdict was bound to the audio but not to the two artifacts it scored

Run 040 stored `audio_sha256` beside a reading's verdict and run 042 wired
`fidelity_gate()` to read it. The two files the gate actually **scores** —
`script.md` and `source.txt` — were required to *exist* and never compared.
`read_lane.py` hashes `script.md` into `parts-read/render-plan.json`, but that hash
has exactly one reader (run 032's render-cache guard), so the publication gate never
consulted it. An operator who corrects `script.md` after `verify` — drops a sentence,
or re-extracts `source.txt` — keeps `verified: true` and the stored coverage figure,
so `fidelity_gate()` grants publication for a deliverable the gate itself would now
fail, and the published show notes keep asserting a fidelity claim that no longer
holds. Run 030/032's provenance class in the verdict half of the lane.

**Fix.** `read_lane.verify()` now returns `artifact_digests` (sha256 of the exact
bytes it scored), `record_verdict()` persists them beside the verdict, and
`fidelity_gate()` re-hashes both files and refuses on mismatch naming both digests.
A **missing** digest is a refusal, not a waiver (runs 036/042): a pre-run-088 entry
must be re-verified. `verify()` the function stays side-effect free.

**Proof.** Load-bearing: 6 of the 8 tests in `tests/test_verdict_artifact_binding.py`
fail against the pre-fix backups (`pipeline/*.bak-run088`) — the post-verdict script
edit, the post-verdict source re-extraction, the missing-digest refusal and the
persist test each return `ok: true` / no digest pre-fix; the two no-weakening tests
(`verify` side-effect free, gate grants nothing it already granted) pass on **both**
sides. Full suite **546 tests OK**. Additive: 0 removed lines outside the ledger's own
writer. Exactly three functions changed — `verify`, `record_verdict`, `fidelity_gate`
(32 + 75 functions, the rest byte-identical).

**Audits.** `coverage ok: true` (3/3), `registry ok: true` (4 ledger / 3 manifest —
the 501 no-work stub), `feedsync ok: true` (committed md5 == regenerated,
`9fc23235fcb49ca809059092da619b54`), `status healthy: true`. Live Summerize V4WXTY8M
and Read DV6F4ILX both empty against durable state; nothing published this run.


## Run 091 — run 090's gate fix committed and the corrected episode 001 audio deployed live

Run 090 added the render-plan reader to the interview publication gate (run 088's class in
the interview lane: the render plan's `script_sha256` had only the run-032 render-cache reader,
nothing on the publish path) and re-rendered episode 001 from the corrected script, but died
before deploying. Its gate change and `tests/test_render_plan_provenance.py` were still
uncommitted at the start of this slice; committed as run 090 after re-verifying that
`preflight 001 --audio` is `ok: true` with the plan digest matching the current script
(27f3fa638d9b) and the on-disk mp3 matching the stored `audio_sha256`.

**Deployed.** `push --episode 001 --wait 240` -> `pushed: true`, `ok: true`, 11673574 bytes
staged. Live `feed.xml` md5 now identical to local (`3570d744126e2d3ac136ce275443ad29`); the
live item carries `length="11657900"` and `duration 00:12:09` for the re-rendered audio, which
is what the shipped script actually speaks. Byte-range 206 on `episode-001.mp3`, 200 on
`episode-001-notes.md`.

**Notes defect fixed in the same pass.** `episodes/001/episode-notes.md` asserted
"Approximately fifteen minutes" for an episode that measures **12:09** (728.5 s by ffprobe) —
a published deliverable stating a duration no artifact supports. Reworded to the measured
runtime, and the tree-root mirror re-synced (the gate refuses root-vs-`feed-site/` drift, and
Pages serves the root). Live notes now carry the measured figure.

**Ledger.** 001 restored to `published_and_moved` on evidence; no Zotero write was needed —
live `items/<key>` reads show all five source parents (4UDPRQZR, FFGWMS4C, BGWWIUWC, BW34V8PX,
QNHR6NPF) in Produced (6P2KVFKQ) with no intake membership left.

**Audits.** `coverage ok: true` (3/3, every enclosure length == on-disk size),
`registry ok: true` (4 ledger / 3 manifest — the 501 no-work stub), `feedsync ok: true`
(committed md5 == regenerated), `verify --remote ok: true`, suite **552 tests OK**. Read
DV6F4ILX and Summerize V4WXTY8M both empty against durable state.


## Run 092 — the read lane's `audio` field decided the delivered bytes and had no reader

`publish_feed.py` open-coded `ROOT/episodes/<num>/<rec['audio']>` twice: once in
`read_episodes()` to test existence, once in `main()` to copy the file into
`feed-site/`. No gate ever compared that registry field to anything. The read
fidelity gate hashed the path it merely **assumed** — `episode-NNN.mp3` — and
reported the digest of that assumed file against the digest recorded by
`read_lane.verify()`, which is the digest of the file `render_episode()` wrote
under the canonical name. So the gate blessed the verified audio while the copy
step obeyed the field, and the two never looked at the same file.

Repro (scratch tree, stub mp3s, no TTS spend, real `main()` and real
`publish_local()`): a registry entry for reading 991 whose `audio` field is
`../990/episode-990.mp3` passes `fidelity_gate` with an **empty issue list** —
the gate hashed 991's own canonical file, which matched its recorded digest —
and the mandated publish command accepted it and wrote episode **990**'s bytes
into `feed-site/episode-991-reading.mp3`. `verify_feed` (existence + length +
digest-vs-registry), `feed_coverage` (GUID + enclosure + title) and
`registry_audit` all reported ok on the resulting feed: each checks the field it
was written to check, and none checks *which file the field names*. The control
shows the detector is not broken — the same wrong bytes reached through the path
the gate does read (canonical field, swapped file) are refused with the digest
mismatch. The defect was the unread field, not a weak hash.

A non-string field was worse in a different way: the copy step had no validation
at all, so `Path / int` crashed `main()` mid-publish rather than refusing.

**Fix.** One resolver, `publish_feed.read_copy_source(num, rec, root=None)`, used
by both call sites and by the gate; `root` lets the gate anchor the path to the
directory it is auditing while the rule (field, default, anchor) stays in one
place. `fidelity_gate` now hashes the file the copy step will actually ship and
refuses a field that escapes `episodes/<num>/` or is not a usable filename, and
reports `shipped_from` in its audio check. `main()` refuses instead of crashing.

**Nothing granted.** The canonical case still passes with an empty issue list;
missing digest, coverage below the 99.5% floor and missing `source.txt` still
refuse; every resolved path still stays inside its own episode directory. Proof:
8 checks on the pre-fix copies (defect reproduced), 15 on the fixed modules
(refused, wrong bytes never reach `feed-site/`, canonical reading still
publishes with its own bytes), `tests/test_read_copy_source_gate.py` 7 tests —
4 fail against `pipeline/*.bak-run092` and pass on the fixed tree. Full suite
559 tests OK. Function census: `fidelity_gate` changed, `_read_copy_source` and
`read_copy_source` added, 74 of 75 `robust_pipeline` functions byte-identical.

The repro opened attempt `501-1795286619` (superseding attempt 85, marked
`stopped`); that ledger write is committed with this run. No live feed change:
no reading was re-rendered or redeployed.

## Run 093 — the show notes stated a production record that nothing compared to the sources it states

`write_notes()` has exactly one call site, `build()`, which necessarily runs before
any audio exists. It printed, into a published deliverable, two claims about this
pipeline's own behaviour:

- `Fidelity gate: {coverage} of extracted words present ...` — stated as a gate
  result, while the same call had returned `ok=False` with "no audio rendered yet";
- `Rendered: {rendered} ({voice})` — a date and a voice for an event that had not
  happened, taken from the module constants `VOICE` / `RENDER_TEXT_VERSION` rather
  than from any record of the render.

Nothing read those claims. `record_verdict()` (run 040) persists the real verdict but
must not silently rewrite a published deliverable, so it never touched the notes;
`feed_sync` "regenerates" the notes by copying the very file it audits, so it can only
prove byte-identity with its own copy — a claim inside the record can never disagree
with the registry. The record was the only place in the read lane where a claim about
the pipeline's behaviour was published with no reader.

Repro (scratch tree, real functions, silent `ffmpeg anullsrc` audio, no TTS spend):
18 checks on the pre-fix copies — single call site proven by AST, the record written
before any render, the gate figure asserted as a result while the same call had
refused, a render date naming a voice for an event that had not occurred,
`record_verdict()` not rewriting the notes, `feed_sync` reporting ok on a record whose
figure was hand-edited to disagree with the registry, and the published copy carrying
the contradicted figure.

The same family produced a second, independent refusal: `preflight()`'s render-plan
provenance check read the **interview** lane's directory (`parts-robust`) for both
lanes, so a genuine reading with a correct plan in `parts-read` was refused at publish,
while the plan the read lane actually wrote was read by nothing on the publish path.

**Fix.** Two halves. (1) The writer states the verdict the gate actually returned
("gate NOT PASSED at write time") and does not claim a render before one exists; after
a render the two claim lines are brought into agreement by `refresh_notes_record()`,
which reads the render plan — the only record of the event — touches only those two
lines, leaves run 040's protected build-time facts byte-identical, and refuses to
invent a notes file `build()` never wrote. It is an explicit operator command, not a
side effect of `verify()`. (2) `fidelity_gate()` — the single read verdict with one
owner — now reads the parsed record and refuses where its claims disagree with the
registry (figure, verdict) or with the render provenance (date, voice, missing plan).
It grants nothing. `render_plan_for_lane()` resolves the plan path from the lane the
record belongs to and is used by both `preflight()` and `fidelity_gate()`.

**Nothing granted.** The canonical case still passes with an empty issue list; a
record that claims a render with no plan, a figure that disagrees with the registry, a
verdict that disagrees, a render date that predates the plan, a voice that disagrees,
or a record that states no verdict, is refused. Existing refusals still bite: missing
digest, coverage below the 99.5% floor, missing `source.txt`, script digest mismatch.

Proof: 18 checks on the pre-fix copies (defect reproduced);
`tests/test_notes_production_record_gate.py` — 17 tests, all pass on the fixed tree,
3 fail and 14 error against `pipeline/*.bak-run093`. Full suite 576 tests OK.
Function census: `read_lane.py` 35 functions — `write_notes`, `main` changed, 4 added
(`refresh_notes_record`, `render_claim`, `render_plan_for_read`, `voice_claim`), 31
byte-identical; `robust_pipeline.py` 70 — `fidelity_gate`, `preflight` changed, 2 added
(`notes_production_record`, `render_plan_for_lane`), 68 byte-identical.

Attempt `501-1795303437` (superseding attempt 86, marked `stopped`) was closed
`completed` with detail "defect slice"; no render and no publish for 501. No live feed
change: no reading was re-rendered or redeployed.
