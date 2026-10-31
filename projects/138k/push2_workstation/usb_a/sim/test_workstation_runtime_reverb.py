#!/usr/bin/env python3
"""Prepared48k cycle equivalence and independent fixed-point dual-rate Reverb."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline
from workstation_reverb_provenance import verify as verify_reverb, restore as restore_reverb, ADAPTATION


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sat(value):
    return min(2147483647, max(-2147483648, value))


def signed(value):
    return value - (1 << 32) if value & (1 << 31) else value


class FixedRoom:
    """Frame-domain integer model; no RTL states, RAM banking or timing copied."""
    def __init__(self, banks):
        self.banks = banks
        self.rate = '48000'
        self.gain = self.fraction = 0
        self.clear()

    def clear(self, legacy=False, rate=None):
        if rate is not None:
            self.rate = rate
        if legacy:
            self.gain = self.fraction = 0
        self.bank = self.banks[self.rate]
        self.lengths = self.bank['fdn_lengths']
        self.lines = [[0] * length for length in self.lengths]
        self.pointers = [0] * 4
        self.damping = [0] * 4
        self.early = [0] * 2048
        self.early_pointer = self.frames = 0

    def frame(self, left, right, enable):
        increment = 128
        if self.rate == '44100':
            self.fraction += 47
            increment = 139 + (self.fraction >= 147)
            self.fraction %= 147
        target = 8192 if enable else 0
        self.gain = min(target, self.gain + increment) if target > self.gain else max(target, self.gain - increment)
        tail = [self.lines[i][self.pointers[i]] if self.frames >= self.lengths[i] else 0 for i in range(4)]
        alpha = self.bank['damping']['old_q31']
        beta = self.bank['damping']['input_q31']
        self.damping = [sat((old * alpha + value * beta) // (1 << 31))
                        for old, value in zip(self.damping, tail)]
        a, b, c, d = self.damping
        hadamard = [(a + b + c + d) // 2, (a - b + c - d) // 2,
                    (a + b - c - d) // 2, (a - b - c + d) // 2]
        mono = (left + right) // 2
        feedback = [mono // 8 + value - value // 8 for value in hadamard]
        early = [0, 0]
        for tap in self.bank['taps']:
            value = self.early[(self.early_pointer - tap['delay']) % 2048] if self.frames >= tap['delay'] else 0
            early[tap['ear']] += value * tap['gain_q15'] // 32768
        a, b, c, d = tail
        wet = [sat(early[0] + (a + b - c - d) // 4),
               sat(early[1] + (a - b + c - d) // 4)]
        mixed = [left + wet[0] * self.gain // 32768,
                 right + wet[1] * self.gain // 32768]
        clip = any(value != sat(value) for value in feedback + mixed)
        for i, value in enumerate(feedback):
            self.lines[i][self.pointers[i]] = sat(value)
            self.pointers[i] = (self.pointers[i] + 1) % self.lengths[i]
        self.early[self.early_pointer] = mono
        self.early_pointer = (self.early_pointer + 1) % 2048
        self.frames += 1
        return sat(mixed[0]), sat(mixed[1]), int(clip)


def impulse_metrics(pcm, sample_rate):
    energy = [float(left * left + right * right) for left, right in pcm]
    reverse = [0.] * len(energy)
    total = 0.
    for i in range(len(energy) - 1, -1, -1):
        total += energy[i]
        reverse[i] = total
    # Exclude dry/early reflections and use the same physical tail start.
    start = math.ceil(.03 * sample_rate)
    normal = reverse[start]
    points = [(i / sample_rate, 10 * math.log10(value / normal))
              for i, value in enumerate(reverse) if i >= start and value > 0]
    fit = [(t, db) for t, db in points if -25 <= db <= -5]
    slope, intercept = statistics.linear_regression([p[0] for p in fit], [p[1] for p in fit])
    quiet = pcm[-sample_rate // 4:]
    return dict(scope='Fixed-point RTL-matched full wet response after30ms;not measured acoustic RT60.',
                t20_extrapolated_rt60_seconds=-60 / slope, fit_points=len(fit),
                impulse_frames=len(pcm), sample_rate=sample_rate,
                final_quarter_second_peak_lsb=max(abs(v) for pair in quiet for v in pair),
                final_quarter_second_energy=sum(l * l + r * r for l, r in quiet),
                final_sample=list(pcm[-1]), fit_slope_db_per_second=slope,
                first_wet_frame=next(i for i, pair in enumerate(pcm) if i > 0 and any(pair)),
                fit_intercept_db=intercept)


class RuntimeReverbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('verilator'):
            raise RuntimeError('Verilator is required for banked RAM RTL verification')
        cls.temp = tempfile.TemporaryDirectory(prefix='runtime-reverb-')
        cls.stage = Path(cls.temp.name)
        native = ROOT / 'rtl/audio/workstation_runtime_spatial_reverb.sv'
        provenance_path = native.with_suffix('.provenance.json')
        provenance = json.loads(provenance_path.read_text())
        payload = native.read_bytes()
        adaptation_path = ROOT / ADAPTATION
        restored, cls.reverb_provenance_evidence = verify_reverb(
            payload, provenance_path.read_bytes(), adaptation_path.read_bytes())
        scratch = restore_reverb(payload, provenance_path.read_bytes(), adaptation_path.read_bytes(), scratch=True)
        scratch_reference = cls.stage / 'scratch_reference_spatial_reverb.sv'
        scratch_reference.write_bytes(scratch.replace(b'module workstation_runtime_spatial_reverb (',
                                                       b'module scratch_reference_spatial_reverb ('))
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        if baseline.read_bytes('rtl/audio/serial_spatial_reverb.sv') != restored.encode():
            raise ValueError('prepared Reverb does not match versioned baseline')
        dependencies = {
            'legacy/rtl/audio/audio_math_pkg.sv': 'f07fab099e112b18d9fc142eeb701139cae62be79e2f25596e134aaecea88f3d',
            'rtl/audio/serial_spatial_reverb.sv': provenance['prepared_sha256'],
            'rtl/audio/spatial_room_preset.svh': '1eb6d0f0ab0b9ff2b6013dfed034e0eb593f23302e441932193883343c6b33d4',
            'rtl/memory/workstation_sdp.sv': '2e804a142f941b63a31d41b13f9238f540d1fc758c90f1098af020530d4d72ec',
            'rtl/memory/workstation_sdp_banked.sv': 'edefe1108cdae09cffa7f55edffa69055bcebf8e556203a2f55571d531df553c',
        }
        sources = []
        for name, expected in dependencies.items():
            data = baseline.read_bytes(name)
            if digest(data) != expected:
                raise ValueError('prepared test dependency drifted: ' + name)
            path = cls.stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if path.suffix == '.sv':
                sources.append(path)
        bank_path = ROOT / 'rtl/audio/runtime_spatial_room_preset.json'
        header = ROOT / 'rtl/audio/runtime_spatial_room_preset.svh'
        target = cls.stage / 'rtl/audio/runtime_spatial_room_preset.svh'
        target.write_bytes(header.read_bytes())
        cls.banks = json.loads(bank_path.read_text())['banks']
        tb = ROOT / 'sim/audio/tb_workstation_runtime_reverb.sv'
        cls.source_hashes = {str(path.relative_to(ROOT)): digest(path.read_bytes())
                             for path in (native, provenance_path, adaptation_path,
                                          ROOT / 'tools/workstation_reverb_provenance.py',
                                          bank_path, header, tb, Path(__file__))}
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_reverb',
                   '--Mdir', str(cls.stage / 'obj'), '-o', 'runtime_reverb',
                   '-DRUNTIME_REVERB_SCRATCH_REFERENCE',
                   *map(str, sources), str(native), str(scratch_reference), str(tb)]
        result = subprocess.run(command, cwd=cls.stage, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout[-3000:] + result.stderr[-16000:])
        cls.warning_counts = {}
        for line in result.stderr.splitlines():
            if line.startswith('%Warning-'):
                name = line.split(':', 1)[0][9:]
                cls.warning_counts[name] = cls.warning_counts.get(name, 0) + 1
        if cls.warning_counts != {'TIMESCALEMOD': 1, 'WIDTHEXPAND': 26, 'WIDTHTRUNC': 8}:
            raise RuntimeError('unexpected compile warnings: ' + result.stderr)
        if any(str(native) + ':' in line for line in result.stderr.splitlines()
               if line.startswith('%Warning-')):
            raise RuntimeError('maintained Reverb must compile without width warnings')
        # Exact frozen prepared/scratch references and banked RAM indexing;
        # maintained Reverb has explicit widths and no compile warnings.
        print('COMPILE_WARNINGS', json.dumps(cls.warning_counts, sort_keys=True))
        cls.compile_warnings = result.stderr
        cls.binary = cls.stage / 'obj/runtime_reverb'
        cls.metrics = {}

    @classmethod
    def tearDownClass(cls):
        for name, expected in cls.source_hashes.items():
            if digest((ROOT / name).read_bytes()) != expected:
                raise ValueError('verified input changed during tests: ' + name)
        print('SOURCE_SHA256', json.dumps(cls.source_hashes, sort_keys=True))
        print('IMPULSE_METRICS', json.dumps(cls.metrics, sort_keys=True))
        if set(cls.metrics) == {'48000', '44100'}:
            ratio = cls.metrics['44100']['t20_extrapolated_rt60_seconds'] / cls.metrics['48000']['t20_extrapolated_rt60_seconds']
            if abs(ratio - 1) > .02:
                raise ValueError('dual-rate fixed-point tail decay differs by more than2percent')
            print('PASS fixed-point tail RT60 relative difference=', ratio - 1)
        cls.temp.cleanup()

    def fixture(self, scenario, records):
        path = self.stage / f'vectors{scenario}.txt'
        model = FixedRoom(self.banks)
        pcm = []
        with path.open('w') as stream:
            stream.write(str(len(records)) + '\n')
            for operation, left, right, enable in records:
                if operation == 0:
                    result = model.frame(left, right, enable)
                    pcm.append(result[:2])
                else:
                    model.clear(legacy=operation == 4,
                                rate='44100' if operation == 1 else '48000' if operation == 2 else None)
                    result = (0, 0, 0)
                stream.write(f'{operation} {left & 0xffffffff:08x} {right & 0xffffffff:08x} {enable} '
                             f'{result[0] & 0xffffffff:08x} {result[1] & 0xffffffff:08x} {result[2]}\n')
        return path, pcm

    def scenario(self, number, vector_file=None, expected='PASS runtime Reverb model'):
        command = [str(self.binary), f'+SCENARIO={number}']
        if vector_file:
            command.append('+VECTOR_FILE=' + str(vector_file))
        result = subprocess.run(command, cwd=self.stage, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout)
        print(result.stdout.strip())

    @staticmethod
    def random_records(count, seed=0x17b93a4f):
        records = []
        state = seed
        for _ in range(count):
            state = (state >> 1) ^ (0x80200003 if state & 1 else 0)
            left = signed(state)
            state = (state >> 1) ^ (0x80200003 if state & 1 else 0)
            records.append((0, left, signed(state), (state >> 7) & 1))
        return records

    def test_48k_per_cycle_and_independent_integer_reference(self):
        records = self.random_records(15000)
        records += [(4, 0, 0, 0)] + self.random_records(15000, 0x698a125b)
        path, _ = self.fixture(0, records)
        self.scenario(0, path)

    def test_44100_three_second_impulse_fixed_point(self):
        rate = 44100
        records = [(1, 0, 0, 0), (0, 1 << 28, 1 << 28, 1)] + [(0, 0, 0, 1)] * (3 * rate - 1)
        path, pcm = self.fixture(1, records)
        self.scenario(1, path)
        metrics = impulse_metrics(pcm, rate)
        self.assertLess(metrics['final_quarter_second_peak_lsb'], 65536)
        self.assertEqual(metrics['first_wet_frame'], min(t['delay'] for t in self.banks[str(rate)]['taps']))
        self.metrics['44100'] = metrics

    def test_48k_three_second_impulse_fixed_point(self):
        rate = 48000
        records = [(0, 1 << 28, 1 << 28, 1)] + [(0, 0, 0, 1)] * (3 * rate - 1)
        path, pcm = self.fixture(2, records)
        self.scenario(2, path)
        metrics = impulse_metrics(pcm, rate)
        self.assertLess(metrics['final_quarter_second_peak_lsb'], 65536)
        self.assertEqual(metrics['first_wet_frame'], min(t['delay'] for t in self.banks[str(rate)]['taps']))
        self.metrics['48000'] = metrics

    def test_switches_history_and_gain_remainder(self):
        records = self.random_records(3000)
        for operation in (1, 3, 2, 1, 4):
            records += [(operation, 0, 0, 0)] + self.random_records(3000, 0x15baf345)
        path, _ = self.fixture(3, records)
        self.scenario(3, path)

    def test_clear_cancel_at_ram_and_pipeline_boundaries(self):
        self.scenario(4, expected='PASS runtime Reverb clear cancellation16')

    def test_config_backpressure_includes_ram_write_tail(self):
        self.scenario(5, expected='PASS runtime Reverb config backpressure')


if __name__ == '__main__':
    unittest.main()
