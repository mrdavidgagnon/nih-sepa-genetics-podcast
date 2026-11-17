"""Run 070: the channel attribution/classification block is gated.

publish_feed.py writes six channel-level fields on every feed -- <language>,
<copyright>, <itunes:author>, <itunes:type>, <itunes:category> and the
channel-level <itunes:explicit> -- and verify_feed() read NONE of them before
this run, so each shipped with ok: true and an empty issue list.

The sharpest case, and the reason this is not cosmetic: <itunes:author> is an
IDENTITY slot that run 066's FORBIDDEN_SHOW_TITLES never reached, so the
sibling show's prose name could sit there green.
"""
import hashlib
import pathlib
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import robust_pipeline as rp  # noqa: E402

BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"
SIBLING = "Human in the Loop"

CHANNEL_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<rss version="2.0" '
    'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
    'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>'
    '<title>Moral Machines</title>'
    f'<link>{BASE}/</link>'
    '<description>Playful, dramatized interviews synthesizing research on '
    'machine ethics.</description>'
    '{attribution}'
    f'<itunes:image href="{BASE}/cover.png"/>'
    f'<image><url>{BASE}/cover.png</url><title>Moral Machines</title>'
    f'<link>{BASE}/</link></image>\n'
)

FULL_ATTRIBUTION = (
    '<language>en-us</language>'
    '<copyright>\u00a9 2026 Field Day Lab, UW\u2013Madison</copyright>'
    '<itunes:author>Field Day Lab, UW\u2013Madison</itunes:author>'
    '<itunes:explicit>false</itunes:explicit>'
    '<itunes:type>episodic</itunes:type>'
    '<itunes:category text="Education"/>'
)


class ChannelAttributionGateTests(unittest.TestCase):
    """Each of the six fields is read, and the real feed still passes."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="mm_attrib_test_"))
        self.site = self.tmp / "feed-site"
        self.site.mkdir()
        # A scratch tree lands on another filesystem, so os.link fails with
        # 'Invalid cross-device link'. stat()/read() follow a symlink, so the
        # advertised byte lengths and digests are the real ones.
        real = ROOT / "feed-site"
        for f in real.iterdir():
            if f.suffix == ".mp3":
                (self.site / f.name).symlink_to(f)
            elif f.is_file():
                shutil.copy2(f, self.site / f.name)
        self.feed = self.site / "feed.xml"
        self.intact = self.feed.read_text()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # ---------------------------------------------------------------- utils
    def _verify(self):
        return rp.verify_feed(str(self.feed))

    def _sub(self, old, new, count=1):
        text = self.feed.read_text()
        self.assertIn(old, text, "fixture anchor missing")
        self.feed.write_text(text.replace(old, new, count))

    def _check(self, result):
        for c in result["checks"]:
            if c["name"] == "channel_attribution":
                return c
        self.fail("channel_attribution check absent")

    def _assert_refused(self, fragment):
        result = self._verify()
        self.assertFalse(result["ok"], result["issues"])
        self.assertTrue(
            any(fragment in i for i in result["issues"]),
            f"no issue mentions {fragment!r}: {result['issues']}")

    # ------------------------------------------------------- healthy state
    def test_the_real_feed_passes_and_every_field_is_reported(self):
        result = self._verify()
        self.assertTrue(result["ok"], result["issues"])
        check = self._check(result)
        self.assertEqual(check["language"], "en-us")
        self.assertEqual(check["itunes_type"], "episodic")
        self.assertEqual(check["itunes_explicit"], "false")
        self.assertEqual(check["itunes_categories"], ["Education"])
        self.assertIn("Field Day Lab", check["copyright"])
        self.assertIn("Field Day Lab", check["itunes_author"])

    # ------------------------------------------------------------ language
    def test_a_wrong_language_is_refused(self):
        self._sub("<language>en-us</language>", "<language>de-DE</language>")
        self._assert_refused("<language>")

    def test_an_empty_language_is_refused(self):
        self._sub("<language>en-us</language>", "<language></language>")
        self._assert_refused("empty channel <language>")

    def test_a_missing_language_element_is_refused(self):
        self._sub("<language>en-us</language>", "")
        self._assert_refused("no <language> element")

    def test_a_wrong_case_language_is_refused(self):
        self._sub("<language>en-us</language>", "<language>EN-US</language>")
        self._assert_refused("only in case")

    # ----------------------------------------------------------- copyright
    def test_a_copyright_naming_another_holder_is_refused(self):
        self._sub("<copyright>\u00a9 2026 Field Day Lab, UW\u2013Madison"
                  "</copyright>",
                  "<copyright>\u00a9 2026 Some Other Lab</copyright>")
        self._assert_refused("<copyright>")

    def test_an_empty_copyright_is_refused(self):
        self._sub("<copyright>\u00a9 2026 Field Day Lab, UW\u2013Madison"
                  "</copyright>", "<copyright></copyright>")
        self._assert_refused("empty channel <copyright>")

    def test_a_reworded_rights_line_naming_the_holder_passes(self):
        """A rights line is prose and is legitimately reworded."""
        self._sub("<copyright>\u00a9 2026 Field Day Lab, UW\u2013Madison"
                  "</copyright>",
                  "<copyright>Copyright 2026, Field Day Lab. All rights "
                  "reserved.</copyright>")
        result = self._verify()
        self.assertTrue(result["ok"], result["issues"])

    def test_a_copyright_naming_the_sibling_show_is_refused(self):
        self._sub("<copyright>\u00a9 2026 Field Day Lab, UW\u2013Madison"
                  "</copyright>",
                  f"<copyright>\u00a9 2026 Field Day Lab \u2014 {SIBLING}"
                  "</copyright>")
        self._assert_refused("sibling show")

    # ------------------------------------------------------ itunes:author
    def test_an_author_naming_someone_else_is_refused(self):
        self._sub("<itunes:author>Field Day Lab, UW\u2013Madison"
                  "</itunes:author>",
                  "<itunes:author>Another Group</itunes:author>")
        self._assert_refused("<itunes:author>")

    def test_an_empty_author_is_refused(self):
        self._sub("<itunes:author>Field Day Lab, UW\u2013Madison"
                  "</itunes:author>", "<itunes:author></itunes:author>")
        self._assert_refused("empty channel <itunes:author>")

    def test_a_missing_author_element_is_refused(self):
        self._sub("<itunes:author>Field Day Lab, UW\u2013Madison"
                  "</itunes:author>", "")
        self._assert_refused("no <itunes:author> element")

    def test_the_author_slot_cannot_carry_the_sibling_shows_name(self):
        """Run 066's title guard never reached this slot."""
        self._sub("<itunes:author>Field Day Lab, UW\u2013Madison"
                  "</itunes:author>",
                  f"<itunes:author>{SIBLING}</itunes:author>")
        self._assert_refused("sibling show")

    # -------------------------------------------------------- itunes:type
    def test_serial_is_refused_because_it_reorders_the_catalogue(self):
        self._sub("<itunes:type>episodic</itunes:type>",
                  "<itunes:type>serial</itunes:type>")
        self._assert_refused("oldest-first")

    def test_a_non_enumerated_type_is_refused(self):
        self._sub("<itunes:type>episodic</itunes:type>",
                  "<itunes:type>weekly</itunes:type>")
        self._assert_refused("not one of")

    def test_a_wrong_case_type_is_refused(self):
        self._sub("<itunes:type>episodic</itunes:type>",
                  "<itunes:type>Episodic</itunes:type>")
        self._assert_refused("only in case")

    def test_a_missing_type_element_is_refused(self):
        self._sub("<itunes:type>episodic</itunes:type>", "")
        self._assert_refused("no <itunes:type> element")

    # ---------------------------------------------------- itunes:category
    def test_an_empty_category_attribute_is_refused(self):
        self._sub('<itunes:category text="Education"/>',
                  '<itunes:category text=""/>')
        self._assert_refused("uncategorised")

    def test_a_missing_category_element_is_refused(self):
        self._sub('<itunes:category text="Education"/>', "")
        self._assert_refused("no <itunes:category> element")

    def test_a_misspelled_category_is_refused(self):
        self._sub('<itunes:category text="Education"/>',
                  '<itunes:category text="Educational"/>')
        self._assert_refused("Apple's vocabulary")

    def test_an_additional_category_alongside_the_required_one_passes(self):
        self._sub('<itunes:category text="Education"/>',
                  '<itunes:category text="Education"/>'
                  '<itunes:category text="Science"/>')
        result = self._verify()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(self._check(result)["itunes_categories"],
                         ["Education", "Science"])

    # ---------------------------------------------------- itunes:explicit
    def test_a_wrong_explicit_value_is_refused(self):
        self._sub("<itunes:explicit>false</itunes:explicit>",
                  "<itunes:explicit>true</itunes:explicit>")
        self._assert_refused("<itunes:explicit>")

    def test_a_non_boolean_explicit_is_refused(self):
        self._sub("<itunes:explicit>false</itunes:explicit>",
                  "<itunes:explicit>maybe</itunes:explicit>")
        self._assert_refused("not one of")

    def test_a_missing_channel_explicit_element_is_refused(self):
        self._sub("<itunes:explicit>false</itunes:explicit>", "")
        self._assert_refused("no <itunes:explicit> element")

    # -------------------------------------------------- nothing granted
    def test_the_gate_writes_nothing(self):
        before = hashlib.md5(self.feed.read_bytes()).hexdigest()
        self._verify()
        self.assertEqual(hashlib.md5(self.feed.read_bytes()).hexdigest(),
                         before)

    def test_no_legacy_waiver_exists_for_these_fields(self):
        """Run 036: a waiver is a gate with the sign flipped.

        Channel fields are not a property of any one episode, so no ledger
        status can excuse them. Proved by refusing while the ledger's only
        legacy-eligible status is in play.
        """
        self._sub("<language>en-us</language>", "<language>de-DE</language>")
        result = self._verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("<language>" in i for i in result["issues"]))

    def test_item_level_explicit_is_not_mistaken_for_the_channels(self):
        """Items carry their own <itunes:explicit>; only the channel's counts.

        The channel element is removed while every item keeps its own, so a
        gate reading the wrong one would pass.
        """
        self._sub("<itunes:explicit>false</itunes:explicit>", "", 1)
        text = self.feed.read_text()
        self.assertIn("<itunes:explicit>false</itunes:explicit>", text,
                      "item-level explicit should survive")
        self._assert_refused("no <itunes:explicit> element")

    def test_a_feed_with_no_channel_does_not_raise(self):
        self.feed.write_text(
            '<?xml version="1.0"?><rss version="2.0"></rss>')
        result = rp.verify_feed(str(self.feed))
        self.assertIsInstance(result, dict)
        self.assertIn("checks", result)

    def test_the_check_is_reported_even_when_it_refuses(self):
        self._sub("<language>en-us</language>", "<language></language>")
        result = self._verify()
        self.assertFalse(result["ok"])
        self._check(result)

    def test_feed_still_parses_as_xml_after_every_probe(self):
        ET.fromstring(self.feed.read_text())


if __name__ == "__main__":
    unittest.main()
