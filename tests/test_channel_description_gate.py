"""Run 068: the channel <description> -- the show's own blurb -- is gated.

Run 066 gated the four show-NAME slots. The blurb was the fifth slot run 004
retargeted off the sibling show by hand, and it had zero readers, while the
item-level <description> of the same name was gated by run 038.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import robust_pipeline as rp  # noqa: E402

TREE = Path(__file__).resolve().parent.parent
LIVE_FEED = TREE / "feed-site" / "feed.xml"
SIBLING_DESC = ("Playful, dramatized interviews synthesizing research about "
                "learning, technology, and human judgment. Private unlisted "
                "review feed.")


def _feed_with(desc=None, drop=False):
    """The real feed XML with the channel description replaced or removed."""
    xml = LIVE_FEED.read_text()
    if drop:
        return re.sub(r"<description>Playful.*?</description>", "", xml, count=1)
    return re.sub(
        r"(<channel>.*?)<description>Playful.*?</description>",
        lambda m: m.group(1) + "<description>" + desc + "</description>",
        xml, count=1, flags=re.S)


def _channel_desc(xml):
    ch = ET.fromstring(xml).find("channel")
    el = ch.find("description") if ch is not None else None
    return (el.text or "").strip() if el is not None else None


class ChannelDescriptionConstantsTests(unittest.TestCase):
    def test_no_required_content_arm_exists(self):
        """The gate tests what is WRONG; it does not prescribe the blurb.

        An earlier draft demanded a project anchor and 16 pre-existing
        fixtures in four other gate suites failed on it -- the evidence that
        it mandated editorial content rather than detecting a defect.
        """
        self.assertFalse(hasattr(rp, "SHOW_DESCRIPTION_REQUIRED"))

    def test_sibling_blurb_phrase_is_forbidden(self):
        self.assertIn("learning, technology, and human judgment",
                      rp.FORBIDDEN_SHOW_DESCRIPTIONS)

    def test_sibling_blurb_names_neither_show(self):
        """Why a third representation is needed: name guards cannot see it."""
        self.assertNotIn("Human in the Loop", SIBLING_DESC)
        self.assertNotIn("human-in-the-loop", SIBLING_DESC.lower())

    def test_placeholder_tokens_present(self):
        for token in ("todo", "tbd", "lorem ipsum"):
            self.assertIn(token, rp.PLACEHOLDER_DESCRIPTION_TOKENS)

    def test_placeholder_tokens_are_lowercase_for_casefolded_matching(self):
        for token in rp.PLACEHOLDER_DESCRIPTION_TOKENS:
            self.assertEqual(token, token.lower())


class ChannelDescriptionGateTests(unittest.TestCase):
    """verify_feed() must refuse each reachable class, naming it."""

    def _issues(self, **kw):
        feed = Path(self.tmp) / "feed.xml"
        feed.write_text(_feed_with(**kw))
        return rp.verify_feed(feed)["issues"]

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _assert_names(self, fragment, **kw):
        issues = self._issues(**kw)
        self.assertTrue(any(fragment in i for i in issues),
                        f"no issue naming {fragment!r}; got {issues}")

    def test_sibling_blurb_refused(self):
        self._assert_names("sibling show's blurb phrasing", desc=SIBLING_DESC)

    def test_empty_description_refused(self):
        self._assert_names("empty channel <description>", desc="")

    def test_missing_element_refused(self):
        self._assert_names("no <description> element", drop=True)

    def test_placeholder_refused(self):
        self._assert_names("placeholder token",
                           desc="TODO: describe this podcast. NIH SEPA.")

    def test_placeholder_refused_wrong_case(self):
        """An identity placeholder is refused whatever its case."""
        self._assert_names("placeholder token", desc="ToDo. NIH SEPA.")

    def test_sibling_show_name_in_blurb_refused(self):
        self._assert_names("names the sibling show",
                           desc="Human in the Loop. NIH SEPA feed.")

    def test_topic_only_blurb_is_not_refused(self):
        """No content mandate: a blurb need not name the grant."""
        issues = [i for i in self._issues(
            desc="Dramatized interviews on machine ethics. Private feed.")
            if "<description>" in i]
        self.assertEqual(issues, [])

    def test_no_legacy_waiver(self):
        """run 036: a waiver is a gate with the sign flipped."""
        feed = Path(self.tmp) / "feed.xml"
        feed.write_text(_feed_with(desc=""))
        result = rp.verify_feed(feed)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("legacy_exempt_episodes"), [])


class ChannelDescriptionNothingGrantedTests(unittest.TestCase):
    """The gate must not false-fail ordinary editorial prose."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _issues_for(self, desc):
        """Description-scoped issues, scored against a feed-site that holds
        the real assets.

        Harness note: an earlier version wrote feed.xml into a bare temp dir,
        so the cover/enclosure/notes/index probes all reported missing files
        and swamped the verdict -- a harness bug that reads exactly like the
        gate false-failing (run 029's rule).
        """
        site = Path(tempfile.mkdtemp(dir=self.tmp))
        for p in LIVE_FEED.parent.iterdir():
            if p.is_file() and p.name != "feed.xml":
                try:
                    os.symlink(p, site / p.name)
                except OSError:
                    shutil.copy2(p, site / p.name)
        feed = site / "feed.xml"
        feed.write_text(_feed_with(desc=desc))
        return [i for i in rp.verify_feed(feed)["issues"]
                if "<description>" in i]

    def test_live_feed_description_satisfies_the_gate(self):
        desc = _channel_desc(LIVE_FEED.read_text())
        self.assertTrue(desc)
        self.assertEqual(self._issues_for(desc), [])

    def test_editorial_rewording_passes(self):
        """Not an exact-match guard: a blurb is prose and gets reworded."""
        self.assertEqual(self._issues_for(
            "Dramatized research interviews on the ethics of automated "
            "decision-making, built for the 2026 NIH SEPA project. Private "
            "unlisted review feed."), [])

    def test_topic_may_broaden_without_failing(self):
        """The parent collection already reaches past AV ethics."""
        self.assertEqual(self._issues_for(
            "Interviews on bioethics and genome-editing governance."), [])

    def test_gate_records_the_blurb_length(self):
        """run 042: a field with no reader is the defect; prove one exists."""
        result = rp.verify_feed(LIVE_FEED)
        identity = [c for c in result["checks"] if c["name"] == "show_identity"]
        self.assertEqual(len(identity), 1)
        self.assertGreater(identity[0]["channel_description_chars"], 0)

    def test_adds_no_new_check_name(self):
        """One identity, one owner: this folds into show_identity."""
        names = sorted(c["name"] for c in rp.verify_feed(LIVE_FEED)["checks"])
        self.assertEqual(names.count("show_identity"), 1)

    def test_live_feed_still_passes_entirely(self):
        self.assertTrue(rp.verify_feed(LIVE_FEED)["ok"])


if __name__ == "__main__":
    unittest.main()
