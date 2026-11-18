"""Run 065: verify_feed() must check the <guid> VALUE, not just its digits.

A GUID is the subscriber's permanent identity for an episode -- a client keys
its played/downloaded state on it, so a changed GUID re-delivers an old episode
and a colliding one makes an episode shadow another. This show's docs call a
cross-show GUID collision "a hard bug".

Until run 065 every consumer reduced the GUID to something else:
_feed_item_number() took only `episode-(\\d+)` (falling back to the enclosure
URL with `or`, so the two were never compared), run 056 compared local and
remote GUID SETS, and the duplicate check compared GUIDs only to each other.
robust_pipeline.py did not contain the string "moral-machines" at all, while
run 063's cross-show guard was scoped to advertised URLs -- one field away from
the field the docs name as the hard bug.
"""
import json
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

def _make_fixture_png(width: int = 1400, height: int = 1400) -> bytes:
    """A real, decodable, square PNG so the run-074 cover gate can decode it.

    Run 074 made cover_art DECODE the artwork rather than merely measure it,
    the same way run 058 made <itunes:duration> prove an enclosure is real
    audio. The old fixture cover (``PNG signature + b"art" * 32``) has no
    IHDR, IDAT, IEND or chunk CRCs -- a file no real export can produce -- so
    it is completed here rather than the gate being relaxed. Stdlib only, to
    match the gate.
    """
    def chunk(ctype: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + ctype + body
                + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


FIXTURE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><link>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/</link><description>Show</description><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><image><url>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png</url><title>Moral Machines</title><link>https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/</link></image>
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">{guid}</guid><enclosure url="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/{audio}" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>1</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:duration>00:00:02</itunes:duration><itunes:explicit>false</itunes:explicit><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p><p><a href="episode-001-notes.md">Full source notes, evidence limitations, and direct Zotero links</a></p>]]></content:encoded></item>
</channel></rss>
"""

INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Moral Machines</title></head><body><h1>Moral Machines</h1>'
    '<p><a href="feed.xml">RSS feed</a></p><h2>Episodes</h2><ul>'
    '<li><a href="episode-001.mp3">Episode 001</a></li>'
    '</ul></body></html>'
)


def _make_fixture_mp3() -> bytes:
    """A real decodable 2s mp3 -- run 058 gates <itunes:duration>."""
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


class GuidGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="guid_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        self.audio = self.site / "episode-001.mp3"
        self.audio.write_bytes(_FIXTURE_MP3)
        (self.site / "episode-001-notes.md").write_text("# notes\n")
        cover = _make_fixture_png()
        (self.site / "cover.png").write_bytes(cover)
        (self.dir / "cover.png").write_bytes(cover)
        (self.site / "index.html").write_text(INDEX_HTML)
        self.feed = self.site / "feed.xml"

        self._root = rp.ROOT
        rp.ROOT = self.dir
        self.addCleanup(lambda: setattr(rp, "ROOT", self._root))

        self.ledger = self.dir / "state.json"
        self.ledger.write_text(json.dumps({"schema_version": 1, "episodes": {
            "001": {"status": "published_and_moved", "transitions": [
                {"from": "rendering", "to": "rendered",
                 "at": "2026-11-03T23:39:45Z", "reason": "fixture"}]}}}))
        self._ledger = rp.LEDGER_PATH
        rp.LEDGER_PATH = self.ledger
        self.addCleanup(lambda: setattr(rp, "LEDGER_PATH", self._ledger))

        self.manifest = self.dir / "manifest.json"
        self.manifest.write_text(json.dumps({"schema_version": 1, "episodes": {
            "001": {"number": "001", "title": "Ep One",
                    "description": "Desc one", "status": "published_and_moved",
                    "sources": ["AAAA1111"]}}}))
        self._manifest = rp.MANIFEST_PATH
        rp.MANIFEST_PATH = self.manifest
        self.addCleanup(lambda: setattr(rp, "MANIFEST_PATH", self._manifest))

    def write_feed(self, guid="moral-machines-episode-001",
                   audio="episode-001.mp3"):
        self.feed.write_text(FIXTURE_FEED.format(
            guid=guid, audio=audio, length=self.audio.stat().st_size))

    def verify(self):
        return rp.verify_feed(str(self.feed))

    def guid_check(self, result):
        hits = [c for c in result["checks"] if c.get("name") == "guid"]
        self.assertEqual(len(hits), 1, result["checks"])
        return hits[0]

    # ------------------------------------------------------------- healthy
    def test_conforming_guid_passes_and_is_reported(self):
        self.write_feed()
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        check = self.guid_check(result)
        self.assertEqual(check["guid"], "moral-machines-episode-001")
        self.assertTrue(check["prefix_ok"])
        self.assertEqual(check["lane"], "interview")
        self.assertEqual(check["guid_number"], "001")
        self.assertEqual(check["enclosure_number"], "001")

    # ------------------------------------------------------------ refusals
    def test_cross_show_guid_is_an_issue(self):
        """The documented hard bug: the sibling show's prefix."""
        self.write_feed(guid="human-in-the-loop-episode-001")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("cross-show" in i and "GUID" in i
                            for i in result["issues"]), result["issues"])

    def test_cross_show_guid_also_fails_the_prefix_test(self):
        self.write_feed(guid="human-in-the-loop-episode-001")
        self.assertTrue(any("required prefix" in i
                            for i in self.verify()["issues"]))

    def test_missing_show_prefix_is_an_issue(self):
        self.write_feed(guid="episode-001")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("required prefix" in i and "moral-machines-" in i
                            for i in result["issues"]), result["issues"])

    def test_interview_carrying_the_reading_marker_is_an_issue(self):
        self.write_feed(guid="moral-machines-episode-001-reading-AAAA1111")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("is an interview but advertises" in i
                            and "-reading" in i for i in result["issues"]),
                        result["issues"])

    def test_guid_and_enclosure_number_disagreement_is_an_issue(self):
        """The `or` fallback meant the two numbers were never compared."""
        self.write_feed(guid="moral-machines-episode-002")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("the identity and the audio" in i
                            for i in result["issues"]), result["issues"])

    def test_tokenless_guid_is_an_issue(self):
        self.write_feed(guid="moral-machines-pilot")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("no episode-NNN token" in i
                            for i in result["issues"]), result["issues"])

    def test_absent_guid_is_an_issue(self):
        self.write_feed()
        self.feed.write_text(self.feed.read_text().replace(
            '<guid isPermaLink="false">moral-machines-episode-001</guid>', ""))
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("has no <guid>" in i for i in result["issues"]),
                        result["issues"])

    # ------------------------------------------------------ nothing granted
    def test_no_legacy_waiver_for_the_guid(self):
        """A legacy import's GUID is the subscriber's identity too (run 036)."""
        self.ledger.write_text(json.dumps({"schema_version": 1, "episodes": {
            "001": {"status": "published", "transitions": []}}}))
        self.write_feed(guid="human-in-the-loop-episode-001")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("cross-show" in i for i in result["issues"]),
                        result["issues"])

    def test_reading_guid_with_prefix_and_marker_is_accepted(self):
        """A genuine reading GUID must satisfy both tests."""
        good = "moral-machines-episode-501-reading-ZZZZ1111"
        self.assertTrue(good.startswith(rp.GUID_REQUIRED_PREFIX))
        self.assertIn(rp.GUID_READING_MARKER, good)

    def test_guid_check_does_not_mask_other_gates(self):
        """A conforming GUID must not suppress a pre-existing refusal."""
        self.write_feed()
        (self.site / "cover.png").unlink()
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("cover" in i.lower() for i in result["issues"]),
                        result["issues"])

    def test_check_is_reported_even_when_the_guid_is_bad(self):
        self.write_feed(guid="episode-001")
        check = self.guid_check(self.verify())
        self.assertFalse(check["prefix_ok"])
        self.assertEqual(check["guid"], "episode-001")


if __name__ == "__main__":
    unittest.main()
