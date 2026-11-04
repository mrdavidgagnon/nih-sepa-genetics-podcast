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
