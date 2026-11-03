# Episode 001 — Should the Crowd Program the Car?

**Host:** Welcome to Moral Machines, the show about the ethical decisions we are quietly handing to software. I'm your host. Today we start where this whole field started: with a thought experiment that escaped the philosophy seminar and got installed in a car. The trolley problem used to be a way to make undergraduates uncomfortable. Now it's a specification document. And there's a tempting answer to it that I want to spend this episode taking apart — the idea that if nobody can agree on the right thing to do, we should just ask everybody and average it. Here to help me take that apart is our correspondent, Dr. Rowan Field. Rowan, welcome.

**Rowan:** Glad to be here. Quick flag: I'm a fictional correspondent, and this is an AI-generated summary of the papers, so it can be wrong. Read them.

**Host:** Noted. So let's start before the crowdsourcing. Where does this begin?

**Rowan:** It begins with a social dilemma, and I mean that in the technical sense. Jean-François Bonnefon, Azim Shariff, and Iyad Rahwan published "The social dilemma of autonomous vehicles" in Science in 2016 — volume 352, issue 6293. Six online surveys, US respondents recruited from Amazon Mechanical Turk between June and November 2015. And they found a split that should worry anyone writing a regulation. In their first study, with a hundred and eighty-two participants, seventy-six percent said it would be more moral for a car to sacrifice one passenger rather than kill ten pedestrians. Asked how a car should be programmed, on a scale from protect-the-passenger to minimize-casualties, the median answer was eighty-five. Strongly utilitarian.

**Host:** So people want the self-sacrificing car. Case closed?

**Rowan:** That's the trap. The same people, asked what they'd actually buy, moved sharply. When respondents imagined themselves and a family member in the car that would sacrifice them, their reported likelihood of purchase dropped to a median of nineteen, against a median of fifty for the self-protective model. In a later study participants allocated a hundred points across algorithms. The self-sacrificing car scored fifty for morality and fifty for "good for other people to have" — but only thirty-three on purchase intention.

**Host:** They want everyone else to buy the moral car.

**Rowan:** Precisely the signature of a free-riding dilemma. And the authors draw the uncomfortable policy conclusion themselves: mandating utilitarian algorithms could paradoxically increase casualties, by delaying adoption of a technology that is safer overall. The boundary here matters, though. These are six surveys of stated preference from US Mechanical Turk workers, not observed purchasing behavior, and the authors are explicit that Turk respondents aren't a representative national sample. It establishes a conflict in what people say, not a measured market outcome.

**Host:** Which sets up the move to go bigger. Much bigger.

**Rowan:** Enormously bigger. Edmond Awad and colleagues, "The Moral Machine experiment," Nature, October 2018 — the online platform that collected about forty million decisions in ten languages from millions of people across two hundred and thirty-three countries and territories. The design probes nine factors: humans over pets, staying on course versus swerving, passengers versus pedestrians, more lives versus fewer, men versus women, young versus elderly, lawful versus jaywalking pedestrians, fit versus less fit, and higher versus lower social status.

**Host:** And the headline finding?

**Rowan:** Three preferences dominate globally: sparing humans over animals, sparing more lives, and sparing young lives. The authors suggest those three might be essential building blocks for machine ethics. But the more interesting result is the variation. A cluster analysis found three distinct moral clusters of countries — the authors label them Western, Eastern, and Southern. Western covers North America and many European countries of Protestant, Catholic, and Orthodox heritage. Eastern includes Confucian-influenced countries like Japan and Taiwan alongside Islamic countries such as Indonesia, Pakistan, and Saudi Arabia. Southern covers Latin America plus countries with French influence.

**Host:** So geography predicts your trolley answers.

**Rowan:** Culture and institutions do, measurably. Participants from individualistic cultures showed a stronger preference for sparing the greater number. Prosperity, indexed by GDP per capita, and institutional quality, indexed by Rule of Law, correlated with a greater preference against sparing pedestrians who cross illegally — people from poorer countries with weaker institutions were more tolerant of jaywalkers. And higher national economic inequality, by Gini coefficient, corresponded to treating high- and low-status characters more unequally in the game.

**Host:** That last one is bleak. Inequality teaches you to value people unequally.

**Rowan:** That's the authors' suggested reading — regular encounters with inequality seeping into moral preference. And here's where it collides with policy directly. German Ethical Rule number nine prohibits distinctions based on personal features such as age. The Moral Machine data show a strong, consistent preference for sparing the young: the four most-spared characters are the baby, the little girl, the little boy, and the pregnant woman. The paper is careful — it does not conclude policymakers should follow public opinion. It says the clash is something policymakers must knowingly confront.

**Host:** Now, the boundaries on a dataset this big must be substantial.

**Rowan:** They are, and the central one is the sample. This is a self-selected, unrepresentative online convenience sample — people who found a viral MIT website and chose to play. It is extraordinary breadth with no sampling control. It tells you about the people who showed up, and the country-level correlations are correlations, not causal claims about institutions shaping morality.

**Host:** There's a companion paper in the Zotero folder, though, that tightens this up.

**Rowan:** Same team, different instrument. Awad, Dsouza, Shariff, Rahwan, and Bonnefon, "Universals and variations in moral decisions made in 42 countries by 70,000 participants," in the Proceedings of the National Academy of Sciences, volume 117, issue 5, 2020. This uses the Moral Machine site's "Classic" mode — the actual textbook trolley variants: Switch, Loop, and Footbridge. Seventy thousand responses, ten languages, forty-two countries.

**Host:** And this is where I want to be careful, because these two papers get conflated constantly.

**Rowan:** Worth stating clearly: forty million decisions and two hundred thirty-three countries is the 2018 Nature paper on autonomous-vehicle dilemmas. Seventy thousand participants in forty-two countries is the 2020 PNAS paper on classic trolley variants. Different scenarios, different samples, different claims.

**Host:** Thank you. So what did the forty-two-country study find?

**Rowan:** A universal ordering with local volume knobs. Every single country showed the same pattern: sacrifice endorsed most in Switch, at a country-level average of eighty-one percent, then Loop at seventy-two percent, then Footbridge at fifty-one percent. The ordering never flipped anywhere, which the authors argue points to basic cognitive processes rather than cultural norms. But the quantitative acceptability varied substantially by country, and the strongest cultural correlate was relational mobility — in societies where people are more cautious about alienating existing social partners, sacrifices for the greater good were more likely to be rejected, especially in Eastern countries.

**Host:** Universal shape, local amplitude.

**Rowan:** That's a fair compression. And the boundary is the same family of limits — still a self-selected online sample, still correlational on the country-level predictors.

**Host:** All right. So we have this enormous global map of moral preference. The engineering temptation is obvious: turn the map into a function and ship it. What happens when someone checks that math?

**Rowan:** It doesn't survive contact. Michael Feffer, Hoda Heidari, and Zachary Lipton, "Moral Machine or Tyranny of the Majority?", in the Proceedings of the AAAI Conference on Artificial Intelligence, volume 37, issue 5, 2023. They examine a specific proposed mechanism — inferring a linear preference function for each person and then aggregating by averaging those parameters across the population.

**Host:** Sounds democratic enough.

**Rowan:** It isn't. They analyze a deliberately simple setting: two groups, a minority holding some share alpha below one half, homogeneous preferences within each group. Four results. First, even when everyone reports preferences honestly, the share of contested cases the minority wins is less than proportionate to alpha. Second, that sub-proportionality gets worse as disagreement between the groups grows. Third, when people report strategically, pure-strategy equilibria don't always exist. And fourth — this is the one — whenever a pure-strategy equilibrium does exist, the majority group prevails one hundred percent of the time.

**Host:** So averaging doesn't dilute the minority. It erases them.

**Rowan:** In that setting, yes, and worst precisely when the disagreement is deepest — exactly the cases you built the mechanism to resolve. The authors discuss alternatives, including randomized dictatorship and median-based mechanisms. The boundary is important: this is a theoretical analysis of a stylized two-group model with homogeneous within-group preferences, not an empirical audit of a deployed system. It's a proof about a mechanism, and that's enough to disqualify naive averaging.

**Host:** Which brings us to the newest problem, which is that we may not be the ones answering anymore.

**Rowan:** Kazuhiro Takemoto, "The moral machine experiment on large language models," Royal Society Open Science, volume 11, issue 2, 2024. He ran the Moral Machine framework at GPT-3.5, GPT-4, PaLM 2, and Llama 2, and compared their responses to the human preference profile.

**Host:** Do they agree with us?

**Rowan:** Broadly in shape, not in degree. The models align with humans on the big ones — prioritizing humans over pets, favoring saving more lives. PaLM 2 and Llama 2 showed distinct deviations. And across the board there were significant quantitative disparities: the models leaned toward more uncompromising decisions than the milder human inclinations. Same direction, harder edges.

**Host:** Define "uncompromising" for me, because that's doing a lot of work.

**Rowan:** Where a human population produces a soft gradient — a mild preference for sparing the young, say — a model tends to produce something closer to a rule. The preference saturates. Boundary: this is one study, a snapshot of four specific model versions on one scenario battery, and model behavior shifts with versions and prompting. It is not a stable law about machine morality.

**Host:** So let me try to pull the thread. We asked the crowd because experts disagreed. The crowd gave us an answer that varies by culture, correlates with inequality, and clashes with existing law. The mechanism for turning that answer into code mathematically silences minorities. And the systems now in the loop hold the same preferences more rigidly than we do.

**Rowan:** And notice that each step was individually reasonable. Survey people — reasonable. Scale it globally — reasonable. Aggregate into a function — sounds reasonable, provably isn't. Ask the model — increasingly unavoidable. You get a chain of sensible moves ending somewhere nobody chose.

**Host:** So here's my two-sentence abstract. Crowdsourced moral data is real evidence about what people prefer, and it is genuinely informative about how culture and institutions shape those preferences. But a preference distribution is not a decision procedure, and the step from "most people feel this way" to "the machine shall do this" is a political act that no amount of data performs for you.

**Rowan:** I'd add one thing. Every one of these papers is more honest than its own headline. Bonnefon's team flagged that mandates might backfire. Awad's team explicitly declined to say policy should follow public opinion. Feffer's team went looking for the flaw in a mechanism their own field proposed. The literature is not overclaiming. The summaries of it often do.

**Host:** The complete citations are in the show notes, with links to the Zotero files when you have been granted access. Next time, the question underneath all of this: who is accountable when the car does what it was told. Until then — when someone shows you an average, ask who got rounded off. And keep the human in the loop.
