"""Run 060: verify_feed() must gate the landing page it deploys.

publish_feed.py writes feed-site/index.html on every publish and
push_to_remote() syncs the whole feed-site/ directory to the repo root, so the
page is a deployed deliverable exactly like feed.xml, the enclosures, the show
notes and the cover art. Until run 060 NOTHING read it: robust_pipeline.py
contained zero references to it, so deleting it, emptying it, corrupting it to
binary junk, or drifting it until it advertised episodes the feed does not
carry all returned ok: true with an EMPTY issue list -- the verdict
publish_local() refuses on and push_to_remote()'s wait loop breaks on.

The real tree was shipping a live dead link at the time: the page linked
needs-full-text.html, a file that has never existed here, inherited from the
sibling show whose feed-site really does carry it.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

FIXTURE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><link>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/</link><description>Show</description><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><image><url>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png</url><title>Moral Machines</title><link>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/</link></image>
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">moral-machines-episode-001</guid><enclosure url="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/episode-001.mp3" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>1</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:duration>00:00:02</itunes:duration><itunes:explicit>false</itunes:explicit><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p>]]></content:encoded></item>
</channel></rss>
"""

PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<title>Moral Machines</title></head><body><h1>Moral Machines</h1>'
        '<p><a href="feed.xml">RSS feed</a></p><ul>'
        '<li><a href="episode-001.mp3">Episode 001</a></li>'
        '</ul></body></html>')


def _make_mp3(seconds: int = 2) -> bytes:
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


class IndexPageGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="index_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        self.audio = self.site / "episode-001.mp3"
        self.audio.write_bytes(_MP3)
        cover = b"\x89PNG\r\n\x1a\n" + b"art" * 32
        (self.site / "cover.png").write_bytes(cover)
        (self.dir / "cover.png").write_bytes(cover)
        self.index = self.site / "index.html"
        self.index.write_text(PAGE)
        self.feed = self.site / "feed.xml"
        self.feed.write_text(FIXTURE_FEED.format(
            length=self.audio.stat().st_size))
        self._root = rp.ROOT
        rp.ROOT = self.dir
        self.addCleanup(lambda: setattr(rp, "ROOT", self._root))
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

    def issues(self):
        return self.verify()["issues"]

    # ---------------------------------------------------------- healthy
    def test_intact_page_passes_and_is_reported(self):
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        checks = [c for c in result["checks"] if c.get("name") == "index_page"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["page_episodes"], ["001"])
        self.assertEqual(checks[0]["feed_episodes"], ["001"])

    def test_page_may_link_itself(self):
        self.index.write_text(PAGE.replace(
            "<ul>", '<ul><li><a href="index.html">home</a></li>'))
        self.assertTrue(self.verify()["ok"], self.issues())

    # ---------------------------------------------------------- refusals
    def test_missing_page_is_refused(self):
        self.index.unlink()
        issues = self.issues()
        self.assertFalse(self.verify()["ok"])
        self.assertTrue(any("missing local landing page" in i for i in issues),
                        issues)

    def test_empty_page_is_refused(self):
        self.index.write_text("")
        issues = self.issues()
        self.assertTrue(any("is empty" in i for i in issues), issues)

    def test_non_html_page_is_refused(self):
        self.index.write_bytes(b"\x00 not html \xff")
        issues = self.issues()
        self.assertTrue(any("is not HTML" in i for i in issues), issues)

    def test_dead_local_link_is_refused(self):
        self.index.write_text(PAGE.replace(
            'href="feed.xml"', 'href="needs-full-text.html"'))
        issues = self.issues()
        self.assertTrue(
            any("links needs-full-text.html" in i for i in issues), issues)

    def test_page_advertising_an_episode_the_feed_lacks_is_refused(self):
        self.index.write_text(PAGE.replace(
            "<ul>", '<ul><li><a href="episode-099.mp3">099</a></li>'))
        issues = self.issues()
        self.assertTrue(
            any("advertises episode 099" in i for i in issues), issues)

    def test_page_omitting_a_feed_episode_is_refused(self):
        self.index.write_text(PAGE.replace(
            '<li><a href="episode-001.mp3">Episode 001</a></li>', ""))
        issues = self.issues()
        self.assertTrue(any("omits episode 001" in i for i in issues), issues)

    # ---------------------------------------------------------- no waiver
    def test_a_legacy_import_does_not_waive_the_landing_page(self):
        """Run 036: a waiver is a gate with the sign flipped."""
        ledger = self.dir / "state.json"
        ledger.write_text(json.dumps(
            {"episodes": {"001": {"status": "published"}}}))
        original = rp.LEDGER_PATH
        rp.LEDGER_PATH = ledger
        try:
            self.index.unlink()
            result = self.verify()
            # The fixture really is legacy-exempt...
            self.assertEqual(result["legacy_exempt_episodes"], ["001"])
            # ...and the landing page is refused anyway.
            self.assertFalse(result["ok"])
            self.assertTrue(
                any("missing local landing page" in i
                    for i in result["issues"]), result["issues"])
        finally:
            rp.LEDGER_PATH = original

    # ---------------------------------------------------------- read-only
    def test_the_check_writes_nothing(self):
        before = {p.name: p.read_bytes() for p in self.site.iterdir()
                  if p.is_file()}
        self.verify()
        after = {p.name: p.read_bytes() for p in self.site.iterdir()
                 if p.is_file()}
        self.assertEqual(before, after)


class PublishFeedIndexTemplateTests(unittest.TestCase):
    """The generated page must not link the sibling show's queue file."""

    def test_template_has_no_needs_full_text_link(self):
        src = (Path(__file__).resolve().parents[1]
               / "pipeline" / "publish_feed.py").read_text()
        self.assertIn("atomic_text(SITE/'index.html'", src)
        self.assertNotIn("needs-full-text", src)

    def test_template_links_the_feed(self):
        src = (Path(__file__).resolve().parents[1]
               / "pipeline" / "publish_feed.py").read_text()
        self.assertIn('<a href="feed.xml">RSS feed</a>', src)


if __name__ == "__main__":
    unittest.main()
