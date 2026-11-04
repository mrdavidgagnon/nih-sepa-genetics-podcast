# Human in the Loop: Moral Machine Edition — NIH SEPA Podcast

Repository: `mrdavidgagnon/nih-sepa-genetics-podcast`
Feed: `https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/feed.xml`

This project turns research in the **2026 NIH SEPA** Zotero collection into a
private, playful audio review — same pipeline and same two-person interview
format as *Human in the Loop*, pointed at a different library and a different
feed. The two shows are fully independent: separate trees, separate ledgers,
separate episode numbering, separate GitHub repos.

Pipeline tree: `/data/.openclaw/workspace/media/sepa-genetics-podcast/`

## Episode production contract

These requirements apply to every article included in an episode, without
exception:

1. Verify the bibliographic metadata against Zotero and, when available, the
   publisher or DOI record before scripting.
2. Cite the article in the spoken episode with every author name, the complete
   article title, the journal or other publication venue, and the publication
   year. Do not shorten an author list to "et al." in this citation.
3. Give the same complete citation in the show notes. Each show-notes entry must
   include a direct link to the Zotero item when the listener has been granted
   access. A DOI or publisher link may be included as an additional public link,
   but it does not replace the Zotero link.
4. Tell listeners in every episode: "The complete citations are in the show
   notes, with links to the Zotero files when you have been granted access."
5. Before rendering or publishing, check the script and notes article by
   article. An episode is not ready if a source is merely named, if any author
   is omitted, or if the title, venue, year, or access-appropriate Zotero link
   is missing.

The spoken citation can appear when an article is introduced or in a dedicated
source segment. Clarity matters more than citation-style punctuation; all five
bibliographic elements must be audible.

## Zotero collections (group library `2412036`, parent `YF84AUZK` "2026 NIH SEPA")

- **Summerize** (`V4WXTY8M`) — two-voice interview episodes. The production
  contract above applies in full. Episodes numbered from **001**.
- **Read** (`DV6F4ILX`) — single-voice verbatim readings of one work, built by
  `pipeline/read_lane.py` and numbered from **501**. The episode-production
  contract above is written for interview episodes; readings follow the
  Read-lane rules in `style_guide.md` instead (body text only, no paraphrase,
  fidelity gate rather than reviewer panel, no Dr. Rowan Field).
- **Produced** (`6P2KVFKQ`) — the sink. `pipeline/move_verified_sources.py`
  moves sources here after publication checks pass. Never delete items.

Read-lane commands:

```
pipeline/read_lane.py zotero-read                      # what is waiting in Read
pipeline/read_lane.py build --item KEY --pdf PATH      # extract + script + notes + gate
pipeline/read_lane.py render --episode 501             # single-voice TTS
pipeline/read_lane.py verify --episode 501             # fidelity gate (exit 1 = fail)
```

## Robust production tooling

Use [pipeline/ROBUST_PIPELINE.md](pipeline/ROBUST_PIPELINE.md) and
`pipeline/robust_pipeline.py` for all production work. The wrapper keeps a
durable ledger and inventory, serializes mutating operations with a lock,
requires the three-reviewer gate, performs deterministic preflight checks,
resumes rendering from valid parts with atomic outputs, and verifies local or
explicitly requested remote feed/audio/notes checks.

```sh
python3 pipeline/robust_pipeline.py status
python3 pipeline/robust_pipeline.py preflight NNN
python3 pipeline/robust_pipeline.py render --episode NNN
python3 pipeline/robust_pipeline.py verify feed-site/feed.xml
python3 pipeline/robust_pipeline.py publish --episode NNN
python3 pipeline/robust_pipeline.py push --episode NNN
```

## Inherited traps (same code, same bugs)

This tree is a clone of the Human in the Loop pipeline, so every known trap in
that pipeline applies here verbatim. The important ones:

- **`publish_feed.py` builds the feed from a hardcoded `EP` list**, not from
  `manifest.json`. A new episode missing from `EP` is silently skipped and
  `publish --episode NNN` still returns `ok: true`. Append a tuple for every new
  interview episode:
  `('NNN','Title','episode-NNN.mp3','description','episode-NNN-slug','episode-NNN')`
  The `EP` list in this tree starts **empty**.
- **`read_lane.py` never writes `state.json`/`manifest.json`.** After a reading
  is built, rendered, verified and published, write the bookkeeping yourself.
- **`state.json` per-episode `errors` lists are append-only** and never
  self-clear. A stale error is not evidence of a current problem; check disk.
- **`pipeline/.pipeline.lock` is not unlinked on release.** A lock file present
  with `lock.active: false` is the normal steady state, not an active run.
- **`preflight()` scores readings against interview-only rules** and will report
  three issues for every compliant reading. Defer to the fidelity gate.
- **`verify` takes the feed as a positional arg** — there is no `--feed` flag.
- Push with `background=true`; readings can exceed the 300s push timeout, and a
  timed-out push means *unknown*, not failed — check `git ls-remote` first.

## Deploy

GitHub Pages on branch `main` of `mrdavidgagnon/nih-sepa-genetics-podcast`.
Token: `GITHUB_PODCAST_TOKEN` in `/opt/data/.env` (shared with the HITL feed;
same account, `repo` scope). Pages lags a push by 1–3 minutes.
