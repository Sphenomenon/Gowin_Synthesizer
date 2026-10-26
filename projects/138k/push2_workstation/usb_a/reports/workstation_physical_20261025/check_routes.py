"""Dated native physical verification; no programming or release promotion."""

from pathlib import Path
import hashlib
import json
import re
import sys
import traceback

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
physical = Path(sys.argv[1]).resolve()
physical_inputs = json.loads((physical / 'physical_inputs.json').read_text())
for name, expected in physical_inputs['input_sha256'].items():
    if hashlib.sha256((physical / name).read_bytes()).hexdigest() != expected:
        raise ValueError('physical input drifted: ' + name)
candidate = Path(physical_inputs['parent_candidate'])
stage = candidate / 'workstation/Prj1'
parent = json.loads((physical / 'parent_integration_inputs.json').read_text())
for name in ('scripts/check_video_pll_init.py', 'scripts/check_serializer_startup.py', 'scripts/check_build.py'):
    if hashlib.sha256((stage / name).read_bytes()).hexdigest() != parent['staged_input_sha256'][name]:
        raise ValueError('physical verification dependency drifted: ' + name)
sys.path.insert(0, str(stage / 'scripts'))
from check_video_pll_init import RoutedDesign
from tools.workstation_synthesis_netlist import SynthesisNetlist

pnr = physical / 'impl/pnr/custom_138k_integration'
vo = pnr.with_suffix('.vo').read_text()
design = RoutedDesign(pnr.with_suffix('.sdf').read_text(), vo)
for name, (kind, pins) in design.cells.items():
    if kind == 'ALU':
        for output in ('SUM', 'COUT'):
            if pins.get(output):
                design.add_driver(pins[output], name, output)
source_audit = json.loads((physical / 'parent_synthesis_audit.json').read_text())
result = dict(passed=False, controls={}, pointers={}, mailboxes={}, held_pcm={}, display_snapshots={}, errors=[],
              hardware_tested=False, deployment_allowed=False,
              scope='routed native USB toggle chains, event FIFO, held mailboxes, FPC/BLE PCM, LCD snapshots and UART receiver; not overall CDC signoff')

def ports(name):
    kind, pins = design.cells[name]
    assert kind.startswith('DFF'), name
    return pins

def chain(source, first, second, bound=None):
    origin, meta, synced = map(ports, (source, first, second))
    assert origin['Q'] == meta['D'] and meta['Q'] == synced['D'], (source, first, second)
    assert origin['CLK'] != meta['CLK'] and meta['CLK'] == synced['CLK'], (source, first, second)
    assert meta.get('CLEAR') == synced.get('CLEAR'), first
    consumers = {name for name, (_, pins) in design.cells.items()
                 if any(net == meta['Q'] and design.drivers.get(net) != (name, pin) for pin, net in pins.items())}
    assert consumers == {second}, (first, consumers)
    flight = design.arc(first, 'CLK', 'Q') + design.route(first + '/Q', second + '/D')
    if bound is not None:
        assert flight <= bound, (first, second, flight, bound)
    return dict(source=source, first=first, second=second, synchronizer_flight_ns=flight)

def payload_paths(net, endpoint, selected, visiting=()):
    if net in design.constants:
        return {}
    assert net not in visiting, net
    name, output = design.drivers[net]
    kind, pins = design.cells[name]
    if kind.startswith('DFF'):
        if name not in selected:
            return {}
        assert output == 'Q', name
        return {name: design.arc(name, 'CLK', 'Q') + design.route(name + '/Q', endpoint)}
    assert kind in ('INV', 'ALU') or re.fullmatch(r'LUT[1-6]', kind), (name, kind)
    paths = {}
    inputs = ('I',) if kind == 'INV' else tuple(pin for pin in ('I0', 'I1', 'I2', 'I3', 'CIN') if pin in pins) if kind == 'ALU' else tuple('I' + str(index) for index in range(int(kind[3:])))
    for pin in inputs:
        for origin, delay in payload_paths(pins[pin], name + '/' + pin, selected, (*visiting, net)).items():
            total = delay + design.arc(name, pin, output) + design.route(name + '/' + output, endpoint)
            paths[origin] = max(paths.get(origin, 0), total)
    return paths

def held(name, entry, bound):
    selected = set(entry['source_registers'].values())
    flights = []
    for bit, target in entry['destination_registers'].items():
        paths = payload_paths(ports(target)['D'], target + '/D', selected)
        assert entry['source_registers'][bit] in paths, (name, bit, target)
        assert max(paths.values()) <= bound, (name, target, paths, bound)
        flights.extend(paths.values())
    return dict(bits=len(entry['destination_registers']), maximum_payload_flight_ns=max(flights), bound_ns=bound)

def registers(prefix, stem, count):
    found = {int(match[1]): name for name, (kind, _) in design.cells.items()
             if kind.startswith('DFF') and (match := re.fullmatch(re.escape(prefix + '/' + stem) + r'_(\d+)_s\d+', name))}
    assert set(found) == set(range(count)), (prefix, stem, len(found), count)
    return {str(bit): name for bit, name in found.items()}

try:
    for name, entry in source_audit['usb2_bridge_cdc_audit']['controls'].items():
        result['controls'][name] = [chain(origin, entry['first_stage'][bit], entry['second_stage'][bit], 2)
                                    for bit, origin in entry['source_registers'].items()]
    for name, entry in source_audit['input_fifo_cdc_audit']['pointers'].items():
        checks = []
        for bit, origin in entry['source_registers'].items():
            check = chain(origin, entry['first_stage'][bit], entry['second_stage'][bit], 2)
            flight = design.arc(origin, 'CLK', 'Q') + design.route(origin + '/Q', entry['first_stage'][bit] + '/D')
            assert flight <= 10, (name, bit, flight)
            checks.append(dict(**check, pointer_flight_ns=flight))
        result['pointers'][name] = checks
    for name, entry in source_audit['usb2_bridge_cdc_audit']['mailboxes'].items():
        result['mailboxes'][name] = held(name, entry, 16)
    original = SynthesisNetlist((physical / 'custom_138k_integration.vg').read_text(), 'workstation_custom_138k_top')
    mailboxes = []
    for prefix, width, preserved in [('u_fpc_audio/u_samples', 49, 41), ('u_ble_pcm_cdc', 64, 64),
                                      ('u_lcd/u_feedback', 290, 143)]:
        held_sources = {original.pin(name, 'Q'): name for name, cell in original.cells.items()
                        if cell['kind'].startswith('DFF') and re.fullmatch(re.escape(prefix) + r'/held_data_\d+_s\d+', name)}
        snapshot = dict(source_registers={}, destination_registers={})
        for name, cell in original.cells.items():
            match = re.fullmatch(re.escape(prefix) + r'/destination_data_(\d+)_s\d+', name)
            if cell['kind'].startswith('DFF') and match:
                assert 0 <= int(match[1]) < width and match[1] not in snapshot['destination_registers'], name
                snapshot['source_registers'][match[1]] = held_sources[original.pin(name, 'D')]
                snapshot['destination_registers'][match[1]] = name
        assert len(held_sources) == len(snapshot['destination_registers']) == preserved, (prefix, 'preserved inventory changed')
        assert set(snapshot['source_registers'].values()) == set(held_sources.values()), prefix
        mailboxes.append((prefix, snapshot))
    del original
    for prefix, entry in mailboxes:
        collection = result['display_snapshots'] if prefix == 'u_lcd/u_feedback' else result['held_pcm']
        collection[prefix] = held(prefix, entry, 10)
        for origin_stem, first_stem, second_stem in [('request_toggle', 'req_meta', 'req_sync'),
                                                      ('acknowledge_toggle', 'ack_meta', 'ack_sync')]:
            names = []
            for stem in (origin_stem, first_stem, second_stem):
                matches = [name for name, (kind, _) in design.cells.items() if kind.startswith('DFF')
                           and re.fullmatch(re.escape(prefix + '/' + stem) + r'_s\d+', name)]
                assert len(matches) == 1, (prefix, stem, matches)
                names.append(matches[0])
            collection[prefix][first_stem] = chain(*names)
    first, second = ['u_bluetooth/u_core/transport/uart/rx_sync_' + str(index) + '_s0' for index in range(2)]
    if ports(first)['Q'] != ports(second)['D']:
        result['errors'].append('BLE UART receiver has combinational logic between synchronizer stages')
        result['uart_receiver'] = dict(first=ports(first), second=ports(second))
    else:
        assert ports(first)['CLK'] == ports(second)['CLK']
        flight = design.arc(first, 'CLK', 'Q') + design.route(first + '/Q', second + '/D')
        assert flight <= 2, flight
        result['uart_receiver_flight_ns'] = flight
    resolved = {}
    pins = [name + '/' + pin for name, (_, entries) in design.cells.items() for pin in entries]
    registers_all = [name for name, (kind, _) in design.cells.items() if kind.startswith('DFF')]
    for selector in source_audit['shared_cdc_audit']['deferred_opaque_ddr_selectors']:
        match = re.fullmatch(r'(get_regs|get_pins) \{(.+)\}', selector)
        assert match, selector
        matches = set()
        for pattern in match[2].split():
            expression = re.compile('^' + re.escape(pattern).replace(r'\*', '.*').replace(r'\?', '.') + '$')
            selected = {name for name in (registers_all if match[1] == 'get_regs' else pins) if expression.fullmatch(name)}
            assert selected, pattern
            matches.update(selected)
        resolved[selector] = len(matches)
    result['resolved_opaque_ddr_selectors'] = resolved
    divider = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv'
    assert design.cells[divider][0] == 'CLKDIV' and design.parameters[(divider, 'DIV_MODE')] == '"4"'
    observers = registers('u_memory', 'ui_reset_sync', 3)
    assert all(ports(name)['CLK'] == design.cells[divider][1]['CLKOUT'] for name in observers.values())
    result['ddr_ui_clock_observers'] = observers
    if parent['identity'].endswith('-a23'):
        phy = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
        launch, capture = phy + '/ddr_init_internal_r_s0', phy + '/wloadn_3_s0'
        assert design.cells[launch][0].startswith('DFF') and design.cells[capture][0].startswith('DFF')
        assert ports(launch)['Q'] == ports(capture)['D'], 'DDR hold constraint no longer binds a direct path'
        assert ports(launch)['CLK'] == design.cells[divider][1]['CLKOUT']
        assert ports(capture)['CLK'] == design.clock_net
        constraint = f'set_min_delay 0.800 -from [get_pins {{{launch}/Q}}] -to [get_pins {{{capture}/D}}]'
        assert constraint in (physical / 'physical.sdc').read_text().splitlines(), 'DDR minimum delay tightening missing'
        result['ddr_initialization_hold_path'] = dict(
            launch=launch, capture=capture, minimum_delay_constraint_ns=0.8,
            data_flight_ns=design.arc(launch, 'CLK', 'Q') + design.route(launch + '/Q', capture + '/D'),
            signoff='full routed STA including clock skew, not data flight alone')
        if physical_inputs.get('ddr_hold_floorplan'):
            placed = re.findall(r'R(\d+)C(\d+)\[\d+\]\[[AB]\]\s+' + re.escape(capture) + r'/(?:CLK|D)\b',
                                pnr.with_suffix('.tr').read_text())
            assert placed and all(40 <= int(row) <= 50 and 70 <= int(column) <= 90 for row, column in placed), 'DDR hold floorplan was not honored'
            result['ddr_initialization_hold_path']['placed_region'] = 'R[40:50]C[70:90]'
    reference_entry = source_audit['native_receiver_audit']['fpc_reference_monitor']
    reference_toggles = [name for name, (kind, _) in design.cells.items()
                         if kind.startswith('DFF') and re.fullmatch(r'u_fpc_audio/reference_toggle_s\d+', name)]
    assert len(reference_toggles) == 1, reference_toggles
    result['reference_monitor'] = chain(reference_toggles[0], reference_entry['first'], reference_entry['second'], 2)
    result['native_usb_reset_boundaries'] = {}
    reset_audit = source_audit.get('native_usb_reset_audit')
    if reset_audit:
        for collection in ('resets', 'levels'):
            for label, entry in reset_audit[collection].items():
                first, second = entry['first'], entry['second']
                meta, synced = ports(first), ports(second)
                assert meta['Q'] == synced['D'] and meta['CLK'] == synced['CLK'], label
                assert meta['CLEAR'] == synced['CLEAR'], label
                consumers = {name for name, (_, pins) in design.cells.items()
                             if any(net == meta['Q'] and design.drivers.get(net) != (name, pin)
                                    for pin, net in pins.items())}
                assert consumers == {second}, (label, consumers)
                flight = design.arc(first, 'CLK', 'Q') + design.route(first + '/Q', second + '/D')
                assert flight <= entry['maximum_stage_flight_ns'], (label, flight)
                result['native_usb_reset_boundaries'][label] = dict(first=first, second=second, flight_ns=flight)
    if parent.get('model_flash'):
        config = (pnr.parent / 'device.cfg').read_text()
        assert re.search(r'^set MSPI regular_io = true$', config, re.M), 'native model Flash pads are not user-owned'
        assert re.search(r'^set CPU regular_io = true$', config, re.M), 'CPU mux still owns the model Flash pads'
        first, second = 'u_music/model_memory_meta_s0', 'u_music/model_memory_ready_s0'
        meta, synced = ports(first), ports(second)
        assert meta['Q'] == synced['D'] and meta['CLK'] == synced['CLK'] == design.clock_net
        consumers = {name for name, (_, pins) in design.cells.items()
                     if any(net == meta['Q'] and design.drivers.get(net) != (name, pin)
                            for pin, net in pins.items())}
        assert consumers == {second}, ('model readiness first-stage fanout', consumers)
        flight = design.arc(first, 'CLK', 'Q') + design.route(first + '/Q', second + '/D')
        assert flight <= 2, ('model readiness synchronization flight', flight)
        result['model_flash_readiness'] = dict(first=first, second=second, flight_ns=flight, bound_ns=2)
        result['model_flash_mspi_as_gpio'] = True
    result['passed'] = not result['errors']
except (AssertionError, KeyError, ValueError) as error:
    result['errors'].append(str(error))
    result['traceback'] = traceback.format_exc()
result['evidence_sha256'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in (Path(__file__), pnr.with_suffix('.sdf'), pnr.with_suffix('.vo'),
                                          physical / 'parent_synthesis_audit.json')}
(physical / 'native-routes-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(passed=result['passed'], errors=result['errors']), indent=2))
raise SystemExit(0 if result['passed'] else 1)
