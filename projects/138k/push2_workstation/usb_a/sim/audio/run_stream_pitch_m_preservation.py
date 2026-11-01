#!/usr/bin/env python3
"""Compare complete native M and legacy services to the pre-W-Pitch sources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import workstation_stream_pitch_provenance as lineage
from run_runtime_controlled import runtime_sources
from run_event_config_contract import wrapper


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--negative-control', action='store_true')
    args = ap.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    contract = lineage.source_bundle(ROOT)
    bench = ROOT/'sim/audio/tb_event_config_service_contract.sv'
    text = bench.read_text().replace('.NATIVE(1),.D_ONLY(1)', '.NATIVE(1),.D_ONLY(0)')
    text = text.replace('PASS full W/legacy module contracts', 'PASS pre-Pitch/current full M/legacy contracts')
    tb = output/'tb_stream_pitch_m_preservation.sv'
    tb.write_text(text)
    excluded = {'workstation_runtime_audio.sv', 'workstation_runtime_controlled.sv',
                'workstation_observation_consumers.sv', 'workstation_controlled_services.sv',
                'audio_capture_fifo.sv', 'score_led_player.sv', 'workstation_pcm_observation_bridge.sv'}
    sources = []
    for path in runtime_sources(project, tb):
        if path.name in excluded:
            continue
        if path.is_relative_to(project) and path.relative_to(project).parts[:2] == ('rtl', 'control'):
            path = ROOT/path.relative_to(project)
        if path not in sources:
            sources.append(path)
    renames = {'gw138k_event_workstation': 'gw138k_event_workstation_before_event_config',
               'workstation_audio_render_service': 'workstation_audio_render_service_before_event_config',
               'workstation_parameters': 'workstation_parameters_before_stream_pitch'}
    service = ROOT/'rtl/audio/workstation_audio_render_service.sv'
    for relative in ('rtl/audio/gw138k_event_workstation.sv',
                     'rtl/control/workstation_parameters.sv',
                     'rtl/audio/workstation_audio_render_service.sv'):
        source = (ROOT/relative).read_bytes()
        previous = lineage.restore_parent(relative, source).decode() if relative in lineage.HUNKS else source.decode()
        for name, target in renames.items():
            previous = re.sub(r'\b'+name+r'\b', target, previous)
        target = output/(Path(relative).stem+'_before_stream_pitch.sv')
        target.write_text(previous)
        sources.append(target)
    if args.negative_control:
        original = ROOT/'rtl/audio/gw138k_event_workstation.sv'
        text = original.read_text()
        anchor = 'assign pcm_pitch_quiet=1;assign pcm_pitch_joined=1;'
        assert text.count(anchor) == 1
        target = output/'gw138k_event_workstation_m_guard_negative.sv'
        target.write_text(text.replace(anchor, 'assign pcm_pitch_quiet=1;assign pcm_pitch_joined=0;'))
        sources = [target if p == original else p for p in sources]
    target = output/'event_config_contract_miter.sv'
    target.write_text(wrapper(service.read_text()).replace('M13/current', 'pre-W-Pitch/current M'))
    sources.append(target)
    memory_reference = ROOT/'sim/audio/tb_workstation_runtime_effects.sv'
    text = memory_reference.read_text()
    anchor = '\nmodule tb_workstation_runtime_effects;'
    assert text.count(anchor) == 1
    target = output/'ordered_posted_ddr_model.sv'
    target.write_text(text[:text.index(anchor)])
    sources.append(target)
    inputs = list(dict.fromkeys(sources+[Path(__file__).resolve(), bench, memory_reference,
        ROOT/'sim/audio/run_runtime_controlled.py', ROOT/'sim/audio/run_event_config_contract.py',
        ROOT/'tools/workstation_stream_pitch_provenance.py',
        ROOT/'rtl/audio/runtime_spatial_room_preset.svh', *(ROOT/n for n in lineage.HUNKS)]))
    inputs += sorted((project/'sim/data').rglob('*.mem'))
    inputs += sorted((project/'sim/matlab/output').rglob('*.mem'))
    hashes = {str(p): sha(p) for p in inputs}
    report = dict(schema=1, passed=False, negative_control=args.negative_control,
        scope='Complete unchanged native M and legacy service+engines+FX+DMA against exact pre-W-Pitch parents; public50/common25/native7 every half-cycle',
        source_contract=contract, input_sha256=hashes, hardware_tested=False, physical_timing_verified=False)
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', 'tb_event_config_service_contract', '--Mdir', str(output/'obj'),
            '-I'+str(ROOT), '-I'+str(project), *map(str, sources)]
        with (output/'compile.log').open('x') as log:
            subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        assert 'UNOPTFLAT' not in (output/'compile.log').read_text(), 'combinational admission loop'
        with (output/'run.log').open('x') as log:
            run = subprocess.run([str(output/'obj/Vtb_event_config_service_contract')],
                cwd=project, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        log = (output/'run.log').read_text()
        report['run_exit_code'] = run.returncode
        if args.negative_control:
            assert run.returncode != 0 and 'full service output differs' in log, log[-3000:]
            report['negative_control_rejected'] = True
        else:
            assert run.returncode == 0 and 'PASS pre-Pitch/current full M/legacy contracts' in log, log[-3000:]
            report['cases'] = [dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', line))
                for line in log.splitlines() if line.startswith('PASS event_config_contract')]
            report['miter_metrics'] = [dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', line))
                for line in log.splitlines() if line.startswith('CONTRACT_MITER')]
            assert len(report['cases']) == len(report['miter_metrics']) == 2
        assert hashes == {str(p): sha(p) for p in inputs}, 'consumed input drift'
        report.update(passed=True, all_consumed_inputs_unchanged=True)
        print(log, end='')
    finally:
        report['logs_sha256'] = {p.name: sha(p) for p in output.glob('*.log')}
        (output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
