"""Run 055: publish gates every episode it EMITS, not just the selected one.

publish_local() takes a `selected` set that controls which ledger records
transition. It never bounded the blast radius: publish_feed.main() rebuilds the
whole feed and re-copies every emitted episode's audio and notes into
feed-site/. So `publish --episode 001` used to re-ship every other episode with
no check run against it, in BOTH lanes.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent / "pipeline"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EmittedEpisodeNumbersTests(unittest.TestCase):
    """The helper that defines the gate's scope."""

    def setUp(self):
        self.rp = _load("rp_scope", PIPELINE / "robust_pipeline.py")

    def test_returns_a_set(self):
        self.assertIsInstance(self.rp._emitted_episode_numbers(), set)

    def test_covers_the_published_catalogue(self):
        """Every published episode is emitted, so every one must be gated."""
        emitted = self.rp._emitted_episode_numbers()
        ledger = json.loads((PIPELINE / "state.json").read_text())
        published = {
            number
            for number, rec in (ledger.get("episodes") or {}).items()
            if str(rec.get("status", "")).startswith("published")
        }
        self.assertTrue(published, "fixture has no published episodes")
        self.assertTrue(published <= emitted, f"{published - emitted} not gated")

    def test_is_fail_open_not_fail_closed(self):
        """An unusable derivation must not block publishing outright.

        The helper can only widen the gated set. If it could raise, a broken
        import would make every publish impossible rather than degrading to
        the previous selection-only behaviour.
        """
        broken = Path(tempfile.mkdtemp()) / "pipeline"
        broken.mkdir()
        shutil.copy2(PIPELINE / "robust_pipeline.py", broken / "robust_pipeline.py")
        (broken / "publish_feed.py").write_text("raise RuntimeError('boom')\n")
        saved = sys.path[:]
        sys.modules.pop("publish_feed", None)
        try:
            sys.path.insert(0, str(broken))
            mod = _load("rp_broken", broken / "robust_pipeline.py")
            self.assertEqual(mod._emitted_episode_numbers(), set())
        finally:
            sys.path[:] = saved
            sys.modules.pop("publish_feed", None)

    def test_scope_is_read_from_publish_feed_not_reimplemented(self):
        """The gate must consult the real derivation, or its scope can drift."""
        source = (PIPELINE / "robust_pipeline.py").read_text()
        body = source.split("def _emitted_episode_numbers", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("interview_episodes", body)
        self.assertIn("read_episodes", body)


class PublishScopeTests(unittest.TestCase):
    """publish_local() must preflight the union of selected and emitted."""

    def test_union_of_selected_and_emitted_is_gated(self):
        source = (PIPELINE / "robust_pipeline.py").read_text()
        self.assertIn(
            "for number in sorted(set(selected) | _emitted_episode_numbers()):",
            source,
        )

    def test_selection_only_loop_is_gone(self):
        """The pre-fix loop gated `selected` alone; it must not come back."""
        source = (PIPELINE / "robust_pipeline.py").read_text()
        publish = source.split("def publish_local", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("\n    for number in selected:\n        if number not in legacy_numbers:", publish)

    def test_legacy_exemption_still_applies(self):
        """Imported history stays exempt; this change only adds refusals."""
        source = (PIPELINE / "robust_pipeline.py").read_text()
        publish = source.split("def publish_local", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("if number not in legacy_numbers:", publish)

    def test_coverage_assertion_still_precedes_transitions(self):
        """Run 041's erasure check must still run before any ledger write."""
        publish = (PIPELINE / "robust_pipeline.py").read_text()
        publish = publish.split("def publish_local", 1)[1].split("\ndef ", 1)[0]
        self.assertLess(
            publish.index("coverage = feed_coverage("),
            publish.index('transition(ledger, number, "verified"'),
        )


if __name__ == "__main__":
    unittest.main()
