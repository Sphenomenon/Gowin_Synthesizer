#!/usr/bin/env python3
"""Exact prepared migration, per-clock48k reference and held runtime switches."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RuntimeOscillatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('verilator'):
            raise RuntimeError('Verilator is required for exact parameter-string RTL')
        cls.temp = tempfile.TemporaryDirectory(prefix='runtime-oscillator-')
        cls.stage = Path(cls.temp.name)
        native = ROOT / 'rtl/audio/workstation_runtime_oscillator_engine.sv'
        provenance = json.loads(native.with_suffix('.provenance.json').read_text())
        payload = native.read_bytes()
        if digest(payload) != provenance['native_sha256']:
            raise ValueError('native migration drifted from its recorded identity')
        restored = payload.decode()
        for edit in reversed(provenance['forward_edits']):
            if restored.count(edit['after']) != edit['count']:
                raise ValueError('reverse provenance anchor drifted')
            restored = restored.replace(edit['after'], edit['before'])
        if digest(restored.encode()) != provenance['prepared_sha256']:
            raise ValueError('native module does not reverse to exact prepared engine')
        reference = cls.stage / 'reference_engine.sv'
        reference.write_text(restored)
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        sources = []
        for name, entry in provenance['test_dependencies'].items():
            data = baseline.read_bytes(name)
            if digest(data) != entry['baseline_sha256']:
                raise ValueError('locked test dependency drifted: ' + name)
            if 'prepared_exact_edit' in entry:
                edit = entry['prepared_exact_edit']
                text = data.decode()
                if text.count(edit['before']) != 1:
                    raise ValueError('sine preparation anchor drifted')
                data = text.replace(edit['before'], edit['after']).encode()
                if digest(data) != entry['prepared_sha256']:
                    raise ValueError('sine test dependency differs from actual prepared input')
            target = cls.stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if target.suffix == '.sv':
                sources.append(target)
        tb = ROOT / 'sim/audio/tb_workstation_runtime_oscillator.sv'
        cls.source_hashes = {str(path.relative_to(ROOT)): digest(path.read_bytes())
                             for path in (native, native.with_suffix('.provenance.json'), tb)}
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_oscillator',
                   '--Mdir', str(cls.stage / 'obj'), '-o', 'runtime_oscillator',
                   str(tb), str(native), str(reference), *map(str, sources)]
        result = subprocess.run(command, cwd=cls.stage, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout[-3000:] + result.stderr[-12000:])
        cls.binary = cls.stage / 'obj/runtime_oscillator'
        cls.compile_warning_details = result.stderr
        cls.compile_warning_counts = {}
        for line in result.stderr.splitlines():
            if line.startswith('%Warning-'):
                name = line.split(':', 1)[0][9:]
                cls.compile_warning_counts[name] = cls.compile_warning_counts.get(name, 0) + 1
        unexpected = set(cls.compile_warning_counts) - {'PINMISSING', 'UNSIGNED'}
        if unexpected:
            raise RuntimeError('unexpected compile warnings: ' + result.stderr)
        # PINMISSING is the intentional omitted-runtime-input compatibility
        # call. UNSIGNED is inherited in the exact prepared priority logic.
        print('COMPILE_WARNINGS', json.dumps(cls.compile_warning_counts, sort_keys=True))

    @classmethod
    def tearDownClass(cls):
        for name, expected in cls.source_hashes.items():
            if digest((ROOT / name).read_bytes()) != expected:
                raise ValueError('source changed during verification: ' + name)
        print('SOURCE_SHA256', json.dumps(cls.source_hashes, sort_keys=True))
        cls.temp.cleanup()

    def scenario(self, number, expected):
        result = subprocess.run([str(self.binary), f'+SCENARIO={number}'], cwd=self.stage,
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout)
        print(result.stdout.strip())

    def test_48k_per_cycle_reference_five_timbres_32voices_abc(self):
        self.scenario(0, 'PASS runtime oscillator unity')

    def test_held_switch_exact_dds_envelope_cutoff_reverse(self):
        self.scenario(1, 'PASS runtime oscillator held switch')

    def test_panic_natural_tail_true_quiescence(self):
        self.scenario(2, 'PASS runtime oscillator PANIC quiescent')

    def test_busy_rate_commit_is_rejected(self):
        result = subprocess.run([str(self.binary), '+SCENARIO=3'], cwd=self.stage,
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('rate commit outside oscillator quiescence', result.stdout + result.stderr)
        print('PASS runtime oscillator rejects busy commit')


if __name__ == '__main__':
    unittest.main()
