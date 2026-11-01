#!/usr/bin/env python3
"""Compare complete M/W/legacy services with the exact pre-slot source view."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch_slot_sources as slots
from run_runtime_controlled import runtime_sources
from run_event_config_contract import wrapper


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, out = args.project.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    contract = slots.source_contract()
    bench = ROOT / 'sim/audio/tb_event_config_service_contract.sv'
    text = bench.read_text().replace('wire w_done,legacy_done;', 'wire w_done,m_done,legacy_done;')
    text = text.replace('  event_config_service_case #(.NATIVE(0),.D_ONLY(0)) legacy_case(legacy_done);',
                        '  event_config_service_case #(.NATIVE(1),.D_ONLY(0)) master_case(m_done);\n'
                        '  event_config_service_case #(.NATIVE(0),.D_ONLY(0)) legacy_case(legacy_done);')
    text = text.replace('wait(w_done && legacy_done)', 'wait(w_done && m_done && legacy_done)')
    text = text.replace('PASS full W/legacy module contracts', 'PASS full M/W/legacy dispatch slot contracts')
    tb = out / 'tb_dispatch_slots.sv'
    tb.write_text(text)
    # Uninstantiated board/consumer sources belong to parallel W work. The
    # actual service, all engines/effects, DMA and ordered DDR model remain.
    excluded = {'workstation_runtime_audio.sv', 'workstation_runtime_controlled.sv',
                'workstation_observation_consumers.sv', 'workstation_controlled_services.sv',
                'audio_capture_fifo.sv', 'score_led_player.sv', 'workstation_pcm_observation_bridge.sv'}
    sources = [p for p in runtime_sources(project, tb) if p.name not in excluded]
    modules = ('gw138k_event_workstation', 'workstation_runtime_render_engines',
               'workstation_runtime_oscillator_engine', 'workstation_audio_render_service')
    service = ROOT / 'rtl/audio/workstation_audio_render_service.sv'
    for module in modules:
        relative = 'rtl/audio/' + module + '.sv'
        previous = slots.reference_view(relative) if relative in slots.HUNKS else service.read_text()
        for name in modules:
            previous = re.sub(r'\b' + name + r'\b', name + '_before_event_config', previous)
        path = out / (module + '_before_event_config.sv')
        path.write_text(previous)
        sources.append(path)
    miter = wrapper(service.read_text()).replace('M13/current', 'M23/stored-slot')
    anchor = 'comparisons=comparisons+1;end'
    checks = ('workstation.event_ready', 'workstation.core_event_valid',
              'workstation.core_expression_valid', 'workstation.held',
              'workstation.deferred', 'workstation.releasing', 'workstation.release_index')
    assert miter.count(anchor) == 1
    miter = miter.replace(anchor, ''.join(
        'if(actual.' + name + ' !== reference.' + name + ')$fatal(1,"stored slot boundary differs: ' + name + '");\n'
        for name in checks) + anchor)
    path = out / 'event_config_contract_miter.sv'
    path.write_text(miter)
    sources.append(path)
    memory_reference = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
    memory_text = memory_reference.read_text()
    anchor = '\nmodule tb_workstation_runtime_effects;'
    assert memory_text.count(anchor) == 1
    path = out / 'ordered_posted_ddr_model.sv'
    path.write_text(memory_text[:memory_text.index(anchor)])
    sources.append(path)
    inputs = list(dict.fromkeys(sources + slots.contract_inputs() + [service, bench, memory_reference,
        Path(__file__).resolve(), ROOT / 'sim/audio/run_runtime_controlled.py',
        ROOT / 'sim/audio/run_event_config_contract.py', ROOT / 'rtl/audio/runtime_spatial_room_preset.svh']))
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    hashes = {str(p): sha(p) for p in inputs}
    result = dict(schema=1, passed=False, source_contract=contract, source_sha256=hashes,
                  scope='Complete pre-slot/current services and real engines, effects, DMA in M/W/legacy; every half-cycle public and private state comparison',
                  additional_compared_boundaries=list(checks), hardware_tested=False, physical_timing_verified=False)
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_event_config_service_contract', '--Mdir', str(out / 'obj'),
                   '-I' + str(ROOT), '-I' + str(project), *map(str, sources)]
        with (out / 'compile.log').open('w') as log:
            subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        assert '%Warning-UNOPTFLAT' not in (out / 'compile.log').read_text(), 'combinational admission loop'
        with (out / 'run.log').open('w') as log:
            subprocess.run([str(out / 'obj/Vtb_event_config_service_contract')], cwd=project,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        log = (out / 'run.log').read_text()
        assert 'PASS full M/W/legacy dispatch slot contracts' in log
        result['cases'] = [{k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
                           for line in log.splitlines() if line.startswith('PASS event_config_contract')]
        assert len(result['cases']) == 3
        assert all(sha(p) == value for p, value in hashes.items()), 'dispatch contract input drift'
        result['all_inputs_unchanged'] = True
        result['passed'] = True
        print(log, end='')
    finally:
        result['logs_sha256'] = {p.name: sha(p) for p in out.glob('*.log')}
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
