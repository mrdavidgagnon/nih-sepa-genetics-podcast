"""Run 090: the interview gate must bind the audio to the script it was rendered from.

preflight() compares the mp3 against the digest recorded at render time (run 045),
which proves the bytes on disk ARE the rendered bytes -- not that they were rendered
from the script.md being published. render_episode() writes that provenance to
parts-robust/render-plan.json, whose script_sha256 had exactly one reader: the
run-032 render-cache guard, never the publication path. Episode 001 is the live
instance -- run 047 corrected a quotation in script.md without re-rendering, so the
shipped audio speaks the pre-correction text while script.md and the passed panel
hold the corrected text, and preflight passed with an empty issue list.
"""
import json, shutil, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import robust_pipeline

KEY = "SCRATCH9"

class RenderPlanProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(robust_pipeline, k) for k in
                      ("ROOT", "PIPELINE", "LEDGER_PATH", "MANIFEST_PATH", "READ_MANIFEST_PATH")}
        self.tmp = Path(tempfile.mkdtemp(prefix="mm_plan_"))
        self.pipeline = self.tmp / "pipeline"; self.pipeline.mkdir()
        self.ep = self.tmp / "episodes" / "907"; self.ep.mkdir(parents=True)
        robust_pipeline.ROOT = self.tmp
        robust_pipeline.PIPELINE = self.pipeline
        robust_pipeline.LEDGER_PATH = self.pipeline / "state.json"
        robust_pipeline.MANIFEST_PATH = self.pipeline / "manifest.json"
        robust_pipeline.READ_MANIFEST_PATH = self.pipeline / "read-episodes.json"
        (self.ep / "script.md").write_text(
            "**Host:** Opening. Dr. Rowan Field is a fictional correspondent and this "
            "episode is AI-generated.\n\n**Rowan:** The crowd chose the outcome and the "
            "aggregate erased the minority. The paper reports a median of fifty.\n")
        (self.ep / "episode-notes.md").write_text(
            "# Episode 907\n\n1. Awad et al. Moral Machine experiment. Nature, 2018, "
            f"reporting millions of decisions. [Open in David Gagnon's Zotero library]"
            f"(https://www.zotero.org/groups/2412036/items/{KEY})\n\n"
            f"{robust_pipeline.REQUIRED_DISCLOSURE}\n")
        (self.pipeline / "manifest.json").write_text(json.dumps(
            {"schema_version": 1, "episodes": {"907": {"number": "907",
             "title": "T", "description": "D", "sources": [KEY], "status": "rendered"}}}))
        (self.pipeline / "state.json").write_text(json.dumps(
            {"schema_version": 1, "episodes": {"907": {"status": "rendered",
             "transitions": [], "artifacts": {}}}}))
        parts = self.ep / "parts-robust"; parts.mkdir()
        (self.ep / "episode-907.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 4096)
        (self.ep / "source-SCRATCH9.txt").write_text(
            "The crowd chose the outcome and the aggregate erased the minority. "
            "The paper reports a median of fifty.\n")
        self.parts = parts

    def _plan(self, sha):
        (self.parts / "render-plan.json").write_text(json.dumps(
            {"schema_version": 1, "script_sha256": sha, "turns": 2}))

    def _gate(self):
        return robust_pipeline.preflight("907", require_audio=True, enforce_review=False)

    def test_plan_written_from_a_different_script_is_refused(self):
        self._plan("a" * 64)
        r = self._gate()
        self.assertFalse(r["ok"])
        self.assertTrue(any("rendered from a different script.md" in i for i in r["issues"]), r["issues"])

    def test_missing_plan_with_audio_present_is_refused(self):
        r = self._gate()
        self.assertFalse(r["ok"])
        self.assertTrue(any("no readable render plan" in i for i in r["issues"]), r["issues"])

    def test_unreadable_plan_is_refused_not_crashed(self):
        (self.parts / "render-plan.json").write_text("{ not json")
        r = self._gate()
        self.assertFalse(r["ok"])
        self.assertTrue(any("no readable render plan" in i for i in r["issues"]), r["issues"])

    def test_matching_plan_passes(self):
        import hashlib
        self._plan(hashlib.sha256((self.ep / "script.md").read_bytes()).hexdigest())
        r = self._gate()
        self.assertTrue(r["ok"], r["issues"])

    def test_audio_digest_refusal_still_fires_alongside(self):
        # no weakening: run 045's audio-vs-recorded-digest check is untouched.
        import hashlib
        self._plan(hashlib.sha256((self.ep / "script.md").read_bytes()).hexdigest())
        rec = json.loads((self.pipeline / "state.json").read_text())
        rec["episodes"]["907"]["artifacts"] = {"audio_sha256": "b" * 64}
        (self.pipeline / "state.json").write_text(json.dumps(rec))
        r = self._gate()
        self.assertFalse(r["ok"])
        self.assertTrue(any("does not match the digest recorded at render time" in i for i in r["issues"]), r["issues"])

    def test_require_audio_false_is_unaffected(self):
        r = robust_pipeline.preflight("907", require_audio=False, enforce_review=False)
        self.assertTrue(r["ok"], r["issues"])

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(robust_pipeline, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
