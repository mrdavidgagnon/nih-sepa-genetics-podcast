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
