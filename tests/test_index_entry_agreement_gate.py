"""Run 087: the landing page must agree with the feed ENTRY BY ENTRY.

Runs 066 and 073 gated the landing page's identity and its channel-level
navigation. The episode list itself was gated in AGGREGATE only: the existence
arm asks whether each linked file is deployed, and the catalogue arm compares the
SET of episode numbers found in the page's hrefs with the SET the feed carries.
Neither can relate an entry's visible label -- the text a listener clicks -- to
the file that entry points at. So the page can advertise "Episode 001" while its
audio href resolves to episode-002.mp3: the existence arm is satisfied because
episode-002.mp3 is a real deployed deliverable, and the set arm is satisfied
because a swap between two episodes leaves the set unchanged. The listener who
clicks the entry for one paper hears another paper's audio and lands on another
paper's citations, evidence boundaries and Zotero links -- run 075's
right-shape/wrong-target class in the second place this show advertises the same
routes.

The kind label is gated too: "Reading" promises a verbatim reading and "Episode"
the dramatized interview, and the two lanes name their deliverables differently
(`episode-NNN-reading.mp3` vs `episode-NNN.mp3`). A mislabel changes nothing
either aggregate arm can see.

Scoped by control (run 073's rule): an entry naming a file that does NOT exist is
already refused by the existence arm, so the unread classes are right-shape
wrong-target, outright absence of an entry, a wrong kind label, and a duplicate.

**Second half, found this run.** The per-entry arm iterates the FEED items and
looks each one up in the page's labelled entries. Nothing iterates the entries in
the other direction, so an entry whose label names an episode no feed item carries
is READ but never scored -- and the aggregate arm cannot see it either, because it
derives numbers from the HREF text rather than the label. A page listing an
episode the feed does not carry, pointing at another episode's real files, shipped
ok: true with an empty issue list. The reverse arm is added here; the control that
scopes it is the same entry naming a nonexistent file, which the pre-existing arm
already refused.

No legacy waiver (run 036). Entries with no episode label -- the RSS-feed link, a
home link -- are not episode entries and stay with the existing arms.
"""
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import robust_pipeline as rp  # noqa: E402

BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"


def _ffmpeg() -> str:
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _make_mp3(seconds: int = 2) -> bytes:
    """A real, DECODABLE mp3 (silence) -- run 058 decodes enclosures."""
    with tempfile.TemporaryDirectory() as box:
        out = Path(box) / "f.mp3"
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
             "-t", str(seconds), "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
            capture_output=True, check=True)
        return out.read_bytes()


def _make_cover(size: int = 1400) -> bytes:
    """A real decodable PNG -- run 074 gates format, CRCs and dimensions."""
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x30\x40" * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


_MP3_2S = _make_mp3(2)
COVER = _make_cover()

DISC = ("<p>This is a synthetic/dramatized interview with fictional research "
        "correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary "
        "that may contain errors.</p>")

# The disclosure arm is lane-specific by design (run 064): a reading must carry
# the verbatim-reading block and is refused for carrying the interview one.
READING_DISC = ("<p>This episode is a complete automated text-to-speech reading "
                "of the body text of one work, read verbatim by a synthetic "
                "voice. It is not an interview, not a summary, and not a "
                "dramatization: Dr. Rowan Field does not appear.</p>")

ITEM = ("""      <item><title>Ep {num}</title><description>Desc {num}</description>"""
        """<guid isPermaLink="false">{guid}</guid>"""
        """<enclosure url="{base}/{audio}" length="{length}" type="audio/mpeg"/>"""
        """<pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate>"""
        """<itunes:episode>{ordinal}</itunes:episode>"""
        """<itunes:episodeType>full</itunes:episodeType>"""
        """<itunes:duration>00:00:02</itunes:duration>"""
        """<itunes:explicit>false</itunes:explicit>"""
        """<itunes:image href="{base}/cover.png"/>"""
        """<content:encoded><![CDATA[{disc}{link}]]></content:encoded></item>""")

FEED = ("""<?xml version="1.0" encoding="UTF-8"?>\n"""
        """<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" """
        """xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>"""
        """<title>Moral Machines</title><link>{base}/</link>"""
        """<description>Playful, dramatized interviews synthesizing research on """
        """machine ethics and moral decision-making for the 2026 NIH SEPA project."""
        """</description><language>en-us</language>"""
        """<copyright>(c) 2026 Field Day Lab, UW-Madison</copyright>"""
        """<itunes:author>Field Day Lab, UW-Madison</itunes:author>"""
        """<itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type>"""
        """<itunes:category text="Education"/><itunes:image href="{base}/cover.png"/>"""
        """<image><url>{base}/cover.png</url><title>Moral Machines</title>"""
        """<link>{base}/</link></image>\n{items}\n</channel></rss>""")

PAGE = ('<!doctype html><html><head><title>Moral Machines</title></head><body>'
        '<h1>Moral Machines</h1><p><a href="feed.xml">RSS feed</a></p><ul>'
        '{items}</ul></body></html>')


def entry(kind_label, audio, notes):
    """One landing-page entry, in the shape publish_feed.py generates."""
    return (f'<li><a href="{audio}">{kind_label}</a> &middot; '
            f'<a href="{notes}">notes</a></li>')


class IndexEntryAgreementTests(unittest.TestCase):
    """Label-to-target agreement per entry, not just set membership."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="index_entry_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        (self.dir / "pipeline").mkdir()
        (self.site / "cover.png").write_bytes(COVER)
        (self.dir / "cover.png").write_bytes(COVER)
        self._root, self._ledger = rp.ROOT, rp.LEDGER_PATH
        self._manifest, self._read = rp.MANIFEST_PATH, rp.READ_MANIFEST_PATH
        rp.ROOT = self.dir
        rp.LEDGER_PATH = self.dir / "pipeline" / "state.json"
        rp.MANIFEST_PATH = self.dir / "pipeline" / "manifest.json"
        rp.READ_MANIFEST_PATH = self.dir / "pipeline" / "read-episodes.json"
        self.addCleanup(self._restore)
        self.numbers = ["001", "002"]
        self.read_numbers = []
        self._write_registries()

    def _restore(self):
        rp.ROOT, rp.LEDGER_PATH = self._root, self._ledger
        rp.MANIFEST_PATH, rp.READ_MANIFEST_PATH = self._manifest, self._read

    def _audio(self, num):
        return (f"episode-{num}-reading.mp3" if num in self.read_numbers
                else f"episode-{num}.mp3")

    def _notes(self, num):
        return (f"episode-{num}-reading-notes.md" if num in self.read_numbers
                else f"episode-{num}-notes.md")

    def _guid(self, num):
        return (f"moral-machines-episode-{num}-reading-SRC{num}"
                if num in self.read_numbers else f"moral-machines-episode-{num}")

    def _write_registries(self):
        eps = {}
        for n in self.numbers:
            eps[n] = {"number": n, "status": "published_and_moved",
                      "title": f"Ep {n}", "description": f"Desc {n}",
                      "sources": [f"SRC{n}"]}
        rp.MANIFEST_PATH.write_text(json.dumps({"episodes": eps}))
        rp.LEDGER_PATH.write_text(json.dumps({"schema_version": 1, "episodes": {
            n: {"status": "published_and_moved", "transitions": [
                {"from": "rendering", "to": "rendered",
                 "at": "2026-11-03T23:39:45Z", "reason": "fixture"}]}
            for n in self.numbers}}))
        rp.READ_MANIFEST_PATH.write_text(json.dumps({"episodes": {
            n: {"verified": True, "base": f"episode-{n}-reading",
                "title": f"Reading {n}"} for n in self.read_numbers}}))

    def build(self, entries=None):
        items = []
        for n in list(self.numbers) + list(self.read_numbers):
            audio = self._audio(n)
            (self.site / audio).write_bytes(_MP3_2S)
            (self.site / self._notes(n)).write_text("# notes\n")
            items.append(ITEM.format(
                num=n, base=BASE, audio=audio, guid=self._guid(n),
                ordinal=int(n), length=(self.site / audio).stat().st_size,
                disc=READING_DISC if n in self.read_numbers else DISC,
                link=f'<p><a href="{self._notes(n)}">notes</a></p>'))
        feed = self.site / "feed.xml"
        feed.write_text(FEED.format(base=BASE, items="\n".join(items)))
        if entries is None:
            entries = [entry(("Reading" if n in self.read_numbers else "Episode")
                             + f" {n}", self._audio(n), self._notes(n))
                       for n in list(self.numbers) + list(self.read_numbers)]
        (self.site / "index.html").write_text(PAGE.format(items="".join(entries)))
        return feed

    def index_check(self, result):
        return [c for c in result["checks"] if c["name"] == "index_page"][0]

    def refused(self, needle, result):
        self.assertFalse(result["ok"], f"expected refusal, got ok: {result['issues']}")
        hits = [i for i in result["issues"] if needle in i]
        self.assertTrue(hits, f"no issue contained {needle!r}: {result['issues']}")
        return hits[0]

    # ------------------------------------------------------------- healthy
    def test_generator_shaped_page_passes_and_reports_entries(self):
        result = rp.verify_feed(str(self.build()))
        self.assertTrue(result["ok"], result["issues"])
        check = self.index_check(result)
        self.assertEqual(check["entries"], [
            {"kind": "episode", "episode": "001",
             "targets": ["episode-001-notes.md", "episode-001.mp3"]},
            {"kind": "episode", "episode": "002",
             "targets": ["episode-002-notes.md", "episode-002.mp3"]}])
        self.assertEqual(check["page_episodes"], check["feed_episodes"])

    def test_a_reading_entry_is_accepted_under_both_lane_spellings(self):
        self.numbers, self.read_numbers = ["001"], ["501"]
        self._write_registries()
        result = rp.verify_feed(str(self.build()))
        self.assertTrue(result["ok"], result["issues"])
        check = self.index_check(result)
        self.assertEqual(check["entries"], [
            {"kind": "episode", "episode": "001",
             "targets": ["episode-001-notes.md", "episode-001.mp3"]},
            {"kind": "reading", "episode": "501",
             "targets": ["episode-501-reading-notes.md",
                         "episode-501-reading.mp3"]}])

    # ------------------------- class 1: label right, target another episode
    def test_a_swapped_audio_pair_is_refused_though_the_set_agrees(self):
        """Symmetric swap: the aggregate set arm CANNOT see it."""
        entries = [entry("Episode 001", "episode-002.mp3", "episode-001-notes.md"),
                   entry("Episode 002", "episode-001.mp3", "episode-002-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        check = self.index_check(result)
        self.assertEqual(check["page_episodes"], check["feed_episodes"])
        issue = self.refused("another episode's audio", result)
        self.assertIn("episode-002.mp3", issue)
        self.assertNotIn("omits episode", " ".join(result["issues"]))

    def test_a_notes_link_pointing_at_another_episode_is_refused(self):
        entries = [entry("Episode 001", "episode-001.mp3", "episode-002-notes.md"),
                   entry("Episode 002", "episode-002.mp3", "episode-002-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        self.refused("another episode's show notes", result)

    # ------------------------- class 2: entry with no episode label
    def test_an_entry_with_no_label_is_refused_though_its_files_exist(self):
        entries = [entry("listen", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Episode 002", "episode-002.mp3", "episode-002-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        self.refused("has no entry labelled episode 001", result)

    # ------------------------- class 3: wrong kind label
    def test_a_reading_entry_labelled_episode_is_refused(self):
        self.numbers, self.read_numbers = ["001"], ["501"]
        self._write_registries()
        entries = [entry("Episode 001", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Episode 501", "episode-501-reading.mp3",
                         "episode-501-reading-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        self.refused("is labelled Episode, but the feed item is", result)

    def test_an_interview_entry_labelled_reading_is_refused(self):
        entries = [entry("Reading 001", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Episode 002", "episode-002.mp3", "episode-002-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        self.refused("is labelled Reading, but the feed item is", result)

    # ------------------------- class 4: duplicate entry
    def test_a_duplicate_entry_with_different_targets_is_refused(self):
        entries = [entry("Episode 001", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Episode 001", "episode-002.mp3", "episode-002-notes.md"),
                   entry("Episode 002", "episode-002.mp3", "episode-002-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        self.refused("lists episode 001 2 times with different targets", result)

    # --------------- class 5 (found this run): label names no feed item
    def test_an_entry_labelled_an_absent_episode_is_refused(self):
        """Every feed episode still has its own entry, so the forward arm is
        satisfied; the aggregate arm reads numbers from HREFs, not labels."""
        entries = [entry("Episode 001", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Episode 002", "episode-002.mp3", "episode-002-notes.md"),
                   entry("Episode 004", "episode-002.mp3", "episode-002-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        check = self.index_check(result)
        self.assertEqual(check["page_episodes"], check["feed_episodes"])
        self.refused("has an entry labelled episode 004, which the feed does not "
                     "carry", result)

    def test_a_reading_entry_labelled_an_absent_reading_is_refused(self):
        self.numbers, self.read_numbers = ["001"], ["501"]
        self._write_registries()
        entries = [entry("Episode 001", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Reading 501", "episode-501-reading.mp3",
                         "episode-501-reading-notes.md"),
                   entry("Reading 502", "episode-501-reading.mp3",
                         "episode-501-reading-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        self.refused("has an entry labelled reading 502, which the feed does not "
                     "carry", result)

    # --------------------------------------------------------- controls
    def test_a_nonexistent_target_is_still_refused_by_the_existence_arm(self):
        """Run 073's scope control: this class was never the gap."""
        entries = [entry("Episode 001", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Episode 002", "episode-002.mp3", "episode-002-notes.md"),
                   entry("Episode 004", "episode-004.mp3", "episode-004-notes.md")]
        result = rp.verify_feed(str(self.build(entries)))
        self.refused("which is not deployed in feed-site/", result)
        self.refused("has an entry labelled episode 004", result)

    def test_a_cross_show_href_is_still_refused_by_the_show_notes_arm(self):
        """Run 075's guard is unaffected: the entry arm cannot reach a
        cross-show URL because it collapses the href to a filename."""
        self.numbers = ["001"]
        self._write_registries()
        feed = self.build()
        (self.site / "episode-001-notes.md").write_text("# notes\n")
        result = rp.verify_feed(str(feed))
        self.assertTrue(result["ok"], result["issues"])
        # Repoint the ITEM's show-notes href at the sibling show; the entry arm
        # sees only the filename and must not be what refuses it.
        (self.site / "feed.xml").write_text(
            feed.read_text().replace(
                '<p><a href="episode-001-notes.md">notes</a></p>',
                '<p><a href="https://mrdavidgagnon.github.io/human-in-the-loop-AI-podcast/'
                'episode-001-notes.md">notes</a></p>'))
        result = rp.verify_feed(str(feed))
        self.assertFalse(result["ok"], result["issues"])
        self.assertTrue(any("cross-show substring" in i for i in result["issues"]),
                        result["issues"])
        self.assertFalse(any("another episode's show notes" in i
                             for i in result["issues"]), result["issues"])

    def test_non_episode_entries_stay_with_the_existing_arms(self):
        """The RSS-feed link has no episode label and is not an episode entry."""
        entries = [entry("Episode 001", "episode-001.mp3", "episode-001-notes.md"),
                   entry("Episode 002", "episode-002.mp3", "episode-002-notes.md")]
        feed = self.build(entries)
        (self.site / "index.html").write_text(
            (self.site / "index.html").read_text().replace(
                '<p><a href="feed.xml">RSS feed</a></p>',
                '<p><a href="feed.xml">the RSS feed</a></p>'))
        result = rp.verify_feed(str(feed))
        self.assertTrue(result["ok"], result["issues"])
        check = self.index_check(result)
        self.assertIn("feed.xml", check["links"])
        self.assertEqual(len(check["entries"]), 2)

    def test_the_arm_grants_nothing_to_a_page_it_cannot_read(self):
        feed = self.build()
        (self.site / "index.html").unlink()
        result = rp.verify_feed(str(feed))
        self.assertFalse(result["ok"], "expected refusal for an absent page")
        self.assertTrue(any("index.html" in i for i in result["issues"]),
                        result["issues"])

    def test_the_arm_writes_nothing(self):
        feed = self.build()
        before = {p: p.read_bytes() for p in list(self.site.iterdir())
                  if p.is_file()}
        rp.verify_feed(str(feed))
        after = {p: p.read_bytes() for p in list(self.site.iterdir()) if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
