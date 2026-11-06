#!/usr/bin/env python3
"""Bounded asynchronous effects source test; no LCD wire or board acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if not shutil.which('verilator'):
        raise RuntimeError('Verilator is required')
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    math_path = output / 'audio_math_pkg.sv'
    math_path.write_bytes(baseline.read_bytes('legacy/rtl/audio/audio_math_pkg.sv'))
    common = [ROOT / name for name in (
        'rtl/audio/workstation_remote_effect_stream_m.sv',
        'rtl/audio/workstation_remote_effect_stream_w.sv')]
    engine_sources = [ROOT / name for name in (
        'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
        'rtl/music/music_async_fifo.sv', 'rtl/audio/workstation_runtime_spatial_reverb.sv')]
    header = ROOT / 'rtl/audio/runtime_spatial_room_preset.svh'
    bench = ROOT / 'sim/audio/tb_remote_effect_stream_async.sv'
    boundary = ROOT / 'sim/audio/tb_remote_effect_stream_boundaries.sv'
    paths = common + engine_sources + [header, bench, boundary, Path(__file__)]
    locked = {str(path.relative_to(ROOT)): sha(path) for path in paths}
    commands = []
    for module, source in zip(('workstation_remote_effect_stream_m', 'workstation_remote_effect_stream_w'), common):
        command = ['verilator', '--lint-only', '-Wall', '--top-module', module, str(source)]
        commands.append(command)
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / (module + '.lint.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('strict lint failed: ' + result.stderr)
    command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
               '--top-module', 'tb_remote_effect_stream_async', '--Mdir', str(output / 'obj'),
               '-o', 'remote_effect_stream', '-I' + str(ROOT), str(math_path),
               *map(str, common + engine_sources + [bench])]
    commands.append(command)
    built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
    (output / 'compile.stdout').write_text(built.stdout)
    (output / 'compile.stderr').write_text(built.stderr)
    if built.returncode:
        raise RuntimeError('compile failed: ' + built.stderr[-8000:])
    warnings = [line for line in built.stderr.splitlines()
                if line.startswith('%Warning-') and ('remote_effect_stream' in line)]
    if warnings:
        raise RuntimeError('new-source warnings: ' + '\n'.join(warnings))
    results = []
    boundary_dir = output / 'boundaries'
    boundary_dir.mkdir()
    command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
               '--top-module', 'tb_remote_effect_stream_boundaries', '--Mdir', str(boundary_dir / 'obj'),
               '-o', 'boundaries', *map(str, common + [boundary])]
    commands.append(command)
    built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
    (boundary_dir / 'compile.stdout').write_text(built.stdout)
    (boundary_dir / 'compile.stderr').write_text(built.stderr)
    if built.returncode or '%Warning-' in built.stderr:
        raise RuntimeError('boundary compile failed or warned: ' + built.stderr[-8000:])
    command = [str(boundary_dir / 'obj/boundaries')]
    commands.append(command)
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    (boundary_dir / 'run.stdout').write_text(run.stdout)
    (boundary_dir / 'run.stderr').write_text(run.stderr)
    if run.returncode:
        raise RuntimeError('boundary test failed: ' + run.stdout[-6000:] + run.stderr[-2000:])
    parsed = [json.loads(line.split(' ', 1)[1]) for line in run.stdout.splitlines()
              if line.startswith('REMOTE_EFFECT_RESULT ')]
    if len(parsed) != 1 or not parsed[0].get('passed'):
        raise RuntimeError('missing structured boundary result')
    results.extend(parsed)
    for mhz in (25, 50):
        for rate44 in (0, 1):
            command = [str(output / 'obj/remote_effect_stream'), f'+W_MHZ={mhz}', f'+RATE44={rate44}']
            commands.append(command)
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
            name = f'w{mhz}-rate44-{rate44}'
            (output / (name + '.stdout')).write_text(run.stdout)
            (output / (name + '.stderr')).write_text(run.stderr)
            if run.returncode:
                raise RuntimeError('test failed: ' + name + '\n' + run.stdout[-6000:] + run.stderr[-2000:])
            parsed = [json.loads(line.split(' ', 1)[1]) for line in run.stdout.splitlines()
                      if line.startswith('REMOTE_EFFECT_RESULT ')]
            if len(parsed) != 1 or not parsed[0].get('passed'):
                raise RuntimeError('missing structured verification result: ' + name)
            results.extend(parsed)
    # Each mutation must fail a public-behavior assertion, rather than just
    # failing to compile. These are isolated output copies, never input edits.
    mutations = (
        ('m_wrong_key', 0, 'rsp_key_i==key && ', '', 'wrong key field rejected'),
        ('m_unissued', 0, ' && issued[response_slot]', '', 'unissued result rejected'),
        ('m_pcm16', 0, 'left_o<=dry_l[cursor];right_o<=dry_r[cursor];',
         "left_o<={dry_l[cursor][31:16],16'd0};right_o<=dry_r[cursor];", 'deadline matches dry'),
        ('m_rate_reuse', 0, 'revoked<=clear_i || key_i==key;', "revoked<=1'b0;", 'rate-only change cannot reuse'),
        ('w_no_lease', 1, 'ownership=admitted_i && engine_lease_i;', 'ownership=admitted_i;', 'no work without exclusive lease'),
        ('w_no_timeout', 1, "wire timeout_work=state!=IDLE && timer==T'(PROCESS_TIMEOUT_CYCLES-1);",
         "wire timeout_work=1'b0;", 'all completions drain within bound'),
        ('w_unreserved_result', 1, "(rcount<(Q+1)'(QUEUE_FRAMES) || rpop)", "1'b1", 'full request/result queues'),
    )
    controls = []
    for name, source_index, before, after, expected_failure in mutations:
        directory = output / 'negative-controls' / name
        directory.mkdir(parents=True)
        original = common[source_index].read_text()
        if original.count(before) != 1:
            raise RuntimeError('negative-control anchor drift: ' + name)
        changed = directory / common[source_index].name
        changed.write_text(original.replace(before, after))
        mutant_sources = list(common)
        mutant_sources[source_index] = changed
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
                   '--top-module', 'tb_remote_effect_stream_boundaries', '--Mdir', str(directory / 'obj'),
                   '-o', 'boundaries', *map(str, mutant_sources + [boundary])]
        built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        (directory / 'compile.log').write_text(built.stdout + built.stderr)
        if built.returncode:
            raise RuntimeError('negative control did not compile: ' + name)
        run = subprocess.run([str(directory / 'obj/boundaries')], cwd=ROOT,
                             capture_output=True, text=True, timeout=60)
        log = directory / 'run.log'
        log.write_text(run.stdout + run.stderr)
        rejected = run.returncode != 0 and expected_failure in log.read_text()
        controls.append(dict(name=name, rejected=rejected, exit_code=run.returncode,
                             expected_failure=expected_failure, changed_source_sha256=sha(changed),
                             mutation=dict(before=before, after=after), compile_command=command,
                             run_log=str(log), run_log_sha256=sha(log)))
        if not rejected:
            raise RuntimeError('negative control not rejected as expected: ' + name)
    for name, expected in locked.items():
        if sha(ROOT / name) != expected:
            raise RuntimeError('verified input changed: ' + name)
    evidence = dict(schema=1, passed=True, scope='asynchronous logical transport and real engine RTL only',
                    hardware_tested=False, physical_timing_accepted=False, full_cdc_accepted=False,
                    physical_transport_selected=False, profiles_changed=False,
                    source_sha256=locked, baseline=baseline.evidence(),
                    baseline_math_sha256=sha(math_path), results=results,
                    negative_controls=controls, commands=commands)
    (output / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
