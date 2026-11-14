"""Deployed-feed drift checks for verify_feed() (run 056).

verify_feed()'s remote branch used to assert only "HTTP 200 and at least one
RSS item". Every other remote probe iterates the items the LOCAL feed carries
and resolves each asset by filename, so a deploy whose enclosures and notes
landed while feed.xml did not returned ok: true with an empty issue list --
and that verdict is push_to_remote()'s success criterion.

These tests pin both drift directions, and pin that an intact deploy is still
accepted unchanged.
"""
import http.server
import socketserver
import sys
import threading
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import robust_pipeline as rp  # noqa: E402

FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Moral Machines</title>
    <item>
      <title>Episode 001</title>
      <description>First</description>
      <guid>moral-machines-episode-001</guid>
      <enclosure url="https://example.invalid/episode-001.mp3" length="3" type="audio/mpeg"/>
    </item>
    <item>
      <title>Episode 002</title>
      <description>Second</description>
      <guid>moral-machines-episode-002</guid>
      <enclosure url="https://example.invalid/episode-002.mp3" length="3" type="audio/mpeg"/>
    </item>
  </channel>
</rss>
"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True


class RemoteFeedDriftTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="mm-drift-"))
        self.site = self.tmp / "feed-site"
        self.site.mkdir()
        (self.site / "feed.xml").write_text(FEED)
        for n in ("episode-001.mp3", "episode-002.mp3"):
            (self.site / n).write_bytes(b"abc")
        self.remote_dir = self.tmp / "remote"
        self.remote_dir.mkdir()
        for f in self.site.iterdir():
            (self.remote_dir / f.name).write_bytes(f.read_bytes())
        self.httpd = None

    def tearDown(self):
        if self.httpd is not None:
            self.httpd.shutdown()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _serve(self):
        handler = lambda *a, **k: _Quiet(*a, directory=str(self.remote_dir), **k)
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def _drop_remote(self, guid_substr):
        root = ET.fromstring((self.remote_dir / "feed.xml").read_bytes())
        ch = root.find("channel")
        for item in list(ch.findall("item")):
            if guid_substr in (item.findtext("guid") or ""):
                ch.remove(item)
        ET.ElementTree(root).write(self.remote_dir / "feed.xml",
                                   encoding="utf-8", xml_declaration=True)

    def _verify(self):
        return rp.verify_feed(self.site / "feed.xml", remote=self._serve())

    def test_intact_deploy_reports_no_drift(self):
        r = self._verify()
        rf = next(c for c in r["checks"] if c.get("name") == "remote_feed")
        self.assertEqual(rf["missing_from_remote"], [])
        self.assertEqual(rf["only_on_remote"], [])
        self.assertEqual((rf["local_items"], rf["remote_items"]), (2, 2))

    def test_intact_deploy_adds_no_issue(self):
        r = self._verify()
        self.assertFalse([i for i in r["issues"] if "deployed feed" in i])

    def test_stale_deploy_is_refused(self):
        self._drop_remote("episode-002")
        r = self._verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("deployed feed is stale" in i for i in r["issues"]))

    def test_stale_deploy_names_the_missing_guid(self):
        self._drop_remote("episode-002")
        r = self._verify()
        self.assertTrue(any("moral-machines-episode-002" in i for i in r["issues"]))

    def test_stale_deploy_populates_missing_from_remote(self):
        self._drop_remote("episode-002")
        r = self._verify()
        rf = next(c for c in r["checks"] if c.get("name") == "remote_feed")
        self.assertEqual(rf["missing_from_remote"], ["moral-machines-episode-002"])
        self.assertEqual(rf["only_on_remote"], [])

    def test_remote_ahead_of_local_is_refused(self):
        root = ET.fromstring((self.remote_dir / "feed.xml").read_bytes())
        ch = root.find("channel")
        clone = ET.fromstring(ET.tostring(ch.find("item")))
        clone.find("guid").text = "moral-machines-episode-099-ghost"
        ch.append(clone)
        ET.ElementTree(root).write(self.remote_dir / "feed.xml",
                                   encoding="utf-8", xml_declaration=True)
        r = self._verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("ahead of this tree" in i for i in r["issues"]))
        rf = next(c for c in r["checks"] if c.get("name") == "remote_feed")
        self.assertEqual(rf["only_on_remote"], ["moral-machines-episode-099-ghost"])

    def test_both_directions_reported_together(self):
        self._drop_remote("episode-002")
        root = ET.fromstring((self.remote_dir / "feed.xml").read_bytes())
        ch = root.find("channel")
        clone = ET.fromstring(ET.tostring(ch.find("item")))
        clone.find("guid").text = "moral-machines-episode-099-ghost"
        ch.append(clone)
        ET.ElementTree(root).write(self.remote_dir / "feed.xml",
                                   encoding="utf-8", xml_declaration=True)
        r = self._verify()
        rf = next(c for c in r["checks"] if c.get("name") == "remote_feed")
        self.assertEqual(rf["missing_from_remote"], ["moral-machines-episode-002"])
        self.assertEqual(rf["only_on_remote"], ["moral-machines-episode-099-ghost"])

    def test_zero_item_remote_still_refused_as_check_failure(self):
        (self.remote_dir / "feed.xml").write_bytes(
            b'<?xml version="1.0"?><rss><channel></channel></rss>')
        r = self._verify()
        self.assertFalse(r["ok"])
        self.assertTrue(any("remote feed check failed" in i for i in r["issues"]))

    def test_local_only_verify_records_no_remote_check(self):
        r = rp.verify_feed(self.site / "feed.xml")
        self.assertFalse(any(c.get("name") == "remote_feed" for c in r["checks"]))


if __name__ == "__main__":
    unittest.main()
