"""Run 079: the converse sweep over the DEPLOYED file set.

Every other audit in this tree enumerates files that exist LOCALLY and asks
whether the remote has them. Nothing asked what the remote HAS that this tree
no longer produces. push_to_remote() copies feed-site/* into the clone and
stages with `git add -A`, which can never DELETE a retired path -- so anything
ever deployed stays served forever, with every audit green.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402


class RemoteOnlyPathsTests(unittest.TestCase):
    """The predicate itself, retargeted for a repo that serves the whole tree."""

    def setUp(self):
        self.root = Path(rp.ROOT)
        self.site = self.root / "feed-site"

    def test_exact_repo_relative_path_present_locally_is_accounted(self):
        self.assertEqual(
            rp.remote_only_paths(
                ["pipeline/robust_pipeline.py", "README.md"],
                self.root, self.site),
            [])

    def test_flat_feed_site_payload_is_accounted(self):
        # push copies feed-site/* into the clone ROOT, so those arrive flat.
        self.assertEqual(
            rp.remote_only_paths(["feed.xml", "index.html"], self.root, self.site),
            [])

    def test_retired_flat_deliverable_is_an_orphan(self):
        self.assertEqual(
            rp.remote_only_paths(["episode-004.mp3"], self.root, self.site),
            ["episode-004.mp3"])

    def test_retired_nested_path_is_an_orphan(self):
        self.assertEqual(
            rp.remote_only_paths(["episodes/004/script.md"], self.root, self.site),
            ["episodes/004/script.md"])

    def test_basename_does_not_excuse_a_nested_path(self):
        # A stale nested feed.xml must not be waived by the real flat one.
        self.assertEqual(
            rp.remote_only_paths(["stale/feed.xml"], self.root, self.site),
            ["stale/feed.xml"])

    def test_results_are_sorted(self):
        got = rp.remote_only_paths(
            ["zz-orphan.md", "aa-orphan.md"], self.root, self.site)
        self.assertEqual(got, sorted(got))

    def test_allowed_entries_are_exempt_but_the_default_is_empty(self):
        self.assertEqual(rp.DRIFT_ALLOWED_REMOTE_ONLY, ())
        self.assertEqual(
            rp.remote_only_paths(["ghost.md"], self.root, self.site,
                                 allowed=("ghost.md",)),
            [])


class DeployDriftOrphanSweepTests(unittest.TestCase):
    """deploy_drift()'s converse sweep, with the network stubbed out."""

    def setUp(self):
        self.site = Path(rp.ROOT) / "feed-site"
        # Make every byte comparison trivially pass so the assertions below
        # isolate the orphan sweep.
        def fake_fetch(url, timeout=15.0, headers=None):
            name = url.rsplit("/", 1)[-1]
            local = self.site / name
            if not local.is_file():
                return 404, b"", {}
            data = local.read_bytes()
            if headers and "Range" in headers:
                return 206, data[:1], {
                    "Content-Range": f"bytes 0-0/{len(data)}"}
            return 200, data, {"Content-Length": str(len(data))}
        self.fetch = mock.patch.object(rp, "fetch_bytes", side_effect=fake_fetch)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)
        local_names = sorted(p.name for p in self.site.iterdir() if p.is_file())
        self.deployed = [n for n in local_names if not n.endswith((".bak-run004",))]

    def _drift(self, remote_paths, **kw):
        with mock.patch.object(rp, "list_remote_tree", return_value=remote_paths):
            return rp.deploy_drift(remote=rp.FEED_BASE, site=self.site,
                                   orphans=True, **kw)

    def test_clean_deploy_passes_and_reports_the_sweep_completed(self):
        report = self._drift(self.deployed)
        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["remote_only"], [])
        self.assertEqual(report["orphan_audit"], "completed")
        self.assertEqual(report["remote_blobs"], len(self.deployed))

    def test_an_orphan_is_refused_and_named(self):
        report = self._drift(self.deployed + ["episode-004.mp3"])
        self.assertFalse(report["ok"])
        self.assertEqual(report["remote_only"], ["episode-004.mp3"])
        self.assertTrue(any("episode-004.mp3" in i for i in report["issues"]),
                        report["issues"])

    def test_every_orphan_gets_its_own_issue(self):
        extras = ["episode-004.mp3", "feed-old.xml", "episodes/004/script.md"]
        report = self._drift(self.deployed + extras)
        self.assertFalse(report["ok"])
        self.assertEqual(sorted(report["remote_only"]), sorted(extras))
        self.assertEqual(len(report["issues"]), len(extras))

    def test_enumeration_failure_is_an_issue_never_a_pass(self):
        with mock.patch.object(rp, "list_remote_tree",
                               side_effect=RuntimeError("truncated")):
            report = rp.deploy_drift(remote=rp.FEED_BASE, site=self.site,
                                     orphans=True)
        self.assertFalse(report["ok"])
        self.assertTrue(report["orphan_audit"].startswith("failed:"))
        self.assertTrue(any("could not be enumerated" in i
                            for i in report["issues"]), report["issues"])

    def test_sweep_not_attempted_for_a_non_deploy_remote(self):
        with mock.patch.object(rp, "list_remote_tree",
                               side_effect=AssertionError("must not be called")):
            report = rp.deploy_drift(remote="https://example.invalid/site",
                                     site=self.site)
        self.assertIn("not attempted", report["orphan_audit"])

    def test_sweep_is_attempted_by_DEFAULT_for_the_deploy_site(self):
        """M5: the auto-detect branch is the one `push` actually uses.

        Every other test here passes orphans=True explicitly, so a mutant that
        hardcoded `attempt = False` left the sweep dead on the shipping path
        while the suite stayed green.
        """
        with mock.patch.object(rp, "list_remote_tree",
                               return_value=self.deployed + ["episode-004.mp3"]):
            report = rp.deploy_drift(remote=rp.FEED_BASE, site=self.site)
        self.assertEqual(report["orphan_audit"], "completed")
        self.assertEqual(report["remote_only"], ["episode-004.mp3"])
        self.assertFalse(report["ok"])

    def test_default_sweep_runs_when_remote_is_omitted_entirely(self):
        with mock.patch.object(rp, "list_remote_tree",
                               return_value=self.deployed):
            report = rp.deploy_drift(site=self.site)
        self.assertEqual(report["orphan_audit"], "completed")
        self.assertTrue(report["ok"], report["issues"])

    def test_orphans_false_disables_the_sweep(self):
        with mock.patch.object(rp, "list_remote_tree",
                               side_effect=AssertionError("must not be called")):
            report = rp.deploy_drift(remote=rp.FEED_BASE, site=self.site,
                                     orphans=False)
        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["orphan_audit"], "not attempted")

    def test_byte_comparison_still_bites_with_the_sweep_clean(self):
        """Nothing granted: a rewritten deployed file is still refused."""
        def tampered(url, timeout=15.0, headers=None):
            name = url.rsplit("/", 1)[-1]
            local = self.site / name
            if not local.is_file():
                return 404, b"", {}
            data = local.read_bytes()
            if name == "feed.xml":
                data = data + b"<!-- rewritten in place -->"
            if headers and "Range" in headers:
                return 206, data[:1], {
                    "Content-Range": f"bytes 0-0/{len(data)}"}
            return 200, data, {"Content-Length": str(len(data))}
        with mock.patch.object(rp, "fetch_bytes", side_effect=tampered):
            report = self._drift(self.deployed)
        self.assertFalse(report["ok"])
        self.assertEqual(report["remote_only"], [])
        self.assertTrue(any("feed.xml differs" in i for i in report["issues"]),
                        report["issues"])

    def test_sweep_writes_nothing(self):
        before = {p: p.stat().st_mtime_ns for p in self.site.iterdir()
                  if p.is_file()}
        self._drift(self.deployed + ["ghost.md"])
        after = {p: p.stat().st_mtime_ns for p in self.site.iterdir()
                 if p.is_file()}
        self.assertEqual(before, after)


class ListRemoteTreeTests(unittest.TestCase):
    """The network seam: it must refuse a truncated listing, never pass it."""

    def _stub(self, payloads):
        calls = []

        class Resp:
            def __init__(self, body):
                self._body = body
            def read(self):
                return json.dumps(self._body).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def urlopen(request, timeout=None):
            calls.append(request.full_url)
            return Resp(payloads[len(calls) - 1])
        return urlopen, calls

    def test_returns_blob_paths_only(self):
        branch = {"commit": {"commit": {"tree": {"sha": "deadbeef"}}}}
        tree = {"truncated": False, "tree": [
            {"path": "feed.xml", "type": "blob"},
            {"path": "episodes", "type": "tree"},
            {"path": "episodes/001/script.md", "type": "blob"}]}
        urlopen, calls = self._stub([branch, tree])
        with mock.patch("urllib.request.urlopen", urlopen), \
             mock.patch.object(rp, "load_deploy_token", return_value="t"):
            got = rp.list_remote_tree()
        self.assertEqual(got, ["feed.xml", "episodes/001/script.md"])
        self.assertIn("deadbeef", calls[1])

    def test_truncated_listing_raises_rather_than_under_reporting(self):
        branch = {"commit": {"commit": {"tree": {"sha": "abc"}}}}
        tree = {"truncated": True, "tree": [{"path": "feed.xml", "type": "blob"}]}
        urlopen, _ = self._stub([branch, tree])
        with mock.patch("urllib.request.urlopen", urlopen), \
             mock.patch.object(rp, "load_deploy_token", return_value="t"):
            with self.assertRaises(ValueError):
                rp.list_remote_tree()

    def test_targets_this_shows_repo_and_never_the_sibling(self):
        branch = {"commit": {"commit": {"tree": {"sha": "abc"}}}}
        tree = {"truncated": False, "tree": []}
        urlopen, calls = self._stub([branch, tree])
        with mock.patch("urllib.request.urlopen", urlopen), \
             mock.patch.object(rp, "load_deploy_token", return_value="t"):
            rp.list_remote_tree()
        self.assertIn("nih-sepa-genetics-podcast", calls[0])
        for url in calls:
            self.assertNotIn("human-in-the-loop", url.lower())


if __name__ == "__main__":
    unittest.main()
