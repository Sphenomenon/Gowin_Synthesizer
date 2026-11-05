#!/usr/bin/env python3
"""Compare the recording fault boundary in two hash-pinned W synthesis netlists.

This is a local combinational consumer proof. Other tag consumers, resets,
metastability and routed timing require their separate complete audits.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_pcm_cdc import Graph, PcmNetlist
from tools.workstation_recording_phase1_cdc import complete_closure


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inspect(path, expected):
    require(sha(path) == expected, 'input VG identity differs: ' + str(path))
    n = PcmNetlist(path.read_text(), 'workstation_custom_138k_top')
    g = Graph(n)
    tags = sorted(p for p in g.regs if p.startswith('u_task3_media/memory/u_arbiter/')
                  and '/g_recording.tags[' in p)
    require(len(tags) == 128, 'recording tag register inventory changed')
    # The physical SDC names this clock ddr_ui100; the actual VG net is
    # memory_clk. Inspect the connection rather than substituting a STA name.
    require(all(n.pin(p, 'CLK') == 'memory_clk' for p in tags),
            'recording tags are not exclusively on the native memory clock net')
    closure = complete_closure(n, g, tags)
    target = {p: clock for p, clock in closure['ff_endpoints'].items()
              if p.startswith('u_bluetooth/u_core/application/command_endpoint/recording/')}
    first = g.register('u_task3_media', 'ready_control', 0)
    last = g.register('u_task3_media', 'ready_control', 1)
    first_closure = complete_closure(n, g, [first])
    require(n.pin(first, 'CLK') == n.pin(last, 'CLK') == 'clk_50m',
            'control ready synchronizer clock differs')
    require(n.pin(last, 'D') == n.pin(first, 'Q'), 'ready synchronizer chain differs')
    require(first_closure['ff_endpoints'] == {last + '/D': 'clk_50m'}
            and not first_closure['primitive_endpoints']
            and not first_closure['top_output_endpoints'],
            'first ready stage drives a consumer other than final stage D')
    require(n.pin(first, 'CE') in g.high and n.pin(last, 'CE') in g.high,
            'ready synchronizer has a gated enable')
    require(first + '/D' in closure['ff_endpoints'],
            'native tag fault no longer reaches first ready synchronizer')
    return dict(VG=dict(path=str(path), sha256=expected),
                lexical_connection_audit=n.lexical_connection_audit,
                tag_source_registers=tags, tag_source_clock_net='memory_clk',
                tag_to_BLE_recording_FF_endpoints=target, tag_full_closure=closure,
                first_ready_stage=first, final_ready_stage=last,
                first_ready_stage_complete_closure=first_closure,
                final_ready_stage_complete_closure=complete_closure(n, g, [last]),
                ready_chain_direct_clock_and_CE_verified=True,
                first_stage_has_only_final_D_consumer=True)


def run(before, after, before_sha, after_sha, output):
    output.mkdir(parents=True, exist_ok=False)
    inputs = [before, after, Path(__file__).resolve(), *(ROOT / p for p in (
        'tools/workstation_synthesis_netlist.py', 'tools/workstation_runtime_pcm_cdc.py',
        'tools/workstation_recording_phase1_cdc.py'))]
    seals = {str(p): sha(p) for p in inputs}
    result = dict(schema=1, passed=False, input_sha256=seals,
                  scope='Recording-tag combinational consumer delta and local ready synchronizer only',
                  complete_CDC_accepted=False, routed_timing_verified=False, hardware_operated=False)
    try:
        require(before_sha != after_sha, 'before/after VG must be distinct')
        result['before'] = inspect(before, before_sha)
        result['after'] = inspect(after, after_sha)
        old = result['before']['tag_to_BLE_recording_FF_endpoints']
        new = result['after']['tag_to_BLE_recording_FF_endpoints']
        require(bool(old), 'baseline did not reproduce the DDR-to-BLE recording bypass')
        require(not new, 'DDR-to-BLE recording combinational bypass remains')
        require(all(sha(Path(p)) == value for p, value in seals.items()), 'proof input changed')
        result.update(passed=True, inputs_unchanged=True,
                      changed_tag_to_BLE_combinational_bypass_absent=True,
                      before_BLE_endpoint_pins=len(old), after_BLE_endpoint_pins=len(new))
        print(json.dumps({k: result[k] for k in (
            'passed', 'before_BLE_endpoint_pins', 'after_BLE_endpoint_pins',
            'complete_CDC_accepted')}, indent=2))
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--after', required=True, type=Path)
    parser.add_argument('--before-sha256', required=True)
    parser.add_argument('--after-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.before.resolve(), args.after.resolve(), args.before_sha256, args.after_sha256,
        args.output.resolve())
