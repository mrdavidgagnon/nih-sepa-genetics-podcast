"""Run 064: verify_feed() must read the disclosure prose in <content:encoded>.

<content:encoded> is a published deliverable -- a podcast client renders it as
the episode description -- and it carries the show's mandated WRITTEN
disclosures. publish_feed.py builds it independently of script.md and
episode-notes.md via notes_html() / read_notes_html(), branching on
preproduced_episodes() and the read manifest, so the disclosures preflight()
approves are not the ones subscribers receive.

Until run 064 nothing read the prose: robust_pipeline.py mentioned
<content:encoded> twice, both in the block that pulls notes.md hrefs out of it.
An interview advertising the pre-produced provenance (losing both mandated
interview disclosures), an interview advertising the reading disclosure, a
reading advertising the synthetic-interview disclosure, and an emptied block
all returned ok: true with an empty issue list -- publish_local()'s gate and
push_to_remote()'s success criterion.
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



def _make_fixture_mp3() -> bytes:
    """Tiny real mp3 (2s silence) so the run-058 duration gate can decode it."""
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
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

BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"

INTERVIEW_BLOCK = (
    "<p>This is a synthetic/dramatized interview with fictional research "
    "correspondent Dr. Rowan Field. Rowan is a fictional composite; no cited "
    "author was interviewed or is speaking through Rowan.</p>"
    "<p>This is an AI-generated summary that may contain errors and is not a "
    "substitute for reading the cited sources.</p>"
)
READING_BLOCK = (
    "<p>This episode is a complete automated text-to-speech reading of the body "
    "text of one work, read verbatim by a synthetic voice. It is not an "
    "interview, not a summary, and not a dramatization: Dr. Rowan Field does "
    "not appear.</p>"
)
PREPRODUCED_BLOCK = (
    "<p>Pre-recorded audio provided by David Gagnon and added to the feed as-is "
    "at his request. It was not scripted or rendered by the podcast pipeline and "
    "was not reviewed or transcribed before posting.</p>"
)

FEED_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><link>{base}/</link><description>Show</description><itunes:image href="{base}/cover.png"/><image><url>{base}/cover.png</url><title>Moral Machines</title><link>{base}/</link></image>
      <item><title>Ep One</title><description>Desc one</description><guid isPermaLink="false">{guid}</guid><enclosure url="{base}/episode-{num}.mp3" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>{ordinal}</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:duration>00:00:02</itunes:duration><itunes:explicit>false</itunes:explicit><itunes:image href="{base}/cover.png"/>{encoded}</item>
</channel></rss>
"""

INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Moral Machines</title></head><body>'
    '<h1>Moral Machines</h1>'
    '<p><a href="feed.xml">RSS feed</a></p><h2>Episodes</h2><ul>'
    '<li><a href="episode-{num}.mp3">{kind} {num}</a> &middot; '
    '<a href="episode-{num}-notes.md">notes</a></li></ul></body></html>'
)


class DisclosureGateTests(unittest.TestCase):
    """The advertised written disclosure must match the episode's lane."""

    def setUp(self):
        self.box = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.box, True)
        self.site = self.box / "feed-site"
        self.site.mkdir()
        (self.box / "pipeline").mkdir()
        self.root_patch = unittest.mock.patch.object(rp, "ROOT", self.box)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.ledger_patch = unittest.mock.patch.object(
            rp, "LEDGER_PATH", self.box / "pipeline" / "state.json")
        self.ledger_patch.start()
        self.addCleanup(self.ledger_patch.stop)
        self.manifest_patch = unittest.mock.patch.object(
            rp, "MANIFEST_PATH", self.box / "pipeline" / "manifest.json")
        self.manifest_patch.start()
        self.addCleanup(self.manifest_patch.stop)
        if hasattr(rp, "READ_MANIFEST_PATH"):
            self.read_patch = unittest.mock.patch.object(
                rp, "READ_MANIFEST_PATH",
                self.box / "pipeline" / "read-episodes.json")
            self.read_patch.start()
            self.addCleanup(self.read_patch.stop)
        for name in ("cover.png",):
            (self.site / name).write_bytes(_make_fixture_png())
            (self.box / name).write_bytes(_make_fixture_png())
        self._write_registries()

    def _write_registries(self, manifest=None, read=None):
        (self.box / "pipeline" / "manifest.json").write_text(json.dumps(
            manifest if manifest is not None
            else {"episodes": {"001": {"number": "001", "status": "published_and_moved",
                                       "sources": ["AAAA1111"]}}}))
        (self.box / "pipeline" / "state.json").write_text(json.dumps(
            {"episodes": {"001": {"status": "published_and_moved"}}}))
        (self.box / "pipeline" / "read-episodes.json").write_text(json.dumps(
            read if read is not None else {"episodes": {}}))

    def _build(self, encoded_html, num="001"):
        """Write a complete, otherwise-healthy feed-site carrying one item."""
        mp3 = self.site / f"episode-{num}.mp3"
        mp3.write_bytes(_FIXTURE_MP3)
        (self.site / f"episode-{num}-notes.md").write_text("# notes\n")
        kind = "Reading" if int(num) >= 501 else "Episode"
        (self.site / "index.html").write_text(INDEX_HTML.format(num=num, kind=kind))
        # publish_feed.py's notes_html() and read_notes_html() BOTH
        # emit a show-notes link on every item, so a disclosure block
        # without one is a block no generator can produce (run 075).
        # It is appended here rather than baked into the prose
        # constants because only _build() knows the episode number --
        # the constants are passed through literally, never formatted.
        if encoded_html and encoded_html.strip() and "notes.md" not in encoded_html:
            encoded_html = encoded_html + (
                '<p><a href="episode-%s-notes.md">Full source notes</a></p>' % num)
        encoded = ("<content:encoded><![CDATA[" + encoded_html + "]]></content:encoded>"
                   if encoded_html is not None else "")
        feed = self.site / "feed.xml"
        # Lane-correct GUID. read_lane.register() writes a reading's guid as
        # episode-NNN-reading-<itemkey>; an interview's is the plain form.
        # Sharing one interview-shaped guid across both lanes made this
        # fixture incomplete once run 065 gated the GUID value.
        guid = (f"moral-machines-episode-{num}-reading-AAAA1111"
                if int(num) >= 501 else f"moral-machines-episode-{num}")
        feed.write_text(FEED_TEMPLATE.format(
            base=BASE, num=num, guid=guid, ordinal=int(num),
            length=mp3.stat().st_size, encoded=encoded))
        return feed

    def verify(self, feed):
        return rp.verify_feed(str(feed))

    # ---------------------------------------------------------------- healthy
    def test_a_correct_interview_disclosure_passes_and_is_reported(self):
        feed = self._build(INTERVIEW_BLOCK)
        result = self.verify(feed)
        self.assertTrue(result["ok"], result["issues"])
        checks = [c for c in result["checks"] if c.get("name") == "disclosure"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["lane"], "interview")
        self.assertEqual(checks[0]["missing"], [])
        self.assertFalse(checks[0]["preproduced"])
        self.assertGreater(checks[0]["chars"], 0)

    def test_a_correct_reading_disclosure_passes(self):
        self._write_registries(
            manifest={"episodes": {"501": {"number": "501", "kind": "read",
                                           "status": "published_and_moved",
                                           "read_source": ["AAAA1111"]}}},
            read={"episodes": {"501": {"number": "501", "verified": True}}})
        feed = self._build(READING_BLOCK, num="501")
        result = self.verify(feed)
        self.assertTrue(result["ok"], result["issues"])
        checks = [c for c in result["checks"] if c.get("name") == "disclosure"]
        self.assertEqual(checks[0]["lane"], "read")

    # ------------------------------------------------------------- refusals
    def test_an_absent_encoded_element_is_refused(self):
        feed = self._build(None)
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("no <content:encoded>" in i for i in result["issues"]),
                        result["issues"])

    def test_an_empty_encoded_block_is_refused(self):
        feed = self._build("")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("empty <content:encoded>" in i for i in result["issues"]),
                        result["issues"])

    def test_a_whitespace_only_block_is_refused(self):
        feed = self._build("   \n  ")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("empty <content:encoded>" in i for i in result["issues"]),
                        result["issues"])

    def test_an_interview_missing_the_fictional_disclosure_is_refused(self):
        feed = self._build(
            "<p>This is a synthetic/dramatized interview with a research "
            "correspondent.</p><p>This is an AI-generated summary.</p>")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("'fictional'" in i for i in result["issues"]),
                        result["issues"])

    def test_an_interview_missing_the_ai_disclosure_is_refused(self):
        feed = self._build(
            "<p>This is a synthetic/dramatized interview with fictional research "
            "correspondent Dr. Rowan Field.</p>")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("AI-generated summary" in i for i in result["issues"]),
                        result["issues"])

    def test_an_interview_advertising_the_preproduced_provenance_is_refused(self):
        feed = self._build(PREPRODUCED_BLOCK)
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("must not claim supplied audio" in i for i in result["issues"]),
            result["issues"])

    def test_an_interview_advertising_the_reading_disclosure_is_refused(self):
        feed = self._build(INTERVIEW_BLOCK + READING_BLOCK)
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("advertises the verbatim-reading" in i for i in result["issues"]),
            result["issues"])

    def test_a_reading_advertising_the_synthetic_interview_disclosure_is_refused(self):
        self._write_registries(
            manifest={"episodes": {"501": {"number": "501", "kind": "read",
                                           "status": "published_and_moved",
                                           "read_source": ["AAAA1111"]}}},
            read={"episodes": {"501": {"number": "501", "verified": True}}})
        feed = self._build(READING_BLOCK + INTERVIEW_BLOCK, num="501")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("synthetic-interview disclosure" in i for i in result["issues"]),
            result["issues"])

    def test_a_reading_missing_its_own_disclosure_is_refused(self):
        self._write_registries(
            manifest={"episodes": {"501": {"number": "501", "kind": "read",
                                           "status": "published_and_moved",
                                           "read_source": ["AAAA1111"]}}},
            read={"episodes": {"501": {"number": "501", "verified": True}}})
        feed = self._build("<p>Some unrelated prose.</p>", num="501")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("verbatim-reading disclosure phrase" in i for i in result["issues"]),
            result["issues"])

    def test_a_reading_advertising_the_preproduced_provenance_is_refused(self):
        self._write_registries(
            manifest={"episodes": {"501": {"number": "501", "kind": "read",
                                           "status": "published_and_moved",
                                           "read_source": ["AAAA1111"]}}},
            read={"episodes": {"501": {"number": "501", "verified": True}}})
        feed = self._build(READING_BLOCK + PREPRODUCED_BLOCK, num="501")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("pre-produced provenance" in i for i in result["issues"]),
            result["issues"])

    # --------------------------------------------------- preproduced records
    def test_a_genuine_preproduced_record_may_carry_that_disclosure(self):
        self._write_registries(
            manifest={"episodes": {"001": {"number": "001",
                                           "status": "published_and_moved",
                                           "preproduced": True,
                                           "sources": ["AAAA1111"]}}})
        feed = self._build(PREPRODUCED_BLOCK)
        result = self.verify(feed)
        self.assertTrue(result["ok"], result["issues"])
        checks = [c for c in result["checks"] if c.get("name") == "disclosure"]
        self.assertTrue(checks[0]["preproduced"])

    def test_a_declared_preproduced_record_without_the_statement_is_refused(self):
        self._write_registries(
            manifest={"episodes": {"001": {"number": "001",
                                           "status": "published_and_moved",
                                           "preproduced": True,
                                           "sources": ["AAAA1111"]}}})
        feed = self._build(INTERVIEW_BLOCK)
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("does not carry the" in i for i in result["issues"]),
            result["issues"])

    def test_the_preproduced_waiver_is_keyed_on_the_record_not_the_number(self):
        """A non-declared episode 033 gets no waiver (the sibling-show numbers)."""
        self._write_registries(
            manifest={"episodes": {"033": {"number": "033",
                                           "status": "published_and_moved",
                                           "sources": ["AAAA1111"]}}},
            read={"episodes": {}})
        feed = self._build(PREPRODUCED_BLOCK, num="033")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("must not claim supplied audio" in i for i in result["issues"]),
            result["issues"])

    # ----------------------------------------------------------- no waivers
    def test_a_legacy_episode_gets_no_disclosure_waiver(self):
        """Run 036: a waiver is a gate with the sign flipped."""
        (self.box / "pipeline" / "state.json").write_text(json.dumps(
            {"episodes": {"001": {"status": "published"}}}))
        feed = self._build("")
        result = self.verify(feed)
        self.assertFalse(result["ok"])
        self.assertTrue(any("empty <content:encoded>" in i for i in result["issues"]),
                        result["issues"])

    def test_the_check_is_not_keyed_on_remote(self):
        feed = self._build(PREPRODUCED_BLOCK)
        result = rp.verify_feed(str(feed))
        self.assertFalse(result["ok"])

    def test_the_gate_writes_nothing(self):
        feed = self._build(INTERVIEW_BLOCK)
        before = {p: p.read_bytes() for p in sorted(self.box.rglob("*")) if p.is_file()}
        rp.verify_feed(str(feed))
        after = {p: p.read_bytes() for p in sorted(self.box.rglob("*")) if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
