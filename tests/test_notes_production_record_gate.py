"""Run 093: the show notes' Production record states claims about this pipeline's
own behaviour, and nothing read them.

`write_notes()` has exactly one call site -- `build()` -- which is necessarily
before any audio exists, so the record it wrote asserted a render date and a voice
for an event that had not happened, and printed the coverage figure as a gate result
when the same call had returned ok=False with "no audio rendered yet".
`record_verdict()` (run 040) persists the real verdict but must not silently rewrite
a published deliverable, so it never touched the notes; `feed_sync` "regenerates" the
notes by copying the very file it audits, so it can only prove self-consistency -- a
claim inside the file can never disagree with the registry or with the render plan.

Two changes, one family:
  * the writer states the verdict the gate actually returned, and the render is
    stated from the render plan (the only record of the event);
  * `fidelity_gate()` -- the single read verdict with one owner -- now reads the
    record and refuses where its claims disagree with the registry or the render
    provenance. It grants nothing.

Also fixed in the same family: preflight's render-plan check read the INTERVIEW
lane's directory (parts-robust), so a genuine reading -- correct plan in parts-read --
was refused at publish, while the plan the read lane actually wrote was read by
nothing on the publish path.

Scratch trees, real functions, silent ffmpeg audio (no TTS spend).
"""
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import read_lane, robust_pipeline

BODY = ("The machine decided to spare the five and sacrifice the one. Readers disagree "
        "about whether an aggregate preference is a decision. A voting rule is not the "
        "same thing as a moral fact, and the sample is a convenience sample.")
PLAN_VOICE = "en-US-AvaMultilingualNeural"  # run 098: the read-lane baseline
# must be the LOCKED voice; the old Andrew baseline asserted preflight ok for a
# plan contradicting the documented lock.


class Fixture:
    def __init__(self, prefix):
        self.saved = {}
        self.tmp = Path(tempfile.mkdtemp(prefix=prefix, dir="/opt/data/tmp"))
        self.pipeline = self.tmp / "pipeline"
        self.pipeline.mkdir()
        shutil.copy(Path(__file__).resolve().parent.parent / "pipeline" / "publish_feed.py",
                    self.pipeline / "publish_feed.py")
        self.ep = self.tmp / "episodes" / "990"
        self.ep.mkdir(parents=True)
        (self.ep / "parts-read").mkdir()
        for mod in (read_lane, robust_pipeline):
            self.point(mod, "ROOT", self.tmp)
        self.point(read_lane, "EPISODES", self.tmp / "episodes")
        self.point(read_lane, "READ_MANIFEST", self.pipeline / "read-episodes.json")
        self.point(read_lane, "STATE_PATH", self.pipeline / "state.json")
        self.point(read_lane, "MANIFEST_PATH", self.pipeline / "manifest.json")
        self.point(robust_pipeline, "PIPELINE", self.pipeline)
        self.point(robust_pipeline, "LEDGER_PATH", self.pipeline / "state.json")
        self.point(robust_pipeline, "MANIFEST_PATH", self.pipeline / "manifest.json")
        self.point(robust_pipeline, "READ_MANIFEST_PATH", self.pipeline / "read-episodes.json")

        self.item = {"key": "ABC12345", "data": {"key": "ABC12345",
                                                 "title": "Scratch reading", "DOI": "", "url": ""}}
        self.citation = ("Scratch, T. Grounded citation check for the notes production "
                         "record. Journal of Test Venues, 2024.")
        self.extraction = {"words": len(read_lane.normalize_words(BODY)), "pages": 1,
                           "pdf_provenance": {"attachment_key": "ATT", "filename": "x.pdf",
                                              "bytes": 10, "source": "zotero",
                                              "extra_pdf_attachments": 0}}
        (self.ep / "source.txt").write_text(BODY)
        # Fixture built by importing the gate's own constants (run 029's rule).
        self.script = (self.ep / "script.md")
        self.script.write_text(
            "**Reader:** This is an automated text-to-speech verbatim reading, produced by a "
            "synthetic voice, and it can be wrong.\n\n<!-- BEGIN READING -->\n**Reader:** "
            + BODY + "\n<!-- END READING -->\n\n**Reader:** " + robust_pipeline.REQUIRED_DISCLOSURE + "\n")
        spoken = len(read_lane.normalize_words(" ".join(read_lane.script_turns(self.script))))
        self.pre = read_lane.verify("990")
        read_lane.register("990", self.item, self.citation, self.extraction, self.pre)
        self.notes = read_lane.write_notes("990", self.item, self.citation,
                                           self.extraction, "deadbeef", self.pre)
        self.record = read_lane.load_read_manifest()["episodes"]["990"]
        self.audio = self.ep / "episode-990.mp3"
        _, imageio_ffmpeg = read_lane.tts_imports()
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i",
                        "anullsrc=r=44100:cl=mono", "-t", str(int(spoken / 150 * 60)),
                        "-c:a", "libmp3lame", "-b:a", "96k", str(self.audio)],
                       check=True, capture_output=True)
        self.post = read_lane.verify("990")
        self.plan = {"script_sha256": hashlib.sha256(self.script.read_bytes()).hexdigest(),
                     "pieces": 1, "pieces_sha256": "x", "voice": PLAN_VOICE, "rate": "-3%",
                     "render_text_version": 1,
                     "rendered_at": "2026-11-22 01:34 UTC"}
        (self.ep / "parts-read" / "render-plan.json").write_text(
            json.dumps(self.plan, indent=1, sort_keys=True))

    def point(self, mod, attr, value):
        """Repoint a module global for this fixture and remember how to put it back:
        these are shared module state, and a test that leaves them pointing at a
        scratch tree breaks whichever test runs next (run 055's trap)."""
        self.saved.setdefault((mod, attr), getattr(mod, attr))
        setattr(mod, attr, value)

    def restore(self):
        for (mod, attr), value in self.saved.items():
            setattr(mod, attr, value)

    def record_block(self):
        return self.notes.read_text().split("## Production record", 1)[1]

    def truth(self):
        """Bring the published record into agreement with the sources it states."""
        read_lane.record_verdict("990", self.post)
        read_lane.refresh_notes_record("990")
        return robust_pipeline.fidelity_gate("990")


class WriterHonestyTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture("mm093_writer_")
        self.addCleanup(self.f.restore)

    def test_writer_states_the_verdict_the_gate_actually_returned(self):
        self.assertFalse(self.f.pre["ok"])
        self.assertEqual(self.f.pre["issues"], ["no audio rendered yet"])
        block = self.f.record_block()
        self.assertIn("gate NOT PASSED at write time", block)
        self.assertNotIn("(gate PASSED)", block)

    def test_writer_does_not_claim_a_render_before_one_exists(self):
        self.assertNotIn("Rendered: 20", self.f.record_block())
        self.assertIn("Rendered: not rendered yet", self.f.record_block())

    def test_record_names_the_voice_the_render_plan_records(self):
        # run 098: the fixture baseline is now the LOCKED voice, so
        # "names the recorded voice, not the module default" needs a plan
        # that records something the default is not. Meaning preserved.
        drifted = "en-US-AriNeural"
        self.f.plan["voice"] = drifted
        (self.f.ep / "parts-read" / "render-plan.json").write_text(json.dumps(self.f.plan))
        read_lane.record_verdict("990", self.f.post)
        read_lane.refresh_notes_record("990")
        block = self.f.record_block()
        self.assertIn(drifted, block)
        self.assertNotIn(read_lane.VOICE, block)
        self.assertIn(self.f.plan["rendered_at"], block)

    def test_refresh_touches_only_the_two_claim_lines(self):
        before = self.f.notes.read_text().splitlines()
        read_lane.record_verdict("990", self.f.post)
        read_lane.refresh_notes_record("990")
        after = self.f.notes.read_text().splitlines()
        self.assertEqual(len(before), len(after))
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual([before[i] for i in changed],
                         [l for l in before if l.startswith(("- Fidelity gate:", "- Rendered:"))])
        # Run 040's protected build-time fact is byte-identical.
        for line in before:
            if line.startswith("- Extracted body text:") or line.startswith("- Source PDF SHA-256:"):
                self.assertIn(line, after)

    def test_refresh_refuses_to_invent_a_notes_file(self):
        self.f.notes.unlink()
        with self.assertRaises(SystemExit):
            read_lane.refresh_notes_record("990")


class RecordReaderTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture("mm093_reader_")
        self.addCleanup(self.f.restore)

    def canonical(self):
        return self.f.truth()

    def test_canonical_case_grants_with_an_empty_issue_list(self):
        result = self.canonical()
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["issues"], [])

    def test_refusal_when_the_record_claims_a_render_with_no_plan(self):
        self.canonical()
        (self.f.ep / "parts-read" / "render-plan.json").unlink()
        result = robust_pipeline.fidelity_gate("990")
        self.assertFalse(result["ok"])
        self.assertTrue(any("no render plan records" in i for i in result["issues"]), result["issues"])

    def test_refusal_when_the_figure_disagrees_with_the_registry(self):
        self.canonical()
        self.f.notes.write_text(self.f.notes.read_text().replace("100.000%", "99.000%"))
        result = robust_pipeline.fidelity_gate("990")
        self.assertFalse(result["ok"])
        self.assertTrue(any("fidelity figure" in i for i in result["issues"]), result["issues"])

    def test_refusal_when_the_verdict_disagrees_with_the_registry(self):
        self.canonical()
        self.f.notes.write_text(self.f.notes.read_text().replace("(gate PASSED)", "(gate NOT PASSED)"))
        result = robust_pipeline.fidelity_gate("990")
        self.assertFalse(result["ok"])
        self.assertTrue(any("gate verdict" in i for i in result["issues"]), result["issues"])

    def test_refusal_when_the_render_date_predates_the_plan(self):
        self.canonical()
        self.f.notes.write_text(self.f.notes.read_text().replace(
            self.f.plan["rendered_at"], "2026-11-21 23:25 UTC"))
        result = robust_pipeline.fidelity_gate("990")
        self.assertFalse(result["ok"])
        self.assertTrue(any("render date" in i for i in result["issues"]), result["issues"])

    def test_refusal_when_the_voice_disagrees_with_the_plan(self):
        self.canonical()
        self.f.notes.write_text(self.f.notes.read_text().replace(PLAN_VOICE, "en-US-AriNeural"))
        result = robust_pipeline.fidelity_gate("990")
        self.assertFalse(result["ok"])
        self.assertTrue(any("voice the render plan" in i for i in result["issues"]), result["issues"])

    def test_refusal_when_the_record_states_no_verdict(self):
        self.canonical()
        self.f.notes.write_text(self.f.notes.read_text().replace(" (gate PASSED)", ""))
        result = robust_pipeline.fidelity_gate("990")
        self.assertFalse(result["ok"])
        self.assertTrue(any("no gate verdict" in i for i in result["issues"]), result["issues"])

    def test_existing_refusals_still_bite(self):
        self.canonical()
        (self.f.ep / "script.md").write_text(self.f.script.read_text() + "\nAn edited line.\n")
        result = robust_pipeline.fidelity_gate("990")
        self.assertFalse(result["ok"])
        self.assertTrue(any("does not match the verified script" in i for i in result["issues"]),
                        result["issues"])

    def test_the_only_notes_audit_compares_the_file_to_its_own_copy(self):
        """feed_sync proves byte-identity between the show-notes file and its published
        copy; it can never see a claim that disagrees with the registry. The reader
        added in run 093 is the first comparison between the record and the sources it
        states -- publish_feed copies the very file it audits."""
        pipeline = Path(__file__).resolve().parent.parent / "pipeline"
        self.assertIn("episode-notes.md", (pipeline / "publish_feed.py").read_text())
        seg = (pipeline / "robust_pipeline.py").read_text().split("def fidelity_gate")[1].split("\ndef ")[0]
        self.assertIn("episode-notes.md", seg)
        self.canonical()
        self.f.notes.write_text(self.f.notes.read_text().replace("100.000%", "99.000%"))
        self.assertFalse(robust_pipeline.fidelity_gate("990")["ok"])


class RenderPlanLaneTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture("mm093_lane_")
        self.addCleanup(self.f.restore)
        self.canonical = self.f.truth()
        (self.f.pipeline / "manifest.json").write_text(json.dumps({"episodes": {"990": {
            "number": "990", "kind": "read", "title": "Scratch reading",
            "description": "d", "read_source": ["ABC12345"]}}}))

    def test_preflight_reads_the_read_lanes_own_plan(self):
        result = robust_pipeline.preflight("990", require_audio=True, enforce_review=True)
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["issues"], [])

    def test_moving_the_plan_to_the_interview_directory_refuses_the_reading(self):
        shutil.move(str(self.f.ep / "parts-read"), str(self.f.ep / "parts-robust"))
        result = robust_pipeline.preflight("990", require_audio=True, enforce_review=True)
        self.assertFalse(result["ok"])
        self.assertTrue(any("render plan" in i for i in result["issues"]), result["issues"])

    def test_a_missing_plan_is_still_a_refusal_not_a_waiver(self):
        (self.f.ep / "parts-read" / "render-plan.json").unlink()
        result = robust_pipeline.preflight("990", require_audio=True, enforce_review=True)
        self.assertFalse(result["ok"])
        self.assertTrue(any("render plan" in i for i in result["issues"]), result["issues"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
