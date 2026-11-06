#!/usr/bin/env python3
"""Exercise one leased reverb with the actual local effects and DDR fence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_shared_reverb_experiment import project

BENCH_SHA = '5c7fb85775b9d5b365428c6c2f578fa37587aea4d034b57c5b105f2a21e3ec58'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def engine_paths(tree):
    modules = {m['name']: m for m in tree['modulesp'] if m['type'] == 'MODULE'}
    found = []

    def visit(module, path):
        if module.get('origName') == 'workstation_runtime_spatial_reverb':
            found.append(path)
        for cell in nodes(module.get('stmtsp', [])):
            if cell.get('type') == 'CELL':
                visit(modules[cell['modName']], path + '.' + cell['name'])
    visit(modules['tb_shared_reverb_lease'], 'tb_shared_reverb_lease')
    return found


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    math = output / 'audio_math_pkg.sv'
    math.write_bytes(baseline.read_bytes('legacy/rtl/audio/audio_math_pkg.sv'))
    selected, projection = project(ROOT)
    seam = output / 'local_effects.sv'
    seam.write_text(selected)
    original_bench = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
    if sha(original_bench) != BENCH_SHA:
        raise ValueError('actual memory model source drift')
    memory = output / 'memory_model.sv'
    text = original_bench.read_text()
    start = text.index('module runtime_effects_memory_model(')
    end = text.index('endmodule', start) + len('endmodule')
    memory.write_text('`timescale 1ns/1ps\n' + text[start:end] + '\n')
    names = (
        'rtl/audio/workstation_shared_spatial_reverb.sv',
        'rtl/audio/workstation_worker_effects_shared.sv',
        'rtl/audio/workstation_remote_effect_stream_w.sv',
        'rtl/audio/workstation_runtime_spatial_reverb.sv',
        'rtl/audio/workstation_runtime_chorus_effect.sv',
        'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv',
        'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv',
        'rtl/music/music_async_fifo.sv',
        'rtl/memory/workstation_sdp.sv',
        'rtl/memory/workstation_sdp_banked.sv',
        'sim/audio/tb_shared_reverb_lease.sv',
    )
    sources = [ROOT / name for name in names]
    inputs = sources + [original_bench, Path(__file__),
        ROOT / 'rtl/audio/workstation_runtime_stereo_effects.sv',
        ROOT / 'rtl/audio/workstation_runtime_stereo_effects.remote_reverb_partition.json',
        ROOT / 'rtl/audio/runtime_spatial_room_preset.svh',
        ROOT / 'tools/workstation_shared_reverb_experiment.py']
    locked = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
    evidence = dict(schema=1, passed=False, scope='source-only full effects/DDR ownership experiment',
        production_profile_selected=False, hardware_tested=False, bitstream=None,
        synthesis_run=False, physical_timing_accepted=False, full_cdc_accepted=False,
        source_sha256=locked, baseline=baseline.evidence(), projection=projection,
        prepared_sha256={p.name: sha(p) for p in (math, seam, memory)}, commands=[], results=[])

    def invoke(argv, name, timeout=180):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        log = output / (name + '.log')
        log.write_text(result.stdout + result.stderr)
        evidence['commands'].append(dict(argv=argv, exit_code=result.returncode,
            log=str(log), log_sha256=sha(log)))
        return result

    try:
        argv = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
            '--top-module', 'tb_shared_reverb_lease', '--Mdir', str(output / 'obj'),
            '-o', 'shared_lease', '-I' + str(ROOT), str(math), str(seam), str(memory),
            *map(str, sources)]
        built = invoke(argv, 'compile')
        if built.returncode:
            raise RuntimeError('compile failed: ' + built.stderr[-6000:])
        evidence['compile_warnings'] = [line for line in built.stderr.splitlines()
            if line.startswith('%Warning-')]
        new_names = names[:3] + (names[-1],)
        if any(str(ROOT / name) + ':' in line for name in new_names
               for line in evidence['compile_warnings']):
            raise ValueError('new ownership sources must compile without warnings')
        hierarchy = output / 'hierarchy.json'
        meta = output / 'hierarchy.meta.json'
        parse = ['verilator', '--json-only', '--timing', '-Wno-fatal',
            '--top-module', 'tb_shared_reverb_lease', '--json-only-output', str(hierarchy),
            '--json-only-meta-output', str(meta), '-I' + str(ROOT), str(math), str(seam),
            str(memory), *map(str, sources)]
        if invoke(parse, 'hierarchy').returncode:
            raise RuntimeError('elaborated hierarchy failed')
        evidence['actual_reverb_paths'] = engine_paths(json.loads(hierarchy.read_text()))
        if evidence['actual_reverb_paths'] != ['tb_shared_reverb_lease.dut.shared_engine.engine']:
            raise ValueError('one actual reverb instance required')
        evidence['hierarchy_sha256'] = sha(hierarchy)
        for mhz in (25, 50):
            for rate in (0, 1):
                for ack_fault in (0, 1):
                    result = invoke([str(output / 'obj/shared_lease'), f'+W_MHZ={mhz}',
                        f'+LOCAL44={rate}', f'+RESTORE_ACK_FAULT={ack_fault}'],
                        f'w{mhz}-local44-{rate}-ackfault-{ack_fault}')
                    if result.returncode:
                        raise RuntimeError('simulation failed: ' + result.stdout[-5000:] + result.stderr[-2000:])
                    rows = [json.loads(line.split(' ', 1)[1]) for line in result.stdout.splitlines()
                        if line.startswith('SHARED_REVERB_RESULT ')]
                    if len(rows) != 1 or not rows[0].get('passed'):
                        raise ValueError('missing structured result')
                    evidence['results'].extend(rows)
        mutations = (
            ('reset_admission_open', 0, 'local_quiesce_o=!rst_ni || state!=LOCAL || request;',
             'local_quiesce_o=state!=LOCAL || request;', 'reset closes client admission'),
            ('early_grant', 0, 'LOCAL:if(request)begin state<=DRAIN;timer<=0;end',
             'LOCAL:if(request)begin state<=REMOTE;timer<=0;end',
             'last local sample completes before grant'),
            ('skip_ddr_fence', 0, 'else if(local_fence_ready_i)state<=FENCE_WAIT;',
             'else if(local_fence_ready_i)state<=REMOTE;',
             'actual ordered DDR fence returned before grant'),
            ('local_admission_open', 1, 'wire open_local=!local_quiesce_o',
             'wire open_local=rst_ni', 'local admission closed during lease'),
            ('wrong_restore_rate', 0, 'config_rate=restoring ? local_rate',
             'config_rate=restoring ? remote_rate_44100_i', 'local path opens within bound'),
            ('cross_owner_result', 0, 'assign valid_o=rst_ni && local_path && engine_valid',
             'assign valid_o=rst_ni && (local_path || remote_grant_o) && engine_valid',
             'remote completion is hidden from local client'),
            ('no_restore_timeout', 0, "wire restore_timeout=restoring && timer==T'(RESTORE_TIMEOUT_CYCLES-1);",
             "wire restore_timeout=1'b0;", 'failed restoration latches closed fault'),
            ('panic_clears_fault', 0, 'if(fault_o)begin state<=FAILED;timer<=0;end',
             'if(fault_o)begin state<=clear_i ? RETURN_CLEAR : FAILED; if(clear_i)fault_o<=0;timer<=0;end',
             'PANIC cannot clear a restoration fault'),
        )
        evidence['negative_controls'] = []
        for name, index, before, after, expected in mutations:
            directory = output / ('negative-' + name)
            directory.mkdir()
            source = sources[index].read_text()
            if source.count(before) != 1:
                raise ValueError('mutation anchor drift: ' + name)
            mutant = directory / sources[index].name
            mutant.write_text(source.replace(before, after))
            command = list(argv)
            command[command.index(str(sources[index]))] = str(mutant)
            command[command.index('--Mdir') + 1] = str(directory / 'obj')
            if invoke(command, 'negative-' + name + '-compile').returncode:
                raise ValueError('mutation must compile: ' + name)
            result = invoke([str(directory / 'obj/shared_lease')], 'negative-' + name + '-run')
            rejected = result.returncode != 0 and expected in result.stdout + result.stderr
            evidence['negative_controls'].append(dict(name=name, rejected=rejected,
                source_sha256=sha(mutant), before=before, after=after, expected_failure=expected))
            if not rejected:
                raise ValueError('mutation was not rejected as expected: ' + name)
        evidence['passed'] = True
    finally:
        evidence['sources_unchanged'] = locked == {str(p.relative_to(ROOT)): sha(p) for p in inputs}
        (output / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    if not evidence['sources_unchanged']:
        raise ValueError('verified input changed')
    print(json.dumps({k: evidence[k] for k in ('passed', 'results', 'sources_unchanged')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
