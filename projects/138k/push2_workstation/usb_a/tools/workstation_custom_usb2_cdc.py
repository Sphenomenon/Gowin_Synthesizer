"""Bound native USB2 bridge crossings without blanket clock or payload exceptions."""

from pathlib import Path
import fnmatch
import json
import re

from tools.stage_usb_firmware import sha
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_synthesis_netlist import SynthesisNetlist


PLAN_SOURCE = 'boards/custom_138k/usb2_cdc.json'
BRIDGE = 'u_native_usb/host/usb/bridge'
CONTROLS = dict(
    request=('request_toggle_q', 'request_sync_q_0', 'request_sync_q_1', 'cpu', 'ulpi', 1),
    result=('result_toggle_q', 'result_sync_q_0', 'result_sync_q_1', 'ulpi', 'cpu', 1),
    reset=('reset_toggle_q', 'reset_sync_q_0', 'reset_sync_q_1', 'cpu', 'ulpi', 1),
    reset_ack=('reset_ack_q', 'reset_ack_sync_q_0', 'reset_ack_sync_q_1', 'ulpi', 'cpu', 1),
    high_speed=('hs_cpu_q', 'hs_sync_q_0', 'hs_sync_q_1', 'cpu', 'ulpi', 1),
    snapshot=('snapshot_toggle_q', 'snapshot_sync_q_0', 'snapshot_sync_q_1', 'ulpi', 'cpu', 1),
    snapshot_ack=('snapshot_ack_q', 'snapshot_ack_sync_q_0', 'snapshot_ack_sync_q_1', 'cpu', 'ulpi', 1),
    reference_fault=('reference_fault_q', 'reference_fault_meta_q', 'reference_fault_sync_q', 'ref', 'cpu', 3))
MAILBOXES = dict(descriptor=('descriptor_cpu_q', 'descriptor_ulpi_q', 'cpu', 'ulpi', 30),
                 result=('result_mailbox_q', 'result_cpu_q', 'ulpi', 'cpu', 22),
                 snapshot=('snapshot_mailbox_q', 'snapshot_cpu_q', 'ulpi', 'cpu', 80))


def pattern(scope, stem, port, indexed=False):
    return scope + '/' + stem + ('_*' if indexed else '') + '_s*/' + port


def query(selector):
    return '[get_pins {' + selector + '}]'


def cdc_bundle(root):
    source = Path(root) / PLAN_SOURCE
    plan = json.loads(source.read_text())
    if (set(plan) != {'schema', 'identity', 'bridge', 'controls', 'mailboxes', 'synchronizer_max_delay_ns',
                      'mailbox_max_delay_ns', 'snapshot_constant_bits'} or
            plan.get('schema') != 1 or plan.get('identity') != 'custom138k-usb2-bridge-cdc-20261022-v1' or
            plan.get('bridge') != BRIDGE or plan.get('controls') != list(CONTROLS) or
            plan.get('mailboxes') != list(MAILBOXES)):
        raise ValueError('native USB2 CDC inventory changed')
    clocks = clock_bundle(root)['plan']
    frequencies = {entry['name']: entry['frequency_hz'] for entry in (*clocks['primary'], *clocks['generated'])}
    shortest_period = min(1e9 / frequencies[name] for name in ('usb_48m', 'ulpi_60m'))
    for name, upper in (('synchronizer_max_delay_ns', 2.0), ('mailbox_max_delay_ns', shortest_period * 0.96)):
        delay = plan.get(name)
        if type(delay) not in (int, float) or not 0 < delay <= upper:
            raise ValueError('native USB2 CDC delay budget relaxed or invalid: ' + name)
    omitted = plan.get('snapshot_constant_bits')
    if (not isinstance(omitted, list) or any(type(bit) is not int or not 0 <= bit < 80 for bit in omitted) or
            sorted(set(omitted)) != omitted):
        raise ValueError('native USB2 snapshot constant-bit inventory invalid')
    lines, controls, mailboxes = [], {}, {}
    for name, (source_stem, first_stem, second_stem, source_domain, destination_domain, width) in CONTROLS.items():
        source_scope = BRIDGE.rpartition('/')[0] if name == 'reference_fault' else BRIDGE
        selectors = dict(source=pattern(source_scope, source_stem, 'Q', width > 1),
                         first=pattern(BRIDGE, first_stem, 'D', width > 1),
                         first_q=pattern(BRIDGE, first_stem, 'Q', width > 1),
                         second=pattern(BRIDGE, second_stem, 'D', width > 1))
        lines.append(f"set_false_path -from {query(selectors['source'])} -to {query(selectors['first'])}")
        lines.append(f"set_max_delay -from {query(selectors['first_q'])} -to {query(selectors['second'])} {plan['synchronizer_max_delay_ns']:.3f}")
        controls[name] = dict(selectors=selectors, source_scope=source_scope, source_stem=source_stem,
                              first_stem=first_stem, second_stem=second_stem, width=width,
                              source_domain=source_domain, destination_domain=destination_domain)
    for name, (source_stem, destination_stem, source_domain, destination_domain, width) in MAILBOXES.items():
        selectors = dict(source=pattern(BRIDGE, source_stem, 'Q', True),
                         destination=pattern(BRIDGE, destination_stem, 'D', True))
        lines.append(f"set_max_delay -from {query(selectors['source'])} -to {query(selectors['destination'])} {plan['mailbox_max_delay_ns']:.3f}")
        lines.append(f"set_false_path -hold -from {query(selectors['source'])} -to {query(selectors['destination'])}")
        bits = [bit for bit in range(width) if name != 'snapshot' or bit not in omitted]
        mailboxes[name] = dict(selectors=selectors, source_stem=source_stem, destination_stem=destination_stem,
                               source_domain=source_domain, destination_domain=destination_domain, bits=bits)
    return dict(source=PLAN_SOURCE, source_sha256=sha(source), plan=plan, controls=controls,
                mailboxes=mailboxes, sdc='\n'.join(lines) + '\n')


def audit_usb2_cdc(root, netlist_text, clocks):
    bundle = cdc_bundle(root)
    netlist = SynthesisNetlist(netlist_text, 'workstation_custom_138k_top')
    if netlist.frames.get(BRIDGE, {}).get('kind') != 'workstation_usb2_cpu_bridge':
        raise ValueError('native USB2 CDC bridge hierarchy missing')
    domains = {domain: clocks['clocks'][name]['net'] for domain, name in
               (('cpu', 'usb_48m'), ('ulpi', 'ulpi_60m'), ('ref', 'clk_50m'))}
    constants = {netlist.pin(instance_path, 'V') for instance_path, cell in netlist.cells.items()
                 if cell['kind'] == 'VCC' and 'V' in cell['ports']}
    constants.add("1'b1")

    def registers(scope, stem, bits, indexed):
        found = {}
        frame = netlist.frames.get(scope)
        if frame:
            for label, cell in netlist.modules[frame['kind']].items():
                if not cell['kind'].startswith('DFF'):
                    continue
                match = re.fullmatch(re.escape(stem) + (r'_(\d+)' if indexed else '') + r'_s\d+', label)
                if not match:
                    continue
                index = int(match[1]) if indexed else 0
                if index in found:
                    raise ValueError('native USB2 CDC register identity changed: ' + label)
                found[index] = scope + '/' + label
        if set(found) != set(bits):
            raise ValueError('native USB2 CDC register bit inventory changed: ' + stem)
        return found

    def check_clock(instance_path, domain):
        if netlist.pin(instance_path, 'CLK') != domains[domain]:
            raise ValueError('native USB2 CDC clock domain changed: ' + instance_path)

    controls, resolved = {}, {}
    for name, entry in bundle['controls'].items():
        bits = list(range(entry['width']))
        source = registers(entry['source_scope'], entry['source_stem'], bits, entry['width'] > 1)
        first = registers(BRIDGE, entry['first_stem'], bits, entry['width'] > 1)
        second = registers(BRIDGE, entry['second_stem'], bits, entry['width'] > 1)
        for bit in bits:
            check_clock(source[bit], entry['source_domain'])
            for instance_path in (first[bit], second[bit]):
                check_clock(instance_path, entry['destination_domain'])
                if (netlist.cells[instance_path]['kind'] != 'DFFCE' or
                        netlist.pin(instance_path, 'CE') not in constants):
                    raise ValueError('native USB2 synchronizer is not unconditionally clocked: ' + instance_path)
            if (netlist.pin(first[bit], 'D') != netlist.pin(source[bit], 'Q') or
                    netlist.pin(second[bit], 'D') != netlist.pin(first[bit], 'Q') or
                    netlist.pin(first[bit], 'CLEAR') != netlist.pin(second[bit], 'CLEAR')):
                raise ValueError('native USB2 synchronizer two-stage connection changed: ' + name)
        controls[name] = dict(source_registers=source, first_stage=first, second_stage=second,
                              source_clock=domains[entry['source_domain']], destination_clock=domains[entry['destination_domain']])
        for key, collection in (('source', source), ('first', first), ('first_q', first), ('second', second)):
            port = 'Q' if key in ('source', 'first_q') else 'D'
            resolved[entry['selectors'][key]] = sorted(instance_path + '/' + port for instance_path in collection.values())

    bridge_cells = {BRIDGE + '/' + label: cell for label, cell in netlist.modules['workstation_usb2_cpu_bridge'].items()}
    drivers = {}
    for instance_path, cell in bridge_cells.items():
        output = 'F' if re.fullmatch(r'LUT[1-6]', cell['kind']) else 'O' if cell['kind'] == 'INV' else None
        if output:
            net = netlist.pin(instance_path, output)
            if net in drivers:
                raise ValueError('native USB2 payload dependency has multiple drivers')
            drivers[net] = instance_path

    def dependencies(net, sources, seen=()):
        if net in sources:
            return {sources[net]}
        if net in seen:
            raise ValueError('native USB2 cyclic payload dependency')
        if net not in drivers:
            return set()
        instance_path = drivers[net]
        cell = netlist.cells[instance_path]
        return set().union(*(dependencies(netlist.pin(instance_path, port), sources, (*seen, net))
                             for port in cell['ports'] if port == 'I' or re.fullmatch(r'I[0-5]', port)))

    mailboxes = {}
    for name, entry in bundle['mailboxes'].items():
        source = registers(BRIDGE, entry['source_stem'], entry['bits'], True)
        destination = registers(BRIDGE, entry['destination_stem'], entry['bits'], True)
        leaves = {netlist.pin(instance_path, 'Q'): bit for bit, instance_path in source.items()}
        for bit in entry['bits']:
            check_clock(source[bit], entry['source_domain'])
            check_clock(destination[bit], entry['destination_domain'])
            if bit not in dependencies(netlist.pin(destination[bit], 'D'), leaves):
                raise ValueError('native USB2 held payload dependency missing: ' + name + '[' + str(bit) + ']')
        mailboxes[name] = dict(source_registers=source, destination_registers=destination,
                              implemented_bits=entry['bits'], setup_max_delay_ns=bundle['plan']['mailbox_max_delay_ns'],
                              hold_only_false_path=True)
        for key, collection, port in (('source', source, 'Q'), ('destination', destination, 'D')):
            resolved[entry['selectors'][key]] = sorted(instance_path + '/' + port for instance_path in collection.values())
    for selector, pins in resolved.items():
        matching = sorted(instance_path + '/' + port for instance_path, cell in netlist.cells.items()
                          if instance_path.rpartition('/')[0] in (BRIDGE, BRIDGE.rpartition('/')[0])
                          for port in cell['ports'] if fnmatch.fnmatchcase(instance_path + '/' + port, selector))
        if matching != pins:
            raise ValueError('native USB2 CDC selector includes unexpected or missing pins: ' + selector)
    return dict(source=bundle['source'], source_sha256=bundle['source_sha256'],
                controls=controls, mailboxes=mailboxes, resolved_pin_selectors=resolved,
                sdc=bundle['sdc'], source_netlist_endpoints_verified=True,
                payload_hold_behavior_verified=False, physical_timing_verified=False,
                native_constraints_complete=False)
