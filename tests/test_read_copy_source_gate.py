"""Run 092: the read lane's `audio` field decided the delivered bytes and had
no reader anywhere.

`publish_feed.py` open-coded `ROOT/episodes/<num>/<rec['audio']>` twice -- once
to test existence, once to copy the file into `feed-site/` -- and no gate ever
compared that registry field to anything. `robust_pipeline.fidelity_gate()`
hashed the path it merely ASSUMED (`episode-NNN.mp3`) and reported the digest of
that assumed file. A registry entry whose `audio` field points at another
episode's mp3 therefore shipped those bytes through a green gate: the gate
blessed the verified audio while the copy step obeyed the field.

`verify_feed`, `feed_coverage` and `registry_audit` were all accurate and all
blind -- they check existence, length and digest agreement against the recorded
digest of the *assumed* file, so an escaped field satisfies every one of them.

The fix is one resolver (`publish_feed.read_copy_source`) used by both call
sites and by the gate, plus a refusal for a field that escapes its own episode
directory or is not a usable filename. These tests pin the invariant that the
gate hashes the file the copy step will actually ship, and that nothing else was
granted: the canonical case still passes with an empty issue list and every
pre-existing refusal (missing digest, coverage floor, missing source.txt) still
refuses.

Load-bearing: against the pre-fix copies (`pipeline/*.bak-run092`) the escape
passes the gate with an empty issue list, so the assertions below fail. Prove it
with:

    mkdir -p /opt/data/tmp/run092_pre && cp pipeline/*.bak-run092 /opt/data/tmp/run092_pre/ \
      && cd /opt/data/tmp/run092_pre && for f in *.bak-run092; do cp "$f" "${f%.bak-run092}"; done
    RUN092_PRE=/opt/data/tmp/run092_pre python3 tests/test_read_copy_source_gate.py   # fails
    python3 tests/test_read_copy_source_gate.py                                        # passes

Stub audio is arbitrary bytes: the gate hashes whatever is on disk, so no TTS is
spent. `duration()` is stubbed only so the feed build does not shell out to
ffprobe; the assertion is about which file is copied, not about its length.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
PRE = os.environ.get("RUN092_PRE")
if PRE:
    sys.path.insert(0, PRE)
else:
    sys.path.insert(0, str(TREE / "pipeline"))

import publish_feed as pf  # noqa: E402
import robust_pipeline as rp  # noqa: E402


def stub_audio(path: Path) -> None:
    path.write_bytes(b"STUB-AUDIO-BYTES-FOR-READING-" + path.name.encode())


def build(scratch: Path, number: str, audio_field, digest: bool = True,
         coverage: float = 1.0, source: bool = True) -> dict:
    d = scratch / "episodes" / number
    d.mkdir(parents=True)
    stub_audio(d / f"episode-{number}.mp3")
    if source:
        (d / "source.txt").write_text(f"body text of paper {number}\n" * 20)
    script = (d / "script.md")
    script.write_text(f"**Reader:** body text of paper {number}\n" * 20)
    (d / "episode-notes.md").write_text(f"# Reading {number}\n\nnotes\n")
    rec = {
        "episode": number,
        "verified": True,
        "coverage": coverage,
        "source_words": 120,
        "citation": f'Author {number}, "Paper {number}", Journal 2026.',
        "guid": f"episode-{number}-reading-KKEY{number}0",
        "built_at": "2026-11-21T00:00:00+00:00",
        "audio": audio_field,
        "script_sha256": rp.sha256(script),
        "audio_bytes": (d / f"episode-{number}.mp3").stat().st_size,
    }
    if source:
        rec["source_sha256"] = rp.sha256(d / "source.txt")
    if digest:
        rec["audio_sha256"] = rp.sha256(d / f"episode-{number}.mp3")
    return rec


class CopySourceGateTests(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="run092_"))
        (self.scratch / "pipeline").mkdir()
        (self.scratch / "feed-site").mkdir()
        self.old = (rp.ROOT, rp.PIPELINE, rp.READ_MANIFEST_PATH, pf.ROOT, pf.SITE)
        rp.ROOT = self.scratch
        rp.PIPELINE = self.scratch / "pipeline"
        rp.READ_MANIFEST_PATH = rp.PIPELINE / "read-episodes.json"
        pf.ROOT = self.scratch
        pf.SITE = self.scratch / "feed-site"
        (pf.SITE / "cover.png").write_bytes(b"stub-cover")
        (rp.PIPELINE / "manifest.json").write_text(
            json.dumps({"episodes": {}, "schema_version": 1}))
        (rp.PIPELINE / "state.json").write_text(
            json.dumps({"episodes": {}, "schema_version": 1}))

        self.reg = {
            # canonical control: the field is the canonical name
            "990": build(self.scratch, "990", "episode-990.mp3"),
            # the defect: the field points at another episode's audio
            "991": build(self.scratch, "991", "../990/episode-990.mp3"),
            # a field that is not a filename at all
            "992": build(self.scratch, "992", 12345),
            # pre-existing refusals, to show nothing was granted
            "993": build(self.scratch, "993", "episode-993.mp3", digest=False),
            "994": build(self.scratch, "994", "episode-994.mp3", coverage=0.90),
            "995": build(self.scratch, "995", "episode-995.mp3", source=False),
            # the detector still works when the wrong bytes arrive through the
            # path the gate reads: canonical field, swapped audio
            "996": build(self.scratch, "996", "episode-996.mp3"),
        }
        shutil.copyfile(self.scratch / "episodes/990/episode-990.mp3",
                        self.scratch / "episodes/996/episode-996.mp3")
        rp.READ_MANIFEST_PATH.write_text(json.dumps({"episodes": self.reg}))
        pf.EP = []

    def tearDown(self):
        (rp.ROOT, rp.PIPELINE, rp.READ_MANIFEST_PATH, pf.ROOT, pf.SITE) = self.old
        shutil.rmtree(self.scratch, ignore_errors=True)

    def test_registry_path_is_opencoded_exactly_once(self):
        source = (TREE / "pipeline" / "publish_feed.py").read_text()
        self.assertEqual(source.count("rec.get('audio'"), 1,
                         "the registry path is open-coded a second time")

    def test_gate_hashes_the_file_the_copy_step_will_ship(self):
        """The load-bearing invariant: gate path == copy path, for every entry."""
        resolver = getattr(pf, "read_copy_source", None)
        self.assertIsNotNone(resolver, "no single resolver exists for the registry field")
        for number, rec in self.reg.items():
            verdict = rp.fidelity_gate(number)
            # Expected path computed here, independently of the resolver, from the
            # registry field itself -- otherwise this compares the gate to itself.
            field = rec["audio"]
            expected = None if not isinstance(field, str) else str(
                self.scratch / "episodes" / number / field)
            self.assertEqual(
                verdict["audio"].get("shipped_from"), expected,
                f"reading {number}: the gate hashed a file the copy step will not ship")

    def test_field_escaping_its_episode_directory_is_refused(self):
        verdict = rp.fidelity_gate("991")
        self.assertFalse(verdict["ok"])
        issues = " ".join(verdict["issues"])
        self.assertIn("`audio` field resolves outside episodes/991/", issues)
        self.assertIn("episode-990.mp3", issues)

    def test_field_that_is_not_a_filename_is_refused_not_crashed(self):
        verdict = rp.fidelity_gate("992")
        self.assertFalse(verdict["ok"])
        self.assertIn("not a usable filename", " ".join(verdict["issues"]))
        self.assertIsNone(pf.read_copy_source("992", self.reg["992"]))

    def test_canonical_case_still_passes_with_an_empty_issue_list(self):
        verdict = rp.fidelity_gate("990")
        self.assertTrue(verdict["ok"], verdict["issues"])
        self.assertEqual(verdict["issues"], [])
        self.assertEqual(verdict["audio"]["sha256"], self.reg["990"]["audio_sha256"])

    def test_pre_existing_refusals_are_not_granted(self):
        self.assertIn("registry records no audio_sha256",
                      " ".join(rp.fidelity_gate("993")["issues"]))
        self.assertIn("below the", " ".join(rp.fidelity_gate("994")["issues"]))
        self.assertIn("missing source.txt",
                      " ".join(rp.fidelity_gate("995")["issues"]))
        self.assertIn("does not match the verified audio",
                      " ".join(rp.fidelity_gate("996")["issues"]))

    def test_copy_step_ships_what_the_gate_blessed(self):
        resolver = getattr(pf, "read_copy_source", None)
        self.assertIsNotNone(resolver, "no single resolver exists for the registry field")
        shipped = []
        real_copy, real_duration = pf.atomic_copy, pf.duration
        pf.atomic_copy = lambda src, dst: shipped.append((src, dst))
        pf.duration = lambda p: "0:01"
        try:
            pf.main()
        finally:
            pf.atomic_copy, pf.duration = real_copy, real_duration
        self.assertEqual(
            [s for s, _ in shipped],
            [resolver(n, r) for n, r in pf.read_episodes()],
            "the copy step resolved a path the gate did not hash")


if __name__ == "__main__":
    unittest.main(verbosity=2)
