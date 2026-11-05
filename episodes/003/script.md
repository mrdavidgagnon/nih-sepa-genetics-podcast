# Episode 003 — Who Gets Blamed When Both Are Wrong

**Host:** Welcome back to Moral Machines, the show about the ethical decisions we are quietly handing to software. Last episode we built the decider. We found that the engineering to turn crowdsourced moral preferences into a running decision procedure basically exists, that its central aggregation step has a proof against it, and that the systems most likely to end up making these calls were never designed for the job — so the only oversight left is measurement after the fact. I ended by saying that whether anyone is obliged to measure is now the whole ballgame. Today I want to ask where that obligation would even come from. Here to help is our correspondent, Dr. Rowan Field. Rowan, welcome back.

**Rowan:** Good to be here. Quick flag: I'm a fictional correspondent, and this is an AI-generated summary of the paper, so it can be wrong. Read it.

**Host:** One paper today?

**Rowan:** One paper, and I want to be unusually careful about how I cite it, because the citation is part of the story. The published article is Edmond Awad, Sydney Levine, Max Kleiman-Weiner, Sohan Dsouza, Joshua Tenenbaum, Azim Shariff, Jean-François Bonnefon, and Iyad Rahwan, "Drivers are blamed more than their automated cars when both make mistakes," in Nature Human Behaviour — published online the twenty-eighth of October, twenty nineteen, and in print in the twenty twenty volume, pages one thirty-four to one forty-three.

**Host:** And the careful part?

**Rowan:** The version I actually read is not that one. The published article sits behind a paywall I could not open. What I could open is the authors' own preprint, posted to the arXiv in March twenty eighteen under a different title — "Blaming humans in autonomous vehicle accidents: Shared responsibility across levels of automation." Same authors, same three studies, forty pages. So every number I give you today was read out of that preprint, which is the submitted version, not the final published one. Anything the journal's review process changed, I would not know about.

**Host:** Does that worry you?

**Rowan:** It should be on the record, and it is. The published title and abstract point the same direction as the preprint, and that is all I can check. But a preprint is a preprint. If a listener wants to cite a figure from this episode, cite the preprint, because that is where it came from.

**Host:** Noted. So — the question.

**Rowan:** Here it is. A car crashes. A pedestrian is dead. There was a human in the seat and there was software in the loop. Who does the public blame? And the reason that question is not idle sociology is the thing you set up last episode. In a lot of legal systems, including the American one, the safety of a new product gets regulated partly from the bottom up — somebody sues, a jury decides who was at fault, manufacturers notice what losing costs them, and designs change. That mechanism runs entirely on public blame. If public blame points the wrong way, the mechanism does not fire.

**Host:** So blame is the sensor.

**Rowan:** Blame is the sensor — and that framing is mine, not the paper's, so hold it loosely. What the paper actually does is measure how people rate blame when they read a crash vignette. Whether a rating on a survey tracks what a jury does in a courtroom is the gap the whole policy argument has to jump, and we should come back to it.

**Host:** How did they run it?

**Rowan:** Vignettes, on Amazon's Mechanical Turk platform, paid online participants, United States residents only, three studies — so when I say a result, read it as what these respondents rated, not as what the country thinks. Every scenario is the same skeleton: a car has a primary driver whose job is to drive, and a secondary driver whose job is to watch the first one and intervene if the first one errs. A pedestrian ends up dead. Participants then rate, on a hundred-point scale, how blameworthy each driver was and how much each driver caused the death.

**Host:** And the variations?

**Rowan:** Two axes. First, who occupies each seat — human primary with human secondary, human primary with machine secondary, machine primary with human secondary, machine primary with machine secondary. Those four are not arbitrary; they map onto real automation levels. Human alone is the ordinary car. A human driving with a machine watching is the Guardian Angel pattern, where the software overrides you in an emergency. A machine driving with a human watching is the Autopilot pattern. And machine with machine is the fully autonomous car.

**Host:** And the second axis?

**Rowan:** The kind of mistake, and this is the hinge of the whole paper. Case one, which they call Bad Intervention: the primary driver does the right thing — stays on course, nobody dies — and then the secondary driver swerves into a pedestrian. One driver erred. Case two, Missed Intervention: the primary driver stays on course toward a pedestrian, and the secondary driver fails to swerve away. Both drivers erred.

**Host:** One mistake versus two.

**Rowan:** One mistake versus two. Hold onto that, because everything turns on it.

**Host:** Sample sizes?

**Rowan:** Study one, September twenty seventeen, seven hundred eighty-six participants across the four car types. Study two, May twenty seventeen, seven hundred seventy-nine recruited, this time comparing the two shared-control cars against a human-only car and a machine-only car, and also varying whether the machine side was represented as the car itself or as the company that made it. Study three, nine hundred seventy-three recruited, same car types, now with the programmer added as a third possible industry representative, and with the scenarios turned into genuine dilemmas — one pedestrian on one side, five on the other.

**Host:** You said recruited rather than analysed.

**Rowan:** Deliberately, because the regression tables use smaller numbers and I do not want you to think they lost half the sample. The models for studies two and three are restricted to the shared-control conditions only, so they report three hundred eighty-two and five hundred eighty-six participants respectively. Those are subsets by design, not attrition. Across the three studies the regressions run on roughly three thousand, fifteen hundred, and forty-seven hundred observations.

**Host:** Any quality filtering?

**Rowan:** Three filters, and I like that they are specific. Participants had to finish every measure, had to transcribe a hundred and sixty-nine character paragraph from an image near-perfectly, and had to have a unique worker identifier within the study — every repeat identifier was dropped.

**Host:** Good. Start with the easy case. One driver errs.

**Rowan:** The easy case is boringly reassuring, and you should notice how boring it is. When only one driver made a mistake, these participants put the blame on that driver, and whether the driver was a human or a machine made no detectable difference. One thing to say once and carry through: every score I quote is the paper’s combined measure of how blameworthy a driver was and how much it caused the death, on a hundred-point scale. In the regression, the coefficient for having made a mistake is large and significant in all three studies — sixty-three points in study one, fifty-six in study two, and a smaller but still significant eleven in study three, where the dilemma framing compresses everything. The coefficient for the driver being human rather than a machine is small and not statistically significant in any of the three.

**Host:** So no robot bias.

**Rowan:** No robot bias in this condition, which is itself worth saying out loud, because the authors cite earlier work that gave reason to expect one. Berkeley Dietvorst, Joseph Simmons and Cade Massey, in "Algorithm aversion: people erroneously avoid algorithms after seeing them err," in the Journal of Experimental Psychology General, twenty fifteen, found people lose confidence in an erring algorithm faster than in a human making the same error. And Bertram Malle, Matthias Scheutz, Thomas Arnold, John Voiklis and Corey Cusimano, in "Sacrifice one for the good of many? People apply different moral norms to human and robot agents," at the twenty fifteen ACM/IEEE Human-Robot Interaction conference, found robots judged differently from humans for identical decisions. In the one-mistake case here, none of that shows up. An erring machine is blamed like an erring human.

**Host:** Then the hard case.

**Rowan:** Both drivers err, and the sensor goes crooked. Now the only thing left to distinguish the two agents is what kind of thing they are — and that becomes a significant predictor. In study one, being human adds about seventeen points of blame. In study two, about thirteen. Same behaviour, same outcome, same failure to act; the human is rated higher.

**Host:** Is that humans being blamed more, or machines being blamed less?

**Rowan:** Thank you, because that is the right question and the paper answers it. It is machines being blamed less — specifically, machines being blamed less when there is a human in the loop beside them. The clean comparison is against the machine-machine car, where the behaviour is identical and both agents are software. In that car, the machine primary driver gets about sixty-eight. Put a human in the secondary seat instead, change nothing else, and the same machine in the same role doing the same wrong thing gets about fifty-seven. The mirror comparison holds too: a machine in the secondary seat is blamed less when the driver beside it is a human than when it is another machine.

**Host:** So when a human is in the loop, the software is rated lower than when it is not.

**Rowan:** And study two replicates it against a different baseline — the fully autonomous car. Software alone, nobody else to point at, gets just under seventy-six. The same software sharing control with a human gets about fifty-nine and a half when it is driving, and about forty-eight and a half when it is supervising. Both drops are large and statistically strong.

**Host:** Could that just be a general reluctance to blame machines?

**Rowan:** No, and the design is what rules it out. That is exactly what the one-mistake case is for. In shared control with only the machine at fault, human and machine scores sit at about fifty-three and about fifty, and that gap is not significant. So it is not that these respondents went easy on software in general. It is specifically that in a dual-error case, the machine was rated lower when the driver beside it was a human.

**Host:** What about competence? If people think the machine is just not very good, maybe they excuse it the way you'd excuse a novice.

**Rowan:** They tested that and it does not hold. Humans and machines were rated about equally competent, and that was true whether competence was asked before participants read about the crash, in study one, or after, in study two. Competence ratings did not mediate the blame effect.

**Host:** There's a detail in here I want to make sure we say. Did these participants blame agents who weren't even involved?

**Rowan:** They did, a little, and I find it the strangest result in the paper. In the ordinary human-only car, some blame still attached to the car and to the company that built it. In the fully autonomous car, some blame still attached to the human passenger — a person with no controls and no role in the decision. The authors read that second one as people treating the act of getting into the car as an implicit acceptance of some responsibility.

**Host:** Now the one that complicates the story. Study three.

**Rowan:** Study three is where the effect disappears, and the authors state it plainly rather than burying it — though I should be precise: it is a parenthesis in the results and a paragraph in the discussion, not something you would catch from the abstract. When the scenario is a true dilemma — swerve and kill one, or stay and kill five — the driver-type effect in the dual-error case is no longer significant. One of the three studies does not replicate the headline finding, under a specific and clearly described change of scenario.

**Host:** Why would that be?

**Rowan:** Their reading is that it stops being obvious what counts as a mistake. In studies one and two there is a clearly correct action and a clearly wrong one. In a five-versus-one dilemma, refusing to swerve into someone who was previously not in danger is not plainly an error, and they note that the German Ethics Commission on Automated and Connected Driving, in its twenty seventeen report for the Federal Ministry of Transport and Digital Infrastructure, explicitly prohibits trading lives off against each other in the first place. So the error framing that drives the effect may simply dissolve.

**Host:** How much weight should we put on the finding, then?

**Rowan:** Mine would be: solid for cases with an unambiguous mistake, and not shown to extend to dilemma cases — which is a failure to demonstrate the effect there, not a demonstration that it is absent. That is a boundary the paper itself drew, and anyone citing this as "people always blame humans more" has walked past it.

**Host:** Let's get to the policy claim, because that's the reason we're covering this.

**Rowan:** The authors call it a risk of public under-reaction, and that phrase is doing a lot of work. The normal worry about self-driving cars is public over-reaction — one bad crash, a panic, adoption stalls. This paper argues the opposite risk is live in exactly the dual-error cases that real crashes tend to be. If the public instinctively absolves the machine when a human was also in the loop, then juries plausibly will too, and the pressure that tort litigation is supposed to put on manufacturers to improve designs gets weaker precisely where the software failed. Their conclusion is that bottom-up regulation through the jury system could fail here, and that top-down federal rules may be needed instead.

**Host:** And they have a precedent for that.

**Rowan:** A good one, and it is their framing of the history, not an independent finding of theirs. Before the nineteen sixties, car makers had substantial freedom from liability when an occupant was hurt, because blame went to the driver's error. Crashworthiness — the idea that a car should be designed to limit injury when a crash does happen — had to be written into law from above before manufacturers were made to design for it. The campaigning text behind that shift is Ralph Nader, "Unsafe at Any Speed," nineteen sixty-five. Their claim is that we are in a structurally similar moment.

**Host:** Is there a case where the public over-reacts instead?

**Rowan:** One, and it is a nice piece of reasoning. In the human-driving, machine-watching car — the Guardian Angel pattern — a bad intervention is the only one of the shared-control cars where the machine side gets more blame than the human — the only case, that is, where a human is actually a driver. And their explanation is architectural: the machine's job is to correct the human's mistakes, but nothing is assigned to correct the machine's. So when the override is the thing that kills someone, there is nobody else to point at. The authors flag that as a liability exposure manufacturers of supervisory systems should plan for.

**Host:** There's also a line in here about incentives that I thought was genuinely unsettling.

**Rowan:** The speculation that blame patterns, once they are public knowledge, become something people optimise against. People might prefer systems where the machine is likely to take the blame — or even learn to drive in ways that leave blame with the machine, by not intervening to correct a bad override. They draw a parallel to judges leaning on actuarial risk-assessment tables in pretrial release decisions, where attention after a bad outcome lands on the algorithm rather than the judge. That parallel is an analogy they raise, not something this study measured.

**Host:** Full boundary list before we close. What can't this paper support?

**Rowan:** Four things. One of them is the authors' — study three not replicating the main effect. The other three are mine, and I want to be honest that the authors would push back on two of them. One: it is stylized vignettes with a rating scale. A rating is not a verdict, and a Mechanical Turk worker is not a seated juror under instruction with counsel arguing at them. The authors argue the opposite — they say their stylized vignettes do show external validity, and their evidence for that is convergence with how one real crash was received in the press. I do not think one news cycle carries it. Two: the sample is United States residents only, and the authors do not flag that as a limit — it appears in their methods as a neutral descriptor. I am flagging it, because the previous two episodes of this show were built on the finding that moral judgment about cars varies substantially by country. Nothing here tells you whether this effect travels. And three: I read the preprint, not the published version, so treat the exact coefficients as the submitted ones.

**Host:** Let me try to join it to where we were. Episode one: ask the crowd, and the answer varies by culture and clashes with expert guidance. Episode two: you can build a machine that executes the crowd's answer, and faithfulness to the aggregate is the defect, and the systems actually arriving were never designed for the task — so oversight collapses to measurement after the fact. Today: the mechanism that would make anyone measure is public blame, and public blame has a systematic blind spot aimed exactly at the case where a human and a machine both fail.

**Rowan:** Which is the case the real crashes keep being. The first fatal Autopilot crash in twenty sixteen had that structure — neither the software nor the driver braked for a truck crossing the road. The regulator did not find the manufacturer at fault, the family did not blame the car, and press attention fixed on an unfounded rumour about what the driver had been watching. The authors open with that episode and their results say it was not a fluke of one news cycle.

**Host:** Bottom line?

**Rowan:** When a human and a machine fail together, these participants discounted the machine's share — not because it seemed incompetent, and not because people are soft on software generally. Why they did it the authors call an open question, and I will leave it there. What was measured is narrower and still unsettling: change the partner from a machine to a human, change nothing else, and the software's score drops. If that pattern reaches a jury — which the authors forecast and nobody has yet measured — then the feedback loop we rely on to force safety improvements is quietest exactly where the software broke, and that is my inference, not their finding.

**Host:** And if that's right, the oversight obligation we were hunting for last episode doesn't arrive on its own.

**Rowan:** It has to be legislated, because it will not be litigated into existence. That is the paper's argument and I think it survives its own caveats.

**Host:** The complete citations are in the show notes, with links to the Zotero files when you have been granted access. Next time: what the people building these systems actually owe the people they are built for. Until then — when a human and a machine share the wheel, notice which of them the story blames, and ask who benefits from that habit. And keep the human in the loop.
