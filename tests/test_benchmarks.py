"""Regression tests for experiment coverage, resume integrity and mixed-run refusal."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('proposal', ROOT/'benchmarks/proposal.py')
proposal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proposal)


class BenchmarkTests(unittest.TestCase):
    def test_required_workloads(self):
        threads = [1, 2, 4, 8]
        self.assertEqual([len(proposal.configurations(s, threads)) for s in proposal.STAGES], [51, 24, 10, 6, 16])
        self.assertEqual({c['tile'] for c in proposal.configurations('tiles', threads)}, {8, 16, 32, 64})
        quality = proposal.configurations('quality', threads)
        self.assertEqual({c['width'] for c in quality}, {512, 1024})
        self.assertEqual({c['spp'] for c in quality}, {32, 64, 128})
        self.assertEqual({c['scene'] for c in proposal.configurations('main', threads)}, {'room', 'uneven', 'bunny'})

    def test_smoke_is_explicitly_smaller(self):
        full = proposal.configurations('main', [1, 2])
        small = proposal.configurations('main', [1, 2], 'smoke')
        self.assertEqual(len(full), len(small))
        self.assertTrue(all(c['width'] == 67 and c['spp'] == 2 for c in small))

    def test_resume_refuses_changed_inputs(self):
        original = {'binary_sha256': 'a', 'bunny_sha256': 'b', 'host': 'machine-a', 'threads': [1, 2], 'environment': {'OMP_NUM_THREADS': '2'}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            proposal.ensure_provenance(out, original)
            proposal.ensure_provenance(out, original)
            for field, value in [('binary_sha256', 'c'), ('bunny_sha256', 'c'), ('host', 'machine-b'), ('threads', [1, 4]), ('environment', {})]:
                changed = dict(original, **{field: value})
                with self.assertRaisesRegex(ValueError, field):
                    proposal.ensure_provenance(out, changed)
            self.assertEqual(json.loads((out/'run.metadata.json').read_text())['identity'], original)

    def test_legacy_data_are_not_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'main.csv').write_text('historical data\n')
            with self.assertRaisesRegex(ValueError, 'provenance'):
                proposal.ensure_provenance(out, {})

    def test_duplicate_partial_and_incorrect_rows_rejected(self):
        planned = [dict(c, round=0) for c in proposal.configurations('main', [1, 2], 'smoke')]
        row = dict(planned[0], actual_threads=1, render_s=.01, hash='abc')
        done, _ = proposal.check_rows([row], planned)
        self.assertEqual(len(done), 1)
        for rows in [[row, row], [dict(row, actual_threads=2)], [dict(row, hash='')], [dict(row, render_s='nan')], [{'scene': 'room'}]]:
            with self.assertRaises(ValueError):
                proposal.check_rows(rows, planned)
        parallel = dict(planned[1], actual_threads=1, render_s=.01, hash='different')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            proposal.check_rows([row, parallel], planned)


if __name__ == '__main__':
    unittest.main()
