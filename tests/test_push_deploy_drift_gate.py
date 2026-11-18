"""push_to_remote() must assert deployed BYTES, not just existence (run 077).

Every remote probe in verify_feed() is an EXISTENCE probe: show notes, cover
art and the landing page are checked for HTTP 200 plus a few bytes, enclosures
for their Content-Range total only, and the deployed feed by GUID set. So a
deploy whose feed text, notes, cover or landing page was rewritten satisfied it
with an EMPTY issue list -- and that verdict is what push_to_remote()'s wait
loop breaks on to declare a deploy live.

deploy_drift() already detected every one of those classes but was CLI-only, so
the detector existed and the shipping command could not reach it (run 041: wire
a read-only audit into the gate; run 045: ask whether the reader is reachable
from the command the operator runs to SHIP).

deploy_drift() itself must stay a NON-GATE: publish_local() and verify_feed()
still must not call it.
"""
import inspect
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402


class PushAssertsDeployedBytesTests(unittest.TestCase):
    """push_to_remote()'s liveness criterion includes the byte comparator."""

    def test_push_calls_the_drift_comparator(self):
        src = inspect.getsource(rp.push_to_remote)
        self.assertIn("_deploy_drift_verdict", src)

    def test_wait_loop_requires_both_verdicts(self):
        src = inspect.getsource(rp.push_to_remote)
        self.assertRegex(src, r'if\s+v\["ok"\]\s+and\s+d\["ok"\]\s*:')

    def test_final_ok_requires_both_verdicts(self):
        src = inspect.getsource(rp.push_to_remote)
        self.assertIn("live_ok and drift_ok", src)

    def test_drift_reported_under_its_own_key(self):
        """Run 041: a distinct assertion gets a distinct key, never another
        check's dict."""
        src = inspect.getsource(rp.push_to_remote)
        self.assertIn('result["drift"]', src)

    def test_drift_issues_merged_into_the_push_issue_list(self):
        src = inspect.getsource(rp.push_to_remote)
        self.assertIn('drift.get("issues"', src)


class DriftVerdictHelperTests(unittest.TestCase):
    """The helper is fail-open on a fault but never downgrades a refusal."""

    def test_fault_fails_open(self):
        with mock.patch.object(rp, "deploy_drift",
                               side_effect=RuntimeError("boom")):
            verdict = rp._deploy_drift_verdict()
        self.assertTrue(verdict["ok"])
        self.assertIn("unavailable", verdict)

    def test_fault_records_the_reason(self):
        with mock.patch.object(rp, "deploy_drift",
                               side_effect=ValueError("nope")):
            verdict = rp._deploy_drift_verdict()
        self.assertIn("ValueError", verdict["unavailable"])

    def test_a_definite_refusal_is_passed_through(self):
        with mock.patch.object(rp, "deploy_drift",
                               return_value={"ok": False,
                                            "issues": ["feed.xml drifted"]}):
            verdict = rp._deploy_drift_verdict()
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["issues"], ["feed.xml drifted"])

    def test_a_clean_verdict_is_passed_through(self):
        with mock.patch.object(rp, "deploy_drift",
                               return_value={"ok": True, "issues": []}):
            self.assertTrue(rp._deploy_drift_verdict()["ok"])


class DriftStaysANonGateTests(unittest.TestCase):
    """Nothing granted: the comparator must not become an episode gate."""

    def test_publish_local_does_not_call_the_comparator(self):
        src = inspect.getsource(rp.publish_local)
        self.assertNotIn("deploy_drift", src)

    def test_verify_feed_does_not_call_the_comparator(self):
        src = inspect.getsource(rp.verify_feed)
        self.assertNotIn("deploy_drift", src)

    def test_comparator_remains_read_only(self):
        src = inspect.getsource(rp.deploy_drift)
        self.assertNotRegex(src, r"write_text|write_bytes|os\.replace")

    def test_helper_defined_once(self):
        source = inspect.getsource(rp)
        self.assertEqual(source.count("def _deploy_drift_verdict"), 1)


if __name__ == "__main__":
    unittest.main()
