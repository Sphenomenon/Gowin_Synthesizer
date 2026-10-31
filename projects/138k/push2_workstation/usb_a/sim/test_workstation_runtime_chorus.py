#!/usr/bin/env python3
"""Exact prepared Chorus migration and independent physical-time RTL checks."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline
from workstation_chorus_provenance import verify, NARROW_POLICY, ADAPTATION
import workstation_chorus_provenance as chorus


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ChorusAffineLineageTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / chorus.SOURCE).read_bytes()
        self.parent = (ROOT / 'sim/audio/fixtures/chorus_before_affine44.sv').read_bytes()
        self.provenance = (ROOT / chorus.PROVENANCE).read_bytes()
        self.adaptation = (ROOT / chorus.ADAPTATION).read_bytes()

    def test_exact_old_bytes_and_original_prepared_chain(self):
        parent = chorus.restore_affine44(self.source)
        self.assertEqual(parent, self.parent)
        self.assertEqual(digest(parent), chorus.CHORUS_AFFINE44_PARENT_SHA256)
        self.assertEqual(parent.decode().replace(chorus.CHORUS_AFFINE44_BEFORE,
                                               chorus.CHORUS_AFFINE44_AFTER).encode(), self.source)
        original = chorus.verify(parent, self.provenance, NARROW_POLICY, self.adaptation)[0]
        prepared, evidence = chorus.verify(self.source, self.provenance, NARROW_POLICY, self.adaptation)
        self.assertEqual(prepared, original)
        self.assertTrue(evidence['affine44_delay_equivalence'])
        self.assertTrue(evidence['scratch_products_without_reset'])
        self.assertEqual(digest(self.provenance), chorus.PROVENANCE_SHA256)
        self.assertEqual(digest(self.adaptation), chorus.ADAPTATION_SHA256)

    def test_identity_anchor_and_parent_negatives(self):
        after = chorus.CHORUS_AFFINE44_AFTER.encode()
        mutations = [self.source + b'\n', self.source.replace(after, b''),
                     self.source.replace(after, after + after),
                     self.source.replace(b"35'd361267", b"35'd361266")]
        for mutant in mutations:
            with self.subTest(identity=digest(mutant)), self.assertRaises(ValueError):
                chorus.verify(mutant, self.provenance, NARROW_POLICY, self.adaptation)
            # An accidentally rebased outer identity still cannot skip exact
            # anchor cardinality or the exact reviewed old-parent identity.
            with self.subTest(rebased=digest(mutant)), mock.patch.object(
                    chorus, 'CHORUS_AFFINE44_SOURCE_SHA256', digest(mutant)), self.assertRaises(ValueError):
                chorus.restore_affine44(mutant)
        with mock.patch.object(chorus, 'CHORUS_AFFINE44_PARENT_SHA256', '0'*64), self.assertRaises(ValueError):
            chorus.restore_affine44(self.source)


class RuntimeChorusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('verilator'):
            raise RuntimeError('Verilator is required for native RTL verification')
        cls.temp = tempfile.TemporaryDirectory(prefix='runtime-chorus-')
        cls.stage = Path(cls.temp.name)
        native = ROOT / 'rtl/audio/workstation_runtime_chorus_effect.sv'
        provenance_path = native.with_suffix('.provenance.json')
        adaptation_path = ROOT / ADAPTATION
        restored, cls.provenance_evidence = verify(native.read_bytes(), provenance_path.read_bytes(),
                                                  NARROW_POLICY, adaptation_path.read_bytes())
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        effects = baseline.read_bytes('legacy/rtl/audio/stereo_effects.sv').decode()
        start = effects.index('module serial_chorus_effect')
        reference = effects[start:effects.index('endmodule', start) + len('endmodule')]
        if reference != restored:
            raise ValueError('prepared Chorus reference differs from versioned baseline')
        reference_path = cls.stage / 'serial_chorus_effect.sv'
        reference_path.write_text(reference)
        before_affine = ROOT / 'sim/audio/fixtures/chorus_before_affine44.sv'
        before_payload = before_affine.read_bytes()
        if digest(before_payload) != 'a2e09369634b35628920c3198b0020a51a0d4154fe690a2faf93465f8ff57900':
            raise ValueError('exact complete M12 Chorus fixture drifted')
        module_name = 'module workstation_runtime_chorus_effect #('
        if before_payload.decode().count(module_name) != 1:
            raise ValueError('M12 Chorus module rename anchor drifted')
        before_path = cls.stage / 'before_affine44_chorus.sv'
        before_path.write_text(before_payload.decode().replace(module_name,
                              'module workstation_before_affine44_chorus_effect #('))
        math_pkg = baseline.read_bytes('legacy/rtl/audio/audio_math_pkg.sv')
        if digest(math_pkg) != 'f07fab099e112b18d9fc142eeb701139cae62be79e2f25596e134aaecea88f3d':
            raise ValueError('exact prepared arithmetic dependency drifted')
        math_path = cls.stage / 'audio_math_pkg.sv'
        math_path.write_bytes(math_pkg)
        tb = ROOT / 'sim/audio/tb_workstation_runtime_chorus.sv'
        cls.source_hashes = {str(p.relative_to(ROOT)): digest(p.read_bytes())
                             for p in (native, provenance_path, adaptation_path, ROOT / 'tools/workstation_chorus_provenance.py', before_affine, tb, Path(__file__))}
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_chorus',
                   '--Mdir', str(cls.stage / 'obj'), '-o', 'runtime_chorus',
                   str(math_path), str(reference_path), str(before_path), str(native), str(tb)]
        result = subprocess.run(command, cwd=cls.stage, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout[-3000:] + result.stderr[-14000:])
        cls.warning_counts = {}
        for line in result.stderr.splitlines():
            if line.startswith('%Warning-'):
                key = line.split(':', 1)[0][9:]
                cls.warning_counts[key] = cls.warning_counts.get(key, 0) + 1
        # The exact old M12 fixture adds its same four product/mix extensions
        # and CHORUS_BASE assignment truncation; affine arithmetic adds none.
        if cls.warning_counts != {'TIMESCALEMOD': 2, 'WIDTHEXPAND': 12, 'WIDTHTRUNC': 3}:
            raise RuntimeError('unexpected compiler warning: ' + result.stderr)
        print('COMPILE_WARNINGS', json.dumps(cls.warning_counts, sort_keys=True))
        cls.binary = cls.stage / 'obj/runtime_chorus'

    @classmethod
    def tearDownClass(cls):
        for name, expected in cls.source_hashes.items():
            if digest((ROOT / name).read_bytes()) != expected:
                raise ValueError('verified input changed during tests: ' + name)
        print('SOURCE_SHA256', json.dumps(cls.source_hashes, sort_keys=True))
        cls.temp.cleanup()

    def scenario(self, number, expected):
        result = subprocess.run([str(self.binary), f'+SCENARIO={number}'],
                                cwd=self.stage, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout)
        self.assertIn('PASS exact M12/new complete Chorus half-cycle comparisons=', result.stdout)
        print(result.stdout.strip())

    def test_48k_per_cycle_prepared_reference(self):
        self.scenario(0, 'PASS runtime Chorus48k per-cycle')

    def test_44100_fixed_point_and_complete_lfo_period(self):
        self.scenario(1, 'PASS runtime Chorus44.1 fixed point')

    def test_switches_and_history_preserve_phase_and_wet_state(self):
        self.scenario(2, 'PASS runtime Chorus switches/history preserve')

    def test_legacy_clear_cancel_at_all_pipeline_states(self):
        self.scenario(3, 'PASS runtime Chorus legacy clear aborts five FSM states')

    def test_held_configuration_and_history_priority(self):
        self.scenario(4, 'PASS runtime Chorus configuration backpressure')

    def test_exhaustive_triangle_physical_time_and_exact_lfo_average(self):
        maximum_delay_error = 0
        low, high = 10000, 0
        for triangle in range(65536):
            numerator = (480 * 65536 + triangle * 96) * 147
            delay = (numerator + 5242880) // 10485760
            error = abs(delay - numerator / 10485760)
            maximum_delay_error = max(maximum_delay_error, error)
            self.assertLessEqual(error, .5)
            self.assertLess(delay, 1024)
            low, high = min(low, delay), max(high, delay)
        self.assertEqual((low, high), (441, 529))
        increments = [(i + 1) * 349 * 160 // 147 - i * 349 * 160 // 147
                      for i in range(147)]
        self.assertEqual(set(increments), {379, 380})
        self.assertEqual(sum(increments), 349 * 160)
        self.assertEqual(349 * 48000, sum(increments) * 44100 // 147)
        print('PASS exhaustive Chorus triangle delay_error_samples=', maximum_delay_error,
              'lfo147frame_total=', sum(increments))


if __name__ == '__main__':
    unittest.main()
