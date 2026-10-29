#!/usr/bin/env python3
"""Prepare an isolated, permanently muted digital clock/I2S experiment.

The existing Mac ASCII/separate-process EDA builder is reused unchanged.
Preparing and verifying never start EDA or access a board. This is not a
complete-workstation profile, a production builder, or a programming tool.
"""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'probes/audio_clock_i2s/probe.json'
SDC = 'probes/audio_clock_i2s/audio_probe.sdc'
CHECKS = 'probes/audio_clock_i2s/physical_checks.json'
TOOL = 'tools/workstation_audio_probe.py'
LEGACY_BUILDER = 'example/RTL8723DS/tools/gowin_build.py'
DEFAULT_IDE = Path('/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE')
RESERVED_CODES = {'00000000', 'FFFFFFFF', '00000083', '00000085', '13802302',
                  '13802401', '13802402', '13802420', 'C1102024', 'C110210A', 'C11028E5'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(root):
    config = json.loads((root / CONFIG).read_text())
    if config['schema'] != 1 or config['top_module'] != 'workstation_audio_probe_top':
        raise ValueError('Unknown audio probe configuration')
    return config


def source_closure(root, config):
    sources, modules = {}, {}
    for name in config['source_paths']:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or path.suffix != '.sv':
            raise ValueError('Probe source escapes its versioned root: ' + name)
        for module in re.findall(r'^\s*module\s+(\w+)', path.read_text(), re.M):
            if module in modules:
                raise ValueError('Duplicate probe module: ' + module)
            modules[module] = name
        sources[name] = sha(path)
    if set(modules) != {Path(name).stem for name in config['source_paths']}:
        raise ValueError('Probe module closure differs from its explicit five inputs')
    if config['top_module'] not in modules:
        raise ValueError('Probe top missing')
    return sources


def pin_constraints(root, config):
    # Read the established historical files without editing or staging them as
    # a competing implementation. Every enabled location must match evidence.
    repository = root.parents[3]
    references = [repository / 'example/CLOCK_MEASURE/constraints/clocks.cst',
                  repository / 'example/AK4493_AMP/constraints/audio.cst']
    known = {}
    for path in references:
        for signal, pin in re.findall(r'IO_LOC\s+"([^"]+)"\s+(\w+)\s*;', path.read_text()):
            if signal in known and known[signal] != pin:
                raise ValueError('Conflicting audited audio pin: ' + signal)
            known[signal] = pin
    if set(config['pins']) != {'clk_50mhz', 'clk_12m288', 'clk_16m9344', 'restart_n',
                              'ak_pdn', 'ak_mclk', 'ak_bick', 'ak_lrck', 'ak_sdata', 'ak_smute'}:
        raise ValueError('Probe may use only its ten audited digital pins')
    if any(known.get(signal) != pin for signal, pin in config['pins'].items()):
        raise ValueError('Audio probe pin differs from audited reference')
    lines = ['// Existing audited3.3V digital audio pins only; physical SMUTE stays high.']
    for signal, pin in config['pins'].items():
        options = 'IO_TYPE=LVCMOS33 PULL_MODE=' + ('UP' if signal == 'restart_n' else 'NONE')
        if signal.startswith('ak_'):
            options += ' DRIVE=4 BANK_VCCIO=3.3'
        lines += [f'IO_LOC "{signal}" {pin};', f'IO_PORT "{signal}" {options};']
    return '\n'.join(lines) + '\n', {str(path.relative_to(repository)): sha(path) for path in references}


def sdk_capability(config, ide):
    manual = ide / config['sdc_capability']['manual']
    known = manual.is_file() and sha(manual) == config['sdc_capability']['sha256']
    return dict(ide_directory=str(ide), manual=str(manual),
                manual_sha256=sha(manual) if manual.is_file() else None,
                documented_dual_master_supported=known, parser_exercised=False,
                blocker=None if known else 'Unverified SDK dual-master generated-clock support; build is blocked. No false-path fallback.')


def gao_configuration(config, user_code):
    document = ET.Element('GAO_CONFIG')
    ET.SubElement(document, 'Version').text = '3.0'
    ET.SubElement(document, 'Mode').text = 'Standard'
    core = ET.SubElement(document, 'AoCore', index='0', sample_clock=config['sample_clock'],
                         trig_type='0', storage_depth='128', window_num='1', capture_amount='128',
                         implementation='0', trigger_pos='0', module_name=config['top_module'],
                         force_trigger_by_falling_edge='false', capture_init_data_enabled='false')
    signals = ET.SubElement(core, 'SignalList')
    bus = ET.SubElement(signals, 'Bus', capture_enable='true', name=config['debug_bus'])
    for bit in reversed(range(32 * len(config['debug_words_low_first']))):
        ET.SubElement(bus, 'Signal').text = f'audio_probe_debug[{bit}]'
    triggers = ET.SubElement(core, 'Triggers')
    for index in range(16):
        trigger = ET.SubElement(triggers, 'Trigger', index=str(index))
        if index == 0:
            ET.SubElement(ET.SubElement(trigger, 'SignalList'), 'Signal').text = 'audio_probe_debug[32]'
    units = ET.SubElement(core, 'MatchUnits')
    for index in range(16):
        fields = dict(index=str(index), enabled=str(int(index == 0)), match_type='0',
                      counter_enable='0', counter_width='2', counter='2', countinuous='0',
                      func='0', value0='1' if index == 0 else '', value1='0' if index == 0 else '')
        if index == 0:
            fields['trigger'] = '0'
        ET.SubElement(units, 'MatchUnit', **fields)
    ET.SubElement(ET.SubElement(core, 'Expressions', type='Static'), 'Expression').text = 'M0|!M0'
    ET.SubElement(document, 'GAO_ID').text = format(int(user_code[-4:], 16), '016b')
    ET.indent(document, space='  ')
    return ET.tostring(document, encoding='unicode', xml_declaration=True) + '\n'


def project_text(config, user_code):
    lines = ['set project_dir [file dirname [file normalize [info script]]]', 'cd $project_dir',
             'set_device -name GW5AST-138C ' + config['device'],
             'set_option -top_module ' + config['top_module'],
             'set_option -output_base_name audio_probe', 'set_option -synthesis_tool gowinsynthesis',
             'set_option -verilog_std sysv2017',
             'set_option -bit_security 0', 'set_option -user_code ' + user_code,
             'set_option -use_jtag_as_gpio 0', 'set_option -use_cpu_as_gpio 1',
             'set_option -use_sspi_as_gpio 1', 'set_option -use_mspi_as_gpio 1',
             'set_option -unused_pin default', 'set_option -gen_text_timing_rpt 1',
             'set_option -gen_io_cst 1', 'set_option -gen_sdf 1',
             'set_option -gen_verilog_sim_netlist 1', 'set_option -cst_warn_to_error 1',
             'set_option -timing_driven 1', 'set_option -correct_hold_violation 1',
             'set_option -place_option 2', 'set_option -route_option 1']
    lines += ['add_file ' + name for name in config['source_paths']]
    lines += ['add_file constraints/audio_probe.cst', 'add_file constraints/audio_probe.sdc',
              'add_file debug/audio_probe.gao', 'run all']
    return '\n'.join(lines) + '\n'


def prepare(output, user_code, ide=DEFAULT_IDE, root=ROOT):
    root, output, ide = Path(root).resolve(), Path(output).resolve(), Path(ide).resolve()
    if not re.fullmatch(r'[0-9a-fA-F]{8}', user_code or '') or user_code.upper() in RESERVED_CODES:
        raise ValueError('Specify a new explicit eight-hex UserCode; existing accepted/diagnostic identities cannot be reused')
    user_code = user_code.upper()
    if output.exists():
        raise FileExistsError('Probe output must be new: ' + str(output))
    if output.is_relative_to(root) and not any(output.is_relative_to(root / folder) for folder in ('out', 'results')):
        raise ValueError('In-repository probe output must use an ignored out/ or results/ directory')
    config = load_config(root)
    sources = source_closure(root, config)
    cst, pin_evidence = pin_constraints(root, config)
    repository = root.parents[3]
    snapshot = {name: sha(root / name) for name in (*config['source_paths'], CONFIG, SDC, CHECKS, TOOL)}
    external = {LEGACY_BUILDER: sha(repository / LEGACY_BUILDER), **pin_evidence}
    capability = sdk_capability(config, ide)
    output.mkdir(parents=True)
    for name in config['source_paths']:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    for folder in ('constraints', 'debug', 'reports'):
        (output / folder).mkdir()
    (output / 'constraints/audio_probe.cst').write_text(cst)
    shutil.copyfile(root / SDC, output / 'constraints/audio_probe.sdc')
    shutil.copyfile(root / CHECKS, output / 'physical_checks.json')
    shutil.copyfile(root / CONFIG, output / 'probe_config.json')
    (output / 'debug/audio_probe.gao').write_text(gao_configuration(config, user_code))
    (output / 'run_gao.tcl').write_text(project_text(config, user_code))
    manifest = dict(schema=1, identity='custom138k-muted-audio-probe-' + user_code,
                    recorded_at=datetime.now().astimezone().isoformat(), user_code='0x' + user_code,
                    top_module=config['top_module'], source_policy='explicit_versioned_audio_modules_and_probe_top_byte_snapshot',
                    source_paths=config['source_paths'], source_snapshot_sha256=snapshot,
                    external_reference_sha256=external, source_closure_sha256=sources,
                    source_commit=subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip(),
                    sdk_capability=capability, gao_file='debug/audio_probe.gao',
                    signal_schema=config, validation_stage='prepare_only',
                    build_blocked=not capability['documented_dual_master_supported'],
                    physical_audit_complete=False, full_workstation=False,
                    synthesized=False, placed_routed=False, hardware_accepted=False,
                    sram_programmed=False, flash_programmed=False,
                    retirement=config['retirement'],
                    pending_gates=['EDA SDC parser/object resolution; five explicit clocks plus audited SDK GAO clock',
                                   'All physical_checks.json gates; setup/hold/recovery/removal/pulse-width',
                                   'Explicit SRAM candidate identity/readback and separate digital capture acceptance'],
                    input_sha256={str(path.relative_to(output)): sha(path)
                                  for path in sorted(output.rglob('*')) if path.is_file()})
    (output / 'inputs.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    verify(output, root)
    return manifest


def verify(output, root=ROOT):
    output, root = Path(output).resolve(), Path(root).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    config = load_config(root)
    if manifest['source_paths'] != config['source_paths'] or manifest['source_closure_sha256'] != source_closure(root, config):
        raise ValueError('Probe source closure changed; prepare a distinct candidate')
    for name, expected in manifest['source_snapshot_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('Versioned preparation input changed: ' + name)
    for name, expected in manifest['external_reference_sha256'].items():
        if sha(root.parents[3] / name) != expected:
            raise ValueError('Build helper/audited evidence changed: ' + name)
    for name, expected in manifest['input_sha256'].items():
        path = (output / name).resolve()
        if not path.is_relative_to(output) or sha(path) != expected:
            raise ValueError('Prepared probe input changed: ' + name)
    for name, expected in manifest['source_closure_sha256'].items():
        if sha(output / name) != expected:
            raise ValueError('Staged source is not the byte-identical versioned input: ' + name)
    staged_sources = {str(path.relative_to(output)) for path in (output / 'rtl').rglob('*.sv')}
    if staged_sources != set(config['source_paths']):
        raise ValueError('Unexpected/missing staged probe RTL')
    if (output / 'run_gao.tcl').read_text() != project_text(config, manifest['user_code'][2:]):
        raise ValueError('Generated source selection drifted')
    cst, _ = pin_constraints(root, config)
    if (output / 'constraints/audio_probe.cst').read_text() != cst:
        raise ValueError('Generated audited pin selection drifted')
    if (output / 'constraints/audio_probe.sdc').read_bytes() != (root / SDC).read_bytes():
        raise ValueError('Generated timing constraints drifted')
    if (output / 'debug/audio_probe.gao').read_text() != gao_configuration(config, manifest['user_code'][2:]):
        raise ValueError('Generated GAO source selection drifted')
    return manifest


def build(output, root=ROOT):
    manifest = verify(output, root)
    capability = sdk_capability(load_config(root), Path(manifest['sdk_capability']['ide_directory']))
    if not capability['documented_dual_master_supported']:
        raise ValueError(capability['blocker'])
    # The existing helper owns the EDA lock and the ASCII two-process flow.
    # This tool deliberately has no SRAM/Flash/programming operation.
    helper = root.parents[3] / LEGACY_BUILDER
    environment = dict(os.environ, GW138K_IDE_DIR=capability['ide_directory'])
    result = subprocess.run([sys.executable, str(helper), str(Path(output).resolve() / 'run_gao.tcl')], env=environment)
    record = dict(identity=manifest['identity'], helper_returncode=result.returncode,
                  validation_stage='eda_finished_pending_physical_audit' if result.returncode == 0 else 'eda_failed',
                  physical_audit_complete=False, accepted_for_sram=False,
                  pending_gates=manifest['pending_gates'], hardware_accepted=False,
                  sram_programmed=False, flash_programmed=False)
    (Path(output) / 'probe_build_result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'prepare-only', 'verify', 'build'):
        child = commands.add_parser(command)
        child.add_argument('--output', type=Path, required=True)
        if command.startswith('prepare'):
            child.add_argument('--user-code', required=True)
            child.add_argument('--ide-dir', type=Path, default=DEFAULT_IDE)
    args = parser.parse_args()
    try:
        if args.command.startswith('prepare'):
            result = prepare(args.output, args.user_code, args.ide_dir)
            print(json.dumps({key: result[key] for key in ('identity', 'validation_stage', 'build_blocked', 'sdk_capability', 'pending_gates')}, indent=2))
        elif args.command == 'verify':
            result = verify(args.output)
            print(json.dumps(dict(identity=result['identity'], source_closure_verified=True, hardware_accepted=False), indent=2))
        else:
            return build(args.output)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(2, str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
