"""Run 057: verify_feed() must check the cover art the feed advertises.

The feed names cover.png in five slots (channel <itunes:image>, channel
<image><url>, one <itunes:image> per item) and until run 057 no gate read any
of them, while publish_feed.py has no copy site for the cover -- so the tree
root and feed-site/ copies are hand-kept in sync. A missing, empty, drifted or
404ing cover shipped with verify_feed() returning ok: true and an empty issue
list, which is also push_to_remote()'s success criterion.
"""
import json
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

FIXTURE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><description>Show</description><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><image><url>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png</url><title>Moral Machines</title></image>
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">moral-machines-episode-001</guid><enclosure url="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/episode-001.mp3" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>1</itunes:episode><itunes:duration>00:00:02</itunes:duration><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p>]]></content:encoded></item>
</channel></rss>
"""


def _make_fixture_mp3() -> bytes:
    """Tiny real mp3 (2s silence) so the run-058 duration gate can decode it."""
    import subprocess
    import sys as _sys
    _sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    with tempfile.TemporaryDirectory() as box:
        out = Path(box) / "f.mp3"
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi",
             "-i", "anullsrc=r=22050:cl=mono", "-t", "2",
             "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
            capture_output=True, check=True)
        return out.read_bytes()


_FIXTURE_MP3 = _make_fixture_mp3()


INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Moral Machines</title></head><body>'
    '<h1>Moral Machines</h1>'
    '<p><a href="feed.xml">RSS feed</a></p><h2>Episodes</h2><ul>'
    '<li><a href="episode-001.mp3">Episode 001</a></li>'
    '</ul></body></html>'
)

class CoverArtGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cover_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        self.audio = self.site / "episode-001.mp3"
        # A REAL decodable 2-second mp3: run 058 gates <itunes:duration>
        # against the decoded audio, so a fixture of ID3 padding is an
        # incomplete fixture rather than a cover-art finding.
        self.audio.write_bytes(_FIXTURE_MP3)
        self.cover_bytes = b"\x89PNG\r\n\x1a\n" + b"art" * 32
        (self.site / "cover.png").write_bytes(self.cover_bytes)
        # A real feed-site/ always carries the landing page
        # publish_feed.py writes; run 060 gates it, so a fixture
        # without one is incomplete rather than a cover finding.
        (self.site / "index.html").write_text(INDEX_HTML)
        self.feed = self.site / "feed.xml"
        self.feed.write_text(FIXTURE_FEED.format(length=self.audio.stat().st_size))
        # ROOT is module-level; point it at our scratch tree for the
        # root-vs-deployed drift comparison.
        self._root = rp.ROOT
        rp.ROOT = self.dir
        self.addCleanup(lambda: setattr(rp, "ROOT", self._root))
        (self.dir / "cover.png").write_bytes(self.cover_bytes)
        # <pubDate> is gated since run 062 against the production event the
        # durable ledger records, so the fixture carries its own scratch
        # ledger: without it the check would read this tree's real
        # pipeline/state.json for episode 001 and compare a scratch feed
        # against live production history.
        self.ledger = self.dir / "state.json"
        self.ledger.write_text(json.dumps({"schema_version": 1, "episodes": {
            "001": {"status": "published_and_moved", "transitions": [
                {"from": "rendering", "to": "rendered",
                 "at": "2026-11-03T23:39:45Z", "reason": "fixture"}]}}}))
        self._ledger = rp.LEDGER_PATH
        rp.LEDGER_PATH = self.ledger
        self.addCleanup(lambda: setattr(rp, "LEDGER_PATH", self._ledger))

    def verify(self):
        return rp.verify_feed(str(self.feed))

    # ---------------------------------------------------------- healthy
    def test_intact_cover_passes_and_is_reported(self):
        result = self.verify()
        cover = [c for c in result["checks"] if c.get("name") == "cover_art"]
        self.assertEqual(len(cover), 1)
        self.assertEqual(cover[0]["files"], ["cover.png"])
        self.assertNotIn("cover", json.dumps(result["issues"]).lower())

    def test_root_and_deployed_digests_recorded(self):
        cover = [c for c in self.verify()["checks"]
                 if c.get("name") == "cover_art"][0]
        self.assertEqual(cover["root_sha256"], cover["site_sha256"])
        self.assertEqual(cover["local_bytes"], len(self.cover_bytes))

    # ---------------------------------------------------------- refusals
    def test_missing_cover_is_an_issue(self):
        (self.site / "cover.png").unlink()
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing local cover art" in i and "cover.png" in i
                            for i in result["issues"]), result["issues"])

    def test_empty_cover_is_an_issue(self):
        (self.site / "cover.png").write_bytes(b"")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("is empty" in i for i in result["issues"]),
                        result["issues"])

    def test_drift_between_root_and_feed_site_is_an_issue(self):
        (self.site / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\ndifferent")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("differs between the tree root and feed-site/" in i
                            and "edit both" in i for i in result["issues"]),
                        result["issues"])

    def test_absent_root_copy_is_not_an_issue(self):
        """The feed never references the root copy, so its absence is benign."""
        (self.dir / "cover.png").unlink()
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])

    def test_feed_with_no_cover_reference_is_an_issue(self):
        self.feed.write_text(self.feed.read_text()
                             .replace('<itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/>', "")
                             .replace("<image><url>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png</url><title>Moral Machines</title></image>", ""))
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertIn("feed advertises no cover art", result["issues"])

    # ---------------------------------------------------------- no waiver
    def test_legacy_item_gets_no_cover_waiver(self):
        """A waiver is a gate with the sign flipped (run 036)."""
        (self.site / "cover.png").unlink()
        original = rp._legacy_episode_numbers
        rp._legacy_episode_numbers = lambda: {"001"}
        self.addCleanup(lambda: setattr(rp, "_legacy_episode_numbers", original))
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing local cover art" in i
                            for i in result["issues"]), result["issues"])

    # ------------------------------------------------- nothing granted
    def test_existing_enclosure_gate_still_bites(self):
        self.audio.unlink()
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("enclosure" in i for i in result["issues"]))

    def test_existing_empty_description_gate_still_bites(self):
        self.feed.write_text(self.feed.read_text()
                             .replace("<description>Desc one</description>",
                                      "<description></description>"))
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("empty <description>" in i
                            for i in result["issues"]), result["issues"])


if __name__ == "__main__":
    unittest.main()
