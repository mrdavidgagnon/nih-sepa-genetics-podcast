"""Run 072: verify_feed() must gate each item's own artwork and rating.

``publish_feed.py`` emits on EVERY item it writes, in BOTH lanes::

    <itunes:explicit>false</itunes:explicit>
    <itunes:image href="{BASE_URL}/cover.png"/>

Until run 072 nothing read either per-item value, and three existing guards
each stop just short of them:

* Run 057 gated COVER ART, but its check is a document-wide SET UNION over
  every image reference, resolved to FILENAMES and probed for existence. It
  answers "do the referenced files exist", not "does each item advertise
  artwork" -- so removing the reference from every item (or from every item
  AND the channel) leaves the surviving ``<image><url>`` repopulating the
  union and the feed shipping green. An aggregate check cannot gate a
  per-element requirement.
* Run 063 gated an advertised URL's base and absoluteness -- a MISSING URL
  advertises nothing and is outside that guard by construction.
* Run 070 gated the CHANNEL's ``<itunes:explicit>``; the item field of the
  same name had no reader (run 032's lane-asymmetry axis on the feed's two
  levels).

Ten mutation classes each shipped ``ok: true`` with an EMPTY issue list and
were indistinguishable from an intact feed -- the verdict ``publish_local()``
refuses on and ``push_to_remote()``'s wait loop breaks on to declare a deploy
live.
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

BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"

FIXTURE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><link>{base}/</link><description>Playful, dramatized interviews synthesizing research on machine ethics.</description><itunes:image href="{channel_cover}"/><image><url>{channel_cover}</url><title>Moral Machines</title><link>{base}/</link></image>
{items}
</channel></rss>
"""

ITEM = """      <item><title>Ep {num}</title><description>Desc {num}</description><guid isPermaLink="false">moral-machines-episode-{num}</guid><enclosure url="{base}/episode-{num}.mp3" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>{ordinal}</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:duration>00:00:02</itunes:duration>{rating}{artwork}<content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p><p><a href="episode-{num}-notes.md">Full source notes, evidence limitations, and direct Zotero links</a></p>]]></content:encoded></item>"""

INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Moral Machines</title></head><body><h1>Moral Machines</h1>'
    '<p><a href="feed.xml">RSS feed</a></p><h2>Episodes</h2><ul>{li}</ul>'
    "</body></html>"
)


def _mp3(seconds: int = 2) -> bytes:
    """A real decodable mp3 -- magic bytes plus zeros are correctly refused
    by run 058's duration gate, which is a fixture bug, not a defect."""
    sys.path.insert(0, "/data/.openclaw/workspace/vendor/two-voice-tts")
    import imageio_ffmpeg
    box = Path(tempfile.mkdtemp())
    out = box / "f.mp3"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi",
         "-i", "anullsrc=r=22050:cl=mono", "-t", str(seconds),
         "-c:a", "libmp3lame", "-b:a", "32k", str(out)],
        capture_output=True, check=True)
    data = out.read_bytes()
    shutil.rmtree(box, ignore_errors=True)
    return data


_MP3 = _mp3()


class ItemArtworkRatingGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="item_artwork_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        cover = b"\x89PNG\r\n\x1a\n" + b"art" * 64
        (self.site / "cover.png").write_bytes(cover)
        (self.dir / "cover.png").write_bytes(cover)
        # A second real artwork file, so a DISAGREEMENT can be tested without
        # the run-057 existence probe firing instead of the agreement arm.
        (self.site / "other.png").write_bytes(cover)
        (self.dir / "other.png").write_bytes(cover)
        self.numbers = ["001"]
        self._write_assets()
        self.ledger = self.dir / "state.json"
        self.manifest = self.dir / "manifest.json"
        self.read_manifest = self.dir / "read-episodes.json"
        self._write_registries()
        for name, value in (("ROOT", self.dir), ("PIPELINE", self.dir),
                            ("LEDGER_PATH", self.ledger),
                            ("MANIFEST_PATH", self.manifest),
                            ("READ_MANIFEST_PATH", self.read_manifest)):
            saved = getattr(rp, name)
            setattr(rp, name, value)
            self.addCleanup(lambda n=name, v=saved: setattr(rp, n, v))
        self.feed = self.site / "feed.xml"
        self.write_feed()

    # ------------------------------------------------------------- helpers
    def _write_assets(self):
        for n in self.numbers:
            (self.site / f"episode-{n}.mp3").write_bytes(_MP3)
            (self.site / f"episode-{n}-notes.md").write_text(
                "# notes\n\nFull source notes, evidence limitations, and "
                "direct Zotero links\n\n1. A source\n")
        (self.site / "index.html").write_text(INDEX_HTML.format(
            li="".join(f'<li><a href="episode-{n}.mp3">Episode {n}</a> '
                       f'&middot; <a href="episode-{n}-notes.md">notes</a>'
                       f"</li>" for n in self.numbers)))

    def _write_registries(self, status="published_and_moved"):
        self.ledger.write_text(json.dumps({"schema_version": 1, "episodes": {
            n: {"status": status, "transitions": [
                {"from": "rendering", "to": "rendered",
                 "at": "2026-11-03T23:39:45Z", "reason": "fixture"}]}
            for n in self.numbers}}))
        self.manifest.write_text(json.dumps({"episodes": {
            n: {"number": n, "title": f"Ep {n}", "description": f"Desc {n}",
                "sources": [f"KEY{n}"]} for n in self.numbers}}))
        self.read_manifest.write_text(json.dumps({"episodes": {}}))

    def write_feed(self, rating="false", artwork="cover.png",
                   channel_cover=None):
        """rating/artwork: a value, or False to omit the element entirely."""
        if rating is False:
            rating_xml = ""
        else:
            rating_xml = f"<itunes:explicit>{rating}</itunes:explicit>"
        if artwork is False:
            art_xml = ""
        elif artwork == "":
            art_xml = '<itunes:image href=""/>'
        else:
            art_xml = f'<itunes:image href="{BASE}/{artwork}"/>'
        chan = channel_cover or f"{BASE}/cover.png"
        items = "\n".join(
            ITEM.format(num=n, base=BASE, ordinal=int(n), rating=rating_xml,
                        artwork=art_xml,
                        length=(self.site / f"episode-{n}.mp3").stat().st_size)
            for n in self.numbers)
        self.feed.write_text(FIXTURE_FEED.format(
            base=BASE, items=items, channel_cover=chan))

    def verify(self):
        return rp.verify_feed(self.feed)

    def _assert_refused(self, phrase):
        result = self.verify()
        self.assertFalse(result["ok"], "expected a refusal")
        self.assertTrue(any(phrase in i for i in result["issues"]),
                        f"{phrase!r} not in {result['issues']}")
        return result

    # --------------------------------------------------------- happy path
    def test_a_correct_item_passes_and_is_reported(self):
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        checks = [c for c in result["checks"]
                  if c["name"] == "item_artwork_rating"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["episode"], "001")
        self.assertEqual(checks[0]["rating"], "false")
        self.assertEqual(checks[0]["artwork"], f"{BASE}/cover.png")
        self.assertEqual(checks[0]["channel_artwork"], f"{BASE}/cover.png")
        self.assertEqual(checks[0]["lane"], "interview")

    def test_the_check_runs_once_per_item(self):
        self.numbers = ["001", "002"]
        self._write_assets()
        self._write_registries()
        self.write_feed()
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        checks = [c for c in result["checks"]
                  if c["name"] == "item_artwork_rating"]
        self.assertEqual(sorted(c["episode"] for c in checks),
                         ["001", "002"])

    # ------------------------------------------------------------ artwork
    def test_a_missing_item_artwork_is_refused(self):
        self.write_feed(artwork=False)
        self._assert_refused("advertises no <itunes:image>")

    def test_an_empty_item_artwork_href_is_refused(self):
        self.write_feed(artwork="")
        self._assert_refused("empty <itunes:image> href")

    def test_item_artwork_disagreeing_with_the_channel_is_refused(self):
        """other.png EXISTS, so run 057's probe cannot be what refuses it."""
        self.write_feed(artwork="other.png")
        result = self._assert_refused("while the channel advertises")
        self.assertFalse(any("missing local cover art" in i
                             for i in result["issues"]),
                         "the agreement arm, not the existence probe, must "
                         "be what refuses this")

    def test_a_consistent_artwork_rename_is_not_refused(self):
        """A rename applied to the channel AND the item is legitimate."""
        self.write_feed(artwork="other.png",
                        channel_cover=f"{BASE}/other.png")
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])

    def test_the_missing_artwork_issue_names_the_episode(self):
        self.write_feed(artwork=False)
        result = self.verify()
        self.assertTrue(any("episode 001" in i for i in result["issues"]),
                        result["issues"])

    # ------------------------------------------------------------- rating
    def test_a_missing_item_rating_is_refused(self):
        self.write_feed(rating=False)
        self._assert_refused("advertises no <itunes:explicit>")

    def test_an_empty_item_rating_is_refused(self):
        self.write_feed(rating="")
        self._assert_refused("empty <itunes:explicit>")

    def test_an_item_rating_of_true_is_refused(self):
        self.write_feed(rating="true")
        self._assert_refused("every episode this pipeline produces is")

    def test_an_item_rating_outside_the_vocabulary_is_refused(self):
        self.write_feed(rating="banana")
        self._assert_refused("which is not one of")

    def test_a_wrong_case_item_rating_is_named_as_case(self):
        """An envelope-like value is machine-read, so case is exact."""
        self.write_feed(rating="False")
        result = self._assert_refused("only in case")
        self.assertFalse(any("which is not one of" in i
                             for i in result["issues"]),
                         "a case defect must not be reported as an "
                         "out-of-vocabulary value")

    def test_the_rating_issue_names_the_episode(self):
        self.write_feed(rating="true")
        result = self.verify()
        self.assertTrue(any("episode 001" in i for i in result["issues"]),
                        result["issues"])

    # ----------------------------------------------------- nothing granted
    def test_both_fields_can_be_refused_together(self):
        self.write_feed(rating=False, artwork=False)
        result = self.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("<itunes:image>" in i for i in result["issues"]))
        self.assertTrue(any("<itunes:explicit>" in i
                            for i in result["issues"]))

    def test_a_legacy_item_gets_no_artwork_waiver(self):
        """A waiver is a gate with the sign flipped (run 036)."""
        self._write_registries(status="published")
        self.write_feed(artwork=False)
        self._assert_refused("advertises no <itunes:image>")

    def test_a_legacy_item_gets_no_rating_waiver(self):
        self._write_registries(status="published")
        self.write_feed(rating="true")
        self._assert_refused("every episode this pipeline produces is")

    def test_the_channel_rating_gate_is_unaffected(self):
        """Run 070's channel gate must still bite independently."""
        self.write_feed()
        self.feed.write_text(self.feed.read_text().replace(
            "<itunes:author>Field Day Lab, UW–Madison</itunes:author>"
            "<itunes:explicit>false</itunes:explicit>",
            "<itunes:author>Field Day Lab, UW–Madison</itunes:author>"
            "<itunes:explicit>true</itunes:explicit>"))
        self._assert_refused("channel <itunes:explicit>")

    def test_the_cover_art_existence_probe_is_unaffected(self):
        """Run 057 must still refuse artwork whose file is absent."""
        (self.site / "cover.png").unlink()
        self._assert_refused("missing local cover art")

    def test_the_gate_writes_nothing(self):
        before = self.feed.read_bytes()
        for _ in range(3):
            self.verify()
        self.assertEqual(self.feed.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
