"""Run 058: verify_feed() must gate the <itunes:duration> it advertises.

Every feed item carries an <itunes:duration>, publish_feed.py derives it from
duration() -- which parses ffmpeg stderr and returns the LITERAL string
"00:00:00" whenever no Duration: line is found -- and until run 058 no gate read
the emitted value. Enclosures are checked by BYTE LENGTH, which a file of
garbage at the right size satisfies, and preflight() sizes and hashes the audio
without ever decoding it. So an undecodable or truncated mp3, a duration that
disagrees with the audio by any margin, a malformed value and a missing element
all shipped with verify_feed() returning ok: true and an empty issue list --
which is publish_local()'s gate and push_to_remote()'s success criterion.
"""
import json
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest
import unittest.mock
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
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">moral-machines-episode-001</guid><enclosure url="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/episode-001.mp3" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>1</itunes:episode><itunes:episodeType>full</itunes:episodeType>{duration}<itunes:explicit>false</itunes:explicit><itunes:image href="https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast/cover.png"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p>]]></content:encoded></item>
</channel></rss>
"""

DURATION_EL = "<itunes:duration>{value}</itunes:duration>"


def _ffmpeg() -> str:
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _make_mp3(seconds: int) -> bytes:
    """A real, decodable mp3 of the requested length (silence)."""
    with tempfile.TemporaryDirectory() as box:
        out = Path(box) / "f.mp3"
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
             "-t", str(seconds), "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
            capture_output=True, check=True)
        return out.read_bytes()


_MP3_2S = _make_mp3(2)
_MP3_30S = _make_mp3(30)


INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Moral Machines</title></head><body>'
    '<h1>Moral Machines</h1>'
    '<p><a href="feed.xml">RSS feed</a></p><h2>Episodes</h2><ul>'
    '<li><a href="episode-001.mp3">Episode 001</a></li>'
    '</ul></body></html>'
)

class DurationGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="duration_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        self.audio = self.site / "episode-001.mp3"
        self.audio.write_bytes(_MP3_2S)
        self.cover_bytes = _make_fixture_png()
        (self.site / "cover.png").write_bytes(self.cover_bytes)
        # A real feed-site/ always carries the landing page
        # publish_feed.py writes; run 060 gates it, so a fixture
        # without one is incomplete rather than a duration finding.
        (self.site / "index.html").write_text(INDEX_HTML)
        (self.dir / "cover.png").write_bytes(self.cover_bytes)
        self._root = rp.ROOT
        rp.ROOT = self.dir
        self.addCleanup(lambda: setattr(rp, "ROOT", self._root))
        self.feed = self.site / "feed.xml"
        self.write_feed("00:00:02")
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

    def write_feed(self, duration_value):
        element = "" if duration_value is None else DURATION_EL.format(
            value=duration_value)
        self.feed.write_text(FIXTURE_FEED.format(
            length=self.audio.stat().st_size, duration=element))

    def verify(self):
        return rp.verify_feed(str(self.feed))

    def duration_check(self, result):
        hits = [c for c in result["checks"] if c.get("name") == "duration"]
        self.assertEqual(len(hits), 1, json.dumps(result["checks"]))
        return hits[0]

    # ------------------------------------------------------------- healthy
    def test_matching_duration_passes_and_is_reported(self):
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        check = self.duration_check(result)
        self.assertEqual(check["advertised"], "00:00:02")
        self.assertEqual(check["advertised_seconds"], 2)
        self.assertIsNotNone(check["actual_seconds"])

    def test_subsecond_rounding_is_tolerated(self):
        # publish_feed.duration() rounds to whole seconds, so a ~0.06s
        # rounding difference must not be a refusal.
        self.write_feed("00:00:02")
        self.assertTrue(self.verify()["ok"])

    def test_tolerance_constant_is_small_and_positive(self):
        self.assertGreater(rp.DURATION_TOLERANCE_SECONDS, 0)
        self.assertLessEqual(rp.DURATION_TOLERANCE_SECONDS, 5)

    # ------------------------------------------------------------ refusals
    def test_zero_duration_sentinel_is_refused(self):
        self.write_feed("00:00:00")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("00:00:00" in i and "sentinel" in i
                            for i in result["issues"]), result["issues"])

    def test_missing_duration_element_is_refused(self):
        self.write_feed(None)
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("no <itunes:duration>" in i
                            for i in result["issues"]), result["issues"])

    def test_malformed_duration_is_refused(self):
        self.write_feed("twelve minutes")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("malformed" in i and "twelve minutes" in i
                            for i in result["issues"]), result["issues"])

    def test_duration_longer_than_audio_is_refused(self):
        self.write_feed("09:59:59")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("duration mismatch" in i and "09:59:59" in i
                            for i in result["issues"]), result["issues"])

    def test_duration_shorter_than_audio_is_refused(self):
        self.audio.write_bytes(_MP3_30S)
        self.write_feed("00:00:03")
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("duration mismatch" in i
                            for i in result["issues"]), result["issues"])

    def test_undecodable_audio_at_right_byte_length_is_refused(self):
        """The core case: bytes of the right size are not playable audio."""
        size = self.audio.stat().st_size
        self.audio.write_bytes(b"\x00\xff" * (size // 2) + b"\x00" * (size % 2))
        self.assertEqual(self.audio.stat().st_size, size)
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("could not be decoded" in i
                            for i in result["issues"]), result["issues"])
        # the enclosure LENGTH check must still pass, proving the duration
        # block is what caught it
        self.assertFalse(any("length mismatch" in i for i in result["issues"]))

    # -------------------------------------------------------- no waivers
    def test_no_legacy_waiver_for_a_bad_duration(self):
        """A waiver is a gate with the sign flipped (run 036)."""
        self.write_feed("00:00:00")
        with unittest.mock.patch.object(
                rp, "_legacy_episode_numbers", return_value={"001"}):
            result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("00:00:00" in i for i in result["issues"]),
                        result["issues"])

    # ------------------------------------------------------ nothing granted
    def test_missing_enclosure_is_not_double_reported(self):
        self.audio.unlink()
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing local enclosure" in i
                            for i in result["issues"]))
        self.assertFalse(any("could not be decoded" in i
                             for i in result["issues"]), result["issues"])

    def test_length_mismatch_still_refused(self):
        self.audio.write_bytes(_MP3_2S + b"\x00" * 99)
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("length mismatch" in i for i in result["issues"]))

    def test_empty_description_still_refused(self):
        text = self.feed.read_text().replace(
            "<description>Desc one</description>", "<description></description>")
        self.feed.write_text(text)
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("empty <description>" in i
                            for i in result["issues"]))

    def test_missing_cover_still_refused(self):
        (self.site / "cover.png").unlink()
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("cover" in i.lower() for i in result["issues"]))

    # --------------------------------------------------------- the parser
    def test_parse_hhmmss_shapes(self):
        self.assertEqual(rp._parse_hhmmss("00:12:07"), 727)
        self.assertEqual(rp._parse_hhmmss("12:07"), 727)
        self.assertEqual(rp._parse_hhmmss("00:00:00"), 0)
        self.assertIsNone(rp._parse_hhmmss("twelve"))
        self.assertIsNone(rp._parse_hhmmss(""))
        self.assertIsNone(rp._parse_hhmmss("1:2:3:4"))

    def test_audio_duration_none_for_undecodable(self):
        bad = self.dir / "bad.mp3"
        bad.write_bytes(b"not audio" * 50)
        self.assertIsNone(rp._audio_duration_seconds(bad))

    def test_audio_duration_real_for_decodable(self):
        good = self.dir / "good.mp3"
        good.write_bytes(_MP3_30S)
        seconds = rp._audio_duration_seconds(good)
        self.assertIsNotNone(seconds)
        self.assertAlmostEqual(seconds, 30, delta=1.5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
