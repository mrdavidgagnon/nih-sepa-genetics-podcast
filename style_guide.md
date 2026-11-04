# Human in the Loop: Moral Machine Edition style guide

This is the living design guide for *Human in the Loop: Moral Machine Edition*, the 2026 NIH SEPA
research-review podcast. It is inherited verbatim from the *Human in the Loop*
style guide, whose craft rules, citation contract, reviewer gate and Read-lane
rules all apply here unchanged. Episode-specific precedents below refer to that
show's pilot and episodes 002–004 until this show builds its own. Update it when a deliberate change
survives an episode review; do not silently treat one-off experiments as a new
standard.

## What the show is for

*Human in the Loop: Moral Machine Edition* is a private, unlisted research-review podcast that helps
David Gagnon keep up with the 2026 NIH SEPA Zotero collection while walking his
cockapoo or biking to work. It translates research about machine ethics, moral
decision-making, autonomous systems, and human judgment into an engaging audio conversation without pretending that a
synthesis is an author interview.

The desired listening experience is:

- intellectually serious but light on its feet;
- understandable without looking at a screen;
- candid about what the evidence does and does not establish;
- useful as an orientation to the source, never a substitute for reading it;
- playful enough for a commute, precise enough to preserve scholarly trust.

## Editorial invariants

These are integrity requirements, not optional stylistic flourishes.

### One short disclosure, said once

Dr. Rowan Field is a fictional research correspondent and composite translator
of the literature — not an author, interviewee, or simulation of a specific
scholar. Dialogue paraphrases and synthesizes the research; it must never
invent quotations, statements, motives, or reactions for an author.

**On this show the spoken disclosure is one sentence, said once, near the top,
and never repeated at the close.** David's instruction 2026-11-03: minimize and
shorten the whole AI apology. A disclaimer the listener skips protects nobody.

Keep it to a single line that covers both required facts — Rowan is fictional,
and the episode is AI-generated and fallible. Current form:

> **Rowan:** Quick flag: I'm a fictional correspondent, and this is an
> AI-generated summary of the papers — it can be wrong, so read them.

Vary the wording freely, but every version must contain the words "fictional"
and "correspondent" and the phrase "AI-generated" (the preflight gate greps for
these), stay one sentence, and stay in Rowan's voice rather than becoming a
read-aloud legal notice.

Do **not** add: a second disclosure at the close, a separate
"no-author-was-interviewed" sentence, a separate "synthesis and paraphrase"
sentence, or an "evidence limits" promise. Those four facts live in the notes
and the feed description, which is where a listener who cares can read them.
The full disclosure text stays unabridged in `publish_feed.py`'s notes HTML —
shortening applies to the audio, not the written record.

### Cite every source completely

Every article discussed must receive an audible citation that includes:

1. every author name, without replacing names with “et al.”;
2. the complete article title;
3. the journal or other publication venue;
4. the publication year.

The spoken citation may appear when the source is introduced or in a dedicated
source passage. Favor conversational clarity over formal citation punctuation,
but do not omit a required element. Verify metadata against Zotero and, when
available, the publisher or DOI record before scripting.

Every episode must also say this sentence verbatim:

> The complete citations are in the show notes, with links to the Zotero files
> when you have been granted access.

### Short quotations

When an article uses unusually precise or memorable language, Turing may quote
a short passage verbatim. Introduce it with the source's complete spoken
citation, clearly distinguish the author's words from the show's synthesis, and
use only wording verified in the primary text. Otherwise paraphrase it.

### Make the show notes a trustworthy evidence map

The show notes must repeat the complete citation for every source: every author,
full title, venue, and year. Each entry must include a direct link to the Zotero
item for listeners who have been granted access. A DOI, publisher page, lawful
full-text link, or institutional record may be added as a public convenience,
but it does not replace the Zotero link.

Follow each citation with a short evidence note that distinguishes what the
source supports from what it does not support. State relevant boundaries such
as sample and setting, study type, construct validity, generalizability, and
whether the source is conceptual, methodological, design-based, observational,
or an intervention study.

Earlier checked-in notes sometimes link titles without listing complete
bibliographic metadata. They document the show's development, but they are not
the template for new work. The complete-citation rule above is now canonical.

## Voice and tone

### Host

The host is curious, brisk, and gently skeptical. The host frames the big
question, translates jargon into plain language, and asks the awkward follow-up
question before a metric or model can overclaim. Humor comes from metaphors,
understatement, and the collision between technical systems and ordinary life.

Established moves include a spreadsheet arriving at game night, a graph carried
for emotional support, an “educational” game wearing a little backpack, and a
dashboard becoming a polished mystery. Prefer one compact joke that clarifies a
concept over a string of gags. Never make the research, participants, learners,
or authors the butt of the joke.

### Dr. Turing

Turing is an upbeat, energetic, evidence-minded research correspondent: brisk,
warm, humane, and professionally fond of caveats. Rowan should sound like a
very well-read Oxford seminar guest who has just spotted an elegant connection
and cannot resist pointing it out. The British snark is affectionate and aimed
at overclaiming, jargon, and institutional absurdity—not at learners,
participants, authors, or colleagues.

Turing may use brief, accurate allusions to classic literature, philosophy, and
famous scientists or mathematicians when they genuinely clarify the argument
(for example, Aristotle on explanation, Hume on inference, Orwell on inflated
language, Ada Lovelace on computation, or Turing on the limits of a test).
Keep these references conversational, explain unfamiliar names when needed,
and never let a flourish substitute for evidence.

Turing should actively build continuity: make occasional, relevant callbacks to
earlier episodes and connect the research to the scholarly community around the
show, including UW–Madison, CMU, UPenn, Jaclyn Ocumpaugh, and Luc Paquette when
the source or topic warrants it. These are connections, not endorsements or
invented quotations; do not attribute views to a person who was not interviewed.

Turing answers the host's question, supplies the relevant finding or method, and
then marks the boundary of the inference. Rowan should sound confident about
what the source supports and modest about what it does not. Apologise for being
an AI only when a limitation genuinely needs explaining; do not make a ritual
apology.

Turing should not sound omniscient. Use language such as “the study suggests,”
“in this context,” “implementation evidence,” “a promising signal,” or “this
does not establish.” Avoid “proves,” “shows once and for all,” and universal
claims unless the source genuinely warrants them.

### Dialogue rhythm

- Use an interviewer style: the host advances the inquiry through genuine,
  listener-facing questions, while Rowan answers, qualifies, and connects the
  evidence. Do not alternate prewritten mini-lectures merely to simulate an
  interview.
- Alternate voices in short, speakable turns; do not read an essay in disguise.
- Let the host ask the listener's likely question, then let Rowan answer with a
  finding and its limit.
- Use callbacks sparingly to give the episode continuity.
- Explain acronyms and technical terms on first use.
- Put numbers in context and make denominators, base rates, and sample sizes
  audible when they matter.
- Write for listening while moving: avoid dense parentheticals, citation-symbol
  language, and long lists without verbal signposts.
- Use contractions and natural syntax. Read every line aloud before rendering.

## Episode architecture

The established structure is a default, not a stopwatch-driven formula.

1. **Cold open and question.** Welcome the listener, introduce one vivid tension
   or metaphor, state the topic, and bring in Rowan.
2. **Early disclosure.** One sentence from Rowan: fictional correspondent,
   AI-generated summary, can be wrong. Then move on — no close-out repeat.
3. **Source sequence.** Group sources into an argument rather than reciting an
   annotated bibliography. Give each source its complete spoken citation,
   useful finding, and evidence boundary.
4. **Synthesis.** Compare sources, identify tensions or complementarity, and ask
   what remains a human responsibility.
5. **Compact takeaway.** Use a short, memorable formulation—a "2-sentence abstract," "closing thought," or similar—when
   it genuinely sharpens the episode's central distinction.
6. **Notes reminder.** Say the required complete-citations/Zotero sentence
   verbatim. Do *not* restate the fictional-correspondent or AI-generated
   disclosure here — it is given once in step 2, and repeating it is exactly the
   padding this show cut.
7. **Sign-off.** End with a topic-specific imperative followed by “keep the human
   in the loop.”

The canonical package is approximately 15 minutes and approximately five
articles organized around one coherent theme. These are design targets, not
quotas: do not rush a citation to hit 15 minutes, pad a thin theme, or include a
weakly related article merely to reach five. Earlier episodes ran approximately
10–13 minutes and used three to six works; that is historical context, not the
current default. Assign each focal article to only one episode in a production
run.

## Titles and descriptions

Episode titles use title case and usually pose a human-scale question or pair a
concrete image with an analytical concern. Examples include “Can We See
Learning in the Game?”, “When a Game Needs a Teacher,” and “The Feeling Learner
and the Evidence Trail.” Avoid paper-title pastiche, unexplained acronyms, and
generic labels such as “Research Roundup.”

Descriptions should be one sentence. Identify the episode as a playful,
dramatized interview with fictional correspondent Dr. Rowan Field, name the
topic cluster, and avoid promotional claims the sources cannot support.

## Evidence design patterns

The show's central explanatory unit is **claim plus boundary**:

- “This is implementation evidence, not a learning-gains trial.”
- “The detector identifies an associated pattern; inference is not direct
  observation.”
- “Feelings are evidence about an experience, not proof of learning.”
- “A case study can demonstrate a possibility without establishing a universal
  effect.”

Other recurring patterns:

- distinguish a behavioral trace from the construct inferred from it;
- distinguish infrastructure or design guidance from outcome evidence;
- identify whose experience or context may be absent;
- make human contestability and accountability explicit;
- treat AI as a visible, challengeable participant rather than an invisible
  replacement for judgment;
- connect abstract methods to decisions a teacher, designer, researcher, or
  learner might face.

Do not manufacture disagreement for drama. When sources differ, say whether the
difference concerns evidence, method, construct, setting, or values.

### Research significant concepts

When a cited article relies on a significant named concept, framework, method,
or historical claim that a listener needs in order to understand the episode,
conduct modest background research before scripting. The goal is a concise,
reliable orientation—usually a sentence or short exchange—not an uncited lore
drop or a second literature review.

- Prefer primary and authoritative sources: the foundational publication,
  original project or institutional record, and later scholarly histories when
  the development is contested or distributed.
- Verify the historical verb. **Originated**, **developed**, **introduced**,
  **formalized**, and **popularized** are different claims. Name the relevant
  people and contributions precisely; do not credit a single person with an
  idea simply because they became closely associated with it.
- Treat examples such as the association between Evidence-Centered Design and
  Robert Mislevy as research prompts, not established wording. Verify who
  originated, developed, formalized, or popularized the concept before making
  the claim.
- If authoritative sources do not support a clean attribution, describe the
  concept without the historical claim or explicitly say that its development
  was distributed.
- Give every background source a complete spoken citation and a complete entry
  in the show notes, including all authors or creators, full title, publication
  venue or location, and year. Clearly label it as background rather than one of
  the approximately five focal articles.

Background research supports explanation; it must not silently expand or alter
the focal articles' findings. Apply the same claim-plus-boundary discipline to
it, and never present an unsupported historical attribution as settled fact.

## Audio design

The current production uses two synthetic voices with no spoken role labels:

- host: `en-US-AvaMultilingualNeural`, currently rendered at `-3%` rate;
- Rowan: `en-GB-ThomasNeural`, rendered at `-2%` rate; this is a warm, measured
  British correspondent voice selected for energetic conversational delivery.

Render each turn as a separate part, concatenate in dialogue order, and encode
the final MP3 at 128 kbps. Preserve clean alternation and conversational pacing;
do not add “Host:” or “Guest:” to the audio. Music and sound effects are not an
established design pattern and should be treated as experiments until adopted
deliberately.

Verify final duration and file integrity before publication. Current notes name
`ffprobe`; the publishing checks also confirm enclosure byte length and HTTP
range support.

## Visual identity

The cover is square (1400 × 1400) and intentionally simple at thumbnail size:

- dark navy-to-slate diagonal background (`#181b2f` to `#384e74`);
- warm yellow microphone and loop (`#f5ca5c`);
- white uppercase show title;
- pale blue-gray uppercase subtitle, “PLAYFUL RESEARCH INTERVIEWS”;
- cover art is currently inherited from the HITL show and still reads “HUMAN IN
  THE LOOP”; replace `feed-site/cover.svg` + `cover.png` before any real
  distribution;
- centered, geometric composition with generous negative space;
- bold, legible sans serif typography (currently DejaVu Sans).

Preserve high contrast, the microphone/loop motif, and immediate title
legibility in future variants. Decorative detail that disappears in a podcast
thumbnail is not helping.

## Show-notes template

Use this structure for each new episode:

```markdown
# Episode NNN — Episode Title

Playful, dramatized interview with fictional research correspondent Dr. Rowan
Field. The dialogue is a synthesis/paraphrase, not an interview with any
author; no author statements or quotations are fabricated. This is an
AI-generated summary that may contain errors and is not a substitute for
reading the cited sources.

## Sources

1. Author One, Author Two, and Author Three. “Complete Article Title.”
   *Journal or Publication Venue* (Year).
   - [Open in David Gagnon's Zotero library](ZOTERO_ITEM_URL)
   - [DOI or publisher record](PUBLIC_URL)
     - Evidence: what this source supports; the most important limitation or
     boundary on its use in the episode.

## Background sources

List any source used to explain a significant concept or historical attribution
in the same complete format as above. Label the specific background claim it
supports and distinguish it from the episode's focal article set.

## Production

- Voices and any intentional departures from the standard voice treatment.
- Spoken synthetic/dramatized disclosure confirmed.
- Spoken AI-summary disclosure confirmed near the opening and close.
- Complete spoken citations and required Zotero show-notes reminder confirmed.
- Final duration, audio verification, RSS enclosure, and stable GUID confirmed.
```

List every author even when the list is long. If an item is not an article,
adapt the bibliographic fields to the source type while retaining all creators,
complete title, publication location or venue, and year.

## Feed and publishing patterns

- Show title: *Human in the Loop: Moral Machine Edition*.
- Voices (chosen by David 2026-11-03): Host `en-US-AvaMultilingualNeural` at
  rate `-3%` — the same main voice as *Human in the Loop*, deliberately shared
  so the two shows sound like siblings. Dr. Rowan Field
  `en-US-AndrewMultilingualNeural` at rate `-2%`. This replaces HITL's
  `en-GB-SoniaNeural` Rowan: Rowan is male on this show. Set in
  `pipeline/robust_pipeline.py` and `pipeline/render_from_script.py`; the Read
  lane stays single-voice Ava.
- Project/repository name: `nih-sepa-genetics-podcast`.
- Feed base URL: `https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/`.
- GUID prefix: `moral-machines-` (the HITL feed uses `human-in-the-loop-`;
  the two feeds must never share a GUID).
- Feed type: episodic, Education category, English (`en-us`), not explicit.
- Publisher identity: Field Day Lab, UW–Madison.
- Distribution: private and unlisted; the feed landing page uses `noindex` and
  `nofollow`.
- Each episode has a stable, non-permalink GUID. Never change a published GUID
  merely because a title, note, or file is corrected.
- Publish the MP3 and full notes together. RSS extended content must repeat the
  fictional/synthetic disclosure and link to the full source notes.
- Keep current feed URLs until an intentional migration is planned and verified.

Do not move a Zotero parent item from Incoming to Podcasted until episode audio,
notes, RSS entry, and live HTTP/RSS/range checks pass. Preserve all other Zotero
collection memberships, use a fresh item version for updates, and never delete
an item as part of the move.

## Pre-publication review

Review article by article, not merely episode by episode.

- [ ] Metadata was verified against Zotero and an available DOI/publisher record.
- [ ] The script audibly names every author, full title, venue, and year.
- [ ] The notes repeat that complete citation and include the direct Zotero link.
- [ ] The script says the required show-notes/Zotero sentence verbatim.
- [ ] Each substantive claim is supported and its key evidence limit is stated.
- [ ] Significant concepts received modest background research from primary or
      authoritative sources; historical verbs and attributions are supported.
- [ ] Every background source receives a complete citation in the audio and
      notes and is clearly distinguished from the focal article set.
- [ ] Rowan's fictional status and the AI-generated/fallible warning are
      covered by ONE sentence near the opening, and are not repeated at the
      close. The full four-part disclosure appears in the notes and feed
      content, not in the audio.
- [ ] No fabricated quotation, author statement, or implication of an interview
      appears in the script, notes, description, or feed.
- [ ] Sources are uniquely assigned within the production run.
- [ ] Dialogue sounds natural when read aloud and unexplained jargon is removed.
- [ ] MP3 duration/integrity, enclosure length, stable GUID, RSS parsing, notes
      link, HTTP 200 responses, and audio byte-range response are verified.
- [ ] Zotero moves occur only after every publication check passes.

An episode is not ready if any author is omitted or if a title, venue, year,
evidence boundary, or access-appropriate Zotero link is missing.

## The Read lane (verbatim readings)

Zotero has two intake collections, and they produce different things:

- **Summerize** (`JMPPH95R`, formerly "Incoming") — normal two-voice interview
  episodes with Dr. Rowan Field. Everything else in this guide governs these.
- **Read** (`XWYVT82A`) — a single-voice **verbatim reading** of one work. These
  are **not** episodes in the interview sense and most of this guide does not
  apply to them.

Rules specific to a Read item, all mandatory:

1. **One work per reading.** No theming, no grouping, no synthesis.
2. **Main voice only** (`en-US-AvaMultilingualNeural`, rate -3%). Dr. Rowan
   Field never appears in a reading, and the synthetic-interview disclosure is
   never applied to one.
3. **Body text only.** Front matter, running heads/footers, page numbers,
   figures, tables and their captions, equations, acknowledgements, funding
   statements, appendices, and the reference list are not read. Figure and table
   content is **not** described or summarized — leaving a gap is correct, and
   filling it with narration is not.
4. **Verbatim means verbatim.** The reading text may not be paraphrased,
   abridged, smoothed, corrected, or commented on. The only non-source speech is
   the fixed intro and outro in `pipeline/read_lane.py`.
5. **Full disclosure in the intro**, spoken before the work begins: that it is
   an automated unreviewed TTS reading rather than a summary or interview; that
   it is body text only with figures and tables excluded and not described; that
   PDF extraction can garble text and anything that sounds wrong should be
   checked against the original; plus the complete citation and the standard
   show-notes reminder.
6. **The fidelity gate replaces the reviewer panel.** Verbatim has no paraphrase
   risk, so the 3-reviewer gate does not apply; the risk is silent omission. The
   gate requires >= 99.5% of extracted body words present, in source order, no
   added words, and audio duration consistent with the spoken word count. A
   reading that fails the gate must not be published — `publish_feed.py` only
   emits readings whose manifest entry has `verified: true`.
7. **Numbering and feed.** Readings are numbered from 501 (interview episodes
   keep their own sequence) and publish to the same feed, titled
   `Reading NNN: <work title>`.
8. **Copyright is David's call.** The lane reads whatever he places in Read; it
   does not check licensing. He decided this explicitly on 2026-10-24.

## How this guide evolves

When changing the format, record the decision below after it has been reviewed
in a real episode. Describe the pattern, why it changed, and which episode first
used it. Keep integrity requirements separate from revisable craft choices.

| Date | First episode | Decision | Reason |
| --- | --- | --- | --- |
| 2026-08-26 | Next produced episode | Require complete spoken and written citations for every source, a direct Zotero item link in the notes, and the standard spoken show-notes reminder. | Make the audio independently attributable while preserving a reliable path back to David's library. |
| 2026-08-26 | Next produced episode | Adopt a roughly 15-minute interviewer-style episode built around roughly five focal articles on one theme; require an AI-summary warning and cited background research for significant concepts. | Establish a consistent listening package while making the synthesis process and historical attribution more transparent. |
| 2026-10-24 | Reading 501 | Add the Read lane: items in the Zotero Read collection become single-voice verbatim body-text readings with a full-disclosure intro and an automated fidelity gate instead of the reviewer panel. | David wants to hear specific works read to him directly rather than summarized, while the audio stays honest about being unreviewed machine reading of body text only. |
