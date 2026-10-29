"""Checked, offline pin relocation plans; never a synthesis or programming path."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from tools.workstation_baselines import load_baseline


PROFILE_PATH = Path('boards/custom_138k/pinout.json')
LOCATION = re.compile(r'^IO_LOC\s+"([^"]+)"\s+([^;]+);\s*$')
BALL_NET = re.compile(r'(?:.*_)?BANK(\d+)_([A-Z]+\d+)(?:_.*)?$')


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


class Netlist:
    def __init__(self, payload):
        self.nets = {}
        self.nodes = {}
        active = False
        finished = False
        current = None
        for raw_line in payload.decode('utf-8-sig').splitlines():
            line = raw_line.strip()
            if line == '$NETS':
                if active:
                    raise ValueError('duplicate $NETS section')
                active = True
                continue
            if not active or not line:
                continue
            if line.startswith('$'):
                finished = True
                break
            if ';' in line:
                current, nodes = line.split(';', 1)
                current = current.strip().strip("'")
                if not current or current in self.nets:
                    raise ValueError('empty or duplicate network: ' + current)
                self.nets[current] = []
            else:
                nodes = line
            if current is None:
                raise ValueError('network continuation without a name')
            for node in nodes.replace(',', ' ').split():
                if not re.fullmatch(r'[^.\s]+\.[^.\s]+', node):
                    raise ValueError('invalid netlist node: ' + node)
                if node in self.nodes:
                    raise ValueError('duplicate netlist node: ' + node)
                self.nodes[node] = current
                self.nets[current].append(node)
        if not active or not finished or not self.nets:
            raise ValueError('missing or incomplete $NETS section')

    def network(self, node):
        if node not in self.nodes:
            raise ValueError('missing netlist node: ' + node)
        return self.nodes[node]

    def same(self, *nodes):
        networks = [self.network(node) for node in nodes]
        if len(set(networks)) != 1:
            raise ValueError('disconnected nodes: ' + ', '.join(nodes))
        return networks[0]

    def ball(self, node, bank=None):
        network = self.network(node)
        match = BALL_NET.fullmatch(network)
        if not match or (bank is not None and int(match[1]) != bank):
            raise ValueError('missing or wrong bank/ball identity: ' + node + ' = ' + network)
        return match[2]


def load_sources(profile, directory):
    directory = Path(directory).resolve()
    netlists = {}
    evidence = {}
    for role, source in profile['sources'].items():
        filename = source['filename']
        if Path(filename).name != filename or filename in ('.', '..'):
            raise ValueError('source filename must be a basename: ' + filename)
        path = directory / filename
        if not path.resolve().is_relative_to(directory) or not path.is_file():
            raise ValueError('missing or escaping netlist input: ' + filename)
        payload = path.read_bytes()
        if digest(payload) != source['sha256']:
            raise ValueError('netlist input drifted: ' + filename)
        netlists[role] = Netlist(payload)
        evidence[role] = dict(filename=filename, sha256=digest(payload),
                              networks=len(netlists[role].nets), nodes=len(netlists[role].nodes))
    return netlists, evidence


def parse_locations(text):
    locations = {}
    for line in text.splitlines():
        match = LOCATION.fullmatch(line.strip())
        if not match:
            if line.strip().startswith('IO_LOC'):
                raise ValueError('malformed IO_LOC: ' + line)
            continue
        port, fields = match.groups()
        balls = [ball.strip() for ball in fields.split(',')]
        if port in locations or not all(re.fullmatch(r'[A-Z]+\d+', ball) for ball in balls):
            raise ValueError('duplicate port or invalid ball: ' + port)
        locations[port] = balls
    return locations


def checked_ulpi_bypass(bypass):
    if not isinstance(bypass, dict) or any(part not in ('U4', 'U5') or mode != 'not_fitted_short'
                                           for part, mode in bypass.items()):
        raise ValueError('unreviewed ULPI bypass declaration')
    return bypass


def check_ulpi_electrical(carrier, bypass=None):
    bypass = checked_ulpi_bypass({} if bypass is None else bypass)
    supplies_mv = {'VDD_1V8': 1800, '3V3_USB3300': 3300}
    translators = []
    findings = []
    for part, supply_a, supply_b in (('U4', 'U4.2', 'U4.19'), ('U5', 'U5.1', 'U5.14')):
        bypassed = part in bypass
        supply_node = supply_b if bypassed else supply_a
        network = carrier.network(supply_node)
        nominal_mv = supplies_mv.get(network)
        translators.append(dict(part=part, assembly=bypass.get(part, 'fitted'),
                                phy_side='B' if bypassed else 'A', supply_node=supply_node,
                                supply_network=network, nominal_mv=nominal_mv))
        if nominal_mv is None:
            findings.append(dict(code='ULPI_UNKNOWN_SUPPLY', part=part, node=supply_node,
                                 message='No reviewed nominal voltage for PHY-side translator supply'))
        elif bypassed and nominal_mv != 3300:
            findings.append(dict(code='ULPI_BYPASS_SUPPLY_DOMAIN', part=part, node=supply_node,
                                 nominal_mv=nominal_mv,
                                 message='Direct USB3300 ULPI path requires the reviewed 3.3 V domain'))
        elif not bypassed and nominal_mv < 2600:
            findings.append(dict(code='ULPI_PHY_OUTPUT_DOMAIN', part=part, node=supply_node,
                                 translator_input_high_max_mv=nominal_mv,
                                 phy_output_supply_min_mv=3000,
                                 phy_output_high_min_mv=2600,
                                 message='USB3300 output high is outside the translator A-side recommended input range'))
    stp_supply = next(entry for entry in translators if entry['part'] == 'U5')
    if 'U5' not in bypass and stp_supply['nominal_mv'] is not None and stp_supply['nominal_mv'] < 2000:
        findings.append(dict(code='ULPI_STP_HIGH_LEVEL', part='U5',
                             driver_node='U5.3', receiver_node='U2.13',
                             driver_supply_mv=stp_supply['nominal_mv'], receiver_vih_min_mv=2000,
                             message='Translator PHY-side supply is below USB3300 minimum valid high input'))
    return dict(status='blocked' if findings else 'no_voltage_domain_conflict_detected',
                scope='USB3300 nominal ULPI voltage domains and declared translator assembly only',
                actual_board_measured=False, full_electrical_acceptance=False,
                translators=translators, findings=findings)


def resolve(profile, netlists, core_text):
    if profile.get('schema_version') != 1:
        raise ValueError('unsupported board profile schema')
    bypass = checked_ulpi_bypass(profile.get('ulpi_bypass', {}))
    models = profile.get('electrical_evidence', {}).get('component_models')
    expected_models = {'U2': 'USB3300-EZK', 'U4': 'TXS0108EPWR', 'U5': 'TXS0104EPWR'}
    if models != {part: model for part, model in expected_models.items() if part not in bypass}:
        raise ValueError('unreviewed USB2 device models')
    carrier, amplifier, bluetooth = [netlists[role] for role in ('carrier', 'amplifier', 'bluetooth')]
    reference = parse_locations(core_text)
    ports = {}

    def add(port, balls, origin):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\[\d+\])?', port) or port in ports:
            raise ValueError('invalid or duplicate port: ' + port)
        balls = balls if isinstance(balls, list) else [balls]
        if not balls or not all(re.fullmatch(r'[A-Z]+\d+', ball) for ball in balls):
            raise ValueError('invalid ball for port: ' + port)
        occupied = {ball for entry in ports.values() for ball in entry['balls']}
        if len(set(balls)) != len(balls) or occupied.intersection(balls):
            raise ValueError('ball collision: ' + port + ' = ' + ','.join(balls))
        ports[port] = dict(balls=balls, origin=origin)

    core_ports = set(profile['core_ports']) | {port for port in reference if port.startswith('ddr_')}
    for port in sorted(core_ports):
        if port not in reference:
            raise ValueError('missing core port: ' + port)
        add(port, reference[port], 'unchanged_locked_core')
    core_lines = []
    for line in core_text.splitlines():
        match = re.match(r'^IO_(?:LOC|PORT)\s+"([^"]+)"', line.strip())
        if match and match[1] in core_ports:
            core_lines.append(line)

    for channel in profile['audio']:
        pin = channel['pin']
        connector = 'FPC1.' + str(pin)
        if 'array' in channel:
            near, far = channel['array']
            near_part, near_pin = near.split('.')
            far_part, far_pin = far.split('.')
            if near_part not in ('RN1', 'RN2') or near_part != far_part or {int(near_pin), int(far_pin)} not in ({1, 8}, {2, 7}, {3, 6}, {4, 5}):
                raise ValueError('undeclared resistor-array pairing: ' + channel['port'])
            amplifier.same(connector, near)
            amplifier.same(far, channel['dac'])
        else:
            amplifier.same(connector, channel['dac'], *channel.get('additional_nodes', []))
        add(channel['port'], carrier.ball('FPC2.' + str(pin), 2), 'audio_1_to_1_candidate')
    for pin in (1, 2, 3, 4, 5, 6, 7, 18, 19, 20, 21, 22, 23, 24):
        supply = carrier.network('FPC2.' + str(pin))
        peer_supply = amplifier.network('FPC1.' + str(pin))
        if supply != peer_supply and (supply, peer_supply) != ('+12V', 'INPUT_12V'):
            raise ValueError('audio cable supply mismatch: ' + str(pin))

    for channel in profile['ulpi']:
        low, high = channel['bridge']
        carrier.same(channel['phy'], low)
        add(channel['port'], carrier.ball(high, 2), 'usb2_ulpi_level_shifter')
    supplies = {'U4.19': '3V3_USB3300', 'U5.14': '3V3_USB3300'}
    if 'U4' not in bypass:
        supplies.update({'U4.2': 'VDD_1V8', 'U4.10': 'VDD_1V8'})
    if 'U5' not in bypass:
        supplies.update({'U5.1': 'VDD_1V8', 'U5.8': 'VDD_1V8'})
    for node, supply in supplies.items():
        if carrier.network(node) != supply:
            raise ValueError('ULPI level-shifter supply/OE changed: ' + node)
    if carrier.network('U2.9') != 'GND':
        raise ValueError('USB3300 reset wiring changed')
    for port, node in profile['tf_spi'].items():
        add(port, carrier.ball(node, 5), 'tf_card_spi')

    hdmi = []
    for pair in profile['hdmi_pairs']:
        native_balls = [carrier.ball(node, 3) for node in pair['native_nodes']]
        if native_balls != reference.get(pair['port']):
            raise ValueError('native HDMI differential pair drifted: ' + pair['port'])
        connected = []
        for native in pair['native_nodes']:
            destinations = []
            for capacitor in pair['capacitors']:
                for terminal in (1, 2):
                    near = capacitor + '.' + str(terminal)
                    far = capacitor + '.' + str(3 - terminal)
                    if carrier.network(native) == carrier.network(near):
                        destinations.extend(index for index, node in enumerate(pair['connector_nodes'])
                                            if carrier.network(far) == carrier.network(node))
            if len(destinations) != 1:
                raise ValueError('ambiguous HDMI capacitor route: ' + native)
            connected.extend(destinations)
        if connected not in ([0, 1], [1, 0]):
            raise ValueError('invalid HDMI differential endpoints: ' + pair['port'])
        add(pair['port'], native_balls, 'native_differential_pair')
        hdmi.append(dict(port=pair['port'], native_balls=native_balls,
                         invert_serialized_lane=connected == [1, 0], implemented=False))
    for port, channel in profile['carrier_controls'].items():
        add(port, carrier.ball(channel['node'], channel['bank']), 'carrier_control')
    carrier.same('R21.2', 'USB3.13')

    ble = []
    for channel in profile['bluetooth']:
        pin = channel['pin']
        peer = 'FPC1.' + str(25 - pin)
        module_net = bluetooth.same(peer, channel['module'])
        if module_net != channel['signal']:
            raise ValueError('Bluetooth module signal drifted: ' + peer)
        network = carrier.network('FPC3.' + str(pin))
        if network != module_net and not (pin == 5 and network == 'BANK5_T14' and module_net == 'UART_RX'):
            raise ValueError('Bluetooth cable signal mismatch: ' + network + ' / ' + module_net)
        ble.append(dict(signal=module_net, carrier_pin=pin, module_pin=25 - pin,
                        module_node=channel['module'], carrier_network=network))
    for pin in (1, 2, 3, 4, 21, 22, 23, 24):
        if carrier.network('FPC3.' + str(pin)) != bluetooth.network('FPC1.' + str(25 - pin)):
            raise ValueError('Bluetooth cable supply mismatch: ' + str(pin))

    reserved = {node: carrier.ball(node) for node in profile['reserved_nodes']}
    occupied = {ball for entry in ports.values() for ball in entry['balls']}
    if occupied.intersection(reserved.values()):
        raise ValueError('assigned ball overlaps reserved board function')
    if ports.keys() & set(profile['retired_ports']):
        raise ValueError('retired Dock port remains assigned')
    return dict(schema_version=1, identity=profile['identity'], device=profile['device'],
                validation_stage='offline_pinout_only', source_policy='explicit_custom_board_pinout',
                synthesis_allowed=False, hardware_accepted=False, sram_deployed=False,
                flash_deployed=False, bitstream_sha256=None, ports=ports,
                unchanged_core_constraints=core_lines, hdmi_polarity=hdmi,
                bluetooth_cable=ble, reserved_balls=reserved,
                retired_ports=profile['retired_ports'], assumptions=profile['assumptions'],
                ulpi_bypass=bypass, electrical_check=check_ulpi_electrical(carrier, bypass),
                electrical_evidence=profile['electrical_evidence'],
                implementation_gaps=profile['implementation_gaps'])


def render_constraints(plan):
    lines = list(plan['unchanged_core_constraints'])
    for port, entry in plan['ports'].items():
        if entry['origin'] != 'unchanged_locked_core':
            lines.append('IO_LOC "' + port + '" ' + ','.join(entry['balls']) + ';')
    return '\n'.join(lines) + '\n'


def prepare(root, input_directory, output=None):
    root = Path(root).resolve()
    profile_path = root / PROFILE_PATH
    profile = json.loads(profile_path.read_bytes())
    netlists, sources = load_sources(profile, input_directory)
    baseline = load_baseline(root, profile['core_baseline'])
    core_payload = baseline.read_bytes('constraints/tang_mega_138k.cst')
    plan = resolve(profile, netlists, core_payload.decode('utf-8-sig'))
    constraints = render_constraints(plan)
    if parse_locations(constraints) != {port: entry['balls'] for port, entry in plan['ports'].items()}:
        raise ValueError('generated constraints do not match resolved locations')
    plan['source_baseline'] = baseline.evidence()
    plan['source_inputs'] = sources
    plan['core_constraints_sha256'] = digest(core_payload)
    plan['recipe_inputs'] = {PROFILE_PATH.as_posix(): digest(profile_path.read_bytes()),
                             'tools/workstation_pinout.py': digest(Path(__file__).read_bytes()),
                             'tools/workstation_baselines.py': digest(Path(__file__).with_name('workstation_baselines.py').read_bytes()),
                             'build.py': digest((root / 'build.py').read_bytes())}
    plan['constraints_sha256'] = digest(constraints.encode('utf-8'))
    output = Path(output).resolve() if output is not None else root / 'results' / datetime.now().strftime('custom_138k_pinout_%Y%m%d_%H%M%S_%f')
    if output.is_relative_to(Path(input_directory).resolve()):
        raise ValueError('pinout output must not be written inside netlist inputs')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'custom_138k.locations.cst').write_text(constraints, encoding='utf-8')
    (output / 'pinout.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output, plan
