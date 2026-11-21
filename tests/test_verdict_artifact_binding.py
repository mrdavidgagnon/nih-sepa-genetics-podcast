"""Run 088: the read fidelity verdict must be bound to the artifacts it scored.

Run 040 stored an audio digest beside the verdict and run 042 wired a reader into
fidelity_gate(). The two files the gate actually SCORES -- script.md and source.txt --
were required to exist but never compared, so a post-verdict edit kept `verified: true`
and the published show notes kept asserting a fidelity claim the gate would now fail.
"""
import hashlib, json, re, shutil, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import read_lane, robust_pipeline


class VerdictArtifactBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mm_artifact_"))
        self.pipeline = self.tmp / "pipeline"; self.pipeline.mkdir()
        self.ep = self.tmp / "episodes" / "991"; self.ep.mkdir(parents=True)
        for mod in (read_lane, robust_pipeline):
            mod.ROOT = self.tmp
        read_lane.EPISODES = self.tmp / "episodes"
        read_lane.READ_MANIFEST = self.pipeline / "read-episodes.json"
        read_lane.STATE_PATH = self.pipeline / "state.json"
        read_lane.MANIFEST_PATH = self.pipeline / "manifest.json"
        robust_pipeline.PIPELINE = self.pipeline
        robust_pipeline.LEDGER_PATH = self.pipeline / "state.json"
        robust_pipeline.MANIFEST_PATH = self.pipeline / "manifest.json"
        robust_pipeline.READ_MANIFEST_PATH = self.pipeline / "read-episodes.json"
        body = ("Autonomous vehicles promise large reductions in road fatalities. "
                "Yet self-driving systems face trade-offs that are not merely technical: "
                "they are moral. We replicate the effect across three studies (N = 1,303) "
                "and find the effect size unchanged.")
        self.paras = [body] * 6
        (self.ep / "source.txt").write_text("\n\n".join(self.paras))
        block = "\n".join(f"**Reader:** {p}" for p in self.paras)
        (self.ep / "script.md").write_text(
            "**Reader:** This is Moral Machines, reading number 991. This is a verbatim "
            "reading, produced by an automated text-to-speech voice from the body text of "
            "one paper.\n\n"
            f"<!-- BEGIN READING -->\n{block}\n<!-- END READING -->\n\n"
            "**Reader:** That was the complete body text.\n")
        key = "SCRATCH1"
        self.key = key
        (self.ep / "episode-notes.md").write_text(
            "# Reading 991\n\n1. Jane Q. Researcher. \"Moral trade-offs.\" Journal of "
            f"Machine Ethics 4(2), 2026, pp. 101-139. [Open in David Gagnon's Zotero library]"
            f"(https://www.zotero.org/groups/2412036/items/{key})\n\n{robust_pipeline.REQUIRED_DISCLOSURE}\n")
        self.read_manifest = {"schema_version": 1, "episodes": {"991": {
            "number": "991", "kind": "read", "title": "Moral trade-offs",
            "item_key": key, "citation": "Jane Q. Researcher. 2026.",
            "audio": "episode-991.mp3", "base": "episode-991-reading",
            "guid": f"episode-991-reading-{key}", "source_words": 100, "pages": 6,
            "coverage": None, "verified": False,
            "built_at": "2026-11-16T12:00:00+00:00"}}}
        self._write_read()
        (self.pipeline / "state.json").write_text(json.dumps({"schema_version": 1, "episodes": {"991": {"status": "verified", "kind": "read", "attempt_log": []}}}))
        (self.pipeline / "manifest.json").write_text(json.dumps({"schema_version": 1, "episodes": {"991": {"number": "991", "kind": "read", "title": "Moral trade-offs", "description": "A verbatim reading.", "read_source": [key], "status": "verified"}}}))
        (self.ep / "episode-991.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 4096)
        spoken = " ".join(re.sub(r"^\*\*Reader:\*\*\s+", "", l) for l in (self.ep / "script.md").read_text().splitlines() if l.startswith("**Reader:**"))
        n = len(re.findall(r"[a-z0-9]+", spoken.lower()))
        read_lane.audio_seconds = lambda p: n / read_lane.WORDS_PER_MINUTE * 60
        self._record()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_read(self):
        read_lane.READ_MANIFEST.write_text(json.dumps(self.read_manifest))

    def _record(self):
        result = read_lane.verify("991")
        self.assertTrue(result["ok"], result["issues"])
        read_lane.record_verdict("991", result)
        return result

    def _entry(self):
        return json.loads(read_lane.READ_MANIFEST.read_text())["episodes"]["991"]

    def test_verify_exposes_digests_of_the_artifacts_it_scores(self):
        result = read_lane.verify("991")
        self.assertTrue(result["ok"])
        self.assertIn("artifact_digests", result)
        for field in ("script_sha256", "source_sha256"):
            self.assertEqual(result["artifact_digests"][field], hashlib.sha256((self.ep / {"script_sha256": "script.md", "source_sha256": "source.txt"}[field]).read_bytes()).hexdigest())

    def test_verify_is_still_side_effect_free(self):
        before = hashlib.md5(read_lane.READ_MANIFEST.read_bytes()).hexdigest()
        read_lane.verify("991")
        self.assertEqual(hashlib.md5(read_lane.READ_MANIFEST.read_bytes()).hexdigest(), before)

    def test_record_verdict_persists_the_digests(self):
        entry = self._entry()
        self.assertTrue(entry["verified"])
        self.assertIn("script_sha256", entry); self.assertIn("source_sha256", entry)

    def test_post_verdict_edit_to_script_is_refused(self):
        (self.ep / "script.md").write_text((self.ep / "script.md").read_text().replace("Yet self-driving", "Yet driving", 1))
        self.assertFalse(read_lane.verify("991")["ok"])
        gate = robust_pipeline.fidelity_gate("991")
        self.assertFalse(gate["ok"])
        self.assertTrue(any("script.md does not match the verified script.md" in i for i in gate["issues"]))
        self.assertFalse(robust_pipeline.preflight("991", require_audio=True, enforce_review=True)["ok"])

    def test_post_verdict_re_extraction_of_source_is_refused(self):
        (self.ep / "source.txt").write_text((self.ep / "source.txt").read_text() + "\n\nAn added paragraph.")
        gate = robust_pipeline.fidelity_gate("991")
        self.assertFalse(gate["ok"])
        self.assertTrue(any("source.txt does not match" in i for i in gate["issues"]))

    def test_missing_digest_is_a_refusal_not_a_waiver(self):
        entry = self._entry()
        entry.pop("script_sha256"); entry.pop("source_sha256")
        self.read_manifest["episodes"]["991"] = entry; self._write_read()
        gate = robust_pipeline.fidelity_gate("991")
        self.assertFalse(gate["ok"])
        self.assertTrue(any("registry records no script_sha256" in i for i in gate["issues"]))

    def test_the_refusal_clears_only_by_re_verifying_on_the_actual_bytes(self):
        original = (self.ep / "script.md").read_text()
        (self.ep / "script.md").write_text(original.replace("Yet self-driving", "Yet driving", 1))
        self.assertFalse(robust_pipeline.fidelity_gate("991")["ok"])
        (self.ep / "script.md").write_text(original)
        self._record()
        self.assertTrue(robust_pipeline.fidelity_gate("991")["ok"])

    def test_gate_grants_nothing_it_already_granted(self):
        entry = self._entry(); entry["verified"] = False
        self.read_manifest["episodes"]["991"] = entry; self._write_read()
        self.assertFalse(robust_pipeline.fidelity_gate("991")["ok"])
        entry = self._entry(); entry["verified"] = True; entry["coverage"] = 0.90
        self.read_manifest["episodes"]["991"] = entry; self._write_read()
        self.assertFalse(robust_pipeline.fidelity_gate("991")["ok"])


if __name__ == "__main__":
    unittest.main()
