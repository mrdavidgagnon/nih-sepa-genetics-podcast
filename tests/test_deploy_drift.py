"""Tests for deploy_drift() -- the live-vs-local byte audit (ported run 061).

Every remote probe in verify_feed() is an EXISTENCE probe: notes, cover art and
the landing page are checked for HTTP 200 plus a few bytes, enclosures by
Content-Range total, and the deployed feed by GUID set (run 056). So a deploy
whose notes, cover, landing page or feed *text* was rewritten returned ok: true
with an empty issue list -- the verdict publish_local() refuses on and
push_to_remote() breaks on to call a deploy live. deploy_drift() closes that by
comparing bytes.

fetch_bytes() is the single network seam, so every class here is exercised
offline via mock.patch.object.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402


def _fake_site(tmp, files):
    site = Path(tmp) / "feed-site"
    site.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        p = site / name
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return site


def _responder(deployed, *, ranged=None):
    """Build a fetch_bytes stand-in serving `deployed` {name: bytes}."""
    def fake(url, timeout=15.0, headers=None):
        name = url.rsplit("/", 1)[-1]
        if name not in deployed:
            return 404, b"", {}
        body = deployed[name]
        if headers and "Range" in headers:
            total = len(body) if ranged is None else ranged.get(name, len(body))
            return 206, body[:1], {"Content-Range": f"bytes 0-0/{total}"}
        return 200, body, {"Content-Length": str(len(body))}
    return fake


class DeployDriftTests(unittest.TestCase):
    def setUp(self):
        box = tempfile.TemporaryDirectory()
        self.addCleanup(box.cleanup)
        self.tmp = Path(box.name)

    # ------------------------------------------------------------- clean ----
    def test_byte_identical_deploy_passes(self):
        files = {"feed.xml": "<rss/>", "episode-001-notes.md": "notes",
                 "index.html": "<html></html>"}
        site = _fake_site(self.tmp, files)
        deployed = {k: v.encode() for k, v in files.items()}
        with mock.patch.object(rp, "fetch_bytes", _responder(deployed)):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertTrue(r["ok"])
        self.assertEqual(r["issues"], [])
        self.assertEqual(sorted(r["identical"]), sorted(files))

    def test_writes_nothing(self):
        files = {"feed.xml": "<rss/>"}
        site = _fake_site(self.tmp, files)
        before = sorted(p.name for p in site.iterdir())
        with mock.patch.object(rp, "fetch_bytes",
                               _responder({"feed.xml": b"<rss/>"})):
            rp.deploy_drift(remote="http://x", site=site)
        self.assertEqual(sorted(p.name for p in site.iterdir()), before)

    # ------------------------------------------------------- text drift ----
    def test_text_md5_mismatch_is_refused_and_named(self):
        site = _fake_site(self.tmp, {"episode-001-notes.md": "local"})
        with mock.patch.object(rp, "fetch_bytes",
                               _responder({"episode-001-notes.md": b"LIVE"})):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["md5_mismatch"]), 1)
        entry = r["md5_mismatch"][0]
        self.assertEqual(entry["file"], "episode-001-notes.md")
        self.assertEqual(entry["local_md5"], hashlib.md5(b"local").hexdigest())
        self.assertEqual(entry["remote_md5"], hashlib.md5(b"LIVE").hexdigest())
        self.assertTrue(any("episode-001-notes.md differs" in s for s in r["issues"]))

    def test_feed_text_drift_with_identical_guids_is_caught(self):
        """The run-056 GUID-set check cannot see this; bytes can."""
        local = ("<rss><item><guid>moral-machines-episode-001</guid>"
                 "<description>real</description></item></rss>")
        live = ("<rss><item><guid>moral-machines-episode-001</guid>"
                "<description>DRIFTED</description></item></rss>")
        site = _fake_site(self.tmp, {"feed.xml": local})
        with mock.patch.object(rp, "fetch_bytes",
                               _responder({"feed.xml": live.encode()})):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertFalse(r["ok"])
        self.assertTrue(any("feed.xml differs" in s for s in r["issues"]))

    def test_text_file_absent_live_is_refused(self):
        site = _fake_site(self.tmp, {"feed.xml": "<rss/>"})
        with mock.patch.object(rp, "fetch_bytes", _responder({})):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing_remote"][0]["http"], 404)
        self.assertTrue(any("not deployed" in s for s in r["issues"]))

    # ----------------------------------------------------- binary drift ----
    def test_binary_size_mismatch_is_refused(self):
        site = _fake_site(self.tmp, {"episode-001.mp3": b"a" * 100})
        fake = _responder({"episode-001.mp3": b"a" * 100}, ranged={"episode-001.mp3": 77})
        with mock.patch.object(rp, "fetch_bytes", fake):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertFalse(r["ok"])
        self.assertEqual(r["size_mismatch"][0],
                         {"file": "episode-001.mp3", "local_bytes": 100,
                          "remote_bytes": 77})

    def test_binary_matching_size_passes(self):
        site = _fake_site(self.tmp, {"episode-001.mp3": b"a" * 100})
        with mock.patch.object(rp, "fetch_bytes",
                               _responder({"episode-001.mp3": b"a" * 100})):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertTrue(r["ok"])
        self.assertIn("episode-001.mp3", r["identical"])

    def test_undeterminable_size_is_reported_not_passed(self):
        site = _fake_site(self.tmp, {"episode-001.mp3": b"a" * 10})
        def fake(url, timeout=15.0, headers=None):
            return 206, b"a", {}        # no Content-Range at all
        with mock.patch.object(rp, "fetch_bytes", fake):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertFalse(r["ok"])
        self.assertEqual(r["unverifiable"][0]["file"], "episode-001.mp3")

    def test_text_only_skips_binaries(self):
        site = _fake_site(self.tmp, {"feed.xml": "<rss/>", "episode-001.mp3": b"x" * 9})
        fake = _responder({"feed.xml": b"<rss/>", "episode-001.mp3": b"x" * 9},
                          ranged={"episode-001.mp3": 123456})
        with mock.patch.object(rp, "fetch_bytes", fake):
            r = rp.deploy_drift(remote="http://x", site=site, text_only=True)
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["checked"], 1)
        self.assertTrue(r["text_only"])

    # ----------------------------------------- gitignored-backup retarget ---
    def test_gitignored_files_are_not_demanded_live(self):
        """This tree's feed-site/ holds gitignored *.bak-run004 cover backups.

        push_to_remote() copies every file then runs `git add -A`, which
        respects .gitignore, so they are never deployed and correctly 404.
        A verbatim port of the sibling's loop would report permanent false
        issues against a clean deploy.
        """
        site = _fake_site(self.tmp, {"cover.png": b"img",
                                     "cover.png.bak-run004": b"old"})
        with mock.patch.object(rp, "_deployable_site_files",
                               lambda d: ([site / "cover.png"],
                                          ["cover.png.bak-run004"])):
            with mock.patch.object(rp, "fetch_bytes",
                                   _responder({"cover.png": b"img"})):
                r = rp.deploy_drift(remote="http://x", site=site)
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["not_deployed_by_design"], ["cover.png.bak-run004"])

    def test_non_ignored_missing_file_is_still_refused(self):
        """The retarget is an exclusion for ignored files only, not a waiver."""
        site = _fake_site(self.tmp, {"extra-asset.md": "x"})
        with mock.patch.object(rp, "fetch_bytes", _responder({})):
            r = rp.deploy_drift(remote="http://x", site=site)
        self.assertFalse(r["ok"])
        self.assertTrue(any("extra-asset.md is not deployed" in s
                            for s in r["issues"]))

    def test_deployable_site_files_excludes_real_gitignored_backups(self):
        """Against the REAL feed-site/, driven by git check-ignore."""
        site = rp.ROOT / "feed-site"
        if not site.is_dir():
            self.skipTest("feed-site/ not present")
        keep, skipped = rp._deployable_site_files(site)
        names = {p.name for p in keep}
        self.assertNotIn("cover.png.bak-run004", names)
        self.assertIn("feed.xml", names)
        for name in skipped:
            self.assertIn(".bak-", name)

    # ------------------------------------------------------------ misc ----
    def test_missing_site_dir_is_reported_not_raised(self):
        r = rp.deploy_drift(remote="http://x", site=self.tmp / "nope")
        self.assertFalse(r["ok"])
        self.assertTrue(any("site directory not found" in s for s in r["issues"]))

    def test_defaults_to_this_shows_feed_base(self):
        site = _fake_site(self.tmp, {})
        with mock.patch.object(rp, "fetch_bytes", _responder({})):
            r = rp.deploy_drift(site=site)
        self.assertEqual(r["remote"], rp.FEED_BASE.rstrip("/"))
        self.assertNotIn("human-in-the-loop", r["remote"])


class RemoteTotalSizeTests(unittest.TestCase):
    def test_content_range_total_wins(self):
        self.assertEqual(
            rp.remote_total_size({"Content-Range": "bytes 0-0/4242"}, 206, 1), 4242)

    def test_lowercase_header(self):
        self.assertEqual(
            rp.remote_total_size({"content-range": "bytes 0-0/7"}, 206, 1), 7)

    def test_content_length_on_200(self):
        self.assertEqual(
            rp.remote_total_size({"Content-Length": "99"}, 200, 99), 99)

    def test_body_length_fallback_on_200(self):
        self.assertEqual(rp.remote_total_size({}, 200, 55), 55)

    def test_none_when_undeterminable(self):
        self.assertIsNone(rp.remote_total_size({}, 206, 1))


class FileMd5Tests(unittest.TestCase):
    def test_matches_hashlib_over_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.bin"
            data = bytes(range(256)) * 9000      # > 1 MiB block size
            p.write_bytes(data)
            self.assertEqual(rp.file_md5(p), hashlib.md5(data).hexdigest())


class DriftIsNotAGateTests(unittest.TestCase):
    """drift grants nothing: it must not appear in any publication gate."""

    def test_publish_local_does_not_call_deploy_drift(self):
        import inspect
        self.assertNotIn("deploy_drift", inspect.getsource(rp.publish_local))

    def test_verify_feed_does_not_call_deploy_drift(self):
        import inspect
        self.assertNotIn("deploy_drift", inspect.getsource(rp.verify_feed))


if __name__ == "__main__":
    unittest.main()
