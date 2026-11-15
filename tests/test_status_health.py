"""Run 059: status()/watchdog() must judge each episode by its OWN rules.

``status.healthy`` was pinned ``False`` by construction. ``status()`` ran a
DELIVERABLES preflight against every ledger record, so a ``planned`` stub was
failed for having no ``script.md`` -- which is what ``planned`` MEANS. Episode
501 had been doing exactly that for 53 attempts and was the sole reason this
tree could never report healthy, making the signal worthless to the scheduler
and to ``watchdog()``, which inherits the verdict.

Unlike the sibling Human in the Loop tree, ``preflight()`` here has been
lane-aware since run 029 (it branches on manifest ``kind``), so a
correctly-registered reading already passed the interview-rule half. What
``status()`` did NOT do was reach the read lane's gate: it calls preflight with
``enforce_review=False``, so a reading recorded as published whose fidelity gate
is not ``verified`` was reported HEALTHY -- the run-422 live-but-unrecorded
class. That is detection this classifier GAINED.

These tests pin both halves: the signal can come back true, and nothing was
granted -- failed/blocked/rendering still pin unhealthy, an interview in a
production state still has to pass preflight, the run-037 three-part legacy
waiver is unchanged, and inapplicable findings are PRESERVED under
``planned_audit_issues`` / ``read_audit_issues`` rather than dropped.
"""
import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402


def _ledger(episodes: dict) -> dict:
    return {"schema_version": 1, "pipeline": "podcast",
            "updated_at": "2026-11-15T00:00:00Z", "episodes": episodes}


def _interview(status: str, **kw) -> dict:
    rec = {"status": status, "sources": ["AAAAAAAA"], "attempts": 0, "checks": {},
           "artifacts": {}, "errors": [],
           "transitions": [{"from": None, "to": status,
                            "at": "2026-11-15T00:00:00Z", "reason": "fixture"}]}
    rec.update(kw)
    return rec


def _reading(status: str, **kw) -> dict:
    rec = {"status": status, "kind": "read", "read_source": ["ZZZZZZZZ"],
           "attempts": 0, "checks": {}, "artifacts": {}, "errors": [],
           "transitions": [{"from": "planned", "to": status,
                            "at": "2026-11-15T00:00:00Z", "reason": "fixture"}]}
    rec.update(kw)
    return rec


class StatusHealthBase(unittest.TestCase):
    """Drives the real status() against a scratch ledger / read registry."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mm_status_health_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.episodes_dir = self.tmp / "episodes"
        self.episodes_dir.mkdir()
        self.ledger_path = self.tmp / "state.json"
        self.read_path = self.tmp / "read-episodes.json"
        self.write_read({})

    # -- fixtures ---------------------------------------------------------
    def write_ledger(self, episodes: dict) -> None:
        self.ledger_path.write_text(json.dumps(_ledger(episodes)))

    def write_read(self, episodes: dict) -> None:
        self.read_path.write_text(json.dumps({"schema_version": 1,
                                              "episodes": episodes}))

    def run_status(self, preflight_result=None):
        """status() with the ledger, read registry and ROOT redirected.

        preflight is stubbed by default so these tests isolate the CLASSIFIER
        rather than re-testing preflight, which is covered elsewhere and is
        asserted byte-identical by this run's proof harness.
        """
        result = preflight_result if preflight_result is not None else {
            "ok": False, "issues": ["missing episode-notes.md"], "checks": {}}

        def fake_preflight(number, require_audio=False, enforce_review=True):
            if callable(result):
                return result(number)
            return dict(result)

        with unittest.mock.patch.object(rp, "LEDGER_PATH", self.ledger_path), \
             unittest.mock.patch.object(rp, "READ_MANIFEST_PATH", self.read_path), \
             unittest.mock.patch.object(rp, "ROOT", self.tmp), \
             unittest.mock.patch.object(rp, "preflight", fake_preflight), \
             unittest.mock.patch.object(rp, "lock_status",
                                        lambda *a, **k: {"present": False, "active": False}):
            return rp.status()


class PlannedStubHealthTests(StatusHealthBase):
    """A planned episode has no deliverables BY DEFINITION."""

    def test_planned_interview_stub_does_not_pin_unhealthy(self):
        self.write_ledger({"017": _interview("planned")})
        report = self.run_status()
        self.assertTrue(report["healthy"])
        self.assertTrue(report["episodes"]["017"]["preflight_ok"])
        self.assertEqual(report["episodes"]["017"]["issues"], [])

    def test_planned_stub_findings_are_preserved_not_dropped(self):
        self.write_ledger({"017": _interview("planned")})
        report = self.run_status()
        self.assertEqual(report["episodes"]["017"]["planned_audit_issues"],
                         ["missing episode-notes.md"])

    def test_planned_stub_is_not_classified_as_a_reading(self):
        self.write_ledger({"017": _interview("planned")})
        self.assertIsNone(self.run_status()["episodes"]["017"].get("kind"))

    def test_planned_stub_waives_nothing_for_another_episode(self):
        self.write_ledger({"017": _interview("planned"),
                           "002": _interview("verified")})
        report = self.run_status()
        self.assertFalse(report["healthy"])
        self.assertTrue(report["episodes"]["017"]["preflight_ok"])
        self.assertFalse(report["episodes"]["002"]["preflight_ok"])
        self.assertEqual(report["episodes"]["002"]["issues"],
                         ["missing episode-notes.md"])


class ProductionStateHealthTests(StatusHealthBase):
    """Nothing granted: a real defect still pins unhealthy."""

    def test_production_states_still_require_preflight(self):
        for state in ("rendered", "verified", "reviewed", "review_pending"):
            with self.subTest(state=state):
                self.write_ledger({"002": _interview(state)})
                report = self.run_status()
                self.assertFalse(report["healthy"])
                self.assertFalse(report["episodes"]["002"]["preflight_ok"])

    def test_failed_blocked_rendering_pin_unhealthy_even_when_preflight_passes(self):
        for state in ("failed", "blocked", "rendering"):
            with self.subTest(state=state):
                self.write_ledger({"002": _interview(state)})
                report = self.run_status(
                    preflight_result={"ok": True, "issues": [], "checks": {}})
                self.assertFalse(report["healthy"])

    def test_published_interview_still_requires_preflight(self):
        self.write_ledger({"002": _interview("published_and_moved")})
        report = self.run_status()
        self.assertFalse(report["healthy"])
        self.assertFalse(report["episodes"]["002"]["preflight_ok"])

    def test_active_lock_pins_unhealthy(self):
        self.write_ledger({"002": _interview("published_and_moved")})
        with unittest.mock.patch.object(rp, "LEDGER_PATH", self.ledger_path), \
             unittest.mock.patch.object(rp, "READ_MANIFEST_PATH", self.read_path), \
             unittest.mock.patch.object(rp, "ROOT", self.tmp), \
             unittest.mock.patch.object(
                 rp, "preflight",
                 lambda *a, **k: {"ok": True, "issues": [], "checks": {}}), \
             unittest.mock.patch.object(
                 rp, "lock_status",
                 lambda *a, **k: {"present": True, "active": True}):
            self.assertFalse(rp.status()["healthy"])


class LegacyWaiverUnchangedTests(StatusHealthBase):
    """The run-037 three-part legacy test still governs the waiver."""

    def test_legacy_import_is_exempt_and_its_findings_preserved(self):
        self.write_ledger({"004": _interview("published")})
        with unittest.mock.patch.object(rp, "_legacy_episode_numbers",
                                        lambda: {"004"}):
            report = self.run_status()
        self.assertTrue(report["healthy"])
        self.assertTrue(report["episodes"]["004"]["preflight_ok"])
        self.assertEqual(report["episodes"]["004"]["legacy_audit_issues"],
                         ["missing episode-notes.md"])

    def test_published_status_alone_does_not_confer_the_waiver(self):
        self.write_ledger({"004": _interview("published")})
        with unittest.mock.patch.object(rp, "_legacy_episode_numbers",
                                        lambda: set()):
            report = self.run_status()
        self.assertFalse(report["healthy"])
        self.assertFalse(report["episodes"]["004"]["preflight_ok"])


class ReadingClassificationTests(StatusHealthBase):
    def test_is_reading_by_number_range(self):
        self.assertTrue(rp.is_reading("501", {}))
        self.assertTrue(rp.is_reading("990", {}))
        self.assertFalse(rp.is_reading("001", {}))
        self.assertFalse(rp.is_reading("003", {}))

    def test_is_reading_by_registry_outside_the_range(self):
        self.assertTrue(rp.is_reading("007", {"007": {"kind": "read"}}))

    def test_is_reading_tolerates_a_non_numeric_number(self):
        self.assertFalse(rp.is_reading("draft", {}))

    def test_load_read_manifest_returns_empty_on_corrupt_registry(self):
        self.read_path.write_text("{not json")
        with unittest.mock.patch.object(rp, "READ_MANIFEST_PATH", self.read_path):
            self.assertEqual(rp.load_read_manifest(), {})

    def test_load_read_manifest_returns_empty_when_absent(self):
        with unittest.mock.patch.object(rp, "READ_MANIFEST_PATH",
                                        self.tmp / "nope.json"):
            self.assertEqual(rp.load_read_manifest(), {})


class ReadingGateHealthTests(StatusHealthBase):
    """Detection GAINED: a published reading owes a verified fidelity gate."""

    def test_published_reading_with_refused_gate_is_unhealthy(self):
        for state in ("published", "published_and_moved",
                      "published_pending_zotero_move"):
            with self.subTest(state=state):
                self.write_ledger({"991": _reading(state)})
                self.write_read({"991": {"verified": False, "coverage": 0.41}})
                report = self.run_status(
                    preflight_result={"ok": True, "issues": [], "checks": {}})
                entry = report["episodes"]["991"]
                self.assertFalse(report["healthy"])
                self.assertFalse(entry["preflight_ok"])
                self.assertEqual(entry["kind"], "read")
                self.assertFalse(entry["read_gate_verified"])
                self.assertTrue(any("read-episodes.json" in i for i in entry["issues"]))

    def test_published_reading_with_passed_gate_is_healthy(self):
        self.write_ledger({"991": _reading("published_and_moved")})
        self.write_read({"991": {"verified": True, "coverage": 1.0}})
        report = self.run_status(
            preflight_result={"ok": True, "issues": [], "checks": {}})
        self.assertTrue(report["healthy"])
        self.assertTrue(report["episodes"]["991"]["read_gate_verified"])
        self.assertEqual(report["episodes"]["991"]["issues"], [])

    def test_published_reading_with_no_registry_entry_is_refused_not_waived(self):
        self.write_ledger({"991": _reading("published_and_moved")})
        self.write_read({})
        report = self.run_status(
            preflight_result={"ok": True, "issues": [], "checks": {}})
        self.assertFalse(report["healthy"])
        self.assertFalse(report["episodes"]["991"]["preflight_ok"])

    def test_corrupt_read_registry_refuses_rather_than_raising(self):
        self.write_ledger({"991": _reading("published_and_moved")})
        self.read_path.write_text("{not json")
        report = self.run_status(
            preflight_result={"ok": True, "issues": [], "checks": {}})
        self.assertFalse(report["episodes"]["991"]["preflight_ok"])

    def test_wrong_case_status_does_not_unlock_the_published_arm(self):
        self.write_ledger({"991": _reading("PUBLISHED_AND_MOVED")})
        self.write_read({"991": {"verified": False, "coverage": 0.41}})
        report = self.run_status(
            preflight_result={"ok": True, "issues": [], "checks": {}})
        entry = report["episodes"]["991"]
        self.assertIn("read_gate_verified", entry)
        self.assertTrue(entry["preflight_ok"])

    def test_planned_reading_is_not_yet_owed_a_passed_gate(self):
        self.write_ledger({"501": _reading("planned")})
        self.write_read({})
        report = self.run_status()
        entry = report["episodes"]["501"]
        self.assertTrue(report["healthy"])
        self.assertTrue(entry["preflight_ok"])
        self.assertEqual(entry["read_audit_issues"], ["missing episode-notes.md"])

    def test_rendered_reading_is_governed_by_preflight_not_the_gate(self):
        self.write_ledger({"991": _reading("rendered")})
        self.write_read({"991": {"verified": False, "coverage": 0.41}})
        report = self.run_status(
            preflight_result={"ok": True, "issues": [], "checks": {}})
        entry = report["episodes"]["991"]
        self.assertTrue(entry["preflight_ok"])
        self.assertFalse(entry["read_gate_verified"])

    def test_a_reading_is_never_classified_as_legacy(self):
        """The legacy arm keys on the literal "published"; the reading test
        must come first or a reading at that status skips its gate."""
        self.write_ledger({"991": _reading("published")})
        self.write_read({"991": {"verified": False, "coverage": 0.41}})
        with unittest.mock.patch.object(rp, "_legacy_episode_numbers",
                                        lambda: {"991"}):
            report = self.run_status(
                preflight_result={"ok": True, "issues": [], "checks": {}})
        entry = report["episodes"]["991"]
        self.assertEqual(entry["kind"], "read")
        self.assertFalse(entry["preflight_ok"])
        self.assertNotIn("legacy_audit_issues", entry)


class WatchdogInheritanceTests(StatusHealthBase):
    def test_watchdog_reports_healthy_on_a_clean_planned_only_tree(self):
        self.write_ledger({"501": _reading("planned")})
        with unittest.mock.patch.object(rp, "LEDGER_PATH", self.ledger_path), \
             unittest.mock.patch.object(rp, "READ_MANIFEST_PATH", self.read_path), \
             unittest.mock.patch.object(rp, "ROOT", self.tmp), \
             unittest.mock.patch.object(
                 rp, "preflight",
                 lambda *a, **k: {"ok": False, "issues": ["no script"], "checks": {}}), \
             unittest.mock.patch.object(
                 rp, "lock_status",
                 lambda *a, **k: {"present": False, "active": False}):
            report = rp.watchdog()
        self.assertTrue(report["healthy"])
        self.assertEqual(report["stale"], [])

    def test_watchdog_still_pins_unhealthy_on_a_real_defect(self):
        self.write_ledger({"002": _interview("verified")})
        with unittest.mock.patch.object(rp, "LEDGER_PATH", self.ledger_path), \
             unittest.mock.patch.object(rp, "READ_MANIFEST_PATH", self.read_path), \
             unittest.mock.patch.object(rp, "ROOT", self.tmp), \
             unittest.mock.patch.object(
                 rp, "preflight",
                 lambda *a, **k: {"ok": False, "issues": ["no notes"], "checks": {}}), \
             unittest.mock.patch.object(
                 rp, "lock_status",
                 lambda *a, **k: {"present": False, "active": False}):
            self.assertFalse(rp.watchdog()["healthy"])


class StatusWritesNothingTests(StatusHealthBase):
    def test_status_is_read_only(self):
        self.write_ledger({"501": _reading("planned")})
        before = (self.ledger_path.read_bytes(), self.read_path.read_bytes())
        self.run_status()
        self.assertEqual(before,
                         (self.ledger_path.read_bytes(), self.read_path.read_bytes()))


if __name__ == "__main__":
    unittest.main()
