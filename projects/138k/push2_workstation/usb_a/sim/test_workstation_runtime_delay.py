#!/usr/bin/env python3
"""Offline runtime Delay: exact48k,44.1 fixed point,CDC barriers and faults.

All reference inputs reconstruct from versioned baselines or reversible native
provenance. No historical results directory or local prepared tree is needed.
"""
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


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class RuntimeDelayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('verilator'):
            raise RuntimeError('Verilator is required for parameter-string FIFO RTL')
        cls.temp = tempfile.TemporaryDirectory(prefix='runtime-delay-')
        cls.stage = Path(cls.temp.name)
        cls.source_hashes = {}
        natives = []
        for name in ('workstation_runtime_delay_effect_ddr', 'workstation_runtime_delay_ddr_dma'):
            native = ROOT / 'rtl/audio/delay_ddr' / (name + '.sv')
            provenance_path = native.with_suffix('.provenance.json')
            provenance = json.loads(provenance_path.read_text())
            payload = native.read_bytes()
            if sha256(payload) != provenance['native_sha256']:
                raise ValueError('native source identity drifted: ' + name)
            restored = payload.decode()
            for edit in reversed(provenance['forward_edits']):
                if restored.count(edit['after']) != edit['count']:
                    raise ValueError('reverse provenance anchor drifted: ' + name)
                restored = restored.replace(edit['after'], edit['before'])
            if sha256(restored.encode()) != provenance['prepared_sha256']:
                raise ValueError('source does not reverse to exact prepared bytes: ' + name)
            for path in (native, provenance_path):
                cls.source_hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes())
            natives.append(native)
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        math_pkg = baseline.read_bytes('legacy/rtl/audio/audio_math_pkg.sv')
        if sha256(math_pkg) != 'f07fab099e112b18d9fc142eeb701139cae62be79e2f25596e134aaecea88f3d':
            raise ValueError('exact prepared math package drifted')
        math_path = cls.stage / 'audio_math_pkg.sv'
        math_path.write_bytes(math_pkg)
        effects = baseline.read_bytes('legacy/rtl/audio/stereo_effects.sv').decode()
        start = effects.index('module serial_delay_effect')
        end = effects.index('endmodule', start) + len('endmodule')
        reference = effects[start:end]
        # This exact module matches actual F02 rev2 prepared legacy_audio input.
        if sha256(reference.encode()) != '8e9ec829f87fbe31b4979d219939b20cdc72b8af7772e4c2601ff15c4e95ffac':
            raise ValueError('prepared BRAM delay reference drifted')
        reference_path = cls.stage / 'serial_delay_effect.sv'
        reference_path.write_text(reference)
        fifo = ROOT / 'rtl/music/music_async_fifo.sv'
        if sha256(fifo.read_bytes()) != 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792':
            raise ValueError('actual F02 prepared FIFO implementation drifted')
        tb = ROOT / 'sim/audio/tb_workstation_runtime_delay.sv'
        for path in (fifo, tb, Path(__file__)):
            cls.source_hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes())
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_delay',
                   '--Mdir', str(cls.stage / 'obj'), '-o', 'runtime_delay',
                   str(math_path), str(reference_path), str(fifo), *map(str, natives), str(tb)]
        result = subprocess.run(command, capture_output=True, text=True, cwd=cls.stage, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout[-3000:] + result.stderr[-16000:])
        cls.compile_warning_counts = {}
        for line in result.stderr.splitlines():
            if line.startswith('%Warning-'):
                name = line.split(':', 1)[0][9:]
                cls.compile_warning_counts[name] = cls.compile_warning_counts.get(name, 0) + 1
        if cls.compile_warning_counts != {'TIMESCALEMOD': 2, 'WIDTHEXPAND': 16}:
            raise RuntimeError('unexpected compile warnings: ' + result.stderr)
        # Sign widening and missing package timescale are inherited prepared
        # arithmetic; the per-clock reference checks their preserved behavior.
        print('COMPILE_WARNINGS', json.dumps(cls.compile_warning_counts, sort_keys=True))
        cls.binary = cls.stage / 'obj/runtime_delay'

    @classmethod
    def tearDownClass(cls):
        for name, expected in cls.source_hashes.items():
            if sha256((ROOT / name).read_bytes()) != expected:
                raise ValueError('verified input changed during tests: ' + name)
        print('SOURCE_SHA256', json.dumps(cls.source_hashes, sort_keys=True))
        cls.temp.cleanup()

    def scenario(self, number, message):
        result = subprocess.run([str(self.binary), f'+SCENARIO={number}'],
                                cwd=self.stage, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)
        print(result.stdout.strip())

    def test_48k_per_cycle_reference_with_clear_and_ring_wrap(self):
        self.scenario(0, 'PASS runtime delay 48k per-cycle')

    def test_44100_independent_fixed_point_echo_feedback_slew(self):
        self.scenario(1, 'PASS runtime delay 44.1 independent fixed-point')

    def test_old_read_posted_write_fence_then_matching_audio_ack(self):
        self.scenario(2, 'PASS runtime delay drain+ordered fence')

    def test_missing_late_fence_timeout_does_not_ack(self):
        self.scenario(3, 'PASS runtime delay missing/late fence timeout')

    def test_memory_clock_stopped_detected_by_audio(self):
        self.scenario(4, 'PASS runtime delay memory-clock stop')

    def test_audio_clock_stopped_detected_by_memory(self):
        self.scenario(5, 'PASS runtime delay audio-clock stop')

    def test_stale_wrong_transaction_ack_rejected(self):
        self.scenario(6, 'PASS runtime delay wrong/stale marker rejected')

    def test_reserved_transaction_payload_rejected(self):
        self.scenario(7, 'PASS runtime delay reserved marker payload rejected')

    def test_ddr_stall_faults_observable_stream_not_blocked(self):
        self.scenario(8, 'PASS runtime delay sustained DDR stall')

    def test_read_burst_preempt_and_ack_fifo_backpressure(self):
        self.scenario(9, 'PASS runtime delay preempts old read burst')

    def test_old_pcm_backlog_cannot_overtake_pending_read_fence(self):
        self.scenario(10, 'PASS runtime delay old PCM FIFO backlog drains')

    def test_legacy_clear_aborts_every_pipeline_state_and_coalesces(self):
        self.scenario(11, 'PASS runtime delay legacy clear aborts five FSM states')

    def test_config_backpressure_and_history_priority(self):
        self.scenario(12, 'PASS runtime delay held config backpressure')


if __name__ == '__main__':
    unittest.main()
