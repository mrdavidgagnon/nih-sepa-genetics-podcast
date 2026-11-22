"""Run 097: the move-evidence reader must see BOTH paths the mover has written.

Defect (proved against pipeline/robust_pipeline.py.bak-run097): run 096 wired the
first reader for the mover's evidence, but the reader read only the canonical path
(run 004's decision). The evidence this tree actually committed lives at the
pre-run-004 path `pipeline/move-results.json`, so ten TRUE move claims reported
`move_evidence_missing` — the audit asserted a defect that did not exist. A
single-path reader over a two-path artifact.

Semantics kept honest: the writer's declared file must still exist (the split is a
real, clearable defect — running the mover regenerates it), and a disagreement
between the two copies is refused. The harvest must not paper over either.
"""
import json
import hashlib
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PIPELINE = Path('/data/.openclaw/workspace/media/sepa-genetics-podcast/pipeline')
sys.path.insert(0, str(PIPELINE))
import robust_pipeline as rp

SUM, READ, PROD = rp.SUMMERIZE_COLLECTION, rp.READ_COLLECTION, rp.PRODUCED_COLLECTION


def rec(key, episode, lane, colls, status='moved'):
    return {'key': key, 'episode': episode, 'kind': 'interview', 'intake': lane,
            'status': status, 'collections': colls}


def ledger(episodes):
    return {'episodes': episodes}


class TwoPathEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='mm097-'))
        self.canon = self.dir / 'move-results.json'
        self.legacy = self.dir / 'pipeline-move-results.json'

    def _run(self, man, led):
        with mock.patch.object(rp, 'MOVE_RESULTS_PATH', self.canon), \
             mock.patch.object(rp, 'LEGACY_MOVE_RESULTS_PATH', self.legacy):
            return rp.move_evidence_report(led, man)

    def test_canonical_evidence_satisfies_the_claim(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']}}
        self.canon.write_text(json.dumps([rec('K1', '001', SUM, [PROD])]))
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'}}))
        self.assertTrue(r['ok'], r['issues'])
        self.assertEqual(r['move_evidence_missing'], [])

    def test_legacy_only_evidence_no_longer_reports_a_false_missing_claim(self):
        """The defect. Pre-fix the claim was asserted against an absent file and
        reported missing although the proof existed in the repo."""
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']}}
        self.legacy.write_text(json.dumps([rec('K1', '001', SUM, [PROD])]))
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'}}))
        self.assertEqual(r['move_evidence_missing'], [], r['issues'])
        self.assertEqual(r['move_evidence_contradiction'], [])
        # the path split itself is still named, not papered over
        self.assertTrue(any('move-results.json' in i and 'cannot read' in i for i in r['issues']))
        self.assertIn(str(self.legacy), r['evidence_paths'])

    def test_union_of_both_paths_covers_different_claims(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']},
               '002': {'status': 'published_and_moved', 'sources': ['K2']}}
        self.canon.write_text(json.dumps([rec('K1', '001', SUM, [PROD])]))
        self.legacy.write_text(json.dumps([rec('K2', '002', SUM, [PROD])]))
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'},
                                   '002': {'status': 'published_and_moved'}}))
        self.assertTrue(r['ok'], r['issues'])
        self.assertEqual(r['move_evidence_missing'], [])

    def test_disagreement_between_the_two_copies_is_refused(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']}}
        self.canon.write_text(json.dumps([rec('K1', '001', SUM, [PROD])]))
        self.legacy.write_text(json.dumps([rec('K1', '001', SUM, [PROD, SUM])]))
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'}}))
        self.assertFalse(r['ok'])
        self.assertTrue(any('disagrees between' in i for i in r['issues']))

    def test_no_evidence_on_either_path_still_refuses(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']}}
        self.canon.write_text(json.dumps([]))
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'}}))
        self.assertFalse(r['ok'])
        self.assertEqual(r['move_evidence_missing'],
                         [{'episode': '001', 'key': 'K1', 'lane': SUM}])

    def test_unparseable_legacy_file_is_a_refusal_not_a_waiver(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']}}
        self.canon.write_text(json.dumps([]))
        self.legacy.write_text('{not json')
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'}}))
        self.assertFalse(r['ok'])
        self.assertTrue(any('cannot read' in i for i in r['issues']))

    def test_non_published_statuses_are_not_demanded(self):
        man = {'001': {'status': 'published_pending_zotero_move', 'sources': ['K1']}}
        self.canon.write_text(json.dumps([]))
        r = self._run(man, ledger({'001': {'status': 'published_pending_zotero_move'}}))
        self.assertTrue(r['ok'], r['issues'])
        self.assertEqual(r['move_evidence_checked'], 0)

    def test_contradiction_still_bites_through_the_harvest(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']}}
        self.legacy.write_text(json.dumps([rec('K1', '001', SUM, [PROD, SUM])]))
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'}}))
        self.assertEqual(len(r['move_evidence_contradiction']), 1)

    def test_dual_use_key_is_checked_against_its_own_lane(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']},
               '501': {'status': 'published_and_moved', 'kind': 'read', 'read_source': ['K1']}}
        self.legacy.write_text(json.dumps([
            rec('K1', '001', SUM, [PROD, READ]),
            rec('K1', '501', READ, [PROD, SUM], 'already-moved')]))
        r = self._run(man, ledger({'001': {'status': 'published_and_moved'},
                                   '501': {'status': 'published_and_moved'}}))
        self.assertEqual(r['move_evidence_contradiction'], [])
        self.assertEqual(r['move_evidence_missing'], [])

    def test_unclaimed_evidence_is_still_reported(self):
        man = {}
        self.canon.write_text(json.dumps([]))
        self.legacy.write_text(json.dumps([rec('K9', '077', SUM, [PROD])]))
        r = self._run(man, ledger({}))
        self.assertEqual(r['move_records_unclaimed'], [{'key': 'K9', 'episode': '077'}])

    def test_the_reader_writes_nothing(self):
        man = {'001': {'status': 'published_and_moved', 'sources': ['K1']}}
        self.legacy.write_text(json.dumps([rec('K1', '001', SUM, [PROD])]))
        self.canon.write_text(json.dumps([]))
        before = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in (self.canon, self.legacy)}
        self._run(man, ledger({'001': {'status': 'published_and_moved'}}))
        after = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in (self.canon, self.legacy)}
        self.assertEqual(before, after)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         ['move-results.json', 'pipeline-move-results.json'])

    def test_registry_exposes_the_contributing_paths(self):
        with mock.patch.object(rp, 'LEDGER_PATH', self.dir / 'state.json'), \
             mock.patch.object(rp, 'MANIFEST_PATH', self.dir / 'manifest.json'), \
             mock.patch.object(rp, 'MOVE_RESULTS_PATH', self.canon), \
             mock.patch.object(rp, 'LEGACY_MOVE_RESULTS_PATH', self.legacy):
            (self.dir / 'state.json').write_text(json.dumps({'episodes': {}}))
            (self.dir / 'manifest.json').write_text(json.dumps({'episodes': {}}))
            self.legacy.write_text(json.dumps([]))
            r = rp.registry_audit()
            self.assertIn('evidence_paths', r)
            self.assertIn(str(self.legacy), r['evidence_paths'])


if __name__ == '__main__':
    unittest.main()
