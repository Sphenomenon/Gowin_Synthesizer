#!/usr/bin/env python3
"""Check asynchronous media hold RTL, regression sensitivity and Gowin mapping."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_synthesis_netlist import SynthesisNetlist

TOP = 'tb_workstation_media_hold_fence'
PROBE = 'workstation_media_hold_probe'
OWNER = ROOT / 'rtl/workstation/workstation_runtime_controlled.sv'
SERVICE = ROOT / 'rtl/services/workstation_controlled_services.sv'
TB = Path(__file__).with_name(TOP + '.sv')
GOWIN = Path('/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE')
PRIMITIVES = GOWIN / 'simlib/gw5a/prim_sim.v'
OLD_BRIDGE_SHA = '1a4a185af2fb420b23d538098c24fc0805c3080b8c87de75d6dfa6149761b976'
NEW_BLOCK = '''    // Both safety conditions asynchronously assert the same preset value.
    // A single async preset maps to real FFs; mixed async clear/preset made
    // the Gowin mapper infer combinational feedback for these two bits.
    wire hold_assert=!reset_ni || hold_50;
    always @(posedge compute_clk_i or posedge hold_assert)
        if(hold_assert)hold_compute<=2'b11;
        else hold_compute<={hold_compute[0],1'b0};'''
OLD_BLOCK = '''    always @(posedge compute_clk_i or posedge hold_50 or negedge reset_ni)
        if(!reset_ni)hold_compute<=0;
        else if(hold_50)hold_compute<=2'b11;
        else hold_compute<={hold_compute[0],1'b0};'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(body, before, after):
    assert body.count(before) == 1, 'Exact mutation/extraction anchor drift: ' + before
    return body.replace(before, after)


def execute(argv, directory, label, timeout=60, env=None):
    log = directory / (label + '.log')
    with log.open('w') as stream:
        process = subprocess.run(argv, cwd=directory, env=env, stdout=stream,
                                 stderr=subprocess.STDOUT, timeout=timeout)
    return dict(argv=list(map(str, argv)), returncode=process.returncode,
                log=str(log), log_sha256=sha(log))


def simulate(output, name, owner=OWNER, mapped=None, expected=None):
    directory = output / name
    directory.mkdir()
    argv = ['iverilog', '-g2012', '-s', TOP, '-o', str(directory / 'simulation.vvp')]
    if mapped:
        argv += ['-DMEDIA_HOLD_MAPPED', str(mapped)]
    argv += list(map(str, [owner, SERVICE, TB]))
    if mapped:
        argv.append(str(PRIMITIVES))
    compilation = execute(argv, directory, 'compile')
    assert compilation['returncode'] == 0, Path(compilation['log']).read_text()[-6000:]
    run = execute(['vvp', str(directory / 'simulation.vvp')], directory, 'run')
    log = Path(run['log']).read_text()
    result = dict(compile=compilation, run=run)
    if expected:
        result.update(expected_failure=expected,
                      rejected=run['returncode'] != 0 and expected in log)
        assert result['rejected'], 'Mutant escaped or unrelated failure: ' + name + '\n' + log
    else:
        assert run['returncode'] == 0 and 'PASS media_hold_fence:' in log, log
        result['metrics'] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', log)}
        assert result['metrics']['cases'] == 8, log
    return result


def extract_bridge(body):
    match = re.search(r'^module workstation_runtime_media_stop_bridge\b.*?^endmodule\n', body, re.M | re.S)
    assert match, 'Media bridge missing'
    return '`timescale 1ns/1ps\n' + match[0]


def probe_wrapper(bridge):
    header = bridge[bridge.index('module workstation_runtime_media_stop_bridge'):bridge.index(');') + 2]
    header = replace_once(header, 'module workstation_runtime_media_stop_bridge #(parameter bit ENABLE=0)',
                          'module ' + PROBE).replace('output reg', 'output wire')
    return header + '\n    workstation_runtime_media_stop_bridge #(.ENABLE(1)) bridge(.*);\nendmodule\n'


def synthesize(output, old, new):
    # Shared with the full build. Never run a second proprietary-tool process
    # when another owner has this lock, even for this small isolated probe.
    with open('/private/tmp/gw138k-build.lock', 'a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        paths = []
        for label, body in [('original', old), ('proposal', new)]:
            directory = output / ('gowin-' + label)
            directory.mkdir()
            source, probe, script = (directory / name for name in ('bridge.sv', 'probe.sv', 'run.tcl'))
            source.write_text(body)
            probe.write_text(probe_wrapper(body))
            script.write_text(f'''cd {{{directory}}}
set_device GW5AST-LV138PG484AC2/I1 -device_version C
set_option -synthesis_tool gowinsynthesis
set_option -top_module {PROBE}
set_option -output_base_name {PROBE}
set_option -verilog_std sysv2017
add_file -type verilog {{{source}}}
add_file -type verilog {{{probe}}}
run syn
''')
            env = dict(os.environ, DYLD_LIBRARY_PATH=str(GOWIN / 'lib'), DYLD_FRAMEWORK_PATH=str(GOWIN / 'lib'))
            result = execute([str(GOWIN / 'bin/gw_sh'), str(script)], directory, 'launch', 180, env)
            assert result['returncode'] == 0, Path(result['log']).read_text()[-6000:]
            paths.append(directory)
        return paths


def mapping_audit(directory, expected_bridge, original):
    source, probe = directory / 'bridge.sv', directory / 'probe.sv'
    assert source.read_text() == expected_bridge, 'Gowin bridge source does not match sealed source'
    assert probe.read_text() == probe_wrapper(expected_bridge), 'Gowin wrapper drift'
    script = (directory / 'run.tcl').read_text()
    required = ['set_device GW5AST-LV138PG484AC2/I1 -device_version C',
                'set_option -synthesis_tool gowinsynthesis', 'set_option -top_module ' + PROBE,
                'set_option -output_base_name ' + PROBE, 'set_option -verilog_std sysv2017', 'run syn']
    assert all(line in script.splitlines() for line in required), 'Gowin configuration drift'
    assert re.findall(r'^add_file -type verilog \{(.*?)\}$', script, re.M) == list(map(str, [source, probe]))
    log = directory / ('impl/gwsynthesis/' + PROBE + '.log')
    vg = directory / ('impl/gwsynthesis/' + PROBE + '.vg')
    assert log.read_text().rstrip().endswith('GowinSynthesis finish'), 'Gowin synthesis incomplete'
    assert '//Tool Version "V1.9.12"' in vg.read_text(), 'Gowin version drift'
    launch = directory / ('launch.log' if (directory / 'launch.log').is_file() else 'run.log')
    assert 'current device: GW5AST-138C  GW5AST-LV138PG484AC2/I1' in launch.read_text()
    assert launch.read_text().rstrip().endswith('GowinSynthesis finish'), 'Gowin launch incomplete'
    parsed = SynthesisNetlist(vg.read_text(), PROBE)
    loops = []
    lut_drivers = {parsed.pin(p, 'F'): p for p, c in parsed.cells.items() if re.fullmatch(r'LUT\d+', c['kind'])}
    graph = {p: [lut_drivers[parsed.pin(p, port)] for port in c['ports']
                 if re.fullmatch(r'I\d+', port) and parsed.pin(p, port) in lut_drivers]
             for p, c in parsed.cells.items() if re.fullmatch(r'LUT\d+', c['kind'])}
    def visit(node, path):
        for dependency in graph[node]:
            if dependency in path:
                cycle = path[path.index(dependency):]
                normalized = min(tuple(cycle[i:] + cycle[:i]) for i in range(len(cycle)))
                if normalized not in loops:
                    loops.append(normalized)
            else:
                visit(dependency, path + [dependency])
    for node in graph:
        visit(node, [node])
    notices = {name: len(re.findall(r'\(' + name + r'\)', log.read_text())) for name in ('AG0100', 'AG0101')}
    result = dict(directory=str(directory), input_sha256={str(p): sha(p) for p in [source, probe, directory / 'run.tcl', log, vg, launch]},
                  synthesis_log=str(log), synthesis_log_sha256=sha(log), netlist=str(vg), netlist_sha256=sha(vg),
                  launch_log=str(launch), launch_log_sha256=sha(launch),
                  ag_notices=notices, lut_cycles=[list(cycle) for cycle in sorted(loops)])
    if original:
        assert notices == dict(AG0100=6, AG0101=2) and len(loops) == 2, result
        feedback = []
        for cycle in loops:
            assert len(cycle) == 1 and 'hold_compute' in cycle[0], cycle
            path = cycle[0]
            cell = parsed.cells[path]
            assert cell['kind'] == 'LUT3' and cell['parameters']['INIT'].upper() == "8'HE0", cell
            assert parsed.pin(path, 'F') == parsed.pin(path, 'I0'), cell
            # For reset=1, hold_50=0 the LUT output equals its own input.
            assert [(0xE0 >> (i0 + 0 * 2 + 1 * 4)) & 1 for i0 in (0, 1)] == [0, 1]
            feedback.append(dict(path=path, cell=cell, self_feedback_pin='I0', reset_high_hold_low='F=I0'))
        result['hold_feedback'] = feedback
    else:
        assert notices == dict(AG0100=0, AG0101=0) and not loops, result
        assert not re.search(r'^WARN\s', log.read_text(), re.M), 'New isolated synthesis warning'
        hold = {p: c for p, c in parsed.cells.items() if 'hold_compute' in p}
        assert len(hold) == 2 and all(c['kind'] == 'DFFPE' for c in hold.values()), hold
        first, second = sorted(hold)
        assert parsed.pin(first, 'CLK') == parsed.pin(second, 'CLK') == 'compute_clk_i'
        assert parsed.pin(second, 'D') == parsed.pin(first, 'Q')
        assert parsed.pin(second, 'Q') == parsed.pin('local_hold_o_obuf', 'I')
        ground = [parsed.pin(p, 'G') for p, c in parsed.cells.items() if c['kind'] == 'GND']
        power = [parsed.pin(p, 'V') for p, c in parsed.cells.items() if c['kind'] == 'VCC']
        assert parsed.pin(first, 'D') in ground
        assert all(parsed.pin(p, 'CE') in power for p in hold)
        preset = parsed.pin(first, 'PRESET')
        assert parsed.pin(second, 'PRESET') == preset
        driver = lut_drivers[preset]
        cell = parsed.cells[driver]
        assert cell['kind'] == 'LUT2' and cell['parameters']['INIT'].upper() == "4'HB", cell
        assert parsed.pin(driver, 'I1') == 'reset_ni'
        hold50 = [p for p, c in parsed.cells.items() if c['kind'].startswith('DFF')
                  and parsed.pin(p, 'Q') == parsed.pin(driver, 'I0')]
        assert len(hold50) == 1 and 'hold_50' in hold50[0]
        truth = [dict(reset_n=reset, hold_50=level, preset=(0xB >> (level + reset * 2)) & 1)
                 for reset in (0, 1) for level in (0, 1)]
        assert all(row['preset'] == int(not row['reset_n'] or row['hold_50']) for row in truth)
        model = re.search(r'^module DFFPE\b.*?^endmodule', PRIMITIVES.read_text(), re.M | re.S)[0]
        assert "parameter INIT = 1'b1" in model and 'always @(gsrt or PRESET)' in model
        assert re.search(r"else if\(PRESET\)\s+assign Q_reg = 1'b1;", model)
        result.update(hold_endpoints={p: dict(kind=c['kind'], pins={pin: parsed.pin(p, pin) for pin in c['ports']})
                                      for p, c in hold.items()}, preset_driver=driver, preset_truth_table=truth,
                      official_dffpe_init=1, primitive_library_sha256=sha(PRIMITIVES))
    return result, vg


def attach_verification(path):
    data = json.loads(path.read_text())
    assert data['passed'] and not data['hardware_tested'], 'Unsuccessful or unexpected attached validation'
    hashes = data['input_sha256']
    inputs = {key: Path(data.get('input_paths', {}).get(key, key)) for key in hashes}
    assert all(p.is_file() and sha(p) == hashes[key] for key, p in inputs.items()), 'Attached source evidence drift: ' + str(path)
    runtime = [hashes[k] for k in hashes if k.endswith('/rtl/workstation/workstation_runtime_controlled.sv')]
    assert runtime == [sha(OWNER)], 'Attached runtime source does not match'
    return dict(path=str(path), sha256=sha(path), identity=data['identity'], input_count=len(inputs),
                all_inputs_rehashed=True, runtime_sha256=runtime[0], metrics=data.get('metrics', {}),
                negative_controls=len(data.get('negative_controls', [])), hardware_tested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gowin', action='store_true', help='Run isolated synthesis under shared nonblocking lock')
    parser.add_argument('--gowin-original', type=Path, help='Reuse sealed original isolated synthesis directory')
    parser.add_argument('--gowin-proposal', type=Path, help='Reuse sealed fixed isolated synthesis directory')
    parser.add_argument('--attach-verification', type=Path, action='append', default=[])
    args = parser.parse_args()
    assert bool(args.gowin_original) == bool(args.gowin_proposal), 'Supply both synthesis directories'
    assert not (args.gowin and args.gowin_original), 'Choose fresh or existing isolated synthesis'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    paths = [OWNER, SERVICE, TB, Path(__file__).resolve(), ROOT / 'rtl/services/MEDIA_STOP_POLICY.md',
             ROOT / 'tools/workstation_synthesis_netlist.py']
    if args.gowin or args.gowin_original:
        paths.append(PRIMITIVES)
    hashes = {str(path): sha(path) for path in paths}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    verification = dict(schema=1, passed=False, hardware_tested=False,
                        identity='runtime-media-hold-fence-offline-v1-' + identity[:16],
                        source_set_sha256=identity, input_sha256=hashes,
                        validation_stage='unit-CDC-fence-with-actual-REC-owner-and-isolated-Gowin-mapping',
                        limits='Local completion, TF pending/terminal and physical quiet are unit fixtures. Actual REC_ENABLE owner is real. Attached joint tests cover real backends separately. Mapped simulation uses zero-delay official functional primitives; no recovery/removal, metastability, routed timing/CDC/PLL, full-board synthesis or hardware acceptance.')
    try:
        verification['tools'] = {name: execute([name, '--version' if name == 'verilator' else '-V'], output, name + '-version')
                                 for name in ('verilator', 'iverilog', 'vvp')}
        verification['positive'] = simulate(output, 'positive')
        lint = execute(['verilator', '--lint-only', '--timing', '-Wno-fatal', '--top-module', TOP,
                        str(OWNER), str(SERVICE), str(TB)], output, 'lint')
        warnings = re.findall(r'^%Warning-.*', Path(lint['log']).read_text(), re.M)
        assert lint['returncode'] == 0 and not warnings, Path(lint['log']).read_text()
        verification['lint'] = dict(**lint, warnings=warnings)
        original = OWNER.read_text()
        assert original.count(NEW_BLOCK) == 1, 'Hold implementation drift'
        mutations = [
            ('synchronous-only-hold', NEW_BLOCK,
             '''    always @(posedge compute_clk_i or negedge reset_ni)
        if(!reset_ni)hold_compute<=2'b11;
        else if(hold_50)hold_compute<=2'b11;
        else hold_compute<={hold_compute[0],1'b0};''',
             'asynchronous media hold waited for a stopped compute clock'),
            ('one-edge-release', "else hold_compute<={hold_compute[0],1'b0};", "else hold_compute<=2'b00;",
             'hold release used fewer than two compute edges'),
            ('cpu-reset-in-hold', 'wire hold_assert=!reset_ni || hold_50;',
             'wire hold_assert=!reset_ni || !owner_reset_ni || hold_50;', 'CPU-only reset changed idle hold'),
            ('old-mixed-clear-preset', NEW_BLOCK, OLD_BLOCK,
             'common reset did not asynchronously assert conservative hold'),
        ]
        verification['negative_controls'] = []
        for name, before, after, marker in mutations:
            mutant = output / (name + '.sv')
            mutant.write_text(replace_once(original, before, after))
            result = simulate(output, name, owner=mutant, expected=marker)
            verification['negative_controls'].append(dict(name=name, mutant_sha256=sha(mutant), **result))
        new = extract_bridge(original)
        old = replace_once(new, NEW_BLOCK, OLD_BLOCK)
        assert hashlib.sha256(old.encode()).hexdigest() == OLD_BRIDGE_SHA, 'Original bridge identity drift'
        verification['bridge_sha256'] = dict(original=OLD_BRIDGE_SHA, fixed=hashlib.sha256(new.encode()).hexdigest())
        if args.gowin or args.gowin_original:
            directories = synthesize(output, old, new) if args.gowin else [args.gowin_original.resolve(), args.gowin_proposal.resolve()]
            old_result, _ = mapping_audit(directories[0], old, True)
            new_result, netlist = mapping_audit(directories[1], new, False)
            verification['gowin'] = dict(original=old_result, fixed=new_result,
                                        reused_existing_evidence=not args.gowin,
                                        tool_executable=str(GOWIN / 'bin/gw_sh'), tool_sha256=sha(GOWIN / 'bin/gw_sh'),
                                        tool_version='GowinSynthesis V1.9.12', device='GW5AST-LV138PG484AC2/I1', device_version='C')
            mapped = replace_once(netlist.read_text(), 'module workstation_runtime_media_stop_bridge (',
                                  'module mapped_workstation_runtime_media_stop_bridge (')
            mapped = replace_once(mapped, '  workstation_runtime_media_stop_bridge bridge (',
                                  '  mapped_workstation_runtime_media_stop_bridge bridge (')
            target = output / 'mapped-fixed.v'
            target.write_text(mapped)
            verification['mapped_positive'] = dict(mapped_sha256=sha(target), **simulate(output, 'mapped-positive', mapped=target))
            broken = output / 'mapped-one-edge.v'
            before = '''  DFFPE hold_compute_1_s0 (
    .Q(local_hold_o_d),
    .D(hold_compute[0]),'''
            broken.write_text(replace_once(mapped, before, before.replace('.D(hold_compute[0])', '.D(GND)')))
            verification['mapped_negative'] = dict(mapped_sha256=sha(broken),
                **simulate(output, 'mapped-one-edge-release', mapped=broken,
                           expected='hold release used fewer than two compute edges'))
            verification['gowin']['evidence_unchanged_during_audit'] = all(
                sha(Path(p)) == digest for result in (old_result, new_result)
                for p, digest in result['input_sha256'].items())
            assert verification['gowin']['evidence_unchanged_during_audit'], 'Gowin evidence drift'
        verification['attached_regressions'] = [attach_verification(p.resolve()) for p in args.attach_verification]
        verification['inputs_unchanged_during_run'] = hashes == {str(path): sha(path) for path in paths}
        assert verification['inputs_unchanged_during_run'], 'Source drift during run'
        verification['passed'] = True
        print(json.dumps(dict(identity=verification['identity'], passed=True,
                              metrics=verification['positive']['metrics'],
                              rtl_negative_controls=len(verification['negative_controls']),
                              gowin_verified='gowin' in verification), indent=2))
    finally:
        (output / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n')


if __name__ == '__main__':
    main()
