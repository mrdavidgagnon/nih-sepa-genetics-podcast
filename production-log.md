# Human in the Loop: Moral Machine Edition - production log

Cloned from the Human in the Loop pipeline 2026-11-03. Episodes numbered from 001; readings from 501.

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
