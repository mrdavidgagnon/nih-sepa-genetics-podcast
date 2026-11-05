# Episode 003 — reviewer findings (round 1, 2026-11-05)

NOT the review-panel.md gate file. These are the raw round-1 findings from three
independent reviewers run against the extracted full text of arXiv:1803.07170v2.
Two reviewers returned FAIL. Revisions below MUST be applied to script.md (and
episode-notes.md where noted) before a gate-compliant review-panel.md is built.

Gate reminder: one `**Final verdict: PASS.**` line per reviewer and nothing else
matching `verdict:` — an Initial/Post-revision pair yields 5 matches for 3
reviewers and fails review_gate. Revision history goes in prose.

## Reviewer 1 — fact-checker — PASS with 2 required precision fixes

All 18 quantitative claims reconcile against the preprint: Table 1 coefficients
(63.347, 56.011, 17.321, 13.268; non-significant Human terms in Bad Intervention
and in study 3 Missed Intervention), Ns 786/382/586, observations
3,144/1,528/4,688, the three exclusion filters incl. the 169-character
transcription, cell means (68.02 -> 57.22; 53.45; 75.56 -> 59.50 and 48.51;
53.36 vs 49.78 at p=.1014), the competence null, residual blame on uninvolved
parties, the Guardian Angel reversal, and the under-reaction/crashworthiness
argument. Published citation independently confirmed via Crossref: Nature Human
Behaviour vol 4, issue 2, pp. 134-143, online 28 Oct 2019, eight authors in
order. Preprint-version disclosure judged accurate and sufficient.

R1-FIX-1 (study 3 Mistake coefficient). Script says the "made a mistake"
coefficient is "enormous and overwhelmingly significant in all three studies —
sixty-three points ... fifty-six in study two." Study 3's Mistake coefficient is
11.645 (SE 0.939) — significant but an order of magnitude smaller, because the
dilemma framing compresses the scale. Reword to: large and significant in all
three, much larger in studies one and two (sixty-three and fifty-six), with a
smaller but still significant eleven points in the dilemma study.

R1-FIX-2 (Guardian Angel scope). Script calls it "the only case in the whole
paper where the machine side gets more blame than the human." The authors' claim
is scoped to shared control ("the only cases we identified where the car
receives more blame than the human"); supplemental tables show Industry > User
in the fully autonomous car too (study 2 BI 80.61 vs 29.58; study 3 MI 35.50 vs
19.08), where the human is a passenger. Add "of the shared-control cars" / "where
a human is actually a driver."

R1-OPTIONAL: "the authors put that front and centre" overstates placement — the
study-3 null is parenthetical in Results, developed in Discussion, absent from
the abstract. "They state it plainly rather than burying it" is exact.

R1 could not re-check the published abstract (paywalled); Rowan's hedged aside
that it points the same direction rests on the earlier research pass.

## Reviewer 2 — evidence boundaries — FAIL, 3 blocking

R2-BLOCK-1 (closing mechanism asserted as fact — most serious). Script closes:
"...not because it seems incompetent, and not because people are soft on
software generally, but because a human in the loop is available to absorb it."
Both negatives are supported. The positive is a causal mechanism the paper
expressly disclaims: "the reason that subjects blame machine drivers less than
human drivers in Missed Intervention cases remains an open question," and the
authors' own candidate explanation is different (uncertainty about machines'
agential status). The measured contrast — that the presence of a human partner
moves the rating — IS supported; "absorbs" imports an untested conserved-quantity
model of blame. Replace with the measured contrast plus an explicit
open-question flag. Apply the same hedge to "absorbs" at the two earlier turns
("the human's presence is associated with lower machine blame").

R2-BLOCK-2 (liability claim from blame ratings). "a human in the supervisory
seat functions, among other things, as liability insulation for the system
around them" — factive verb plus a legal category, from 0-100 blameworthiness
and causal-responsibility ratings. No liability, legal-exposure or insurance
variable was measured. The authors only forecast ("we expect that juries will be
biased to absolve the car manufacturer"). Re-mark as the script's inference
extending the authors' expectation, and state that no liability outcome was
measured.

R2-BLOCK-3 (boundary list misattribution — the panel's core failure mode, and it
runs in the direction of flattering the paper). Script: "Four things, and three
of them are the authors'." Only study 3's null is the authors'. The authors never
raise the US-only/MTurk sampling limit ("USA residents" appears only as a neutral
methods descriptor; their sole generalisability caveat concerns other domains,
not other countries), and on vignettes they argue the OPPOSITE: "while we
employed stylized, simplified vignettes in our research, our findings show
external validity." Rewrite as: "Four things. One of them is the authors' —
study three. The other three are mine." Optionally add that the authors' external
-validity argument rests on convergence with a single news cycle.

R2-FIX-4 (study 3 handling). (a) "the authors put that front and centre rather
than burying it" is not supportable (parenthetical in Results, absent from
abstract, Figure 2 plots studies 1-2 only) but it does get a real Discussion
paragraph — say that instead. (b) "demonstrated not to extend to dilemma cases"
overclaims a null; Human = 2.341, SE 0.959 is failure to demonstrate, not
demonstration of failure. Use "not shown to extend."

R2-FIX-5 (population language). Substitute "these participants" / "US survey
respondents" wherever measured results are reported; reserve "the public" for
passages explicitly quoting the authors' argument, and name the sample in-body
at first use. The script inherits the paper's "the public", which is not a
defence for a convenience sample underwriting a tort-regulation argument.

R2-FIX-6 (setup metaphor). "this paper is a calibration test on the sensor" is
the script's own framing, unlabelled, and "calibration" implies the vignette
ratings validly index the courtroom quantity the policy argument needs —
asserting in the setup what the boundary list later concedes is unproven. Label
it as the script's framing and pre-empt the survey-vs-courtroom gap.

R2-FIX-7 (Guardian Angel). "the reason is architectural" -> "their explanation
is architectural." No condition manipulated architecture while holding role
constant; the paper says "it is possible for the machine to make an error that
it is not the human's responsibility to correct."

R2-FIX-8 (version disclosure trim). "The published abstract and the preprint
tell the same story in the same direction" -> "the published title and abstract
point the same direction as the preprint, which is all I can check." Also verify
"forty pages" against the PDF.

R2 judged ACCEPTABLE as written: the jury extrapolation (correctly attributed
and hedged), the passenger-residual interpretation (correctly marked as the
authors'), and the speculation/analogy labelling.

Full R2 report: /opt/data/cache/delegation/subagent-summary-1-20261105_042435_731103.txt

## Reviewer 3 — craft and house rules — FAIL, citation hygiene

Confirmed passing: zero arabic digits in dialogue; one short disclosure said once
containing fictional/correspondent/AI-generated with no close-out repeat; the
verbatim Zotero show-notes sentence; complete author list in the spoken citation;
preprint-vs-published disclosure on air; speculation labelled; continuity
callbacks to 001 and 002; topic-specific imperative before "keep the human in
the loop"; next-episode tease. No "refrigerator magnet". Only Host/Rowan turns.

R3-FIX-1 (background citations). The turn asserting two outside empirical
findings — algorithm aversion (Dietvorst, Simmons & Massey) and robots blamed
more than humans (Malle, Scheutz, Arnold, Voiklis & Cusimano) — names no source
on air and the notes have no Background sources section. Either cite both
completely on air plus notes entries, or reframe as "the authors cite earlier
work finding..." and add both under a new Background sources section in the notes.

R3-FIX-2 (same treatment). Attribute the pre-1960s crashworthiness history to
the authors' framing and to Ralph Nader, Unsafe at Any Speed, 1965; name the
German source as the Ethics Commission on Automated and Connected Driving report
for the Federal Ministry of Transport and Digital Infrastructure, 2017. Add both
to Background sources.

R3-FIX-3 (publication year). Spoken citation gives only the online date (28 Oct
2019) while the notes give the version of record (Nature Human Behaviour vol 4,
2020, pp. 134-143). Say both on air: "published online the twenty-eighth of
October, twenty nineteen, in the twenty twenty volume of Nature Human Behaviour."

R3-FIX-4 (measure precision). Every mean quoted on air (68, 57, just under 76,
59.5, 48.5, 53, 50) is the paper's aggregate of blame AND causal-responsibility
ratings, and in study 2 the machine-side figure aggregates car and company
ratings. Add one clause naming the construct once.

R3-FIX-5 (notes runtime). Notes claim "approximately fourteen minutes"; ~2,860
spoken words at episode 002's measured rate projects ~16 minutes. Set to
approximately sixteen and reconcile against the rendered duration.

R3-NOTE: single focal source against the guide's ~five-article target is accepted
as a deliberate one-paper deep read, but should be logged in production-log.md as
a recorded precedent rather than drift.

## Next command

Apply the fixes above to episodes/003/script.md and episode-notes.md via a python
script under /opt/data/tmp/ (write tools refuse this tree), py_compile nothing
needed, then re-verify: no arabic digits in dialogue, disclosure count 1,
required-disclosure sentence count 1. Then build review-panel.md with three
distinct reviewer headings, exact `Required revisions:` labels, one
`Revision record` section, exactly three `verdict:` matches, and no
unresolved/not addressed/blocked anywhere. Then `preflight 003`, then render as a
tracked background process.
