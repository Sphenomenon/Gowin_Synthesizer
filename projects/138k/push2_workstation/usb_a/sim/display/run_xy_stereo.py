#!/usr/bin/env python3
"""M stereo R-L/L+R axes from real PCM, preserving the frozen M26-1 vector image."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
REFERENCE_COMMIT = '29f5a335'
REFERENCE_PATH = 'projects/138k/push2_workstation/usb_a/rtl/display_data/output_audio_analysis.v'
REFERENCE_SHA256 = '1a01118a3552507253731dcfc79df5ae3f68a378dc4dc4b5e736a1c41dc66c5d'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def raster(points):
    result = set()
    previous = None
    for x, y, active in points:
        if not active:
            previous = None
            continue
        if previous is None:
            result.add(y * 256 + x)
        else:
            x0, y0 = previous
            dx, dy = abs(x - x0), -abs(y - y0)
            sx, sy = (1 if x0 < x else -1), (1 if y0 < y else -1)
            error = dx + dy
            while True:
                result.add(y0 * 256 + x0)
                if (x0, y0) == (x, y):
                    break
                twice = 2 * error
                if twice >= dy:
                    error += dy
                    x0 += sx
                if twice <= dx:
                    error += dx
                    y0 += sy
        previous = x, y
    return result

def cases():
    full_sine = [round(24576 * math.sin(2 * math.pi * 7 * i / 2048)) for i in range(2048)]
    def pair(fn):
        return [fn(i, value) for i, value in enumerate(full_sine)]
    result = [
        ('in_phase_vertical', True, pair(lambda i, s: (s, s))),
        ('left_only_backslash', True, pair(lambda i, s: (s, 0))),
        ('right_only_slash', True, pair(lambda i, s: (0, s))),
        ('anti_phase_horizontal', True, pair(lambda i, s: (s, -s))),
        ('signed_full_scale', True, [((-32768, -32768), (-32768, 32767), (32767, -32768), (32767, 32767))[i % 4] for i in range(2048)]),
        ('signed_odd_rounding', True, [((-3, -2), (-1, 0), (0, -1), (1, 2), (3, -3), (-7, 5))[i % 6] for i in range(2048)]),
        ('small_curve', True, [(round(1536 * math.sin(2 * math.pi * 9 * i / 2048)), round(1100 * math.sin(2 * math.pi * 2 * i / 2048))) for i in range(2048)]),
        ('retained_previous_raw', False, [(round(1536 * math.sin(2 * math.pi * 2 * i / 2048 + 0.4)), round(1100 * math.sin(2 * math.pi * 13 * i / 2048 + 0.7))) for i in range(2048)]),
        ('gain_retires_history', False, [(0, 0)] * 2048),
        ('finite_history_source', True, [(24576, 15000)] * 2048),
        ('one_silent_tail', False, [(0, 0)] * 2048),
        ('second_silent_tail', False, [(0, 0)] * 2048),
        ('independent_vector_curve', False, [(round(24576 * math.sin(2 * math.pi * 7 * i / 2048)), round(18000 * math.sin(2 * math.pi * 5 * i / 2048 + 0.3))) for i in range(2048)]),
    ]
    for expected_gain, amplitude in enumerate((24576, 12000, 6000, 3000, 1500, 750, 375, 100)):
        result.append(('gain_' + str(expected_gain), True, [(round(amplitude * math.sin(2 * math.pi * 5 * i / 2048)), round(amplitude * math.cos(2 * math.pi * 3 * i / 2048))) for i in range(2048)]))
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--negative', choices=('reverse_y', 'missing_normalization', 'vector_changed', 'narrow_sum', 'logical_normalization'))
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    from tools.workstation_baselines import load_baseline
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    owner = root / 'rtl/display_data/output_audio_analysis.v'
    trace = root / 'rtl/display_data/workstation_xy_trace.sv'
    tb = Path(__file__).with_name('tb_workstation_xy_stereo.sv')
    inputs = {str(p): sha(p) for p in (owner, trace, tb, Path(__file__).resolve())}
    original = subprocess.check_output(['git', 'show', REFERENCE_COMMIT + ':' + REFERENCE_PATH], cwd=root.parents[3])
    assert hashlib.sha256(original).hexdigest() == REFERENCE_SHA256
    frozen = out / 'reference.v'
    frozen.write_text(original.decode().replace('output_audio_analysis', 'reference_output_audio_analysis').replace('gw138k_spectrum_column_rom', 'reference_spectrum_column_rom'))
    sources = []
    for source in (owner, trace, tb):
        target = out / source.name
        target.write_bytes(source.read_bytes())
        sources.append(target)
    if args.negative:
        target = sources[0]
        text = target.read_text()
        before, after = {
            'reverse_y': ("18'sd128-($signed(plot_mid) >>> image_shift)", "18'sd128+($signed(plot_mid) >>> image_shift)"),
            'missing_normalization': ('plot_mid<=mid_sum >>> 1;', 'plot_mid<=mid_sum;'),
            'vector_changed': ('XY_STEREO_ENABLE && !vector_xy_i', 'XY_STEREO_ENABLE'),
            'narrow_sum': ('wire signed [16:0] mid_sum=', 'wire signed [15:0] mid_sum='),
            'logical_normalization': ('plot_mid<=mid_sum >>> 1;', 'plot_mid<=mid_sum >> 1;'),
        }[args.negative]
        assert text.count(before) == 1
        target.write_text(text.replace(before, after))
    baseline = load_baseline(root, 'resource_rework_route0')
    for name in ('output_audio_capture.v', 'audio_analysis_rom.v'):
        target = out / name
        target.write_bytes(baseline.read_bytes('src/video/' + name))
        sources.append(target)
    sources.append(frozen)
    frames = cases()
    samples, direct_expected, stereo_expected, peaks, gains, resets, coverage = [], [], [], [], [], [], []
    histories, last_gain = [set(), set()], None
    for frame, (name, reset, values) in enumerate(frames):
        left_peak, right_peak = max(abs(l) for l, r in values), max(abs(r) for l, r in values)
        peak, gain = max(left_peak, right_peak), 0
        for bit in range(7):
            if peak and peak < (16384 >> bit):
                gain = bit + 1
        direct_points, stereo_points = [], []
        for left, right in values:
            direct_points.append((max(0, min(255, 128 + (left >> (9 - gain)))), max(0, min(255, 128 - (right >> (9 - gain)))), bool(left or right)))
            # Python integers model mathematical signed extension first. Floor
            # division is the arithmetic shift used for common /2 normalization.
            side, mid = (right - left) // 2, (left + right) // 2
            stereo_points.append((max(0, min(255, 128 + (side >> (9 - gain)))), max(0, min(255, 128 - (mid >> (9 - gain)))), bool(left or right)))
        if name == 'in_phase_vertical':
            assert len({x for x, y, active in stereo_points if active}) == 1
        if name == 'left_only_backslash':
            assert all(abs((x - 128) - (y - 128)) <= 1 for x, y, active in stereo_points)
        if name == 'right_only_slash':
            assert all(abs((x - 128) + (y - 128)) <= 1 for x, y, active in stereo_points)
        if name == 'anti_phase_horizontal':
            assert len({y for x, y, active in stereo_points if active}) == 1
        raw = [raster(direct_points), raster(stereo_points)]
        images = [current | old if last_gain == gain and not reset else current for current, old in zip(raw, histories)]
        direct_expected.extend(int(i in images[0]) for i in range(65536))
        stereo_expected.extend(int(i in images[1]) for i in range(65536))
        samples.extend(((l & 65535) << 16) | (r & 65535) for l, r in values)
        peaks.append((left_peak << 16) | right_peak)
        gains.append(gain)
        resets.append(int(reset))
        coverage.append(dict(frame=frame, name=name, reset=reset, gain=gain, direct_pixels=len(images[0]), stereo_pixels=len(images[1]), raw_direct_pixels=len(raw[0]), raw_stereo_pixels=len(raw[1])))
        histories, last_gain = raw, gain
    assert set(gains) == set(range(8))
    assert coverage[10]['stereo_pixels'] > 0 and coverage[11]['stereo_pixels'] == 0
    for name, values, width in [('samples', samples, 8), ('direct', direct_expected, 1), ('stereo', stereo_expected, 1), ('peaks', peaks, 8), ('gains', gains, 1), ('resets', resets, 1)]:
        (out / (name + '.mem')).write_text(''.join(format(value, '0' + str(width) + 'x') + '\n' for value in values))
    execution = {str(p): sha(p) for p in [*sources, *out.glob('*.mem')]}
    report = dict(schema=1, passed=False, scope='Four complete 2048-point stereo FFT/XY instances with independent pixel oracle; frozen M26-1 direct preservation, signed widened sum/difference, equal normalization, screen orientation, all gains, continuous trace, finite history, immutable front, stalled reads', input_sha256=inputs, execution_sha256=execution, reference_git=REFERENCE_COMMIT + ':' + REFERENCE_PATH, reference_sha256=REFERENCE_SHA256, coverage=coverage, negative_control=args.negative, baseline=baseline.evidence(), hardware_tested=False, synthesized=False, placed_routed=False)
    try:
        argv = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal', '--top-module', 'tb_workstation_xy_stereo', '--Mdir', str(out / 'obj'), '-GFRAMES=' + str(len(frames)), *map(str, sources)]
        report['compile_argv'] = argv
        with (out / 'compile.log').open('w') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        warnings = re.findall(r'^%Warning-([^:]+): (.*)', (out / 'compile.log').read_text(), re.M)
        report['warnings'] = warnings
        assert not any(kind == 'UNOPTFLAT' for kind, message in warnings), 'combinational loop'
        assert not any('/tb_workstation_xy_stereo.sv:' in message and kind != 'TIMESCALEMOD' for kind, message in warnings), 'new fixture warning'
        with (out / 'run.log').open('w') as log:
            run = subprocess.run([str(out / 'obj/Vtb_workstation_xy_stereo')], cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        log = (out / 'run.log').read_text()
        print(log, end='')
        if args.negative:
            assert run.returncode != 0 and ('stereo bitmap mismatch' in log or 'stereo vector/default cycle mismatch' in log)
            report['negative_control_rejected'] = True
        else:
            assert run.returncode == 0, log[-3000:]
            match = re.search(r'PASS xy_stereo frames=(\d+) vector_default_cycles=(\d+) pixels=(\d+) stereo_fft_columns=(\d+) stalls=(\d+)', log)
            assert match
            report['metrics'] = dict(zip(('frames', 'vector_default_cycle_checks', 'pixel_checks', 'stereo_fft_column_checks', 'stalled_reads'), map(int, match.groups())))
        assert all(sha(path) == expected for path, expected in inputs.items())
        assert all(sha(path) == expected for path, expected in execution.items())
        report['passed'] = True
    finally:
        report['logs'] = {path.name: sha(path) for path in (out / 'compile.log', out / 'run.log') if path.exists()}
        (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')

if __name__ == '__main__':
    main()
