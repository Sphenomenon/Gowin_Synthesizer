"""Bind the resource candidate to the existing native routed checks.

Historical checkers stay byte-identical. Only their evidence field names and
the candidate identity dispatch are adapted; timing bounds stay unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKERS = dict(
    timing=('check_timing.py', '86fe99e9a448fae12a30090ad6c6ee05bb7b8a92462f015596bb3c208a0a7628'),
    pll=('check_pll.py', '41d0a89a353e3c017b315740f5cd9bed1f73d2d2c0b08e83caea33fc3135e24d'),
    routes=('check_routes.py', 'd6e334a69d9a4ca357c5141350c03925ddcc96887939dafae1173b49780b1156'),
    cdc=('check_common_cdc.py', 'dc872759ce7968371fcd2b21d6fc281dde0cdc217eff3e6387cc752863f3a328'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('resource physical checker anchor drift: ' + old)
    return text.replace(old, new)


def adapt(kind, text):
    if kind == 'routes':
        text = once(text, "source_audit = json.loads((physical / 'parent_synthesis_audit.json').read_text())",
                    """source_audit = json.loads((physical / 'parent_synthesis_audit.json').read_text())
checks = source_audit['checks']
source_audit = dict(source_audit,
    usb2_bridge_cdc_audit=checks['usb2_cdc'], input_fifo_cdc_audit=checks['input_fifo'],
    shared_cdc_audit=checks['shared_cdc'], native_receiver_audit=checks['receivers'],
    native_usb_reset_audit=checks['usb_resets'])""")
        text = once(text, "if parent['identity'].endswith('-a23'):",
                    "if parent['identity'].startswith('custom138k-native-integration-20261102-'):")
        # Reference CSTs carry the same region without the older manifest flag.
        # Check the actual placement whenever that explicit region is selected.
        text = once(text, "if physical_inputs.get('ddr_hold_floorplan'):",
                    "if physical_inputs.get('ddr_hold_floorplan') or "
                    "('INS_LOC \"' + capture + '\" R[40:50]C[70:90];') in "
                    "(physical / 'physical.cst').read_text().splitlines():")
    if kind == 'cdc':
        anchor = "adapted = original.replace('u_push/', 'u_native_usb/input_owner/')"
        text = once(text, anchor, anchor+'\nadapted = extend_resource_cdc(adapted)')
        anchor = "namespace['constraints'] = lambda: constraints().replace('u_push/', 'u_native_usb/input_owner/')"
        text = once(text, anchor, "namespace['checked_fifo_heads'] = resource_fifo_heads\n"
                    "namespace['repair_primitive_inventory'] = resource_primitive_inventory\n"+anchor)
    return text


def primitive_inventory(design, vo):
    """Parse Gowin's inline closing ports as well as separate closing lines."""
    cells = {}
    pattern = r'^(\w+)\s+(\\\S+|\w+)\s*\((.*?)\);'
    for match in re.finditer(pattern, vo, re.M | re.S):
        kind, name = match[1], match[2].lstrip('\\')
        if kind == 'module':
            continue
        if name in cells:
            raise ValueError('duplicate routed primitive: '+name)
        pins = {m[1]: re.sub(r'\s+|\\', '', m[2]) for m in
                re.finditer(r'\.(\w+)\s*\(([^)]*)\)', match[3])}
        cells[name] = kind, pins
    if not set(design.cells) <= set(cells):
        raise ValueError('complete routed parser lost historical primitive inventory')
    design.cells, design.drivers = cells, {}
    for name, (kind, pins) in cells.items():
        outputs = (('Q',) if kind.startswith('DFF') else ('F',) if kind.startswith('LUT') else
                   ('O',) if kind in ('INV', 'IBUF', 'OBUF') else ('SUM', 'COUT') if kind == 'ALU' else ())
        for pin in outputs:
            if pins.get(pin):
                design.add_driver(pins[pin], name, pin)
    return design


def fifo_head_domains(design, read_clock, vo=None):
    """An asynchronous FIFO RAM head is addressed in its read clock domain.

Accept only the a27 command FIFO's exact RAM/pointer inventory. The separate
storage check proves both Gray synchronizers and their physical flight bounds.
"""
    scope = 'u_bluetooth/g_store.u_store/u_commands'
    if vo is None:
        memories = [(name, pins) for name, (kind, pins) in design.cells.items()
                    if name.startswith(scope+'/g_small_head.') and kind == 'RAM16SDP4']
    else:
        # Gowin closes distributed RAM instances on the final port line.
        # The historical SDF parser expects a separate closing line; parse
        # this exact new primitive inventory independently, without changing it.
        memories = []
        pattern = r'^RAM16SDP4\s+\\(\S+)\s*\((.*?)\);'
        for match in re.finditer(pattern, vo, re.M | re.S):
            if match[1].startswith(scope+'/g_small_head.'):
                pins = {m[1]: re.sub(r'\s+|\\', '', m[2]) for m in
                        re.finditer(r'\.(\w+)\s*\(([^)]*)\)', match[2])}
                memories.append((match[1], pins))
    if len(memories) != 12:
        raise ValueError('BLE command FIFO head RAM inventory changed')
    domains = {}
    for name, pins in memories:
        if pins['CLK'] != design.clock_net:
            raise ValueError('BLE command FIFO RAM write clock changed: '+name)
        for port, stem, clock in [('WAD', 'write_binary', design.clock_net), ('RAD', 'read_binary', read_clock)]:
            bits = list(reversed(design.bits(pins[port])))
            if len(bits) != 4:
                raise ValueError('BLE command FIFO RAM address width changed')
            for bit, net in enumerate(bits):
                driver, pin = design.drivers[net]
                kind, origin = design.cells[driver]
                if (not kind.startswith('DFF') or pin != 'Q' or origin['CLK'] != clock or
                        not re.fullmatch(re.escape(scope+'/'+stem+'_'+str(bit))+r'_s\d+', driver)):
                    raise ValueError('BLE command FIFO RAM address provenance changed: '+driver)
        for net in design.bits(pins['DO']):
            if net in domains:
                raise ValueError('BLE command FIFO RAM output aliases another driver')
            domains[net] = {read_clock}
    return domains


def extend_common_cdc(text):
    anchor = '        design = RoutedDesign(files[0].read_text(), vo)'
    text = once(text, anchor, anchor+'\n        design = repair_primitive_inventory(design, vo)')
    anchor = "        ddr_clock=next(iter(registers('u_music/u_ddr_req_cdc/write_gray_meta_').values()))['CLK']"
    text = once(text, anchor, anchor+"\n        head_domains=checked_fifo_heads(design,ddr_clock,vo)\n"
                "        result['asynchronous_fifo_head_provenance']=dict(ram16sdp4=12,output_bits=len(head_domains),read_clock=ddr_clock,write_clock=design.clock_net)")
    anchor = '            if net in design.constants:return set()'
    text = once(text, anchor, anchor+'\n            if net in head_domains:return head_domains[net]')
    anchor = "            elif kind.startswith('LUT'):inputs=[key for key in ports if key.startswith('I')]"
    return once(text, anchor, anchor+"\n            elif kind=='ALU':inputs=[key for key in ('I0','I1','I2','I3','CIN') if key in ports]")


def check(kind, physical, source_root=ROOT):
    physical, source_root = Path(physical).resolve(), Path(source_root).resolve()
    parent = json.loads((physical / 'parent_integration_inputs.json').read_text())
    if (parent['identity'] not in ('custom138k-native-integration-20261102-a27',
                                  'custom138k-native-integration-20261102-a28',
                                  'custom138k-native-integration-20261102-a29') or
            parent['hdmi']['mode'] != '1080p60'):
        raise ValueError('explicit a27/a28/a29 1080p source identity required')
    filename, expected = CHECKERS[kind]
    checker = source_root / 'reports/workstation_physical_20261025' / filename
    if sha(checker) != expected:
        raise ValueError('historical physical checker changed: ' + filename)
    code = adapt(kind, checker.read_text())
    record = dict(source_checker=str(checker), source_sha256=expected,
                  adapter_sha256=sha(__file__), adapted_sha256=hashlib.sha256(code.encode()).hexdigest(),
                  source_root=str(source_root), parent_identity=parent['identity'],
                  bounds_changed=False, board_accessed=False,
                  exit_plan='Move native routed audits to shared configuration before promoting this candidate.')
    (physical / ('resource-checker-' + kind + '.json')).write_text(json.dumps(record, indent=2) + '\n')
    old_argv = sys.argv
    try:
        sys.argv = [str(checker), str(physical)]
        exec(compile(code, str(checker) + ':resource-evidence-schema', 'exec'),
             dict(__file__=str(checker), __name__='__main__',
                  extend_resource_cdc=extend_common_cdc, resource_fifo_heads=fifo_head_domains,
                  resource_primitive_inventory=primitive_inventory))
    finally:
        sys.argv = old_argv


def storage(physical):
    """Check both new PCM FIFO pointer crossings against the physical nets/SDF."""
    physical = Path(physical).resolve()
    inputs = json.loads((physical/'physical_inputs.json').read_text())
    for name, expected in inputs['input_sha256'].items():
        if sha(physical/name) != expected:
            raise ValueError('physical input drifted: '+name)
    stage = Path(inputs['parent_candidate'])/'workstation/Prj1'
    parent = json.loads((physical/'parent_integration_inputs.json').read_text())
    checker = stage/'scripts/check_video_pll_init.py'
    if sha(checker) != parent['staged_input_sha256']['scripts/check_video_pll_init.py']:
        raise ValueError('routed parser identity changed')
    sys.path.insert(0, str(stage/'scripts'))
    from check_video_pll_init import RoutedDesign
    base = physical/'impl/pnr/custom_138k_integration'
    design = RoutedDesign(base.with_suffix('.sdf').read_text(), base.with_suffix('.vo').read_text())
    design = primitive_inventory(design, base.with_suffix('.vo').read_text())
    clocks = dict(clk_50m=design.clock_net,
                  ddr_ui100=design.cells['u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv'][1]['CLKOUT'])
    result = dict(passed=False, buses={}, errors=[], hardware_tested=False, deployment_allowed=False)
    prefix = 'u_bluetooth/g_store.u_store'

    def register(stem):
        found = [name for name, (kind, _) in design.cells.items()
                 if kind.startswith('DFF') and re.fullmatch(re.escape(stem)+r'_s\d+', name)]
        if len(found) != 1:
            raise ValueError('BLE physical synchronizer inventory changed: '+stem)
        return found[0]

    def stage_check(first, second, target_clock):
        one, two = design.cells[first][1], design.cells[second][1]
        if one['Q'] != two['D'] or one['CLK'] != two['CLK'] or one['CLK'] != target_clock:
            raise ValueError('BLE physical two-stage topology changed: '+first)
        consumers = {name for name, (_, pins) in design.cells.items()
                     if any(net == one['Q'] and design.drivers.get(net) != (name, pin)
                            for pin, net in pins.items())}
        if consumers != {second} or one.get('CLEAR') != two.get('CLEAR'):
            raise ValueError('BLE physical first-stage fanout/reset changed: '+first)
        flight = design.arc(first, 'CLK', 'Q')+design.route(first+'/Q', second+'/D')
        if flight > 2:
            raise ValueError(f'BLE stage flight exceeds 2ns: {first} {flight}')
        return flight

    try:
        for fifo, width, wc, rc in [('u_commands', 5, 'clk_50m', 'ddr_ui100'),
                                    ('u_responses', 3, 'ddr_ui100', 'clk_50m')]:
            for side, source, target in [('write', wc, rc), ('read', rc, wc)]:
                bus = []
                for bit in range(width):
                    stem = prefix+'/'+fifo+'/'+side
                    first = register(stem+'_gray_meta_'+str(bit))
                    second = register(stem+'_gray_sync_'+str(bit))
                    flight = stage_check(first, second, clocks[target])
                    origin, pin = design.drivers[design.cells[first][1]['D']]
                    kind, ports = design.cells[origin]
                    if (not kind.startswith('DFF') or pin != 'Q' or ports['CLK'] != clocks[source] or
                            not re.fullmatch(re.escape(stem)+r'_(gray|binary)_'+str(bit)+r'_s\d+', origin) or
                            ('_binary_' in origin and bit != width-1)):
                        raise ValueError('BLE pointer is not the registered Gray bit/MSB alias: '+origin)
                    pointer_flight = design.arc(origin, 'CLK', 'Q')+design.route(origin+'/Q', first+'/D')
                    if pointer_flight > 10:
                        raise ValueError(f'BLE Gray flight exceeds 10ns: {origin} {pointer_flight}')
                    bus.append(dict(source=origin, first=first, second=second,
                                    pointer_flight_ns=pointer_flight, stage_flight_ns=flight))
                result['buses'][fifo+'/'+side] = bus
        first, second = register(prefix+'/ready_meta'), register(prefix+'/ready_sync')
        result['ready_stage_flight_ns'] = stage_check(first, second, clocks['clk_50m'])
        result['passed'] = True
    except (ValueError, KeyError, AssertionError) as error:
        result['errors'].append(str(error))
    result['evidence_sha256'] = {str(p): sha(p) for p in
        (Path(__file__), checker, base.with_suffix('.vo'), base.with_suffix('.sdf'), physical/'physical.sdc')}
    (physical/'ble-storage-routes-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'], errors=result['errors']), indent=2))
    if not result['passed']:
        raise SystemExit(1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('check', choices=[*CHECKERS, 'storage'])
    parser.add_argument('physical', type=Path)
    parser.add_argument('--source-root', type=Path, default=ROOT,
                        help='Hash-bound source snapshot used to prepare the parent synthesis.')
    args = parser.parse_args()
    if args.check == 'storage':
        storage(args.physical)
    else:
        check(args.check, args.physical, args.source_root)


if __name__ == '__main__':
    main()
