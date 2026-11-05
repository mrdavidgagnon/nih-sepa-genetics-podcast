# Episode 002 — Review panel: "Building the Decider"

Three independent reviewers, each given the extracted full text of all four
sources (not the script alone). Sources: W5Q7PFMK Kim et al. 2018 (AAAI/ACM
AIES), W9D57F3R Noothigattu et al. 2018 (AAAI 32), VDWW52G6 Awad et al. 2020
(CACM 63(3)), 2WH5N968 bin Ahmad & Takemoto 2025 (PLOS One 20(5) e0322776).

## Reviewer 1 — Quantitative accuracy and source attribution

**Final verdict: PASS.** Rendering is authorized by this reviewer.

Scope: every numeric claim, statistic, sample size, author list, venue, year and
page range in the script and notes, checked against the extracted full texts.
Spelled-out number forms were converted to digits before comparison.

Verified:
- Kim pages 197–203, AIES 2018, seven-author MIT list; 18x24 binary
  character-to-abstract-feature matrix over twenty character types.
- Kim 99 Danish respondents / 1,287 judgments; 10,000 respondents, first 13
  scenarios = 130,000 decisions, train on 8, test on remaining 5; three
  same-author benchmarks compared as curve margins, no headline accuracy.
- Kim 1,727 US respondents / 22,451 judgments, 120-second cutoff, response-time
  versus model-certainty agreement.
- Noothigattu AAAI vol. 32 (2018), seven-author list, four-step pipeline, swap
  dominance with anonymity/neutrality/monotonicity; 18,254,285 pairwise
  comparisons from 1,303,778 voters; ~14 comparisons per voter; 98.2% and 95.1%
  agreement figures; 412 Food Rescue deployment reference.
- Awad CACM 63(3), March 2020, pp. 48–55, five-author list; tabulated
  criticisms-and-responses; Germany's 2016 expert committee, the
  animals-overlap agreement and the age-discrimination clash; the authors' own
  "too naive" and "too simple" concessions; Society in the Loop.
- Attribution boundary across the three Awad papers holds: 40M decisions / 233
  countries / nine attributes is credited to Awad 2018 Nature, 70,000
  participants / 42 countries to Awad 2020 PNAS, and neither is claimed for the
  CACM retrospective that is this episode's source.
- bin Ahmad & Takemoto PLOS One 20(5) e0322776, 52 LLMs, AMCE conjoint; rho =
  -0.54 (p = 0.0076) for size versus distance; GPT-4 species and group-size
  effects above 0.9 against a human ~0.6; GPT-4o law-abiding 0.8 against 0.4;
  Sonnet 3 to 3.5 improving 1.2 to 0.9; Haiku 3 to 3.5 diverging; Gemini 1.5
  Pro Preview 0.9 rising to 1.1; fitness and passenger-versus-pedestrian
  inversions.

Required revisions: none. One note recorded rather than a change: the Kim page
range is absent from the extracted text and was confirmed instead from the ACM
DOI record 10.1145/3278721.3278770 plus three independent publisher listings.

## Reviewer 2 — Evidence boundaries and overclaim control

**Final verdict: PASS.** Rendering is authorized by this reviewer, on the
revised script. This reviewer's first read returned a failing assessment on six
counts; all six are corrected below and were rechecked against the full texts.

Scope: whether each interpretive claim stays inside what its source licenses;
correlation stated as causation, sample generalised to people in general,
capability overstated, authors credited with normative claims their data cannot
support, author-stated limitations omitted, editorial framing presented as
finding, same-author benchmarks described as validated.

Within bounds on first read: Kim's abstraction and hierarchical prior described
as modelling choices; the response-time check framed as supporting evidence
rather than validation, with its US-only sample named; the script's refusal to
quote a headline accuracy and its naming of the benchmarks as same-author
constructs; Kim's boundary that the model covers individual judgment and
explicitly leaves aggregation out of scope; Noothigattu's Theorem 4.1 scope;
the CACM concessions quoted faithfully with the three Awad papers kept apart;
the bin Ahmad boundary turn on the world-average benchmark, binary text
dilemmas and version snapshots; and "faithfulness to the aggregate is precisely
the defect", which is explicitly voiced as the host's own take.

Required revisions: six overclaims, each now corrected in the script.
1. The 98.2%/95.1% agreement was presented as faithfully reproducing what the
   aggregate would have chosen. The benchmark is a Borda count on a sampled
   estimate of the mean profile, and the paper states the true 1,303,778-voter
   winner is uncomputable. Rewritten to say it measures fidelity to the
   authors' own aggregation step, not moral correctness.
2. The Noothigattu boundaries turn omitted the authors' third stated
   limitation. Added: the feature set is contentious and simultaneously too
   coarse, carrying no probabilities or degrees of harm.
3. "It is exactly the same mechanism" asserted an identity between Feffer,
   Heidari and Lipton's analysis and this system. Rewritten to state that they
   analysed preference-vector averaging and did not study this system, so the
   connection is the show's inference, not their finding.
4. Germany's public preference was called "the public's strongest preference";
   CACM supports only "largely approves", with sparing the young one of several
   top preferences. Corrected.
5. "Agrees with us roughly in proportion to its size" restated rho = -0.54 as
   proportionality. Rewritten as a moderate rank correlation with loud
   exceptions, not a law.
6. "Only legible through post-hoc statistics" and "a preference profile you can
   only measure after the fact" presented the show's argument as a finding of
   the papers. Both rewritten to attribute the claim to the host and bound it
   to the evidence in these four papers.

## Reviewer 3 — Format, disclosure compliance, and listenability

**Final verdict: PASS.** Rendering is authorized by this reviewer, on the
revised script. This reviewer's first read returned a failing assessment on
spoken-number form only; all seven fixes are applied and verified below.

Passed on first read: exactly one disclosure sentence near the top carrying
"fictional", "correspondent" and "AI-generated", with zero occurrences in the
final three turns; all four sources introduced on air with full author lists,
title, venue and year; the required show-notes and Zotero sentence present;
no banned phrasing, and a varied closing prompt; every non-title line a Host or
Rowan turn with no stage directions; 34 Host and 33 Rowan turns alternating
cleanly.

Required revisions: spoken-number form. Model and organisation version tokens
plus one year were left as raw digits that TTS would mangle. Seven fixes:
"2018 AAAI/ACM" to words; "412 Food Rescue" to "four one two Food Rescue";
GPT-4, GPT-4o and their possessives to spoken forms; "Claude 3.5 family" to
"Claude three point five family"; "o1" to "oh one"; the Llama 3, Llama 3.1,
Llama 70B and Gemma 2 at 2B tokens to spoken forms; and "Claude Sonnet 3 to
3.5", "Haiku 3 to 3.5" and "1.5 Pro Preview" to spoken forms.

## Revision record

All required revisions from reviewers 2 and 3 are resolved in
episodes/002/script.md. Reviewer 1 required none.

- Reviewer 3's seven spoken-number fixes were applied by
  /opt/data/tmp/mm002_tts_fix.py under assertion guard: exactly six lines
  reworded, line count unchanged, 67 turns preserved, disclosure still present
  exactly once and absent from the close, and a digit scan over every spoken
  turn returning zero. Backup at script.md.bak-tts. Reviewer 3 re-read the
  result and moved to pass.
- Reviewer 2's six boundary revisions were applied by
  /opt/data/tmp/mm002_r2_fix.py under the same guard pattern: eight anchored
  replacements, each anchor asserted unique beforehand; seven original lines
  reworded and every one of them accounted for in an explicit expected-reword
  whitelist; line count unchanged at 136; 67 turns preserved; disclosure
  unchanged in position and count; no digits reintroduced into spoken turns.
  Backup at script.md.bak-r2. Script moved from 3,608 to 3,760 words, the
  growth being the added limitation and the added attributions.
- Reviewer 1's verification ran against the post-revision script, so its pass
  covers the text as it now stands.

Reviewers 1 and 2 were run as independent parallel subagents with the extracted
full texts rather than the script alone. An earlier dispatch of both died on
output-token limits without emitting verdicts; no verdict was inferred from
those partial transcripts, and both were re-run under a verdict-first, compact
output contract until each produced an explicit verdict.
