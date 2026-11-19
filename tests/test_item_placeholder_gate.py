"""Run 081: the item-level <title>/<description> VALUE is gated.

Run 038 gated these two fields for EMPTINESS only; nothing read what they say,
while the channel <description> of the SAME NAME was scored against
PLACEHOLDER_DESCRIPTION_TOKENS (run 067). That is run 072's granularity axis:
one field name gated at the channel level and unread at the item level.

publish_feed.py reads an interview item's title and description straight off
pipeline/manifest.json, so an unfilled stub written at registration ships
verbatim as the episode's name and blurb -- the two fields a podcast client
renders before any audio is fetched. No other audit can see it: feedsync
regenerates from the registries and compares bytes, so a bad registry INPUT
regenerates identically forever and committed == regenerated.

These tests drive the REAL verify_feed() against a scratch copy of the
published feed-site, so each one fails if the gate is removed.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

SITE = Path(rp.ROOT) / "feed-site"
FEED = SITE / "feed.xml"


def scratch_site(tmp):
    """Copy feed-site, SYMLINKING the mp3s.

    A scratch tree lives on another filesystem, so os.link fails with
    'Invalid cross-device link'; and enclosures/notes resolve relative to the
    feed's own directory, so a bare cp of feed.xml makes every asset report
    absent and masquerades as the defect under test.
    """
    site = Path(tmp) / "feed-site"
    site.mkdir(parents=True)
    for f in sorted(SITE.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() == ".mp3":
            (site / f.name).symlink_to(f)
        else:
            shutil.copy2(f, site / f.name)
    return site


def verdict_with(item_field_edits):
    """Apply literal feed.xml replacements, then run the real gate."""
    with tempfile.TemporaryDirectory() as tmp:
        site = scratch_site(tmp)
        feed = site / "feed.xml"
        text = feed.read_text()
        for old, new in item_field_edits:
            assert text.count(old) >= 1, f"anchor not found: {old!r}"
            text = text.replace(old, new, 1)
        feed.write_text(text)
        return rp.verify_feed(feed)


FIRST_TITLE = "<title>Should the Crowd Program the Car?</title>"


def first_description():
    text = FEED.read_text()
    m = re.search(r"<item>.*?(<description>.*?</description>)", text, re.S)
    assert m, "no item description found in the published feed"
    return m.group(1)


@unittest.skipUnless(FEED.exists(), "no local feed")
class ItemPlaceholderGateTests(unittest.TestCase):
    """The gate must refuse unfilled boilerplate in either item field."""

    def test_the_published_feed_verifies_clean(self):
        report = rp.verify_feed(FEED)
        self.assertEqual(report["issues"], [])
        self.assertTrue(report["ok"])

    def test_a_placeholder_description_is_refused(self):
        report = verdict_with([(first_description(),
                                "<description>TBD</description>")])
        self.assertFalse(report["ok"])
        self.assertTrue(any("placeholder token" in i and "<description>" in i
                            for i in report["issues"]), report["issues"])

    def test_a_placeholder_title_is_refused(self):
        report = verdict_with([(FIRST_TITLE, "<title>TODO</title>")])
        self.assertFalse(report["ok"])
        self.assertTrue(any("placeholder token" in i and "<title>" in i
                            for i in report["issues"]), report["issues"])

    def test_the_issue_names_the_episode_and_the_token(self):
        report = verdict_with([(FIRST_TITLE, "<title>FIXME</title>")])
        hits = [i for i in report["issues"] if "placeholder token" in i]
        self.assertTrue(hits)
        self.assertTrue(any("001" in i for i in hits), hits)
        self.assertTrue(any("fixme" in i.lower() for i in hits), hits)

    def test_every_declared_token_is_refused_in_the_title(self):
        for token in rp.PLACEHOLDER_DESCRIPTION_TOKENS:
            with self.subTest(token=token):
                report = verdict_with(
                    [(FIRST_TITLE, f"<title>Real {token} Words</title>")])
                self.assertFalse(report["ok"])
                self.assertTrue(
                    any("placeholder token" in i for i in report["issues"]))

    def test_every_declared_token_is_refused_in_the_description(self):
        desc = first_description()
        for token in rp.PLACEHOLDER_DESCRIPTION_TOKENS:
            with self.subTest(token=token):
                report = verdict_with(
                    [(desc, f"<description>Real {token} words.</description>")])
                self.assertFalse(report["ok"])
                self.assertTrue(
                    any("placeholder token" in i for i in report["issues"]))

    def test_a_placeholder_is_refused_regardless_of_case(self):
        for variant in ("TbD", "tBd", "ToDo", "LOREM IPSUM"):
            with self.subTest(variant=variant):
                report = verdict_with(
                    [(FIRST_TITLE, f"<title>Pending {variant}</title>")])
                self.assertFalse(report["ok"])

    def test_both_fields_are_scored_independently(self):
        report = verdict_with([
            (FIRST_TITLE, "<title>TODO</title>"),
            (first_description(), "<description>TBD</description>"),
        ])
        hits = [i for i in report["issues"] if "placeholder token" in i]
        self.assertEqual(len(hits), 2, hits)

    def test_the_issue_says_which_slot_a_listener_sees(self):
        title_report = verdict_with([(FIRST_TITLE, "<title>TBD</title>")])
        self.assertTrue(any("name" in i for i in title_report["issues"]
                            if "placeholder token" in i))
        desc_report = verdict_with([(first_description(),
                                     "<description>TBD</description>")])
        self.assertTrue(any("blurb" in i for i in desc_report["issues"]
                            if "placeholder token" in i))


@unittest.skipUnless(FEED.exists(), "no local feed")
class ItemPlaceholderGateGrantsNothingTests(unittest.TestCase):
    """The gate must detect a defect, never mandate editorial content."""

    def test_the_run_038_emptiness_arm_still_bites(self):
        report = verdict_with([(FIRST_TITLE, "<title></title>")])
        self.assertFalse(report["ok"])
        self.assertTrue(any("empty <title>" in i for i in report["issues"]),
                        report["issues"])

    def test_sibling_show_wording_as_domain_prose_stays_legal(self):
        """'human in the loop' is this show's SUBJECT (episode 003).

        A sibling-NAME arm on an item field would refuse correct copy, so the
        gate deliberately has none -- run 066's 'a guard's form must match the
        field's form', and run 067's refusal to mandate content.
        """
        report = verdict_with([(
            first_description(),
            "<description>On keeping a human in the loop when an automated "
            "system and its driver both make mistakes.</description>")])
        self.assertEqual(
            [i for i in report["issues"] if "placeholder" in i], [])
        self.assertTrue(report["ok"], report["issues"])

    def test_no_length_or_required_content_arm_was_added(self):
        report = verdict_with([(FIRST_TITLE, "<title>Blame</title>")])
        self.assertTrue(report["ok"], report["issues"])

    def test_a_word_merely_containing_a_token_prefix_is_legal(self):
        report = verdict_with([(first_description(),
                                "<description>The Toddler Study.</description>")])
        self.assertTrue(report["ok"], report["issues"])

    def test_an_ordinary_reworded_blurb_is_legal(self):
        report = verdict_with([(
            first_description(),
            "<description>A dramatized interview on crowdsourced moral "
            "preferences and why a preference distribution is not a "
            "decision procedure.</description>")])
        self.assertTrue(report["ok"], report["issues"])

    def test_the_real_published_items_carry_no_placeholder(self):
        report = rp.verify_feed(FEED)
        self.assertEqual(
            [i for i in report["issues"] if "placeholder" in i], [])


if __name__ == "__main__":
    unittest.main()
