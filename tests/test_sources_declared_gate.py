"""Run 049: an interview episode declaring no manifest sources must be REFUSED.

With `sources: []` no source text is loaded, so preflight()'s quoted-span
intersection stays None and every quoted span is VACUOUSLY verified -- a
deliverable could quote a sentence present in no paper and preflight returned
ok: true with an empty issue list. The same empty list skips the ownership
check, the manifest-key-in-notes check and the numbered citation / year /
Zotero-link loop.

Both directions are load-bearing:
  * a sourceless episode is refused, and the report says the file was unscored
  * a SOURCED episode is still scored, still catches an invented quotation,
    and a clean one still passes (the fix grants nothing and refuses nothing new)
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import robust_pipeline as R


INVENTED = 'the authors wrote "every single participant demanded a kill switch" here'


def _panel():
    out = ["# Review panel\n"]
    for i, name in enumerate(["Ada Vance", "Boris Lang", "Cleo Mar"], 1):
        out.append(
            f"\n## Reviewer {i} \u2014 {name}\n\n**Final verdict: PASS.**\n\n"
            f"Required revisions: none needed; the draft was checked.\n")
    out.append("\n## Revision record\n\nAll findings applied.\n")
    return "".join(out)


class SourcesDeclaredGateTests(unittest.TestCase):
    """preflight() must not treat 'no declared sources' as a clean bill."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = Path(self._tmp.name)
        (self.tree / "pipeline").mkdir()
        (self.tree / "pipeline" / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "episodes": {}}))
        (self.tree / "pipeline" / "state.json").write_text(
            json.dumps({"schema_version": 1, "episodes": {}}))
        self._root, self._pipe = R.ROOT, R.PIPELINE
        self._man, self._ledger = R.MANIFEST_PATH, R.LEDGER_PATH
        R.ROOT = self.tree
        R.PIPELINE = self.tree / "pipeline"
        R.MANIFEST_PATH = self.tree / "pipeline" / "manifest.json"
        R.LEDGER_PATH = self.tree / "pipeline" / "state.json"
        self.addCleanup(self._restore)

    def _restore(self):
        R.ROOT, R.PIPELINE = self._root, self._pipe
        R.MANIFEST_PATH, R.LEDGER_PATH = self._man, self._ledger
        self._tmp.cleanup()

    def _episode(self, num, sources, extra="", key="SRCKEY01", with_source=True):
        d = self.tree / "episodes" / num
        d.mkdir(parents=True, exist_ok=True)
        (d / "script.md").write_text(
            f"**Host:** Welcome. {extra}\n\n**Rowan:** Quick flag: I'm a fictional "
            f"correspondent, and this is an AI-generated summary of the papers, so "
            f"it can be wrong. Read them.\n\n**Host:** Thanks.\n\n**Rowan:** Bye.\n")
        (d / "episode-notes.md").write_text(
            f"# Notes\n\n{R.REQUIRED_DISCLOSURE}\n\n## Sources\n\n"
            f"1. Author, A. (2020). A Real Long Title Of Sufficient Length Here. "
            f"Journal of Things. "
            f"[link](https://www.zotero.org/groups/2412036/items/{key})\n")
        (d / "review-panel.md").write_text(_panel())
        if with_source:
            (d / f"source-{key}.txt").write_text(
                "This paper reports that drivers were rated differently. "
                "Nothing about kill switches appears in this text.\n")
        man = json.loads((self.tree / "pipeline" / "manifest.json").read_text())
        entry = {"number": num, "title": "t", "description": "d", "status": "rendered"}
        if sources is not None:
            entry["sources"] = sources
        man["episodes"][num] = entry
        (self.tree / "pipeline" / "manifest.json").write_text(json.dumps(man))
        return d

    # ------------------------------------------------ the waiver is closed
    def test_empty_sources_list_is_refused(self):
        self._episode("902", [], extra=INVENTED)
        r = R.preflight("902", require_audio=False, enforce_review=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("no Zotero source keys are declared" in i
                            for i in r["issues"]), r["issues"])

    def test_missing_sources_key_is_refused(self):
        self._episode("903", None, extra=INVENTED)
        r = R.preflight("903", require_audio=False, enforce_review=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("no Zotero source keys are declared" in i
                            for i in r["issues"]), r["issues"])

    def test_unscored_file_is_reported_as_unscored(self):
        """`unverified: []` must be distinguishable from 'never compared'."""
        self._episode("902", [], extra=INVENTED)
        r = R.preflight("902", require_audio=False, enforce_review=False)
        spans = r["checks"]["quoted_spans"]["script.md"]
        self.assertEqual(spans["unverified"], [])
        self.assertFalse(spans["checked_against_sources"])

    # ------------------------------------------- nothing granted / nothing new
    def test_sourced_episode_is_marked_scored(self):
        self._episode("900", ["SRCKEY00"], key="SRCKEY00")
        r = R.preflight("900", require_audio=False, enforce_review=False)
        self.assertTrue(r["ok"], r["issues"])
        self.assertTrue(
            r["checks"]["quoted_spans"]["script.md"]["checked_against_sources"])

    def test_sourced_episode_still_catches_invented_quotation(self):
        self._episode("901", ["SRCKEY01"], extra=INVENTED, key="SRCKEY01")
        r = R.preflight("901", require_audio=False, enforce_review=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("quoted-span gate" in i for i in r["issues"]),
                        r["issues"])
        self.assertNotIn("no Zotero source keys are declared", " ".join(r["issues"]))

    def test_declared_but_absent_extract_is_still_refused(self):
        self._episode("905", ["SRCKEY05"], key="SRCKEY05", with_source=False)
        r = R.preflight("905", require_audio=False, enforce_review=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("extracted source text is missing" in i
                            for i in r["issues"]), r["issues"])

    def test_reading_is_unaffected(self):
        """A reading's key lives under read_source; this gate is interview-only."""
        d = self.tree / "episodes" / "990"
        d.mkdir(parents=True, exist_ok=True)
        (d / "script.md").write_text(
            "**Reader:** This is Moral Machines, reading number 990.\n")
        (d / "episode-notes.md").write_text(f"# Notes\n\n{R.REQUIRED_DISCLOSURE}\n")
        man = json.loads((self.tree / "pipeline" / "manifest.json").read_text())
        man["episodes"]["990"] = {"number": "990", "title": "r", "description": "d",
                                  "kind": "read", "read_source": ["RDKEY001"],
                                  "status": "built"}
        (self.tree / "pipeline" / "manifest.json").write_text(json.dumps(man))
        r = R.preflight("990", require_audio=False, enforce_review=False)
        self.assertNotIn("quoted_spans", r["checks"])
        self.assertNotIn("no Zotero source keys are declared", " ".join(r["issues"]))


if __name__ == "__main__":
    unittest.main()
