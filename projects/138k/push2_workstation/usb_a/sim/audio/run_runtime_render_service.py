#!/usr/bin/env python3
"""Verify real dual-rate render/service transactions and modeled wet PCM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
from test_workstation_runtime_effects import Effects


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    miter = parser.add_mutually_exclusive_group()
    miter.add_argument('--effect-slot-miter', action='store_true',
                       help='Compare every public service output and core_ce to exact consumed M11 modules every half cycle')
    miter.add_argument('--event-config-miter', action='store_true',
                       help='Compare the complete service/event pair to exact consumed M13 modules, including dispatch and configuration transactions')
    miter.add_argument('--sample-admission-miter', action='store_true',
                       help='Compare every public output and private boundary to the immutable source before native sample admission factoring')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                     key=lambda path: (not path.name.endswith('_pkg.sv'), str(path)))
    sources += [project / name for name in (
        'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
        'rtl/audio/serial_spatial_reverb.sv', 'rtl/memory/workstation_sdp.sv',
        'rtl/memory/workstation_sdp_banked.sv')]
    for folder in ('rtl/audio/scope_vec', 'rtl/control', 'rtl/audio/delay_ddr'):
        sources += sorted((project / folder).glob('*.sv'))
    sources += [ROOT / name for name in (
        'rtl/music/music_async_fifo.sv', 'rtl/audio/gw138k_event_workstation.sv',
        'rtl/audio/workstation_audio_render_service.sv', 'rtl/audio/workstation_frame_delivery.sv',
        'rtl/audio/workstation_runtime_div147.sv',
        'rtl/audio/workstation_rate_pitch_expression.sv', 'rtl/audio/workstation_runtime_oscillator_engine.sv',
        'rtl/audio/workstation_runtime_scope_vec.sv', 'rtl/audio/workstation_runtime_render_engines.sv',
        'rtl/audio/workstation_runtime_stereo_effects.sv', 'rtl/audio/workstation_runtime_chorus_effect.sv',
        'rtl/audio/workstation_runtime_spatial_reverb.sv',
        'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv',
        'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv')]
    maintained_names = {path.name for path in sources if path.is_relative_to(ROOT)}
    sources = [path for path in sources if not (
        path.is_relative_to(project / 'rtl/audio/delay_ddr') and path.name in maintained_names)]
    memory_reference = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
    memory_text = memory_reference.read_text()
    anchor = '\nmodule tb_workstation_runtime_effects;'
    if memory_text.count(anchor) != 1:
        raise ValueError('Posted DDR model extraction anchor drift')
    memory = output / 'ordered_posted_ddr_model.sv'
    memory.write_text(memory_text[:memory_text.index(anchor)])
    tb = Path(__file__).with_name('tb_workstation_runtime_render_service.sv')
    sources += [memory, tb]
    miter_inputs = []
    private_paths = []
    sample_contract = None
    if args.effect_slot_miter or args.event_config_miter or args.sample_admission_miter:
        if args.sample_admission_miter:
            import prove_sample_admission_cofactor as admission
            sample_contract = admission.source_contract()
            references = list(admission.SAMPLE_ADMISSION_REFERENCES)
            miter_inputs.append(Path(admission.__file__).resolve())
        else:
            references = ([
                (project / 'src/ae350/gw138k_event_workstation.sv', 'gw138k_event_workstation',
                 '5d02329a6b7f08ec30d79552a4814436b7c01611f4e4bed83c1514d154ef3fd1'),
                (project / 'rtl/audio/workstation_audio_render_service.sv', 'workstation_audio_render_service',
                 '148f0fb7b8976099d26bbf71025105c0d0df6f3b5e06ea90f1f75cdae0e46968')]
                if args.event_config_miter else [
                (project / 'src/ae350/gw138k_event_workstation.sv', 'gw138k_event_workstation',
                 '5771d9d60e2e150c27a72e9ad1bf031c7d1faf952bf474d8791237171cb886a2'),
                (project / 'rtl/audio/workstation_runtime_stereo_effects.sv', 'workstation_runtime_stereo_effects',
                 '7bd9a9f547f82bb30f9f015610f9ac448c1ae374fe87366e1d37d52f2093b826'),
                (project / 'rtl/audio/workstation_audio_render_service.sv', 'workstation_audio_render_service',
                 '148f0fb7b8976099d26bbf71025105c0d0df6f3b5e06ea90f1f75cdae0e46968')])
        reference_label = ('pre-sample-admission fixture' if args.sample_admission_miter else
                           'M13 service/event pair' if args.event_config_miter else 'M11 reference')
        for path, name, expected in references:
            if expected is not None and digest(path) != expected:
                raise ValueError('Exact consumed ' + reference_label + ' drift: ' + str(path))
            text = path.read_text()
            for _, module, _ in references:
                text = re.sub(r'\b' + module + r'\b', module + '_before_effect_slot', text)
            if name == 'workstation_runtime_stereo_effects':
                # Verilator conflates the two identically named hierarchical
                # defparam targets in this dual-service miter. Rename only the
                # reference instance and its two targets; keep both exact
                # RAM_STYLE values and all behavioral expressions unchanged.
                if len(re.findall(r'\bdelay_stage\b', text)) != 3:
                    raise ValueError('Reference delay-stage hierarchy drift')
                text = re.sub(r'\bdelay_stage\b', 'reference_delay_stage', text)
            target = output / (name + '_before_effect_slot.sv')
            target.write_text(text)
            sources.append(target);miter_inputs.append(path)
        service = (ROOT / 'rtl/audio/workstation_audio_render_service.sv').read_text()
        header = re.search(r'module workstation_audio_render_service\b.*?\n\);', service, re.S)[0]
        parameters = re.findall(r'parameter (?:bit|integer) (\w+)=', header)
        declarations = re.findall(r'\b(input|output)\s+(?:wire|reg)\s+(signed\s+)?(\[[^\]]+\]\s+)?(.*?)(?=\binput\b|\boutput\b|\)\s*;)', header, re.S)
        ports = [(direction, (signed or '') + (width or ''), name.strip())
                 for direction, signed, width, names in declarations
                 for name in names.rstrip().rstrip(',').split(',')]
        if len(ports) != 72 or any(not re.fullmatch(r'\w+', name) for _, _, name in ports):
            raise ValueError('Exact service miter port inventory drift: ' + str(len(ports)))
        actual_ports = ','.join('.' + name + '(' + name + ')' for _, _, name in ports)
        reference_ports = ','.join('.' + name + '(' + ('reference_' if direction == 'output' else '') + name + ')'
                                   for direction, _, name in ports)
        propagated = '#(' + ','.join('.' + name + '(' + name + ')' for name in parameters) + ')'
        outputs = [name for direction, _, name in ports if direction == 'output']
        wrapper = header.replace('module workstation_audio_render_service', 'module effect_slot_service_miter').replace('output reg', 'output wire')
        wrapper += '\n' + '\n'.join('wire ' + width + 'reference_' + name + ';'
                                    for direction, width, name in ports if direction == 'output')
        wrapper += '\nworkstation_audio_render_service ' + propagated + ' actual(' + actual_ports + ');\n'
        wrapper += 'workstation_audio_render_service_before_effect_slot ' + propagated + ' reference(' + reference_ports + ');\n'
        wrapper += 'integer comparisons=0;\nalways @(posedge clk_i or negedge clk_i)if(rst_ni)begin\n'
        wrapper += 'if({' + ','.join(outputs) + '} !== {' + ','.join('reference_' + name for name in outputs) + '})$fatal(1,"actual old/new full service public output differs");\n'
        wrapper += 'if(actual.workstation.core_ce!==reference.workstation.core_ce)$fatal(1,"actual old/new core_ce sampling edge differs");comparisons=comparisons+1;end\n'
        if args.event_config_miter or args.sample_admission_miter:
            private_paths = ['accepted', 'core_config', 'requested_rate', 'active', 'response_sent',
                'held_rate', 'external_busy', 'request_muted', 'request_cancel_epoch', 'request_epoch_match',
                'held_pcm_left', 'held_pcm_right', 'core_rate_busy', 'core_fault',
                'workstation.dispatch', 'workstation.mode_valid', 'workstation.panic_accept',
                'workstation.parameter_commit', 'workstation.engine_rate_commit',
                'workstation.runtime_config_block', 'workstation.rate_ready_o', 'workstation.history_ready_o',
                'workstation.pending', 'workstation.frame_inflight',
                'workstation.runtime_configuration.busy', 'workstation.runtime_configuration.is_config',
                'workstation.runtime_configuration.pending_rate', 'workstation.runtime_configuration.committed_rate',
                'workstation.runtime_configuration.failed', 'workstation.runtime_configuration.applied',
                'workstation.runtime_configuration.history_done']
            wrapper += 'always @(posedge clk_i or negedge clk_i)if(rst_ni)begin\n'
            boundary_label = 'pre-sample/new' if args.sample_admission_miter else 'M13/new'
            wrapper += ''.join('if(actual.' + path + '!==reference.' + path +
                ')$fatal(1,"actual ' + boundary_label + ' private boundary differs: ' + path + '");\n' for path in private_paths)
            label = 'SAMPLE_ADMISSION_MITER' if args.sample_admission_miter else 'EVENT_CONFIG_MITER'
            wrapper += 'end\nfinal $display("' + label + ' private_boundaries=' + str(len(private_paths)) + '");\n'
        wrapper += 'final $display("EFFECT_SLOT_MITER comparisons=%0d public_outputs=' + str(len(outputs)) + '",comparisons);\nendmodule\n'
        target = output / 'effect_slot_service_miter.sv';target.write_text(wrapper);sources.append(target)
        adapted = output / tb.name
        text = tb.read_text().replace('workstation_audio_render_service #(', 'effect_slot_service_miter #(').replace('dut.', 'dut.actual.')
        if text == tb.read_text():raise ValueError('Actual service miter fixture anchor drift')
        adapted.write_text(text);sources[sources.index(tb)] = adapted;miter_inputs.append(tb)
    banks_path = ROOT / 'rtl/audio/runtime_spatial_room_preset.json'
    inputs = [*sources, *miter_inputs, memory_reference, Path(__file__).resolve(), banks_path,
              ROOT / 'sim/test_workstation_runtime_effects.py', ROOT / 'sim/test_workstation_runtime_reverb.py',
              ROOT / 'rtl/audio/runtime_spatial_room_preset.svh']
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    hashes = {str(path): digest(path) for path in inputs}
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  scope='Opt-in full native dual-rate render service; real 200ms delay ring and ordered posted DDR model',
                  project=str(project), input_sha256=hashes, effect_slot_miter=args.effect_slot_miter,
                  event_config_miter=args.event_config_miter, private_boundaries_compared=private_paths,
                  sample_admission_miter=args.sample_admission_miter, sample_admission_source_contract=sample_contract,
                  memory_model='Exact leading module extracted from committed effects TB; writes execute after command acceptance, fence ACK follows ordered read response')
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_render_service', '--Mdir', str(output / 'obj'),
                   '-I' + str(ROOT), '-I' + str(project), *map(str, sources)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        result['compile_warning_counts'] = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            result['compile_warning_counts'][name] = result['compile_warning_counts'].get(name, 0) + 1
        if 'UNOPTFLAT' in result['compile_warning_counts']:
            raise ValueError('Combinational ready/admission loop')
        trace = output / 'pcm.txt'
        command = [str(output / 'obj/Vtb_workstation_runtime_render_service'), '+TRACE=' + str(trace)]
        result['run_argv'] = command
        with (output / 'run.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        log = (output / 'run.log').read_text()
        matches = [line for line in log.splitlines() if line.startswith('PASS runtime_render_service:')]
        if len(matches) != 1:
            raise ValueError('Missing runtime service verification')
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', matches[0])}
        model = Effects(json.loads(banks_path.read_text())['banks'])
        expected = None
        compared = {48000: 0, 44100: 0}
        for number, line in enumerate(trace.read_text().splitlines(), 1):
            operation, *values = line.split()
            values = list(map(int, values))
            if operation == 'C':
                if expected is not None:
                    raise ValueError(f'Barrier crossed unfinished frame at trace line {number}')
                model.clear(values[0])
            elif operation == 'F':
                if expected is not None:
                    raise ValueError(f'Second unfinished frame at trace line {number}')
                expected = model.frame(*values)[:2]
            elif operation == 'O':
                if tuple(values) != expected:
                    raise ValueError(f'Independent wet PCM mismatch line {number}: RTL={values} model={expected}')
                compared[model.rate] += 1
                expected = None
            else:
                raise ValueError('Unknown trace operation')
        if expected is not None or min(compared.values()) < 24000:
            raise ValueError('Missing complete modeled dual-rate frames')
        result['independent_fixed_point_compared_frames'] = compared
        result['trace_sha256'] = digest(trace)
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Integration inputs drifted during verification')
        result['passed'] = True
        print(log, end='')
        print('Independent effects PCM comparisons:', compared)
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
