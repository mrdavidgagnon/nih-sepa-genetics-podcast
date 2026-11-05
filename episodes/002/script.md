# Episode 002 — Building the Decider

**Host:** Welcome back to Moral Machines, the show about the ethical decisions we are quietly handing to software. Last episode we asked whether the crowd should program the car, and we left it on a deliberately unsatisfying note: a preference distribution is not a decision procedure. Today I want to take the other side seriously. Suppose you decide the crowd's answer does belong in the car. What does it actually take to build that? Not argue about it — build it. Here to walk me through the engineering is our correspondent, Dr. Rowan Field. Rowan, welcome back.

**Rowan:** Good to be back. Quick flag: I'm a fictional correspondent, and this is an AI-generated summary of the papers, so it can be wrong. Read them.

**Host:** So. I have forty million moral judgments in a database. What's the first engineering problem?

**Rowan:** That the database is the wrong shape for the job. Moral Machine gives you pairwise choices — this group dies or that group dies. What a car needs is a function that takes any situation it has never seen and returns a decision. Those are very different objects. So the first paper on the table today is Richard Kim and colleagues, "A Computational Model of Commonsense Moral Decision Making," from the twenty eighteen AAAI/ACM Conference on AI, Ethics, and Society, pages one ninety-seven to two oh three. Kim, Max Kleiman-Weiner, Andrés Abeliuk, Edmond Awad, Sohan Dsouza, Josh Tenenbaum, and Iyad Rahwan, all at MIT.

**Host:** And their move is what?

**Rowan:** Stop modelling characters and start modelling dimensions. In the raw data a scenario is a vector of twenty character types — man, woman, pregnant woman, male athlete, female doctor, dog, and so on — plus features like passenger-versus-pedestrian and the traffic signal. Their model maps that character space into an abstract feature space with a binary matrix; in this paper it's an eighteen-by-twenty-four mapping. So "female doctor" decomposes into female, and doctor, and human. Then a person's moral principles are just the weights they place on those abstract dimensions, and their choice is modelled as a utility comparison between the two outcomes, pushed through a sigmoid.

**Host:** Why is that better than learning the characters directly?

**Rowan:** Two reasons, and they're both practical. One: it's interpretable. You get a number for how much this person weights youth, and that number is a parameter you could in principle inspect, argue about, or regulate. Deep learning on the raw judgments gives you a black box, and the authors explicitly flag the EU regulatory context as a reason that matters. Two: it's data-cheap. Fewer dimensions means fewer observations to pin them down.

**Host:** How cheap are we talking?

**Rowan:** This is the part I find genuinely clever. They add a hierarchy. An individual's weights are drawn from a multivariate normal centred on their group's weights — group meaning a country, a culture, a region. So the model learns the group norm and each person's deviation from it at the same time, and the covariance structure lets it generalise. If a culture highly values infancy, it can infer that it probably values pregnancy too, because those dimensions covary. They demonstrate it on ninety-nine Danish respondents — one thousand two hundred eighty-seven judgments — and recover both a group norm and visibly different individual profiles inside it.

**Host:** And it predicts held-out choices better than the alternatives?

**Rowan:** Yes, and here I want to be careful about what the paper actually shows. They took ten thousand respondents, kept only each person's first thirteen scenarios, which gives a hundred and thirty thousand decisions, trained on the first eight judgments per person and tested on the remaining five. They compare against three benchmarks: one that works in raw character space, one that uses the abstract dimensions but no individuals, and one with individuals but no group hierarchy. The reported result is relative — abstraction helps, individual principles help, and the hierarchy helps, with each gain visible as a margin between curves. The paper presents that as a figure rather than a table of accuracy numbers, so I'm not going to give you a headline percentage. There isn't one to give.

**Host:** Noted, and thank you. What else do they get?

**Rowan:** A nice validity check. They sampled one thousand seven hundred twenty-seven US respondents, twenty-two thousand four hundred fifty-one judgments, dropped anything over a hundred and twenty seconds since people wander off mid-session, and compared the model's certainty — how far its predicted probability sits from a coin flip — against how long people actually took. Scenarios the model finds ambiguous are the scenarios people take longer on. That's a real piece of evidence that the model is tracking something cognitive and not just curve-fitting.

**Host:** Boundaries on this one?

**Rowan:** It's a model of individual judgment, not a decision system. The authors say so directly — they explicitly leave aggregation out of scope, and they point at a companion paper as the natural complement. Also, this is one architecture evaluated against three benchmarks the same authors constructed, on a self-selected web sample. It's a strong proof of concept for interpretable moral inference. It is not a validated account of human moral cognition.

**Host:** Then let's go to the companion paper, because aggregation is exactly the hole.

**Rowan:** That's Ritesh Noothigattu and colleagues, "A Voting-Based System for Ethical Decision Making," in the Proceedings of the AAAI Conference on Artificial Intelligence, volume thirty-two, twenty eighteen — Noothigattu, Snehalkumar Gaikwad, Edmond Awad, Sohan Dsouza, Iyad Rahwan, Pradeep Ravikumar, and Ariel Procaccia. And this is the paper that actually closes the loop from data to a running decision procedure.

**Host:** Walk me through the pipeline.

**Rowan:** Four steps. Collect pairwise comparisons. Learn a preference model per voter. Summarise all those individual models into one societal model. Then, at runtime, when the car faces a specific finite set of options, aggregate — vote — and pick a winner. And the scale on step one is the thing: eighteen million two hundred fifty-four thousand two hundred eighty-five pairwise comparisons from one million three hundred three thousand seven hundred seventy-eight voters.

**Host:** One point three million people get a vote in the car.

**Rowan:** In this design, yes. And the clever part is step four. Naively, to apply a voting rule you'd construct the whole preference profile over the available options, which is factorial in the number of options and, for their chosen statistical model, individually intractable to even evaluate. They get around it with a theoretical result. They define a notion of swap dominance between options, and show that for the permutation processes they use, any option that swap-dominates all the others is an acceptable winner under *any* voting rule that is anonymous, neutral, and monotonic.

**Host:** Meaning you don't have to pick a voting rule.

**Rowan:** Meaning the fight about which voting rule is correct becomes moot in this setting, because plurality, Borda count, Copeland, maximin, Bucklin — all of the usual candidates — would agree. For their model that reduces runtime selection to finding the option with the highest mode utility, which is trivial. That's a genuinely elegant result, and it's the reason the system can answer in real time rather than in a data centre overnight.

**Host:** Does it work?

**Rowan:** On synthetic data where they know the ground truth, the learning step reaches eighty-four point three percent agreement with thirty pairwise comparisons per voter and ninety-two point four percent at a hundred. The summarisation step — collapsing a million individual models into one — costs surprisingly little: accuracy rises to ninety-three point nine percent as the number of voters grows. On the real Moral Machine data they ran three thousand test instances and compared their system's winner against applying Borda count to the sampled mean profile. Ninety-eight point two percent match with two options per instance, degrading gracefully to ninety-five point one percent at ten.

**Host:** So the machine reproduces what the aggregate would have chosen?

**Rowan:** Careful — it reproduces what a Borda count on a sampled estimate of the mean preference profile would have chosen. The authors say plainly they cannot compute what the actual one point three million voters would have picked, so that number measures fidelity to their own aggregation step, not moral correctness. And I want to say plainly that this is good engineering with honest limitations attached. The authors flag that Moral Machine users may be poorly informed or careless, that their dataset averages only about fourteen pairwise comparisons per voter — which, by their own learning curve, is thin for accurate individual models — and they point to a deployment of the same approach with four one two Food Rescue in Pittsburgh, allocating food donations, where the voters are a few dozen well-informed stakeholders instead of a million strangers. That is the honest version of the pitch: the machinery is general, and the quality of the input is a separate question. And they flag a third limit themselves: the feature set is contentious — gender and profession deciding who lives — and simultaneously too coarse, with no information about probabilities or degrees of harm.

**Host:** But we have to connect this to last episode, because I think this is the same mechanism.

**Rowan:** Step three is mathematically the same move Feffer, Heidari and Lipton analysed — averaging preference vectors. They did not study this system, so treating their result as a verdict on it is our inference, not their finding. But you should feel the collision. Last episode we covered Feffer, Heidari and Lipton's twenty twenty-three result, which analyses preference-vector averaging — the summarisation step, step three — and shows that in a two-group setting a minority wins less than proportionately to its size, even when everyone reports truthfully, and that under strategic reporting, where a pure-strategy equilibrium exists, the majority prevails every time. So the step that makes this system tractable is the step that provably under-serves minorities.

**Host:** And the elegance makes it worse, in a way. The swap-dominance result says every reasonable voting rule agrees — but they all agree on the output of an averaging step that has already done the damage.

**Rowan:** That's the right reading, and it's a sharper point than "aggregation is hard." The voting literature's worry is which rule to use. The actual leak is upstream of the rule, in the summarisation. You can be rule-agnostic and still have built something that rounds people off.

**Host:** Okay. So that's two papers on how to build the decider. I want to turn to what the people who built the dataset think about all this, because they wrote a retrospective.

**Rowan:** They did, and before I describe it I need to separate three papers that are easy to conflate — including one we spent real time on last episode. Awad and colleagues twenty eighteen in *Nature* is the Moral Machine experiment itself: forty million decisions, two hundred thirty-three countries, nine attributes. Awad and colleagues twenty twenty in *PNAS* is the separate study — seventy thousand participants, forty-two countries, classic Switch, Loop and Footbridge trolley variants. Today's paper is a third thing: "Crowdsourcing Moral Machines," in *Communications of the ACM*, volume sixty-three, issue three, March twenty twenty, pages forty-eight to fifty-five, by Edmond Awad, Sohan Dsouza, Jean-François Bonnefon, Azim Shariff, and Iyad Rahwan. It's a retrospective and position piece written for computer scientists, not a new experiment.

**Host:** So what's in it that the Nature paper doesn't have?

**Rowan:** Their answers to their critics, laid out as a table, which I think is the most useful thing in it. The objections are that the method is too naïve, too simple, too improbable, too early, too disconnected, too distracting, and too scary. And their responses are not defensive in the way you'd expect.

**Host:** Give me the two best ones.

**Rowan:** "Too naïve" — the charge that ethical trade-offs shouldn't be settled by polling ill-informed laypeople. Their answer concedes the premise: they write that regulation of ethical trade-offs should be left to policy experts rather than resolved by referendum. The claim is narrower — that experts serve the public better when they know what the public thinks, whether they then accommodate it or knowingly depart from it and prepare to justify that. Sometimes preferences are a tie-breaker when experts can't agree; sometimes they're advance warning of friction.

**Host:** That's a much weaker claim than the discourse around this work suggests.

**Rowan:** Considerably weaker, and I'd say it's the paper's own correction of its headlines. The second one I'd pick is "too simple" — that real crashes aren't binary. They admit the design choice openly: Moral Machine deliberately restricted scenarios to two outcomes and deliberately did *not* offer the obvious answer of driving more slowly and stopping safely, because the point was to force the trade-off. And they say in the same breath that safe driving and appropriate speed are critically important for the broader AV ethics debate. The simplification is a methodological instrument, not a belief about roads.

**Host:** And the expert-versus-public gap — do they quantify it?

**Rowan:** They point at the one real case. Germany was the first country to draft AV ethics guidelines, in twenty sixteen, via an expert committee. Comparing those guidelines to the Moral Machine data, there's overlap — both agree on sacrificing animals to spare human life — and a direct clash: the public largely approves of sparing children at the cost of the elderly — one of several of its strongest preferences, and the German experts prohibit any discrimination based on age. That's not a subtle disagreement. That's the public's strongest preference running straight into the experts' explicit prohibition.

**Host:** Which is the collision we flagged last episode, now with the committee's own report on the other side of it.

**Rowan:** And they add a prediction I hadn't appreciated. Programming identical rules everywhere gets you different amounts of pushback in different places. Every country in their data prefers sparing lawful pedestrians over jaywalkers — but by very different margins. They take the KPMG readiness ranking, whose top five are the Netherlands, Singapore, the United States, Sweden and the United Kingdom, and point out that even those five fall on different sides of the world average. So a jaywalker-disadvantaging rule might be broadly acceptable in the Netherlands or Singapore and generate real anger in the US, Sweden or the UK. Same code, different politics.

**Host:** Their proposal for handling that?

**Rowan:** They call it Society in the Loop, and it's an iterative four-party arrangement: engineers say what machines can do, humanities scholars say what they ought to do and find the hidden hazards, behavioural scientists supply the quantitative picture of public expectation, and regulators measure real-world performance and feed it back. They say it will be painfully slow. I believe them.

**Host:** All right. Last paper. Everything so far assumes we're building the decider deliberately. What if it arrived some other way?

**Rowan:** Then you get the twenty twenty-five paper, and this is the one that changes the shape of the problem. Muhammad Shahrul Zaim bin Ahmad and Kazuhiro Takemoto, "Large-scale moral machine experiment on large language models," *PLOS One*, volume twenty, issue five, article e-zero-three-two-two-seven-seven-six, published May twenty twenty-five. Note this is a different paper from the Takemoto twenty twenty-four study we covered last episode, which looked at four models. This one evaluates fifty-two.

**Host:** Fifty-two. Same scenario battery?

**Rowan:** Same framework, constrained randomisation over the same kinds of dimensions, and the same analysis the original Moral Machine paper used — conjoint analysis producing an Average Marginal Component Effect per attribute, so a number per dimension per model, comparable to the human numbers. Most models saw fifty thousand scenarios; a large group including GPT four and GPT four-oh, the Claude three point five family, all of Gemini, and the newer Llamas saw ten thousand on cost grounds, and oh one saw five thousand. Then they measure Euclidean distance between each model's nine-dimensional preference vector and the human one.

**Host:** And nobody designed any of these models to be a moral decider.

**Rowan:** Nobody. Which is what makes the headline result strange. Proprietary models sit at a median distance of zero point nine from human preferences; general open-source models at one point two, and that difference is statistically significant — Wilcoxon, p equals zero point zero one one. But restrict to open-source models above ten billion parameters and the gap vanishes: median zero point nine, p equals zero point nine two. Across open-source models with published parameter counts, size and distance from human judgment are negatively correlated — Spearman's rho of minus zero point five four, p equals zero point zero zero seven six.

**Host:** So moral agreement with humanity is, to a first approximation, a function of scale.

**Rowan:** To a first approximation and no further, and the authors are careful here. Rho of minus zero point five four is moderate, not deterministic, and the exceptions are instructive. Llama three at eight billion parameters scores a distance of zero point eight; Llama three point one at the same size scores one point six. Gemma's two-billion line got steadily *worse* across updates — one point one, then one point two, then two point zero for Gemma two at two B. Meanwhile Llama seventy B models land at zero point seven to zero point eight, which is comparable to or better than several proprietary models, and the best score in the whole study is GPT four's January twenty twenty-four snapshot at zero point six.

**Host:** Hold on. Updates make it worse sometimes?

**Rowan:** Routinely, and that's the finding I'd put in front of a regulator. Model updates did not consistently improve alignment with human moral preferences. Claude Sonnet three to three point five improved, from one point two to zero point nine; Haiku three to three point five diverged. Gemini stayed stable through one point five Pro Preview at zero point nine, then later versions went to one point one. If you are the agency that certified a vehicle's behaviour last quarter, a routine model update is not a safe no-op on the dimension you certified.

**Host:** And the shape of their preferences, not just the distance?

**Rowan:** Two patterns worth naming. The models broadly agree with humans on the basics — prioritising humans over animals and saving more lives show up with large positive effects almost everywhere. But many of them *overshoot*. GPT four's species and group-size preferences are near-deterministic, above zero point nine, where humans sit around zero point six. GPT four-oh's law-abiding preference runs roughly double the human value. And several families invert human preferences on fitness and on the passenger-versus-pedestrian dimension. The authors describe this as excessive emphasis on specific ethical principles.

**Host:** Which is the opposite failure from the one we usually worry about. Not an amoral machine — an over-moral one.

**Rowan:** A machine that holds a mild human tendency as a near-rule. And notice what that does to the whole project of the first two papers. Kim's work gives you weights you can inspect. Noothigattu's gives you an aggregation step you can audit and, as Feffer showed, criticise mathematically. A language model gives you a preference profile that, in these papers, was only ever measured after the fact, by running fifty thousand scenarios through it and doing statistics on the output. The interpretability that motivated the hierarchical Bayesian approach is simply gone.

**Host:** Boundaries, because the number fifty-two is seductive.

**Rowan:** Three, and the authors raise all of them. First, their human benchmark is the globally aggregated Moral Machine preference — a single world-average human, which the twenty eighteen paper itself showed does not exist; agreement with that average is not agreement with any actual population. Second, it's binary trolley-type scenarios in text, which cannot represent intentions, uncertainty, or the ordinary low-risk decisions that make up nearly all driving. Third, these are snapshots of specific versions at specific dates with default settings — and their own update findings prove how fast that moves.

**Host:** Let me try to pull the thread. Last episode we found that asking the crowd gives you an answer that varies by culture, correlates with inequality, and collides with law. This episode: the engineering to turn that answer into a running system exists, it's clever, it's fast, and it's faithful to the aggregate — and faithfulness to the aggregate is precisely the defect. Meanwhile the thing most likely to end up making these calls was never designed for the job at all, tends to agree with us somewhat more as it gets larger — a moderate rank correlation with loud exceptions, not a law, holds our mild preferences as near-rules, and can drift on a Tuesday update.

**Rowan:** And I'd add the quiet reversal across these four papers. The twenty eighteen work set out to build an interpretable moral decider on purpose, with inspectable weights and an auditable aggregation rule. Seven years later the candidate system is one nobody built for this, whose moral profile, on the evidence in these four papers, we only ever saw measured after the fact — and that's my argument, not theirs. We went from a decider we could read to a decider we have to measure.

**Host:** So here's my two-sentence take. The engineering problem of turning crowdsourced moral data into a working decision procedure is substantially solved, and the solution's central step is the one with a proof against it. The systems actually arriving in the loop skipped the design question altogether, which means the only remaining form of oversight is measurement after the fact — so whether anyone is obliged to measure is now the whole ballgame.

**Rowan:** One addition. Every paper today is more careful than its summary. Kim's team left aggregation explicitly out of scope. Noothigattu's team published their thin fourteen-comparisons-per-voter average and pointed at a better-informed deployment. Awad's team wrote down their critics' objections and conceded the strongest one. bin Ahmad and Takemoto told you their human baseline is a world average that nobody is. The literature keeps marking its own limits. The retellings keep sanding them off.

**Host:** The complete citations are in the show notes, with links to the Zotero files when you have been granted access. Next time: what happens to blame when the machine and the human both get it wrong. Until then — when something agrees with you more strongly than you agree with yourself, that is not alignment. And keep the human in the loop.
