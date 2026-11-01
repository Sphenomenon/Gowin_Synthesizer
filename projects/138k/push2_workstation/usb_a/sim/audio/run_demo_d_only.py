#!/usr/bin/env python3
"""Check D-only native effects and retirement while preserving FFT/context.

The prepared project supplies versioned reconstructed support/ROM inputs. Every
selected control/delay source is replaced by the maintained source under test;
no historical build output or synthesized result becomes a production input.
This is offline functional evidence, not physical audio or board acceptance.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

from run_runtime_controlled import runtime_sources

ROOT = Path(__file__).resolve().parents[2]


def spectral_peak(samples, fs, expected_hz, dry_hz):
    """Independent final-output FFT; no internal Pitch signal is a reference."""
    n = len(samples)
    assert n == 8192
    values = [complex(x * (0.5-0.5*math.cos(2*math.pi*i/(n-1)))) for i, x in enumerate(samples)]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            values[i], values[j] = values[j], values[i]
    length = 2
    while length <= n:
        step = complex(math.cos(-2*math.pi/length), math.sin(-2*math.pi/length))
        for start in range(0, n, length):
            w = 1+0j
            for k in range(start, start+length//2):
                a, b = values[k], values[k+length//2]*w
                values[k], values[k+length//2] = a+b, a-b
                w *= step
        length *= 2
    selected = range(math.ceil(600*n/fs), math.floor(1800*n/fs))
    peak = max(selected, key=lambda k: abs(values[k]))
    measured = peak*fs/n
    dry = max(abs(values[k]) for k in range(round(dry_hz*n/fs)-1, round(dry_hz*n/fs)+2))
    ratio = abs(values[peak])/max(1.0, dry)
    assert abs(measured-expected_hz) < 12.0 and ratio > 5.0, ('final-output Pitch spectral mismatch', measured, expected_hz, ratio)
    return dict(expected_hz=expected_hz, measured_peak_hz=measured, shifted_to_dry_magnitude_ratio=ratio)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--event-variant', type=Path, help='Explicit test-only complete event source outside the production tree')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = []
    for path in runtime_sources(project, ROOT / 'sim/audio/tb_workstation_demo_d_only.sv'):
        if path.is_relative_to(project):
            relative = path.relative_to(project)
            if relative.parts[:2] == ('rtl', 'control') or relative.parts[:3] == ('rtl', 'audio', 'delay_ddr'):
                path = ROOT / relative
        if path not in selected:
            selected.append(path)
    if args.event_variant:
        variant = args.event_variant.resolve()
        assert variant.is_file() and not variant.is_relative_to(ROOT), 'test variant must stay outside production inputs'
        selected = [variant if path == ROOT/'rtl/audio/gw138k_event_workstation.sv' else path for path in selected]
    memory_reference = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
    memory_text = memory_reference.read_text()
    anchor = '\nmodule tb_workstation_runtime_effects;'
    if memory_text.count(anchor) != 1:
        raise ValueError('ordered DDR model extraction anchor drift')
    memory = output / 'ordered_posted_ddr_model.sv'
    memory.write_text(memory_text.split(anchor)[0])
    selected.append(memory)
    retired = [project / 'legacy/rtl/audio/audio_math_pkg.sv',
               project / 'legacy/rtl/audio/spectrum_fft256.sv']
    retired += [ROOT / path for path in ('rtl/services/workstation_controlled_services.sv',
        'rtl/audio/workstation_observation_consumers.sv', 'rtl/memory/workstation_sdp.sv',
        'sim/audio/tb_workstation_demo_retirement.sv')]
    inputs = list(dict.fromkeys(selected + retired + [Path(__file__).resolve(), memory_reference,
        ROOT / 'sim/audio/fixtures/d_process_before_exact_mask.svh']))
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    report = dict(passed=False, hardware_tested=False, synthesis_tested=False,
                  scope='D-only native render/effects/ordered-DDR and retired local REC/cue; true FFT/context retained',
                  limits='Synthetic decoder PCM fixture tests functional DSP only; no A2DP, physical I2S/HDMI, P&R or hardware acceptance',
                  test_only_event_variant=str(args.event_variant.resolve()) if args.event_variant else None,
                  input_sha256={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
                  stages=[])
    try:
        stages = [
            ('render_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                '--top-module', 'tb_workstation_demo_d_only', '--Mdir', str(output / 'obj'),
                '-I' + str(ROOT), '-I' + str(project), *map(str, selected)]),
            ('render_run', [str(output / 'obj/Vtb_workstation_demo_d_only'), '+PITCH_PCM='+str(output/'pitch-final-output.txt')]),
            ('retirement_compile', ['iverilog', '-g2012', '-s', 'tb_workstation_demo_retirement',
                '-o', str(output / 'retirement.vvp'), *map(str, retired)]),
            ('retirement_run', ['vvp', str(output / 'retirement.vvp')]),
        ]
        for name, command in stages:
            log = output / (name + '.log')
            with log.open('w') as stream:
                process = subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
            report['stages'].append(dict(name=name, argv=command, exit_code=process.returncode, log=str(log)))
            process.check_returncode()
            contents = log.read_text()
            if '%Error' in contents or 'ERROR:' in contents or 'FATAL:' in contents or 'UNOPTFLAT' in contents:
                raise ValueError('error or combinational admission loop: ' + name)
            if name.endswith('_run'):
                passes = [line for line in contents.splitlines() if line.startswith('PASS ')]
                if len(passes) != 1:
                    raise ValueError('missing unique functional result: ' + name)
                report['stages'][-1]['result'] = passes[0]
                print(passes[0])
        captures = {(rate, down): [[], []] for rate, down in ((0,0),(1,1))}
        for line in (output/'pitch-final-output.txt').read_text().splitlines():
            rate, down, index, left, right = map(int, line.split())
            channels = captures[(rate, down)]
            assert index == len(channels[0])
            channels[0].append(left);channels[1].append(right)
        bends = [int(x,16) for x in (project/'sim/data/audio_chain/pitch_bend_q20.mem').read_text().splitlines()]
        report['final_output_spectral_evidence'] = []
        for (rate, down), channels in captures.items():
            fs = 44100 if rate else 48000
            ratio = bends[0 if down else 255]/1048576
            report['final_output_spectral_evidence'].append(dict(rate_hz=fs, pitch_ratio=ratio,
                channels=[spectral_peak(samples,fs,freq*ratio,freq) for samples,freq in zip(channels,(997,1451))]))
        report['final_output_capture_sha256'] = hashlib.sha256((output/'pitch-final-output.txt').read_bytes()).hexdigest()
        assert report['input_sha256'] == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}, 'consumed D/Pitch input changed during execution'
        report['all_consumed_inputs_unchanged'] = True
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
