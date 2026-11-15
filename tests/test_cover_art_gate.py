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
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><description>Show</description><itunes:image href="https://example.invalid/cover.png"/><image><url>https://example.invalid/cover.png</url><title>Moral Machines</title></image>
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">moral-machines-episode-001</guid><enclosure url="https://example.invalid/episode-001.mp3" length="{length}" type="audio/mpeg"/><itunes:episode>1</itunes:episode><itunes:image href="https://example.invalid/cover.png"/></item>
</channel></rss>
"""


class CoverArtGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cover_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        self.audio = self.site / "episode-001.mp3"
        self.audio.write_bytes(b"ID3" + b"\x00" * 64)
        self.cover_bytes = b"\x89PNG\r\n\x1a\n" + b"art" * 32
        (self.site / "cover.png").write_bytes(self.cover_bytes)
        self.feed = self.site / "feed.xml"
        self.feed.write_text(FIXTURE_FEED.format(length=self.audio.stat().st_size))
        # ROOT is module-level; point it at our scratch tree for the
        # root-vs-deployed drift comparison.
        self._root = rp.ROOT
        rp.ROOT = self.dir
        self.addCleanup(lambda: setattr(rp, "ROOT", self._root))
        (self.dir / "cover.png").write_bytes(self.cover_bytes)

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
                             .replace('<itunes:image href="https://example.invalid/cover.png"/>', "")
                             .replace("<image><url>https://example.invalid/cover.png</url><title>Moral Machines</title></image>", ""))
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
