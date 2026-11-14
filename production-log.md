# Moral Machines - production log

Cloned from the Human in the Loop pipeline 2026-11-03. Episodes numbered from 001; readings from 501.

## 2026-11-14T20:5xZ — run 056 (a stale deployed feed verified green)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; the same 18
items still unfiled in the parent YF84AUZK, David's lane call, not re-raised).
`coverage` ok 3/3, `registry` ok (4 ledger / 3 manifest, the 501 stub),
`verify --remote` ok with no issues, three `reconcile --write` passes at 0/0/0,
preflight 001-003 ok, feed md5 `9fc23235…` equal to live. No production unit,
so the slice closed a latent defect on the deploy path.

**Defect.** `verify_feed()`'s remote branch asserted only "HTTP 200 and at least
one RSS item" about the DEPLOYED feed.xml. Every other remote probe iterates the
items the LOCAL feed carries and resolves each asset by filename, so a deploy
whose enclosures and notes landed while feed.xml did not returned `ok: true`
with an EMPTY issue list — the assets verified green exactly because they were
probed from the local feed, not from the one serving subscribers. And that
verdict is `push_to_remote()`'s success criterion: its wait loop breaks on it
and `result["ok"]` is set from it, so the only check between a half-finished
push and "live" was blind to the half that was missing. The class is the
stale-repo-root trap the docs warn about by hand (`push` is mandated precisely
because a manual `git push` leaves the root feed stale) with nothing on the path
enforcing it.

**Fix.** The deployed item set is now compared against the local one by GUID in
both directions: `missing_from_remote` (an episode listeners cannot see) and
`only_on_remote` (the live site is ahead of this tree), each an issue naming the
GUID, with `local_items`/`remote_items` recorded on the `remote_feed` check. An
intact deploy yields two empty sets and the previous verdict stands, so nothing
is granted. Backup `robust_pipeline.py.bak-run056`; exactly ONE function changed
with 47 byte-identical, including `preflight`, `review_gate`, `fidelity_gate`,
`feed_coverage`, `publish_local`, `registry_audit`, `reconcile` and
`push_to_remote` itself.

The detector already existed as operator discipline — the live-vs-local md5
comparison every slice logs. Run 041's lesson: when a read-only audit catches a
class the gates do not, wire it into the gate instead of relying on a habit.
Generalizable form: **a remote check that resolves what to probe from the LOCAL
artifact cannot detect that the remote artifact is stale.**

Latent in the now-familiar way: the live feed is byte-identical to local, so
`coverage` 3/3, `registry ok` and the old `verify --remote ok: true` were all
accurate and all blind. It would have fired on the first partial push.

Proof: repro `/opt/data/tmp/mm_stale_remote_feed_repro_run056.py` 27/27 against
the UNMODIFIED module — the stale deploy passes with an empty issue list, the
`remote_feed` check is shown recording only HTTP 200 with no item comparison,
all three asset probes run off the local feed, and an intact deploy is proven
INDISTINGUISHABLE from the stale one. Fix proof
`mm_stale_remote_feed_proof_run056.py` 51/51: pre-fix still reproduces; both
drift directions refused and named; nothing granted — an intact deploy still
passes with an identical verdict, a 404 / unparseable / zero-item live feed each
still refused as a check failure, local-only verify unaffected, and the run-038
empty-`<description>`, missing-enclosure and run-036 001-notes gates all still
bite. Real tree post-fix: `verify --remote` ok with `local_items: 3,
remote_items: 3` and both drift lists empty.

Tests `tests/test_remote_feed_drift.py` (9 cases; suite **72 -> 81**), shown
load-bearing by reverting to the backup — 6 failures/errors against the pre-fix
module — then restored with the suite green.

Harness note: a local `SimpleHTTPRequestHandler` spews `ConnectionResetError`
tracebacks when `urlopen` closes a byte-range response early; override
`handle_one_request` to swallow it, or real PASS lines get buried in noise that
looks like a failure. Scratch trees must symlink `feed-site/*.mp3` (another
filesystem, so `os.link` fails with `Invalid cross-device link`), and the
scratch `pipeline/` must go first on `sys.path` with `publish_feed` popped from
`sys.modules` — a stale sibling-show `publish_feed.py` in `/opt/data/tmp` will
otherwise hijack the bare-name import (run 055's trap).

## 2026-11-14T16:5xZ — run 055 (publish gates every episode it ships)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; 18 items still
unfiled in the parent YF84AUZK, David's lane call, not re-raised). Opening
audits all clean and all blind: `coverage` ok 3/3, `registry` ok (ledger 4 /
manifest 3), `verify` ok with no issues, status/manifest agree at
`published_and_moved` for 001-003, stale lock with a dead owner pid. No
production unit, so the slice closed a latent defect.

**Defect.** `publish_local()` preflighted only its `selected` set, but
`publish_feed.main()` rebuilds the whole feed and re-copies every emitted
episode's audio and notes into `feed-site/`. So `publish --episode 001` shipped
every other episode ungated. Proven in both lanes on real code: an interview
with no review panel, and a reading whose audio was swapped after its verdict
(the run-042 provenance refusal), each reached the rebuilt feed with their bytes
copied into `feed-site/` while publish returned ok: true and an empty issue
list. The read lane was never covered even by a bare `publish`, since a
reading's registry of record is read-episodes.json.

**Fix.** Gate `sorted(set(selected) | _emitted_episode_numbers())`, the helper
reading publish_feed's own derivation so the gate's scope cannot drift from what
is emitted. Fail-open by design. Backup `robust_pipeline.py.bak-run055`; exactly
one pre-existing function changed, 10 checked gate functions byte-identical.

Verified on the real tree after the fix: suite 72 OK, `coverage` ok 3/3,
`registry` ok, `verify` ok, and `publish --episode 001` now gates **001, 002 and
003** (was 001 alone) with all three passing, `feed.xml` md5 **unchanged** and
still 3 items. state.json moved only in `updated_at`/`attempt_log`; no episode
status changed.

Proof: repro 13/13 against unmodified code, fix proof 38/38 including
pre-fix-still-reproduces and seven nothing-granted cases. New regression tests
proven load-bearing (6 failures against the pre-fix module, green after restore,
md5 identical). Harness bug, not a code defect: a stale HITL `publish_feed.py`
in /opt/data/tmp shadowed the tree's copy via the bare-name import.

## 2026-11-14 - run 054: the Produced mover stripped BOTH intake lanes

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same **18** on-topic sources still sit directly in `YF84AUZK` with
`collections: ['YF84AUZK']` and no subcollection, so neither lane reads them.
Produced `6P2KVFKQ` holds the 10 parents of 001-003, each exactly
`['6P2KVFKQ']`. No production unit, so the slice closed a durable defect.
Opening audits: `coverage` ok 3/3, `registry` ok (ledger 4 / manifest 3 - the
501 no-work stub, correctly not demanded), `verify` ok with no issues and
`legacy_exempt_episodes: []`, manifest and state agree at `published_and_moved`
for 001-003, preflight 001-003 ok with audio, suite 45 OK. Stale lock owner pid
2012405 dead with the advisory lock free - the normal steady state, cleared with
`unlock --force`. Standing blocker unchanged and **not re-raised** (the lane
call is David's).

**Defect.** `pipeline/move_verified_sources.py` held one tuple of *both* intake
collection keys and did `[c for c in old if c not in LANES]` for **every** key
it collected, with no notion of which lane the episode came from. So the move
deleted the other lane's membership as collateral:

- publishing an **interview** of a paper David had also filed in Read destroyed
  the **Read** membership - the only durable record that he wanted a reading of
  it - de-queueing the reading before it was ever produced;
- publishing a **reading** destroyed a pending **Summerize** membership the
  same way.

One interview plus one reading of the same paper is **legal in this tree by
design**: run 033 keys ownership on the field name (`sources` vs `read_source`)
precisely so the pairing is not a false duplicate. The mover destroyed the other
half of exactly that sanctioned pairing. And the loss is **silent and
unrecoverable by inspection**: a Zotero collection edit raises no deletion
event, so an item dropping out of a lane is indistinguishable from David
unfiling it, which is this show's *documented* signal that he cleared the queue
on purpose. A future slice would have read the empty lane as his intent.

Two further defects in the same function: a reading was moved **without
consulting `read-episodes.json`**, so a source whose fidelity gate failed could
be filed as produced; and the plan was a flat key list, so a dual-use key could
not express one move per lane.

**Latent in the now-familiar way** (runs 008/013/031/033/036/040/042/045/053):
all 10 published parents are single-lane interview sources already sitting in
Produced, so `coverage` 3/3, `registry ok`, `verify ok` and a real `--dry-run`
on live state were all accurate and all blind. It fires on the first dual-use
paper - and 18 unfiled items are waiting for exactly the lane call that creates
one.

**Fix.** Lane-aware rewrite. `build_plan(manifest, state, read_manifest)` emits
one entry per **(source key, intake collection)**, deriving the intake from the
field the key is registered under; `move_one()` strips `c != intake` - exactly
one membership - and adds Produced. A dual-use key published in both lanes now
yields two entries and leaves each intake once. Readings require
`verified: true`. Backup `move_verified_sources.py.bak-run054`; 58 -> 217 lines.

**Deliberately NOT ported from the sibling tree.** Its mover selects on the
literal `published_pending_zotero_move`. Copying that would silently skip this
tree's documented end state `published_and_moved` - the run-005 gate-string
class, already fixed here in run 011. The `published*` family test is kept and
is now pinned by test. Same judgement as run 053's two retargets: read the
sibling's assumptions against **this** tree's behaviour, not just its code.

**Proof.** Repro **13/13** against the unmodified module (both directions of
the lane destruction, the ungated reading, live tree untouched). Fix proof
**61/61**: the pre-fix backup still reproduces; post-fix each lane strips only
itself with the parent and an unrelated collection preserved; **nothing
granted** - already-moved still issues no PUT, all six non-published statuses
and wrong-case `PUBLISHED_AND_MOVED` are refused, all three `published*`
statuses still selected, the ledger still governs selection over the manifest,
an unverified reading refused four ways, the version guard on the wire, two
412s retried, `--dry-run` writing nothing, and no sibling-show identifier in
the file.

**New committed tests, and a mutant sweep that found a gap in my own tests.**
`tests/test_move_verified_sources.py` (suite 45 -> 64). Reverting to the backup
is a **weak** load-bearing proof here - the pre-fix module has no import guard,
dies at import and proves only that the file changed - so I built **12
single-fault mutants on the new structure** instead. Eleven were caught and
**M7 survived**: deleting `If-Unmodified-Since-Version` from `make_client()`
passed a suite that only asserted on the version handed to an *injected fake*
`put()`, because a fake never exercises the header-building code at all. That is
the exact trap the sibling's notes record. Added `RealClientWireTests`, which
drives the real `make_client()` against a stubbed `urlopen` and asserts on the
outgoing `Request`: **12/12** caught, 64 OK, module restored md5-identical.

**Integrity.** `manifest.json`, `state.json`, `read-episodes.json` and
`feed-site/feed.xml` md5-identical throughout (`md5sum -c` clean). Live Zotero
re-read after the work: 10/10 source parents still exactly `['6P2KVFKQ']`, both
intake lanes still 0 - no write was made to the library. `ROBUST_PIPELINE.md`
gains "Only the episode's OWN intake lane is stripped" (purely additive bar one
whitelisted reworded line, diff removals 1 of 1 expected).

**Lessons.**

- **A bookkeeping step can destroy the queue it reads from.** The mover is
  documented as granting no gate, and that is true - but "grants nothing" says
  nothing about what it *deletes*. Audit a post-publication step for
  destructive scope, not just for whether it can wrongly pass something.
- **When two concepts are expressed by two fields, every writer needs the
  discriminator too.** Runs 033 and 053 fixed *readers* that consulted one of
  `sources`/`read_source`; this is the same axis rotated to the write side -
  the mover collected both fields and then threw the distinction away.
- **A mutant sweep tests the tests.** The no-weakening proof and the committed
  suite were both green while the version guard was untested. When the
  back-to-backup proof is weak, mutate the new structure one fault at a time
  and treat a survivor as a real gap in coverage.

## 2026-11-14 - run 052: the quoted-span CLI silently scored ONE paper of five

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same **18** on-topic sources still sit directly in `YF84AUZK` with
`collections: ['YF84AUZK']` and no subcollection, so neither lane reads them.
Produced `6P2KVFKQ` holds the 10 parents of 001-003. No production unit, so the
slice closed a durable defect. Opening audits: `coverage` ok 3/3, `verify` ok
with no issues and `legacy_exempt_episodes: []`, `reconcile` ok, manifest and
state agree at `published_and_moved` for 001-003, suite 38 OK. Stale lock owner
pid 1748266 dead with the advisory lock free (`flock` LOCK_NB succeeded) - the
normal steady state, cleared with `unlock --force`. Standing blocker unchanged
and **not re-raised** (the lane call is David's).

**Defect.** `pipeline/quoted_span_gate.py`'s operator-facing CLI declared
`--source` as a plain argparse **store**, not `action="append"`. So a repeated
`--source` was **silently discarded down to the last path** - no warning, no
usage error, and a confident verdict printed as though every paper had been
read. Episode 001 has **five** extracted sources and 002 has **four**, so the
documented command scored the deliverables against one paper and reported every
span quoted from the other four as `SOURCE 0`.

That is the checker-bug class the module's own docstring calls the most
dangerous false positive this gate has, because a correctly quoted sentence
reporting source 0 is indistinguishable from a fabricated quotation. On 001 it
produced **four** of them, each a real quotation present in another of the
episode's own sources - including `a good algorithm for other people to have`,
the exact span run 047 corrected after finding it misquoted.

**Control that makes this a finding rather than a guess:** `preflight()`'s
publish-path caller already iterates every declared key and intersects the
residuals, so the **detector was fine** and the CLI's argument shape was the
whole difference. Real `preflight 001` returns `ok: true` with 5 sources loaded
and 0 unverified spans while the CLI on the same episode returned 7 residuals.

**Fix.** `--source` now appends, and each source is scored **independently**
with the residual sets intersected - the same semantics `preflight()` uses, so
the operator command and the publication gate now agree by construction rather
than by coincidence. `ROBUST_PIPELINE.md` documents the repeat, the whitelist
caveat (the CLI cannot read the manifest) and why concatenation is wrong.

**A first cut of the fix was itself a weakening, and the harness caught it.**
Concatenating the sources into one haystack - the sibling tree's shape - makes a
span straddling the **boundary** between two joined papers verify while existing
in no single paper. Demonstrated on 001's real extracts: `"Child Study 6d MIT
Open Access"` spans the tail of `source-4UDPRQZR` and the head of
`source-BGWWIUWC`, matches the concatenation, and matches none of the five
sources alone. Replaced with per-source intersection in run 052b; the assertion
that caught it is kept as C5a-e.

**Three harness bugs, none a code defect** (run 029's rule, applied four times):
a 260-char anchor window spilled into the neighbouring `--check` line and
false-failed on *its* legitimate `action="append"`; the docstring's single
literal backslash became two in a non-raw Python anchor, so the anchor count
came back 0 **before any write**; a raw `span in text` residual test could not
see PDF line-wrapping and reported correctly-quoted spans as absent (the very
artefact the module's four normalization views exist for); and the proof omitted
the manifest's `quoted_span_whitelist`, leaving two benign own-speech spans
residual. Each time the guard was right and the harness was wrong.

**Lessons.**

- **An argparse `store` where the caller expects `append` is a silent
  data-loss gate.** `--check` was already `action="append"` in the same
  function; the asymmetry was the tell. When two arguments are both naturally
  repeatable, check that both accumulate.
- **Porting a sibling fix can import a weaker invariant than the local code
  already had.** This tree's `preflight()` was *stricter* than the sibling's CLI
  shape. Before copying the sibling's implementation, diff it against the local
  caller that already solves the same problem and keep the stronger semantics -
  run 010's "this tree's derivation is the better design" applied to a helper.
- **Verify a defect's blast radius against the command the operator is told to
  run.** The publish path was never broken; only the documented CLI was. Run
  045's question ("is that consumer on the publish path?") has an inverse: a
  non-publish-path consumer can still be the one every slice actually types.

**Validation (deterministic, final window):**
- repro `/opt/data/tmp/mm_multisource_repro_run052.py` **25/25** against the
  unmodified module, incl. the `preflight` control proving the detector works
- proof `/opt/data/tmp/mm_multisource_proof_run052.py` **37/37**: pre-fix backup
  still reproduces (false positives remain even with the whitelist passed, and
  each residual is genuinely present in another source); post-fix 001 and 002
  exit 0; single-`--source` residual **set** and exit code unchanged (stdout
  differs on sort order only); 003 byte-identical; nothing granted - invented
  sentences, a word dropped inside quotes, a swapped word, a transposed digit
  and an added clause are each still rejected, the whitelist still waives only
  its own span, and the cross-source boundary span is refused; only `main()`
  changed with **8** functions byte-identical and `robust_pipeline.py` untouched
- suite **38 -> 45** (7 `CliMultiSourceTests`), proven **load-bearing against
  both pre-fix states**: the original store shape fails 2, the concatenation cut
  fails 2 (incl. the boundary test); module restored md5-identical, 45 OK
- `preflight 001/002/003` all ok with `issues: []`; `coverage` ok 3/3; `verify`
  ok, `issues: []`, `legacy_exempt_episodes: []`; `reconcile` 0 issues
- `py_compile` clean on all `pipeline/*.py`
- `feed-site/feed.xml` md5 `9fc23235fcb49ca809059092da619b54`, **unchanged**
  across the whole slice; `grep -c '<item>'` = 3
- both appends additive: 0 removals in a unified diff (tests, ROBUST_PIPELINE.md)

Backups `pipeline/quoted_span_gate.py.bak-run052` (original pre-fix),
`.bak-run052b` (the concatenation cut),
`tests/test_quoted_span_gate.py.bak-run052`,
`pipeline/ROBUST_PIPELINE.md.bak-run052`, `production-log.md.bak-run052`.

**Outcome:** no episode or reading created, rendered or published. One durable
false-positive class closed in the one check that compares a deliverable against
the paper's actual words, and a weaker ported invariant rejected before it
landed. Feed byte-identical, live site unchanged. Standing blocker unchanged:
18 items unfiled in `YF84AUZK` awaiting David's lane decision (Summerize =
interview, Read = verbatim reading).

## 2026-11-13 — run 051: the read lane's extraction artifacts were one `git add -A` from a public repo

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same **18** on-topic sources still sit directly in `YF84AUZK` with
`collections: ['YF84AUZK']` and no subcollection, so neither lane reads them.
Produced `6P2KVFKQ` holds 10 parents (001-003's sources). No production unit
(27th consecutive), so the slice closed a durable defect. Opening `coverage` ok
3/3, `verify` ok with no issues and `legacy_exempt_episodes: []`, manifest and
state agree at `published_and_moved` for 001-003. Stale lock owner pid 1640237
dead with the advisory lock free (`flock` LOCK_NB succeeded) — the normal steady
state, cleared with `unlock --force`. Standing blocker unchanged and **not
re-raised** (the lane call is David's).

**Defect.** Run 047 found the interview lane's extracted source text untracked
but **not ignored** in a repository that is public, and added `source-*.txt` to
`.gitignore`. The read lane writes **three** artifacts of the same copyright
class under names that pattern does not match, and none of them was ignored:

    episodes/NNN/source.txt              verbatim extracted body text
    episodes/NNN/source-<KEY>.pdf        the publisher's own PDF
    episodes/NNN/extraction-report.json  per-page extraction audit trail

All three are written unconditionally by `read_lane.build()` (lines ~1031-1034
and the `target = directory / f"source-{item_key}.pdf"` fetch above them). The
reachability is not hypothetical: `push_to_remote()` runs **`git add -A`** on the
clone it builds, so the first real Read item would have committed a verbatim
copyrighted paper — and the publisher's PDF itself — to a public GitHub
repository, through a push that reports `ok: true`.

`source.txt` is the worse of the three. The interview pattern keys on the
`source-<KEY>` *prefix*, and the read lane deliberately uses a **fixed** filename
because `verify()` reads `(directory / "source.txt")` — so the one artifact the
fidelity gate depends on is precisely the one the ignore rule could never match.

**Proved on real state before fixing.** A scratch `episodes/992/` carrying all
three files: `git check-ignore` returned NOT IGNORED for each, and
`git add -A --dry-run` listed all three as `add`. The **control** that makes this
a finding rather than a guess: `source-ZZZZ1111.txt` in the same directory *was*
ignored pre-fix, so the pattern worked for the lane it was written for and the
gap was lane-shaped, not a broken `.gitignore`.

**Fix.** Three patterns appended to `.gitignore` with a comment naming the
writer, the `git add -A` path and how to regenerate them. Additive only: 0
removals in a unified diff, every original non-blank line present verbatim,
exactly 10 lines added.

**Validation (deterministic, final window):**
- proof `/opt/data/tmp/mm_gitignore_proof_run051.py` **32/32**: pre-fix backup
  still reproduces all three exposures plus the interview control; post-fix all
  three ignored and `git add -A` leaks none
- **nothing granted** — `script.md`, `episode-notes.md`, `review-panel.md`, the
  mp3s, `feed-site/feed.xml` and `pipeline/*.py` all still trackable; the bare
  `source.txt` pattern does **not** swallow `sources.md` or `source-notes.md`
- tracked-file set **unchanged at 52**, no `source.txt` and no `*.pdf` tracked
- `coverage` ok 3/3; `verify` ok, `issues: []`, `legacy_exempt_episodes: []`
- `preflight NNN --audio` ok with `issues: []` for **all three** episodes
- `reconcile --write` x3 at **0, 0, 0** issues (run-008 dedupe holding)
- `tests/` **38/38 OK**; `py_compile` clean on all `pipeline/*.py`
- `feed.xml` md5 `9fc23235fcb49ca809059092da619b54`, **unchanged** and
  byte-identical to the live feed; `grep -c '<item>'` = 3
- scratch `episodes/992/` removed; `state.json`, `manifest.json` and
  `read-episodes.json` carry no 992 entry

Backup `.gitignore.bak-run051`, `production-log.md.bak-run051`.

**Lesson.** Run 047's exposure and this one are the *same defect in the same
file*, and the census that would have caught it is not a code census at all —
it is "which artifacts does each lane write, and is every one of them either a
deliverable or ignored?" A `.gitignore` pattern is a gate like any other, and
run 032's lane-asymmetry axis applies to **data** rules as much as to code
paths: run 047 fixed the lane it was standing in and the sibling lane in the
same tree kept the hole. The sharper form: when a protective pattern keys on a
**filename shape**, enumerate every writer of that class rather than trusting
the shape — the read lane's fixed `source.txt` was unmatchable by construction.

**Outcome:** no episode or reading created, rendered or published. One copyright
exposure closed before the first Read item could trigger it. Feed byte-identical
to live, live site unchanged. Standing blocker unchanged: 18 items unfiled in
`YF84AUZK` awaiting David's lane decision (Summerize = interview, Read =
verbatim reading).

## 2026-11-13 — run 050: the read lane had run 049's waiver, one lane over

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same **18** on-topic sources still sit directly in `YF84AUZK` with
`collections: ['YF84AUZK']` and no subcollection, so neither lane reads them.
Produced `6P2KVFKQ` holds 10 parents (001-003's sources). No production unit, so
the slice closed a durable defect. Opening `coverage` ok 3/3, `verify` ok with no
issues and `legacy_exempt_episodes: []`, manifest and state agree at
`published_and_moved` for 001-003. Stale lock owner pid 1516053 dead with the
advisory lock free (`flock` LOCK_NB succeeded) — the normal steady state, cleared
with `unlock --force`. Standing blocker unchanged and **not re-raised** (the lane
call is David's).

**Defect.** Run 049 refused an interview episode declaring no source keys, and
placed the guard inside `preflight()`'s **interview-only** quoted-span block. But
the citation apparatus it protects is lane **shared**: duplicate ownership, the
manifest-key-in-notes check and the numbered-entry / year / metadata-length /
Zotero-link loop all iterate `expected_keys`, which is drawn from `read_source`
for a reading and `sources` for an interview. All of them are all-of loops, so at
cardinality zero they return no findings — and a **reading** with no citation
apparatus at all therefore passed `preflight` with `ok: true` and an **empty
issue list**, the only episode-level check `publish_local()` runs.

Proved on real code: the identical reading, notes carrying no numbered entry, no
year, no author/title/venue metadata and no Zotero link, is **refused** with
`read_source: ['ZZZZ1111']` and **passes clean** with `read_source: []`. The
fidelity gate passed in both cases, so the declaration was the only difference.

The read lane's reachability is the **stronger** of the two, which is why this
half mattered more than the half run 049 fixed. An interview's `sources` is
hand-written, so an empty list means somebody wrote one. A reading's
`read_source` is *derived* by `read_lane.sync_durable_state()` as
`[item_key] if item_key else []`, with `item_key` itself read as
`entry.get("item_key", "")` — so a registry entry that never recorded an item key
silently becomes `read_source: []`. Demonstrated by calling the real
`sync_durable_state()` with an entry carrying no `item_key`: it wrote
`read_source: []` into `manifest.json`, and that derived state reached the waiver.

**Fix.** The zero-declared-keys refusal moved **up** to the lane-shared apparatus
in `preflight()`, branching on lane so each message names the field and registry
that actually fixes it — a reading is pointed at `item_key` in
`read-episodes.json` and told to re-run `read_lane.py verify` so `read_source` is
mirrored, an interview at `sources` in `manifest.json`. Run 049's interview-only
copy was **retired rather than layered**: a centralized predicate with an
open-coded duplicate still inline is run 044's lesson, so exactly one copy of
each message exists. Both lanes are built *from* a paper, so zero declared
sources is a defect in every case and this only adds refusals.

**Two lessons.**

- **A guard added one run earlier, in the same function, is still a port
  candidate.** Run 032 established lane asymmetry as an axis the line-count
  census does not cover ("does the other lane here lack a guard this lane
  holds?"). The instinct is to apply that across trees or across files; here the
  gap was between two branches of a single function, opened by the *previous
  slice*. When you harden one lane's path, ask immediately whether the machinery
  you hardened is shared — and if it is, whether you guarded the machinery or
  just the one caller.
- **Where a field is DERIVED, cardinality zero is reachable without anyone
  intending it.** Run 049 reasoned about an empty `sources` as a registration
  gap. The read lane's empty `read_source` needs no gap at all: two chained
  `.get(x, "")`/`if else []` defaults manufacture it from a merely incomplete
  registry entry. A field with a silent empty default deserves the same scrutiny
  as a gate with a waiver, because it *is* one.

**Validation (deterministic, final window):**
- repro `/opt/data/tmp/mm_read_sources_waiver_repro_run050.py` **26/26** against
  the **unmodified** module: the waiver, each of the five waived checks
  individually, the declared-key control that catches them, the derived-state
  reachability demonstration through the real `sync_durable_state()`, and the
  interview-lane control proving run 049's guard localizes the gap
- proof `/opt/data/tmp/mm_read_sources_waiver_proof_run050.py` **40/40**: pre-fix
  backup still reproduces; both lanes now refused with their own wording and no
  cross-wording; **nothing granted** — 001/002/003 still `preflight ok` with
  `issues: []` under `require_audio`/`enforce_review`, a declared-key reading is
  still fully scored, a **complete** reading still passes (so the guard is not a
  blanket refusal), and ten read-lane refusal classes each still bite one at a
  time: missing year, missing Zotero link, missing notes, missing verbatim
  disclosure, Rowan in a reading, missing Zotero-links disclosure, empty mp3,
  missing `source.txt`, `verified: false`, and wrong-case `kind: "READ"`;
  **exactly one function changed** (`preflight`) with **45 byte-identical**
  including `review_gate`, `fidelity_gate`, `verify_feed`, `feed_coverage`,
  `publish_local`, `lane_ownership` and `reconcile`
- real state: 38-test suite OK, `coverage` ok 3/3, `verify` ok with no issues,
  three `reconcile --write` passes at 0/0/0, `preflight 001-003` ok with empty
  issue lists, `feed-site/feed.xml` md5 **unchanged** (`9fc23235…`), and the live
  registries md5-asserted unchanged throughout both harnesses
- `ROBUST_PIPELINE.md` gained a run-050 subsection so the read-lane section no
  longer understates the gate (run 031's rule: a doc that outlives a fix routes
  the next slice around it); doc edit additive, 0 removals

Backups: `pipeline/robust_pipeline.py.bak-run050`,
`pipeline/ROBUST_PIPELINE.md.bak-run050`.

## 2026-11-13 — run 049: declaring no sources waived the quoted-span gate AND every citation check

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same **18** on-topic sources still sit directly in `YF84AUZK` with
`collections: ['YF84AUZK']` and no subcollection, so neither lane reads them.
Produced `6P2KVFKQ` holds 10 parents (the sources of 001-003). No production
unit, so the slice closed a durable defect. Opening `coverage` ok 3/3, `verify`
ok with no issues and `legacy_exempt_episodes: []`, manifest and state agree at
`published_and_moved` for 001-003. Stale lock owner pid 1401672 dead with the
advisory lock free (`flock` LOCK_NB succeeded) — the normal steady state,
cleared with `unlock --force`. Standing blocker unchanged and **not re-raised**
(the lane call is David's).

**Defect.** Run 048 put `quoted_span_gate` on the publish path, keyed on the
manifest's `sources` list. But nothing required that list to be **non-empty**,
and with `keys == []` the gate loads no source text, so the `residual`
intersection stays `None` and `sorted(residual or set())` is `[]` — **every
quoted span is vacuously verified**. The same empty list also skips the
ownership check, the manifest-key-in-notes check and the entire numbered
citation / year / length / Zotero-link loop. So an interview episode that
declared no sources could quote a sentence present in no paper on earth and
`preflight` returned **`ok: true` with an empty issue list** — the only
episode-level check `publish_local()` runs.

Proved on real code: the identical deliverable, quoting
`"every single participant demanded a kill switch"` against a source text that
contains nothing of the kind, is **refused** with `sources: ['AAAAAAAA']` and
**passes clean** with `sources: []`. That contrast is the whole finding — the
detector works and the declaration was the only difference.

It is reachable by an ordinary registration gap, not a contrived one: a slice
that renders and publishes without writing the manifest entry is exactly the
class that hid **042** for a run and **026** for two months in the sibling
tree, and the pre-produced path never registers an entry at all. An episode
with no manifest entry whatsoever took the same free pass.

**Fix.** `preflight()` now appends an issue when an interview episode declares
no source keys, naming `pipeline/manifest.json` as the place to fix it. An
interview is built *from* papers, so zero declared sources is a defect in every
case — there is no legitimate interview episode this refuses. The read lane is
untouched: the whole block is interview-only and a reading's key lives under
`read_source`. Also added `checked_against_sources` to each file's
`quoted_spans` report, because `unverified: []` previously could not be
distinguished from *never compared* — and that ambiguity is precisely how the
defect read as healthy.

**Two lessons.**

- **This is run 036's "a waiver is a gate with the sign flipped" one level up
  from where that lesson was applied.** A *missing* `source-KEY.txt` was
  already an issue rather than a waiver — run 048 wrote that policy and a
  comment explaining it. Declaring **no keys at all** skipped the check
  entirely, which is the stronger waiver sitting directly above the weaker one
  that had been reasoned about carefully. When you harden the "evidence is
  missing" branch, ask what happens when the evidence is never *requested*.
- **An empty collection is not a passing collection.** Runs 005/013/031/041
  each fixed a selector that wrongly dropped a record, and run 041 generalized
  it to "a check that validates what is present cannot validate what is
  absent". Here the iterated collection was the *source list itself*: zero
  iterations, zero findings, `ok: true`. When a gate's verdict is an
  intersection or an all-of loop, test it at **cardinality zero** — that is
  where it silently inverts.

**Validation (deterministic, final window):**
- repro `/opt/data/tmp/mm_sources_waiver_repro_run049.py` **20/20** against the
  **unmodified** module: the waiver, the no-manifest-entry variant, the waived
  citation apparatus (notes with no numbered entry, no year, no Zotero link all
  pass), plus the sourced-episode control that catches the invention
- proof `/opt/data/tmp/mm_sources_waiver_proof_run049.py` **50/50**: pre-fix
  backup still reproduces; post-fix refuses both variants; **nothing granted** —
  001/002/003 still `preflight ok` with `issues: []` under
  `require_audio`/`enforce_review`, a sourced episode is still scored and still
  catches an invented quotation, a clean one still passes, a declared-but-absent
  extract is still refused under its own message, duplicate ownership still
  fires, and missing notes / both disclosures / review panel / audio each still
  bite; **exactly one function changed** (`preflight`) with **48
  byte-identical**, including `review_gate`, `fidelity_gate`, `verify_feed`,
  `feed_coverage`, `publish_local` and `reconcile`
- `tests/test_sources_declared_gate.py` added: suite **31 -> 38**, all OK
- tests proven **load-bearing**: reverting the module to `.bak-run049` fails
  **4**; restored module md5-identical (`1a0e8c8a6d01e59a8c73869f6b988499`) with
  38/38 green
- `coverage` ok 3/3; `verify` ok, `issues: []`, `legacy_exempt_episodes: []`;
  three `reconcile --write` passes at 0/0/0 issues with stored-errors total
  **0, 0, 0** (the run-008 dedupe holding)
- `feed.xml` md5 `9fc23235fcb49ca809059092da619b54`, **unchanged** across the
  whole slice; `grep -c '<item>'` = 3
- `py_compile` clean on all `pipeline/*.py`; the fix landed additively (0
  original non-blank lines lost, replacement text asserted present)

**Harness bug, not a code defect** (run 029's rule, which held again): the proof
false-failed 2/48 on its own fixture — the scratch tree accumulated several
episodes all declaring the key `AAAAAAAA`, so `source AAAAAAAA is assigned to
multiple episodes` fired **correctly** on the clean-episode case. Fixed by
giving each scratch episode its own key, and the duplicate-ownership refusal
that caused the confusion is now pinned as an explicit assertion rather than
being worked around.

**Note on `healthy: false`.** `status` still reports it, unchanged from the
slice start: `501` is a bare ledger stub with **no `episodes/501/` directory**
and no manifest entry, so its issues (no script, no notes, no disclosures, no
panel) are **accurate**. The new undeclared-sources issue also appears there and
is equally accurate — the same situation as the sibling tree's planned stubs
017/018/020, whose genuine issues are deliberately left standing.

**Outcome:** no episode or reading created, rendered or published. One
publication-gate waiver closed, with the gate proven still to refuse everything
it refused before. Feed byte-identical, live site unchanged. Standing blocker
unchanged: 18 items unfiled in `YF84AUZK` awaiting David's lane decision
(Summerize = interview, Read = verbatim reading).

## 2026-11-13 — run 048: the quoted-span gate was not on the publish path

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same 18 on-topic sources still sit directly in `YF84AUZK` with no
subcollection, so neither lane reads them. Produced `6P2KVFKQ` holds 10 parents.
No production unit, so the slice closed a durable gap. Opening `coverage` ok
3/3, `verify` ok with no issues, manifest and state agree at
`published_and_moved` for 001-003. Stale lock owner pid 1286041 dead with the
advisory lock free — the normal steady state, cleared with `unlock --force`.
Standing blocker unchanged and **not re-raised** (David's lane call).

**Defect.** Run 047 ported `pipeline/quoted_span_gate.py` and left it with
**zero callers** — `grep -rn quoted_span pipeline/*.py` matched only the module
itself. So the one check in this tree that compares a deliverable against the
**paper's actual words** was reachable solely as a hand-typed CLI command, and
`publish --episode NNN` could not reach it. Every other `preflight()` check
scores the script against the **citation record** (keys, numbered entries,
years, Zotero links), which is exactly why a misquote inside quotation marks
passed a three-reviewer panel and every deterministic gate in **two published
episodes**. Run 047 found the first (001's dropped word) and called the tool
"not a publication gate"; that was the finding, not the fix.

This is runs 042/045's class with the axis rotated again: 042 wired a reader to
a field the gate ignored, 045 asked whether a field's reader is reachable from
the command the operator runs to ship. Here the thing off the publish path was
a whole **module**.

**003's source text was obtainable all along.** Run 047 recorded 003 as
permanently unverifiable because `items/EIUADNKU/children` has no stored PDF.
But this log's own ep-003 entry says the episode was read from the authors'
arXiv preprint `1803.07170v2` — fetched here in one call (6.0 MB, 40 pages,
48,998 chars via the sibling venv's `pypdf`). Lesson: when an intake probe
fails, re-read the record for the route that *was* used; "no Zotero PDF" is not
"no source text".

**What the gate found on 003's first run: a second real misquote in a published
episode.** Nine source-0 spans; eight are the documented benign classes
(bibliographic titles in the notes' reference list — including the focal
paper's *published* title, absent from the preprint because the preprint
carries a different title the episode discloses on air — plus the show's own
scoping vocabulary and two readings the script explicitly **rejects**). The
ninth is the blocking author-attributed class:

    source (EIUADNKU preprint): the table legend defines the term "Mistake"
                                 (`made a mistake` appears 0 times)
    episodes/003/episode-notes.md: the "made a mistake" coefficient

Quotation marks around a regression-term name the authors never print.
Corrected to the paper's own `"Mistake"`. Notes-only **by evidence** — a
per-file count table showed script 0 / notes 1 before the edit, so `script.md`
was not touched on assumption (run 047's lesson, which runs in both
directions). The edit changed exactly one line by exactly the intended
substitution, asserted before writing.

**Fix.** `preflight()` now runs the gate for interview episodes, contributing
issues like every other check, under `checks.quoted_spans`. Three design points:

- **Union-of-sources.** An episode may group several papers (001 has five). The
  CLI takes a single `--source`, so a per-source run reports every span quoted
  from paper A as missing from paper B — a false positive shaped exactly like a
  fabrication. A span verifies if it appears in **any** of the episode's
  sources.
- **Whitelists live in `manifest.json`** (`quoted_span_whitelist`), per episode,
  not on a command line: the waiver is durable, reviewable, attached to the
  record, and inherited by a fresh clone. Per run 036 (a waiver is a gate with
  the sign flipped) all twelve entries across 001-003 are individually justified
  in `/opt/data/tmp/mm_span_whitelist_run048.py`. Neither real defect was
  whitelisted; both were fixed.
- **A missing `source-KEY.txt` is an issue, not a waiver.** The extracts are
  gitignored and regenerable, so a tree that lost them must be told rather than
  silently waived — which is how 003 went unverified for a run.

Readings stay exempt: the read lane's fidelity gate compares the entire script
to `source.txt` word by word, strictly subsuming a quoted-span check.

**Proof (`/opt/data/tmp/mm_span_gate_proof_run048.py`, 52/52).**
A: the unmodified `.bak-run048` module **accepts** an invented, author-attributed
quotation with an empty issue list, while the CLI tool catches the same span —
the control proving the detector worked and only the call site was missing.
B: post-fix it is refused by `preflight` **and** by the real
`publish --episode 003`, with the scratch feed never moving.
C: nothing granted — 001/002/003 still pass with empty residuals, a word dropped
inside quotes is refused, a whitelisted episode still refuses a *new* invented
span, a missing source extract refuses, readings are exempt, and the missing
panel / missing mp3 classes still bite.
D: exactly **one** function changed (`preflight`), 47 byte-identical including
`review_gate`, `verify_feed`, `feed_coverage`, `publish_local`, `fidelity_gate`,
`reconcile` and `render_episode`.

Tests: **23 -> 31**, the eight new ones pinning the *call site* (run 047's 23
all test the module, so the suite could not have caught this). Proven
load-bearing: against the pre-fix module the suite **fails**, and the restored
module is md5-identical with 31/31 green.

Harness note: the proof's first run reported `render_episode` as changed. The
code was right and the harness was wrong — its function-extraction regex was
`^def `, which never matches `async def`. A unified diff showing **0 removals**
settled it. Run 029's rule again: confirm which side is wrong before touching
either.

**Validation (deterministic, final window):** `coverage` ok 3/3; `verify` ok,
`issues: []`, `legacy_exempt_episodes: []`; three `reconcile --write` passes at
0/0/0; `preflight NNN --audio` ok with `issues: []` for all three episodes;
`feed.xml` md5 `9fc23235fcb49ca809059092da619b54` **unchanged** across the whole
slice with `grep -c '<item>'` = 3; `py_compile` clean on all `pipeline/*.py`;
both appends additive (0 removals).

Backups: `robust_pipeline.py.bak-run048`, `manifest.json.bak-run048`,
`episodes/003/episode-notes.md.bak-run048`,
`tests/test_quoted_span_gate.py.bak-run048`, `ROBUST_PIPELINE.md.bak-run048`,
`production-log.md.bak-run048`.

**Lesson.** A ported tool is not a gate until something on the publish path
calls it. When a slice ends with "use this command every run", that is operator
discipline, not enforcement — ask which command the operator actually runs to
ship, and put the check there. And the corollary this run paid for twice: the
gate that scores deliverables against the **source text** is the only one that
can see a misquote, and it has now found one in each of the two published
episodes whose sources it could read.

**Outcome:** no episode or reading created, rendered or published. One durable
verification gap closed, a second real misquote corrected in a published
episode, 003's source text recovered and installed, eight tests added. Feed
byte-identical, live site unchanged. Standing blocker unchanged: 18 items
unfiled in `YF84AUZK` awaiting David's lane decision.

## 2026-11-03 — voices locked

David chose the male voice from audition A plus the Human in the Loop main
voice. Final pairing:

- Host: `en-US-AvaMultilingualNeural`, rate `-3%` (shared with HITL)
- Dr. Rowan Field: `en-US-AndrewMultilingualNeural`, rate `-2%`

Rowan is male on this show, unlike HITL's `en-GB-SoniaNeural`. Confirmation
render through `pipeline/render_from_script.py`: 6 turns, 93s, verified good.

## 2026-11-03 — Rowan sped up, disclosure cut

- Rowan rate `-2%` → `+18%`. Verified 1.208x faster on identical text
  (speech-only, silence excluded, same render batch). edge-tts rate is not
  perfectly linear and varies ~2% between renders; +21% and +24% both measured
  slower than +18%, so +18% is the right value for 1.2x.
- Spoken AI/fictional disclosure cut from four requirements stated twice
  (18.9s) to one sentence stated once (6.5s). Full disclosure retained
  unabridged in the notes HTML and feed description.
- Sample episode runtime: 93.9s → 72.7s.

## 2026-11-03 — Episode 001 shipped

"Should the Crowd Program the Car?" — 12m07s, 43 turns, live and verified at
https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/feed.xml

Sources (all five moved to Produced 6P2KVFKQ): Bonnefon 2016 Science, Awad 2018
Nature, Awad 2020 PNAS, Feffer 2023 AAAI, Takemoto 2024 RSOS. All numbers
verified against extracted full texts, not abstracts.

Two retargeting bugs found in the cloned pipeline, both of which let a command
report success while doing nothing:

- `publish_feed.py` built interview items from a hardcoded `EP` list that was
  emptied when the tree was cloned. `publish` printed ok and wrote a zero-item
  feed. Now derived from manifest + state ledger, gated on a passing render.
- `move_verified_sources.py` read the HITL manifest and keyed off a status
  string this pipeline never sets. Now reads the local manifest and the state
  ledger's `published` status.

Also: `feed-site/` is the build output, but Pages serves the repo root. Use
`robust_pipeline.py push`, which syncs the two; a manual `git push` leaves a
stale root feed and 404s on new assets.

Security: `check_zotero.py` had a live Zotero API key hardcoded and was tracked
in a public repo. Untracked, gitignored, and switched to `ZOTERO_API_KEY` from
the environment. The key is still in pre-fa8bf1f history and should be rotated
in the Zotero group settings.

## Run 002 — 2026-11-04 20:38 UTC — episode 002 "Building the Decider" (stopped at script_drafted)

Selected unit: interview episode **002**. Read lane (DV6F4ILX) empty, so no cheaper unit was available.
Summerize (V4WXTY8M) held 5 unproduced items; 4 were taken for this episode as one thematic arc.

Sources (all grounded in extracted full text, not abstracts):
- W5Q7PFMK Kim et al. 2018, AAAI/ACM AIES pp. 197-203 — hierarchical Bayesian model of individual moral principles over abstract dimensions.
- W9D57F3R Noothigattu et al. 2018, AAAI 32(1) — 4-step voting pipeline, swap dominance, 18,254,285 comparisons / 1,303,778 voters.
- VDWW52G6 Awad et al. 2020, CACM 63(3) pp. 48-55 — retrospective, 7 tabulated criticisms + responses, Germany expert-vs-public clash, Society in the Loop.
- 2WH5N968 bin Ahmad & Takemoto 2025, PLOS One 20(5) e0322776 — 52 LLMs, AMCE conjoint, rho = -0.54 size/distance, updates do not reliably improve alignment.

**EIUADNKU (Awad et al. 2019, blame attribution) excluded**: Zotero items/EIUADNKU/children returns no PDF
attachment, so there is no retrievable full text. Not scripted from its abstract, per the citation contract.
It stays in Summerize and is a natural fit for a later blame/accountability episode (teased on air in 002's close).

Arc: ep 001 asked whether the crowd should program the car; 002 takes the affirmative seriously and follows the
engineering — model the individual (Kim) -> aggregate into a runnable decider (Noothigattu) -> what the platform's
own authors concede (CACM) -> the decider nobody designed (52 LLMs). Leans on ep 001's on-air Awad 2018/2020
distinction and adds a third separation for the CACM piece so the three Awad papers cannot be conflated.
Feffer 2023 is referenced only as covered in 001, not re-cited as new evidence.

Artifacts written: episodes/002/script.md (3,587 words, 67 turns), episodes/002/episode-notes.md
(4 numbered citations with Zotero links, DOIs, per-source Supports/Boundary, plus an explicit evidence-boundaries
section). Registered in pipeline/manifest.json (status script_drafted, sources listed, duplicate-source guard
asserted clean against all other episodes) and pipeline/state.json (status planned + transition). Backups at
*.bak-run002.

preflight 002 is clean on every content check — 67 dialogue turns, 4/4 notes Zotero keys matching manifest
sources, 4 numbered citation entries with years and direct Zotero links, no duplicate links, short-form spoken
disclosure present (fictional correspondent + AI-generated in one sentence near the top, not repeated at close),
REQUIRED_DISCLOSURE citations line present in the closing turn. **Sole remaining issue: review gate: review panel
is missing.**

Stopped here deliberately: the 1500s budget had ~4 minutes left, and the 3-reviewer panel must be run as three
parallel independent subagents each given the extracted full source text (script-only reads miss misattribution).
That does not fit the remaining slice and must not be faked or self-declared.

**Next command** (next slice, start here):
1. Run 3 parallel reviewer subagents against episodes/002/script.md + the extracted texts in
   /opt/data/tmp/mm002/W5Q7PFMK.txt, W9D57F3R.txt, VDWW52G6.txt, 2WH5N968.txt.
2. Write episodes/002/review-panel.md with exact gate labels: "## Reviewer <N> — <distinct name>",
   a "verdict:" line containing "pass", a line labelled exactly "Required revisions:", one "Revision record"
   section, and no occurrence of unresolved/not addressed/blocked.
3. python3 pipeline/robust_pipeline.py preflight 002 -> expect ok: true.
4. render as a tracked background process (exceeds the 600s foreground cap), then verify,
   publish --episode 002, assert grep -c '<item>' feed-site/feed.xml increased from 1 to 2,
   then push --episode 002 --wait 240.
5. After live verification, move W5Q7PFMK/W9D57F3R/VDWW52G6/2WH5N968 to Produced (6P2KVFKQ) with
   pipeline/move_verified_sources.py (needs ZOTERO_API_KEY exported).

## Run — 2026-11-04 — Episode 002 "Building the Decider" SHIPPED

Resumed the interrupted 002 slice. Prior context had script + notes drafted,
reviewer 3 passed, reviewers 1 and 2 outstanding (an earlier parallel dispatch
of both died on output-token limits without emitting verdicts).

Lock: `.pipeline.lock` present with dead owner pid and a free advisory lock —
the documented stale-lock steady state, cleared with `unlock --force`.

Reviewers, re-run as independent parallel subagents against the extracted full
texts under a verdict-first, under-500-word output contract:
- R1 quantitative accuracy / attribution: PASS, no revisions. Verified the Kim,
  Noothigattu, Awad-CACM and bin Ahmad numbers, author lists, venues and page
  ranges, and confirmed the three-Awad-paper boundary holds (40M/233 countries
  credited to Nature 2018, 70k/42 countries to PNAS 2020, neither to the CACM
  retrospective). Kim's 197-203 page range is absent from the extracted text and
  was confirmed from the ACM DOI record plus three publisher listings.
- R2 evidence boundaries / overclaim: FAIL with six revisions, all applied.
  (1) the 98.2%/95.1% agreement was framed as faithfully reproducing the
  aggregate's choice — it is a Borda count on a sampled estimate, and the paper
  says the true 1,303,778-voter winner is uncomputable; (2) added the authors'
  third stated limitation, the contentious-yet-too-coarse feature set; (3) the
  Feffer/Heidari/Lipton connection was asserted as an identity, now attributed
  as the show's inference; (4) "strongest preference" softened to CACM's
  "largely approves"; (5) rho = -0.54 restated as a moderate rank correlation,
  not proportionality; (6) two "only legible post-hoc" claims attributed to the
  host rather than the papers.
- R3 format / disclosure / listenability: PASS (banked earlier, after seven
  spoken-number fixes).

Both edits ran through the assertion-guarded atomic write pattern: anchors
asserted unique, an explicit expected-reword whitelist, line count and 67-turn
count preserved, disclosure still exactly once near the top and absent from the
close, and a digit scan over spoken turns returning zero. Script 3,608 -> 3,760
words. Backups at `script.md.bak-tts` and `script.md.bak-r2`.

Gates: review gate ok, preflight ok (67 turns, 4 numbered sources, 4 Zotero
keys in notes). Render 20,217,260 B / 21m03s / 24 kHz mono, sha256 7da8ddbc,
locked voices Ava -3% + Andrew +18%.

Publish + push: feed items 1 -> 2, enclosure length equals the on-disk byte
count for both episodes, GUID `moral-machines-episode-002` (correctly prefixed,
no HITL collision), live feed md5 byte-identical to local, remote audio 206 and
notes 200 for both episodes, `verify --remote` ok with no issues.

Zotero: all four sources (W5Q7PFMK, W9D57F3R, VDWW52G6, 2WH5N968) moved to
Produced 6P2KVFKQ with Summerize V4WXTY8M stripped and no other membership
touched, each confirmed by a live `items/<key>` read.

Two defects fixed in passing:
- `move_verified_sources.py` wrote its results JSON into the **HITL** tree
  (`media/zotero-podcast/pipeline/move-results.json`) — another instance of the
  documented cloned-script retargeting class. Now writes `ROOT/move-results.json`.
  Backup at `move_verified_sources.py.bak-002`.
- `manifest.json` 002 lagged at `script_drafted` while the ledger said
  `published` — the manifest-vs-state mismatch class that hid HITL episode 026
  from the feed for two months. Advanced to `published_and_moved` under an
  atomic guarded write, with a duplicate-source-ownership scan; feed md5
  unchanged by the edit.

Note for future slices: `review_gate()` counts **every** `verdict:` regex match
and requires exactly three, all passing. An `Initial verdict:` plus
`Post-revision verdict:` pair per reviewer yields five matches and fails with
the misleading "each reviewer must record a pass verdict". Use one
`**Final verdict: PASS.**` line per reviewer, as episode 001 does, and put the
initial-fail history in the revisions prose. Also: `render` takes the episode
**positionally** (`render 002`, not `--episode 002`), while `publish` and `push`
take `--episode`. There is no `coverage` subcommand in this tree and no
`tests/` directory — both are HITL-only.

Queue after this run: Summerize holds one unworked item, EIUADNKU — Awad et al.
2019, "Drivers are blamed more than their automated cars when both make
mistakes", Nature Human Behaviour, DOI 10.1038/s41562-019-0762-8. Read is empty.

## 2026-11-05 — Episode 003 "Who Gets Blamed When Both Are Wrong" (published)

Focal source: Awad et al., "Drivers are blamed more than their automated cars when
both make mistakes," *Nature Human Behaviour* 4 (2020), 134–143. Zotero EIUADNKU,
moved to Produced.

- **Paywalled focal source, preprint substituted.** No PDF in Zotero; Unpaywall and
  OpenAlex found no OA copy of the published version. Read the authors' own
  preprint, arXiv:1803.07170v2 (40pp, same authors, same three studies, different
  title). The version difference is disclosed on air and in the notes, and listeners
  are told to cite the preprint for any figure. Precedent: a preprint substitution is
  acceptable when disclosed this explicitly; coefficients are hedged as approximate.
- **Single-focal-source episode.** One paper against the style guide's ~five-article
  target, as a deliberate one-paper deep read. Recorded here as precedent, not drift.
  Four background sources are cited on air (Dietvorst et al. 2015; Malle et al. 2015;
  Nader 1965; German Ethics Commission 2017) and listed in a Background sources
  section in the notes.
- **Reviewer panel caught three attribution defects, all pointing the same way.**
  Round one: fact-checker PASS with two precision fixes, evidence-boundary reviewer
  FAIL, craft reviewer FAIL. The blocking items were (1) a closing that asserted a
  causal mechanism the authors expressly call an open question, (2) a "liability
  insulation" claim built from 0–100 rating scales with no liability variable
  measured, and (3) a boundary list crediting the authors with three limits that are
  not theirs — including two they argue against. Every defect flattered the paper.
  17 script revisions + 9 notes revisions applied; raw findings retained in
  episodes/003/review-round1-findings.md.
- **Runtime estimates are unreliable from word count.** Notes first said fourteen
  minutes, projection said sixteen, rendered audio is 17:18. Notes now carry the
  measured duration. Reconcile against ffprobe after render, not before.
- Rendered 17:18 / 16.6MB. Feed published with 3 items, pushed, and independently
  verified live: guid moral-machines-episode-003, audio HTTP 206, notes HTTP 200.

## Run 004 — 2026-11-05 — no production unit; show rebranded off Human in the Loop

Both intake lanes empty: Summerize (V4WXTY8M) 0 items, Read (DV6F4ILX) 0 items.
All ten sources from episodes 001-003 confirmed live in Produced (6P2KVFKQ). Live
feed byte-identical to `feed-site/feed.xml` (md5 d4ddcfac50b1bbd7064d6927356192dd,
3 items), ep-003 audio HTTP 206 and notes HTTP 200. No production unit existed, so
per the HITL skill's "spend the slice on a durable defect" rule the slice went to
inherited branding and ledger drift rather than re-proving a known-good feed.

- **The feed was still published under the other show's name.** `publish_feed.py`
  hardcoded `Human in the Loop: Moral Machine Edition` in four slots — the channel
  `<title>`, the channel `<image><title>`, and the index page's `<title>` and `<h1>`.
  All four now read **Moral Machines**, matching the skill's locked show title and
  the `moral-machines-` GUID prefix. The two shows are supposed to be fully
  independent; a shared channel title is exactly the cross-show confusion the
  separation rule exists to prevent.
- **Cover art rebranded.** `cover.svg`/`cover.png` (both at tree root and in
  `feed-site/`) read "HUMAN IN THE LOOP" with the HITL headphone glyph — flagged in
  the skill as blocking real distribution. Replaced with a Moral Machines cover: dark
  purple gradient, teal balance-scale/decision glyph with gold pans, title
  "MORAL MACHINES" over subtitle "MACHINE ETHICS RESEARCH INTERVIEWS". There is no
  SVG rasterizer in this container (no rsvg-convert/inkscape/convert/magick, no
  cairosvg in either venv), so the PNG is drawn directly with PIL 13 + DejaVu from
  the matplotlib bundle at /opt/data/.venv-img/.../mpl-data/fonts/ttf. The SVG is
  kept as the editable source of record; the two are drawn to match but are not
  machine-derived from each other — **edit both when changing the cover.**
- **Manifest/state drift on 003.** `manifest.json` said `scripted` while
  `state.json` said `published`, the episode was live, and its source EIUADNKU was
  already in Produced. Set to `published_and_moved`, matching 002's end state. This
  is the mismatch class the HITL skill says to diff every slice: here the feed was
  fine and only the bookkeeping lagged, but the same signature is what exposed
  HITL's two-month publication gap, so it should not be left sitting.
- Safety: every edit asserted its anchor count first, backed up to `*.bak-run004`,
  wrote atomically (temp + fsync + os.replace), and was proved minimal afterward.
  The anchor-count guard **fired correctly** on the first attempt — the script
  asserted 3 title occurrences and found 4, which stopped the write; all four were
  then confirmed to be show-title slots before the count was corrected. Post-publish
  `diff` of feed.xml shows exactly **1 changed line** (the channel title), with all
  three enclosure lengths still equal to the on-disk byte sizes, all three
  descriptions non-empty, and all three GUIDs still `moral-machines-episode-00N`.
  `py_compile` clean on publish_feed.py.

## Run 005 — 2026-11-05 — no production unit; two silent-publication defects closed

Both intake lanes empty again: Summerize (V4WXTY8M) 0 items, Read (DV6F4ILX) 0
items, all ten sources from episodes 001-003 still in Produced (6P2KVFKQ). Live
feed byte-identical to `feed-site/feed.xml` (md5
9fc23235fcb49ca809059092da619b54, 3 items). Per the HITL skill's "spend the
slice on a durable defect" rule the slice went to two latent defects rather than
re-proving a known-good feed.

- **`publish_feed.py` would have silently erased a shipped episode from the
  feed.** `interview_episodes()` filtered the ledger status against the literal
  tuple `('rendered', 'published')`. But the documented end state for a fully
  shipped interview episode is **`published_and_moved`** (002's convention,
  recorded in the skill), and the pre-move state is
  `published_pending_zotero_move`. Neither matched, so the first `publish` run
  after a Zotero move would have dropped that episode's item while still
  reporting `ok: true`. Proven, not inferred: running the pre-fix module with
  002 at `published_and_moved` returns `['001','003']` — 002 gone — while
  `published` returns all three. This is exactly the HITL `EP`-list silent-skip
  class, and it was armed, because run 004 had just set 002 and 003 to
  `published_and_moved` in the **manifest**; only the fact that `state.json`
  still read `published` kept the feed intact. The filter now accepts
  `rendered` plus any status in the `published*` family; a genuinely
  non-published status is still excluded (verified: `failed` yields
  `['001','003']`).
- **Ported the deterministic `coverage` audit from HITL.** This tree had no
  `coverage` subcommand even though both skills say to run it as the first
  command of every slice. `feed_coverage()` plus its CLI wiring is now present:
  read-only, matches on the episode number inside the item GUID (stable across
  the interview scheme and the read lane's `-reading` suffix, so a hand-built
  `episode-NNN.mp3` false 404 cannot recur), and checks every enclosure exists
  on disk at exactly its advertised byte length. It grants nothing and is not a
  publication gate. Current reading: `ok: true`, 3 feed items, 3 published
  episodes, no missing items and no enclosure issues. Exit code is 1 on any
  issue, so the production cron can now open each slice with a deterministic
  coverage check instead of a hand-rolled audit script.
- Safety: each anchor asserted to occur exactly once before the write, backups
  to `*.bak-run005`, atomic writes (temp + fsync + os.replace), `py_compile`
  clean on both files. The "no original non-blank line may be lost" assertion
  **fired correctly** on the one deliberately reworded line (the exit-code
  command set gaining `"coverage"`); it was whitelisted explicitly via
  `RP_EXPECTED_REWORDS` plus an assertion that the new form is present, rather
  than relaxing the guard. After a full `publish` of 001-003, `feed.xml` is
  **byte-identical** to its pre-change copy and still carries 3 items — the fix
  changes behaviour only in the states that were previously dropped.
- **Standing blocker for David, unchanged and now the only one:** both intake
  lanes are empty, so there is no production unit. 18 on-topic sources sit
  directly in the parent collection `YF84AUZK` (bioethics / genome-editing
  governance / socioscientific-reasoning instruments — e.g. *Heritable Human
  Genome Editing*, *Human genome editing: recommendations*, *Exploring
  Bioethics*, the SDM-Q-9 and CollaboRATE measures), filed in no subcollection
  and therefore invisible to both lanes. Seven of them already carry a PDF
  child. Moving any of them into Summerize (V4WXTY8M) or Read (DV6F4ILX) gives
  the pipeline work immediately; the worker deliberately does not file them
  itself, since lane assignment decides interview-vs-verbatim treatment.

## Run 006 — 2026-11-05 — no production unit; Read lane's on-air show name retargeted

Opened with the deterministic `coverage` audit per both skills: `ok: true`,
3 feed items, 3 published episodes, no `missing_from_feed`, no
`enclosure_issues`, no `unrecorded_feed_items`. Live feed
(`https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/feed.xml`) returns
HTTP 200 and is **byte-identical** to `feed-site/feed.xml`
(md5 `9fc23235fcb49ca809059092da619b54`) — zero deploy drift.

Both intake lanes empty for the third consecutive run: Summerize (V4WXTY8M) 0
items, Read (DV6F4ILX) 0 items, Produced (6P2KVFKQ) holding all 10 sources from
episodes 001-003, parent `YF84AUZK` still carrying 18 unfiled items. No
production unit exists, so per the HITL skill's "spend the slice on a durable
defect" rule the slice went to a latent retargeting defect rather than
re-proving a known-good feed.

Stale `pipeline/.pipeline.lock` from run 005's `attempt finish` was confirmed
dead both ways before clearing (owner pid 1350812 absent from `/proc`,
non-blocking `fcntl.flock` acquired successfully, `status` reporting
`lock.present: true` / `lock.active: false`) — the documented normal steady
state, not an overlapping run.

- **The Read lane would have announced the WRONG SHOW on air.**
  `read_lane.py`'s `DISCLOSURE` string — the spoken intro of every verbatim
  reading — opened with *"This is Human in the Loop: Moral Machine Edition,
  reading number N."* Run 004 fixed the four HITL leftovers in
  `publish_feed.py` (channel title, channel image title, index title, index h1)
  and the cover art, but `read_lane.py` was never audited because no reading has
  ever been produced on this show. The first reading David files would have
  shipped audio naming the sibling show, inside the one lane whose fidelity gate
  cannot catch it: the gate compares the READING block word-for-word against
  `source.txt` and deliberately ignores the intro and outro. Now reads
  *"This is Moral Machines, reading number N."*
  - Proven functionally, not just textually: loaded the patched module under the
    HITL venv and called `build_script('501', ...)`, asserting the first
    `**Reader:**` line contains `Moral Machines` and no `Human in the Loop`.
  - Checked first that **no gate asserts the old string** (`grep "Moral Machine
    Edition" --include=*.py` returned only the definition itself), so the edit
    cannot weaken a check.
- **Retargeted the show title in `README.md` (1 reference) and
  `style_guide.md` (4 references).** The style guide is the document the
  production cron reads on every run, so it was still telling each slice the
  show was called *Human in the Loop: Moral Machine Edition*.
- **Deliberately KEPT four remaining "Human in the Loop" references** —
  `style_guide.md:4` and `README.md:80` (clone provenance / inherited traps),
  `style_guide.md:348` (the Host voice is *deliberately* shared with the sibling
  show), `README.md:8` (same format, different library). These are accurate prose
  about a sibling show, not branding defects. Per the skill's instruction, hits
  were reviewed individually rather than bulk-replaced.
- Safety on every write: anchor asserted to occur **exactly once** before
  substitution, an explicit `EXPECTED_REWORDS` whitelist for the
  "no original non-blank line may be lost" assertion (never relaxed to
  "mostly additive"), identical line counts pre/post, backups to `*.bak-run006`,
  atomic writes (temp + `os.fsync` + `os.replace`). `diff -u` on
  `read_lane.py` shows **1 removal / 1 addition** — a pure one-line
  substitution. `py_compile` clean on all of `pipeline/*.py`.
- No code path touching the feed, any gate, or any published artifact was
  modified: `feed-site/feed.xml` md5 unchanged at
  `9fc23235fcb49ca809059092da619b54`, still 3 items, `coverage` still `ok: true`
  after the edits.

**Standing blocker for David, unchanged and still the only one:** both intake
lanes are empty, so there is no production unit. 18 on-topic sources sit directly
in the parent collection `YF84AUZK` with `collections: ['YF84AUZK']` and no
subcollection, invisible to both lanes — bioethics, genome-editing governance
(*Heritable Human Genome Editing*, *Human genome editing: recommendations*) and
socioscientific-reasoning instruments (SDM-Q-9, CollaboRATE, ESIT). Seven already
carry a PDF child. Moving any of them into Summerize (V4WXTY8M) or Read
(DV6F4ILX) gives the pipeline work immediately. The worker deliberately does not
file them itself: lane assignment decides interview-vs-verbatim treatment and is
David's call. The Read lane is now safe to receive its first item.


## Run 007 — 2026-11-06 — read-lane publish path proven end to end; bookkeeping reconciled

Both intake lanes were empty again (Summerize `V4WXTY8M` 0 items, Read
`DV6F4ILX` 0 items), `coverage` opened `ok: true` (3 items / 3 published), and
the lock file on disk was the usual stale artifact — owner pid 1375758 gone and
the advisory `flock` free, so `unlock --force` was safe. No production unit
existed, so per the skill's standing instruction the slice went to a durable
defect rather than re-proving a known block.

### Chosen defect: the Read lane had still never been exercised end to end

Run 006 fixed `read_lane.py`'s spoken `DISCLOSURE` (it named the sibling show on
air) and proved that one line by calling `build_script()`. But everything
*downstream* of the script — `publish_feed.py`'s `read_episodes()` copy step,
the feed item it emits, `read_notes_html()`, the index entry, and how `coverage`
treats a live reading — had never run on this show, because no reading has ever
been produced here. That is exactly the "a lane that has never been exercised is
unaudited" lesson from run 006, one stage further down the pipe. The highest
stake is the one the skill calls a hard bug: a **cross-show GUID collision**
with Human in the Loop.

Method: built a scratch reading **990** (two seconds of real `anullsrc` mp3 via
the vendored ffmpeg — no TTS spend), registered it in `read-episodes.json` with
`verified: true`, ran the real `publish_feed.py`, asserted against the **parsed
XML**, then rolled everything back and proved restoration byte-identical. This
is the HITL skill's "verify feed changes without publishing junk" pattern, which
had not previously been applied to this tree's read path.

Eleven assertions, all passing:

1. GUID is `moral-machines-episode-990-reading-SCRATCH7` — correct prefix, and
   **no `human-in-the-loop` substring anywhere**, so the two shows cannot
   collide through the read lane.
2. `<description>` non-empty (173 chars) — the ep-002 empty-description class
   does not reach readings, because `publish_feed.py` *synthesizes* a reading
   description from the citation instead of reading a manifest field.
3. `feed-site/episode-990-reading.mp3` was actually copied (the `-reading`
   suffix naming, not the bare `episode-NNN.mp3` of the false-404 trap).
4. `enclosure length` equals the real on-disk byte size.
5. `enclosure url` ends in the `-reading.mp3` published name.
6. `itunes:duration` rendered as `00:00:02`, not empty or zero.
7. `itunes:episode` is `990`.
8. The read disclosure is present in `content:encoded` ("Dr. Rowan Field does
   not appear") and the interview disclosure did **not** leak into it.
9. The coverage figure renders as `99.72%` rather than `0.00%`.
10. `index.html` lists the reading.
11. `coverage` saw the live reading and reported `ok: true` with empty
    `unrecorded_feed_items` and `enclosure_issues` — it did not mistake a
    reading for an unrecorded item or hunt for a bare `episode-990.mp3`.

One assertion fired on the first pass — *"existing item mutated by read publish:
moral-machines-episode-003"*. **It was a harness artifact, not a defect.** When
ep-003 stops being the final `<item>`, its XML `tail` whitespace changes from
`'\n'` to `'\n      '`; `ET.tostring` includes the tail, so a naive string
compare flags it. Re-ran with tail whitespace normalized: existing items are
**content-identical**, and readings append after interviews. Recorded here
because the naive form of that check will fire again for whoever adds the first
real reading.

Rollback proof: `feed.xml` md5 back to `9fc23235fcb49ca809059092da619b54`,
`read-episodes.json` byte-identical, scratch episode dir and all
`feed-site/episode-990*` files gone. Harnesses kept at
`/opt/data/tmp/mm_read_e2e_run007.py` and `…_run007b.py`.

### Reconciled the manifest/state status lag flagged since run 006

The skill's "diff manifest status against state every slice" check found drift,
and the rule is to check the feed before touching the ledger. Evidence first:
all three episodes feed-present, `preflight` `ok: true` for each, and a live
Zotero read confirming **every** source parent of 001/002/003 sits in Produced
(`6P2KVFKQ`) with no remaining `V4WXTY8M` membership. Feed-present plus
sources-moved means this was bookkeeping lag, not a publication gap.

Advanced all three to the documented end state `published_and_moved` in both
registries, and normalized `manifest` `number` fields `'2'`/`'3'` to
`'002'`/`'003'` (001 already correct) — a latent inconsistency, since
`publish_feed.py` keys on the dict key rather than that field.

Safety: both consumers of these status strings (`interview_episodes()` and
`coverage()`) accept the whole `published*` family, so the change cannot drop an
episode from the feed — which is precisely the bug run 005 fixed. Proven rather
than assumed: republished and `feed.xml` md5 is **unchanged**, `coverage` still
`ok: true` at 3/3. Per-key invariants asserted that no field outside
`status`/`number`/`transitions` moved, `sources` is identical, and the
transition history only grew. Backups at `*.bak-run007`.

### Verification

- `coverage`: `ok: true`, 3 items / 3 published, all issue lists empty.
- `verify --remote`: `ok: true`, `issues: []` — 206 on all three audio
  enclosures, 200 on all three notes.
- Live-vs-local `feed.xml` md5 identical (`9fc23235…`) — zero deploy drift, so
  the reconcile needed no push.
- Manifest-wide duplicate-source scan: 10 sources, no duplicate ownership.
- `py_compile` clean on `pipeline/*.py`.

Nothing was pushed this slice: no published artifact changed, and the live feed
already matches local byte for byte.

**Standing blocker for David, unchanged and still the only one:** both intake
lanes are empty, so there is no production unit. 18 on-topic sources sit directly
in the parent collection `YF84AUZK` with `collections: ['YF84AUZK']` and no
subcollection, invisible to both lanes — bioethics (*Exploring Bioethics*),
genome-editing governance (*Heritable Human Genome Editing*, *Human genome
editing: recommendations*) and socioscientific-reasoning instruments (SDM-Q-9,
CollaboRATE, ESIT). Seven already carry a PDF child. Moving any of them into
Summerize (`V4WXTY8M`) or Read (`DV6F4ILX`) gives the pipeline work immediately.
The worker deliberately does not file them itself: lane assignment decides
interview-vs-verbatim treatment and is David's call. As of this run the Read
lane is not merely "safe to receive its first item" on the strength of a grep —
its publish path is **verified end to end**, including the cross-show GUID check.

## Run 008 — 2026-11-06 — no intake unit; fixed the append-only `errors` extend in `reconcile()`

Both lanes empty again (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0, parent
`YF84AUZK` still 18 unfiled, Produced `6P2KVFKQ` 10). Per the idle-slice rule,
spent the slice closing a durable inherited defect rather than re-probing a
known block.

### The defect: `reconcile()` stored issues unboundedly (HITL run-459 bug, unported)

This tree was still running the pre-fix line at `pipeline/robust_pipeline.py`
~425: `rec.setdefault("errors", []).extend(issues)`, unconditional. Because every
slice runs `reconcile(write=True)`, any issue that stays true (e.g. a planned
stub genuinely having no notes) is re-stored forever — the mechanism that reached
655 entries / 218 exact copies in the HITL tree and pinned `status.healthy` false.

It was **latent** here only because no current episode directory has an issue:
001-003 are complete, and 501 is a bare ledger stub with no `episodes/501/`
directory, so `episode_dirs()` never visits it. Three `reconcile --write` passes
on real state left the total at 0, 0, 0 — which is exactly why a grep-only audit
would have called this tree clean.

Reproduced before fixing, with a scratch `episodes/991/`: error count went
**1 -> 2 -> 3** across three passes, distinct count stayed **1**. Post-fix the
same entry held at **3 -> 3 -> 3**, and introducing a genuinely new issue
(flipping 991 to `rendered` with no mp3) still appended `ledger says audio exists
but no MP3 is present`. So dedupe without suppression: `report["ok"]` is still
False, the live issue list is still returned in full, every distinct issue is
still stored, and structured non-string error records are never merged or dropped
(the `seen` set only considers `str` entries).

Safety pattern: single-occurrence anchor assertion, an explicit expected-removal
whitelist (one line, the replaced `extend` call), an assertion that the new text
is present, backup to `robust_pipeline.py.bak-run008`, atomic temp + `fsync` +
`os.replace`, then `diff -u | grep -c '^-[^-]'` returning **1** — the single
intended removal, nothing else lost.

Scratch `episodes/991/` removed and its ledger entry deleted; 001-003 asserted
identical to the pre-run snapshot on `status` and `sources`; total stored errors
back to 0; ledger episode set back to 001/002/003/501.

Lesson worth carrying: **a bug fixed in the sibling tree is not fixed here.**
This pipeline is a clone, so every HITL code fix is a candidate port, and a
latent instance shows no symptom at all until the first episode with a standing
issue. The same audit should be repeated for other HITL fixes landed after the
clone date.

### Verification

- Pre-fix reproduction 1/2/3 and post-fix hold 3/3/3, plus new-distinct-issue
  acceptance — all on real state with a restore snapshot.
- `coverage`: `ok: true`, 3 items / 3 published, all issue lists empty.
- `verify --remote`: `ok: true`, `issues: []` — 206 on all three audio
  enclosures, 200 on all three notes.
- Live-vs-local `feed.xml` md5 identical (`9fc23235fcb49ca809059092da619b54`),
  unchanged from run 007 — no feed byte moved, nothing to push beyond the code
  commit.
- `py_compile` clean on all `pipeline/*.py`.
- Stale lock from run 007 (pid 1401935) confirmed dead via `/proc` plus a
  non-blocking `flock` that succeeded — normal steady state, not an active run.

### Standing blocker for David, unchanged

Both intake lanes are empty, so there is no production unit. 18 on-topic sources
sit directly in parent collection `YF84AUZK` with no subcollection, invisible to
both lanes — bioethics (*Exploring Bioethics*), genome-editing governance
(*Heritable Human Genome Editing*, *Human genome editing: recommendations*) and
socioscientific-reasoning instruments (SDM-Q-9, CollaboRATE, ESIT); seven already
carry a PDF child. Moving any of them into Summerize (`V4WXTY8M`) or Read
(`DV6F4ILX`) gives the pipeline work immediately. The worker deliberately does
not file them itself: lane assignment decides interview-vs-verbatim treatment and
is David's call.


## Run 009 — 2026-11-06 — ported HITL's read-lane durable-state sync

No intake unit again: Summerize (`V4WXTY8M`) and Read (`DV6F4ILX`) both returned
**0 items** live, Produced holds 10, and the same **18 unfiled sources** sit
directly in parent `YF84AUZK`. Slice spent on the next unported sibling fix, per
the run-008 lesson that every HITL code fix landed after this tree's clone date
is a candidate port.

### The defect

`read_lane.py register()` wrote **only** `pipeline/read-episodes.json`. It
defined `STATE_PATH` and never used it, and `MANIFEST_PATH` did not exist in
this tree at all — so a reading built here would be absent from `state.json`,
`manifest.json` and the attempt ledger while being fully publishable. This is
HITL's run-422 bug, where reading 501 went **live and pushed** in exactly that
state, invisible to `status`, the watchdog and duplicate detection. HITL fixed it
with `sync_durable_state()`; this clone never received the port. Latent only
because no reading has ever been produced here — identical in shape to run 008's
finding.

### Retargeting that mattered

HITL's version hardcodes `f"human-in-the-loop-{guid}"` for the manifest guid.
`publish_feed.py` in **this** tree prepends `moral-machines-` itself, so copying
that line verbatim would have written a cross-show GUID into this show's
registry — the collision both skills call a hard bug. The port stores
`moral-machines-<guid>` and the write script asserts the file contains **no**
sibling-show substring anywhere. That assertion fired on the first attempt,
against my own explanatory docstring quoting the sibling prefix; the comment was
reworded rather than the guard relaxed. `MANIFEST_PATH` was also added, since it
was absent here.

### Proof (real code, not greps)

Harness `/opt/data/tmp/mm_sync_state_proof_run009.py` loads the **pre-fix
backup** and the **post-fix live module** against scratch copies of the
registries:

- **A — pre-fix reproduction:** the backup's `register()` wrote the reading into
  `read-episodes.json` while `state.json` and `manifest.json` stayed
  byte-unchanged. The bug is real here, not theoretical.
- **B — post-fix:** 15/15 assertions, including both registries populated,
  `kind: read`, `status: verified`, the fidelity-gate check recorded with its
  coverage figure, the key under **`read_source`** (not `sources`, which would
  trip `preflight()`'s false duplicate-ownership report), a non-empty
  description, the `moral-machines-` GUID with no sibling substring, and 001-003
  untouched.
- **C — merge safety:** re-registering over a `published_and_moved` record does
  **not** downgrade it and preserves `attempt_log` and `errors`.

The harness never writes the live registries: `manifest.json` is byte-identical
to its pre-run snapshot, and `state.json` differs only by this run's
`attempt start`. Scratch 992 exists nowhere in live state.

### Verification

- Write script: **0 removals / 103 additions**, backup `read_lane.py.bak-run009`,
  atomic temp + `fsync` + `os.replace`, `py_compile` clean on all `pipeline/*.py`.
- `coverage`: `ok: true`, 3 items / 3 published, all four issue lists empty.
- `verify --remote`: `ok: true`, `issues: []`, 8 checks.
- Live-vs-local `feed.xml` md5 identical (`9fc23235fcb49ca809059092da619b54`,
  unchanged since run 007) — no feed byte moved; nothing to publish or push
  beyond the code commit.
- Stale lock from run 008 (pid 1459176) confirmed dead via `/proc` plus a
  successful non-blocking `flock` before `unlock --force` — normal steady state.

### Note for the first real reading

`sync_durable_state()` is now called from `register()`, so the manual
"write state.json and manifest.json yourself after every build+render+publish"
step in the HITL skill is **no longer required in this tree**. Verify the two
registries after the first real reading anyway, since the path has never run
against a non-scratch reading.

### Standing blocker for David, unchanged

Both intake lanes are empty. Moving any of the 18 parent-collection items into
Summerize (`V4WXTY8M`) or Read (`DV6F4ILX`) gives the pipeline work immediately.
The worker does not file them itself: lane assignment decides
interview-vs-verbatim treatment and is David's call.

## Run 010 — 2026-11-06 — no intake unit; `read_lane.py build` can now pull its own PDF

Both intake lanes empty again (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0; the
same 18 items sit unfiled in parent `YF84AUZK`). Stale lock from run 009
(pid 1496553) confirmed dead via `/proc` plus a successful non-blocking `flock`
before `unlock --force` — normal steady state, not an overlapping run. Slice
spent on a durable defect per the skill's "both lanes idle" rule.

### Port census first: no backlog in `robust_pipeline.py`

Run 009 flagged the sibling-tree line-count gap as a port backlog, so I diffed
all five shared modules against `/data/.openclaw/workspace/media/zotero-podcast/pipeline/`.
Every difference is legitimate retargeting, not a missing fix:

- `robust_pipeline.py` (11 lines short) — feed/repo URLs, git identity, the
  locked voices (`AndrewMultilingualNeural` +18% vs HITL's `SoniaNeural` -2%),
  `ET` vs `ElementTree` import style, and comment rewording. The run-008 `errors`
  dedupe is present on both sides.
- `publish_feed.py` — this tree's `interview_episodes()` derivation vs HITL's
  hardcoded `EP` list. **This tree is the better design**; the EP-list silent-skip
  class cannot occur here.
- `move_verified_sources.py`, `render_from_script.py`, `read_lane.py` — collection
  keys, voices, show name, and run-009's retargeted GUID prefix.
- HITL-only files (`render_episodes.py`, `_check_incoming.py`,
  `check_incoming_live.py`) are intentionally absent.

So the line-count heuristic from run 009 is **exhausted**: treat it as closed
rather than re-running it every slice.

### The defect: `build()` could not fetch a Zotero attachment

`build()` raised `SystemExit("no --pdf given: download the Zotero attachment
first (read_lane.py cannot yet pull attachments)")` whenever `--pdf` was omitted.
That is the single remaining hard stop between David filing an item in Read and
a reading existing — and it bites the **unattended cron specifically**, because
no pipeline stage puts a PDF on disk before `build`, and the cron has no human to
hand it a path. Runs 006/007/009 verified the lane's disclosure, publish path and
durable-state sync; all of that sat behind a step the cron cannot execute.

Fix: `fetch_pdf_attachment()` + `zotero_get_bytes()`. `build()` now downloads the
item's stored PDF child when `--pdf` is absent and records provenance
(`attachment_key`, `filename`, `bytes`, `source`, `extra_pdf_attachments`) into
the extraction report. Design choices worth keeping:

- `zotero_get()` json-decodes, which a PDF body cannot survive, hence a separate
  bytes helper. The `/file` endpoint 302s to a storage host; urllib follows it and
  the key header is not needed on the redirect target.
- `linked_url` attachments are **skipped**, not downloaded — they have no stored
  file and would yield an empty extraction that looks like a bad PDF.
- A non-`%PDF-` body raises with the byte count rather than being extracted, and
  "no stored PDF" names the item key, so the failure is actionable instead of
  surfacing later as mysteriously empty body text.

### Proof on real code, both sides

Harness `/opt/data/tmp/mm_attachment_proof_run010.py`, 31/31 assertions, against
item `N4Q66RCJ` (Kinslow 2020, one `imported_file` PDF child):

- **A — pre-fix reproduction:** the `read_lane.py.bak-run010` backup raises the
  hard stop with `--pdf` omitted. The block was real here, not theoretical.
- **B — post-fix auto-pull:** 23 pages / 8,284 body words extracted from a
  2,269,920-byte download, `provenance.source == 'zotero'`, byte count matching
  the file on disk, `source.txt` / `extraction-report.json` / `script.md` written,
  script announces **"This is Moral Machines"** with no sibling-show substring,
  manifest guid `moral-machines-…`, source key under **`read_source`** (not
  `sources`, which would trip `preflight()`'s false duplicate-ownership report).
- **Gate still gates:** with no audio rendered, `verify` returned `ok: false`
  while computing word coverage `1.0`. Word fidelity passing does **not** pass the
  episode — the audio-duration check correctly withheld it. A fix to the intake
  step did not weaken the fidelity gate.
- **C — `--pdf` regression:** an explicit local path still works, records
  `source: 'local'`, and extracts the identical word count.
- **Live registries byte-identical** (`read-episodes.json`, `state.json`,
  `manifest.json`); no live `episodes/993` or `episodes/994`. The harness runs
  entirely against scratch copies under `/opt/data/cache/scratch/mm_run010_proof/`.

Harness pitfall for next time: a module copied into scratch resolves `ROOT`
relative to **its own** location, so `ZOTERO_KEY_FILE` points at a nonexistent
`check_zotero.py` and `zotero_key()` dies with `FileNotFoundError`. Export
`ZOTERO_API_KEY` in the harness before loading a relocated copy.

### Verification

- Write script: **7 removals, all whitelisted** (the old hard-stop raise plus two
  reflowed copy lines) / 70 additions; backup `read_lane.py.bak-run010`; atomic
  temp + `fsync` + `os.replace`; `py_compile` clean on all `pipeline/*.py`.
- `coverage`: `ok: true`, 3 items / 3 published, all four issue lists empty.
- `verify --remote`: `ok: true`, `issues: []`, 8 checks.
- `feed-site/feed.xml` md5 `9fc23235fcb49ca809059092da619b54` — unchanged since
  run 007. No feed byte moved; nothing to publish or push beyond the code commit.
- Docs synced: `read_lane.py` usage docstring and `README.md` line 55 no longer
  claim `--pdf` is required.

### Standing blocker for David, unchanged

Both intake lanes are empty. Moving any of the 18 parent-collection items into
Summerize (`V4WXTY8M`) or Read (`DV6F4ILX`) gives the pipeline work immediately —
and as of this run a Read item needs **nothing** but the move: `build` fetches the
PDF, scripts, gates and registers on its own. Seven of the 18 already have a PDF
child. The worker still does not file them itself: lane assignment decides
interview-vs-verbatim treatment and is David's call.


## Run 011 — 2026-11-06 — `move_verified_sources.py` had three silent no-ops

Both intake lanes empty again (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0; the
same 18 items still sit unfiled in parent `YF84AUZK`). No production unit, so the
slice went to a durable defect per the HITL rule — and the one it found is the
step that runs *immediately after* a publish, which run 010's intake fix made
newly reachable.

### Three defects, all silent

`pipeline/move_verified_sources.py` selected its sources with a literal
`status == 'published'` over manifest `sources`, then stripped only Summerize:

1. **Status gate too narrow.** The documented end state `published_and_moved`
   (002's convention) and the pre-move `published_pending_zotero_move` both
   failed `== 'published'`. Re-running the mover after a status bump moved
   nothing and still exited 0. This is the run-005 `interview_episodes()` class
   in a second location — when a status string is a gate, test it against
   **every** status the docs tell you to write.
2. **Readings were invisible to it.** `read_lane.py` registers a reading's Zotero
   key under **`read_source`**, deliberately, so `preflight()`'s interview
   source-ownership model does not report a false duplicate. The mover read only
   `sources`, so a published reading's source could never reach Produced.
3. **The wrong lane was stripped.** A reading's source lives in **Read**, not
   Summerize. After a "successful" move the item kept its `DV6F4ILX` membership,
   so `read_lane.py zotero-read` would re-offer a paper already published as a
   reading — a duplicate-reading loop.

Fix: accept any `published*` status, union `sources` + `read_source` with
de-duplication, and strip both lanes via a new `LANES=(INCOMING, READ)` while
preserving every other membership.

### Why it looked clean

Pre-fix selection against **live** state returns `[]` — 001-003 are all
`published_and_moved`, which the old gate rejected. So the mover had been a
complete no-op on real state and three passes would have shown nothing wrong.
Defect 2 and 3 were latent only because no reading has ever been published here.
Same lesson as run 008: a clean-looking state proves nothing about this class.

### Proof on real code, both sides

Harness `/opt/data/tmp/mm_mover_proof_run011.py`, **33/33 assertions**. It
executes each version's own selection block and strip line extracted from source
text (the module issues PUTs at import, so it is never imported) against scratch
copies of the registries:

- **A — pre-fix reproduction:** published reading selects nothing; both
  `published_and_moved` and `published_pending_zotero_move` select nothing; strip
  leaves `DV6F4ILX` in place; live state selects nothing. All four bugs real here.
- **B — post-fix:** reading *and* interview sources selected at all three
  `published*` statuses.
- **C — gate not weakened:** `planned`, `built`, `verified`, `rendered`,
  `scripted`, `failed` and `''` still excluded.
- **D — de-duplication** and the 10 live sources now selected where pre-fix 0 were.
- **E — strip:** Read stripped, Produced added, unrelated memberships
  (`YF84AUZK`, a decoy) preserved, Summerize regression intact, an item in both
  lanes loses both, an already-moved item is idempotent.
- **F — guards:** no sibling-show substring, results JSON lands in **this** tree,
  no hardcoded key.

### Live run

With the fix in place the real mover selected **10** sources and reported
`already-moved` for all 10, each with `collections: ['6P2KVFKQ']` — **zero PUTs
issued**. That is the correct idempotent outcome and confirms 001-003's sources
are still exactly where run 007 left them.

### Verification

- Write script: 3 removals (all whitelisted) / 20 additions; backup
  `move_verified_sources.py.bak-run011`; atomic temp + `fsync` + `os.replace`;
  `py_compile` clean on all `pipeline/*.py`.
- `coverage`: `ok: true`, 3 items / 3 published.
- `verify --remote`: `ok: true`, `issues: []`.
- `feed-site/feed.xml`, `state.json`, `manifest.json`, `read-episodes.json` all
  **md5-identical** before and after the slice. No feed byte, no gate, no ledger
  status moved.

### Standing blocker for David, unchanged

Both lanes are empty; the 18 on-topic items remain unfiled in `YF84AUZK`. Moving
any one into Summerize or Read gives the pipeline work immediately. As of run 010
a Read item needs nothing but the move, and as of this run its source will also
reach Produced correctly afterwards. Lane assignment stays David's call.

## Run 012 — 2026-11-06 — read-lane `render` audited on real TTS (37/37)

No intake unit: Summerize `V4WXTY8M` **0**, Read `DV6F4ILX` **0**, the same
**18** items still unfiled directly in `YF84AUZK`. `coverage` opened `ok: true`
(3 items / 3 published), manifest and state agree at `published_and_moved` for
001-003, and the lock was the normal dead-owner artifact (pid 1558003 gone,
`flock` free) — cleared with `unlock --force`.

Spent the slice on the last unaudited read-lane stage, per the idle-slice rule.

### Why `render` was the remaining gap

Runs 006-011 verified the lane's spoken show name, publish path, durable-state
sync, Zotero PDF intake and the Produced mover. **Every one of them either used a
silent `anullsrc` stub (run 007) or produced no audio at all.** So
`render_episode()` had never executed in this tree, and neither had the
**audio-duration branch** of the fidelity gate — the half that cannot be tested
without real audio, and the half that is the lane's only protection against a
truncated or padded render. Run 010's lesson applies to itself: verifying stages
around a stage is not verifying the stage.

### Proof

Harness `/opt/data/tmp/mm_render_proof_run012.py`, **37/37**, scratch reading
**990**, real Edge TTS (5 parts, 1,515,788 bytes, 126.3 s). It never calls
`build()`/`register()`, so no registry write path is involved.

- **A — locked voice:** `en-US-AvaMultilingualNeural` at `-3%`, and the read lane
  contains no Rowan voice at all (single-voice invariant holds in code).
- **B — script:** real `build_script()`; intro reads *"This is Moral Machines,
  reading number 990."* and the file contains **no** sibling-show substring.
- **C — gate refuses pre-render:** `ok: false` with exactly `no audio rendered
  yet` while word coverage is already **1.0**. Word fidelity passing is not the
  episode passing; the audio check is what withholds it.
- **D — render:** 5/5 parts above the 500-byte floor, reported part count matches
  disk, `audio_seconds()` parses ffmpeg stderr correctly (**126.3 s**).
- **E — duration gate on honest audio:** `ok: true`, `issues: []`. Measured ratio
  **0.968** against the gate's 0.650-1.450 window; effective rate **154.9 wpm**
  against the assumed `WORDS_PER_MINUTE = 150.0`. The 3% constant error is
  nowhere near either edge, so the window is correctly sized for Ava at `-3%` —
  a real reading would false-fail only below 85 s or above 189 s for 326 spoken
  words. Confirms the run-007-era note that the baseline must count
  intro+reading+outro (326 words) and not the reading block alone (121).
- **F — gate not weakened:** truncating the audio to 3 s is **rejected** naming
  the duration; deleting one source sentence is **rejected** at coverage 0.909;
  injecting 20 words of editorial commentary is **rejected** as text added. Gate
  green again after each restore.
- **G + teardown:** `state.json`, `manifest.json`, `read-episodes.json` and
  `feed-site/feed.xml` all **md5-identical** before, during and after; no `990`
  in either registry; scratch dir removed.

### Net

The read lane is now exercised end to end on real audio — intake, script,
disclosure, render, both halves of the fidelity gate, publish, durable state and
the Produced move have each been proven in this tree. No code changed this run;
nothing was pushed. The lane is ready for the first real Read item.

### Standing blocker for David, unchanged

Both lanes are empty; the 18 on-topic items remain unfiled in `YF84AUZK`
(bioethics, genome-editing governance, socioscientific-reasoning instruments —
7 already carry a PDF child). Moving any one into Summerize or Read gives the
pipeline work immediately; a Read item needs nothing but the move. Lane
assignment stays David's call.

## Run 013 — 2026-11-07 — a published reading was also emitted as an INTERVIEW item (fixed)

Both intake lanes empty again (Summerize `V4WXTY8M` 0, Read `DV6F4ILX` 0, the
same 18 items still unfiled directly in `YF84AUZK`), so the slice went to a
durable defect. Opening state clean: `coverage` 3/3 `ok: true`, manifest and
ledger agree `published_and_moved` on 001-003, `verify --remote ok: true`, live
feed md5 `9fc23235` identical to local. Stale lock with dead pid 1599144
(`flock` free) — the normal steady state; `unlock --force`.

### The defect

`publish_feed.py`'s `interview_episodes()` had **no lane filter**. It selects an
episode on two tests: the ledger status is in the published family, and
`episodes/NNN/episode-NNN.mp3` exists. A reading satisfies **both**:

* `read_lane.sync_durable_state()` (ported run 009) writes a `manifest.json` and
  `state.json` record for the reading, by design.
* `read_lane.render_episode()` writes its audio to exactly
  `episodes/NNN/episode-NNN.mp3` (line ~415). The published *name* gains the
  `-reading` suffix only later, inside `publish_feed.py`.

So the first reading to reach `published` would appear in the feed **twice**: the
correct `episode-NNN-reading.mp3` item from `read_episodes()`, plus a bogus
`episode-NNN.mp3` interview item whose `<content:encoded>` is `notes_html()` —
the synthetic-interview disclosure naming **Dr. Rowan Field**, which the style
guide forbids on a verbatim reading, and which `read_notes_html()` exists
specifically to replace. It would also 404 on the asset, since nothing copies a
bare `episode-NNN.mp3` to `feed-site/` for a reading.

This is the third instance of the same class in this file: a status/shape string
is used as a gate and the *other* lane's records slip through it (run 005's
`('rendered','published')` tuple, run 009's cross-show GUID prefix). The lanes
share the manifest and they share the on-disk audio filename; only `kind`
separates them.

**Latent, and invisible to every green check.** No reading has ever been
published here, so `coverage` 3/3, `verify ok: true` and `publish ok: true` were
all accurate and all blind to it — the run-008 lesson again: a clean state proves
nothing about a class that needs a record no registry holds yet. It would have
fired on the *first real reading*, which is exactly the unit the last seven runs
of read-lane auditing were preparing for.

### Fix

`interview_episodes()` now skips any manifest record whose `kind` is `read`
(interviews carry no `kind` key, so the test is "not explicitly a reading").
Eleven comment lines plus the two-line guard; `diff` shows **0 removed lines**.
Backup `pipeline/publish_feed.py.bak-run013`, atomic temp+`fsync`+`replace`,
`py_compile` clean.

### Proof, on real code, both sides

`/opt/data/tmp/mm_dup_item_proof_run013.py` — 11/11, reproduces the bug against
the **unmodified** module: scratch reading 990 registered the way the real lane
registers one, `EP` returns `['001','002','003','990']`, the bogus tuple
advertises `episode-990.mp3` with GUID suffix `episode-990`, and `notes_html()`
for it names Rowan while `read_notes_html()` correctly says he does not appear.

`/opt/data/tmp/mm_fix_proof_run013.py` — 20/20:

- **A** the pre-fix `.bak` module *still* reproduces the duplicate, so the bug
  was real here and not a harness artifact.
- **B** post-fix `EP` drops 990 while `read_episodes()` **still** returns it —
  the read lane is not weakened, only the interview lane is corrected.
- **C** the three interview tuples are byte-identical pre/post, same order.
- **D** the real `main()` emits **4** items for 3 interviews + 1 reading: exactly
  one `-reading-` GUID, no bare `moral-machines-episode-990` GUID, no
  `episode-990.mp3` enclosure, every `<description>` non-empty, the reading's
  content carries the read disclosure, and no GUID contains any sibling-show
  substring (the hard-bug check).
- **E** `state.json`, `manifest.json`, `read-episodes.json` and `feed.xml`
  md5-identical throughout; scratch removed.

Then on live state: `publish_feed.py` republished to a **byte-identical**
`feed.xml` (`9fc23235`, 3 items), `coverage` 3/3 `ok: true`, `verify --remote`
`ok: true` `issues: []`, and the live feed still md5-matches local. A fix near
the publish path must prove the existing feed did not move.

Note `spec_from_file_location` returns `None` for a `.bak-runNNN` suffix — the
harness copies the backup to a `.py` name inside its own scratch tree first
(run-009 pitfall, hit again).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK` (bioethics,
genome-editing governance, socioscientific-reasoning instruments; 7 already carry
a PDF child). Moving any one into Summerize or Read gives the pipeline work
immediately — a Read item now needs nothing but the move. Lane assignment is
David's call.

---

## Run 014 — no intake unit; ported the stale ROBUST_PIPELINE.md (docs-only)

### Intake state (live Zotero read)

Summarize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. 18 on-topic items
still sit directly in `YF84AUZK` with no subcollection membership -- the
standing blocker for David (lane assignment is his call), unchanged since run
005. No production unit available.

### The defect

`pipeline/ROBUST_PIPELINE.md` was the **pre-run-457 clone** of the sibling
show's doc (107 lines vs 204), and the cron reads it on every run. It:

* listed no `push` or `coverage` subcommands (both exist here; `push` is the
  only correct ship path, `coverage` the mandated first command of every
  slice),
* had no intake-lane or Read-lane section at all, so a slice could not learn
  the collection keys, the reading flow, or the fidelity-gate thresholds from
  the doc,
* told the worker to run `python3 -m unittest discover -s tests`, which dies
  with *Start directory is not importable* in this tree (no `tests/` here),
* described the read-lane `build` as requiring `--pdf` (stale since run 010:
  `build` now pulls the Zotero PDF attachment itself), and the mover as
  keying on exactly `published_pending_zotero_move` (stale since run 011: it
  accepts the whole `published*` family plus `read_source`).

### Fix

Ported the sibling's run-457 sections and retargeted every coordinate against
**verified local facts**, not the sibling's: the CLI subcommand list
(`robust_pipeline.py --help`), `read_lane.py --help` (build auto-pull,
`--pdf` optional), `move_verified_sources.py` source (published* family +
`sources`/`read_source` union), the live Zotero collection names (Summarize /
Read / Produced / 2026 NIH SEPA), and this tree's absence of `tests/`. The
`preflight()` open-issue note is carried over and marked latent: no reading
has been published here yet.

### Proof

Atomic write with `pipeline/ROBUST_PIPELINE.md.bak-run014`; the
alignment-independent line-multiset check shows exactly **3** lost lines (the
stale tests-section sentence + the `unittest` command line) and 98 new
non-blank lines added -- nothing else touched. `py_compile pipeline/*.py`
clean; `feed-site/feed.xml` md5 `9fc23235` unchanged; `coverage` 3/3
`ok: true`; live feed md5 identical to local. Commit `1d6e0c7` pushed via
token URL (docs-only slice; `robust_pipeline.py push` intentionally not used
so no feed-site sync commit was created); remote `main` confirmed at
`1d6e0c7` by `git ls-remote`.

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summarize or Read gives the pipeline work immediately -- a Read item
needs nothing but the move.

---

## Run 017 — no intake unit; no durable defect to spend the slice on

### Intake state (live Zotero read)

Summarize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Produced
`6P2KVFKQ`: 10 episode sources + 9 attachment children, all confirmed on
live `collections`. The 18 on-topic items still sit directly in
`YF84AUZK` (all `dateAdded` 2026-11-03, unchanged since run 005) — the
standing blocker for David: lane assignment (interview vs verbatim) is his
call, and neither lane reads the parent collection.

### Port census re-check

Sibling tree's `pipeline/*.py` mtimes all predate run 010's census
(2026-11-06 15:21) — the sibling has not changed since, so the run-010
verdict stands: every remaining diff in the five shared modules is
legitimate retargeting, and there is no new port candidate. Port backlog
remains closed.

### State

`coverage` 3/3 `ok: true`; `feed-site/feed.xml` md5 `9fc23235` unchanged
local and live (identical). No code, gate, or feed byte moved; no
publication attempted.

---

## Run 018 — no intake unit; steady state re-confirmed on live checks

### Intake state (live Zotero read)

Summarize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items (both LMV 10103).
Parent `YF84AUZK` direct: 18 on-topic items + 7 attachment children, all
dateAdded 2026-11-03, unchanged since run 005 — the standing blocker for
David: lane assignment (interview vs verbatim) is his call, and neither lane
reads the parent collection. No production unit available.

### Drift checks (live, this run)

- Live feed md5 == local `feed-site/feed.xml` md5 (`9fc23235`) — zero deploy
  drift; `coverage` 3/3 `ok: true` (empty issue lists).
- Remote `main` head == local HEAD (`14ba974`) — no missing commits.
- Sibling tree's newest `pipeline/*.py` is 2026-11-06 01:02
  (`publish_feed.py`), predating run 010's census (2026-11-06 15:21): run 010's
  verdict stands, no new port candidate. Port backlog remains closed.
- No logged, deferred durable defect available to spend the slice on (port
  census closed run 010/017, ROBUST_PIPELINE.md ported run 014, preflight
  read-scoring issue is latent here and already recorded as David's call).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summarize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.

## Run 019 — 2026-11-08 — no intake unit; steady state re-confirmed (18 unfiled unchanged)

### Intake state (live Zotero read)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items (both LMV 10103).
Parent `YF84AUZK` strict-direct: 18 on-topic items + 7 attachment children,
all dateAdded 2026-11-03, unchanged since run 005. NOTE: a raw collection
fetch returns 25 "in-tree" items, but 7 of those are the PDF attachment
children (they carry no `collections` array), so the correct unfiled-parent
count is 18 — matching every prior run; the 25 was an attachment double-count
in this run's first script, not new items. No production unit available.

### Drift checks (live, this run)

- Live feed md5 == local `feed-site/feed.xml` md5 (`9fc23235`) — zero deploy
  drift; `coverage` 3/3 `ok: true` (empty issue lists).
- Remote `main` head == local HEAD (`65def27`) — no missing commits.
- Sibling tree's newest `pipeline/*.py` is 2026-11-06 01:02, predating run
  010's census (2026-11-06 15:21): no new port candidate; port backlog closed.
- No logged, deferred durable defect to spend the slice on (port census closed
  010, ROBUST_PIPELINE.md ported 014, read lane fully exercised 006-013).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.

## Run 020 — 2026-11-08 — no intake unit; steady state re-confirmed (18 unfiled unchanged)

### Intake state (live Zotero read)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`:
18 on-topic items direct + 7 attachment children (filtered by itemType, per
run 019's correction of the raw-fetch double-count), unchanged since run 005.
No production unit available.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` (empty issue lists) — first command of the slice.
- Live feed md5 == local `feed-site/feed.xml` md5 (`9fc23235`) — zero deploy
  drift.
- Remote `main` head == local HEAD (`d5a73f5`) — no missing commits.
- Stale lock file present (run 019 owner pid dead, advisory lock free) — the
  normal steady state, not an active run.
- No logged, deferred durable defect available to spend the slice on (port
  census closed 010/017, ROBUST_PIPELINE.md ported 014, preflight
  read-scoring issue is latent here and already recorded as David's call).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.

## Run 021 — 2026-11-08 — no intake unit; steady state re-confirmed (18 unfiled unchanged)

### Intake state (live Zotero read)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items — both confirmed via
direct collection query (counting returned items, not a raw-fetch total). Parent
`YF84AUZK`: 18 on-topic items direct + 7 attachment children, unchanged since
run 005. No production unit available.

### A false alarm this run, and the lesson

My first reconcile script reported "0 items" for **every** SEPA collection —
Summerize, Read, Parent *and* Produced — which looked like a library wipe. It
was a bug in the script, not the library: the `X-Zotero-TotalResults` response
header was **absent** on those responses and the script's
`int(header.get("X-Zotero-TotalResults", "0"))` silently defaulted to 0. Direct
single-item lookups of all ten published source keys (001-003) returned each one
present in `6P2KVFKQ` with `deleted=False`, and the Parent still lists the 18
on-topic items. **Lesson: do not read a missing `X-Zotero-TotalResults` header
as an empty collection — count the returned items or look keys up directly.**
The group LMV advanced (10103 -> 10149) only because this is the shared Field
Day group library (HITL also writes to it), not because SEPA's collections
changed.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` (empty issue lists) — first command of the slice.
- Live feed md5 == local `feed-site/feed.xml` md5 (`9fc23235`) — zero deploy
  drift.
- Remote `main` head == local HEAD (`5d10925`) — no missing commits.
- Stale lock file present (run 020 owner pid dead, advisory lock free) — the
  normal steady state, not an active run.
- No logged, deferred durable defect available to spend the slice on (port
  census closed 010/017, ROBUST_PIPELINE.md ported 014, read lane fully
  exercised 006-013).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.

## Run 022 — 2026-11-08 — no intake unit; steady state re-confirmed (LMV unchanged since 021)

### Intake state (live Zotero read, item-list counts)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items — counted from returned
item lists (limit 100), not the `X-Zotero-TotalResults` header, which is absent
and was the run-021 false-all-zero trap. Parent `YF84AUZK`: 18 unfiled items +
7 attachments, all dateAdded 2026-11-03, unchanged since run 005. Produced
`6P2KVFKQ`: 10 source parents + 9 attachments; all ten published source keys
(001-003) individually confirmed live in `6P2KVFKQ`, `deleted` unset. Group
LMV 10149 — identical to run 021's last observation, so the library has not
changed since the previous run.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` — first command of the slice.
- Live feed md5 == local `feed-site/feed.xml` md5 (`9fc23235`).
- `origin/main` == local HEAD (`db66737`) — no missing commits.
- Stale lock present, owner pid dead — the normal steady state.
- Sibling tree's newest `pipeline/*.py` (2026-11-06 01:02) predates the run-010
  census, so no new port candidate; no logged, deferred durable defect available.

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.
## Run 023 — 2026-11-09 — no intake unit; steady state re-confirmed (eighth consecutive idle run)

### Intake state (live Zotero read, item-list counts)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`:
18 unfiled parent items + 7 attachment children, all dateAdded 2026-11-03,
unchanged since run 005 (the collection-list endpoint is authoritative for
membership; the list-form `collections` field is not populated, and a full
item fetch of a listed member confirms the item is unfiled, not deleted).
No deletion events.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` — first command of the slice.
- Live feed md5 == local `feed-site/feed.xml` md5 (`9fc23235`).
- `origin/main` == local HEAD (`72ffd0cf`) before this run's ledger commit.
- Stale lock present, owner pid dead, advisory lock free — the normal steady
  state, no active run.
- Sibling tree's newest `pipeline/*.py` (2026-11-06 01:02) predates the run-010
  census, so no new port candidate; no logged, deferred durable defect available
  (census closed 010/017, docs ported 014, read lane fully exercised 006-013,
  mover fixed 011).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.
## Run 024 — 2026-11-09 — no intake unit; steady state re-confirmed (ninth consecutive idle run)

### Intake state (live Zotero read, item-list counts)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`:
18 unfiled parent items + 7 attachment children, all dateAdded 2026-11-03,
unchanged since run 005. Produced `6P2KVFKQ`: 10 source parents + 9
attachments, unchanged.

Group LMV advanced 10149 -> 10242 since run 023. The change feed since v10149
carries 25 item entries, all outside the SEPA collections (educational-assessment
and ThermoVR literature from other Field Day projects); every SEPA collection is
unchanged in count and dateAdded. Group-level noise, not SEPA activity.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` — first command of the slice.
- Live feed md5 == local `feed-site/feed.xml` md5 (`9fc23235`).
- `origin/main` == local HEAD (`70628a7`) before this run's ledger commit.
- Stale lock present, owner pid dead, advisory lock free — the normal steady
  state, no active run.
- Sibling tree's newest `pipeline/*.py` (2026-11-06 01:02) still predates the
  run-010 census — no new port candidate; no logged, deferred durable defect
  available (census closed 010/017, docs ported 014, read lane fully exercised
  006-013, mover fixed 011).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.

## Run 025 — 2026-11-09 — no intake unit; steady state re-confirmed (tenth consecutive idle run)

### Intake state (live Zotero read, item-list counts)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`:
25 items (18 unfiled parents + 7 attachment children, all dateAdded
2026-11-03), unchanged since run 005. Produced `6P2KVFKQ`: 19 items (10 source
parents + 9 attachments), unchanged. No deletion events.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` — first command of the slice.
- Working tree clean; local HEAD == `origin/main` (`2fb8de2`).
- Stale lock present, owner pid dead, advisory lock free — the normal steady
  state, no active run.
- Sibling tree's newest `pipeline/*.py` (2026-11-06 01:02, `publish_feed.py`)
  still predates the run-010 census — no new port candidate; no logged,
  deferred durable defect available (census closed 010/017, docs ported 014,
  read lane fully exercised 006-013, mover fixed 011).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.

## Run 026 — 2026-11-09 — no intake unit; steady state re-confirmed (eleventh consecutive idle run)

### Intake state (live Zotero read, item-list counts)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`:
25 items (18 unfiled parents + 7 attachment children, all dateAdded
2026-11-03, same keys as runs 024/025), unchanged since run 005. Produced
`6P2KVFKQ`: 19 items (10 source parents + 9 attachments), unchanged. No
deletion events.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` — first command of the slice.
- Working tree clean; local HEAD == `origin/main` (`86867d2`) before this run's
  ledger commit.
- No lock file at all — no active run (previous runs found the normal stale-lock
  steady state; absence is the safer variant).
- Sibling tree's newest `pipeline/*.py` still predates the run-010 census —
  no new port candidate; no logged, deferred durable defect available (census
  closed 010/017, docs ported 014, read lane fully exercised 006-013, mover
  fixed 011).

### State

No code, gate, or feed byte moved; no publication attempted. Ledger recorded
under the standing no-work key 501 (bare planned stub, no `episodes/501/`).

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing any
one into Summerize or Read gives the pipeline work immediately — a Read item
needs nothing but the move.

## Run 027 — 2026-11-09 — proved a latent HARD BLOCKER in the read lane's mandated publish path

### Intake state (live Zotero read)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`: 18
unfiled parents, unchanged keys since run 005. Produced `6P2KVFKQ`: 10 source
parents. No deletion events. Twelfth consecutive run with no intake unit.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` — first command of the slice.
- Manifest status == state status for 001/002/003, all `published_and_moved`.
- Stale lock present with dead owner pid 2118185, advisory lock free (the normal
  steady state); cleared with `unlock --force`.
- Working tree clean, local HEAD == `origin/main` (`b088fd1`) before this run.
- Sibling `pipeline/*.py` mtimes still predate the run-010 census — no new port.

### The defect (latent, now proved on real code)

Rather than re-prove a known steady state a twelfth time, the slice closed the
`preflight()`-vs-readings open issue that has been carried as "escalated, latent"
since run 014 — and found it is **materially worse than documented**. It was
recorded as "a reading fails preflight"; it is in fact a blocker on the whole
publish command:

1. `preflight()` rejects a fully style-guide-compliant reading on four
   interview-only rules (`no Host/Rowan turns`, fictional-correspondent
   disclosure, AI-summary disclosure, `review gate: review panel is missing`).
   The error text never names the fidelity gate the reading passed.
2. `publish_local()` gates on `status != "published"`, so it routes the reading
   to that interview preflight and **raises** — `publish --episode NNN` cannot
   ship a reading at all.
3. Since run 009 the reading is also in `manifest.json`, so a **bare `publish`
   aborts the entire run**: one registered reading blocks publication of every
   healthy interview episode, while 001/002/003 each return `preflight ok: true`
   individually.
4. `read_lane.py` has no `publish` subcommand, so there is no route around it.

Run 009's durable-state sync is correct and must NOT be reverted — it is simply
what makes this reachable. The collision stayed invisible because runs 007/012/013
exercised the read lane by calling `publish_feed.py` directly and never called
`robust_pipeline.py publish`: **verifying a lane with a harness that skips the
mandated command does not verify the mandated command.** `coverage` 3/3,
`verify ok: true` and `publish ok: true` are all accurate today and all blind to
it, the same shape as runs 008 and 013.

Harnesses: `/opt/data/tmp/mm_read_publish_gate_run027.py` (18 assertions) and
`mm_read_publish_blast_run027.py` (19 assertions, real `publish_local()` against
scratch registry copies). Both assert the real `state.json`, `manifest.json`,
`read-episodes.json` and `feed.xml` are md5-identical throughout; the scratch
`episodes/990/` dir is removed at the end of each.

### Not fixed here, deliberately

`preflight()` and `publish_local()` are publication gates. The fix is a
`kind == "read"` branch deferring to the fidelity gate, mirroring
`publish_feed.py`'s run-013 read guard — a gate edit that must not land
unreviewed at the end of an unattended slice. Escalated to David instead, now
with the proven blast radius and an interim route (call `publish_feed.py main()`,
then `verify`, then `push`) recorded in `pipeline/ROBUST_PIPELINE.md`.

### State

No code, gate, or feed byte moved: `robust_pipeline.py`, `read_lane.py`,
`publish_feed.py`, `state.json`, `manifest.json` and `feed-site/feed.xml` all
md5-unchanged. Documentation-only change (`ROBUST_PIPELINE.md`, +35 non-blank
lines, 0 removals). No publication attempted. Ledger recorded under the standing
no-work key 501.

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing one into
Summerize or Read gives the pipeline work immediately — but **file into Summerize
until the preflight branch lands**, since a Read item would hit the blocker above.

## Run 028 - 2026-11-09 - fixed a latent deploy-path defect: push timeout vs auth failure

### Intake state (live Zotero read)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`: 18
unfiled parents, same keys since run 005. Produced `6P2KVFKQ`: 10 source
parents. Thirteenth consecutive run with no intake unit.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` - first command of the slice.
- Manifest status == state status for 001/002/003, all `published_and_moved`.
- Live feed md5 == local `feed-site/feed.xml` (`9fc23235`).
- Stale lock with dead owner pid 2160985, advisory lock free (normal steady
  state); cleared with `unlock --force`.
- Local HEAD == `origin/main` (`e5d06b2`) before this run's commit.

### The defect (latent, proved on real code both sides)

Run 027 proved the mandated `publish` command had never been exercised against a
reading. The same question applied to the **next** mandated command, `push` - and
it carries a hardcoded 300s `subprocess` timeout whose `TimeoutExpired` is
flattened by the broad `except Exception` into `remote deploy failed`, identical
in shape to a credential rejection. The sibling HITL tree hit this live on its
66 MB reading 501 and spent the diagnosis hunting credentials. Fixed here:
size-aware window (300s floor, 683s for a 66 MB reading), and an explicit
`timed_out` / `remote_state: indeterminate` report. Details and harness paths in
`pipeline/ROBUST_PIPELINE.md`.

Interview episodes (11-20 MB) were never at risk; a long verbatim reading is the
only class in the band, and none has shipped here - which is why three runs of
green checks never saw it. Same shape as runs 008, 013 and 027: a clean state
proves nothing about a class that needs a record no registry holds yet.

### Verification

`mm_push_timeout_repro_run028.py` 17/17, `mm_push_timeout_proof_run028.py` 32/32.
Seven gate functions byte-identical to the pre-fix file; `published*` literal set
unchanged; `py_compile pipeline/*.py` clean; `coverage` 3/3 `ok: true`;
`preflight` 001/002/003 each `ok: true`; a real `push --wait 20` against the live
repo cloned, compared and correctly no-op'd (`local feed already matches the live
site`). `feed-site/feed.xml` md5 unchanged at `9fc23235`.

### State

Code change confined to `push_to_remote()` + its CLI wiring; no gate, status
string, or feed byte moved. No publication attempted. Ledger under the standing
no-work key 501.

### Standing blocker for David, unchanged

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing one into
Summerize or Read gives the pipeline work immediately - but **file into Summerize
until the run-027 `preflight()` read branch lands**, since a Read item still hits
that blocker.

## Run 029 - 2026-11-10 - fixed the twice-escalated read-lane publication blocker

### Intake state (live Zotero read)

Summerize `V4WXTY8M`: 0 items. Read `DV6F4ILX`: 0 items. Parent `YF84AUZK`: 18
unfiled parents, same keys since run 005. Produced `6P2KVFKQ`: 10 source
parents. Fourteenth consecutive run with no intake unit.

### Drift checks (live, this run)

- `coverage` 3/3 `ok: true` - first command of the slice.
- Manifest status == state status for 001/002/003, all `published_and_moved`.
- Live feed md5 == local `feed-site/feed.xml` (`9fc23235`), before and after.
- Stale lock with dead owner pid 2201708, advisory lock free (normal steady
  state); cleared with `unlock --force`.
- Local HEAD == `origin/main` (`e4d48be`) before this run's commit.

### The defect (run 027's escalation, now closed)

Run 027 proved that a fidelity-gate-passed reading **could not ship**:
`publish_local()` routes anything not already `published` through
`preflight(require_audio=True, enforce_review=True)`, which scored readings
against interview-only rules. It failed them for *complying with the style
guide* - no Host/Rowan turns (a reading has one `**Reader:**` voice), no
fictional-correspondent disclosure and no AI-summary disclosure (both
forbidden on a verbatim reading), and a missing reviewer panel (the fidelity
gate replaces it). Worse, since run 009 `sync_durable_state()` registers a
reading in `manifest.json`, so a **bare `publish` selected it and aborted the
whole run** - one reading blocked publication of every healthy interview
episode. Run 027 declined to fix it unreviewed and inverted the standing
"prefer Read items" advice; runs 027 and 028 both carried it forward.

Fixed by giving `preflight()` a `kind == "read"` branch, selected from the
same manifest discriminator `publish_feed.py` has used since run 013.
Interviews carry no `kind` key, so anything not explicitly a reading takes the
interview path unchanged. Two helpers added: `parse_reading_turns()` (single
`**Reader:**` voice, still strict about empty turns and a script with no
reading at all) and `fidelity_gate()`, which **reads** the verdict
`read_lane.py verify` recorded in `read-episodes.json` rather than
re-implementing it, so there is one gate and one verdict that cannot disagree.

### The new branch grants nothing - this is the half that matters

A second lane in a publication gate is an unlocked door unless proved
otherwise. Every one of these is an attempt to get something through the read
branch that must not pass, and every one is refused: `verified: false`,
coverage 98% (below the 99.5% floor), a missing coverage figure, no registry
entry at all, a missing `source.txt` (verdict no longer reproducible),
Dr. Rowan Field appearing in a reading, a missing verbatim-reading or
text-to-speech disclosure, the Zotero-links disclosure absent from **both**
script and notes, a script with no `**Reader:**` turns, an empty mp3, and a
citation with no year. The read lane also keeps every shared check: audio,
citations, Zotero links, duplicate links. `kind: "READ"` in the wrong case does
**not** unlock the branch.

Nine interview gate functions are byte-identical to the pre-fix file
(`review_gate`, `parse_turns`, `verify_feed`, `source_keys`, `publish_local`,
`reconcile`, `feed_coverage`, `push_to_remote`, `status`), as is
`REQUIRED_DISCLOSURE`; `preflight()` is the only changed function.

Two harness failures in the first proof run were **harness** bugs, confirmed
before being touched, not relaxed guards: the module-level name is
`feed_coverage` (`coverage` is only a CLI subparser string, absent from both
versions), and `REQUIRED_DISCLOSURE` is satisfied by script **or** notes by
design, so the case had to strip it from both.

### Verification

`mm_read_preflight_repro_run029.py` 13/13 against the **unmodified** module
(the blocker reproduced, including a bare publish aborting 001/002/003 while
each passes individually), then 11/11 against the fixed module.
`mm_read_preflight_proof_run029.py` 34/34. `py_compile pipeline/*.py` clean.
Live: `coverage` 3/3 `ok: true`, `preflight` 001/002/003 each `ok: true` on the
`interview` lane, a real bare `publish` `ok: true`, `feed-site/feed.xml` md5
unchanged at `9fc23235`, all three `<description>` fields non-empty, no
`human-in-the-loop` substring in any GUID, `verify --remote ok: true` (200 on
the feed and notes, 206 on all three enclosures), live md5 == local.

### State

Change confined to `preflight()` plus two new helper functions; no interview
gate, status string, or feed byte moved. No publication attempted - both lanes
are empty. Ledger under the standing no-work key 501.

### Standing blocker for David, unchanged in substance

Both lanes empty; 18 on-topic items sit directly in `YF84AUZK`. Filing one into
Summerize or Read gives the pipeline work immediately. **Read is now unblocked**:
run 027's inversion is lifted, and the skill's original advice applies again -
a reading is cheaper than an interview, and `build` pulls its own PDF (run 010),
so a Read item needs nothing but the move.


## Run 030 - 2026-11-10 - read-lane number allocation could overwrite a reading

Both intake lanes empty for the **15th** consecutive run (Summerize `V4WXTY8M`
0 items, Read `DV6F4ILX` 0 items, Produced `6P2KVFKQ` 10). No production unit,
so the slice went to a durable defect per the standing rule.

### The defect

`read_lane.py next_number()` allocated from `read-episodes.json` **alone**:

```python
manifest = load_read_manifest()
used = [int(x) for x in manifest.get("episodes", {})]
return str(max(used) + 1 if used else FIRST_READ_NUMBER)
```

That registry is empty, so it returned `501` - a number `state.json` has
**already owned for 24 attempts** as this tree's standing no-work ledger key.
Since run 009 `register()` calls `sync_durable_state()`, which mirrors a reading
into `state.json` and `manifest.json`, so the read manifest is no longer the
only registry that can own a read number; allocating from it understates
occupancy.

The consequence is destructive, not cosmetic. `build()` did
`mkdir(parents=True, exist_ok=True)` and then wrote `source.txt` and `script.md`
**unconditionally**, while leaving any existing `episode-NNN.mp3` in place. So
building a second reading would overwrite the first reading's script and
extraction and keep the first reading's audio - a script/audio mismatch that the
fidelity gate **cannot** see, because it scores the new script against the new
`source.txt` written in the same breath and never against the audio's
provenance. Word coverage would read 1.0 on a feed item whose audio is a
different paper.

### The fix

1. `occupied_numbers()` (new) takes the union of every registry that can own a
   number - `read-episodes.json`, `state.json`, `manifest.json` - plus numeric
   `episodes/NNN` directories on disk. Malformed JSON and non-numeric keys are
   tolerated, not fatal.
2. `next_number()` returns the lowest free number **at or above**
   `FIRST_READ_NUMBER`, so a published interview (001-003) can never drag
   allocation into the interview block, and a gap is filled rather than appended
   past.
3. `build()` refuses an explicitly-passed `--episode` whose directory already
   holds `script.md` or `source.txt`, naming the episode, the offending files and
   a free number. `--force` (new flag, plumbed through the CLI) still permits a
   deliberate in-place rebuild. An **empty** directory is not a block, so
   `mkdir`-only leftovers cannot jam the lane.

### Verification

`mm_next_number_repro_run030.py` **16/16 against the unmodified module**: the
allocation collision, `build()` choosing 501 with `episodes/501` on disk, the
in-place overwrite of script and source, the surviving stale mp3, and the
explicit demonstration that script and `source.txt` agree with each other so the
gate's word check is blind to the mismatch.

`mm_next_number_proof_run030.py` **72/72**. Post-fix: each of the four occupancy
sources independently reserves a number (B2a-d), gap-filling (B3), empty tree
still starts at 501 (B4), interviews do not pull allocation down (B5), the
four-way union lands on 505 (B6), malformed manifest tolerated (B7), non-numeric
keys ignored (B8). Guard: occupied dir refused with a message naming episode,
files and a free alternative (C1), auto-allocation routes around it and the old
files stay intact (C2), `--force` works (C3), a half-built dir with only
`source.txt` is still protected (C4), an empty dir is not blocked (C5).
No-weakening: the **pre-fix backup still reproduces** the collision and the
overwrite (D1a-c), **26 read-lane functions byte-identical** including
`register`, `sync_durable_state`, `verify`, `render_episode`, `build_script`,
`fetch_pdf_attachment` and `dehyphenate` (D2), nine constants unchanged
including `VOICE`/`RATE`/`FIRST_READ_NUMBER` (D3), no cross-show GUID literal and
this show's `moral-machines-` prefix still present (D4).

Live, after the edit: `py_compile pipeline/*.py` clean, `next-number` now returns
**502**, `coverage` `ok: true` 3 items / 3 published with empty
`missing_from_feed` and `enclosure_issues`, `preflight` 001/002/003 each
`ok: true`, a real bare `publish` `ok: true` with the item count still 3 and
`feed-site/feed.xml` md5 **unchanged at `9fc23235`**, `verify --remote`
`ok: true` with no issues, and live feed md5 == local.

### State

Change confined to `next_number()`, `build()` and the `build` CLI parser, plus
the new `occupied_numbers()`. No gate, status string, voice, or feed byte moved.
Backup at `pipeline/read_lane.py.bak-run030`. No publication attempted - both
lanes are empty. Ledger under the standing no-work key 501.

### Standing blocker for David, unchanged

Both lanes empty; **18 on-topic items sit directly in `YF84AUZK`** with
`collections: ['YF84AUZK']` and no subcollection, invisible to both lanes.
Filing one into Summerize or Read gives the pipeline work immediately. Read is
the cheaper route and needs nothing but the move: `build` pulls its own Zotero
PDF (run 010), the publish path is lane-aware (run 013), durable state syncs
itself (run 009), `preflight` has a read branch (run 029), and allocation is now
collision-proof (this run).

## Run 031 (2026-11-10) — no intake unit (16th); reconcile() status-family fix + doc correction

Both lanes empty again: Summerize V4WXTY8M 0 items, Read DV6F4ILX 0 items,
Produced 6P2KVFKQ 10, and the same 18 items sitting unfiled directly in parent
YF84AUZK (invisible to both lanes — still the standing blocker, David's call).
Stale lock from run 030, owner pid dead, advisory lock free: normal steady state.
Spent the slice on two durable defects per the idle-lane rule.

**1. `reconcile()`'s audio-integrity check was dead for the whole published
catalogue.** It gated on the literal set `{"rendered","verified","published"}`,
which omits `published_and_moved` and `published_pending_zotero_move` — the two
documented published end states. All three shipped episodes sit at
`published_and_moved`, so an MP3 could vanish from 001/002/003 and `reconcile`
would return `ok: true` with no issue. Now tests
`status.startswith("published")`, matching `feed_coverage()`. Third instance of
the run-005 class (a status string used as a gate, tested against fewer statuses
than the docs tell you to write).

Latent, as usual: all three episodes have their audio on disk (11.6/20.2/16.6 MB),
so three `reconcile --write` passes showed 0 issues before and after. A clean
state proves nothing about this class.

Proof: `mm_reconcile_status_repro_run031.py` 15/15 against the **unmodified**
module (controls `rendered`/`published` caught; both published_* states silently
skipped at `ok: true`), `mm_reconcile_status_proof_run031.py` 45/45 (pre-fix
backup still reproduces; all five statuses now caught; grants nothing — audio
present still passes, planned/scripted/failed/blocked stay exempt, wrong-case
`PUBLISHED_AND_MOVED` does not unlock it, notes check untouched, run-008 dedupe
holds at [1,1,1]; only `reconcile` changed, 40 functions byte-identical, all
seven gates/consumers unchanged). Real registries and feed md5-asserted
throughout.

**2. ROBUST_PIPELINE.md still documented the read-lane publication blocker as
open.** 49 lines of "Open issue (escalated, latent here)" + run-027 blast radius
+ an "interim route" instructing the operator to call `publish_feed.py` directly
and **bypass the mandated `robust_pipeline.py publish`** — all obsolete since run
029 made `preflight()` lane-aware. Replaced with the resolved state: the `kind ==
"read"` branch, what it still refuses (nothing granted), the lifting of the
prefer-Summerize inversion, and the run-031 fix above. The doc was telling a
future slice to route around a gate that now works.

Verification: py_compile clean on all of pipeline/, coverage ok 3 items / 3
published, preflight 001/002/003 each ok with zero issues, read-lane
`next-number` still 502, zero `Human in the Loop` leakage in the doc, and
`feed-site/feed.xml` md5 unchanged across the whole slice.

## Run 032 (2026-11-10) — no intake unit (17th); read-lane TTS cache had no script-hash guard

Both lanes empty again: Summerize V4WXTY8M 0 items, Read DV6F4ILX 0 items,
Produced 6P2KVFKQ 10, and the same 18 items sitting unfiled directly in parent
YF84AUZK with `collections: ['YF84AUZK']` — still the standing blocker and still
David's call (lane choice decides interview-vs-verbatim treatment). Stale lock
from run 031, owner pid 2307331 dead, advisory lock free: normal steady state.
Spent the slice on a durable defect per the idle-lane rule.

**`read_lane.render_episode()` had no parts-cache invalidation, so a rebuilt
script silently shipped the previous paper's audio.** The cache at
`episodes/NNN/parts-read/NNNNN.mp3` is keyed by piece **index** only and any part
present at >=500 bytes is skipped. So after `build --force` — the sanctioned
rebuild-in-place path run 030 added — rewrites `script.md` and `source.txt` for a
different paper, a plain `render` re-synthesizes **nothing** and the episode keeps
the old paper's voice under the new paper's script, citation and notes.

The fidelity gate cannot see it, and that is the interesting part. `verify()`
compares the new `script.md` against the new `source.txt`, both written in the same
breath, so coverage reads **1.0**; the duration check uses the new word count. No
side of that comparison is the audio's provenance, and the gate's output has no
`audio_sha256`/`rendered_from` field at all. `register()` then wrote
`verified: true`, which is the only flag `publish_feed.py` consults for a reading.

This is the **run-030 lesson in a second location**: a gate that derives both sides
of its comparison from the same write validates internal consistency, not
provenance. Also a lane-asymmetry find — the interview lane in
`robust_pipeline.render_episode()` has had a `render-plan.json` / `script_sha256`
guard with stale-part deletion all along; the read lane had neither. The run-010
census closed the *line-count* port backlog, but a guard the sibling lane holds in
the **same tree** is a different axis and was not covered by it.

Fix: `render_episode()` now writes `parts-read/render-plan.json` recording
`script_sha256`, the chunk count, a hash of the chunk sequence, and the locked
`voice`/`rate`. Any mismatch — or an unreadable plan — deletes the cached parts and
forces a full re-render. The plan is written only **after** ffmpeg succeeds, so a
crashed render never leaves a trusted cache. Purely additive: `diff -u | grep -c
'^-[^-]'` = 0, and the only other change is a module-level `import hashlib`.

Proof, on real code both sides. `mm_stale_parts_repro_run032.py` 31/31 against the
**unmodified** module: paper A renders and gates clean, `build --force` to paper B
re-synthesizes 0 pieces, the audio is byte-identical to paper A's, the gate returns
`ok: true` with an empty issue list, and the record registers `verified: true` under
paper B's citation while carrying paper A's bytes. `mm_stale_parts_proof_run032.py`
39/39: the pre-fix `.bak` still reproduces; post-fix a swapped script re-synthesizes
all 6 pieces and the audio md5 moves; **resumability is preserved** (unchanged script
= 0 calls, deleting 2 parts re-makes exactly 2); the gate still bites (3s truncation
refused naming the duration, a dropped source sentence refused at 98.765% coverage,
25 injected words refused as text added, green again on revert); a corrupt plan
re-renders safely instead of raising; voice and rate changes each invalidate; locked
voice/rate still Ava at `-3%`; 30 read-lane functions byte-identical with
`verify()`/`build()`/`register()` sources unchanged; no sibling-show substring. Both
harnesses used stubbed silent-mp3 TTS (no spend) on scratch trees, and
md5-asserted the real `read-episodes.json`, `state.json`, `manifest.json` and
`feed-site/feed.xml` unchanged throughout.

Verification on live state: py_compile clean across `pipeline/`, `coverage` ok
3 items / 3 published with empty issue lists, `preflight` 001/002/003 each ok with
zero issues, `reconcile --write` ok with 0 issues, read-lane `next-number` still 502,
and `feed-site/feed.xml` md5 `9fc23235fcb49ca809059092da619b54` unchanged across the
whole slice. ROBUST_PIPELINE.md documents the guard (additive, 0 removals); the
run-031 stale-doc grep returns only the run-031 replacement prose.

## Run 033 - 2026-11-10 - readings were in no duplicate-detection map at all

Both intake lanes empty for the 18th consecutive run: Summerize `V4WXTY8M` 0
items, Read `DV6F4ILX` 0 items, and the same 18 items sitting unfiled directly
in parent `YF84AUZK` with `collections: ['YF84AUZK']`. Still the standing
blocker and still David's call, since lane choice decides interview-versus-
verbatim treatment. Stale lock from run 032, owner pid 2359084 dead and the
advisory lock free: the normal steady state. Spent the slice on a durable
defect per the idle-lane rule.

**Source-ownership/duplicate detection ignored the read lane entirely.** All
three ownership maps in `robust_pipeline.py` -- `inventory()` (-> `duplicate_sources`),
`reconcile()` (-> the "assigned to multiple episodes" issue) and `preflight()`
(-> `all_owners`) -- were built from `item.get("sources", [])`. A reading's
Zotero key is registered under **`read_source`**, deliberately, so that a paper
with both an interview and a verbatim reading is not flagged as a conflict
(run 029). The consequence nobody had written down is that readings fell out of
duplicate detection *altogether*: two readings of the **same paper** collide in
silence at all three sites.

`preflight()` was the sharpest case. Since run 029 it correctly resolves a
reading's expected key from `read_source`, then looked that key up in a map
built from `sources` -- so the owner count was 0 or 1 forever and **no number of
readings of one paper could ever trip the check**. The irony is that
`sync_durable_state()`'s own docstring says the state/manifest mirror exists so a
reading is visible to "status, the watchdog and duplicate detection"; the mirror
landed, the detection never read the field it writes.

Fix: `lane_ownership(episodes)` returns `(interview_owners, read_owners)` keyed
on the **field name** -- the same discriminator `move_verified_sources.py`
already uses -- and `duplicate_owners(*maps)` reports collisions *within* a lane.
Two interviews sharing a key is still a conflict; two readings sharing a key is
now a conflict; one interview plus one reading of the same paper stays legal.
`source_ownership` keeps its exact interview-only meaning and shape for every
existing consumer, and `read_source_ownership` is added alongside it in both the
`inventory()` and `reconcile()` reports. Purely additive in effect: the 17
removed lines are the three inline loops the helper replaces, every one of the 14
distinct strings was in the script's explicit whitelist, and no other behaviour
moved.

Proof on real code, both sides. `mm_read_ownership_repro_run033.py` 21/21
against the **unmodified** module: the collision is invisible to `inventory()`
and `reconcile()`, `source_ownership` omits the key entirely, and -- the control
that makes it a finding rather than a guess -- the *identical* collision
expressed under `sources` IS flagged by both, which proves the detector works
and the field name was the whole difference.
`mm_lane_ownership_proof_run033.py` 37/37: the pre-fix backup still reproduces;
post-fix all three sites catch it and `preflight()` on a colliding reading names
the conflict while still selecting the read lane; **nothing granted** --
interview-lane detection unchanged, cross-lane sharing still legal with the key
in both maps once each, and the read gate still refuses a missing `script.md`,
Rowan in a reading, a missing verbatim-reading disclosure, a citation with no
year, `require_audio` with no mp3, and wrong-case `kind: "READ"`; empty/null
fields tolerated; 15 untouched functions byte-identical, including
`review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local` and
`push_to_remote`.

Latent, in the now-familiar way: no reading has ever been registered in this
tree, so `reconcile --write` showed 0 issues before and after, three times
running. A clean state proves nothing about a class that needs a record no
registry holds yet -- the fourth time that sentence has been true here (runs 008,
013, 030, 031).

**The generalizable lesson: when you add a second field to express one concept,
grep every reader of the first.** This is run 030's write-side-mirror-creates-
read-side-debt lesson with the axis rotated -- run 030 was one registry of three,
this is one field of two. It also extends run 032's lane-asymmetry axis from
"does the other lane hold a guard this one lacks?" to "does shared machinery read
only one lane's field?".

Verification on live state: `py_compile` clean across `pipeline/`, `coverage`
ok with 3 items / 3 published and empty issue lists, `preflight` 001/002/003 each
`ok: true` with zero issues and lane `interview`, `reconcile --write` ok with 0
issues and an empty `read_source_ownership` three passes running, read-lane
`next-number` still 502, and `feed-site/feed.xml` md5
`9fc23235fcb49ca809059092da619b54` unchanged across the whole slice.
ROBUST_PIPELINE.md documents the fix in a new `## Source ownership is lane-aware
(run 033)` section (additive, 0 removals); the run-031 stale-doc grep returns
only run-029's replacement prose.

## Run 034 — 2026-11-10 — render-plan cache key missed a TTS input in BOTH lanes

No intake unit for the 19th consecutive slice: live Summerize (`V4WXTY8M`) and
Read (`DV6F4ILX`) both returned **0 items**, while the same **18 on-topic items
sit directly in the parent `YF84AUZK`** with `collections: ['YF84AUZK']` and no
subcollection. Neither lane reads the parent, so the queue is empty by
construction. Lane choice is David's call; not filed here. Opening state was
clean: `coverage` ok 3/3, manifest and state agree at `published_and_moved` for
001-003, read manifest empty, stale lock with a dead owner pid (2394051, the
normal steady state).

Slice spent on a durable defect, found by diffing the two lanes' render paths
rather than the two trees (run 032's lane-asymmetry axis).

**One class, three locations: a cache key that is a provenance record, missing
an input.**

1. **Read lane** — `render_episode()`'s plan recorded `script_sha256`, the chunk
   plan, `voice` and `rate`, but **not** the version of `spoken_text()`, the
   transform applied to every piece immediately before synthesis. Changing that
   transform re-synthesized **nothing**: 0 TTS calls, audio byte-identical.
   Fixed with `RENDER_TEXT_VERSION` (new constant, in the plan).
2. **Interview lane** — the plan recorded `script_sha256` and
   `render_text_version` but **not** the voices/rates used. Changing Rowan's rate
   from the locked `+18%` to `+30%` — the exact edit the documented voice-change
   procedure prescribes — re-synthesized **nothing**, and the episode shipped the
   old rate while the rewritten plan still recorded no rate, so the drift was
   unrecorded too. Fixed by hoisting the `voices`/`rates` maps above the plan
   comparison and recording them as `voices` (`<voice>@<rate>` per role).
3. **Interview lane, surfaced by the proof harness** — the plan was read with a
   bare `json.loads`, so a truncated plan (what a killed background render
   leaves) aborted every later `render NNN` with `JSONDecodeError` rather than
   rebuilding: a stuck episode only a hand-deleted file clears. The read lane has
   been tolerant since run 032. Fixed in run034b; both lanes now treat an
   unreadable plan as no plan.

**No gate can see 1 or 2.** The read lane's fidelity gate compares the new
`script.md` against the new `source.txt` (both written in the same breath, so
coverage reads 1.0) and checks duration against the new word count; the interview
lane's `preflight`/`verify_feed` check structure, disclosures, enclosure sizes
and feed shape. Neither inspects what the audio was rendered **from**, and the
plan is the only provenance record that exists — run 030/032's "a gate that
derives both sides of its comparison from the same write validates internal
consistency, not provenance", now in a third place.

Proof on real code, both sides, stubbed silent-mp3 TTS (no Edge TTS spend),
scratch trees only.
`/opt/data/tmp/mm_render_plan_key_repro_run034.py` **29/29 against the
unmodified modules**, including the per-lane **controls** that make this a
finding rather than a guess: each lane's plan *does* invalidate on the input it
*does* record (changed script re-synthesizes; unchanged script reuses the cache),
so the missing key was the whole difference, and a fresh tree at `+30%` really
does pass `+30%` to TTS.
`/opt/data/tmp/mm_render_plan_key_proof_run034.py` **41/41**: both pre-fix
backups still reproduce; post-fix a bumped transform version, a changed rate and
a changed voice each re-synthesize every piece; **resumability preserved** in
both lanes (unchanged config = 0 calls, deleting 2 parts re-makes exactly 2);
nothing weakened — the fidelity gate still refuses truncation (3s vs ~27s),
dropped source text (coverage 0.710) and injected commentary (+22 words), the
locked voices are still Ava `-3%` / Andrew `+18%` / read-lane Ava `-3%`, no
sibling-show string entered either module, and 14 read-lane + 16
interview-lane functions are byte-identical (`verify`, `build`, `register`,
`preflight`, `review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`push_to_remote`, `lane_ownership`, …).

Two harness bugs were fixed as harness bugs, not by relaxing a check — the rule
from run 029. The stub wrote to the interview lane's atomic `.tmp.<pid>` name
without `-f mp3`, so ffmpeg could not infer the container and died with exit 234
(a code-looking failure); and a fixed-length silent stub made audio
byte-identical across rates, turning a genuine cache-miss assertion into a stub
artifact — the stub now encodes voice+rate in the duration. A third failure was
real and became fix 3 above.

Verification on live state: `py_compile` clean across `pipeline/`, `coverage`
ok 3 items / 3 published with empty issue lists, `preflight` 001/002/003 each
`ok: true` with zero issues, `reconcile --write` ok with 0 issues three passes
running, read-lane `next-number` still 502, `publish` `ok: true` / 3 items,
local `verify` ok, remote `verify --remote` ok, and
`feed-site/feed.xml` md5 `9fc23235fcb49ca809059092da619b54` **unchanged across
the whole slice and byte-identical to the live feed**. Episode mp3s 001-003
md5-unchanged. ROBUST_PIPELINE.md documents the fix (additive, 0 removals); the
run-031 stale-doc grep returns only run-029's replacement prose.

## Run 035 — 2026-11-11 (no intake unit; closed a latent feed-disclosure defect)

Both intake lanes empty for the **20th consecutive run**: Summerize `V4WXTY8M` 0
items, Read `DV6F4ILX` 0 items, while **18 on-topic items remain unfiled directly
in the parent `YF84AUZK`**. Produced `6P2KVFKQ` holds 10 items (001-003's
sources). The standing blocker is unchanged and is David's call: lane choice
decides interview-vs-verbatim treatment, so the items are not filed here. A Read
item needs nothing but the move — `build` fetches its own PDF since run 010.

Stale lock from run 034's `attempt finish` cleared after both liveness checks
(owner pid 2436947 dead, advisory `flock` free) — the documented steady state.

Slice spent on a durable defect, per the standing rule for an idle queue.

**Finding: `publish_feed.py` keyed the pre-produced-audio disclosure on the
sibling show's episode numbers.** `notes_html()` branched on
`num in ('033','034')` and emitted *"Pre-recorded audio provided by David
Gagnon ... not reviewed or transcribed"* — correct in Human in the Loop, where
those are MP3s David supplied. This show numbers interviews from 001, so 033/034
are ordinary future episodes: a normal scripted, reviewed, rendered interview
would have shipped a **false provenance claim** while **losing both mandated
disclosures** (fictional-correspondent, AI-generated). Feed-only — the episode's
own notes file is correct — and invisible to every gate, since `preflight` greps
script/notes, `coverage` matches GUIDs and enclosure bytes, and `verify_feed`
touches `<content:encoded>` only to resolve `notes.md` hrefs.

Fixed by storing provenance on the record: `preproduced_episodes()` reads
manifest `preproduced: true`, and only the literal boolean unlocks the branch.
The two dead `num == '036'` filename overrides were removed in the same pass
(`interview_episodes()` already derives `episode-{num}.mp3`; HITL needed them,
this tree never did). Latent for 30+ runs and reachable in 30 episodes — a
hardcoded *number* survives every sibling-show *string* audit runs 004-010 ran.

Repro `/opt/data/tmp/mm_preproduced_repro_run035.py` **27/27 against the
unmodified module**, including the control that makes it a finding rather than a
guess: a neighbouring episode 032 built identically receives both correct
disclosures, so the number was the whole difference. Proof
`mm_preproduced_proof_run035.py` **43/43**: pre-fix backup still reproduces;
post-fix 032/033/034 all correct; nothing granted — the branch still fires on a
genuine `preproduced: true` and refuses `'yes'`, `false` and a corrupt manifest;
036 still publishes; read lane, run-013 duplicate-item guard and the
`moral-machines-` GUID prefix intact; 7 untouched functions byte-identical.
Two harness bugs fixed as harness bugs (run 029's rule), not by relaxing checks.

Verification on live state: `py_compile` clean across `pipeline/`, `coverage`
ok 3 items / 3 published with empty issue lists, `preflight` 001/002/003 each
`ok: true` with 0 issues, `reconcile --write` ok with 0 issues three passes
running, read-lane `next-number` still 502, `publish` `ok: true` / 3 items,
local `verify` ok, `verify --remote` ok, 3 `fictional composite` disclosures and
**0** `Pre-recorded audio` strings in the feed, and `feed-site/feed.xml` md5
`9fc23235fcb49ca809059092da619b54` **unchanged across the whole slice and
byte-identical to the live feed**. ROBUST_PIPELINE.md documents the fix
(additive, 0 removals); the run-031 stale-doc grep returns only run-029's
replacement prose.

## 2026-11-11 — run 036: verify_feed()'s legacy notes-exemption fired on episode 001

**No intake unit (21st consecutive).** Summerize `V4WXTY8M` 0 items, Read
`DV6F4ILX` 0 items, Produced `6P2KVFKQ` 10 items (001-003's ten source parents,
all confirmed moved). The 18 unfiled on-topic items still sit directly in the
parent collection `YF84AUZK` with no subcollection, invisible to both lanes —
still the standing blocker and still David's call, since lane choice decides
interview-vs-verbatim treatment.

Stale lock from run 035's `attempt finish` cleared after both liveness checks
(owner pid 2536639 absent from /proc, non-blocking flock acquired) — the normal
steady state.

Slice spent on a durable defect, per the "both lanes idle" rule.

**Defect.** `verify_feed()` demoted a missing `episode-NNN-notes.md` from an
issue to a warning for any item it judged legacy, keyed on the feed's
`<itunes:episode>` value being the string `"1"`. `publish_feed.py` emits
`{int(num)}`, so episode **001** always matches — and 001 is a fully gated
interview here (43 turns, three-reviewer panel passed, rendered in-pipeline,
ledger `published_and_moved`), not imported history. Net effect: 001's notes
file could vanish locally or 404 live and `verify` returned `ok: true` with an
empty issue list, which is the only thing `publish_local()` consults before
shipping. 002 and 003 were caught correctly — the detector worked; the episode
number was the whole difference.

**Fix.** Exemption now keyed on the durable ledger: `_legacy_episode_numbers()`
returns episodes at the literal status `published`, the same discriminator
`status()` uses. The `published*` family (`published_and_moved`,
`published_pending_zotero_move`) is not exempt. `_feed_item_number()` derives the
number from the GUID as `feed_coverage()` does, and `verify_feed()` now reports
`legacy_exempt_episodes` (`[]` here = healthy).

**Proof.** `/opt/data/tmp/mm_legacy_exempt_repro_run036.py` 23/23 against the
unmodified module, with the 002 control. `mm_legacy_exempt_proof_run036.py`
39/39: pre-fix backup still reproduces; post-fix 001 caught as an issue; nothing
granted (002/003 still caught, intact-feed verdict identical pre/post); a genuine
ledger `published` still exempted and named; all five of
`published_and_moved`/`published_pending_zotero_move`/`PUBLISHED`/`verified`/
`rendered` refused the waiver; only `verify_feed` changed, 42 functions
byte-identical, `preflight`/`review_gate`/`fidelity_gate`/`feed_coverage`/
`publish_local` untouched. Latent: all three notes files are present and live-200,
so the demotion was never exercised on real state.

**Validation on real state.** coverage ok 3/3; preflight 001/002/003 all ok;
`reconcile --write` 0 issues three passes (run-008 dedupe holding); verify local
ok with `legacy_exempt_episodes: []` and no warnings; verify `--remote` ok;
`publish` ok with `feed.xml` md5 `9fc23235fcb49ca809059092da619b54` **unchanged**,
3 items, every `<description>` non-empty, no `human-in-the-loop` substring in any
GUID.

Class note: this is run 035's error in a second location — an episode *number*
standing in for a property of the record. A waiver is a gate with the sign
flipped, so audit which records a branch *exempts*, not only which statuses it
accepts.

## Run 037 -- 2026-11-11 -- no intake unit (22nd); fixed the run-036 waiver's status test

Summerize `V4WXTY8M` **0 items**, Read `DV6F4ILX` **0 items**, Produced
`6P2KVFKQ` 10 items; **18 items still unfiled** directly in parent `YF84AUZK`,
invisible to both lanes. No production unit available, so the slice went to a
durable defect per the standing rule.

**Defect:** run 036 re-keyed `verify_feed()`'s missing-notes waiver onto the
ledger status literal `published` as "pre-pipeline imports", but
`publish_local()` writes that status itself and `load_ledger()`'s bootstrap maps
`published_and_moved` -> `published`. A fully gated episode was therefore
waived during the whole publish->move window, and a ledger rebuilt from the
manifest waived all three of 001-003 at once. With 001's notes file deleted,
the unmodified module returned `ok: true` / `issues: []`; the same loss at
`published_and_moved` was correctly refused (control).

**Fix:** the waiver now requires the literal status `published` **plus** no
in-pipeline production transition **plus** no `episodes/NNN/script.md` -- i.e.
positive evidence the episode was never produced here. `status()` reuses the
same helper. The exempt set can only shrink.

Repro **19/19** against the unmodified module; proof **43/43** (pre-fix backup
still reproduces, nothing granted, genuine imports still exempted and named, 49
functions byte-identical). Validation on real state: `coverage` ok 3/3,
`preflight 001-003` ok, `reconcile --write` x3 at 0/0/0 issues, `verify` local
and `--remote` both `ok: true` with `legacy_exempt_episodes: []`, `publish`
`ok: true` at 3 items with `feed-site/feed.xml` md5 **unchanged**
(`9fc23235fcb49ca809059092da619b54`), all `pipeline/*.py` compile, and no
`human-in-the-loop` substring in the feed or in `robust_pipeline.py`.
`status.healthy` stays `false` on the pre-existing 501 no-work stub only.

**Standing blocker (22nd consecutive run): the 18 unfiled items in `YF84AUZK`.**
Lane choice is David's call -- Summerize for an interview episode, Read for a
verbatim reading. A Read item needs nothing but the move; `build` pulls its own
PDF.

## Run 038 — 2026-11-11 — no intake unit (23rd); `verify_feed()` now requires a non-empty item title and description

Summerize `V4WXTY8M` and Read `DV6F4ILX` are both **empty** for the 23rd
consecutive run; the 18 on-topic items still sit unfiled directly in the parent
collection `YF84AUZK`, invisible to both lanes. Lane choice is David's call.
Stale `.pipeline.lock` from run 037 (dead pid 2744786, advisory lock free) —
the normal steady state — cleared with `unlock --force`. No production unit, so
the slice went to a durable defect per the standing rule.

**Defect:** `verify_feed()` checked an item's enclosure, GUID uniqueness, byte
lengths and notes file, but never that its `<title>` and `<description>` are
non-empty. `publish_feed.py`'s `interview_episodes()` reads both off
`pipeline/manifest.json` and defaults description to `''`, so an episode
registered without a `description` key shipped a live item with an empty
`<description>` — which is exactly how **episode 002 went out**. The skill has
carried this as a hand-check ("after any publish assert
`len(item.findtext('description')) > 0`") since 002; nothing enforced it.
`publish` returned `ok: true` and `verify_feed` returned `ok: true` with an
**empty issue list**, because every check it ran passed on a feed that was
structurally perfect and editorially blank — and `verify_feed` is the only thing
`publish_local()` consults before shipping.

**Fix:** `verify_feed()` now appends an issue per empty required field, naming
the episode and the field, with **no waiver** — an empty title or description is
wrong for a genuine import too, and run 036's lesson is that a waiver is a gate
with the sign flipped. +17 lines, 0 removals.

Repro **24/24** against the unmodified module (empty string, missing key, empty
title, and the healthy-feed control). Proof **42/42**: the pre-fix backup still
reproduces; post-fix each form is refused including whitespace-only; both fields
blank yields exactly two issues; nothing granted — the healthy-feed verdict is
**identical pre/post**, the new check has no `legacy_item`/warning branch, the
refusal holds at all four publishable statuses (`published`,
`published_and_moved`, `published_pending_zotero_move`, `rendered`) with a
control showing a non-publishable `verified` simply emits no item to gate, and
**only `verify_feed` changed** with 45 functions byte-identical
(`preflight`, `review_gate`, `fidelity_gate`, `feed_coverage`, `publish_local`,
`reconcile`, `_legacy_episode_numbers`, `lane_ownership`, `duplicate_owners`
all untouched).

Validation on real state: `coverage` ok 3/3, `preflight 001-003` ok,
`reconcile --write` x3 at 0/0/0, `publish --episode 003` ok at 3 items with
`feed-site/feed.xml` md5 **unchanged** (`9fc23235fcb49ca809059092da619b54`),
`verify` local and `--remote` both `ok: true` with `legacy_exempt_episodes: []`,
all `pipeline/*.py` compile, and no `human-in-the-loop` substring in
`robust_pipeline.py`. Harnesses `/opt/data/tmp/mm_empty_desc_repro_run038.py`
and `mm_empty_desc_proof_run038.py`.

**Harness lesson (both harnesses hit it):** two of the failures this run were
*harness* bugs, not code defects — the in-episode notes file is
`episode-notes.md` (the `episode-NNN-notes.md` form is the published name under
`feed-site/`), and asserting the refusal at ledger status `verified` false-failed
because that status is outside `interview_episodes()`'s publishable family, so
the episode is dropped from the feed and there is no item to gate. Both were
fixed in the harness; the guard was not relaxed. Confirm whether the harness or
the code is wrong before touching either.

**Standing blocker (23rd consecutive run): the 18 unfiled items in `YF84AUZK`.**
A Read item needs nothing but the move — `build` pulls its own PDF, scripts,
gates and registers on its own.

---

## Run 039 (2026-11-11) — steady state, no intake unit (24th consecutive)

**Intake reconcile (live):** Summerize `V4WXTY8M` = 0, Read `DV6F4ILX` = 0
(LMV 10280). Produced `6P2KVFKQ` = 19 (all published sources + children).
Parent `YF84AUZK` = 25 (18 unfiled bioethics / genome-editing items + 7
attachments), all dateAdded 2026-11-03, unchanged since run 005. No deletions.
Neither lane has a unit.

**Selection:** no actionable unit. The 18 unfiled items in `YF84AUZK` are the
standing blocker and are **David's call** (lane choice = interview-vs-verbatim
treatment); per the skill, do not file them. No Read item to prefer.

**Durable-defect scan:** grep of `README.md` / `style_guide.md` /
`ROBUST_PIPELINE.md` for open / escalated / deferred / blocked markers surfaced
only historical (already-fixed) references — no new logged or deferred defect.
The run-010 port census is closed and the read lane is fully exercised (runs
006-013, 029-035), so no defect was hunted this slice; the slice went to
validation.

**Validation (deterministic, final window):**
- `coverage` ok 3/3 (3 items, 3 published, no issues)
- `verify feed-site/feed.xml` local `ok: true`, 3 items, `issues: []`, `warnings: []`, `legacy_exempt_episodes: []`
- `verify --remote` (live) `ok: true`; all 3 episodes audio 206 / notes 200
- feed md5 local == live == `9fc23235fcb49ca809059092da619b54` (unchanged since the byte-stable feed; zero deploy drift)
- no `human-in-the-loop` substring in any `pipeline/*.py`
- git: local HEAD == origin/main (`2d4e8a0`); only `state.json` modified (this attempt record)

**Outcome:** no episode/reading created, rendered, or published; no gate, code,
or feed byte moved. Steady state re-confirmed (24th consecutive). Standing
blocker unchanged: 18 items unfiled in `YF84AUZK` awaiting David's lane decision.

---

## Run 041 (2026-11-12) — no intake unit (25th); `publish` could erase a published episode

**Intake reconcile (live):** Summerize `V4WXTY8M` = 0 top-level, Read
`DV6F4ILX` = 0 (library version 10642). Produced `6P2KVFKQ` = 19 (10 top-level
+ children). Parent `YF84AUZK` = 25 (18 unfiled items + 7 attachments),
unchanged since run 005. The library version moved 10280 -> 10642 since run
039, but every changed item belongs to unrelated Field Day collections
(`collections: None`); 149 deletions, none in this show's lanes. Neither lane
has a unit.

**Selection:** no actionable unit, so the slice went to a durable defect per
the standing rule. The 18 unfiled items in `YF84AUZK` remain the standing
blocker and are **David's call** (lane choice = interview-vs-verbatim
treatment).

**Stale lock:** owner pid 158814 from run 040's own `attempt finish`; `/proc`
absent and a non-blocking `flock` succeeded, so `unlock --force`. Normal steady
state, not an overlapping run.

**Defect found and fixed: `publish_local()` could not see an ERASED episode.**

`publish_local()` built the feed, validated it with `verify_feed()` and
transitioned the ledger. `verify_feed()` iterates the items the feed
**contains**, so it is structurally unable to notice one that is gone. The feed
is rebuilt from `manifest.json` + ledger status each publish, so anything that
drops an episode out of `interview_episodes()` erases a **live** episode while
`publish` returns `ok: true` with an empty issue list. Two reachable routes,
both proved on real code with 001-003: a lost `manifest.json` entry (also
`publish_local()`'s selection source, so the episode is not even preflighted),
and a status moved outside the `published*` family.

The detector already existed — `feed_coverage()` — but was read-only, CLI-only
and **referenced nowhere in the publish path**, so the documented "run
`coverage` first every slice" habit would only catch the erasure on the *next*
slice, after a push had already taken the episode off the live feed.
`publish_local()` now asserts it after `verify_feed()` and **before any ledger
transition**, reported under a `coverage` key beside `verification`.

Nothing granted: a `verify_feed` failure still refuses first with its own
message, a `planned` episode is still not owed an item, both lane selectors are
unchanged, and only `publish_local` differs (47 functions byte-identical).

**Class:** the erasure half of run 005's silent-skip family. Runs 005/013/031
each fixed a selector that wrongly dropped a record; nothing had ever asked
whether the resulting feed was *missing* something. A check that validates what
is present cannot validate what is absent.

**Harness lessons (both harnesses failed first; neither was a code defect):**
- Deleting `feed-site/episode-NNN-notes.md` does not simulate a `verify_feed`
  defect — `publish_feed.main()` re-copies notes and audio from `episodes/NNN/`
  every run, repairing it before the gate looks. Use a defect publish cannot
  self-heal (a missing manifest `description`, the run-038 gate).
- `feed_coverage()` unions the published set from **both** `state.json` and
  `manifest.json`, so it catches the status-route erasure too; expecting it to
  be blind there was a harness bug. The detector is stricter than assumed,
  which sharpens the finding rather than softening it.
- The first edit attached coverage to `verify_feed()`'s own return dict,
  surfacing it as `verification.coverage` and mutating another check's verdict.
  Corrected to a top-level `coverage` key.

**Validation (deterministic, final window):**
- repro `mm_publish_erasure_repro_run041.py` **29/29** against the unmodified module
- proof `mm_publish_erasure_proof_run041.py` **39/39**, exit 0
- `py_compile` clean on all `pipeline/*.py`
- real `publish --episode 001 002 003`: `ok: true`, `coverage ok: true` 3/3, `verification ok: true`
- `coverage` ok 3/3; `verify` local `ok: true`, `issues: []`, `warnings: []`, `legacy_exempt_episodes: []`
- `verify --remote` live `ok: true`; 3x audio 206, 3x notes 200
- `feed.xml` md5 local == live == `9fc23235fcb49ca809059092da619b54` (unchanged; zero deploy drift)
- `manifest.json` md5 unchanged; no sibling-show GUID substring in any `pipeline/*.py`

**Outcome:** no episode or reading created, rendered or published. One latent
publication-path defect closed with the feed byte-identical. Standing blocker
unchanged: 18 items unfiled in `YF84AUZK` awaiting David's lane decision.

## 2026-11-12T14:08Z — run 043 (interview lane: reconcile stopped deleting audio provenance)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; 18 items still
unfiled in parent YF84AUZK, David's call). `coverage` ok 3/3, `verify` ok with
no issues, live feed byte-identical to local. No production unit available, so
the slice closed a latent defect.

**Defect.** `render_episode()` records the rendered audio's provenance into the
ledger as `artifacts.audio_sha256` plus the turn count. `reconcile()` rebuilt a
`{notes, audio}` dict from disk and assigned it over the top, so
`reconcile --write` -- which runs every slice -- destroyed both on the first
pass after any render. Permanent and silent: nothing re-derives them and
reconcile still returned `ok: true`. The live tree proved it, not a fixture:
001/002/003 each show a `rendering -> rendered` transition reading "atomic
render complete" beside `artifacts` holding only `{audio, notes}`.

This is run 042's class with the sign flipped -- there the read lane stored a
digest no gate read; here the interview lane stored one another function
deleted.

**Fix.** `reconcile()` now merges the disk-derived fields into the existing
artifact dict, and (same slice, per run 042's lesson) re-hashes the audio and
refuses a mismatch naming both digests. An absent digest stays silent by
design: 001-003 had already lost theirs, so refusing them would be a false
failure and waiving them would be a gate with the sign flipped. Their digests
were backfilled on evidence -- in-pipeline render transition, episode-dir and
feed-site audio byte-identical at the advertised enclosure length, local feed
byte-identical to live, `preflight --audio` ok with a matching digest.

Backups `robust_pipeline.py.bak-run043`, `state.json.bak-run043`,
`ROBUST_PIPELINE.md.bak-run043`. Exactly one function changed, 48
byte-identical including `preflight`, `review_gate`, `fidelity_gate`,
`verify_feed`, `feed_coverage` and `publish_local`. `feed-site/feed.xml`
md5-unchanged throughout; three post-fix `reconcile --write` passes clean with
the digests surviving.

Also updated the now-stale `ROBUST_PIPELINE.md` passage asserting the interview
lane relies on `parts/render-plan.json` as its only provenance record.

Proof: repro 28/28 against unmodified code, fix proof 39/39 including
pre-fix-still-reproduces and seven nothing-granted refusals. Two harness bugs
failed first and neither was a code defect (run 029's lesson): the repro's
fixture lacked the real `REQUIRED_DISCLOSURE`, and the backfill's shallow
`dict()` snapshot shared the transitions list so the integrity assertion
false-failed before writing anything.

## 2026-11-12T18:30Z — run 044 (publish gate kept its own copy of the legacy waiver)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; 18 items still
unfiled in parent YF84AUZK, David's call). Opening `coverage` ok 3/3, `verify`
ok with no issues, live feed byte-identical to local, stale lock with dead pid
663121 (normal steady state, cleared with `unlock --force`). No production unit
available, so the slice closed a latent defect.

**Defect.** `publish_local()` -- the publication gate -- skipped `preflight`
entirely for any episode at the ledger status literal `published`:

    if record.get("status") != "published":
        check = preflight(number, require_audio=True, enforce_review=True)

That waived the three-reviewer gate, both spoken disclosures, the Zotero-links
disclosure, every citation check and the audio check together. Runs 036 and 037
had already established that this literal does not mean "imported history" --
`publish_local()` writes it itself (verified -> published), and the
`load_ledger()` bootstrap maps `published_and_moved` -> `published`, waiving the
whole catalogue whenever the ledger is rebuilt -- and run 037 replaced the test
with the three-part `_legacy_episode_numbers()`. But `publish_local()` was never
calling that helper; it carried a separate inline copy of the discarded test.
Run 037's own proof records `publish_local` among its byte-identical functions.

Worse than a skipped check: `publish_feed.main()` re-copies each episode's notes
and audio to `feed-site/` every run, so a corrupted deliverable is actively
propagated to what the next `push` deploys. Proved on real code -- substituted
notes reached `feed-site/episode-001-notes.md` and 001's audio swapped for 002's
was accepted -- with `publish`, `verify_feed` and `feed_coverage` all ok.

**Fix.** Deleted the inline copy; `publish_local()` now defers to
`_legacy_episode_numbers()`. That set can only be narrower than the status
literal, so the change adds refusals and grants nothing.

**Validation (deterministic, final window):**
- repro `mm_publish_waiver_repro_run044.py` **37/37** against the unmodified module
- proof `mm_publish_waiver_proof_run044.py` **51/51**, exit 0
- `py_compile` clean on all `pipeline/*.py`
- real bare `publish`: `ok: true`, all three episodes **preflighted** (none
  waived) and all passing, `verification ok`, `coverage ok` 3/3
- `coverage` ok 3/3; `verify` local ok, `issues: []`, `legacy_exempt_episodes: []`
- `verify --remote` live ok
- `feed.xml` md5 local == live == `9fc23235fcb49ca809059092da619b54` (unchanged)
- 3x `reconcile --write` clean, 0 stored errors on every episode
- exactly one function changed, 48 byte-identical incl. `preflight`,
  `review_gate`, `fidelity_gate`, `verify_feed`, `feed_coverage`,
  `_legacy_episode_numbers`, `reconcile`, `push_to_remote`

Backups `robust_pipeline.py.bak-run044`, `ROBUST_PIPELINE.md.bak-run044`,
`production-log.md.bak-run044`. Two harness bugs failed first and neither was a
code defect (run 029's lesson): deleting `episode-notes.md` made `publish` die
in `publish_feed`'s copy step rather than at the gate, and a synthetic legacy
fixture is refused by run 041's coverage assertion -- the pre-fix module raises
identically, which is what proves no regression.

**Lesson.** A fix is not finished while a second copy of the defect is still
inline elsewhere: centralizing a predicate into a helper is only half the job,
the open-coded duplicates must be migrated to it. And a byte-identical function
in a no-weakening proof is evidence of scope, not of correctness -- when a proof
names a gate as unchanged, ask whether it should have changed.

**Outcome:** no episode or reading created, rendered or published. One latent
publication-gate defect closed with the feed byte-identical. Standing blocker
unchanged: 18 items unfiled in `YF84AUZK` awaiting David's lane decision.


## 2026-11-12 — run 045: the interview publication gate hashed the audio and compared it to nothing

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same 18 on-topic sources still sit directly in `YF84AUZK` with
`collections: ['YF84AUZK']` and no subcollection, so neither lane reads them.
Produced `6P2KVFKQ` holds 10 parents (001-003's sources, all moved). No
production unit available, so the slice closed a latent defect. Opening
`coverage` was `ok: true`, 3 items / 3 published, no issues; manifest and state
agree at `published_and_moved` for 001-003; stale lock with dead owner pid
806998 (normal steady state, advisory `flock` free, cleared with
`unlock --force`).

**Defect.** `preflight()` is the interview lane's deterministic publication gate
and the only episode-level check `publish_local()` runs. With `require_audio`
it computed `sha256(audio[0])`, stored it in `checks.audio.sha256`, and compared
it to **nothing**:

    result["checks"]["audio"] = {"path": ..., "size": ..., "sha256": sha256(audio[0])}

Every other check in that function scores `script.md` and `episode-notes.md` —
the three-reviewer panel, both spoken disclosures, the citation and
evidence-boundary checks — and none of them can tell which episode's audio sits
in the directory. The reader existed in the wrong place: `render_episode()`
records the rendered bytes' digest at `state.json` -> `artifacts.audio_sha256`
and `reconcile()` compares it (run 043 restored that field), but `reconcile` is
**not in the publish path**. `publish_local()` runs `preflight`, `verify_feed`
and `feed_coverage`; the latter two inspect feed *structure*.

Proved on real code with 001's mp3 replaced by 002's: pre-fix `preflight`
returned `ok: true` with `issues: []`, the real `publish --episode 001` exited 0
reporting `ok: true`, and the swapped bytes reached
`feed-site/episode-001.mp3` — what the next `push` deploys — while `reconcile`
on the identical tree returned `ok: false` naming the digest mismatch. That
control is what makes this a finding rather than a guess: the detector worked
and the gate never called it.

**Fix.** `preflight` now compares the computed digest against the recorded one
and reports both in `checks.audio`. It grants nothing: an **absent** digest
stays acceptable (001-003 lost theirs once to the run-043 bug and are genuinely
published, so refusing a pre-provenance record would be a false failure — the
same policy `reconcile()` applies), and only a digest that is present and wrong
is refused.

**Validation (deterministic, final window):**
- repro `mm_interview_provenance_repro_run045.py` **26/26** against the
  **unmodified** module (incl. the `reconcile` control and the
  propagation-to-`feed-site` step)
- proof `mm_interview_provenance_proof_run045.py` **50/50**, exit 0
- `py_compile` clean on all `pipeline/*.py`
- real `preflight NNN --audio` for 001/002/003: `ok: true`, `issues: []`,
  computed digest == recorded digest on all three
- real bare `publish`: `ok: true`, all **3** episodes preflighted (none waived),
  all provenance-bound, `verification ok`, `coverage ok`
- `coverage` ok, 3 items / 3 published; `verify` local ok, `issues: []`,
  `legacy_exempt_episodes: []`, no warnings; `verify --remote` live ok
- `feed.xml` md5 local == live == `9fc23235fcb49ca809059092da619b54` (unchanged
  across the whole slice), `grep -c '<item>'` = 3
- 3x `reconcile --write` clean, 0 stored errors on every episode (run-008
  dedupe holding)
- exactly **one** function changed; 47 byte-identical incl. `reconcile`,
  `publish_local`, `verify_feed`, `feed_coverage`, `review_gate`,
  `fidelity_gate`, `render_episode`, `_legacy_episode_numbers`,
  `lane_ownership`, `push_to_remote`, `status`, `watchdog`
- docs: `ROBUST_PIPELINE.md` preflight contract now states the provenance
  clause, plus a dated run-045 section; additive apart from the one reworded
  contract line

Backups `robust_pipeline.py.bak-run045`, `ROBUST_PIPELINE.md.bak-run045`,
`production-log.md.bak-run045`.

**Harness bugs, neither a code defect** (run 029's rule, twice): `publish`
prints a human summary line before its JSON so `json.loads(stdout)` raises —
parse from the first brace; and `publish --episode NNN` selects **one** episode,
so asserting three preflights needs a **bare** `publish`. A scratch tree also
lands on another filesystem, so `os.link` fails with `EXDEV` — symlink the mp3s
(`stat()` and `read()` follow the link, so size and sha256 are the real ones).

**Lesson.** This is run 042's fix, which landed in the **read lane only**: run
040 stored a reading's `audio_sha256` with no reader and run 042 wired
`fidelity_gate()` to it, but the interview lane's identically-shaped gate was
never revisited *because its digest did have a reader* — just not one on the
publish path. So a field with a reader is not a field with a gate, and run 032's
lane-asymmetry axis extends again: ask whether this lane's reader is reachable
from **the command the operator runs to ship**, not merely whether a reader
exists somewhere in the file.

**Outcome:** no episode or reading created, rendered or published. One latent
publication-gate defect closed with the feed byte-identical and the live site
unchanged. Standing blocker unchanged: 18 items unfiled in `YF84AUZK` awaiting
David's lane decision (Summerize = interview, Read = verbatim reading).

## 2026-11-13T02:5xZ — run 046 (read-lane audio provenance reaches reconcile)

Both intake lanes empty (Summerize V4WXTY8M 0, Read DV6F4ILX 0; 18 items still
unfiled in the parent YF84AUZK, David's lane call -- unchanged, not re-raised).
`coverage` ok 3/3, `verify` ok with no issues, three `reconcile --write` passes
at 0/0/0, preflight 001-003 ok. Root and `feed-site/` copies byte-identical for
all nine deployed files. Stale lock owner pid 962084 dead and the advisory lock
free -- the normal steady state. No production unit, so the slice closed a
latent defect.

**Defect.** `read_lane.sync_durable_state()` mirrored a reading's text artifacts
(`script`, `notes`, `source_pdf`) into `state.json` and omitted the audio.
`reconcile()` gates on `artifacts.audio_sha256`, so the catalogue's
post-publication audio-swap detector was structurally dead for every reading --
while catching the identical swap in the interview lane, where
`render_episode()` writes that field. The digest already existed in
`read-episodes.json` (run 040); it never reached the registry `reconcile()`
reads.

Distinct from run 042: `fidelity_gate()` covers the publish path, `reconcile()`
is the out-of-band audit for a swap that happens *after* publication, which no
publish-path gate re-runs.

**Fix.** Mirror `audio_sha256`, the audio path and `audio_bytes` from the record
the caller already passes in, only when present. Backup
`read_lane.py.bak-run046`; purely additive (0 removals in a unified diff),
exactly one function changed with 32 byte-identical and `robust_pipeline.py`
untouched. Live registries and feed.xml md5-unchanged throughout. Also appended
the ROBUST_PIPELINE.md section so the doc does not outlive the fix (run 031).

Proof: repro 23/23 against unmodified code **with an interview-lane control**
proving the detector works and the absent mirror field was the whole
difference; fix proof 45/45 including pre-fix-still-reproduces, ledger
persistence de-duplicated across three write passes, and eight nothing-granted
refusals. Two harness bugs fixed rather than the guards: the fixture must use
the exact `robust_pipeline.REQUIRED_DISCLOSURE` constant, and word-fidelity
tampering is `read_lane.verify()`'s scope, not `fidelity_gate()`'s.


## 2026-11-13 — run 047: the quoted-span gate, and the misquote it found in a published episode

**Queue.** Summerize `V4WXTY8M` **0** items, Read `DV6F4ILX` **0** items; the
same 18 on-topic sources still sit directly in `YF84AUZK` with
`collections: ['YF84AUZK']` and no subcollection, so neither lane reads them.
Produced `6P2KVFKQ` holds 10 parents (001-003's sources, all moved). No
production unit, so the slice closed a durable gap. Opening `coverage` ok 3/3,
`verify` ok with no issues, `reconcile` ok, manifest and state agree at
`published_and_moved` for 001-003. Stale lock owner pid 1121613 dead with the
advisory lock free -- the normal steady state, cleared with `unlock --force`.
Standing blocker unchanged and **not re-raised** (David's lane call).

**Gap.** The sibling tree has `pipeline/quoted_span_gate.py` (its run 488) and
this tree had **no equivalent at all**. It is a file created *after* this tree's
clone date, so the run-009/010 line-count port census -- which compares the five
shared modules and was correctly closed -- could not have surfaced it. A census
over files that exist on both sides is blind to a file that exists on only one.

The gate asserts every `"..."` span in a deliverable appears in the episode's
extracted source text. Nothing in this pipeline had ever checked that: the
three-reviewer panel and `preflight()` both read the script against the
**citation record** (keys, numbered entries, years, Zotero links), never against
the **source text**. So a misquote inside quotation marks was invisible to every
gate the show had.

**Porting the tool was half the job.** It ran and immediately died with
`FileNotFoundError: episodes/003/source-EIUADNKU.txt` -- no interview episode in
this tree has ever retained its extracted source text, so the gate was unusable
the moment it landed. That is run 010's lesson applied to an imported tool:
check that each stage's **inputs are obtainable by the actor that will run it**,
not merely that the stage works. Re-fetched all 10 source parents from Zotero
(`items/<key>/children` -> `items/<attachkey>/file`, extracted with the sibling
venv's `pypdf` 6.21.2): **9 of 10** succeeded. `EIUADNKU` (003's only source)
has **no stored PDF attachment**, consistent with this log's own record that it
was read as the arXiv preprint `1803.07170v2`, so 003's six script spans and
eleven notes spans remain unverifiable until a PDF is attached.

**What it found on first real use: a genuine misquote in published episode 001.**
Five source-0 hits across 001/002 (45 spans in the catalogue). Four are the
benign classes the sibling skill documents -- the Host's own rhetorical framing
(`"most people feel this way"` -> `"the machine shall do this"`), a dismissive
paraphrase the script itself coins (`"aggregation is hard."`), and a
bibliographic title the notes quote in their own reference list. The fifth is
the blocking **author-attributed** class:

    source (Awad/Bonnefon 4UDPRQZR): "...was considered a good ALGORITHM for
                                      other people to have (median budget
                                      share = 50)"
    episode 001 script.md:           fifty for "good for other people to have"

A word dropped inside quotation marks -- the sibling's run-474 class -- on an
episode that passed a three-reviewer panel and every deterministic gate, and is
live. Corrected to the source's exact words (`being "a good algorithm for other
people to have"`). Script-only by **evidence**: a per-file count table showed
script 1 / notes 0 before the edit, so the notes were never touched on
assumption (the script-only-residual class runs in both directions). The edit
changed exactly one line by exactly the intended substitution, asserted before
writing.

Diagnostic note worth keeping: a shell `grep -o -E ".{70}moral.{70}"` over the
source files returned **zero** hits for `moral` while Python counted 47 in the
same file -- the shell probe was the artifact. When a probe returns an
implausible zero, check the probe against a control term in a second tool before
concluding anything about the data. Then ran the skill's mandated alnum-fold
diagnostic: `alnum-present: False` for all three 001 spans, which is what
distinguishes a real absence from a normalization gap.

**Copyright catch.** The 9 extracted files are verbatim copyrighted paper text
and this repository is **public**; `git status` showed them as untracked and
`git check-ignore` confirmed they were **not** ignored, i.e. one `git add -A`
from publication. Added `source-*.txt` to `.gitignore` with a comment saying why
and how to regenerate them. They are regenerable verification inputs, not
deliverables.

**Validation (deterministic, final window):**
- `pipeline/quoted_span_gate.py` md5 **identical** to the sibling's, 0
  sibling-show references (the module is show-agnostic, so no retargeting was
  needed -- asserted rather than assumed, per run 009)
- `tests/` created (this tree had none): **23/23 OK** -- 20 ported + 3 new
  regression tests pinning the real ep-001 span
- tests proven **load-bearing** both ways: crippling the module to its pre-488
  shape (no `alnum` fallback, 2 views) fails **5**; disabling detection
  entirely fails **9**; restored module md5-identical with 23/23 green
- 001 and 002 now exit **0** with only the benign spans whitelisted; 001 went
  10 spans / 3 unverified -> 10 / **0**
- `preflight NNN --audio` ok with `issues: []` for **all three** episodes after
  the script edit
- `coverage` ok 3/3; `verify` ok, `issues: []`, `legacy_exempt_episodes: []`;
  `reconcile` ok
- `feed.xml` md5 `9fc23235fcb49ca809059092da619b54`, **unchanged** across the
  whole slice; `grep -c '<item>'` = 3
- `py_compile` clean on all `pipeline/*.py`
- both appends additive: 0 removals in a unified diff (tests, ROBUST_PIPELINE.md)

Backups `tests/test_quoted_span_gate.py.bak-run047`,
`episodes/001/script.md.bak-run047`, `ROBUST_PIPELINE.md.bak-run047`,
`.gitignore.bak-run047`, `production-log.md.bak-run047`.

**Audio provenance.** The 001 script edit means `script.md` no longer matches
the rendered mp3 word-for-word (a single word inside one quotation). The audio
is NOT re-rendered: the interview lane has no script-hash gate (`render-plan.json`
records the chunk sequence, not a script digest), `reconcile()` compares the
audio digest to the recorded one and still passes, and re-rendering would change
the live enclosure for a one-word correction. The correct deliverable is the
text; logged here so a future slice does not read the divergence as a defect.

**Lesson.** A port census over files that exist on **both** sides cannot find a
file that exists on only one -- run 010 closed the line-count backlog correctly
and this gap sat outside it. And the deeper one: every gate this show had scores
the deliverables against each other or against the citation record, so none of
them could see fidelity to the paper's actual words. When a gate passes, ask
which artifact it never looked at -- here, for 45 spans across three published
episodes, the answer was the source text itself.

**Outcome:** no episode or reading created, rendered or published. One durable
verification gap closed, one real misquote corrected in a published episode, and
a copyright exposure caught before any commit. Feed byte-identical, live site
unchanged. Standing blocker unchanged: 18 items unfiled in `YF84AUZK` awaiting
David's lane decision (Summerize = interview, Read = verbatim reading).
