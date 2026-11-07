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
