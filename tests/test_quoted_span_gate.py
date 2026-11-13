"""Tests for pipeline/quoted_span_gate.py.

Two directions, both load-bearing:

  * A real quotation must VERIFY through every PDF-extraction artefact the
    pipeline has actually hit (hyphen-at-linebreak, whole-word line wrap,
    list-initial capitalization, spurious intra-word space). A checker that
    false-fails here reads exactly like a fabricated citation, which is the
    most dangerous false positive this gate can produce.

  * Tampering must still be REJECTED despite the permissive alnum fallback:
    invented sentences, words dropped inside quotation marks, a single word
    swapped, a transposed digit, and permuted word order.

Fixtures marked "real" are verbatim from episode source text.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import quoted_span_gate as G


class NoFalseFailTests(unittest.TestCase):
    """Correct quotations survive every extraction artefact."""

    def assert_verifies(self, source, quoted):
        text = f'The Host says "{quoted}" aloud.'
        result = G.verify_text(source, text)
        self.assertTrue(result["ok"], f"false-fail on {quoted!r}: {result['unverified']}")

    def test_hyphen_at_linebreak_real_hyphen(self):
        # Game-\nBased must still match Game-Based (run 482).
        self.assert_verifies(
            "the chapter Foundations of Game-\nBased Learning in the handbook",
            "Foundations of Game-Based Learning",
        )

    def test_hyphen_at_linebreak_split_word(self):
        # measure-\nment must match measurement.
        self.assert_verifies(
            "we report the measure-\nment of epistemic emotions",
            "the measurement of epistemic emotions",
        )

    def test_whole_word_line_wrap(self):
        # No hyphen view closes a newline between whole words (run 483).
        self.assert_verifies(
            "in the Eurasian Journal of Science and\nEnvironmental Education, volume 9",
            "Eurasian Journal of Science and Environmental Education",
        )

    def test_list_initial_capitalization(self):
        # Source prints it list-initial; the script quotes it lowercase (run 484).
        self.assert_verifies(
            "The conclusion lists: (1) Find a promising sector, then validate demand.",
            "find a promising sector",
        )

    def test_spurious_intra_word_space(self):
        # real: the 048 source contains "human e motions" (run 488).
        self.assert_verifies(
            "Pekrun, R.: Control-value theory: From achievement emotion to a "
            "general theory of \nhuman e motions. Educ. Psych. Rev. (2024)",
            "Control-Value Theory: From Achievement Emotion to a General Theory "
            "of Human Emotions",
        )

    def test_spurious_intra_word_space_with_hyphen_wrap(self):
        # real: "epistemically-\nrelated e motion scales" (run 488).
        self.assert_verifies(
            "Measuring emotions during epistemic activities: The epistemically-\n"
            "related e motion scales. Emotion Review (2017)",
            "Measuring emotions during epistemic activities: the "
            "Epistemically-Related Emotion Scales",
        )

    def test_hyphenated_word_split_plus_intra_word_space(self):
        # real: "person-\nalizing f eedback strategies" (run 488).
        self.assert_verifies(
            "Exploring feedback and student characteristics relevant for person-\n"
            "alizing f eedback strategies",
            "Exploring feedback and student characteristics relevant for "
            "personalizing feedback strategies",
        )

    def test_smart_quotes_and_dashes_fold(self):
        self.assert_verifies(
            "the authors\u2019 own term \u201cmotivational conflict\u201d appears",
            "motivational conflict",
        )


class TamperingRejectedTests(unittest.TestCase):
    """The alnum fallback must not forgive substantive differences."""

    def check(self, source, quoted):
        text = f'The Host says "{quoted}" aloud.'
        return G.verify_text(source, text)

    def test_invented_sentence_rejected(self):
        result = self.check(
            "The system prompt instructed the model to answer concisely.",
            "Please keep it to two to four sentences",
        )
        self.assertFalse(result["ok"])

    def test_words_dropped_inside_quotes_rejected(self):
        # run 474: two words dropped inside quotation marks.
        result = self.check(
            "television can teach specific lessons when it is intentionally "
            "designed to do so",
            "television can teach specific lessons when intentionally designed to do so",
        )
        self.assertFalse(result["ok"])

    def test_single_word_swapped_rejected(self):
        result = self.check(
            "We observed a significant increase in motivational conflict.",
            "a significant decrease in motivational conflict",
        )
        self.assertFalse(result["ok"])

    def test_transposed_digit_rejected(self):
        result = self.check(
            "Participants numbered 162 before exclusions and 123 after.",
            "162 before exclusions and 132 after",
        )
        self.assertFalse(result["ok"])

    def test_permuted_word_order_rejected(self):
        result = self.check(
            "the skills, difficulty, value, efficacy and time model",
            "the value, skills, difficulty, efficacy and time model",
        )
        self.assertFalse(result["ok"])

    def test_added_clause_rejected(self):
        result = self.check(
            "the number of potential relationships can become very large",
            "the number of potential relationships can become very large, "
            "about a hundred possible lines",
        )
        self.assertFalse(result["ok"])


class ApparatusTests(unittest.TestCase):

    def test_whitelist_suppresses_only_named_span(self):
        source = "nothing relevant here"
        text = 'He said "alpha beta gamma" and also "delta epsilon zeta".'
        result = G.verify_text(source, text, whitelist=["alpha beta gamma"])
        self.assertEqual(result["unverified"], ["delta epsilon zeta"])

    def test_four_source_views_present(self):
        self.assertEqual(len(G.source_views("a-\nb c")), 4)

    def test_short_spans_ignored(self):
        # Under 4 chars is not a meaningful quotation.
        result = G.verify_text("nothing here", 'he said "ok" twice')
        self.assertEqual(result["spans"], 0)

    def test_span_crossing_newline_not_captured(self):
        result = G.verify_text("nothing here", 'he said "alpha\nbeta gamma" once')
        self.assertEqual(result["spans"], 0)

    def test_alnum_only_drops_punctuation_and_case(self):
        self.assertEqual(G.alnum_only("Game-Based  Learning!"), "gamebasedlearning")

    def test_reports_span_count_and_ok_flag(self):
        result = G.verify_text("alpha beta gamma delta", 'x "alpha beta" y')
        self.assertEqual(result["spans"], 1)
        self.assertTrue(result["ok"])


class MoralMachinesRegressionTests(unittest.TestCase):
    """Real spans from this tree's catalogue (run 047).

    Episode 001 quoted a scale label as "good for other people to have" while
    Awad/Bonnefon's text reads "a good ALGORITHM for other people to have" -- a
    word dropped inside quotation marks, which is the run-474 class and exactly
    what this gate exists to catch. The surrounding sentence is reproduced with
    the real PDF-extraction artefacts (spaced "A V", ligature in "signiﬁcantly")
    so the fixture exercises the normalization path, not a sanitized string.
    """

    SOURCE = (
        "The algorithm that would kill its passenger to save 10 presented a "
        "hybrid proﬁle. Just as the high-valued algorithm, it received high "
        "marks for morality (median budget share = 50), and was considered a "
        "good algorithm for other people to have (median budget share = 50). "
        "But in terms of purchase intention, it received signiﬁcantly fewer "
        "points than the high-valued algorithm (p < 0.001), and was in fact "
        "closer to the low-valued algorithms (median budget share = 33)."
    )

    def test_dropped_word_inside_quotes_is_rejected(self):
        text = 'scored fifty for "good for other people to have" on air.'
        result = G.verify_text(self.SOURCE, text)
        self.assertFalse(result["ok"])
        self.assertIn("good for other people to have", result["unverified"])

    def test_the_correct_span_verifies(self):
        text = 'considered "a good algorithm for other people to have" by participants.'
        result = G.verify_text(self.SOURCE, text)
        self.assertTrue(result["ok"], result["unverified"])

    def test_own_rhetoric_is_a_whitelist_case_not_a_source_hit(self):
        # 001's "most people feel this way" / "the machine shall do this" are the
        # Host's own framing, absent from every source by design. The gate must
        # still report them (they are source 0) so a human triages them; the
        # benign route is --whitelist, never loosening the check.
        text = 'the step from "most people feel this way" to "the machine shall do this"'
        self.assertFalse(G.verify_text(self.SOURCE, text)["ok"])
        allowed = G.verify_text(self.SOURCE, text,
                                ["most people feel this way", "the machine shall do this"])
        self.assertTrue(allowed["ok"], allowed["unverified"])


class PreflightIntegrationTests(unittest.TestCase):
    """The gate must be reachable from the PUBLISH PATH, not just the CLI.

    Run 047 ported quoted_span_gate.py with zero callers: it was reachable only
    as a hand-typed command, so `publish --episode NNN` could not reach the one
    check in this tree that compares a deliverable against the paper's actual
    words. Every other preflight check scores the script against the citation
    record, which is why a misquote inside quotation marks passed a
    three-reviewer panel and every deterministic gate in published episodes 001
    and 003. These tests pin the call site rather than the module.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rp_under_test",
            Path(__file__).resolve().parents[1] / "pipeline" / "robust_pipeline.py")
        cls.rp = importlib.util.module_from_spec(spec)
        sys.modules["rp_under_test"] = cls.rp
        spec.loader.exec_module(cls.rp)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="span_gate_preflight_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ep = Path(self.tmp) / "episodes" / "007"
        self.ep.mkdir(parents=True)
        (self.ep / "source-AAAA1111.txt").write_text(
            "The secondary driver is considered more causally responsible "
            "than the primary driver. Perceived competence did not mediate "
            "the blame effect.\n")
        (self.ep / "script.md").write_text(
            '**Host:** Welcome.\n\n'
            '**Rowan:** The paper reports that "the secondary driver is '
            'considered more causally responsible" here.\n')
        (self.ep / "episode-notes.md").write_text("Notes.\n")

    def residuals(self, manifest, files=("script.md", "episode-notes.md")):
        """Run just the gate's logic the way preflight() composes it."""
        keys = [str(k) for k in manifest.get("sources", [])]
        whitelist = [str(w) for w in manifest.get("quoted_span_whitelist", [])]
        texts, missing = {}, []
        for key in keys:
            path = self.ep / f"source-{key}.txt"
            if path.exists():
                texts[key] = path.read_text()
            else:
                missing.append(key)
        out = {"missing": missing}
        for name in files:
            text = (self.ep / name).read_text()
            residual = None
            for src in texts.values():
                bad = set(G.verify_text(src, text, whitelist)["unverified"])
                residual = bad if residual is None else (residual & bad)
            out[name] = sorted(residual or set())
        return out

    def test_preflight_defines_a_quoted_spans_check(self):
        import inspect
        source = inspect.getsource(self.rp.preflight)
        self.assertIn("quoted_span_gate", source,
                      "preflight() must import the gate; a CLI-only tool is "
                      "not on the publish path")
        self.assertIn('"quoted_spans"', source)

    def test_real_quotation_passes(self):
        r = self.residuals({"sources": ["AAAA1111"]})
        self.assertEqual(r["script.md"], [])

    def test_invented_author_attributed_quote_is_refused(self):
        p = self.ep / "script.md"
        p.write_text(p.read_text() +
                     '**Rowan:** The authors conclude that "blame is a '
                     'conserved quantity that transfers to the human."\n')
        r = self.residuals({"sources": ["AAAA1111"]})
        self.assertEqual(len(r["script.md"]), 1)
        self.assertIn("conserved quantity", r["script.md"][0])

    def test_dropped_word_inside_quotes_is_refused(self):
        p = self.ep / "script.md"
        p.write_text(p.read_text().replace(
            "the secondary driver is considered more causally responsible",
            "the secondary driver is considered causally responsible"))
        r = self.residuals({"sources": ["AAAA1111"]})
        self.assertEqual(len(r["script.md"]), 1)

    def test_missing_source_extract_is_not_a_waiver(self):
        (self.ep / "source-AAAA1111.txt").unlink()
        r = self.residuals({"sources": ["AAAA1111"]})
        self.assertEqual(r["missing"], ["AAAA1111"],
                         "a missing extract must be reported, never skipped")

    def test_union_of_sources_verifies_across_papers(self):
        """A span quoted from paper A must not be 'missing' because of paper B."""
        (self.ep / "source-BBBB2222.txt").write_text(
            "An unrelated paper about voting rules.\n")
        r = self.residuals({"sources": ["AAAA1111", "BBBB2222"]})
        self.assertEqual(r["script.md"], [])

    def test_whitelist_waives_only_its_own_span(self):
        p = self.ep / "script.md"
        p.write_text(p.read_text() +
                     '**Host:** As I put it, "aggregation is hard."\n'
                     '**Rowan:** They measured "liability exposure directly."\n')
        r = self.residuals({"sources": ["AAAA1111"],
                            "quoted_span_whitelist": ["aggregation is hard."]})
        self.assertEqual(len(r["script.md"]), 1)
        self.assertIn("liability exposure", r["script.md"][0])

    def test_notes_are_checked_against_the_source_not_the_script(self):
        (self.ep / "episode-notes.md").write_text(
            'The notes assert "a mechanism the paper never names."\n')
        r = self.residuals({"sources": ["AAAA1111"]})
        self.assertEqual(len(r["episode-notes.md"]), 1)


if __name__ == "__main__":
    unittest.main()
