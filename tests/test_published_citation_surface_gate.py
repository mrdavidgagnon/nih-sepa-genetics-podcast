"""Run 095: the read lane's PUBLISHED citation must be the citation the gate scored.

`preflight()` scored episode-notes.md. For an interview that IS the published
surface (notes_html builds <content:encoded> from the numbered lines of that
file). For a reading it is not: publish_feed.read_notes_html() prints
read-episodes.json's `citation` verbatim into <content:encoded> and the item
<description> is synthesized from the same field. `citation` had one reader in
the pipeline -- the publisher -- and no gate.

These tests run preflight with no audio and no review enforcement, so they score
the citation apparatus alone.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

NUM = "990"
KEY = "SCRATCH7"
GOOD = ("Scratch, R. (2026). Run-095 fixture paper. Journal of Harness Studies, "
        "vol. 4, pp. 1-9.")
OTHER = ("Other, A. (2019). A completely different paper. Other Venue. "
         "https://www.zotero.org/groups/2412036/items/WRONGKEY")
ZLINK = f"https://www.zotero.org/groups/2412036/items/{KEY}"


class PublishedCitationSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pipeline = self.root / "pipeline"
        self.pipeline.mkdir()
        self.ep = self.root / "episodes" / NUM
        self.ep.mkdir(parents=True)
        self._saved = {k: getattr(rp, k) for k in
                       ("ROOT", "PIPELINE", "MANIFEST_PATH", "LEDGER_PATH",
                        "READ_MANIFEST_PATH")}
        rp.ROOT = self.root
        rp.PIPELINE = self.pipeline
        rp.MANIFEST_PATH = self.pipeline / "manifest.json"
        rp.LEDGER_PATH = self.pipeline / "state.json"
        rp.READ_MANIFEST_PATH = self.pipeline / "read-episodes.json"
        for name in ("manifest.json", "state.json", "read-episodes.json"):
            (self.pipeline / name).write_text(json.dumps(
                {"schema_version": 1, "updated_at": "", "episodes": {}}))
        body = ("The crowd's answer varies by culture. Averaging preferences provably "
                "erases minorities. A preference distribution is not a decision procedure.")
        (self.ep / "source.txt").write_text(body)
        (self.ep / "script.md").write_text(
            "**Reader:** This is Moral Machines, reading number 990. It is a verbatim "
            "reading of the body text, produced by an automated text-to-speech voice.\n\n"
            "**Reader:** " + body + "\n\n**Reader:** " + rp.REQUIRED_DISCLOSURE + "\n")
        self.notes = (f"## Source\n\n1. {GOOD} Zotero item: {ZLINK}\n\n"
                      + rp.REQUIRED_DISCLOSURE + "\n")
        (self.ep / "episode-notes.md").write_text(self.notes)

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(rp, k, v)
        self.tmp.cleanup()

    def _registry(self, citation, kind="read"):
        reg = json.loads(rp.READ_MANIFEST_PATH.read_text())
        reg["episodes"][NUM] = {"number": NUM, "kind": "read", "title": "fixture",
                                "item_key": KEY, "citation": citation,
                                "coverage": 1.0, "source_words": 22}
        rp.READ_MANIFEST_PATH.write_text(json.dumps(reg))
        mf = json.loads(rp.MANIFEST_PATH.read_text())
        entry = {"number": NUM, "title": "fixture", "description": "fixture",
                 "status": "published_and_moved",
                 "guid": f"moral-machines-episode-{NUM}-reading-{KEY}"}
        if kind == "read":
            entry["kind"] = "read"
            entry["read_source"] = [KEY]
        else:
            entry["sources"] = [KEY]
        mf["episodes"][NUM] = entry
        rp.MANIFEST_PATH.write_text(json.dumps(mf))
        st = json.loads(rp.LEDGER_PATH.read_text())
        st["episodes"][NUM] = {"status": "published_and_moved", "transitions": [],
                               "artifacts": {}}
        rp.LEDGER_PATH.write_text(json.dumps(st))

    def run_gate(self):
        return rp.preflight(NUM, require_audio=False, enforce_review=False)

    def test_canonical_reading_passes_with_no_issue(self):
        self._registry(GOOD)
        result = self.run_gate()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["checks"].get("published_citation"), GOOD)

    def test_empty_published_citation_is_refused(self):
        self._registry("")
        result = self.run_gate()
        self.assertFalse(result["ok"])
        self.assertTrue(any("publishes an empty citation" in i for i in result["issues"]))

    def test_missing_citation_field_is_refused(self):
        self._registry(GOOD)
        reg = json.loads(rp.READ_MANIFEST_PATH.read_text())
        reg["episodes"][NUM].pop("citation")
        rp.READ_MANIFEST_PATH.write_text(json.dumps(reg))
        result = self.run_gate()
        self.assertFalse(result["ok"])
        self.assertTrue(any("publishes an empty citation" in i for i in result["issues"]))

    def test_citation_naming_a_different_paper_is_refused(self):
        self._registry(OTHER)
        result = self.run_gate()
        self.assertFalse(result["ok"])
        self.assertTrue(any("did not score" in i for i in result["issues"]))

    def test_interview_lane_is_not_scored_by_the_read_reader(self):
        self._registry(OTHER, kind="interview")
        result = self.run_gate()
        # The interview path is byte-identical: it scores the notes file, which is
        # what publish_feed publishes for an interview, and never consults the read
        # registry. Its own failures are interview rules, not citation-surface ones.
        self.assertIsNone(result["checks"].get("published_citation"))
        self.assertFalse(any("citation this gate did not score" in i or
                             "publishes an empty citation" in i for i in result["issues"]),
                         result["issues"])

    def test_existing_citation_checks_still_bite(self):
        cases = {
            "no publication year": ("Scratch, R. Run-095 fixture paper SCRATCH7. Journal of Harness Studies.",
                                    "has no publication year"),
            "too short for metadata": ("Scratch, R. (2026) SCRATCH7 Short. [link](https://www.zotero.org/groups/2412036/items/SCRATCH7)",
                                       "too short for author/title/venue metadata"),
            "no direct Zotero link": ("Scratch, R. (2026). Run-095 fixture paper. Journal of Harness Studies, vol. 4. record SCRATCH7",
                                      "has no direct Zotero link"),
        }
        for label, (portion, expected) in cases.items():
            self._registry(portion)
            (self.ep / "episode-notes.md").write_text(
                f"## Source\n\n1. {portion}\n\n" + rp.REQUIRED_DISCLOSURE + "\n")
            result = self.run_gate()
            self.assertFalse(result["ok"], f"{portion} -> {result['issues']}")
            self.assertTrue(any(expected in i for i in result["issues"]),
                            f"{portion} -> {result['issues']}")
            # the new reader AGREED with the notes line, so the refusal came from
            # the pre-existing check alone, not from the new one.
            self.assertEqual(result["checks"].get("published_citation"), portion,
                             f"{portion} -> new reader disagreed")

    def test_no_numbered_entry_is_still_refused(self):
        self._registry(GOOD)
        (self.ep / "episode-notes.md").write_text(
            "## Source\n\nSource: " + GOOD + "\n\n" + rp.REQUIRED_DISCLOSURE + "\n")
        result = self.run_gate()
        self.assertFalse(result["ok"])
        self.assertTrue(any("no numbered citation entry" in i for i in result["issues"]))


if __name__ == "__main__":
    unittest.main()
