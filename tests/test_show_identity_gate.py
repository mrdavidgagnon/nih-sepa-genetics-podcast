"""The channel's own identity -- the show name -- must be gated (run 066).

Runs 056-065 gated every advertised per-item field and the channel's assets.
Nothing read the channel's identity TEXT, in any of the four slots
publish_feed.py writes it to: the channel <title>, the channel
<image><title>, index.html's <title> and its <h1>. Those are the exact slots
run 004 found still naming the sibling show after this tree was cloned from
it, and retargeted by hand; nothing has held them since.

Run 063's FORBIDDEN_ADVERTISED_SUBSTRINGS guard is scoped to advertised URLs
and expressed as a slug ("human-in-the-loop"), which cannot match the sibling
show's prose name ("Human in the Loop") even where it is applied.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import robust_pipeline as rp  # noqa: E402

REAL = Path(__file__).resolve().parent.parent
SHOW = "Moral Machines"
SIBLING = "Human in the Loop"


def _scratch_tree(dst: Path) -> Path:
    """A minimal feed-site + episodes tree, enclosures symlinked.

    A scratch tree lands on another filesystem, so os.link fails with
    `Invalid cross-device link`; symlink instead (stat/read follow it).
    """
    (dst / "feed-site").mkdir(parents=True)
    for f in (REAL / "feed-site").glob("*"):
        if f.suffix == ".mp3":
            os.symlink(f, dst / "feed-site" / f.name)
        else:
            shutil.copy2(f, dst / "feed-site" / f.name)
    for name in ("cover.png", "cover.svg"):
        if (REAL / name).exists():
            shutil.copy2(REAL / name, dst / name)
    return dst


class ShowIdentityGateTests(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tree = _scratch_tree(Path(self._td.name) / "t")
        self.feed = self.tree / "feed-site" / "feed.xml"
        self.page = self.tree / "feed-site" / "index.html"
        self._root = rp.ROOT
        rp.ROOT = self.tree

    def tearDown(self):
        rp.ROOT = self._root
        self._td.cleanup()

    def _sub(self, path, old, new):
        text = path.read_text()
        self.assertEqual(text.count(old), 1, f"anchor {old!r}")
        path.write_text(text.replace(old, new))

    def _verify(self):
        return rp.verify_feed(str(self.feed))

    # ---------------------------------------------------------- constants

    def test_show_title_constant_is_this_show(self):
        self.assertEqual(rp.SHOW_TITLE, SHOW)

    def test_forbidden_show_titles_names_the_sibling_in_prose_form(self):
        self.assertIn(SIBLING, rp.FORBIDDEN_SHOW_TITLES)
        # The slug guard cannot match the prose name, which is why a
        # separate constant is needed rather than reusing run 063's.
        self.assertFalse(any(b in SIBLING.lower()
                             for b in rp.FORBIDDEN_ADVERTISED_SUBSTRINGS))

    # ------------------------------------------------------- channel title

    def test_intact_tree_passes_and_reports_the_identity(self):
        res = self._verify()
        self.assertTrue(res["ok"], res["issues"])
        check = [c for c in res["checks"] if c["name"] == "show_identity"][0]
        self.assertEqual(check["channel_title"], SHOW)
        self.assertEqual(check["image_title"], SHOW)
        self.assertEqual(check["expected"], SHOW)

    def test_sibling_show_channel_title_is_refused(self):
        self._sub(self.feed, f"<channel><title>{SHOW}</title>",
                  f"<channel><title>{SIBLING}</title>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("sibling show" in i for i in res["issues"]),
                        res["issues"])

    def test_wrong_show_title_is_refused_even_when_not_the_sibling(self):
        self._sub(self.feed, f"<channel><title>{SHOW}</title>",
                  "<channel><title>Some Other Show</title>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("this show is" in i for i in res["issues"]),
                        res["issues"])

    def test_empty_channel_title_is_refused(self):
        self._sub(self.feed, f"<channel><title>{SHOW}</title>",
                  "<channel><title></title>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("nameless show" in i for i in res["issues"]),
                        res["issues"])

    def test_surrounding_whitespace_is_not_a_defect(self):
        self._sub(self.feed, f"<channel><title>{SHOW}</title>",
                  f"<channel><title>  {SHOW}  </title>")
        self.assertTrue(self._verify()["ok"])

    def test_wrong_case_show_title_is_refused(self):
        self._sub(self.feed, f"<channel><title>{SHOW}</title>",
                  "<channel><title>moral machines</title>")
        self.assertFalse(self._verify()["ok"])

    # ------------------------------------------------------ artwork caption

    def test_drifted_artwork_caption_is_refused(self):
        self._sub(self.feed, f"</url><title>{SHOW}</title>",
                  f"</url><title>{SIBLING}</title>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("disagrees with the channel" in i
                            for i in res["issues"]), res["issues"])

    def test_empty_artwork_caption_is_refused(self):
        self._sub(self.feed, f"</url><title>{SHOW}</title>",
                  "</url><title></title>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("artwork advertises no show name" in i
                            for i in res["issues"]), res["issues"])

    # --------------------------------------------------------- landing page

    def test_index_page_title_naming_the_sibling_is_refused(self):
        self._sub(self.page, f"<title>{SHOW}</title>",
                  f"<title>{SIBLING}</title>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("index.html advertises" in i and SIBLING in i
                            for i in res["issues"]), res["issues"])

    def test_index_page_h1_naming_the_sibling_is_refused(self):
        self._sub(self.page, f"<h1>{SHOW}</h1>", f"<h1>{SIBLING}</h1>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("index.html advertises" in i
                            for i in res["issues"]), res["issues"])

    def test_empty_index_h1_is_refused(self):
        self._sub(self.page, f"<h1>{SHOW}</h1>", "<h1></h1>")
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("advertises no show name" in i
                            for i in res["issues"]), res["issues"])

    def test_index_page_identity_is_reported(self):
        res = self._verify()
        check = [c for c in res["checks"] if c["name"] == "index_page"][0]
        self.assertEqual(check.get("page_title"), SHOW)
        self.assertEqual(check.get("page_h1"), SHOW)

    # ------------------------------------------------------ nothing granted

    def test_identity_gate_is_the_only_added_check(self):
        names = [c["name"] for c in self._verify()["checks"]]
        self.assertIn("show_identity", names)
        for required in ("feed_parse", "cover_art", "advertised_base",
                         "index_page", "guid", "disclosure", "duration",
                         "pubdate"):
            self.assertIn(required, names)

    def test_pre_existing_gates_still_bite(self):
        intact = self.feed.read_text()
        # run 065 GUID
        self.feed.write_text(intact.replace("moral-machines-episode-001",
                                            "human-in-the-loop-episode-001"))
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("cross-show substring" in i for i in res["issues"]))
        # run 057 cover art
        self.feed.write_text(intact)
        (self.tree / "feed-site" / "cover.png").unlink()
        res = self._verify()
        self.assertFalse(res["ok"])
        self.assertTrue(any("cover art" in i for i in res["issues"]))

    def test_no_legacy_waiver_for_the_show_name(self):
        """A waiver is a gate with the sign flipped (run 036)."""
        self._sub(self.feed, f"<channel><title>{SHOW}</title>",
                  f"<channel><title>{SIBLING}</title>")
        res = rp.verify_feed(str(self.feed))
        self.assertFalse(res["ok"])
        # legacy exemptions must not reach a channel-level field
        self.assertEqual(
            [i for i in res["warnings"] if "title" in i.lower()], [])


if __name__ == "__main__":
    unittest.main()
