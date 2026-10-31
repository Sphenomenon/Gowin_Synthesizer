#!/usr/bin/env python3
"""Opt-in ADSR register cuts retain ordered PCM and drained voice state."""
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
from workstation_oscillator_expression_provenance import ADAPTATION, restore_native


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RuntimeADSRPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('verilator'):
            raise RuntimeError('Verilator is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='runtime-adsr-pipeline-')
        cls.stage = Path(cls.temp.name)
        native = ROOT / 'rtl/audio/workstation_runtime_oscillator_engine.sv'
        provenance = native.with_suffix('.provenance.json')
        metadata = json.loads(provenance.read_bytes())
        parent = restore_native(native.read_bytes(), provenance.read_bytes(), (ROOT / ADAPTATION).read_bytes())
        if digest(parent) != metadata['native_sha256']:
            raise ValueError('native ADSR provenance drifted')
        restored = parent.decode()
        for edit in reversed(metadata['forward_edits']):
            if restored.count(edit['after']) != edit['count']:
                raise ValueError('ADSR reverse provenance anchor drifted')
            restored = restored.replace(edit['after'], edit['before'])
        if digest(restored.encode()) != metadata['prepared_sha256']:
            raise ValueError('ADSR ancestry no longer reaches exact prepared bytes')
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        sources = []
        for name, identity in metadata['test_dependencies'].items():
            data = baseline.read_bytes(name)
            if digest(data) != identity['baseline_sha256']:
                raise ValueError('locked dependency drifted: ' + name)
            if 'prepared_exact_edit' in identity:
                edit = identity['prepared_exact_edit']
                if data.decode().count(edit['before']) != 1:
                    raise ValueError('prepared dependency anchor drifted')
                data = data.decode().replace(edit['before'], edit['after']).encode()
                if digest(data) != identity['prepared_sha256']:
                    raise ValueError('prepared dependency hash drifted')
            target = cls.stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if target.suffix == '.sv':
                sources.append(target)
        tb = ROOT / 'sim/audio/tb_workstation_runtime_adsr_pipeline.sv'
        cls.hashes = {str(path.relative_to(ROOT)): digest(path.read_bytes())
                      for path in (native, provenance, tb, ROOT / ADAPTATION,
                                   ROOT / 'tools/workstation_oscillator_expression_provenance.py')}
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_adsr_pipeline',
                   '--Mdir', str(cls.stage / 'obj'), '-o', 'runtime_adsr_pipeline',
                   str(tb), str(native), *map(str, sources)]
        result = subprocess.run(command, cwd=cls.stage, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout[-2000:] + result.stderr[-10000:])
        warnings = [line for line in result.stderr.splitlines() if line.startswith('%Warning-')]
        unexpected = [line for line in warnings if not line.startswith('%Warning-UNSIGNED:')]
        if unexpected:
            raise RuntimeError('unexpected compile warning: ' + '\n'.join(unexpected))
        print('COMPILE_WARNINGS', json.dumps(warnings))
        cls.binary = cls.stage / 'obj/runtime_adsr_pipeline'

    @classmethod
    def tearDownClass(cls):
        for name, expected in cls.hashes.items():
            if digest((ROOT / name).read_bytes()) != expected:
                raise ValueError('source changed during ADSR verification: ' + name)
        print('SOURCE_SHA256', json.dumps(cls.hashes, sort_keys=True))
        cls.temp.cleanup()

    def scenario(self, value, expected):
        result = subprocess.run([str(self.binary), f'+SCENARIO={value}'], cwd=self.stage,
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout)
        print(result.stdout.strip())

    def test_ordered_pcm_and_drained_state_all_modes_32voices_both_rates(self):
        self.scenario(0, 'PASS ADSR pipeline transactions')

    def test_zero_saturation_borrow_decay_boundary_and_random_states(self):
        self.scenario(1, 'PASS ADSR pipeline arithmetic4096 voices')

    def test_panic_flush_every_adsr_stage_and_renderer_tail_then_reuse(self):
        self.scenario(2, 'PASS ADSR pipeline PANIC47 offsets')


if __name__ == '__main__':
    unittest.main()
