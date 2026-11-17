"""Run 062: verify_feed() must gate the <pubDate> it advertises.

Every feed item carries a <pubDate> and until run 062 NOTHING read it -- the
field appeared zero times in robust_pipeline.py and in no test.
publish_feed.py derives an interview's value from production_dates(), which
mines state.json for the `rendered` (fallback `published`) transition, and
falls back to the LEGACY_PUB_DATE constant 'Wed, 26 Aug 2026 03:45:00 +0000'
whenever no such event exists; a reading falls back to the same constant on an
unparseable `built_at`. That constant is a FAILURE SENTINEL in exactly the
sense duration()'s "00:00:00" is, and a fully-produced episode shipping it
advertises itself ~2.5 months older than it is.

A feed is ordered by this field, so a sentinel date buries a new episode below
the whole back catalogue in every date-sorted client and a future date pins an
item to the top forever -- while the enclosure, duration, cover and
deployed-item-set checks all pass. verify_feed() is publish_local()'s gate and
push_to_remote()'s success criterion, so the advertised date is compared here
against the production event the durable registries record.

No waiver for a legacy import (run 036 -- a waiver is a gate with the sign
flipped). A genuine import is accommodated by EVIDENCE instead: the registries
hold no dated production event for it, which is exactly why publish_feed.py
emits the sentinel, so there is nothing to compare.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

GOOD_PUB = "Tue, 03 Nov 2026 23:39:45 +0000"
GOOD_ISO = "2026-11-03T23:39:45Z"
SENTINEL = "Wed, 26 Aug 2026 03:45:00 +0000"

FIXTURE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><description>Show</description><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><image><url>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png</url><title>Moral Machines</title></image>
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">moral-machines-episode-001</guid>{pub}<enclosure url="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/episode-001.mp3" length="{length}" type="audio/mpeg"/><itunes:duration>00:00:02</itunes:duration><itunes:episode>1</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p>]]></content:encoded></item>
</channel></rss>
"""

INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Moral Machines</title></head><body><h1>Moral Machines</h1>'
    '<p><a href="feed.xml">RSS feed</a></p><h2>Episodes</h2><ul>'
    '<li><a href="episode-001.mp3">Episode 001</a></li></ul></body></html>'
)


def _make_mp3(seconds: int = 2) -> bytes:
    """A real, decodable mp3 so the run-058 duration gate can read it."""
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    with tempfile.TemporaryDirectory() as box:
        out = Path(box) / "f.mp3"
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi",
             "-i", "anullsrc=r=22050:cl=mono", "-t", str(seconds),
             "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
            capture_output=True, check=True)
        return out.read_bytes()


_MP3 = _make_mp3()


class PubDateGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="pubdate_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        self.audio = self.site / "episode-001.mp3"
        self.audio.write_bytes(_MP3)
        cover = b"\x89PNG\r\n\x1a\n" + b"art" * 32
        (self.site / "cover.png").write_bytes(cover)
        (self.dir / "cover.png").write_bytes(cover)
        (self.site / "index.html").write_text(INDEX_HTML)
        (self.site / "episode-001-notes.md").write_text("# notes\n")
        self.feed = self.site / "feed.xml"
        self._root = rp.ROOT
        rp.ROOT = self.dir
        self.addCleanup(lambda: setattr(rp, "ROOT", self._root))
        self.ledger = self.dir / "state.json"
        self._ledger = rp.LEDGER_PATH
        rp.LEDGER_PATH = self.ledger
        self.addCleanup(lambda: setattr(rp, "LEDGER_PATH", self._ledger))
        self._read = rp.READ_MANIFEST_PATH
        rp.READ_MANIFEST_PATH = self.dir / "read-episodes.json"
        self.addCleanup(lambda: setattr(rp, "READ_MANIFEST_PATH", self._read))
        self.write_ledger(GOOD_ISO)
        self.write_feed(GOOD_PUB)

    # ------------------------------------------------------------- helpers
    def write_feed(self, pub):
        element = "" if pub is None else f"<pubDate>{pub}</pubDate>"
        self.feed.write_text(FIXTURE_FEED.format(
            pub=element, length=self.audio.stat().st_size))

    def write_ledger(self, rendered_at):
        """A produced episode, or (rendered_at=None) a genuine import with no
        dated production event -- the only case publish_feed.py emits the
        LEGACY_PUB_DATE sentinel for."""
        if rendered_at is None:
            record = {"status": "published", "transitions": []}
        else:
            record = {"status": "published_and_moved", "transitions": [
                {"from": "rendering", "to": "rendered", "at": rendered_at,
                 "reason": "fixture"}]}
        self.ledger.write_text(json.dumps(
            {"schema_version": 1, "episodes": {"001": record}}))

    def verify(self):
        return rp.verify_feed(self.feed)

    def issues(self):
        return self.verify()["issues"]

    def pubdate_check(self):
        return next(c for c in self.verify()["checks"]
                    if c.get("name") == "pubdate")

    # ------------------------------------------------------------ the gate
    def test_matching_pubdate_passes_and_is_reported(self):
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["issues"], [])
        check = self.pubdate_check()
        self.assertEqual(check["advertised"], GOOD_PUB)
        self.assertIn("rendered", check["expected_source"])
        self.assertLessEqual(check["drift_seconds"], 1.0)

    def test_the_legacy_sentinel_on_a_produced_episode_is_refused(self):
        """The whole point: the sentinel means "no date was available"."""
        self.write_feed(SENTINEL)
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("pubDate mismatch" in i for i in result["issues"]),
                        result["issues"])

    def test_the_refusal_names_both_dates_and_the_drift(self):
        self.write_feed(SENTINEL)
        issue = next(i for i in self.issues() if "pubDate mismatch" in i)
        self.assertIn(SENTINEL, issue)
        self.assertIn("03 Nov 2026", issue)
        self.assertIn("days apart", issue)
        self.assertIn("ledger rendered transition", issue)

    def test_a_missing_pubdate_is_refused(self):
        self.write_feed(None)
        self.assertTrue(any("has no <pubDate>" in i for i in self.issues()))

    def test_an_empty_pubdate_is_refused(self):
        self.write_feed("")
        self.assertTrue(any("has no <pubDate>" in i for i in self.issues()))

    def test_a_malformed_pubdate_is_refused(self):
        self.write_feed("not a date at all")
        self.assertTrue(any("malformed <pubDate>" in i for i in self.issues()))

    def test_a_far_future_pubdate_is_refused(self):
        future = time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                               time.gmtime(time.time() + 86400 * 400))
        self.write_feed(future)
        self.write_ledger(None)
        self.assertTrue(any("in the future" in i for i in self.issues()),
                        self.issues())

    def test_a_date_disagreeing_with_the_ledger_is_refused(self):
        self.write_ledger("2026-11-05T05:49:35Z")
        self.assertTrue(any("pubDate mismatch" in i for i in self.issues()))

    def test_the_published_transition_is_the_documented_fallback(self):
        """production_dates() falls back to `published`; so must the gate."""
        self.ledger.write_text(json.dumps({"schema_version": 1, "episodes": {
            "001": {"status": "published_and_moved", "transitions": [
                {"from": "verified", "to": "published", "at": GOOD_ISO,
                 "reason": "p"}]}}}))
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        self.assertIn("published", self.pubdate_check()["expected_source"])

    # --------------------------------------------------- nothing granted
    def test_subsecond_formatting_skew_is_tolerated(self):
        self.write_feed("Tue, 03 Nov 2026 23:39:00 +0000")
        self.assertTrue(self.verify()["ok"], self.issues())

    def test_an_equivalent_date_in_another_timezone_is_tolerated(self):
        self.write_feed("Tue, 03 Nov 2026 18:39:45 -0500")
        self.assertTrue(self.verify()["ok"], self.issues())

    def test_a_genuine_import_with_no_production_event_is_accommodated(self):
        """By EVIDENCE, not by waiver: there is nothing to compare."""
        self.write_ledger(None)
        self.write_feed(SENTINEL)
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        # The fixture really is legacy-exempt, so this is the no-waiver case.
        self.assertEqual(result["legacy_exempt_episodes"], ["001"])
        self.assertIn("no production event",
                      self.pubdate_check()["expected_source"])

    def test_an_import_with_no_date_at_all_is_still_refused(self):
        """Run 036: a waiver is a gate with the sign flipped."""
        self.write_ledger(None)
        self.write_feed(None)
        result = self.verify()
        self.assertEqual(result["legacy_exempt_episodes"], ["001"])
        self.assertFalse(result["ok"])
        self.assertTrue(any("has no <pubDate>" in i for i in result["issues"]))

    def test_an_import_with_a_malformed_date_is_still_refused(self):
        self.write_ledger(None)
        self.write_feed("whenever")
        self.assertTrue(any("malformed <pubDate>" in i for i in self.issues()))

    def test_a_corrupt_ledger_does_not_raise(self):
        self.ledger.write_text("{not json")
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])

    # ------------------------------------------------------------ helpers
    def test_parse_rfc2822_rejects_junk_and_accepts_real_dates(self):
        self.assertIsNone(rp._parse_rfc2822(""))
        self.assertIsNone(rp._parse_rfc2822("   "))
        self.assertIsNone(rp._parse_rfc2822("not a date"))
        self.assertIsNone(rp._parse_rfc2822(None))
        self.assertEqual(rp._parse_rfc2822(GOOD_PUB).year, 2026)
        # A naive date is assumed UTC rather than rejected.
        self.assertIsNotNone(rp._parse_rfc2822("Tue, 03 Nov 2026 23:39:45"))

    def test_a_reading_is_dated_from_its_own_registry(self):
        """A reading's pubDate comes from read-episodes.json built_at."""
        rp.READ_MANIFEST_PATH.write_text(json.dumps({"episodes": {
            "501": {"built_at": "2026-11-09T12:00:00+00:00"}}}))
        epoch, origin = rp._expected_pubdate_epoch("501")
        self.assertIsNotNone(epoch)
        self.assertIn("built_at", origin)

    def test_an_unregistered_reading_has_no_expected_date(self):
        epoch, origin = rp._expected_pubdate_epoch("501")
        self.assertIsNone(epoch)
        self.assertEqual(origin, "")

    # ---------------------------------------------------------- read-only
    def test_the_check_writes_nothing(self):
        before = {p.name: p.read_bytes() for p in self.site.iterdir()}
        ledger_before = self.ledger.read_bytes()
        self.verify()
        after = {p.name: p.read_bytes() for p in self.site.iterdir()}
        self.assertEqual(before, after)
        self.assertEqual(ledger_before, self.ledger.read_bytes())


if __name__ == "__main__":
    unittest.main()
