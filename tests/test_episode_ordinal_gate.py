"""Run 069: verify_feed() must gate the ordinal and kind it advertises.

Every feed item carries ``<itunes:episode>{int(num)}</itunes:episode>`` and a
hardcoded ``<itunes:episodeType>full</itunes:episodeType>``. The ordinal is
what every podcast client sorts the feed by and prints beside the title;
episodeType tells the client whether the item is a ``full`` episode, a
``trailer`` or ``bonus`` -- and Apple pins a trailer OUTSIDE the numbered run,
so a mislabelled episode vanishes from the sequence a listener follows.

Until run 069 nothing read either value. The sharp part: ``<itunes:episode>``
HAD a reader and run 036 REMOVED it, because it was keyed on the value ``"1"``
as a legacy waiver -- not what the field means. Run 036 was right to delete
that use; nothing replaced it, so the field went from misread to unread. A
wrong ordinal, a ``trailer`` label, a malformed value and a missing element all
shipped with ``verify_feed()`` returning ok: true and an EMPTY issue list,
which is exactly what ``publish_local()`` refuses on and what
``push_to_remote()``'s wait loop breaks on to declare a deploy live.

The ordinal is scored against the item's own GUID (``_feed_item_number()``),
making this a cross-field AGREEMENT test rather than a second opinion about
what the number ought to be.
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
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/><link>{base}/</link><description>Playful, dramatized interviews synthesizing research on machine ethics.</description><itunes:image href="{base}/cover.png"/><image><url>{base}/cover.png</url><title>Moral Machines</title><link>{base}/</link></image>
{items}
</channel></rss>
"""

ITEM = """      <item><title>Ep {num}</title><description>Desc {num}</description><guid isPermaLink="false">moral-machines-episode-{num}</guid><enclosure url="{base}/episode-{num}.mp3" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate>{episode}{etype}<itunes:duration>00:00:02</itunes:duration><itunes:explicit>false</itunes:explicit><itunes:image href="{base}/cover.png"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p><p><a href="episode-{num}-notes.md">Full source notes, evidence limitations, and direct Zotero links</a></p>]]></content:encoded></item>"""

INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Moral Machines</title></head><body><h1>Moral Machines</h1>'
    '<p><a href="feed.xml">RSS feed</a></p><h2>Episodes</h2><ul>{li}</ul>'
    "</body></html>"
)


def _mp3(seconds: int = 2) -> bytes:
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


class EpisodeOrdinalGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="ordinal_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        cover = b"\x89PNG\r\n\x1a\n" + b"art" * 64
        (self.site / "cover.png").write_bytes(cover)
        (self.dir / "cover.png").write_bytes(cover)
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

    def write_feed(self, episode=None, etype="full"):
        """episode: None -> int(num); a str -> literal; False -> omit."""
        items = []
        for n in self.numbers:
            if episode is False:
                ep = ""
            elif episode is None:
                ep = f"<itunes:episode>{int(n)}</itunes:episode>"
            else:
                ep = f"<itunes:episode>{episode}</itunes:episode>"
            et = "" if etype is False else \
                f"<itunes:episodeType>{etype}</itunes:episodeType>"
            items.append(ITEM.format(
                base=BASE, num=n, episode=ep, etype=et,
                length=(self.site / f"episode-{n}.mp3").stat().st_size))
        self.feed.write_text(FIXTURE_FEED.format(
            base=BASE, items="\n".join(items)))

    def verify(self):
        return rp.verify_feed(str(self.feed))

    def ordinal_check(self, result, index=0):
        hits = [c for c in result["checks"]
                if c.get("name") == "episode_number"]
        self.assertEqual(len(hits), len(self.numbers),
                         json.dumps([c.get("name") for c in result["checks"]]))
        return hits[index]

    def assertRefused(self, result, *needles):
        self.assertFalse(result["ok"], result["issues"])
        self.assertTrue(
            any(all(n.lower() in i.lower() for n in needles)
                for i in result["issues"]),
            f"{needles} not named in {result['issues']}")

    # ------------------------------------------------------------- healthy
    def test_an_agreeing_ordinal_passes_and_is_reported(self):
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        check = self.ordinal_check(result)
        self.assertEqual(check["advertised"], "1")
        self.assertEqual(check["episode"], "001")
        self.assertEqual(check["episode_type"], "full")
        self.assertEqual(check["lane"], "interview")

    def test_the_real_feed_still_passes(self):
        """The live catalogue must be unaffected by this gate."""
        for name in ("ROOT", "PIPELINE", "LEDGER_PATH", "MANIFEST_PATH",
                     "READ_MANIFEST_PATH"):
            setattr(rp, name, getattr(rp, name))
        tree = Path(__file__).resolve().parents[1]
        rp.ROOT = tree
        rp.PIPELINE = tree / "pipeline"
        rp.LEDGER_PATH = tree / "pipeline" / "state.json"
        rp.MANIFEST_PATH = tree / "pipeline" / "manifest.json"
        rp.READ_MANIFEST_PATH = tree / "pipeline" / "read-episodes.json"
        result = rp.verify_feed(str(tree / "feed-site" / "feed.xml"))
        self.assertTrue(result["ok"], result["issues"])
        hits = [c for c in result["checks"] if c.get("name") == "episode_number"]
        self.assertEqual(len(hits), 3)
        for hit in hits:
            self.assertEqual(int(hit["advertised"]), int(hit["episode"]))

    def test_the_required_type_is_in_the_allowed_vocabulary(self):
        self.assertIn(rp.EPISODE_TYPE_REQUIRED, rp.EPISODE_TYPE_ALLOWED)
        self.assertEqual(rp.EPISODE_TYPE_REQUIRED, "full")

    def test_the_gate_writes_nothing(self):
        before = sorted((p.name, p.read_bytes()) for p in self.site.iterdir())
        self.verify()
        after = sorted((p.name, p.read_bytes()) for p in self.site.iterdir())
        self.assertEqual(before, after)

    # ------------------------------------------------------------ refusals
    def test_an_ordinal_disagreeing_with_the_guid_is_refused(self):
        self.write_feed(episode="7")
        self.assertRefused(self.verify(), "itunes:episode", "7", "001")

    def test_a_zero_ordinal_is_refused(self):
        self.write_feed(episode="0")
        self.assertRefused(self.verify(), "ordinal of zero")

    def test_a_missing_ordinal_element_is_refused(self):
        self.write_feed(episode=False)
        self.assertRefused(self.verify(), "no <itunes:episode>")

    def test_an_empty_ordinal_is_refused(self):
        self.write_feed(episode="")
        self.assertRefused(self.verify(), "empty", "itunes:episode")

    def test_a_non_numeric_ordinal_is_refused(self):
        self.write_feed(episode="one")
        self.assertRefused(self.verify(), "malformed", "one")

    def test_a_fractional_ordinal_is_refused(self):
        self.write_feed(episode="1.5")
        self.assertRefused(self.verify(), "malformed", "1.5")

    def test_a_negative_ordinal_is_refused(self):
        self.write_feed(episode="-3")
        self.assertRefused(self.verify(), "malformed", "-3")

    def test_a_missing_episode_type_is_refused(self):
        self.write_feed(etype=False)
        self.assertRefused(self.verify(), "no <itunes:episodetype>")

    def test_a_trailer_label_is_refused(self):
        self.write_feed(etype="trailer")
        self.assertRefused(self.verify(), "trailer", "numbered run")

    def test_a_bonus_label_is_refused(self):
        self.write_feed(etype="bonus")
        self.assertRefused(self.verify(), "bonus")

    def test_a_wrong_case_type_is_refused_because_a_label_is_exact(self):
        """run 066: an identity is exact, so FULL is not full."""
        self.write_feed(etype="FULL")
        self.assertRefused(self.verify(), "full", "vocabulary")

    def test_a_junk_type_is_refused_as_outside_the_vocabulary(self):
        self.write_feed(etype="episode")
        self.assertRefused(self.verify(), "vocabulary")

    # ------------------------------------------------------ nothing granted
    def test_a_legacy_episode_gets_no_waiver(self):
        """A waiver is a gate with the sign flipped (run 036)."""
        self._write_registries(status="published")
        self.write_feed(episode="7")
        self.assertRefused(self.verify(), "itunes:episode", "7")

    def test_a_legacy_episode_with_a_correct_ordinal_still_passes(self):
        self._write_registries(status="published")
        self.write_feed()
        self.assertTrue(self.verify()["ok"], self.verify()["issues"])

    def test_a_reading_is_scored_against_its_own_number(self):
        """publish_feed.py emits {int(num)}, so reading 501 advertises 501."""
        self.numbers = ["501"]
        self._write_assets()
        self._write_registries()
        self.manifest.write_text(json.dumps({"episodes": {
            "501": {"number": "501", "kind": "read", "title": "R",
                    "description": "D", "read_source": ["RKEY"]}}}))
        self.read_manifest.write_text(json.dumps({"episodes": {
            "501": {"number": "501", "verified": True}}}))
        self.write_feed(episode="1")
        self.assertRefused(self.verify(), "itunes:episode", "1", "501")

    def test_two_items_sharing_an_ordinal_are_refused(self):
        """Caught by the agreement arm, which is why no duplicate arm exists.

        A first draft carried a dedicated duplicate-ordinal arm; the proof
        harness showed it could never fire, because an item advertising
        another episode's ordinal necessarily disagrees with its own GUID.
        The dead arm was removed rather than the claim weakened.
        """
        self.numbers = ["001", "002"]
        self._write_assets()
        self._write_registries()
        self.write_feed(episode="1")
        self.assertRefused(self.verify(), "itunes:episode", "1", "002")

    def test_no_dead_duplicate_ordinal_machinery_survives(self):
        source = (Path(__file__).resolve().parents[1] / "pipeline"
                  / "robust_pipeline.py").read_text()
        self.assertNotIn("advertised_ordinals", source)

    def test_neighbouring_detectors_still_bite(self):
        """The new arm must not shadow the gates around it."""
        self.write_feed()
        text = self.feed.read_text().replace(
            "<description>Desc 001</description>", "<description></description>")
        self.feed.write_text(text)
        self.assertRefused(self.verify(), "empty <description>")


if __name__ == "__main__":
    unittest.main()
