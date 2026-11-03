# Moral Machines - production log

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
