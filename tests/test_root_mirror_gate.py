"""Tests for the tree-root mirror gate (run 078).

GitHub Pages serves the REPOSITORY ROOT and push_to_remote() copies
feed-site/* into the clone's root, so the root IS the live site. This tree
keeps a second git-tracked copy of every deployed deliverable at its own root,
publish_feed.py has no copy site for it, and before run 078 only cover.png /
cover.svg had a reader (run 057's arm). The other eight copies could drift --
including to the sibling show's name, or to another episode's audio -- while
verify_feed() returned ok: true with an empty issue list, which is the verdict
publish_local() refuses on and push_to_remote()'s wait loop breaks on.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import robust_pipeline as rp  # noqa: E402

TREE = Path(__file__).resolve().parent.parent


class RootMirrorGateTests(unittest.TestCase):
    """Each test builds a scratch tree whose feed-site mirrors the real one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="run078-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "pipeline").mkdir(parents=True)
        for f in ("state.json", "manifest.json", "read-episodes.json"):
            s = TREE / "pipeline" / f
            if s.exists():
                shutil.copy2(s, self.tmp / "pipeline" / f)
        (self.tmp / "feed-site").mkdir()
        # Scratch trees land on another filesystem, so os.link fails with
        # "Invalid cross-device link" -- symlink the binaries (stat() and
        # read() follow, so sizes and digests are the real ones).
        for f in sorted((TREE / "feed-site").iterdir()):
            if not f.is_file():
                continue
            for dest in (self.tmp / "feed-site" / f.name, self.tmp / f.name):
                if f.suffix.lower() in (".xml", ".html", ".md", ".svg"):
                    shutil.copy2(f, dest)
                else:
                    os.symlink(f, dest)
        shutil.copytree(TREE / "episodes", self.tmp / "episodes",
                        symlinks=True)
        self._saved = (rp.ROOT, rp.PIPELINE, rp.LEDGER_PATH, rp.MANIFEST_PATH,
                       rp.READ_MANIFEST_PATH)
        rp.ROOT = self.tmp
        rp.PIPELINE = self.tmp / "pipeline"
        rp.LEDGER_PATH = self.tmp / "pipeline" / "state.json"
        rp.MANIFEST_PATH = self.tmp / "pipeline" / "manifest.json"
        rp.READ_MANIFEST_PATH = self.tmp / "pipeline" / "read-episodes.json"
        self.addCleanup(self._restore)

    def _restore(self):
        (rp.ROOT, rp.PIPELINE, rp.LEDGER_PATH, rp.MANIFEST_PATH,
         rp.READ_MANIFEST_PATH) = self._saved

    def verify(self):
        return rp.verify_feed(str(self.tmp / "feed-site" / "feed.xml"))

    def mirror(self, report):
        return next(c for c in report["checks"]
                    if c.get("name") == "root_mirror")

    def unlink_root(self, name):
        p = self.tmp / name
        if p.is_symlink() or p.exists():
            p.unlink()
        return p

    # ------------------------------------------------------------ healthy
    def test_clean_tree_is_green(self):
        r = self.verify()
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["issues"], [])

    def test_root_mirror_check_is_emitted(self):
        self.assertIn("root_mirror",
                      [c.get("name") for c in self.verify()["checks"]])

    def test_every_deliverable_is_mirrored(self):
        m = self.mirror(self.verify())
        self.assertEqual(len(m["mirrored"]), 10, m["mirrored"])
        self.assertEqual(m["no_root_copy"], [])

    # ------------------------------------------------- the four proved classes
    def test_root_feed_missing_an_item_is_refused(self):
        p = self.unlink_root("feed.xml")
        t = (TREE / "feed-site" / "feed.xml").read_text()
        a = t.index("      <item>")
        b = t.index("</item>", a) + len("</item>")
        p.write_text(t[:a] + t[b:])
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("feed.xml" in s and "tree root" in s
                            for s in r["issues"]), r["issues"])

    def test_root_index_naming_the_sibling_show_is_refused(self):
        p = self.unlink_root("index.html")
        p.write_text((TREE / "feed-site" / "index.html").read_text()
                     .replace("Moral Machines", "Human in the Loop"))
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("index.html" in s and "tree root" in s
                            for s in r["issues"]), r["issues"])

    def test_root_notes_drift_is_refused(self):
        p = self.unlink_root("episode-001-notes.md")
        p.write_text("gone\n")
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("episode-001-notes.md" in s and "tree root" in s
                            for s in r["issues"]), r["issues"])

    def test_root_audio_holding_another_episode_is_refused(self):
        """The run-042/045 wrong-paper-audio class, at the root this time."""
        p = self.unlink_root("episode-001.mp3")
        shutil.copy2(TREE / "feed-site" / "episode-002.mp3", p)
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("episode-001.mp3" in s and "tree root" in s
                            for s in r["issues"]), r["issues"])

    def test_issue_names_both_digests_and_both_sizes(self):
        p = self.unlink_root("episode-003-notes.md")
        p.write_text((TREE / "feed-site" / "episode-003-notes.md").read_text()
                     + "\nDRIFT\n")
        issue = next(s for s in self.verify()["issues"]
                     if "episode-003-notes.md" in s)
        site = hashlib.sha256(
            (TREE / "feed-site" / "episode-003-notes.md").read_bytes()
        ).hexdigest()
        self.assertIn(site[:12], issue)
        self.assertIn("bytes", issue)

    # ------------------------------------------------------- nothing granted
    def test_absent_root_copy_waives(self):
        """Run 057's ruling: the feed references feed-site/, and
        publish_feed.py never writes the root, so no mirror is not a defect."""
        for name in ("feed.xml", "index.html", "cover.png", "cover.svg",
                     "episode-001.mp3", "episode-001-notes.md",
                     "episode-002.mp3", "episode-002-notes.md",
                     "episode-003.mp3", "episode-003-notes.md"):
            self.unlink_root(name)
        r = self.verify()
        self.assertTrue(r["ok"], r["issues"])
        m = self.mirror(r)
        self.assertEqual(len(m["no_root_copy"]), 10)
        self.assertEqual(m["mirrored"], [])

    def test_repo_docs_are_exempt_and_not_demanded(self):
        self.assertEqual(set(rp.ROOT_MIRROR_EXEMPT_NAMES),
                         {"README.md", "production-log.md", "style_guide.md"})
        # None of the three exists in this scratch root; still green.
        self.assertTrue(self.verify()["ok"])

    def test_a_stray_root_file_with_no_feed_site_twin_is_ignored(self):
        """The gate iterates feed-site/, so an extra root file is not a
        mirror and must not be demanded or refused."""
        (self.tmp / "scratch-notes.md").write_text("local only\n")
        self.assertTrue(self.verify()["ok"])

    def test_gate_does_not_fire_when_site_dir_is_the_root(self):
        """A tree serving feed.xml from its own root has one copy, not two."""
        flat = self.tmp / "flat"
        flat.mkdir()
        for f in sorted((TREE / "feed-site").iterdir()):
            if f.is_file():
                os.symlink(f, flat / f.name)
        saved = rp.ROOT
        rp.ROOT = flat
        try:
            r = rp.verify_feed(str(flat / "feed.xml"))
            m = self.mirror(r)
            self.assertEqual(m["mirrored"], [])
            self.assertEqual(m["no_root_copy"], [])
        finally:
            rp.ROOT = saved

    # --------------------------------------- these catch a weakened rewrite
    def test_cover_root_arm_from_run_057_still_fires(self):
        p = self.unlink_root("cover.png")
        p.write_text("not the artwork\n")
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("cover" in s.lower() for s in r["issues"]),
                        r["issues"])

    def test_preexisting_empty_description_gate_still_fires(self):
        for name in ("feed.xml",):
            for p in (self.tmp / "feed-site" / name, self.unlink_root(name)):
                t = (TREE / "feed-site" / "feed.xml").read_text()
                a = t.index("<description>", t.index("<item>"))
                b = t.index("</description>", a)
                p.write_text(t[:a] + "<description>" + t[b:])
        r = self.verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("description" in s for s in r["issues"]),
                        r["issues"])

    def test_read_only(self):
        before = {p.name: hashlib.md5(p.read_bytes()).hexdigest()
                  for p in (self.tmp / "feed-site").iterdir() if p.is_file()}
        for _ in range(3):
            self.verify()
        after = {p.name: hashlib.md5(p.read_bytes()).hexdigest()
                 for p in (self.tmp / "feed-site").iterdir() if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
