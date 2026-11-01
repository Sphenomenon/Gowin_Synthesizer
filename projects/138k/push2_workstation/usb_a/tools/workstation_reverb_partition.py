#!/usr/bin/env python3
"""Prepare matched reverb partition synthesis experiments, never production builds.

Only explicit ``--synthesize`` runs Gowin synthesis. There is no P&R, pinout,
bitstream or programming path. Integrate validated RTL through the existing
workstation profiles; retire these subsystem experiments after whole-system
resource/timing comparisons have replaced them.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_synthesis_netlist import SynthesisNetlist

BASELINE = 'resource_rework_route0'
LOCKED = ('legacy/rtl/audio/audio_math_pkg.sv',
          'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv')
ACTIVE = ('rtl/audio/workstation_runtime_stereo_effects.sv',
          'rtl/audio/workstation_runtime_chorus_effect.sv',
          'rtl/audio/workstation_runtime_spatial_reverb.sv',
          'rtl/audio/runtime_spatial_room_preset.svh',
          'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv',
          'rtl/music/music_async_fifo.sv',
          'rtl/audio/workstation_remote_reverb_m.sv',
          'rtl/audio/workstation_remote_reverb_w.sv')
TOOLS = ('tools/workstation_reverb_partition.py', 'tools/workstation_baselines.py',
         'tools/workstation_synthesis_netlist.py')
CHAIN = 'rtl/audio/workstation_runtime_stereo_effects.sv'
WORKER = 'rtl/audio/workstation_remote_reverb_w.sv'
CONFIG = dict(device='GW5AST-LV138PG484AC2/I1', device_version='C',
              synthesis_tool='gowinsynthesis', verilog_std='sysv2017',
              compute_clock_hz=76800000, compute_period_ns='13.020833333',
              remote_deadline_cycles=512, worker_timeout_cycles=256,
              vector_enable=1, d_delay_send_enable=1,
              remote_macro='WORKSTATION_REMOTE_REVERB_PARTITION')
CASES = ('local', 'm_remote', 'w_reverb')


def require(value, message):
    if not value:
        raise ValueError('reverb partition experiment: ' + message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def interface(text, name):
    """Copy the maintained ANSI interface; do not maintain a reduced test API."""
    match = re.search(r'\bmodule\s+' + re.escape(name) + r'\b\s*', text)
    require(match is not None, 'module missing: ' + name)
    offset = match.end()

    def group(start):
        require(text[start] == '(', 'ANSI interface changed: ' + name)
        depth = 1
        for end in range(start + 1, len(text)):
            depth += (text[end] == '(') - (text[end] == ')')
            if not depth:
                return text[start + 1:end], end + 1
        raise ValueError('unterminated ANSI interface: ' + name)

    if text[offset] == '#':
        offset += 1
        while text[offset].isspace():
            offset += 1
        _, offset = group(offset)
        while text[offset].isspace():
            offset += 1
    ports, _ = group(offset)
    return re.sub(r'\b(input|output|inout)\s+(?:logic|reg)\b', r'\1 wire', ports)


def wrapper(case, payload):
    worker = case == 'w_reverb'
    module = 'workstation_remote_reverb_w' if worker else 'workstation_runtime_stereo_effects'
    top = 'reverb_partition_worker_top' if worker else 'reverb_partition_chain_top'
    parameters = '.PROCESS_TIMEOUT_CYCLES(256)' if worker else (
        '.VECTOR_ENABLE(1),.D_DELAY_SEND_ENABLE(1),.REMOTE_REVERB_ENABLE(' +
        ('1' if case == 'm_remote' else '0') + '),.REMOTE_REVERB_DEADLINE_CYCLES(512)')
    return ('`define WORKSTATION_REMOTE_REVERB_PARTITION\nmodule ' + top + ' (' +
            interface(payload.decode(), module) + '\n);\n' + module + ' #(' +
            parameters + ') dut (.*);\nendmodule\n'), top


def case_sources(case):
    if case == 'w_reverb':
        return (*LOCKED, 'rtl/audio/workstation_runtime_spatial_reverb.sv', WORKER)
    return (*LOCKED, CHAIN, 'rtl/audio/workstation_runtime_chorus_effect.sv',
            'rtl/audio/workstation_runtime_spatial_reverb.sv',
            'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv',
            'rtl/music/music_async_fifo.sv', 'rtl/audio/workstation_remote_reverb_m.sv')


def tcl_path(path):
    value = str(path)
    require(not any(char in value for char in '{}\n\r'), 'unsupported Tcl path')
    return '{' + value + '}'


def script(case, directory, top):
    lines = ['set_device ' + CONFIG['device'] + ' -device_version C',
             'set_option -synthesis_tool gowinsynthesis',
             'set_option -verilog_std sysv2017',
             'set_option -top_module ' + top,
             'set_option -output_base_name partition',
             'set_option -include_path ' + tcl_path(directory.parent / 'sources'),
             'set_option -verilog_define {WORKSTATION_REMOTE_REVERB_PARTITION}']
    lines.extend('add_file -type verilog ' + tcl_path(directory.parent / 'sources' / name)
                 for name in case_sources(case))
    lines += ['add_file -type verilog ' + tcl_path(directory / 'binding.sv'),
              'add_file -type sdc ' + tcl_path(directory / 'experiment.sdc'), 'run syn']
    return '\n'.join(lines) + '\n'


def clocks(case):
    text = 'create_clock -name audio_compute -period ' + CONFIG['compute_period_ns'] + ' [get_ports {clk_i}]\n'
    if case != 'w_reverb':
        text += 'create_clock -name memory_model -period ' + CONFIG['compute_period_ns'] + ' [get_ports {mem_clk_i}]\n'
    return text


def source_bundle(root):
    baseline = load_baseline(root, BASELINE)
    payloads = {name: baseline.read_bytes(name) for name in LOCKED}
    payloads.update({name: (root / name).read_bytes() for name in ACTIVE})
    records = {name: dict(origin='locked_baseline' if name in LOCKED else 'maintained_rtl',
                          sha256=digest(payload), bytes=len(payload))
               for name, payload in payloads.items()}
    return payloads, records, baseline.evidence()


def prepare(output, root=ROOT):
    output, root = Path(output).resolve(), Path(root).resolve()
    require(not output.exists(), 'output must not exist')
    repository = root.parents[3]
    require(output != repository and repository not in output.parents,
            'generated evidence must be outside the source repository')
    payloads, records, baseline = source_bundle(root)
    tools = {name: sha(root / name) for name in TOOLS}
    require('REMOTE_REVERB_ENABLE' in payloads[CHAIN].decode(), 'remote chain integration missing')
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    output.mkdir(parents=True)
    for name, data in payloads.items():
        path = output / 'sources' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    case_records = {}
    for case in CASES:
        directory = output / case
        directory.mkdir()
        binding, top = wrapper(case, payloads[WORKER if case == 'w_reverb' else CHAIN])
        files = {'binding.sv': binding, 'run.tcl': script(case, directory, top), 'experiment.sdc': clocks(case)}
        for name, text in files.items():
            (directory / name).write_text(text)
        case_records[case] = dict(top=top, compiled_sources=list(case_sources(case)),
                                 generated_sha256={name: sha(directory / name) for name in files})
    manifest = dict(schema=1, stage='prepared_subsystem_experiment', source_root=str(root),
                    source_commit=source_commit, source_files=records, tools_sha256=tools,
                    baseline=baseline, configuration=CONFIG, cases=case_records,
                    source_policy='explicit_maintained_effects_and_locked_support_only',
                    PNR=False, bitstream_generated=False, hardware_tested=False,
                    synthesis_resources_are_not_routed_physical_resources=True,
                    integration_exit='select reviewed RTL through existing workstation profiles; replace with whole-system evidence')
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (output / 'manifest.sha256').write_text(sha(output / 'manifest.json') + '\n')
    verify(output, root)
    return manifest


def verify(output, root=ROOT):
    output, root = Path(output).resolve(), Path(root).resolve()
    manifest = json.loads((output / 'manifest.json').read_text())
    require(sha(output / 'manifest.json') == (output / 'manifest.sha256').read_text().strip(), 'manifest identity drifted')
    require(manifest.get('schema') == 1 and manifest.get('source_root') == str(root), 'manifest source/schema mismatch')
    require(manifest.get('configuration') == CONFIG, 'configuration drifted')
    payloads, records, baseline = source_bundle(root)
    require(manifest.get('source_files') == records, 'source manifest omitted or modified an input')
    require(manifest.get('baseline') == baseline, 'baseline manifest changed')
    require(manifest.get('tools_sha256') == {name: sha(root / name) for name in TOOLS}, 'tool input drifted')
    require(set(manifest.get('cases', {})) == set(CASES), 'matched case inventory changed')
    staged = {path.relative_to(output / 'sources').as_posix() for path in (output / 'sources').rglob('*') if path.is_file()}
    require(staged == set(payloads), 'staged source inventory changed')
    for name, data in payloads.items():
        require((output / 'sources' / name).read_bytes() == data, 'staged source drifted: ' + name)
    for case in CASES:
        directory = output / case
        binding, top = wrapper(case, payloads[WORKER if case == 'w_reverb' else CHAIN])
        files = {'binding.sv': binding, 'run.tcl': script(case, directory, top), 'experiment.sdc': clocks(case)}
        expected = dict(top=top, compiled_sources=list(case_sources(case)),
                        generated_sha256={name: digest(text.encode()) for name, text in files.items()})
        require(manifest['cases'][case] == expected, 'case configuration/source manifest drifted: ' + case)
        for name, text in files.items():
            require((directory / name).read_bytes() == text.encode(), 'generated input drifted: ' + case + '/' + name)
    return manifest


def census(text, top):
    netlist = SynthesisNetlist(text, top)
    leaves = {path: cell for path, cell in netlist.cells.items() if cell['kind'] not in netlist.modules}
    counts = Counter(cell['kind'] for cell in leaves.values())
    reverb_frames = sorted(path for path, frame in netlist.frames.items()
                           if frame['kind'].startswith('workstation_runtime_spatial_reverb'))
    reverb_counts = Counter(cell['kind'] for path, cell in leaves.items()
                            if any(path.startswith(frame + '/') for frame in reverb_frames))
    return dict(leaf_primitive_instances=dict(sorted(counts.items())),
                recursive_leaf_instances=len(leaves), reverb_instances=reverb_frames,
                reverb_leaf_primitive_instances=dict(sorted(reverb_counts.items())),
                bsram_primitive_instances={kind: count for kind, count in sorted(counts.items())
                                           if re.match(r'^(?:SDP|DP|SP|ROM|pROM|BSRAM)', kind)},
                resource_scope='emitted_synthesis_primitive_instances_not_routed_physical_BSRAM')


def synthesize(output, gw_sh=None, root=ROOT):
    output = Path(output).resolve()
    manifest = verify(output, root)
    require(not (output / 'synthesis.json').exists(), 'synthesis report already exists; use a new experiment')
    tool = Path(gw_sh or shutil.which('gw_sh') or '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gw_sh').resolve()
    require(tool.is_file(), 'Gowin executable missing')
    tool_identity = sha(tool)
    env = dict(os.environ)
    libraries = tool.parent.parent / 'lib'
    if libraries.is_dir():
        env['DYLD_LIBRARY_PATH'] = str(libraries)
        env['DYLD_FRAMEWORK_PATH'] = str(libraries)
    cases = {}
    for case in CASES:
        directory = output / case
        require(not (directory / 'impl').exists() and not (directory / 'synthesis.log').exists(), 'case already started: ' + case)
        verify(output, root)
        log = directory / 'synthesis.log'
        with log.open('w') as stream:
            result = subprocess.run([str(tool), str(directory / 'run.tcl')], cwd=directory, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
        text = log.read_text()
        require(result.returncode == 0 and 'GowinSynthesis finish' in text and not re.search(r'^ERROR\b', text, re.M), 'synthesis failed: ' + case)
        vg = directory / 'impl/gwsynthesis/partition.vg'
        require(vg.is_file() and vg.stat().st_size > 0, 'actual emitted VG missing: ' + case)
        vg_text = vg.read_text()
        version = re.search(r'//Tool Version "([^"\n]+)"', vg_text)
        require(version is not None, 'emitted tool version missing: ' + case)
        resources = census(vg_text, manifest['cases'][case]['top'])
        require(len(resources['reverb_instances']) == (0 if case == 'm_remote' else 1), 'actual reverb ownership mismatch: ' + case)
        cases[case] = dict(returncode=result.returncode, tool_version=version[1],
                           VG_sha256=sha(vg), log_sha256=sha(log), resources=resources,
                           artifacts_sha256={path.relative_to(directory).as_posix(): sha(path)
                                              for path in sorted(directory.rglob('*')) if path.is_file()})
    verify(output, root)
    require(sha(tool) == tool_identity, 'Gowin executable changed during synthesis')
    kinds = set(cases['local']['resources']['leaf_primitive_instances']) | set(cases['m_remote']['resources']['leaf_primitive_instances'])
    delta = {kind: cases['m_remote']['resources']['leaf_primitive_instances'].get(kind, 0) -
             cases['local']['resources']['leaf_primitive_instances'].get(kind, 0) for kind in sorted(kinds)}
    report = dict(schema=1, stage='actual_subsystem_synthesis_only', passed=True,
                  manifest_sha256=sha(output / 'manifest.json'), tool=str(tool), tool_sha256=tool_identity,
                  configuration=CONFIG, cases=cases, m_remote_minus_local_primitive_instances=delta,
                  PNR=False, timing_accepted=False, physical_BSRAM_count=None,
                  hardware_tested=False, bitstream_generated=False, production_profile_selected=False,
                  limitations='Dynamic subsystem ports prevent fixed-input pruning; no whole-workstation resource, timing, LCD or hardware acceptance.')
    (output / 'synthesis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify', 'synthesize'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--synthesize', action='store_true', help='explicitly run synthesis after prepare')
    parser.add_argument('--gw-sh', type=Path)
    args = parser.parse_args()
    require(not args.synthesize or args.action == 'prepare', '--synthesize only applies to prepare')
    if args.action == 'prepare':
        prepare(args.output)
    elif args.action == 'verify':
        verify(args.output)
    if args.action == 'synthesize' or args.synthesize:
        synthesize(args.output, args.gw_sh)
    print(json.dumps(dict(passed=True, action=args.action, output=str(args.output.resolve()),
                          synthesis=args.action == 'synthesize' or args.synthesize, PNR=False)))


if __name__ == '__main__':
    main()
