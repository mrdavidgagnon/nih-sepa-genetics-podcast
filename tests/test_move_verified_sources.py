"""Tests for pipeline/move_verified_sources.py (the Zotero Produced mover).

The invariant these pin is run 054's fix: a move strips EXACTLY the episode's
own intake lane. The pre-fix mover removed both intake collections from every
key, so publishing an interview of a paper David had also filed in Read
destroyed the Read membership -- de-queueing a sanctioned reading (one
interview plus one reading of the same paper is legal by design, see
lane_ownership()) with no report and no Zotero deletion event.

No network: the module is imported with MOVE_VERIFIED_SOURCES_IMPORT_ONLY=1
and build_plan()/move_one() are driven against in-memory fakes.
"""
import importlib.util
import json
import os
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "pipeline" / "move_verified_sources.py"


def load_mover():
    """Import the mover without firing its module-level main()."""
    os.environ["MOVE_VERIFIED_SOURCES_IMPORT_ONLY"] = "1"
    spec = importlib.util.spec_from_file_location("mover_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mover = load_mover()
SUMMERIZE, READ, PRODUCED = mover.SUMMERIZE, mover.READ, mover.PRODUCED
PARENT = "YF84AUZK"
KEY = "DUALKEY1"


def published(number, status="published_pending_zotero_move"):
    return {"episodes": {number: {"status": status}}}


class FakeClient:
    """get/put pair over one in-memory item, recording versions and bodies."""

    def __init__(self, collections, version=100, fail_412=0):
        self.item = {"version": version,
                     "data": {"key": KEY, "collections": list(collections)}}
        self.puts = []
        self.versions_sent = []
        self.fail_412 = fail_412

    def get(self, key):
        return json.loads(json.dumps(self.item))

    def put(self, key, obj, version):
        self.versions_sent.append(version)
        if self.fail_412 > 0:
            self.fail_412 -= 1
            raise urllib.error.HTTPError("u", 412, "Precondition Failed", {}, None)
        self.puts.append(list(obj["data"]["collections"]))
        self.item["version"] = version + 1
        self.item["data"] = json.loads(json.dumps(obj["data"]))
        return 204, str(self.item["version"])

    @property
    def collections(self):
        return list(self.item["data"]["collections"])


class LaneIsolationTests(unittest.TestCase):
    """A move must strip one lane and only one lane."""

    def test_interview_move_preserves_the_read_membership(self):
        client = FakeClient([PARENT, SUMMERIZE, READ])
        item = {"episode": "004", "key": KEY, "kind": "interview",
                "intake": SUMMERIZE}
        result = mover.move_one(item, client.get, client.put)
        self.assertEqual(result["status"], "moved")
        self.assertNotIn(SUMMERIZE, client.collections)
        self.assertIn(READ, client.collections, "the other lane must survive")
        self.assertIn(PRODUCED, client.collections)
        self.assertIn(PARENT, client.collections)

    def test_reading_move_preserves_the_summerize_membership(self):
        client = FakeClient([PARENT, SUMMERIZE, READ])
        item = {"episode": "501", "key": KEY, "kind": "read", "intake": READ}
        mover.move_one(item, client.get, client.put)
        self.assertNotIn(READ, client.collections)
        self.assertIn(SUMMERIZE, client.collections, "the other lane must survive")
        self.assertIn(PRODUCED, client.collections)

    def test_exactly_one_membership_is_removed(self):
        extra = "EXTRACOL"
        client = FakeClient([PARENT, extra, SUMMERIZE, READ])
        mover.move_one({"episode": "004", "key": KEY, "kind": "interview",
                        "intake": SUMMERIZE}, client.get, client.put)
        removed = [c for c in (PARENT, extra, SUMMERIZE, READ)
                   if c not in client.collections]
        self.assertEqual(removed, [SUMMERIZE])

    def test_already_moved_issues_no_put(self):
        client = FakeClient([PARENT, PRODUCED])
        result = mover.move_one({"episode": "004", "key": KEY,
                                 "kind": "interview", "intake": SUMMERIZE},
                                client.get, client.put)
        self.assertEqual(result["status"], "already-moved")
        self.assertEqual(client.puts, [])

    def test_version_guard_is_passed_and_412_is_retried(self):
        client = FakeClient([PARENT, SUMMERIZE], version=777, fail_412=2)
        mover.move_one({"episode": "004", "key": KEY, "kind": "interview",
                        "intake": SUMMERIZE}, client.get, client.put)
        self.assertEqual(client.versions_sent, [777, 777, 777])
        self.assertEqual(len(client.puts), 1)

    def test_no_lane_tuple_strips_both_collections(self):
        """Regression guard on the source itself: no both-lanes removal."""
        source = MODULE_PATH.read_text()
        self.assertIn("c != intake", source)
        self.assertNotIn("not in LANES", source)


class RealClientWireTests(unittest.TestCase):
    """Drive the REAL make_client() against a stubbed urlopen.

    A mutant that deleted If-Unmodified-Since-Version from make_client()
    survived a suite that only asserted on the version handed to an injected
    fake put(): the fake never exercises the header-building code at all. The
    version guard is what makes the move safe against a concurrent edit, so it
    has to be asserted on the outgoing Request itself.
    """

    def _capture(self, method_body):
        sent = []

        class Resp:
            def __init__(self, body=b"{}", status=200):
                self._b, self.status = body, status
                self.headers = {"Zotero-Library-Version": "101"}

            def read(self, *a):
                return self._b

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(request, *a, **kw):
            sent.append(request)
            if (getattr(request, "method", None) or "GET") == "PUT":
                return Resp(b"", 204)
            return Resp(json.dumps({"version": 100, "data": {"collections": []}}).encode())

        real = mover.urllib.request.urlopen
        mover.urllib.request.urlopen = fake_urlopen
        try:
            method_body()
        finally:
            mover.urllib.request.urlopen = real
        return sent

    def test_put_carries_the_version_guard_on_the_wire(self):
        get, put = mover.make_client("not-a-real-key")
        obj = {"version": 777, "data": {"key": KEY, "collections": [PRODUCED]}}
        sent = self._capture(lambda: put(KEY, obj, 777))
        self.assertEqual(len(sent), 1)
        headers = {k.lower(): v for k, v in sent[0].header_items()}
        self.assertEqual(headers.get("if-unmodified-since-version"), "777",
                         "the version guard must reach the wire")
        self.assertEqual(headers.get("content-type"), "application/json")
        self.assertEqual(sent[0].method, "PUT")

    def test_requests_carry_the_api_key_header(self):
        get, put = mover.make_client("not-a-real-key")
        sent = self._capture(lambda: get(KEY))
        headers = {k.lower(): v for k, v in sent[0].header_items()}
        self.assertIn("zotero-api-key", headers)

    def test_requests_target_this_groups_items_endpoint(self):
        get, _ = mover.make_client("not-a-real-key")
        sent = self._capture(lambda: get(KEY))
        self.assertTrue(sent[0].full_url.startswith(
            "https://api.zotero.org/groups/2412036/items/"), sent[0].full_url)


class BuildPlanTests(unittest.TestCase):
    """Selection: the durable ledger governs, and the lane comes from the field."""

    def test_interview_keys_leave_summerize(self):
        manifest = {"episodes": {"004": {"sources": [KEY]}}}
        plan = mover.build_plan(manifest, published("004"), {})
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["intake"], SUMMERIZE)
        self.assertEqual(plan[0]["kind"], "interview")

    def test_reading_keys_leave_read(self):
        manifest = {"episodes": {"501": {"kind": "read", "read_source": [KEY]}}}
        read = {"episodes": {"501": {"verified": True}}}
        plan = mover.build_plan(manifest, published("501"), read)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["intake"], READ)
        self.assertEqual(plan[0]["kind"], "read")

    def test_dual_use_key_yields_one_entry_per_lane(self):
        manifest = {"episodes": {
            "004": {"sources": [KEY]},
            "501": {"kind": "read", "read_source": [KEY]}}}
        state = {"episodes": {
            "004": {"status": "published_and_moved"},
            "501": {"status": "published_pending_zotero_move"}}}
        read = {"episodes": {"501": {"verified": True}}}
        plan = mover.build_plan(manifest, state, read)
        self.assertEqual(len(plan), 2)
        self.assertEqual(sorted(e["intake"] for e in plan),
                         sorted([READ, SUMMERIZE]))

    def test_whole_published_family_is_selected(self):
        """Run 011: a literal == 'published' skipped the documented end state."""
        manifest = {"episodes": {"004": {"sources": [KEY]}}}
        for status in ("published", "published_pending_zotero_move",
                       "published_and_moved"):
            plan = mover.build_plan(manifest, published("004", status), {})
            self.assertEqual(len(plan), 1, status)

    def test_non_published_statuses_are_not_selected(self):
        manifest = {"episodes": {"004": {"sources": [KEY]}}}
        for status in ("planned", "scripted", "rendered", "verified",
                       "failed", "blocked", "PUBLISHED_AND_MOVED"):
            plan = mover.build_plan(manifest, published("004", status), {})
            self.assertEqual(plan, [], status)

    def test_unverified_reading_is_not_selected(self):
        manifest = {"episodes": {"501": {"kind": "read", "read_source": [KEY]}}}
        for read in ({}, {"episodes": {}},
                     {"episodes": {"501": {"verified": False}}},
                     {"episodes": {"501": {"coverage": 1.0}}}):
            plan = mover.build_plan(manifest, published("501"), read)
            self.assertEqual(plan, [], read)

    def test_duplicate_and_empty_keys_are_normalised(self):
        manifest = {"episodes": {"004": {"sources": [KEY, KEY, ""]}}}
        plan = mover.build_plan(manifest, published("004"), {})
        self.assertEqual([e["key"] for e in plan], [KEY])

    def test_missing_registries_do_not_raise(self):
        self.assertEqual(mover.build_plan({}, {}, {}), [])
        self.assertEqual(mover.build_plan(None, None, None), [])

    def test_results_path_is_this_tree_root(self):
        """Run 004: the bookkeeping once landed in the sibling show's tree."""
        self.assertEqual(mover.RESULTS_PATH, ROOT / "move-results.json")

    def test_collection_keys_are_this_shows(self):
        self.assertEqual((SUMMERIZE, READ, PRODUCED),
                         ("V4WXTY8M", "DV6F4ILX", "6P2KVFKQ"))


if __name__ == "__main__":
    unittest.main()
