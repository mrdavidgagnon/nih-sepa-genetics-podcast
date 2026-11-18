"""Run 073: verify_feed() must gate the channel's navigation + artwork container.

``publish_feed.py`` emits all four of these unconditionally, from its one
``BASE_URL`` constant::

    <channel><link>{BASE_URL}/</link>
    <channel><image><url>{BASE_URL}/cover.png</url>
                    <title>Moral Machines</title>
                    <link>{BASE_URL}/</link></image>

They are not fields a client renders as prose; they are how a subscriber
LEAVES the feed. ``<channel><link>`` is the show's homepage -- every podcast
client's "visit website" affordance, and the canonical page a directory
submission records. ``<image><url>`` is the RSS 2.0 artwork a non-iTunes
client renders, and ``<image><link>`` is where that artwork clicks through to.

Until run 073 nothing read any of them. Each existing reader reduced them to
something else, or skipped them outright:

* ``cover_art`` (run 057) is a document-wide SET UNION over image references,
  reduced to ``Path(urlparse(h).path).name`` and probed for existence. A
  REMOVED or EMPTIED ``<image><url>`` is repopulated by the surviving per-item
  ``<itunes:image href>``, so the union still reports ``files=['cover.png']``.
* ``show_identity`` (run 066) guards its entire artwork arm behind
  ``if channel_image is not None``, so a wholly ABSENT ``<image>`` block skips
  every artwork check rather than failing one.
* ``advertised_base`` (run 063) collects ``node.text`` for any tag ending in
  "url"/"link" and checks the HOST and DIRECTORY. A ``<link>`` repointed at
  this show's own ``episode-001.mp3`` is under the expected base and passes;
  an ABSENT ``<link>`` advertises nothing and is outside that guard by
  construction.

This is run 072's per-element-vs-aggregate lesson with the granularity
INVERTED. Run 072 found a field gated in aggregate and unread per element;
here the per-element arm EXISTS and is skipped by its own presence guard,
while the aggregate arm is satisfied by a DIFFERENT element's contribution.
A presence guard written to avoid a crash is structurally unable to gate
presence.

Nine mutation classes each shipped ``ok: true`` with an EMPTY issue list and
were indistinguishable from an intact feed -- the verdict ``publish_local()``
refuses on and ``push_to_remote()``'s wait loop breaks on to declare a deploy
live.

SCOPE BY CONTROL: two nearby mutations are ALREADY refused pre-fix, and the
tests below record which guard does it, so this module cannot be read as
claiming more than the fix earns. A wrong-CASE host is caught incidentally by
run 063's base check (it is not under the expected base), and an
``<image><url>`` naming a file that does NOT exist is caught by run 057's
existence probe. So the genuinely unreadable classes are absent / empty /
disagrees-while-naming-a-file-that-EXISTS -- which is why the agreement test
below writes ``other.png`` to disk first.
"""
import json
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


BASE = "https://mrdavidgagnon.github.io/nih-sepa-genetics-podcast"

FIXTURE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Moral Machines</title><language>en-us</language><copyright>© 2026 Field Day Lab, UW–Madison</copyright><itunes:author>Field Day Lab, UW–Madison</itunes:author><itunes:explicit>false</itunes:explicit><itunes:type>episodic</itunes:type><itunes:category text="Education"/>{channel_link}<description>Playful, dramatized interviews synthesizing research on machine ethics.</description><itunes:image href="{channel_cover}"/>{image_block}
{items}
</channel></rss>
"""

ITEM = """      <item><title>Ep {num}</title><description>Desc {num}</description><guid isPermaLink="false">moral-machines-episode-{num}</guid><enclosure url="{base}/episode-{num}.mp3" length="{length}" type="audio/mpeg"/><pubDate>Tue, 03 Nov 2026 23:39:45 +0000</pubDate><itunes:episode>{ordinal}</itunes:episode><itunes:episodeType>full</itunes:episodeType><itunes:duration>00:00:02</itunes:duration><itunes:explicit>false</itunes:explicit><itunes:image href="{base}/{art}"/><content:encoded><![CDATA[<p>This is a synthetic/dramatized interview with fictional research correspondent Dr. Rowan Field.</p><p>This is an AI-generated summary that may contain errors.</p><p><a href="episode-{num}-notes.md">Full source notes, evidence limitations, and direct Zotero links</a></p>]]></content:encoded></item>"""

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


class ChannelNavigationGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="channel_nav_gate_"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.site = self.dir / "feed-site"
        self.site.mkdir()
        cover = _make_fixture_png()
        for name in ("cover.png", "other.png"):
            (self.site / name).write_bytes(cover)
            (self.dir / name).write_bytes(cover)
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

    def write_feed(self, link=None, image=True, image_url="cover.png",
                   image_link=None, channel_cover=None, item_art=None):
        """link/image_url/image_link: a value, or False to omit the element.

        image=False omits the whole <image> container.
        """
        if link is False:
            link_xml = ""
        elif link == "":
            link_xml = "<link></link>"
        else:
            link_xml = f"<link>{link or BASE + '/'}</link>"
        if not image:
            image_xml = ""
        else:
            if image_url is False:
                url_xml = ""
            elif image_url == "":
                url_xml = "<url></url>"
            else:
                url_xml = f"<url>{BASE}/{image_url}</url>"
            if image_link is False:
                ilink_xml = ""
            elif image_link == "":
                ilink_xml = "<link></link>"
            else:
                ilink_xml = f"<link>{image_link or BASE + '/'}</link>"
            image_xml = (f"<image>{url_xml}<title>Moral Machines</title>"
                         f"{ilink_xml}</image>")
        items = "\n".join(
            ITEM.format(num=n, base=BASE, ordinal=int(n),
                        art=item_art or "cover.png",
                        length=(self.site / f"episode-{n}.mp3").stat().st_size)
            for n in self.numbers)
        self.feed.write_text(FIXTURE_FEED.format(
            channel_link=link_xml, image_block=image_xml, items=items,
            channel_cover=channel_cover or f"{BASE}/cover.png"))

    def verify(self):
        return rp.verify_feed(self.feed)

    def _assert_refused(self, phrase):
        result = self.verify()
        self.assertFalse(result["ok"], "expected a refusal")
        self.assertTrue(any(phrase in i for i in result["issues"]),
                        f"{phrase!r} not in {result['issues']}")
        return result

    # --------------------------------------------------------- happy path
    def test_a_correct_channel_passes_and_is_reported(self):
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        checks = [c for c in result["checks"]
                  if c["name"] == "channel_navigation"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["channel_link"], f"{BASE}/")
        self.assertEqual(checks[0]["image_url"], f"{BASE}/cover.png")
        self.assertEqual(checks[0]["image_link"], f"{BASE}/")
        self.assertIs(checks[0]["image_present"], True)

    def test_the_check_runs_once_for_the_channel_not_per_item(self):
        self.numbers = ["001", "002"]
        self._write_assets()
        self._write_registries()
        self.write_feed()
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(
            len([c for c in result["checks"]
                 if c["name"] == "channel_navigation"]), 1)

    # --------------------------------------------------- channel homepage
    def test_a_missing_channel_link_is_refused(self):
        self.write_feed(link=False)
        self._assert_refused("has no <link> element")

    def test_an_empty_channel_link_is_refused(self):
        self.write_feed(link="")
        self._assert_refused("empty channel <link>")

    def test_a_channel_link_repointed_within_this_show_is_refused(self):
        """Under the expected base, so run 063 cannot be what refuses it."""
        self.write_feed(link=f"{BASE}/episode-001.mp3")
        result = self._assert_refused("this show's homepage is")
        self.assertFalse(any("not under this show's base" in i
                             for i in result["issues"]),
                         "run 063's base guard must not be the refusing arm")

    def test_a_channel_link_at_a_sibling_directory_is_refused(self):
        self.write_feed(link="https://mrdavidgagnon.github.io/")
        self._assert_refused("this show's homepage is")

    def test_a_trailing_slash_free_homepage_still_passes(self):
        """No podcast client distinguishes the two forms."""
        self.write_feed(link=BASE)
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])

    # -------------------------------------------- artwork container
    def test_a_wholly_absent_image_block_is_refused(self):
        """show_identity SKIPS its artwork arm here rather than failing it."""
        self.write_feed(image=False)
        self._assert_refused("has no <image> element")

    def test_a_missing_image_url_is_refused(self):
        self.write_feed(image_url=False)
        self._assert_refused("<image> has no <url> element")

    def test_an_empty_image_url_is_refused(self):
        self.write_feed(image_url="")
        self._assert_refused("empty channel <image><url>")

    def test_an_image_url_disagreeing_with_the_itunes_image_is_refused(self):
        """other.png EXISTS, so run 057's probe cannot be what refuses it."""
        self.write_feed(image_url="other.png")
        result = self._assert_refused("disagrees with the channel "
                                      "<itunes:image href>")
        self.assertFalse(any("missing local cover art" in i
                             for i in result["issues"]),
                         "run 057's existence probe must not be the arm")

    def test_a_consistent_artwork_rename_still_passes(self):
        """Nothing granted: agreement is the requirement, not a filename."""
        self.write_feed(image_url="other.png",
                        channel_cover=f"{BASE}/other.png",
                        item_art="other.png")
        result = self.verify()
        self.assertTrue(result["ok"], result["issues"])

    def test_a_missing_image_link_is_refused(self):
        self.write_feed(image_link=False)
        self._assert_refused("<image> has no <link> element")

    def test_an_empty_image_link_is_refused(self):
        self.write_feed(image_link="")
        self._assert_refused("empty channel <image><link>")

    def test_an_image_link_repointed_within_this_show_is_refused(self):
        self.write_feed(image_link=f"{BASE}/feed.xml")
        self._assert_refused("is not this show's homepage")

    # ------------------------------------------------- nothing granted
    def test_no_legacy_waiver_for_a_ledger_published_import(self):
        """A waiver is a gate with the sign flipped (run 036); an envelope-
        level property belongs to the format, not to an episode."""
        self._write_registries(status="published")
        self.write_feed(link=False)
        self._assert_refused("has no <link> element")

    def test_the_check_is_read_only(self):
        before = self.feed.read_bytes()
        for _ in range(3):
            self.verify()
        self.assertEqual(self.feed.read_bytes(), before)

    def test_prior_gates_still_bite(self):
        """Run 066's title guard and run 070's language guard are untouched."""
        self.write_feed()
        text = self.feed.read_text()
        self.feed.write_text(text.replace(
            "<title>Moral Machines</title>",
            "<title>Human in the Loop</title>", 1))
        self._assert_refused("names the sibling show")
