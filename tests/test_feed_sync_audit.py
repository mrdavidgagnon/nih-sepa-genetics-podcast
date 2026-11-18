"""Tests for feed_sync(): the committed feed-site bytes vs a fresh regeneration.

Run 076. `coverage` asks whether a published episode reached the committed feed,
`registry` whether the two durable registries agree, `verify` whether the
committed document is internally consistent and fetchable, `drift` whether the
live bytes equal the local bytes. None of them asks whether the committed bytes
still equal what publish_feed.py GENERATES from the current registries, so a
registry edit that is never republished is invisible offline and the next push
deploys it.

These tests drive feed_sync() against synthetic trees with a stub generator, so
they are fast and do not depend on the real episode catalogue.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import robust_pipeline as rp  # noqa: E402


# A minimal stand-in for publish_feed.py: it derives feed.xml, one
# <base>-notes.md per episode and index.html from manifest.json, which is
# exactly the shape feed_sync() audits. Kept as a list of lines so this file
# contains no nested triple-quoted string.
STUB_GENERATOR = "\n".join([
    "import json, shutil",
    "from pathlib import Path",
    "",
    "ROOT = Path(__file__).resolve().parent.parent",
    "SITE = ROOT / 'feed-site'",
    "",
    "",
    "def main():",
    "    man = json.loads((ROOT / 'pipeline' / 'manifest.json').read_text())",
    "    SITE.mkdir(parents=True, exist_ok=True)",
    "    items = []",
    "    entries = []",
    "    for num in sorted(man['episodes']):",
    "        rec = man['episodes'][num]",
    "        items.append(",
    "            '<item><title>%s</title><description>%s</description>'",
    "            '<guid>moral-machines-episode-%s</guid></item>'",
    "            % (rec.get('title', ''), rec.get('description', ''), num))",
    "        entries.append('<li>Episode %s - %s</li>'",
    "                       % (num, rec.get('title', '')))",
    "        notes_src = ROOT / 'episodes' / num / 'episode-notes.md'",
    "        if notes_src.is_file():",
    "            shutil.copyfile(notes_src, SITE / ('episode-%s-notes.md' % num))",
    "    (SITE / 'feed.xml').write_text(",
    "        '<rss version=\"2.0\"><channel><title>Moral Machines</title>'",
    "        + ''.join(items) + '</channel></rss>')",
    "    (SITE / 'index.html').write_text(",
    "        '<html><title>Moral Machines</title><ul>'",
    "        + ''.join(entries) + '</ul></html>')",
    "    print('stub generator wrote %d items' % len(items))",
    "",
    "",
    "if __name__ == '__main__':",
    "    main()",
    "",
])


class FeedSyncAuditTests(unittest.TestCase):
    """feed_sync() detects a committed artifact the generator disagrees with."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="feedsync-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "pipeline").mkdir()
        (self.tmp / "feed-site").mkdir()
        self.manifest = {
            "episodes": {
                "001": {"title": "First", "description": "Desc one",
                        "status": "published_and_moved"},
                "002": {"title": "Second", "description": "Desc two",
                        "status": "published_and_moved"},
            }
        }
        self.write_manifest()
        for num in ("001", "002"):
            d = self.tmp / "episodes" / num
            d.mkdir(parents=True)
            (d / "episode-notes.md").write_text("Notes for " + num + "\n")
        self.generator = self.tmp / "pipeline" / "publish_feed.py"
        self.generator.write_text(STUB_GENERATOR)
        # Point the module's globals at the synthetic tree. Resolved at call
        # time, never as a default argument value (run 501's rule).
        self._patch("ROOT", self.tmp)
        self._patch("PUBLISH_FEED_PATH", self.generator)
        self.publish()

    def _patch(self, name: str, value: object) -> None:
        old = getattr(rp, name)
        setattr(rp, name, value)
        self.addCleanup(setattr, rp, name, old)

    def publish(self) -> None:
        """Run the stub generator for real, writing the committed site."""
        spec = importlib.util.spec_from_file_location("_t_pf", self.generator)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.SITE = self.tmp / "feed-site"
        with contextlib.redirect_stdout(io.StringIO()):
            mod.main()

    def write_manifest(self) -> None:
        (self.tmp / "pipeline" / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2))

    # ------------------------------------------------------------ clean state
    def test_untouched_tree_passes(self) -> None:
        report = rp.feed_sync()
        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["committed_md5"], report["regenerated_md5"])

    def test_reports_what_it_audited(self) -> None:
        report = rp.feed_sync()
        self.assertEqual(report["notes_checked"], 2)
        self.assertEqual(report["site_text_checked"], 1)
        self.assertEqual(report["committed_items"], 2)
        self.assertEqual(report["regenerated_items"], 2)

    # --------------------------------------------------------------- feed.xml
    def test_manifest_title_edit_is_caught(self) -> None:
        self.manifest["episodes"]["002"]["title"] = "Renamed"
        self.write_manifest()
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(any("feed.xml differs" in i for i in report["issues"]),
                        report["issues"])
        self.assertNotEqual(report["committed_md5"], report["regenerated_md5"])

    def test_diff_sample_shows_the_changed_value(self) -> None:
        self.manifest["episodes"]["001"]["title"] = "A Distinctive New Title"
        self.write_manifest()
        report = rp.feed_sync()
        self.assertTrue(report["diff_sample"])
        self.assertTrue(
            any("A Distinctive New Title" in line
                for line in report["diff_sample"]),
            report["diff_sample"])

    def test_manifest_description_edit_is_caught(self) -> None:
        self.manifest["episodes"]["001"]["description"] = "Rewritten description"
        self.write_manifest()
        report = rp.feed_sync()
        self.assertFalse(report["ok"])

    def test_missing_committed_feed_is_reported_not_raised(self) -> None:
        (self.tmp / "feed-site" / "feed.xml").unlink()
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(any("no committed feed" in i for i in report["issues"]))

    # ------------------------------------------------------------------ notes
    def test_stale_committed_notes_is_caught_with_feed_unchanged(self) -> None:
        note = self.tmp / "episodes" / "001" / "episode-notes.md"
        note.write_text(note.read_text() + "an unpublished edit\n")
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        # the feed itself is untouched, so only the notes arm can see this
        self.assertEqual(report["committed_md5"], report["regenerated_md5"])
        self.assertEqual(len(report["notes_stale"]), 1)
        self.assertEqual(report["notes_stale"][0]["file"],
                         "episode-001-notes.md")

    def test_notes_stale_entry_records_both_digests(self) -> None:
        note = self.tmp / "episodes" / "002" / "episode-notes.md"
        note.write_text("totally different\n")
        report = rp.feed_sync()
        entry = report["notes_stale"][0]
        for field in ("committed_md5", "regenerated_md5",
                      "committed_bytes", "regenerated_bytes"):
            self.assertIn(field, entry)
        self.assertNotEqual(entry["committed_md5"], entry["regenerated_md5"])

    def test_missing_committed_notes_is_caught(self) -> None:
        (self.tmp / "feed-site" / "episode-002-notes.md").unlink()
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertEqual(report["notes_missing"], ["episode-002-notes.md"])

    # -------------------------------------------------------------- site text
    def test_stale_index_html_is_caught(self) -> None:
        idx = self.tmp / "feed-site" / "index.html"
        idx.write_text(idx.read_text().replace("Second", "Hand Edited"))
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(any(e["file"] == "index.html"
                            for e in report["site_text_stale"]),
                        report["site_text_stale"])

    def test_missing_index_html_is_caught(self) -> None:
        (self.tmp / "feed-site" / "index.html").unlink()
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertEqual(report["site_text_missing"], ["index.html"])

    def test_mp3_enclosures_are_not_hashed(self) -> None:
        """Audio is excluded by design; coverage audits advertised length."""
        (self.tmp / "feed-site" / "episode-001.mp3").write_bytes(b"not audio")
        report = rp.feed_sync()
        self.assertTrue(report["ok"], report["issues"])
        self.assertNotIn("mp3", json.dumps(report))

    # ---------------------------------------------------------- read-only-ness
    def test_audit_writes_nothing(self) -> None:
        def sig() -> dict:
            return {
                str(p): hashlib.md5(p.read_bytes()).hexdigest()
                for p in sorted(self.tmp.rglob("*"))
                if p.is_file() and "__pycache__" not in str(p)
            }

        before = sig()
        rp.feed_sync()
        rp.feed_sync()
        self.assertEqual(before, sig())

    def test_leaves_no_scratch_directory(self) -> None:
        tmpdir = Path(tempfile.gettempdir())
        before = set(tmpdir.glob("feedsync-*"))
        rp.feed_sync()
        self.assertEqual(set(tmpdir.glob("feedsync-*")) - before, set())

    def test_generator_import_failure_is_reported_not_raised(self) -> None:
        """A generator that explodes at IMPORT time."""
        self.generator.write_text("raise RuntimeError('boom')\n")
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(any("failed to import" in i for i in report["issues"]),
                        report["issues"])

    def test_generator_runtime_failure_is_reported_not_raised(self) -> None:
        """A generator that imports cleanly and then raises inside main().

        This is a DIFFERENT branch from the import failure above: the module
        loads, so the exception surfaces from module.main(). A mutant that
        swallows it survives a suite testing only the import path.
        """
        self.generator.write_text(
            "def main():\n    raise RuntimeError('boom in main')\n")
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(any("raised RuntimeError" in i for i in report["issues"]),
                        report["issues"])

    def test_generator_systemexit_is_reported_not_raised(self) -> None:
        """publish_feed.main() refuses to build via SystemExit."""
        self.generator.write_text(
            "import sys\n\n\ndef main():\n"
            "    raise SystemExit('refusing to build')\n")
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(any("refused to build" in i for i in report["issues"]),
                        report["issues"])

    def test_generator_producing_no_feed_is_reported(self) -> None:
        self.generator.write_text("def main():\n    pass\n")
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(any("produced no feed.xml" in i
                            for i in report["issues"]), report["issues"])

    def test_unloadable_generator_path_is_reported(self) -> None:
        self._patch("PUBLISH_FEED_PATH", self.tmp / "pipeline" / "nope.py")
        report = rp.feed_sync()
        self.assertFalse(report["ok"])
        self.assertTrue(report["issues"])

    def test_is_not_a_publication_gate(self) -> None:
        """publish_local() must not call feed_sync(): it is an audit."""
        import inspect
        self.assertNotIn("feed_sync(", inspect.getsource(rp.publish_local))
        self.assertNotIn("feed_sync(", inspect.getsource(rp.push_to_remote))


class FeedDiffSampleTests(unittest.TestCase):
    """feed.xml puts each <item> on one very long line."""

    def test_window_centres_on_the_first_divergence(self) -> None:
        a = "x" * 400 + "OLDVALUE" + "y" * 400
        b = "x" * 400 + "NEWVALUE" + "y" * 400
        sample = rp._feed_diff_sample(a, b)
        joined = "\n".join(sample)
        self.assertIn("NEWVALUE", joined)
        self.assertIn("OLDVALUE", joined)
        self.assertTrue(any(line.startswith("@@") for line in sample))

    def test_identical_documents_produce_no_sample(self) -> None:
        self.assertEqual(rp._feed_diff_sample("same\n", "same\n"), [])

    def test_sample_is_bounded_by_opcode_count(self) -> None:
        """`limit` bounds differing RUNS, not output lines.

        The counter is tested once per difflib opcode, so one giant replace
        run emits every line of it; the limit bites when the documents
        interleave many separate differing runs, which is the real shape of a
        drifted feed. Asserting a line ceiling against a single-opcode input
        is a test bug, not a code defect.
        """
        a, b = [], []
        for i in range(100):
            a += ["same " + str(i), "old " + str(i)]
            b += ["same " + str(i), "new " + str(i)]
        sample = rp._feed_diff_sample("\n".join(a), "\n".join(b), limit=5)
        self.assertLessEqual(len(sample), 20)
        self.assertIn("... diff truncated ...", sample)

    def test_single_differing_run_is_emitted_in_full(self) -> None:
        a = "\n".join("line " + str(i) for i in range(50))
        b = "\n".join("other " + str(i) for i in range(50))
        sample = rp._feed_diff_sample(a, b, limit=5)
        self.assertEqual(len(sample), 100)
        self.assertNotIn("... diff truncated ...", sample)


class SyncTextSuffixTests(unittest.TestCase):
    def test_audio_is_excluded_and_text_included(self) -> None:
        self.assertNotIn(".mp3", rp.SYNC_TEXT_SUFFIXES)
        for suffix in (".html", ".xml", ".json", ".svg", ".txt"):
            self.assertIn(suffix, rp.SYNC_TEXT_SUFFIXES)


if __name__ == "__main__":
    unittest.main()
