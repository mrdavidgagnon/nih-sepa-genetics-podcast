"""Run 075: verify_feed() must read the show-notes LINK's VALUE.

Every item publish_feed.py writes carries a show-notes href -- notes_html()
and read_notes_html() both emit `<p><a href="...-notes.md">...</a></p>`
unconditionally, in both lanes and on the pre-produced path -- and the notes
are a published deliverable: they carry the unabridged disclosure, the
evidence boundaries and every numbered citation with its Zotero link,
deliberately left in full when David shortened the SPOKEN disclosure to one
sentence. The href is a listener's only route to them from a podcast client.

Until this run the href was READ but never SCORED. The one block touching it
reduced each href to `Path(urlparse(href).path).name` and asked only whether
that filename exists locally / returns HTTP 200 live. So three classes shipped
with verify_feed() returning ok: true and an EMPTY issue list -- the verdict
publish_local() refuses on and push_to_remote()'s wait loop breaks on:

  * repointed at ANOTHER EPISODE (the existence probe is satisfied, because
    the file it names is a real published deliverable)
  * ABSENT entirely (the loop body never runs, so the item's notes are
    probed zero times -- run 041's lesson per item)
  * repointed at the SIBLING SHOW (the documented hard bug; run 063's
    advertised_base iterates XML ATTRIBUTES plus url/link ELEMENT TEXT, and
    this href is neither -- it lives inside a CDATA blob, outside that guard
    by construction, while the existence probe collapses the cross-show URL
    to its local filename and passes it)

Scoped by control: an href naming a file that does NOT exist is already
refused by the existence arm, so the unread classes are all RIGHT-SHAPE
WRONG-TARGET plus outright absence.
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

BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"
SIBLING = ("https://mrdavidgagnon.github.io/human-in-the-loop-AI-podcast/"
           "episode-001-notes.md")

def _ffmpeg() -> str:
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _make_mp3(seconds: int) -> bytes:
    """A real, DECODABLE mp3 of the requested length (silence).

    Run 058's duration gate decodes the enclosure, so synthetic bytes of the
    right length are correctly refused as "not playable audio".
    """
    import subprocess
    with tempfile.TemporaryDirectory() as box:
        out = Path(box) / "f.mp3"
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
             "-t", str(seconds), "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
            capture_output=True, check=True)
        return out.read_bytes()


_MP3_2S = _make_mp3(2)

DISCLOSURE = ("<p>This is a synthetic/dramatized interview with fictional "
              "research correspondent Dr. Rowan Field.</p><p>This is an "
              "AI-generated summary that may contain errors.</p>")

ITEM = """      <item><title>Ep {num}</title><description>Desc {num}</description>\
<guid isPermaLink="false">{guid}</guid>\
<enclosure url="{base}/{audio}" length="{length}" type="audio/mpeg"/>\
<pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate>\
<itunes:episode>{ordinal}</itunes:episode>\
<itunes:episodeType>full</itunes:episodeType>\
<itunes:duration>00:00:02</itunes:duration>\
<itunes:explicit>false</itunes:explicit>\
<itunes:image href="{base}/cover.png"/>\
<content:encoded><![CDATA[{disclosure}{link}]]></content:encoded></item>"""

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" \
xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>\
<title>Moral Machines</title><link>{base}/</link>\
<description>Playful, dramatized interviews synthesizing research on machine \
ethics and moral decision-making for the 2026 NIH SEPA project.</description>\
<language>en-us</language><copyright>(c) 2026 Field Day Lab, UW-Madison\
</copyright><itunes:author>Field Day Lab, UW-Madison</itunes:author>\
<itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type>\
<itunes:category text="Education"/><itunes:image href="{base}/cover.png"/>\
<image><url>{base}/cover.png</url><title>Moral Machines</title>\
<link>{base}/</link></image>
{items}
</channel></rss>"""

INDEX_HTML = ("<!doctype html><html><head><title>Moral Machines</title></head>"
              "<body><h1>Moral Machines</h1><ul>{items}</ul></body></html>")


class ShowNotesLinkGateTests(unittest.TestCase):
    """The href's VALUE, not merely the existence of what it names."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="notes_link_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        (self.dir / "pipeline").mkdir()
        self.cover = rp.decode_png.__globals__.get("_unused", None)
        self.cover_bytes = _make_cover()
        (self.site / "cover.png").write_bytes(self.cover_bytes)
        (self.dir / "cover.png").write_bytes(self.cover_bytes)
        self._root = rp.ROOT
        self._ledger = rp.LEDGER_PATH
        self._manifest = rp.MANIFEST_PATH
        self._read = rp.READ_MANIFEST_PATH
        rp.ROOT = self.dir
        rp.LEDGER_PATH = self.dir / "pipeline" / "state.json"
        rp.MANIFEST_PATH = self.dir / "pipeline" / "manifest.json"
        rp.READ_MANIFEST_PATH = self.dir / "pipeline" / "read-episodes.json"
        self.addCleanup(self._restore)
        self.numbers = ["001"]
        self.read_numbers = []
        self._write_registries()

    def _restore(self):
        rp.ROOT = self._root
        rp.LEDGER_PATH = self._ledger
        rp.MANIFEST_PATH = self._manifest
        rp.READ_MANIFEST_PATH = self._read

    # ------------------------------------------------------------- fixtures
    def _write_registries(self):
        eps = {}
        for n in self.numbers:
            eps[n] = {"number": n, "status": "published_and_moved",
                      "title": "Ep %s" % n, "description": "Desc %s" % n,
                      "sources": ["SRC%s" % n]}
        rp.MANIFEST_PATH.write_text(json.dumps({"episodes": eps}))
        rp.LEDGER_PATH.write_text(json.dumps({"schema_version": 1, "episodes": {
            n: {"status": "published_and_moved", "transitions": [
                {"from": "rendering", "to": "rendered",
                 "at": "2026-11-03T23:39:45Z", "reason": "fixture"}]}
            for n in self.numbers}}))
        read = {n: {"verified": True, "base": "episode-%s-reading" % n,
                    "title": "Reading %s" % n}
                for n in self.read_numbers}
        rp.READ_MANIFEST_PATH.write_text(json.dumps({"episodes": read}))

    def _audio_name(self, num):
        return ("episode-%s-reading.mp3" % num if num in self.read_numbers
                else "episode-%s.mp3" % num)

    def _guid(self, num):
        return ("moral-machines-episode-%s-reading-SRC%s" % (num, num)
                if num in self.read_numbers
                else "moral-machines-episode-%s" % num)

    def write_feed(self, links=None, notes_files=None):
        """links: {num: href or None}. notes_files: extra names to create."""
        links = links if links is not None else {}
        items, index_items = [], []
        for n in self.numbers:
            audio = self._audio_name(n)
            (self.site / audio).write_bytes(_MP3_2S)
            href = links.get(n, "episode-%s-notes.md" % n)
            link_html = ('<p><a href="%s">Full source notes</a></p>' % href
                         if href else "")
            items.append(ITEM.format(
                num=n, base=BASE, audio=audio, guid=self._guid(n),
                ordinal=int(n), length=(self.site / audio).stat().st_size,
                disclosure=DISCLOSURE, link=link_html))
            index_items.append(
                '<li><a href="%s">Episode %s</a> &middot; '
                '<a href="episode-%s-notes.md">notes</a></li>' % (audio, n, n))
            (self.site / ("episode-%s-notes.md" % n)).write_text("# notes\n")
            if n in self.read_numbers:
                (self.site / ("episode-%s-reading-notes.md" % n)).write_text(
                    "# notes\n")
        for extra in (notes_files or []):
            (self.site / extra).write_text("# notes\n")
        (self.site / "index.html").write_text(
            INDEX_HTML.format(items="".join(index_items)))
        feed = self.site / "feed.xml"
        feed.write_text(FEED.format(base=BASE, items="\n".join(items)))
        return feed

    def verify(self, feed=None):
        return rp.verify_feed(str(feed or (self.site / "feed.xml")))

    def _notes_checks(self, result):
        return [c for c in result["checks"] if c["name"] == "show_notes_link"]

    def _assert_refused(self, needle, result=None):
        result = result if result is not None else self.verify()
        self.assertFalse(result["ok"], "expected refusal, got ok")
        self.assertTrue(any(needle in i for i in result["issues"]),
                        "no issue contained %r: %s" % (needle, result["issues"]))
        return result

    # -------------------------------------------------------------- healthy
    def test_a_correct_link_passes_and_is_reported(self):
        self.write_feed()
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        checks = self._notes_checks(result)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["episode"], "001")
        self.assertEqual(checks[0]["lane"], "interview")
        self.assertEqual(checks[0]["advertised"], ["episode-001-notes.md"])
        self.assertEqual(checks[0]["expected"], ["episode-001-notes.md"])

    def test_the_check_runs_once_per_item(self):
        self.numbers = ["001", "002"]
        self._write_registries()
        self.write_feed()
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(sorted(c["episode"] for c in
                                self._notes_checks(result)), ["001", "002"])

    # ----------------------------------------- class 1: wrong episode
    def test_a_link_to_another_episode_is_refused(self):
        """The target EXISTS, so the existence arm cannot be what refuses it."""
        self.numbers = ["001", "002"]
        self._write_registries()
        self.write_feed(links={"001": "episode-002-notes.md"})
        self.assertTrue((self.site / "episode-002-notes.md").exists())
        result = self._assert_refused("and not this episode's")
        self.assertFalse(any("missing local notes file" in i
                             for i in result["issues"]),
                         "the existence arm must not be the refusing check")

    def test_the_refusal_names_both_the_episode_and_the_wrong_target(self):
        self.write_feed(links={"001": "episode-003-notes.md"},
                        notes_files=["episode-003-notes.md"])
        result = self._assert_refused("episode-003-notes.md")
        self.assertTrue(any("episode 001" in i for i in result["issues"]))
        self.assertTrue(any("another episode" in i for i in result["issues"]))

    # ----------------------------------------- class 2: absent
    def test_an_absent_link_is_refused(self):
        self.write_feed(links={"001": None})
        self._assert_refused("advertises no show-notes link")

    def test_an_absent_link_still_leaves_the_disclosure_prose_intact(self):
        """Proves the 064 guard is not what refuses it."""
        self.write_feed(links={"001": None})
        result = self.verify()
        # TEST BUG GUARD: the new refusal message itself contains the word
        # "disclosure" (it explains what the notes carry), so matching on that
        # word alone cannot distinguish the 064 guard from this one. Assert on
        # the 064 check's own phrasing instead.
        self.assertFalse(any("required interview disclosure phrase" in i
                             or "required reading disclosure phrase" in i
                             for i in result["issues"]), result["issues"])

    def test_an_empty_href_is_refused(self):
        self.write_feed(links={"001": ""})
        self._assert_refused("advertises no show-notes link")

    # ----------------------------------------- class 3: cross-show
    def test_a_sibling_show_link_is_refused(self):
        self.write_feed(links={"001": SIBLING})
        result = self._assert_refused("cross-show substring")
        self.assertTrue(any("not under this show" in i
                            for i in result["issues"]))

    def test_an_off_base_absolute_link_is_refused(self):
        self.write_feed(links={"001": "https://evil.example.com/"
                                      "episode-001-notes.md"})
        self._assert_refused("not under this show")

    def test_an_absolute_link_under_this_shows_base_is_accepted(self):
        self.write_feed(links={"001": BASE + "/episode-001-notes.md"})
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])

    # ----------------------------------------- the read lane
    def test_a_reading_accepts_the_reading_notes_spelling(self):
        self.numbers = ["501"]
        self.read_numbers = ["501"]
        self._write_registries()
        self.write_feed(links={"501": "episode-501-reading-notes.md"})
        result = self.verify()
        checks = self._notes_checks(result)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["lane"], "read")
        self.assertFalse(any("show-notes link" in i
                             for i in result["issues"]), result["issues"])

    def test_a_reading_accepts_the_plain_spelling(self):
        self.numbers = ["501"]
        self.read_numbers = ["501"]
        self._write_registries()
        self.write_feed(links={"501": "episode-501-notes.md"})
        result = self.verify()
        self.assertFalse(any("show-notes link" in i
                             for i in result["issues"]), result["issues"])

    def test_a_reading_linking_to_an_interviews_notes_is_refused(self):
        self.numbers = ["501"]
        self.read_numbers = ["501"]
        self._write_registries()
        self.write_feed(links={"501": "episode-001-notes.md"},
                        notes_files=["episode-001-notes.md"])
        self._assert_refused("and not this episode's")

    # ----------------------------------------- nothing granted
    def test_a_nonexistent_target_is_still_refused_by_the_existence_arm(self):
        """The CONTROL that bounds the claim (run 073)."""
        self.write_feed(links={"001": "episode-999-notes.md"})
        self._assert_refused("missing local notes file episode-999-notes.md")

    def test_no_legacy_waiver(self):
        """Run 036: a waiver is a gate with the sign flipped."""
        self.write_feed(links={"001": "episode-002-notes.md"},
                        notes_files=["episode-002-notes.md"])
        rp.LEDGER_PATH.write_text(json.dumps({"schema_version": 1, "episodes": {
            "001": {"status": "published"}}}))
        self._assert_refused("and not this episode's")

    def test_the_check_writes_nothing(self):
        import hashlib
        feed = self.write_feed()
        watched = [feed, rp.LEDGER_PATH, rp.MANIFEST_PATH, rp.READ_MANIFEST_PATH]
        before = {p.name: hashlib.md5(p.read_bytes()).hexdigest()
                  for p in watched}
        for _ in range(3):
            self.verify()
        after = {p.name: hashlib.md5(p.read_bytes()).hexdigest()
                 for p in watched}
        self.assertEqual(before, after)


def _make_cover(size=1400):
    """A real decodable PNG -- run 074 gates format, CRCs and dimensions."""
    import struct
    import zlib

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x30\x40" * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    unittest.main()
