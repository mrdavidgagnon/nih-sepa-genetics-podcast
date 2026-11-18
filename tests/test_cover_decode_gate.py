"""Run 074: verify_feed() must DECODE the cover art, not merely measure it.

Run 057 wired the first reader for the artwork and stopped at EXISTENCE
(present, non-empty, tree-root copy == feed-site copy, remote HTTP 200). Run
058 found the identical shape one asset over -- "enclosures are verified by
byte length, which garbage at the right size satisfies" -- and closed it for
AUDIO by making <itunes:duration> the one check that proves an enclosure is
real, playable audio. The artwork stayed on the measured-but-never-decoded
side of that line.

Proved against the unmodified module: a NUL-filled cover at exactly the right
length, a truncated PNG (signature intact), a JPEG saved as cover.png, a
CRC-corrupt cover at identical byte length, and a valid 200x120 PNG each
returned ok: true with an EMPTY issue list -- the verdict publish_local()
refuses on and push_to_remote()'s wait loop breaks on to call a deploy live --
and an intact cover was INDISTINGUISHABLE from all of them.

No other audit covers it: feed_coverage() audits enclosures, registry_audit()
relates ledger to manifest, and deploy_drift() compares LOCAL bytes to REMOTE
bytes, so identical garbage on both sides is "no drift". publish_feed.py has
no copy site for the cover, which is precisely why a bad export lands in both
copies at once and the root-vs-site digest comparison agrees.

The gate is stdlib only (zlib + struct): this tree's interpreter is 3.14,
where `imghdr` was removed, and PIL is not a dependency.
"""
import json
import shutil
import struct
import sys
import tempfile
import unittest
import unittest.mock
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><link>{base}/</link><description>Playful, dramatized interviews synthesizing research on machine ethics. Built for the 2026 NIH SEPA project.</description><language>en-us</language><copyright>(c) 2026 Field Day Lab, UW-Madison</copyright><itunes:author>Field Day Lab, UW-Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><itunes:image href="{base}/cover.png"/><image><url>{base}/cover.png</url><title>Moral Machines</title><link>{base}/</link></image>
      <item><title>Ep One</title><description>Desc one</description><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p>]]></content:encoded><guid isPermaLink="false">moral-machines-episode-001</guid><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><enclosure url="{base}/episode-001.mp3" length="{length}" type="audio/mpeg"/><itunes:duration>00:00:02</itunes:duration><itunes:episode>1</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:explicit>false</itunes:explicit><itunes:image href="{base}/cover.png"/></item>
</channel></rss>
"""


def _chunk(ctype: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + ctype + body
            + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))


def make_png(width: int = 1400, height: int = 1400) -> bytes:
    """A real, decodable PNG. Stdlib only, to match the gate."""
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (rp.PNG_SIGNATURE
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9))
            + _chunk(b"IEND", b""))


def _ffmpeg() -> str:
    # The vendored bundle is NOT on sys.path by default -- a bare
    # `import imageio_ffmpeg` raises, and swallowing that in a try/except
    # turns a path bug into a misleading "no ffmpeg available" skip.
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _make_fixture_mp3() -> bytes:
    """Tiny real mp3 so the run-058 duration gate can decode it."""
    import subprocess
    with tempfile.TemporaryDirectory() as box:
        out = Path(box) / "a.mp3"
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
             "-t", "2", "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
            capture_output=True, check=True)
        return out.read_bytes()


_MP3_2S = _make_fixture_mp3()


class CoverDecodeTests(unittest.TestCase):
    """The gate must decode the artwork and read its dimensions."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mm-coverdecode-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.site = self.tmp / "feed-site"
        self.site.mkdir()
        audio = self.site / "episode-001.mp3"
        audio.write_bytes(_MP3_2S)
        (self.site / "episode-001-notes.md").write_text("notes\n")
        (self.site / "index.html").write_text(
            "<html><head><title>Moral Machines</title></head>"
            "<body><h1>Moral Machines</h1><ol><li>"
            '<a href="episode-001.mp3">Ep One</a></li></ol></body></html>')
        self.feed = self.site / "feed.xml"
        self.feed.write_text(FEED.format(base=BASE,
                                         length=audio.stat().st_size))
        self.good = make_png()
        self.put(self.good)
        self.root_patch = unittest.mock.patch.object(rp, "ROOT", self.tmp)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def put(self, data: bytes):
        """Write BOTH copies.

        The cover is hand-kept in sync (publish_feed.py has no copy site for
        it), so a bad export lands in both -- which is exactly why run 057's
        root-vs-site digest comparison agrees on a broken cover.
        """
        (self.site / "cover.png").write_bytes(data)
        (self.tmp / "cover.png").write_bytes(data)

    def verify(self):
        return rp.verify_feed(self.feed)

    def cover(self, result=None):
        result = result or self.verify()
        for c in result.get("checks", []):
            if c.get("name") == "cover_art":
                return c
        return {}

    # -- the healthy case is unchanged -------------------------------------

    def test_a_real_square_cover_passes_and_is_reported(self):
        r = self.verify()
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["issues"], [])
        c = self.cover(r)
        self.assertTrue(c["decoded"])
        self.assertEqual(c["format"], "png")
        self.assertEqual((c["width"], c["height"]), (1400, 1400))

    def test_run_057s_existing_arms_are_still_reported(self):
        c = self.cover()
        for key in ("advertised", "files", "local_bytes",
                    "site_sha256", "root_sha256"):
            self.assertIn(key, c)

    def test_the_boundary_sizes_are_accepted(self):
        for size in (rp.COVER_MIN_PIXELS, 2048, rp.COVER_MAX_PIXELS):
            with self.subTest(size=size):
                self.put(make_png(size, size))
                r = self.verify()
                self.assertTrue(r["ok"], r["issues"])

    # -- the unread classes are now refused --------------------------------

    def test_a_nul_filled_cover_at_the_right_length_is_refused(self):
        self.put(b"\x00" * len(self.good))
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("not renderable" in i for i in r["issues"]),
                        r["issues"])

    def test_a_truncated_cover_is_refused_and_named_as_truncated(self):
        self.put(self.good[: len(self.good) // 3])
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("truncated" in i for i in r["issues"]), r["issues"])

    def test_a_jpeg_saved_as_cover_png_is_refused_and_named(self):
        # A real JPEG decodes fine, so a decode-only check is not enough --
        # all five advertised slots name a .png, so the FORMAT must be read.
        self.put(b"\xff\xd8\xff\xe0" + b"\x00" * 512)
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("jpeg" in i.lower() for i in r["issues"]),
                        r["issues"])

    def test_a_crc_corrupt_cover_at_identical_length_is_refused(self):
        # Byte length, signature, IHDR, IDAT and IEND are all intact; only
        # the chunk CRC catches it. This is the arm a magic-byte sniff or a
        # size comparison structurally cannot have.
        bad = bytearray(self.good)
        bad[len(bad) // 2] ^= 0xFF
        self.assertEqual(len(bad), len(self.good))
        self.put(bytes(bad))
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("CRC" in i for i in r["issues"]), r["issues"])

    def test_a_cover_with_no_pixel_data_is_refused(self):
        self.put(rp.PNG_SIGNATURE
                 + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1400, 1400, 8, 2, 0, 0, 0))
                 + _chunk(b"IEND", b""))
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("not renderable" in i for i in r["issues"]),
                        r["issues"])

    def test_a_non_square_cover_is_refused(self):
        self.put(make_png(3000, 2000))   # both dimensions in range
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("not square" in i for i in r["issues"]), r["issues"])

    def test_an_undersized_cover_is_refused(self):
        self.put(make_png(800, 800))     # square, but below the minimum
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("minimum" in i for i in r["issues"]), r["issues"])

    def test_an_oversized_cover_is_refused(self):
        self.put(make_png(3400, 3400))
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("maximum" in i for i in r["issues"]), r["issues"])

    def test_a_small_non_square_cover_raises_both_arms(self):
        self.put(make_png(200, 120))
        r = self.verify()
        joined = " | ".join(r["issues"])
        self.assertIn("not square", joined)
        self.assertIn("minimum", joined)

    # -- nothing granted ---------------------------------------------------

    def test_there_is_no_legacy_waiver(self):
        """Run 036: a waiver is a gate with the sign flipped.

        An advertised asset a client cannot render is a defect for an
        imported episode too, so a ledger-published record waives nothing.
        """
        (self.tmp / "pipeline").mkdir(exist_ok=True)
        (self.tmp / "pipeline" / "state.json").write_text(json.dumps(
            {"episodes": {"001": {"status": "published"}}}))
        with unittest.mock.patch.object(
                rp, "LEDGER_PATH", self.tmp / "pipeline" / "state.json"):
            self.put(b"\x00" * len(self.good))
            r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("not renderable" in i for i in r["issues"]),
                        r["issues"])

    def test_run_057s_missing_and_empty_arms_still_bite(self):
        (self.site / "cover.png").unlink()
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("missing local cover" in i for i in r["issues"]),
                        r["issues"])
        self.put(b"")
        r = self.verify()
        self.assertFalse(r["ok"])

    def test_run_057s_root_vs_site_drift_arm_still_bites(self):
        (self.tmp / "cover.png").write_bytes(make_png(2048, 2048))
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(
            any("differs between the tree" in i for i in r["issues"]),
            r["issues"])

    def test_an_absent_root_copy_is_still_not_an_issue(self):
        """Run 057's deliberate policy: the feed never references the root."""
        (self.tmp / "cover.png").unlink()
        r = self.verify()
        self.assertTrue(r["ok"], r["issues"])

    def test_the_check_writes_nothing(self):
        before = {p.name: p.read_bytes() for p in self.site.iterdir()
                  if p.is_file()}
        for _ in range(3):
            self.verify()
        after = {p.name: p.read_bytes() for p in self.site.iterdir()
                 if p.is_file()}
        self.assertEqual(before, after)


class DecodePngTests(unittest.TestCase):
    """decode_png() must never raise, and must name what it found."""

    def test_a_real_png_decodes_with_its_dimensions(self):
        out = rp.decode_png(make_png(1400, 1400))
        self.assertTrue(out["ok"])
        self.assertEqual(out["format"], "png")
        self.assertEqual((out["width"], out["height"]), (1400, 1400))
        self.assertIsNone(out["error"])

    def test_every_malformed_input_returns_an_error_rather_than_raising(self):
        cases = [b"", b"\x00" * 64, b"not a png at all",
                 rp.PNG_SIGNATURE, rp.PNG_SIGNATURE + b"\x00" * 8,
                 make_png()[:40], make_png()[:-6],
                 b"\xff\xd8\xff\xe0junk", b"GIF89a" + b"\x00" * 32,
                 b"BM" + b"\x00" * 32, b"RIFF0000WEBP" + b"\x00" * 16,
                 b'<?xml version="1.0"?><svg/>']
        for i, data in enumerate(cases):
            with self.subTest(case=i):
                out = rp.decode_png(data)
                self.assertFalse(out["ok"])
                self.assertTrue(out["error"])

    def test_the_container_it_found_is_named(self):
        for data, fmt in [(b"\xff\xd8\xff\xe0x", "jpeg"),
                          (b"GIF89a" + b"\x00" * 8, "gif"),
                          (b"RIFF0000WEBP0000", "webp"),
                          (b"BM" + b"\x00" * 8, "bmp"),
                          (b'<?xml version="1.0"?><svg></svg>', "svg")]:
            with self.subTest(fmt=fmt):
                out = rp.decode_png(data)
                self.assertEqual(out["format"], fmt)
                self.assertIn(fmt, out["error"])

    def test_a_zero_dimension_is_refused(self):
        bad = (rp.PNG_SIGNATURE
               + _chunk(b"IHDR", struct.pack(">IIBBBBB", 0, 10, 8, 2, 0, 0, 0))
               + _chunk(b"IDAT", zlib.compress(b"\x00"))
               + _chunk(b"IEND", b""))
        out = rp.decode_png(bad)
        self.assertFalse(out["ok"])
        self.assertIn("zero dimension", out["error"])

    def test_an_invalid_bit_depth_or_colour_type_is_refused(self):
        for depth, colour, needle in [(7, 2, "bit depth"), (8, 9, "colour type")]:
            with self.subTest(depth=depth, colour=colour):
                bad = (rp.PNG_SIGNATURE
                       + _chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, depth,
                                                     colour, 0, 0, 0))
                       + _chunk(b"IDAT", zlib.compress(b"\x00"))
                       + _chunk(b"IEND", b""))
                out = rp.decode_png(bad)
                self.assertFalse(out["ok"])
                self.assertIn(needle, out["error"])

    def test_undecompressable_pixel_data_is_refused(self):
        bad = (rp.PNG_SIGNATURE
               + _chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
               + _chunk(b"IDAT", b"\xde\xad\xbe\xef")
               + _chunk(b"IEND", b""))
        out = rp.decode_png(bad)
        self.assertFalse(out["ok"])
        self.assertIn("decompress", out["error"])

    def test_the_gate_adds_no_new_dependency(self):
        """Stdlib only: 3.14 removed imghdr and PIL is not a dependency."""
        src = (Path(rp.__file__)).read_text()
        imports = [l for l in src.split("\n")
                   if l.startswith("import ") or l.startswith("from ")]
        self.assertFalse([l for l in imports
                          if "PIL" in l or "imghdr" in l])
        self.assertIn("import zlib", imports)
        self.assertIn("import struct", imports)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
