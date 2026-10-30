#!/usr/bin/env python3
"""Actual RTL plus behavioral mutants; all generated evidence stays outside source."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
FLOW = ROOT / 'rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv'
EVENT = ROOT / 'rtl/bluetooth/hci_owner/workstation_hci_event_decoder.sv'
BENCHES = {
    'flow': ROOT / 'sim/tb_workstation_hci_flow_owner.sv',
    'event': ROOT / 'sim/tb_workstation_hci_event_decoder.sv',
}
MUTANTS = (
    ('shared_pool_removed', 'flow', 'shared_pool<=le_acl_count_i==0;', 'shared_pool<=0;'),
    ('stale_generation_accepted', 'flow', 'acl_generation_i != generations[acl_slot]', "1'b0"),
    ('disconnect_credit_lost', 'flow', 'br_available_o<=br_available_o+outstanding[lifecycle_slot];', 'br_available_o<=br_available_o;'),
    ('host_credit_command_blocked', 'flow', '(special_command || (!command_pending_o && command_credits_o != 0));', '(!command_pending_o && command_credits_o != 0);'),
    ('opcode_zero_completes_command', 'flow', "if (response_opcode_i == 16'h0000) begin end", "if (1'b0) begin end"),
    ('timeout_success_race', 'flow', 'else if (command_timeout_i) begin', 'else if (command_timeout_i && !command_response_i) begin'),
    ('outer_event_length_ignored', 'event', "else if(packet_read_address_o==1 && length!={1'b0,packet_read_data_i}+9'd2)fail(F_LENGTH);", "else if(1'b0)fail(F_LENGTH);"),
    ('reserved_handle_bits_truncated', 'event', "lifecycle_handle>16'h0eff", "lifecycle_handle[11:0]>12'heff"),
    ('ncp_handle_validation_removed', 'event', "{packet_read_data_i,pair_handle_low}>16'h0eff)fail(F_HANDLE);", "1'b0)fail(F_HANDLE);"),
    ('le_shared_pool_count_changed', 'event', "{8'd0,prefix[8]} : {prefix[10],prefix[9]}", "16'd1 : {prefix[10],prefix[9]}"),
    ('packet_lifetime_unchecked', 'event', '(!packet_valid_i || packet_length_i != length)) fail(F_LIFETIME);', "1'b0) fail(F_LIFETIME);"),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, cwd, log, expected_success=True):
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=90)
    log.write_text(proc.stdout + proc.stderr)
    if expected_success and proc.returncode:
        raise RuntimeError(f'{args[0]} failed: {log}')
    return proc


def run_case(out, name, bench, flow, event):
    dest = out / name
    dest.mkdir()
    top = f'tb_workstation_hci_{"flow_owner" if bench == "flow" else "event_decoder"}'
    sources = [flow] + ([event] if bench == 'event' else []) + [BENCHES[bench]]
    command(['iverilog', '-g2012', '-s', top, '-o', str(dest / 'bench.vvp'), *map(str, sources)],
            dest, dest / 'compile.log')
    return command(['vvp', str(dest / 'bench.vvp')], dest, dest / 'simulation.log', False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='gw138k-hci-owner-'))
    if out == REPO or REPO in out.parents:
        parser.error('evidence must be outside the source tree')
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        parser.error('evidence directory must be empty')
    report = {'stage': 'unselected_source_only', 'inputs': {}, 'tools': {}, 'baseline': {}, 'mutants': {}}
    for source in [Path(__file__).resolve(), FLOW, EVENT, *BENCHES.values()]:
        report['inputs'][str(source.relative_to(ROOT))] = sha(source)
    for tool in ('iverilog', 'vvp', 'verilator'):
        path = Path(shutil.which(tool) or '')
        if not path.is_file():
            raise RuntimeError(f'missing {tool}')
        result = command([str(path), '-V'], out, out / f'{tool}-version.log', False)
        report['tools'][tool] = {'path': str(path.resolve()), 'sha256': sha(path.resolve()),
                                 'version_log': f'{tool}-version.log', 'version_returncode': result.returncode}
    report['lint'] = {}
    for source in (FLOW, EVENT):
        command(['verilator', '--lint-only', '-Wall', '--top-module', source.stem, str(source)],
                out, out / f'{source.stem}-lint.log')
        report['lint'][source.name] = 'passed_strict_Wall'
    for bench in BENCHES:
        result = run_case(out, f'baseline-{bench}', bench, FLOW, EVENT)
        match = re.search(r'PASS checks=(\d+).*', result.stdout)
        if result.returncode or not match:
            raise RuntimeError(f'{bench} baseline failed: {out}')
        report['baseline'][bench] = {'summary': match.group(), 'checks': int(match[1])}
    for name, kind, before, after in MUTANTS:
        original = FLOW if kind == 'flow' else EVENT
        text = original.read_text()
        # The lifecycle comparison intentionally occurs in two fixed events.
        expected_anchors = 2 if name == 'reserved_handle_bits_truncated' else 1
        if text.count(before) != expected_anchors:
            raise RuntimeError(f'{name}: adaptation anchor drift')
        path = out / f'{name}.sv'
        path.write_text(text.replace(before, after))
        result = run_case(out, name, kind, path if kind == 'flow' else FLOW, path if kind == 'event' else EVENT)
        if result.returncode == 0 or 'FAIL ' not in result.stdout:
            raise RuntimeError(f'{name}: behavior mutant survived or failed without assertion')
        report['mutants'][name] = {'rejected': True, 'mutation_sha256': sha(path),
                                    'failure': next(line for line in result.stdout.splitlines() if line.startswith('FAIL '))}
    report['invalid_parameters'] = {}
    for parameter, value in (('HANDLE_SLOTS', 0), ('HANDLE_SLOTS', 17),
                             ('H5_ACL_DATA_LIMIT', 0), ('H5_ACL_DATA_LIMIT', 277)):
        name = f'{parameter}-{value}'
        executable = out / f'{name}.vvp'
        command(['iverilog', '-g2012', '-s', FLOW.stem, '-P', f'{FLOW.stem}.{parameter}={value}',
                 '-o', str(executable), str(FLOW)], out, out / f'{name}-compile.log')
        result = command(['vvp', str(executable)], out, out / f'{name}-simulation.log', False)
        if result.returncode == 0 or 'unsupported HCI flow owner parameter' not in result.stdout:
            raise RuntimeError(f'{name}: invalid parameter accepted')
        report['invalid_parameters'][name] = 'rejected'
    for name, identity in report['inputs'].items():
        if sha(ROOT / name) != identity:
            raise RuntimeError(f'input changed during verification: {name}')
    report['outputs'] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(out), 'baseline': report['baseline'], 'rejected_mutants': len(MUTANTS)}))


if __name__ == '__main__':
    main()
