"""Bound the selected native USB/audio event FIFO Gray crossings."""

from pathlib import Path
import fnmatch
import json
import re

from tools.stage_usb_firmware import sha
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_custom_usb2_cdc import pattern, query
from tools.workstation_synthesis_netlist import SynthesisNetlist


PLAN_SOURCE = 'boards/custom_138k/input_cdc.json'
FIFO = 'u_native_usb/input_owner/events/fifo/unbuffered'
POINTERS = dict(read=('consume_r_gry', 'consume_cdc', 'audio_76m8', 'usb_48m'),
                write=('produce_w_gry', 'produce_cdc', 'usb_48m', 'audio_76m8'))


def input_cdc_bundle(root):
    source = Path(root) / PLAN_SOURCE
    plan = json.loads(source.read_text())
    if (set(plan) != {'schema', 'identity', 'fifo', 'pointer_bits', 'write_binary_alias_bit',
                      'gray_max_delay_ns', 'synchronizer_max_delay_ns'} or
            plan.get('schema') != 1 or plan.get('identity') != 'custom138k-input-fifo-cdc-20261022-v1' or
            plan.get('fifo') != FIFO or type(plan.get('pointer_bits')) is not int or plan['pointer_bits'] != 7 or
            type(plan.get('write_binary_alias_bit')) is not int or plan['write_binary_alias_bit'] != 6):
        raise ValueError('native input FIFO CDC inventory changed')
    clocks = clock_bundle(root)['plan']
    frequencies = {entry['name']: entry['frequency_hz'] for entry in (*clocks['primary'], *clocks['generated'])}
    shortest_period = min(1e9 / frequencies[name] for name in ('usb_48m', 'audio_76m8'))
    for name, upper in (('gray_max_delay_ns', min(10.0, shortest_period * 0.96)),
                        ('synchronizer_max_delay_ns', 2.0)):
        delay = plan.get(name)
        if type(delay) not in (int, float) or not 0 < delay <= upper:
            raise ValueError('native input FIFO delay budget relaxed or invalid: ' + name)
    lines, pointers = [], {}
    for name, (stem, synchronizer, source_clock, destination_clock) in POINTERS.items():
        scope = FIFO + '/' + synchronizer
        sources = [pattern(FIFO, stem, 'Q', True)]
        if name == 'write':
            sources.append(pattern(FIFO, 'produce_w_bin_6', 'Q'))
        selectors = dict(source=sources, first=pattern(scope, 'stage0', 'D', True),
                         first_q=pattern(scope, 'stage0', 'Q', True), second=pattern(scope, 'stage1', 'D', True))
        origin, destination = query(' '.join(sources)), query(selectors['first'])
        lines.append(f"set_max_delay -from {origin} -to {destination} {plan['gray_max_delay_ns']:.3f}")
        lines.append(f'set_false_path -hold -from {origin} -to {destination}')
        lines.append(f"set_max_delay -from {query(selectors['first_q'])} -to {query(selectors['second'])} {plan['synchronizer_max_delay_ns']:.3f}")
        pointers[name] = dict(stem=stem, scope=scope, selectors=selectors,
                              source_clock=source_clock, destination_clock=destination_clock)
    return dict(source=PLAN_SOURCE, source_sha256=sha(source), plan=plan, pointers=pointers,
                sdc='\n'.join(lines) + '\n')


def audit_input_fifo(root, netlist_text, clocks, *, top='workstation_custom_138k_top'):
    bundle = input_cdc_bundle(root)
    netlist = SynthesisNetlist(netlist_text, top)
    if netlist.frames.get(FIFO, {}).get('kind') != 'gw138k_usb_event_fifo.fifo.unbuffered':
        raise ValueError('native input FIFO hierarchy missing')
    high = {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'} | {"1'b1"}
    low = {netlist.pin(name, 'G') for name, cell in netlist.cells.items() if cell['kind'] == 'GND'} | {"1'b0"}

    def registers(scope, stem, expected_bits):
        found = {}
        for label, cell in netlist.modules[netlist.frames[scope]['kind']].items():
            match = re.fullmatch(re.escape(stem) + r'_(\d+)_s\d+', label)
            if not match or not cell['kind'].startswith('DFF'):
                continue
            bit = int(match[1])
            if bit in found:
                raise ValueError('native input FIFO duplicate register bit: ' + stem)
            found[bit] = scope + '/' + label
        if set(found) != set(expected_bits):
            raise ValueError('native input FIFO register bit inventory changed: ' + stem)
        return found

    resolved, pointers = {}, {}
    for name, entry in bundle['pointers'].items():
        bits = range(7)
        source = registers(FIFO, entry['stem'], range(6) if name == 'write' else bits)
        if name == 'write':
            source[6] = registers(FIFO, 'produce_w_bin', range(7))[6]
        first = registers(entry['scope'], 'stage0', bits)
        second = registers(entry['scope'], 'stage1', bits)
        origin_clock = clocks['clocks'][entry['source_clock']]['net']
        destination_clock = clocks['clocks'][entry['destination_clock']]['net']
        for bit in bits:
            if netlist.pin(source[bit], 'CLK') != origin_clock:
                raise ValueError('native input FIFO clock domain changed: ' + source[bit])
            for instance in (first[bit], second[bit]):
                if netlist.pin(instance, 'CLK') != destination_clock:
                    raise ValueError('native input FIFO clock domain changed: ' + instance)
                if (netlist.cells[instance]['kind'] != 'DFFCE' or netlist.pin(instance, 'CE') not in high or
                        netlist.pin(instance, 'CLEAR') not in low):
                    raise ValueError('native input FIFO synchronizer is not unconditionally clocked: ' + instance)
            if netlist.pin(source[bit], 'Q') != netlist.pin(first[bit], 'D'):
                raise ValueError('native input FIFO registered Gray pointer source changed: ' + name)
            if netlist.pin(first[bit], 'Q') != netlist.pin(second[bit], 'D'):
                raise ValueError('native input FIFO two-stage connection changed: ' + name)
        expected = {}
        for selector in entry['selectors']['source']:
            expected[selector] = [instance + '/Q' for instance in source.values() if fnmatch.fnmatchcase(instance + '/Q', selector)]
        for key, collection, port in (('first', first, 'D'), ('first_q', first, 'Q'), ('second', second, 'D')):
            expected[entry['selectors'][key]] = [instance + '/' + port for instance in collection.values()]
        for selector, pins in expected.items():
            actual = sorted(instance + '/' + port for instance, cell in netlist.cells.items()
                            if cell['kind'].startswith('DFF') for port in cell['ports']
                            if fnmatch.fnmatchcase(instance + '/' + port, selector))
            if not pins or actual != sorted(pins):
                raise ValueError('native input FIFO selector expansion changed: ' + selector)
            resolved[selector] = actual
        pointers[name] = dict(source_registers=source, first_stage=first, second_stage=second,
                              source_clock=origin_clock, destination_clock=destination_clock)
    memories = [name for name, cell in netlist.cells.items() if name.startswith(FIFO + '/') and cell['kind'] == 'SDPX9B']
    if (len(memories) != 1 or netlist.pin(memories[0], 'CLKA') != clocks['clocks']['usb_48m']['net'] or
            netlist.pin(memories[0], 'CLKB') != clocks['clocks']['audio_76m8']['net']):
        raise ValueError('native input FIFO dual-clock packet memory changed')
    return dict(source=bundle['source'], source_sha256=bundle['source_sha256'], pointers=pointers,
                resolved_pin_selectors=resolved, pointer_bits=14, memory=memories[0],
                write_binary_alias_bit=6, source_netlist_endpoints_verified=True,
                gray_encoding_behavior_verified=False, physical_timing_verified=False,
                native_constraints_complete=False)
