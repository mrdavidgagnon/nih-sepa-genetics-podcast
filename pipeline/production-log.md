# Production log

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
