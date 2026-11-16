"""Run 067: the read verdict must not overwrite a build-time published fact.

``source_words`` means two different things on either side of the
build/verify boundary, and ``read_lane.record_verdict()`` let the second
overwrite the first:

* ``build()``/``register()`` store ``extraction["words"]``, i.e.
  ``len(text.split())`` over the pypdf body-text extraction -- a BUILD-TIME
  FACT.
* ``verify()`` exposes a same-named field holding ``len(normalize_words(
  source))``, the count of ``[a-z0-9]+`` runs in ``source.txt`` -- a GATE
  METRIC.

They disagree by a few percent on any real paper (hyphenated compounds,
parenthesised statistics and numerals split differently): 13602 vs 13985 on
the sibling tree's real reading 501.

The build-time figure is a PUBLISHED DELIVERABLE, not bookkeeping.
``publish_feed.read_notes_html()`` prints it verbatim into the feed's
``<content:encoded>`` ("... of the N extracted body words are present in the
reading, in source order") and ``read_lane.write_notes()`` prints the same
number into ``episodes/NNN/episode-notes.md``. So the documented operator flow
-- ``render`` then ``verify --episode NNN`` (run 040) -- silently rewrote a
sentence in the published show notes and left the deployed notes file and the
feed item disagreeing about the same paper.

No gate can see it. The fidelity gate compares ``script.md`` against
``source.txt`` (both written in the same breath, so coverage reads 1.0) and
merely REPORTS this field without comparing it to anything; the notes file is
checked for existence, never for agreement with the feed. ``coverage``,
``registry``, ``verify`` and ``preflight`` were all accurate and all blind.

These tests pin both halves: the build-time fact survives every verify, and
nothing was granted -- a failing gate still writes ``verified: false`` with its
issue list, and the gate's own counts remain auditable under their own names.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import read_lane as rl  # noqa: E402

TREE = Path(__file__).resolve().parents[1]

CITATION = ('Jane Q. Researcher. "Moral trade-offs in autonomous driving." '
            'Journal of Machine Ethics 4(2), 2026, pp. 101-139.')

# Prose with the punctuation/hyphen density of a real extracted paper, so the
# two counting rules genuinely disagree. If they agreed the overwrite would be
# harmless, so this divergence is the premise of the whole module.
BODY = (
    "Autonomous vehicles promise large reductions in road fatalities. "
    "Yet self-driving systems face trade-offs that are not merely technical: "
    "they are moral. Bonnefon et al. (2016) showed that participants approved "
    "of utilitarian vehicles in the abstract, with 76% favouring sacrifice of "
    "one passenger to save ten pedestrians, while reporting a lower likelihood "
    "of buying such a vehicle themselves. This self-interest gap is robust. "
    "We replicate it across three studies (N = 1,303; N = 2,404; N = 998) and "
    "find the effect size unchanged (d = 0.41, 95% CI [0.33, 0.49])."
)


class SourceWordsProvenanceTests(unittest.TestCase):
    """record_verdict() persists the gate's counts without clobbering build's."""

    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.root = root
        (root / "pipeline").mkdir()
        self.epdir = root / "episodes" / "990"
        self.epdir.mkdir(parents=True)

        source_text = "\n\n".join([BODY] * 8)
        (self.epdir / "source.txt").write_text(source_text)
        self.build_words = len(source_text.split())
        self.gate_words = len(re.findall(r"[a-z0-9]+", source_text.lower()))

        paras = source_text.split("\n\n")
        self.paras = paras
        self._write_script(paras)

        self.read_manifest = root / "pipeline" / "read-episodes.json"
        self.state_path = root / "pipeline" / "state.json"
        self.manifest_path = root / "pipeline" / "manifest.json"
        self._write_registry(self.build_words)
        for path in (self.state_path, self.manifest_path):
            path.write_text(json.dumps({"schema_version": 1, "episodes": {}}))
        (self.epdir / "episode-notes.md").write_text(
            f"- Extracted body text: {self.build_words} words from 8 PDF pages\n")

        # Repoint the module's path constants at the scratch tree. Patching the
        # module attributes is enough because read_lane resolves them at call
        # time, not as default argument values (the sibling's run-501 lesson).
        self._saved = {name: getattr(rl, name) for name in
                       ("ROOT", "EPISODES", "READ_MANIFEST", "STATE_PATH",
                        "MANIFEST_PATH")}
        rl.ROOT = root
        rl.EPISODES = root / "episodes"
        rl.READ_MANIFEST = self.read_manifest
        rl.STATE_PATH = self.state_path
        rl.MANIFEST_PATH = self.manifest_path

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(rl, name, value)
        self.tmp.cleanup()

    # -- fixtures ---------------------------------------------------------
    def _write_script(self, paras):
        block = "\n".join(f"**Reader:** {p}" for p in paras)
        (self.epdir / "script.md").write_text(
            "**Reader:** This is Moral Machines, reading number 990. What "
            "follows is a complete automated text-to-speech reading of the "
            "body text of one paper, read verbatim.\n\n"
            f"<!-- BEGIN READING -->\n{block}\n<!-- END READING -->\n\n"
            "**Reader:** That was the complete body text.\n")

    def _write_registry(self, source_words):
        self.read_manifest.write_text(json.dumps({
            "schema_version": 1,
            "episodes": {"990": {
                "number": "990", "kind": "read",
                "title": "Moral trade-offs in autonomous driving",
                "item_key": "SCRATCH99", "citation": CITATION,
                "audio": "episode-990.mp3", "base": "episode-990-reading",
                "guid": "episode-990-reading-SCRATCH99",
                "source_words": source_words, "pages": 8,
                "coverage": None, "verified": False,
                "built_at": "2026-11-16T12:00:00+00:00",
            }},
        }))

    def _fake_audio(self, seconds):
        """A placeholder mp3 whose duration audio_seconds() will report."""
        path = self.epdir / "episode-990.mp3"
        path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 4096)
        self._patch_audio_seconds(seconds)
        return path

    def _patch_audio_seconds(self, seconds):
        original = rl.audio_seconds
        rl.audio_seconds = lambda _p: seconds
        self.addCleanup(lambda: setattr(rl, "audio_seconds", original))

    def _pass_verdict(self):
        """Render a gate-passing verdict (audio duration matched to the words)."""
        script = (self.epdir / "script.md").read_text()
        spoken = " ".join(
            re.sub(r"^\*\*Reader:\*\*\s+", "", line)
            for line in script.splitlines() if line.startswith("**Reader:**"))
        words = len(re.findall(r"[a-z0-9]+", spoken.lower()))
        self._fake_audio(words / rl.WORDS_PER_MINUTE * 60)
        return rl.verify("990")

    def _record(self):
        return json.loads(self.read_manifest.read_text())["episodes"]["990"]

    # -- premise ----------------------------------------------------------
    def test_the_two_metrics_genuinely_disagree(self):
        self.assertNotEqual(self.build_words, self.gate_words)
        self.assertGreater(
            abs(self.gate_words - self.build_words) / self.build_words, 0.01,
            "fixture must reproduce a material divergence")

    def test_verify_exposes_the_gate_metric_under_the_shared_name(self):
        verdict = self._pass_verdict()
        self.assertTrue(verdict["ok"], verdict["issues"])
        self.assertEqual(verdict["source_words"], self.gate_words)
        self.assertNotEqual(verdict["source_words"], self.build_words)

    # -- the fix ----------------------------------------------------------
    def test_build_time_source_words_survives_the_verify_step(self):
        rl.record_verdict("990", self._pass_verdict())
        self.assertEqual(self._record()["source_words"], self.build_words)

    def test_gate_counts_are_kept_under_their_own_names(self):
        verdict = self._pass_verdict()
        rl.record_verdict("990", verdict)
        record = self._record()
        self.assertEqual(record["gate_source_words"], verdict["source_words"])
        self.assertEqual(record["gate_spoken_words"], verdict["spoken_words"])

    def test_the_ambiguous_spoken_words_key_is_no_longer_written(self):
        rl.record_verdict("990", self._pass_verdict())
        self.assertNotIn("spoken_words", self._record())

    def test_published_sentence_quotes_the_build_time_count(self):
        """The exact sentence publish_feed.read_notes_html() emits."""
        sys.path.insert(0, str(TREE / "pipeline"))
        import publish_feed  # noqa: WPS433

        rl.record_verdict("990", self._pass_verdict())
        html = publish_feed.read_notes_html("990", self._record())
        quoted = re.search(r"of the (\S+) extracted body words", html)
        self.assertIsNotNone(quoted, html)
        self.assertEqual(quoted.group(1), str(self.build_words))

    def test_feed_item_and_deployed_notes_file_agree(self):
        sys.path.insert(0, str(TREE / "pipeline"))
        import publish_feed  # noqa: WPS433

        rl.record_verdict("990", self._pass_verdict())
        html = publish_feed.read_notes_html("990", self._record())
        quoted = re.search(r"of the (\S+) extracted body words", html).group(1)
        notes = (self.epdir / "episode-notes.md").read_text()
        self.assertIn(quoted, notes)

    def test_repeated_verifies_never_move_the_published_count(self):
        for _ in range(5):
            rl.record_verdict("990", self._pass_verdict())
            self.assertEqual(self._record()["source_words"], self.build_words)

    # -- nothing granted --------------------------------------------------
    def test_a_passing_verdict_is_still_recorded(self):
        verdict = self._pass_verdict()
        rl.record_verdict("990", verdict)
        record = self._record()
        self.assertIs(record["verified"], True)
        self.assertEqual(record["coverage"], verdict["coverage"])
        self.assertEqual(record["gate_issues"], [])
        self.assertTrue(record["verified_at"])

    def test_a_failing_gate_is_still_stored_as_unverified(self):
        """Truncated audio: refused, and the refusal is persisted."""
        self._fake_audio(3.0)
        verdict = rl.verify("990")
        self.assertFalse(verdict["ok"], verdict)
        rl.record_verdict("990", verdict)
        record = self._record()
        self.assertIs(record["verified"], False)
        self.assertTrue(record["gate_issues"])

    def test_build_time_count_survives_a_refusal_too(self):
        self._fake_audio(3.0)
        rl.record_verdict("990", rl.verify("990"))
        self.assertEqual(self._record()["source_words"], self.build_words)

    def test_dropped_source_text_is_still_refused(self):
        self._write_script(self.paras[1:])
        verdict = self._pass_verdict()
        self.assertFalse(verdict["ok"], verdict)
        self.assertLess(verdict["coverage"], 0.995)

    def test_injected_commentary_is_still_refused(self):
        self._write_script(self.paras + [
            "Worth noting that the authors are plainly overstating their "
            "case and the replication literature does not support this "
            "reading at all, in my own editorial judgement."])
        verdict = self._pass_verdict()
        self.assertFalse(verdict["ok"], verdict)
        self.assertTrue(any("added" in issue or "more words" in issue
                            for issue in verdict["issues"]), verdict["issues"])

    def test_missing_audio_is_refused_even_at_full_word_coverage(self):
        """Word fidelity passing is never the episode passing."""
        verdict = rl.verify("990")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["coverage"], 1.0)
        self.assertIn("no audio rendered yet", verdict["issues"])

    def test_record_verdict_refuses_to_invent_an_entry(self):
        self.read_manifest.write_text(
            json.dumps({"schema_version": 1, "episodes": {}}))
        with self.assertRaises(SystemExit) as caught:
            rl.record_verdict("990", self._pass_verdict())
        self.assertIn("990", str(caught.exception))

    def test_audio_provenance_is_still_recorded(self):
        """Runs 040/042: the verdict stays bound to the audio it was earned on."""
        rl.record_verdict("990", self._pass_verdict())
        record = self._record()
        self.assertIsInstance(record["audio_sha256"], str)
        self.assertTrue(record["audio_sha256"])
        self.assertGreater(record["audio_bytes"], 0)

    def test_durable_state_is_still_mirrored(self):
        """Run 009: a reading must be visible to status/watchdog/dup detection."""
        rl.record_verdict("990", self._pass_verdict())
        state = json.loads(self.state_path.read_text())["episodes"]
        manifest = json.loads(self.manifest_path.read_text())["episodes"]
        self.assertIn("990", state)
        self.assertIn("990", manifest)
        self.assertEqual(state["990"]["kind"], "read")
        self.assertEqual(state["990"]["read_source"], ["SCRATCH99"])

    def test_mirrored_record_carries_no_cross_show_identity(self):
        """Run 009: a sibling-show GUID prefix here is a hard bug."""
        rl.record_verdict("990", self._pass_verdict())
        self.assertNotIn("human-in-the-loop",
                         self.manifest_path.read_text().lower())

    def test_verify_itself_remains_side_effect_free(self):
        before = {p: p.read_bytes() for p in
                  (self.read_manifest, self.state_path, self.manifest_path)}
        self._pass_verdict()
        rl.verify("990")
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data, path.name)

    def test_build_time_pages_and_citation_are_untouched(self):
        rl.record_verdict("990", self._pass_verdict())
        record = self._record()
        self.assertEqual(record["pages"], 8)
        self.assertEqual(record["citation"], CITATION)


if __name__ == "__main__":
    unittest.main()
