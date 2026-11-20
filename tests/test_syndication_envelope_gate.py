"""The syndication-envelope gate (run 071).

The five fields that tell a podcast client what kind of document the feed is
and how to read it -- <rss version>, xmlns:itunes, xmlns:content,
<enclosure type> and <guid isPermaLink> -- had ZERO readers until run 071, so
every defect in them shipped ok: true with an EMPTY issue list from
verify_feed(): the verdict publish_local() refuses on and push_to_remote()'s
wait loop breaks on to declare a deploy live.

Enumerated values, compared exactly, wrong case refused separately, and NO
legacy waiver (run 036) -- the envelope is a property of the syndication
format, not of any episode.
"""
import hashlib
import shutil
import subprocess
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
    audio. The old fixture cover (``PNG signature + filler``) has no IHDR,
    IDAT, IEND or chunk CRCs -- a file no real export can produce -- so it is
    completed here rather than the gate being relaxed. Stdlib only, to match
    the gate.
    """
    def chunk(ctype: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + ctype + body
                + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><link>{base}/</link><description>Playful, dramatized interviews synthesizing research on machine ethics. Built for the 2026 NIH SEPA project.</description><language>en-us</language><copyright>(c) 2026 Field Day Lab, UW-Madison</copyright><itunes:author>Field Day Lab, UW-Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><itunes:image href="{base}/cover.png"/><image><url>{base}/cover.png</url><title>Moral Machines</title><link>{base}/</link></image>
      <item><title>Ep One</title><description>Desc one</description><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p><p><a href="episode-001-notes.md">Full source notes, evidence limitations, and direct Zotero links</a></p>]]></content:encoded><guid isPermaLink="false">moral-machines-episode-001</guid><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><enclosure url="{base}/episode-001.mp3" length="{length}" type="audio/mpeg"/><itunes:duration>00:00:02</itunes:duration><itunes:episode>1</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:explicit>false</itunes:explicit><itunes:explicit>false</itunes:explicit><itunes:image href="{base}/cover.png"/></item>
</channel></rss>
"""


def _ffmpeg() -> str:
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _make_mp3(seconds: int) -> bytes:
    """A real, decodable mp3 of the requested length (silence).

    Run 058's duration gate DECODES the enclosure, so a fixture of mp3 magic
    bytes plus zeros is correctly refused as "the right byte length but not
    playable audio". That gate was right and the first draft of this fixture
    was wrong (run 029) -- it built a feed this pipeline cannot produce.
    """
    with tempfile.TemporaryDirectory() as box:
        out = Path(box) / "f.mp3"
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
             "-t", str(seconds), "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
            capture_output=True, check=True)
        return out.read_bytes()


_MP3_2S = _make_mp3(2)


class SyndicationEnvelopeTests(unittest.TestCase):
    """Each case mutates ONE envelope field and asserts the refusal."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mm-envelope-"))
        self.site = self.tmp / "feed-site"
        self.site.mkdir()
        audio = self.site / "episode-001.mp3"
        audio.write_bytes(_MP3_2S)
        (self.site / "episode-001-notes.md").write_text("notes\n")
        png = self.tmp / "cover.png"
        png.write_bytes(_make_fixture_png())
        shutil.copy2(png, self.site / "cover.png")
        (self.site / "index.html").write_text(
            "<html><head><title>Moral Machines</title></head>"
            "<body><h1>Moral Machines</h1><ol><li>"
            '<a href="episode-001.mp3">Episode 001</a> &middot; <a href="episode-001-notes.md">notes</a></li></ol></body></html>')
        self.feed = self.site / "feed.xml"
        self.length = audio.stat().st_size
        self.feed.write_text(FEED.format(base=BASE, length=self.length))
        self._root = rp.ROOT
        rp.ROOT = self.tmp

    def tearDown(self):
        rp.ROOT = self._root
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------- helpers
    def _mutate(self, old, new, count=1):
        text = self.feed.read_text()
        self.assertIn(old, text, "fixture anchor absent")
        self.feed.write_text(text.replace(old, new, count))

    def _verify(self):
        return rp.verify_feed(self.feed)

    def _envelope(self, result):
        return next((c for c in result["checks"]
                     if c.get("name") == "syndication_envelope"), None)

    def _assert_refused(self, needle):
        r = self._verify()
        self.assertFalse(r["ok"], f"expected refusal, issues={r['issues']}")
        self.assertTrue(any(needle in i for i in r["issues"]),
                        f"{needle!r} not named; issues={r['issues']}")
        return r

    # ---------------------------------------------- the healthy baseline
    def test_intact_envelope_passes_and_is_reported(self):
        r = self._verify()
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["issues"], [])
        env = self._envelope(r)
        self.assertIsNotNone(env, "gate emits no syndication_envelope check")
        self.assertEqual(env["rss_version"], "2.0")
        self.assertEqual(env["root_element"], "rss")
        self.assertEqual(env["declared_namespaces"]["itunes"],
                         "http://www.itunes.com/dtds/podcast-1.0.dtd")
        self.assertEqual(env["declared_namespaces"]["content"],
                         "http://purl.org/rss/1.0/modules/content/")
        self.assertEqual(env["enclosure_types"]["001"], "audio/mpeg")
        self.assertEqual(env["permalink_flags"]["001"], "false")

    # ------------------------------------------------- <rss version>
    def test_wrong_rss_version_refused(self):
        self._mutate('<rss version="2.0"', '<rss version="1.0"')
        self._assert_refused("not '2.0'")

    def test_absent_rss_version_refused(self):
        self._mutate('<rss version="2.0" ', '<rss ')
        self._assert_refused("declares no version attribute")

    def test_non_rss_root_element_refused(self):
        text = self.feed.read_text().replace("<rss ", "<feed ", 1)
        self.feed.write_text(text.replace("</rss>", "</feed>"))
        self._assert_refused("not <rss>")

    # --------------------------------------------- namespace bindings
    def test_wrong_itunes_namespace_refused(self):
        self._mutate('xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"',
                     'xmlns:itunes="http://example.invalid/itunes"')
        self._assert_refused("binds xmlns:itunes")

    def test_wrong_content_namespace_refused(self):
        """Run 064's gate stays green through this: it finds the element with
        an endswith("encoded") fallback that matches in ANY namespace."""
        self._mutate('xmlns:content="http://purl.org/rss/1.0/modules/content/"',
                     'xmlns:content="http://example.invalid/content"')
        self._assert_refused("binds xmlns:content")

    def test_case_variant_namespace_refused_as_case(self):
        self._mutate('xmlns:content="http://purl.org/rss/1.0/modules/content/"',
                     'xmlns:content="HTTP://PURL.ORG/RSS/1.0/MODULES/CONTENT/"')
        self._assert_refused("only in case")

    # ------------------------------------------- <enclosure type>
    def test_wrong_enclosure_type_refused(self):
        self._mutate('type="audio/mpeg"', 'type="video/mp4"')
        self._assert_refused("advertises enclosure type")

    def test_absent_enclosure_type_refused(self):
        self._mutate(' type="audio/mpeg"', '')
        self._assert_refused("no type attribute")

    def test_empty_enclosure_type_refused(self):
        self._mutate('type="audio/mpeg"', 'type=""')
        self._assert_refused("advertises enclosure type")

    def test_case_variant_enclosure_type_refused_as_case(self):
        self._mutate('type="audio/mpeg"', 'type="AUDIO/MPEG"')
        self._assert_refused("only in case")

    # ---------------------------------------- <guid isPermaLink>
    def test_ispermalink_true_refused(self):
        self._mutate('isPermaLink="false"', 'isPermaLink="true"')
        self._assert_refused("advertises isPermaLink")

    def test_absent_ispermalink_refused(self):
        """RSS DEFAULTS isPermaLink to true, so an absent attribute makes a
        client resolve the episode's permanent identity as a URL."""
        self._mutate(' isPermaLink="false"', '')
        self._assert_refused("no isPermaLink attribute")

    def test_case_variant_ispermalink_refused_as_case(self):
        self._mutate('isPermaLink="false"', 'isPermaLink="FALSE"')
        self._assert_refused("only in case")

    # ------------------------------------------- nothing granted
    def test_no_legacy_waiver_for_the_envelope(self):
        """An envelope is a property of the FORMAT, so no episode's
        provenance can exempt it (run 036: a waiver is a gate with the sign
        flipped)."""
        import json
        ledger = self.tmp / "state.json"
        ledger.write_text(json.dumps(
            {"episodes": {"001": {"status": "published"}}}))
        old = rp.LEDGER_PATH
        rp.LEDGER_PATH = ledger
        try:
            self._mutate('type="audio/mpeg"', 'type="video/mp4"')
            r = self._verify()
            self.assertFalse(r["ok"])
            self.assertTrue(any("enclosure type" in i for i in r["issues"]),
                            f"legacy item was waived; issues={r['issues']}")
        finally:
            rp.LEDGER_PATH = old

    def test_gate_writes_nothing(self):
        before = hashlib.md5(self.feed.read_bytes()).hexdigest()
        for _ in range(3):
            self._verify()
        self.assertEqual(before, hashlib.md5(self.feed.read_bytes()).hexdigest())

    def test_neighbouring_gates_still_bite(self):
        """The envelope arm must not shadow the per-field gates it sits above."""
        for old, new, needle in (
                ("<itunes:episodeType>full</itunes:episodeType>",
                 "<itunes:episodeType>trailer</itunes:episodeType>", "episodeType"),
                ("moral-machines-episode-001",
                 "human-in-the-loop-episode-001", None),
                ("<itunes:duration>00:00:02</itunes:duration>",
                 "<itunes:duration>00:00:00</itunes:duration>", None)):
            with self.subTest(old=old):
                self.feed.write_text(FEED.format(base=BASE, length=self.length))
                self._mutate(old, new)
                r = self._verify()
                self.assertFalse(r["ok"], f"{old} no longer refused")
                if needle:
                    self.assertTrue(any(needle in i for i in r["issues"]))

    def test_envelope_reports_every_item(self):
        env = self._envelope(self._verify())
        self.assertEqual(sorted(env["enclosure_types"]), ["001"])
        self.assertEqual(sorted(env["permalink_flags"]), ["001"])
        self.assertEqual(env["expected_enclosure_type"], "audio/mpeg")
        self.assertEqual(env["expected_ispermalink"], "false")
        self.assertEqual(env["expected_rss_version"], "2.0")


if __name__ == "__main__":
    unittest.main()
