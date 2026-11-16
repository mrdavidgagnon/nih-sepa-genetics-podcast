import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import robust_pipeline as rp  # noqa: E402

BASE = rp.FEED_BASE
SIBLING = "https://mrdavidgagnon.github.io/human-in-the-loop-AI-podcast"

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><link>{base}/</link><description>Show</description><itunes:image href="{base}/cover.png"/><image><url>{base}/cover.png</url><title>Moral Machines</title><link>{base}/</link></image>
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">moral-machines-episode-001</guid><enclosure url="{enclosure}" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>1</itunes:episode><itunes:duration>00:00:02</itunes:duration><itunes:image href="{item_cover}"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p><p><a href="episode-001-notes.md">notes</a></p>]]></content:encoded></item>
</channel></rss>
"""

INDEX = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
         '<title>Moral Machines</title></head><body><h1>Moral Machines</h1>'
         '<p><a href="feed.xml">RSS feed</a></p><ul>'
         '<li><a href="episode-001.mp3">Episode 001</a> '
         '· <a href="episode-001-notes.md">notes</a></li>'
         '</ul></body></html>')


def _silent_mp3(path: Path) -> None:
    """Two seconds of real, decodable audio."""
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i",
         "anullsrc=r=44100:cl=mono", "-t", "2", "-q:a", "9", str(path)],
        check=True, capture_output=True)


class AdvertisedBaseGateTests(unittest.TestCase):
    """verify_feed() must gate the URL PREFIX the feed advertises.

    Until run 063 every check reduced an advertised URL to its basename and
    rebuilt the probe URL from FEED_BASE, so the scheme, host and directory a
    subscriber actually resolves were never compared to anything.
    """

    @classmethod
    def setUpClass(cls):
        cls._audio = Path(tempfile.mkdtemp(prefix="mmbase_audio_")) / "a.mp3"
        _silent_mp3(cls._audio)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._audio.parent, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mmbase_"))
        self.site = self.tmp / "feed-site"
        self.site.mkdir()
        shutil.copy2(self._audio, self.site / "episode-001.mp3")
        (self.site / "episode-001-notes.md").write_text("# notes\n")
        (self.site / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
        (self.site / "index.html").write_text(INDEX)
        ledger = {"episodes": {"001": {
            "status": "published_and_moved",
            "transitions": [{"to": "published",
                             "at": "2026-11-03T23:39:45Z"}]}}}
        (self.tmp / "pipeline").mkdir()
        (self.tmp / "pipeline" / "state.json").write_text(json.dumps(ledger))
        (self.tmp / "pipeline" / "manifest.json").write_text(
            json.dumps({"episodes": {"001": {"status": "published_and_moved",
                                             "title": "Ep One",
                                             "description": "Desc one"}}}))
        self._root, self._ledger = rp.ROOT, rp.LEDGER_PATH
        self._man = rp.MANIFEST_PATH
        rp.ROOT = self.tmp
        rp.LEDGER_PATH = self.tmp / "pipeline" / "state.json"
        rp.MANIFEST_PATH = self.tmp / "pipeline" / "manifest.json"

    def tearDown(self):
        rp.ROOT, rp.LEDGER_PATH = self._root, self._ledger
        rp.MANIFEST_PATH = self._man
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, base=BASE, enclosure=None, item_cover=None):
        length = (self.site / "episode-001.mp3").stat().st_size
        feed = self.site / "feed.xml"
        feed.write_text(FEED.format(
            base=base, length=length,
            enclosure=enclosure or f"{base}/episode-001.mp3",
            item_cover=item_cover or f"{base}/cover.png"))
        return feed

    def _verify(self, **kw):
        return rp.verify_feed(self._write(**kw))

    def _check(self, result):
        return next(c for c in result["checks"]
                    if c.get("name") == "advertised_base")

    # ----------------------------------------------------------- healthy ---
    def test_correct_base_passes_and_is_reported(self):
        result = self._verify()
        self.assertTrue(result["ok"], result["issues"])
        check = self._check(result)
        self.assertEqual(check["expected_bases"], [BASE])
        self.assertEqual(check["distinct_bases"], [BASE])
        self.assertEqual(check["relative"], [])
        self.assertTrue(all(u.startswith(BASE) for u in check["advertised"]))

    def test_the_check_is_always_present(self):
        self.assertIn("advertised_base",
                      {c.get("name") for c in self._verify()["checks"]})

    # ------------------------------------------------------- cross-show ---
    def test_a_cross_show_base_is_refused(self):
        result = self._verify(base=SIBLING)
        self.assertFalse(result["ok"])
        self.assertTrue(any("cross-show" in i for i in result["issues"]),
                        result["issues"])

    def test_a_single_cross_show_enclosure_is_refused(self):
        result = self._verify(enclosure=f"{SIBLING}/episode-001.mp3")
        self.assertFalse(result["ok"])
        self.assertTrue(any("cross-show" in i for i in result["issues"]),
                        result["issues"])

    def test_a_cross_show_item_artwork_is_refused(self):
        result = self._verify(item_cover=f"{SIBLING}/cover.png")
        self.assertFalse(result["ok"])

    # --------------------------------------------------- wrong prefixes ---
    def test_a_wrong_repo_slug_is_refused(self):
        """A path-boundary match, not a bare startswith: ...podcastS must fail."""
        result = self._verify(base=BASE + "s")
        self.assertFalse(result["ok"], result["issues"])
        self.assertTrue(any(BASE + "s" in i for i in result["issues"]),
                        result["issues"])

    def test_a_foreign_host_is_refused(self):
        result = self._verify(base="https://example.invalid/somewhere")
        self.assertFalse(result["ok"])

    def test_a_downgraded_http_scheme_is_refused(self):
        result = self._verify(base=BASE.replace("https://", "http://"))
        self.assertFalse(result["ok"])

    def test_a_relative_enclosure_url_is_refused(self):
        result = self._verify(enclosure="episode-001.mp3")
        self.assertFalse(result["ok"])
        self.assertTrue(any("non-absolute" in i for i in result["issues"]),
                        result["issues"])

    def test_a_relative_item_artwork_url_is_refused(self):
        result = self._verify(item_cover="cover.png")
        self.assertFalse(result["ok"])
        self.assertTrue(any("non-absolute" in i for i in result["issues"]),
                        result["issues"])

    # ------------------------------------------------------ boundary fn ---
    def test_under_advertised_base_requires_a_path_boundary(self):
        self.assertTrue(rp._under_advertised_base(BASE, BASE))
        self.assertTrue(rp._under_advertised_base(BASE + "/", BASE))
        self.assertTrue(rp._under_advertised_base(BASE + "/x.mp3", BASE))
        self.assertFalse(rp._under_advertised_base(BASE + "s", BASE))
        self.assertFalse(rp._under_advertised_base(BASE + "s/x.mp3", BASE))
        self.assertFalse(rp._under_advertised_base("https://other/x", BASE))

    # -------------------------------------------------- nothing granted ---
    def test_no_legacy_waiver_for_a_wrong_prefix(self):
        """Run 036: a waiver is a gate with the sign flipped."""
        ledger = {"episodes": {"001": {"status": "published"}}}
        rp.LEDGER_PATH.write_text(json.dumps(ledger))
        result = self._verify(base=SIBLING)
        self.assertFalse(result["ok"], result["issues"])

    def test_the_expected_base_matches_publish_feeds_own_constant(self):
        """The two hardcoded copies must agree, which nothing checked before."""
        import re
        text = (ROOT / "pipeline" / "publish_feed.py").read_text()
        found = re.search(r"^BASE_URL\s*=\s*'([^']+)'", text, re.M)
        self.assertIsNotNone(found)
        self.assertEqual(found.group(1).rstrip("/"),
                         rp.EXPECTED_ADVERTISED_BASES[0].rstrip("/"))

    def test_the_gate_writes_nothing(self):
        # Write the feed FIRST: _write() creates feed.xml, so snapshotting
        # before it exists compares two different file sets, not two states.
        feed = self._write(base=SIBLING)
        before = {q: q.read_bytes() for q in sorted(self.site.iterdir())}
        rp.verify_feed(feed)
        after = {q: q.read_bytes() for q in sorted(self.site.iterdir())}
        self.assertEqual(before, after)

    def test_other_gates_still_bite_on_a_correct_base(self):
        feed = self._write()
        feed.write_text(feed.read_text().replace(
            "<itunes:duration>00:00:02", "<itunes:duration>09:59:59"))
        result = rp.verify_feed(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("duration" in i for i in result["issues"]),
                        result["issues"])


if __name__ == "__main__":
    unittest.main()
