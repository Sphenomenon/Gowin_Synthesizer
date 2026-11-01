#!/usr/bin/env python3
"""Actual M stereo held-frame CDC, whole-window mode revocation and recovery."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative', choices=('separate_vector', 'no_mode_revoke'))
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT))
    from tools.workstation_baselines import load_baseline
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    tb = Path(__file__).with_name('tb_workstation_xy_stereo_context.sv')
    maintained = [ROOT / 'rtl/display_data_layout_pkg.svh'] + [ROOT / ('rtl/display_data/' + name) for name in ('output_audio_analysis.v', 'workstation_xy_trace.sv', 'display_data_analysis_source.sv', 'workstation_display_runtime.sv', 'feedback_capture.v', 'display_data_writer.v', 'display_data_reader.v')]
    maintained += [ROOT / 'rtl/migration/workstation_runtime_counter_cdc.sv', tb, Path(__file__).resolve()]
    address_map = ROOT / 'rtl/ddr_address_map.vh'
    inputs = {str(path): sha(path) for path in maintained + [address_map]}
    staged_map = out / 'src/memory/ddr_address_map.vh'
    staged_map.parent.mkdir(parents=True)
    staged_map.write_bytes(address_map.read_bytes())
    sources = []
    for path in maintained[:-1]:
        target = out / path.name
        target.write_bytes(path.read_bytes())
        sources.append(target)
    for relative in ('src/video/output_audio_capture.v', 'src/video/audio_analysis_rom.v', 'src/video/feedback_wave_align.v', 'src/migration/gw138k_stream_cdc.sv'):
        target = out / Path(relative).name
        target.write_bytes(baseline.read_bytes(relative))
        sources.append(target)
    if args.negative:
        target = out / ('workstation_display_runtime.sv' if args.negative == 'separate_vector' else 'display_data_analysis_source.sv')
        text = target.read_text()
        before, after = (('assign tuple_vector=destination_tuple[204];', 'assign tuple_vector=frame_vector_i;') if args.negative == 'separate_vector' else ('(XY_STEREO_ENABLE && vector_xy_i!=vector_xy_q)', "1'b0"))
        assert text.count(before) == 1
        target.write_text(text.replace(before, after))
    execution = {str(path): sha(path) for path in sources + [staged_map]}
    report = dict(schema=1, passed=False, scope='Actual maintained runtime/205-bit CDC and producer with real analysis; completed raw history and partial PCM window revocation, normal/vector transition recovery, source tuple scoreboard', input_sha256=inputs, execution_sha256=execution, baseline=baseline.evidence(), negative_control=args.negative, hardware_tested=False, synthesized=False, placed_routed=False)
    try:
        argv = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal', '--top-module', 'tb_workstation_xy_stereo_context', '--Mdir', str(out / 'obj'), *map(str, sources)]
        report['compile_argv'] = argv
        with (out / 'compile.log').open('w') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        warnings = re.findall(r'^%Warning-([^:]+): (.*)', (out / 'compile.log').read_text(), re.M)
        report['warnings'] = warnings
        assert not any(kind == 'UNOPTFLAT' for kind, message in warnings)
        assert not any('/tb_workstation_xy_stereo_context.sv:' in message and kind != 'TIMESCALEMOD' for kind, message in warnings), 'new fixture warning'
        with (out / 'run.log').open('w') as log:
            result = subprocess.run([str(out / 'obj/Vtb_workstation_xy_stereo_context')], cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        log = (out / 'run.log').read_text()
        print(log, end='')
        if args.negative:
            assert result.returncode != 0 and ('stereo mode change admitted' in log or 'stereo 205bit tuple torn' in log or 'stereo completed window/history survived' in log or 'stereo partial vector block survived' in log)
            report['negative_control_rejected'] = True
        else:
            assert result.returncode == 0, log[-3000:]
            match = re.search(r'PASS xy_stereo_context tuples=(\d+) mode_revocations=(\d+) points=(\d+)', log)
            assert match
            report['metrics'] = dict(zip(('atomic_tuples', 'mode_revocations', 'actual_producer_points'), map(int, match.groups())))
        assert all(sha(path) == expected for path, expected in inputs.items())
        assert all(sha(path) == expected for path, expected in execution.items())
        report['passed'] = True
    finally:
        report['logs'] = {path.name: sha(path) for path in (out / 'compile.log', out / 'run.log') if path.exists()}
        (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')

if __name__ == '__main__':
    main()
