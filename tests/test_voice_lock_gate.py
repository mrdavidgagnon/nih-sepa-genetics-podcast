"""Run 098 - the LOCKED voice configuration had no reader.

Three hand-kept copies (read_lane.py, render_from_script.py, and
robust_pipeline.py's own render path) declared the show's voices, and
every existing comparison derived BOTH sides from the same copy: the
run-032 cache guard compares the plan against the dict that generates
the plan; run 093 compares the notes' claimed voice against the plan
that same dict wrote. A partial edit - the documented failure mode -
produced a plan recording the drifted voice, notes claiming the drifted
voice, and a gate agreeing with itself while episodes shipped in a
voice contradicting the documented lock.

Proven load-bearing: every refusal below fails against
pipeline/robust_pipeline.py.bak-run098 (the pre-fix module has neither
the constants nor the checks).
"""
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import robust_pipeline as rp

KEY = "SCRATCHV"
REAL_PIPELINE = rp.PIPELINE
AVA, ANDREW = rp.LOCKED_VOICES["host"], rp.LOCKED_VOICES["rowan"]


def decl_files(voice_read=None, rate_read=None, vrs=None, rrs=None, vrp=None, rrp=None):
    """Minimal declaration stubs for the three hand-kept files."""
    d = Path(tempfile.mkdtemp(prefix="mm_voice_", dir="/opt/data/tmp"))
    (d / "read_lane.py").write_text(f'VOICE = "{voice_read or AVA}"\nRATE = "{rate_read or rp.LOCKED_RATES["host"]}"\n')
    vrs = vrs or {"host": AVA, "rowan": ANDREW}
    rrs = rrs or {"host": rp.LOCKED_RATES["host"], "rowan": rp.LOCKED_RATES["rowan"]}
    (d / "render_from_script.py").write_text(f'VOICE = {vrs}\nRATE = {rrs}\n')
    vrp = vrp or {"host": AVA, "rowan": ANDREW, "guest": ANDREW}
    rrp = rrp or dict(rp.LOCKED_RATES)
    (d / "robust_pipeline.py").write_text(f'voices = {vrp}\nrates = {rrp}\n')
    return d


class TreeAgreementTests(unittest.TestCase):
    def test_healthy_stubs_agree(self):
        r = rp.voice_config_agreement(decl_files())
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["issues"], [])

    def test_real_tree_files_agree_with_the_lock(self):
        r = rp.voice_config_agreement(REAL_PIPELINE)
        self.assertTrue(r["ok"], r["issues"])

    def test_partial_edit_of_read_lane_is_refused_naming_the_file(self):
        r = rp.voice_config_agreement(decl_files(voice_read=ANDREW, rate_read="+18%"))
        self.assertFalse(r["ok"])
        self.assertTrue(any("read_lane.py" in i for i in r["issues"]), r["issues"])

    def test_partial_edit_of_render_from_script_rate_is_refused(self):
        r = rp.voice_config_agreement(decl_files(rrs={"host": rp.LOCKED_RATES["host"], "rowan": "+20%"}))
        self.assertFalse(r["ok"])
        self.assertTrue(any("render_from_script.py" in i for i in r["issues"]), r["issues"])

    def test_wrong_format_rate_is_refused(self):
        r = rp.voice_config_agreement(decl_files(rate_read="-3"))
        self.assertFalse(r["ok"])

    def test_unknown_role_is_refused(self):
        r = rp.voice_config_agreement(decl_files(vrp={"host": AVA, "rowan": ANDREW, "guest": ANDREW, "extra": AVA},
                                                 rrp=dict(rp.LOCKED_RATES, extra="-3%")))
        self.assertFalse(r["ok"])

    def test_missing_declaration_is_refused_not_crashed(self):
        d = decl_files()
        (d / "read_lane.py").write_text("VOICE = None\n")
        r = rp.voice_config_agreement(d)
        self.assertFalse(r["ok"])

    def test_role_dict_missing_rowan_is_refused(self):
        r = rp.voice_config_agreement(decl_files(vrs={"host": AVA}))
        self.assertFalse(r["ok"])


class PlanVoiceTests(unittest.TestCase):
    def lock(self):
        return {r: f"{rp.LOCKED_VOICES[r]}@{rp.LOCKED_RATES[r]}" for r in sorted(rp.LOCKED_VOICES)}

    def test_interview_plan_recording_lock_voices_passes(self):
        r = rp.plan_voice_agreement({"voices": self.lock()}, False)
        self.assertTrue(r["ok"], r["issues"])

    def test_interview_plan_with_drifted_voice_is_refused(self):
        drifted = dict(self.lock(), host=f"{ANDREW}@-3%")
        r = rp.plan_voice_agreement({"voices": drifted}, False)
        self.assertFalse(r["ok"])

    def test_historical_absent_interview_plan_is_reported_not_refused(self):
        r = rp.plan_voice_agreement({"script_sha256": "x"}, False)
        self.assertTrue(r["ok"])
        self.assertIn("historical", str(r["recorded"]))

    def test_read_plan_recording_lock_voice_passes(self):
        r = rp.plan_voice_agreement({"voice": AVA, "rate": rp.LOCKED_RATES["host"]}, True)
        self.assertTrue(r["ok"], r["issues"])

    def test_read_plan_with_drifted_voice_is_refused(self):
        r = rp.plan_voice_agreement({"voice": ANDREW, "rate": "+18%"}, True)
        self.assertFalse(r["ok"])

    def test_absent_read_plan_voice_is_reported_not_refused(self):
        r = rp.plan_voice_agreement({"script_sha256": "x"}, True)
        self.assertTrue(r["ok"])
        self.assertIn("unverified", str(r["recorded"]))


class PreflightWiringTests(unittest.TestCase):
    """The refusal must be reachable from the command the operator runs to ship."""

    def setUp(self):
        self.saved = {k: getattr(rp, k) for k in ("ROOT", "PIPELINE", "LEDGER_PATH", "MANIFEST_PATH", "READ_MANIFEST_PATH")}
        self.tmp = Path(tempfile.mkdtemp(prefix="mm_voice_pre_", dir="/opt/data/tmp"))
        self.pipeline = self.tmp / "pipeline"; self.pipeline.mkdir()
        for f in decl_files().iterdir():
            shutil.copy(f, self.pipeline / f.name)
        self.ep = self.tmp / "episodes" / "908"; self.ep.mkdir(parents=True)
        rp.ROOT = self.tmp
        rp.PIPELINE = self.pipeline
        rp.LEDGER_PATH = self.pipeline / "state.json"
        rp.MANIFEST_PATH = self.pipeline / "manifest.json"
        rp.READ_MANIFEST_PATH = self.pipeline / "read-episodes.json"
        (self.ep / "script.md").write_text(
            "**Host:** Opening. Dr. Rowan Field is a fictional correspondent and this "
            "episode is AI-generated.\n\n**Rowan:** The crowd chose the outcome and the "
            "aggregate erased the minority. The paper reports a median of fifty.\n")
        (self.ep / "episode-notes.md").write_text(
            "# Episode 908\n\n1. Awad et al. Moral Machine experiment. Nature, 2018, "
            "reporting millions of decisions. [Open in David Gagnon's Zotero library]"
            f"(https://www.zotero.org/groups/2412036/items/{KEY})\n\n"
            f"{rp.REQUIRED_DISCLOSURE}\n")
        (self.pipeline / "manifest.json").write_text(json.dumps(
            {"schema_version": 1, "episodes": {"908": {"number": "908",
             "title": "T", "description": "D", "sources": [KEY], "status": "rendered"}}}))
        (self.pipeline / "state.json").write_text(json.dumps(
            {"schema_version": 1, "episodes": {"908": {"status": "rendered",
             "transitions": [], "artifacts": {}}}}))
        parts = self.ep / "parts-robust"; parts.mkdir()
        (self.ep / "episode-908.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 4096)
        (self.ep / "source-SCRATCHV.txt").write_text(
            "The crowd chose the outcome and the aggregate erased the minority. "
            "The paper reports a median of fifty.\n")
        self.parts = parts

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(rp, k, v)

    def _gate(self):
        return rp.preflight("908", require_audio=True, enforce_review=False)

    def _plan(self, extra=None):
        plan = {"schema_version": 1,
                "script_sha256": hashlib.sha256((self.ep / "script.md").read_bytes()).hexdigest(),
                "turns": 2}
        plan.update(extra or {})
        (self.parts / "render-plan.json").write_text(json.dumps(plan))

    def test_plan_recording_lock_voices_passes_and_reports_the_agreement(self):
        lock = {r: f"{rp.LOCKED_VOICES[r]}@{rp.LOCKED_RATES[r]}" for r in sorted(rp.LOCKED_VOICES)}
        self._plan({"voices": lock})
        r = self._gate()
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["checks"]["plan_voice"]["recorded"], lock)

    def test_plan_recording_a_drifted_voice_is_refused_at_publish(self):
        lock = {r: f"{rp.LOCKED_VOICES[r]}@{rp.LOCKED_RATES[r]}" for r in sorted(rp.LOCKED_VOICES)}
        self._plan({"voices": dict(lock, host=f"{ANDREW}@-3%")})
        r = self._gate()
        self.assertFalse(r["ok"])
        self.assertTrue(any("lock" in i for i in r["issues"]), r["issues"])

    def test_historical_plan_without_voices_still_passes_and_is_reported(self):
        self._plan()
        r = self._gate()
        self.assertTrue(r["ok"], r["issues"])
        self.assertIn("historical", str(r["checks"]["plan_voice"]["recorded"]))


import json
if __name__ == "__main__":
    unittest.main()
