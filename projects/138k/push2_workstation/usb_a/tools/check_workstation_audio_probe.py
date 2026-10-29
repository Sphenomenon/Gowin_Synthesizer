#!/usr/bin/env python3
"""Quantify the independent muted probe's actual routed netlist and SDF.

Read-only: no EDA, JTAG, programmer, or GAO process is started. Requirements JSON
is not evidence. SDF bounds are conservative min/max across rise/fall corners;
STA and source/simulation evidence remain separate, complementary gates.
"""
import argparse
from collections import defaultdict, Counter
from datetime import datetime
import fnmatch
import importlib.util
import json
from pathlib import Path
import re
import sys

import workstation_audio_probe as probe


def require(condition, message):
    if not condition:
        raise ValueError(message)


def norm(value):
    return ''.join(value.strip().lstrip('\\').replace('\\/', '/').split())


class Routed:
    def __init__(self, vo, sdf):
        require(re.search(r'\(TIMESCALE\s+1\s*ns\)', sdf), 'SDF must use ns')
        self.cells = {}
        self.graph = defaultdict(list)
        self.c2q = {}
        self.drivers = {}
        for kind, name, body in re.findall(r'^\s*(\w+)\s+(\\\S+|[A-Za-z0-9_]+)\s*\((.*?)\);', vo, re.M | re.S):
            if kind == 'module':
                continue
            name = norm(name)
            pins = {pin: norm(net) for pin, net in re.findall(r'\.(\w+)\s*\(([^)]*)\)', body)}
            require(name not in self.cells, 'Duplicate netlist cell: ' + name)
            self.cells[name] = (kind, pins)
            for pin in ('Q', 'F', 'S', 'O', 'CLKOUT'):
                if pin in pins:
                    self.drivers[pins[pin]] = (name, pin)
        self.sdf_cells = set()
        for kind, name, body in re.findall(r'\(CELL\s+\(CELLTYPE\s+"([^"]+)"\)\s+\(INSTANCE\s*([^)]*)\)(.*?)\n  \)', sdf, re.S):
            name = norm(name)
            if not name:
                continue
            require(name in self.cells and self.cells[name][0] == kind, 'SDF/VO cell mismatch: ' + name)
            self.sdf_cells.add(name)
            for src, dst, delays in re.findall(r'\(IOPATH\s+(\w+)\s+(\w+)((?:\s+\([^()]+\))+)', body):
                values = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', delays)]
                lo, hi = min(values), max(values)
                if kind.startswith('DFF'):
                    if src == 'CLK' and dst == 'Q':
                        self.c2q[name] = (lo, hi)
                else:
                    self.graph[name + '/' + src].append((name + '/' + dst, lo, hi))
        for src, dst, delays in re.findall(r'\(INTERCONNECT\s+(\S+)\s+(\S+)\s+\(([^)]+)\)\)', sdf):
            values = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', delays)]
            self.graph[norm(src)].append((norm(dst), min(values), max(values)))
        require(len(self.sdf_cells) > 5000, 'Incomplete routed SDF')
        self.vo = vo

    def matching(self, pattern):
        return sorted(name for name in self.cells if fnmatch.fnmatchcase(name, pattern))

    def ff(self, name):
        require(name in self.cells and self.cells[name][0].startswith('DFF'), 'Missing sequential cell: ' + name)
        require(name in self.sdf_cells and name in self.c2q, 'Missing sequential delay: ' + name)
        return self.cells[name][1]

    def paths(self, start):
        """All combinational routed paths; sequential cells have no graph arcs."""
        memo, visiting = {}, set()
        def walk(node):
            require(node not in visiting, 'Combinational cycle: ' + node)
            if node in memo:
                return memo[node]
            visiting.add(node)
            result = {node: (0., 0.)}
            for dst, lo, hi in self.graph.get(node, []):
                for target, (rlo, rhi) in walk(dst).items():
                    nlo, nhi = lo + rlo, hi + rhi
                    old = result.get(target)
                    result[target] = (nlo, nhi) if old is None else (min(old[0], nlo), max(old[1], nhi))
            visiting.remove(node)
            memo[node] = result
            return result
        return walk(start)

    def route(self, start, end):
        paths = self.paths(start)
        require(end in paths, 'Missing routed path: ' + start + ' -> ' + end)
        return paths[end]

    def roots(self, net, seen=None):
        seen = set() if seen is None else seen
        require(net not in seen, 'Reset cone cycle: ' + net)
        if net not in self.drivers:
            return {net}
        name, out = self.drivers[net]
        kind, pins = self.cells[name]
        if kind.startswith('DFF'):
            return {net}
        result = set()
        for pin, value in pins.items():
            if pin != out:
                result |= self.roots(value, seen | {net})
        return result


def bounded_pair(model, source, target, clock_root=None, limit=20.):
    model.ff(source); model.ff(target)
    wire_lo, wire_hi = model.route(source + '/Q', target + '/D')
    cq_lo, cq_hi = model.c2q[source]
    result = dict(source=source, target=target, q_to_d_min_ns=round(wire_lo, 6),
                  q_to_d_max_ns=round(wire_hi, 6),
                  clock_to_data_min_ns=round(cq_lo + wire_lo, 6),
                  clock_to_data_max_ns=round(cq_hi + wire_hi, 6))
    require(cq_hi + wire_hi < limit, 'Routed data bound exceeded: ' + source)
    if clock_root:
        clo, chi = model.route(clock_root, source + '/CLK')
        result.update(clock_distribution_min_ns=round(clo, 6), clock_distribution_max_ns=round(chi, 6),
                      root_to_data_min_ns=round(clo + cq_lo + wire_lo, 6),
                      root_to_data_max_ns=round(chi + cq_hi + wire_hi, 6))
        require(chi + cq_hi + wire_hi < limit, 'Gray root-to-data bound exceeded: ' + source)
    return result


def gray_audit(model):
    result = {}
    for monitor, source_clock, clock_root in (
        ('reference_48_monitor', 'clk_12m288_d', 'clk_12m288_ibuf/I'),
        ('reference_44_monitor', 'clk_16m9344_d', 'clk_16m9344_ibuf/I'),
        ('selected_monitor', 'ak_mclk_d', 'audio_domain/selector/CLKOUT')):
        prefix = 'audio_domain/' + monitor + '/'
        require(len(model.matching(prefix + 'source_gray_*_s0')) == 32, 'Gray bit optimized/missing: ' + monitor)
        records = []
        for bit in range(32):
            src, meta, sync = (prefix + f'{name}_{bit}_s0' for name in ('source_gray', 'gray_meta', 'gray_sync'))
            sp, mp, yp = model.ff(src), model.ff(meta), model.ff(sync)
            require(sp['CLK'] == source_clock and mp['CLK'] == yp['CLK'] == 'clk_50mhz_d', 'Gray clock relationship: ' + src)
            require(mp['D'] == sp['Q'] and yp['D'] == mp['Q'], 'Gray synchronizer structure: ' + src)
            model.route(meta + '/Q', sync + '/D')
            records.append(bounded_pair(model, src, meta, clock_root))
        skew = max(x['root_to_data_max_ns'] for x in records) - min(x['root_to_data_min_ns'] for x in records)
        require(skew < 20, 'Gray skew bound exceeded: ' + monitor)
        result[monitor] = dict(surviving_bits=32, optimized_bits=[],
                              conservative_root_arrival_skew_ns=round(skew, 6), bits=records)
    return result


def payload_audit(model):
    require(len(model.matching('snapshot_hold_*_s0')) == 192, 'Held snapshot width changed')
    result = []
    for bit in range(192):
        src, meta, sync = (f'{base}_{bit}_s0' for base in ('snapshot_hold', 'snapshot_payload_meta', 'snapshot_payload_sync'))
        require(model.ff(src)['CLK'] == 'ak_mclk_d', 'Snapshot source clock')
        require(model.ff(meta)['CLK'] == model.ff(sync)['CLK'] == 'clk_50mhz_d', 'Snapshot receiver clock')
        model.route(meta + '/Q', sync + '/D')
        result.append(bounded_pair(model, src, meta))
    return result


def config_audit(model):
    result = [bounded_pair(model, f'audio_domain/transaction/pending_epoch_{bit}_s0', f'serializer/epoch_{bit}_s0') for bit in range(32)]
    modes = [name for name in model.matching('serializer/mode_44k1_s*') if model.cells[name][0].startswith('DFF')]
    require(len(modes) >= 1, 'Missing held mode')
    result += [bounded_pair(model, 'audio_domain/transaction/pending_44k1_s0', dst) for dst in modes]
    for record in result:
        require(model.ff(record['source'])['CLK'] == 'clk_50mhz_d' and model.ff(record['target'])['CLK'] == 'ak_mclk_d', 'Held configuration clock')
    return result


def control_audit(model):
    records = []
    for base in ('quiesce_sync', 'resume_sync', 'snapshot_request_sync', 'quiet_sync', 'prefill_sync', 'running_sync', 'idle_sync', 'snapshot_ack_sync'):
        meta, sync = (base + f'_{bit}_s0' for bit in range(2))
        mp, sp = model.ff(meta), model.ff(sync)
        require(mp['CLK'] == sp['CLK'], 'Single-bit receiver clock: ' + base)
        model.route(meta + '/Q', sync + '/D')
        paths = []
        for root in sorted(model.roots(mp['D'])):
            require(root in model.drivers, 'Unregistered single-bit control root: ' + root)
            source, pin = model.drivers[root]
            require(pin == 'Q', 'Single-bit root is not registered: ' + root)
            paths.append(bounded_pair(model, source, meta))
        require(paths, 'No single-bit first-stage data paths: ' + base)
        records.append(dict(first_stage=meta, second_stage=sync, data_paths=paths))
    for monitor, root in [('reference_48_monitor', 'clk_12m288_ibuf/I'), ('reference_44_monitor', 'clk_16m9344_ibuf/I'), ('selected_monitor', 'audio_domain/selector/CLKOUT')]:
        prefix = 'audio_domain/' + monitor + '/'
        meta, sync = prefix + 'level_meta_s0', prefix + 'level_sync_s0'
        require(model.ff(meta)['CLK'] == model.ff(sync)['CLK'] == 'clk_50mhz_d', 'Level synchronizer clock')
        require(model.ff(sync)['D'] == model.ff(meta)['Q'], 'Level second-stage connection')
        model.route(meta + '/Q', sync + '/D')
        lo, hi = model.route(root, meta + '/D')
        require(hi < 20, 'Source-level first-stage bound')
        records.append(dict(first_stage=meta, second_stage=sync, root=root, max_data_delay_ns=round(hi, 6)))
    return records


def reset_audit(model):
    chains = [(['audio_domain/control_reset_pre_0_s0', 'audio_domain/control_reset_pre_1_s0', 'audio_domain/control_reset_n_s0'], 'clk_50mhz_d', {'restart_n', 'power_ready'}),
              ([f'audio_domain/reset_release_{bit}_s0' for bit in range(3)], 'ak_mclk_d', {'restart_n', 'power_ready', 'audio_domain/requested_audio_reset_n', 'selected_qualified'})]
    for monitor, clock in [('reference_48_monitor', 'clk_12m288_d'), ('reference_44_monitor', 'clk_16m9344_d'), ('selected_monitor', 'ak_mclk_d')]:
        prefix = 'audio_domain/' + monitor + '/'
        chains.append(([prefix + 'source_reset_pre_0_s0', prefix + 'source_reset_pre_1_s0', prefix + 'source_reset_n_s0'], clock, {'audio_domain/control_reset_n'}))
        resetq = model.ff(prefix + 'source_reset_n_s0')['Q']
        for kind in ('source_gray', 'source_binary'):
            for name in model.matching(prefix + kind + '*'):
                require(model.roots(model.ff(name)['CLEAR']) == {resetq}, 'Source counter reset: ' + name)
    records = []
    for names, clock, anchors in chains:
        for index, name in enumerate(names):
            pins = model.ff(name)
            require(pins['CLK'] == clock and pins['CE'] == 'VCC', 'Reset chain clock/enable: ' + name)
            require(pins['D'] == ('VCC' if index == 0 else model.ff(names[index-1])['Q']), 'Reset chain is not three real edges: ' + name)
            require(model.roots(pins['CLEAR']) == anchors, 'Async reset roots: ' + name)
        records.append(dict(cells=names, clock_net=clock, async_roots=sorted(anchors)))
    groups = Counter()
    for name, (kind, pins) in model.cells.items():
        if not kind.startswith('DFF'):
            continue
        reset = pins.get('CLEAR', pins.get('PRESET'))
        require(reset is not None, 'Unreviewed synchronous/unreset register: ' + name)
        roots = model.roots(reset)
        groups[(pins['CLK'], tuple(sorted(roots)))] += 1
        if pins['CLK'] == 'ak_mclk_d' and not name.startswith('audio_domain/'):
            require(roots == {'audio_reset_n'}, 'Selected consumer local reset: ' + name)
        if name.startswith(('snapshot_payload_', 'snapshot_ack_sync_', 'quiet_sync_', 'prefill_sync_', 'running_sync_', 'idle_sync_')):
            require(roots == {'power_ready', 'restart_n'}, 'Return snapshot/ACK global reset: ' + name)
    require(sum(groups.values()) == len(model.c2q), 'Not all sequential reset endpoints audited')
    return dict(three_edge_chains=records, all_sequential_reset_groups=[dict(clock=k[0], roots=list(k[1]), endpoints=v) for k, v in sorted(groups.items())])


def constraint_audit(model, sdc, clock_names, ports):
    records = []
    pins = {name + '/' + pin for name, (_, ps) in model.cells.items() for pin in ps}
    for kind, expressions in re.findall(r'\[get_(regs|pins|ports|clocks)\s+\{([^}]+)\}\]', sdc):
        universe = {'regs': {n for n, (t, _) in model.cells.items() if t.startswith('DFF')}, 'pins': pins, 'ports': set(ports), 'clocks': set(clock_names)}[kind]
        for pattern in expressions.split():
            matched = sorted(x for x in universe if fnmatch.fnmatchcase(x, pattern))
            require(matched, 'Zero-match SDC object: ' + kind + ' ' + pattern)
            records.append(dict(kind=kind, pattern=pattern, matched_count=len(matched)))
    require('set_clock_groups' not in sdc, 'Unreviewed broad clock group')
    false_paths = [x for x in sdc.splitlines() if x.startswith('set_false_path')]
    allowed_hold = {
        'set_false_path -hold -from [get_regs {' + prefix + '/source_gray*}] -to [get_regs {' + prefix + '/gray_meta*}]'
        for prefix in ('audio_domain/reference_48_monitor', 'audio_domain/reference_44_monitor', 'audio_domain/selected_monitor')}
    allowed_hold |= {
        'set_false_path -hold -through [get_pins {quiesce_sync_0_s0/D resume_sync_0_s0/D snapshot_request_sync_0_s0/D}]',
        'set_false_path -hold -through [get_pins {quiet_sync_0_s0/D prefill_sync_0_s0/D running_sync_0_s0/D idle_sync_0_s0/D snapshot_ack_sync_0_s0/D}]',
        'set_false_path -hold -from [get_regs {snapshot_hold*}] -to [get_regs {snapshot_payload_meta*}]',
        'set_false_path -hold -from [get_regs {audio_domain/transaction/pending_epoch* audio_domain/transaction/pending_44k1_s0}] -to [get_regs {serializer/epoch* serializer/mode_44k1*}]',
        'set_false_path -hold -through [get_pins {audio_domain/reference_48_monitor/level_meta_s0/D audio_domain/reference_44_monitor/level_meta_s0/D audio_domain/selected_monitor/level_meta_s0/D}]'}
    require({line for line in false_paths if '-hold' in line} == allowed_hold, 'Changed first-stage hold exception scope')
    max_delays = [line for line in sdc.splitlines() if line.startswith('set_max_delay')]
    require(len(max_delays) == 8 and all(line.startswith('set_max_delay 20 ') for line in max_delays), 'Dropped/relaxed CDC bound')
    for line in false_paths:
        if '-hold' in line:
            require(not any(x in line for x in ('gray_sync', 'payload_sync', 'CLEAR', 'PRESET', 'reset_release', 'control_reset')), 'Reset/second-stage exception: ' + line)
        elif 'get_clocks' in line:
            clocks = re.findall(r'get_clocks \{(\w+)\}', line)
            require(set(clocks) == {'selected48', 'selected44'} and len(clocks) == 2, 'Overbroad clock exception')
        else:
            require(line == 'set_false_path -from [get_ports {restart_n}] -to [get_regs {power_on_count* power_ready_s0}]', 'Unreviewed async exception: ' + line)
    return dict(object_bindings=records, exact_false_paths=false_paths)


def sta_audit(tr):
    clocks = {}
    block = tr.split('\n2.2 Clock Summary\n')[1].split('\n2.3')[0]
    for line in block.splitlines():
        row = line.split()
        if row and row[0].isdigit():
            clocks[row[1]] = dict(type=row[2], period_ns=float(row[3]), source=row[7] if row[2] == 'Generated' else None,
                                  master=row[8] if row[2] == 'Generated' else None, object=row[-1])
    expected = dict(reference50=20, raw48=81.380208, raw44=59.051398, selected48=81.380208, selected44=59.051398, tck_pad_i=50)
    require(set(clocks) == set(expected), 'Dropped or unexpected STA clock')
    for name, period in expected.items():
        require(abs(clocks[name]['period_ns'] - period) < .001, 'Clock period drift: ' + name)
    for name, source, master in [('selected48', 'clk_12m288', 'raw48'), ('selected44', 'clk_16m9344', 'raw44')]:
        require(clocks[name]['source'] == source and clocks[name]['master'] == master and clocks[name]['object'] == 'audio_domain/selector/CLKOUT', 'Generated clock lineage: ' + name)
    for analysis in ('Setup', 'Hold'):
        require(re.findall(r'<Numbers of ' + analysis + r' Violated Endpoints>:\s*(\d+)', tr) == ['0'], analysis + ' violations')
    reports = []
    for match in re.finditer(r'<Report Command>:(report_timing[^\n]*)\n', tr):
        body = tr[match.end():tr.find('\n\n', match.end())]
        rows = [line.split() for line in body.splitlines() if re.match(r'\s+\d+\s+[-\d.]', line)]
        require(rows, 'Empty requested timing table: ' + match[1])
        require(min(float(row[1]) for row in rows) >= 0, 'Negative requested timing slack: ' + match[1])
        reports.append(dict(command=match[1], paths=len(rows), min_slack_ns=min(float(row[1]) for row in rows),
                            endpoints=[row[3] for row in rows], clock_pairs=sorted({(row[4], row[5]) for row in rows})))
    for selector, count in [('reference_48_monitor/source_gray', 32), ('reference_44_monitor/source_gray', 32), ('selected_monitor/source_gray', 32), ('snapshot_hold*', 192), ('pending_epoch*', 33)]:
        matches = [x for x in reports if ' -from ' in x['command'] and selector in x['command'] and x['command'].startswith('report_timing -setup')]
        require(len(matches) == 1 and len(set(matches[0]['endpoints'])) >= count, 'Ineffective CDC bound: ' + selector)
    for mode in ('selected48', 'selected44'):
        for kind in ('setup', 'hold', 'recovery', 'removal'):
            matches = [x for x in reports if x['command'].startswith('report_timing -' + kind + ' -to [get_clocks {' + mode + '}]')]
            require(len(matches) == 1 and matches[0]['paths'] > 0, 'Missing selected-mode timing: ' + mode + '/' + kind)
    pulse = tr.split('\n3.2 Minimum Pulse Width Table\n')[1].split('\n3.3')[0]
    pulse_rows = [line.split() for line in pulse.splitlines() if re.match(r'\s+\d+\s+[-\d.]', line)]
    require(pulse_rows, 'Missing minimum pulse-width table')
    # Table columns are inspected by name, not inferred from the requirements JSON.
    require(all(float(row[1]) >= 0 for row in pulse_rows), 'Minimum pulse-width violation')
    pulse_by_clock = {}
    for row in pulse_rows:
        name = row[-2]
        pulse_by_clock[name] = min(pulse_by_clock.get(name, float('inf')), float(row[1]))
    require({'reference50', 'selected48', 'selected44'} <= set(pulse_by_clock), 'No actual MPW coverage for both selected modes')
    for report in reports:
        del report['endpoints']
    return dict(clocks=clocks, timing_reports=reports, minimum_pulse_width_min_slack_ns=min(float(row[1]) for row in pulse_rows),
                minimum_pulse_width_min_slack_by_clock_ns=pulse_by_clock,
                sdk_mode_query_limitation='Clock-object hold/recovery/removal queries alias the same physical DCS output and report the faster selected44 relation; identical routed endpoints and conservative faster-clock recovery cover selected48. Setup CDC held paths explicitly list both modes; MPW explicitly lists both modes.')


def dcs_audit(model, rpt, logs):
    names = [name for name, (kind, _) in model.cells.items() if kind == 'DCS']
    require(names == ['audio_domain/selector'], 'DCS primitive count/type')
    pins = model.cells[names[0]][1]
    require(pins == dict(SELFORCE='GND', CLKIN0='clk_12m288_d', CLKIN1='clk_16m9344_d', CLKIN2='GND', CLKIN3='GND', CLKSEL='{GND,GND,clock_select[1:0]}', CLKOUT='ak_mclk_d'), 'DCS dedicated source wiring')
    require(re.search(r'defparam\s+\\audio_domain/selector\s*\.DCS_MODE="FALLING";', model.vo), 'DCS FALLING setting')
    select = [model.ff(model.drivers[f'clock_select[{bit}]'][0]) for bit in range(2)]
    require(all(pins['CLK'] == 'clk_50mhz_d' for pins in select) and select[0]['CE'] == select[1]['CE'], 'DCS select is not a common-enable registered control')
    require(select[0].get('PRESET') == select[1].get('CLEAR') and model.roots(select[0]['PRESET']) == {'audio_domain/control_reset_n'}, 'DCS select reset must be onehot48')
    for net in ('clk_12m288_d', 'clk_16m9344_d', 'ak_mclk_d'):
        require(re.search(r'^\s*' + net + r'\s*\|\s*PRIMARY\s*\|', rpt, re.M), 'DCS branch is not PRIMARY: ' + net)
    warnings = [line.strip() for line in logs.splitlines() if re.search(r'WARN|WARNING', line)]
    generic = [line for line in warnings if 'PR1014' in line]
    require(all('clk_50mhz' in line for line in generic), 'Unreviewed generic clock routing')
    require(not re.search(r'ERROR|TA2003|ignored|unsupported', logs, re.I), 'EDA log contains ignored/unresolved error')
    return dict(primitive=names[0], mode='FALLING', selected_output_route='PRIMARY', source_routes='PRIMARY', retained_warnings=warnings,
                limitation='PR1014 on50MHz remains visible; external oscillator electrical integrity and analog DAC behavior require hardware measurement')


def negative_checks(model, sdc, clocks, ports):
    rejected = []
    source = 'audio_domain/reference_48_monitor/source_gray_0_s0/Q'
    target = 'audio_domain/reference_48_monitor/gray_meta_0_s0/D'
    old = model.graph[source]
    try:
        model.graph[source] = [(dst, lo, 25. if dst == target else hi) for dst, lo, hi in old]
        try: gray_audit(model)
        except ValueError: rejected.append('actual_gray_wire_25ns')
    finally: model.graph[source] = old
    name = 'audio_domain/reference_48_monitor/gray_sync_0_s0'
    old = model.cells.pop(name)
    try:
        try: gray_audit(model)
        except ValueError: rejected.append('missing_actual_second_stage')
    finally: model.cells[name] = old
    try: constraint_audit(model, sdc + '\nset_max_delay 20 -to [get_pins {missing_register/D}]\n', clocks, ports)
    except ValueError: rejected.append('zero_match_constraint')
    require(len(rejected) == 3, 'Negative physical check failed to reject mutation')
    return rejected


def audit(output, self_test=False):
    output = Path(output).resolve()
    inputs = probe.verify(output)
    manifests = sorted(path for path in (output / 'reports').glob('build_*.json'))
    require(len(manifests) == 1, 'Select a candidate with exactly one immutable build manifest')
    manifest = manifests[0]
    spec = importlib.util.spec_from_file_location('sram_check', probe.ROOT.parents[3] / 'example/RTL8723DS/program_sram.py')
    programmer = importlib.util.module_from_spec(spec); spec.loader.exec_module(programmer)
    artifact, code = programmer.verified_artifact(manifest, allow_gao=True)
    require(code == int(inputs['user_code'], 16), 'Input/bitstream UserCode mismatch')
    pnr = Path(artifact['path']).parent
    paths = [pnr / ('audio_probe.' + suffix) for suffix in ('vo', 'sdf', 'tr', 'rpt.txt')]
    vo, sdf, tr, rpt = (path.read_text() for path in paths)
    build = json.loads(manifest.read_text())
    require(build['passed'] and all(x['returncode'] == 0 for x in build['phases'].values()), 'EDA phases failed')
    logs = '\n'.join(Path(x['log']).read_text() for x in build['phases'].values())
    model = Routed(vo, sdf)
    sta = sta_audit(tr)
    sdc = (output / 'constraints/audio_probe.sdc').read_text()
    active = [line for line in tr.splitlines() if ' Actived ' in line]
    for command in sdc.splitlines():
        if command and not command.startswith('#'):
            require(any(command in line for line in active), 'Requested SDC command was not active: ' + command)
    exception_setup = tr.split('\n3.7.1 Setup Analysis Report\n')[1].split('\n3.7.2')[0]
    bounds = re.findall(r'Timing Path Constraint\[\d+\]:[^\n]*set_max_delay[^\n]*\n(.*?)(?=Timing Path Constraint|\Z)', exception_setup, re.S)
    require(len(bounds) == 8 and all('Path Summary:' in body and 'No timing paths' not in body for body in bounds), 'CDC bounds were overridden in effective setup exceptions')
    require(model.cells.get('ak_smute_obuf') == ('OBUF', {'I': 'VCC', 'O': 'ak_smute'}), 'Physical SMUTE is not constant asserted')
    require(model.cells.get('ak_sdata_obuf') == ('OBUF', {'I': 'GND', 'O': 'ak_sdata'}), 'Physical PCM output is not constant zero')
    ports = inputs['signal_schema']['pins']
    result = dict(schema=1, recorded_at=datetime.now().astimezone().isoformat(), candidate=inputs['identity'], user_code=inputs['user_code'],
                  prepared_input_manifest=str(output / 'inputs.json'), immutable_build_manifest=str(manifest),
                  artifact=artifact, source_snapshot_sha256=inputs['source_snapshot_sha256'],
                  evidence_sha256={str(path): probe.sha(path) for path in [manifest, *paths]}, checker_sha256=probe.sha(__file__),
                  sta=sta, constraint_resolution=constraint_audit(model, sdc, sta['clocks'], ports),
                  dcs=dcs_audit(model, rpt, logs), gray=gray_audit(model), payload=payload_audit(model),
                  held_configuration=config_audit(model), control_and_ack=control_audit(model), resets=reset_audit(model),
                  physical_audit_complete=True, eligible_for_parent_sram_review=True,
                  hardware_accepted=False, sram_programmed=False, flash_programmed=False,
                  limitations=['Independent permanently muted digital experiment; no production profile or analog acceptance',
                               'SDF conservative extrema quantify implemented routes; source protocols require separate simulation',
                               'Source/selected clock reset synchronizer assertion/removal uses metastability containment; first stages retain STA checks',
                               'GAO implementation is verified by SDK timing/CRC; core VO/SDF excludes GAO internals'])
    result['negative_checks'] = negative_checks(model, sdc, sta['clocks'], ports) if self_test else []
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    try:
        result = audit(args.output, args.self_test)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        parser.exit(2, 'Physical audit failed: ' + str(error) + '\n')
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('candidate', 'artifact', 'physical_audit_complete', 'negative_checks')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
