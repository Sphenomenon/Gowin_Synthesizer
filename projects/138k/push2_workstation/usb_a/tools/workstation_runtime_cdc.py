"""Reviewed runtime CDC constraints and sealed source-netlist checks.

First tranche: 21 Gray groups plus the shared BLE reset release aliases.
This does not close the other records in the 150-record source inventory.
"""

from collections import defaultdict
from pathlib import Path
import argparse
import fnmatch
import json
import math
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_custom_usb2_cdc import pattern, query
from tools.workstation_runtime_clock_audit import (
    AUDIT_SOURCES as CLOCK_AUDIT_SOURCES, MODE_EXCLUSIONS, VG_RELATIVE,
    audit_runtime_clocks, digest, file_sha, verify_synthesis_identity,
)
from tools.workstation_synthesis_netlist import SynthesisNetlist

TOP = 'workstation_custom_138k_top'
POLICY = 'native-runtime-cdc-gray-reset-v1'
DELAY = 'u_managed/runtime/service/workstation/runtime_effects.effects/delay_stage/'
GRAY = (
    # id, scope, producer, first, second, width, source domain, destination domain
    ('guard-heartbeat', 'u_runtime_memory_guard', 'memory_gray', 'gray_meta', 'gray_sync', 32, 'memory', 'control'),
    ('midi-drop-count', 'u_managed/midi_drops', 'gray', 'meta', 'sync_value', 32, 'control', 'compute'),
    ('clock-reference_48_monitor', 'u_managed/runtime/clocks/reference_48_monitor', 'source_gray', 'gray_meta', 'gray_sync', 32, 'reference48', 'control'),
    ('clock-reference_44_monitor', 'u_managed/runtime/clocks/reference_44_monitor', 'source_gray', 'gray_meta', 'gray_sync', 32, 'reference44', 'control'),
    ('clock-selected_monitor', 'u_managed/runtime/clocks/selected_monitor', 'source_gray', 'gray_meta', 'gray_sync', 32, 'selected', 'control'),
    ('delay-write-wptr', DELAY + 'u_write_fifo', 'write_gray', 'write_gray_meta', 'write_gray_sync', 10, 'compute', 'memory'),
    ('delay-write-rptr', DELAY + 'u_write_fifo', 'read_gray', 'read_gray_meta', 'read_gray_sync', 10, 'memory', 'compute'),
    ('delay-read-wptr', DELAY + 'u_read_fifo', 'write_gray', 'write_gray_meta', 'write_gray_sync', 10, 'memory', 'compute'),
    ('delay-read-rptr', DELAY + 'u_read_fifo', 'read_gray', 'read_gray_meta', 'read_gray_sync', 10, 'compute', 'memory'),
    ('physical-observer-wptr', 'u_managed/observation/frames', 'write_gray', 'write_gray_meta', 'write_gray_sync', 5, 'selected', 'compute'),
    ('physical-observer-rptr', 'u_managed/observation/frames', 'read_gray', 'read_gray_meta', 'read_gray_sync', 5, 'compute', 'selected'),
    ('physical-observer-drops', 'u_managed/observation/drops', 'gray', 'meta', 'sync_value', 32, 'selected', 'compute'),
    ('display-memory-drops', 'u_video/u_runtime_display/drops', 'gray', 'meta', 'sync_value', 32, 'control', 'memory'),
    ('tf-frames-wptr', 'u_tf_audio/frames/frames_0', 'write_gray', 'write_gray_meta', 'write_gray_sync', 5, 'control', 'compute'),
    ('tf-frames-rptr', 'u_tf_audio/frames/frames_0', 'read_gray', 'read_gray_meta', 'read_gray_sync', 5, 'compute', 'control'),
    ('tf-generation', 'u_tf_audio/frames', 'source_generation_gray', 'generation_meta', 'generation_sync', 32, 'control', 'compute'),
    ('tf-generation-ack', 'u_tf_audio/frames', 'ack_gray', 'ack_meta', 'ack_sync', 32, 'compute', 'control'),
    ('tf-byte-capture-wptr', 'u_tf_audio/path/u_capture_fifo', 'wr_gray', 'wr_gray_r1', 'wr_gray_r2', 13, 'control', 'memory'),
    ('tf-byte-capture-rptr', 'u_tf_audio/path/u_capture_fifo', 'rd_gray', 'rd_gray_w1', 'rd_gray_w2', 13, 'memory', 'control'),
    ('tf-byte-playback-wptr', 'u_tf_audio/path/u_playback_fifo', 'wr_gray', 'wr_gray_r1', 'wr_gray_r2', 13, 'memory', 'control'),
    ('tf-byte-playback-rptr', 'u_tf_audio/path/u_playback_fifo', 'rd_gray', 'rd_gray_w1', 'rd_gray_w2', 13, 'control', 'memory'),
)
# Registered binary MSB equals registered Gray MSB; Gowin merged these exact
# source bits. Do not accept arbitrary missing Gray bits or discover aliases
# merely by following whatever happens to drive the first stage.
GRAY_MSB_ALIASES = {
    'delay-write-wptr': 'write_binary', 'delay-write-rptr': 'read_binary',
    'delay-read-wptr': 'write_binary', 'delay-read-rptr': 'read_binary',
    'physical-observer-rptr': 'read_binary', 'tf-frames-rptr': 'read_binary',
    'tf-generation': 'source_generation_o', 'tf-generation-ack': 'ack_binary',
    'tf-byte-capture-rptr': 'rd_bin', 'tf-byte-playback-rptr': 'rd_bin',
}
BLE_RELEASE_ALIASES = (
    ('source', 'u_managed/observation/drops', 'source_release', 'selected', 'ack_meta'),
    ('destination', 'u_managed/midi_bytes', 'source_release', 'control', 'req_meta'),
)
# These unchanged peripheral commands do not alter reviewed Gray setup paths.
# Keep exact shapes instead of allowing arbitrary new timing commands.
PERIPHERAL_SDC = (
    'set_min_delay 0.800 -from [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/ddr_init_internal_r_s0/Q}] '
    '-to [get_pins {u_memory/u_ddr3/gw3_top/u_ddr_phy_top/wloadn_3_s0/D}]',
    'set_input_delay 15.000 -clock [get_clocks {clk_50m}] [get_ports {flash_miso}]',
    *(f'report_timing -{kind} -max_paths 2000 -max_common_paths 1'
      for kind in ('setup', 'hold', 'recovery', 'removal')),
)
AUDIT_SOURCES = tuple(dict.fromkeys((*CLOCK_AUDIT_SOURCES,
    'tools/workstation_runtime_cdc.py', 'tools/workstation_runtime_profile.py',
    'tools/workstation_custom_board.py', 'tools/workstation_custom_usb2_cdc.py',
    'sim/test_workstation_runtime_cdc.py', 'sim/test_workstation_runtime_sources.py',
    'sim/test_workstation_custom_board.py')))


def require(condition, message):
    if not condition:
        raise ValueError('runtime CDC audit: ' + message)


def runtime_cdc_bundle(root):
    clocks = clock_bundle(root)['plan']
    frequencies = {x['name']: x['frequency_hz'] for x in (*clocks['primary'], *clocks['generated'])}
    frequencies = dict(control=frequencies['clk_50m'], compute=frequencies['audio_76m8'],
                       memory=frequencies['ddr_ui100'], reference48=frequencies['dac_ref12m288'],
                       reference44=16934400, selected=max(frequencies['dac_ref12m288'], 16934400))
    lines, groups = [], []
    for identity, scope, source, first, second, width, origin, destination in GRAY:
        # Round down: serialization must never relax a one-source-period bound.
        delay = math.floor(1e12 / frequencies[origin]) / 1000
        sources = [pattern(scope, source + '_' + str(bit), 'Q')
                   for bit in range(width - (identity in GRAY_MSB_ALIASES))]
        if identity in GRAY_MSB_ALIASES:
            sources.append(pattern(scope, GRAY_MSB_ALIASES[identity] + '_' + str(width - 1), 'Q'))
        selectors = dict(source=sources,
                         first=[pattern(scope, first + '_' + str(bit), 'D') for bit in range(width)])
        path = f"-from {query(' '.join(selectors['source']))} -to {query(' '.join(selectors['first']))}"
        lines += [f'set_max_delay {delay:.3f} {path}', f'set_false_path -hold {path}']
        groups.append(dict(id=identity, scope=scope, source=source, first=first, second=second,
            width=width, source_domain=origin, destination_domain=destination, selectors=selectors,
            registered_msb_alias=GRAY_MSB_ALIASES.get(identity),
            max_delay_ns=delay, source_period_ns=1e9 / frequencies[origin],
            setup_false_path=False, propagation_skew_bound_method='nonnegative_bit_flight_bounded_by_source_period'))
    reset_selectors = [pattern(scope, stem, 'CLEAR', True)
                       for _, scope, stem, _, _ in BLE_RELEASE_ALIASES]
    lines.append('set_false_path -to ' + query(' '.join(reset_selectors)))
    return dict(policy=POLICY, source='tools/workstation_runtime_cdc.py',
        source_sha256=file_sha(Path(root) / 'tools/workstation_runtime_cdc.py'),
        gray_groups=groups, ble_reset_alias_selectors=reset_selectors, sdc='\n'.join(lines) + '\n',
        source_inventory_group_count=150, reviewed_gray_group_count=21, reviewed_gray_bits=400,
        reviewed_reset_alias_group='ble-physical-tuple-reset', remaining_inventory_complete=False,
        constraints_complete=False, physical_cdc_accepted=False, routed_propagation_verified=False,
        remaining=['Non-Gray held payload capture, identity comparison and enable endpoints',
                   'FIFO memory ownership/collision and restart clear/drain contracts',
                   'Remaining level/pulse and local release groups, including new USB fence',
                   'Tool-side selector resolution and routed max flight/skew/reset acceptance'])


def _register_bits(n, scope, stem, width):
    require(scope in n.frames, 'Gray or reset scope missing: ' + scope)
    found = {}
    for path, c in n.cells.items():
        m = re.fullmatch(re.escape(scope + '/' + stem) + r'_(\d+)_s\d+', path)
        if m and c['kind'].startswith('DFF'):
            bit = int(m[1])
            require(bit not in found, 'duplicate register bit: ' + scope + '/' + stem)
            found[bit] = path
    require(set(found) == set(range(width)), 'exact register bit inventory: ' + scope + '/' + stem)
    return found


def audit_runtime_cdc(root, netlist_text, clock_audit):
    """Map every reviewed bit and reset alias; physical gates remain false."""
    bundle = runtime_cdc_bundle(root)
    n = SynthesisNetlist(netlist_text, TOP)
    clocks = clock_audit['base_13_clock_audit']['clocks']
    domains = {k: clocks[v]['net'] for k, v in
               dict(control='clk_50m', compute='audio_76m8', memory='ddr_ui100', reference48='dac_ref12m288').items()}
    domains.update(reference44='clk_16m9344', selected=clock_audit['dcs']['output_net'])
    regs = {p: c for p, c in n.cells.items() if c['kind'].startswith('DFF')}
    q_drivers, combinational, consumers = defaultdict(list), defaultdict(list), defaultdict(list)
    high = {"1'b1"}
    for p, c in n.cells.items():
        if p in regs:
            q_drivers[n.pin(p, 'Q')].append(p)
        elif c['kind'] == 'VCC':
            high.add(n.pin(p, 'V'))
        if c['kind'] in n.modules:
            continue
        for port in c['ports']:
            net = n.pin(p, port)
            if c['kind'].startswith('LUT') and port == 'F' or c['kind'] == 'INV' and port == 'O':
                combinational[net].append(p)
            if port not in ('Q', 'F', 'O', 'OF', 'SUM', 'COUT', 'CARRY', 'V', 'G'):
                consumers[net].append((p, port))

    def clear_gate(destination, clock):
        drivers = combinational[n.pin(destination, 'D')]
        require(len(drivers) == 1, 'Gray local-clear LUT driver: ' + destination)
        lut = drivers[0]
        require(n.cells[lut]['kind'] == 'LUT3' and n.cells[lut]['parameters'].get('INIT') == "8'h90",
                'Gray local-clear LUT truth table: ' + destination)
        local, nets = [], []
        for port in ('I0', 'I1'):
            net = n.pin(lut, port)
            drivers = q_drivers[net]
            require(len(drivers) == 1 and n.pin(drivers[0], 'CLK') == clock,
                    'Gray clear input is not a local register: ' + destination)
            local.append(dict(lut_pin=port, register=drivers[0], clock=clock))
            nets.append(net)
        return n.pin(lut, 'I2'), lut, local, nets

    rows, resolved = [], {}
    for group in bundle['gray_groups']:
        width, scope = group['width'], group['scope']
        alias = GRAY_MSB_ALIASES.get(group['id'])
        source = _register_bits(n, scope, group['source'], width - bool(alias))
        if alias:
            paths = [p for p, c in regs.items() if re.fullmatch(
                re.escape(scope + '/' + alias + '_' + str(width - 1)) + r'_s\d+', p)]
            require(len(paths) == 1, 'Gray registered MSB alias missing or ambiguous: ' + group['id'])
            source[width - 1] = paths[0]
        first, second = [_register_bits(n, scope, group[k], width) for k in ('first', 'second')]
        paths = []
        for bit in range(group['width']):
            s, f, t = source[bit], first[bit], second[bit]
            require(n.pin(s, 'CLK') == domains[group['source_domain']], 'Gray source clock: ' + s)
            require(all(n.pin(p, 'CLK') == domains[group['destination_domain']] for p in (f, t)),
                    'Gray destination clock: ' + f)
            require(all('CE' not in n.cells[p]['ports'] or n.pin(p, 'CE') in high for p in (f, t)),
                    'Gray synchronizer enable is conditional: ' + f)
            data = n.pin(f, 'D')
            second_data, fanout = n.pin(t, 'D'), (t, 'D')
            through, second_through, local = [], [], []
            if group['id'].startswith('tf-byte-'):
                data, lut, local, clears = clear_gate(f, domains[group['destination_domain']])
                second_data, second_lut, _, second_clears = clear_gate(t, domains[group['destination_domain']])
                require(clears == second_clears, 'Gray clear conditions differ between stages: ' + f)
                fanout = (second_lut, 'I2')
                through = [dict(cell=lut, kind='LUT3', INIT="8'h90", gray_input='I2')]
                second_through = [dict(cell=second_lut, kind='LUT3', INIT="8'h90", first_stage_input='I2')]
            require(n.pin(f, 'Q') == second_data, 'Gray second-stage connection: ' + f)
            require(consumers[n.pin(f, 'Q')] == [fanout], 'Gray first-stage fanout: ' + f)
            require(data == n.pin(s, 'Q') and q_drivers[data] == [s], 'Gray bit identity or unique producer: ' + f)
            paths.append(dict(bit=bit, source=s, first=f, second=t,
                source_clock=n.pin(s, 'CLK'), destination_clock=n.pin(f, 'CLK'),
                source_q_net=data, first_d_net=n.pin(f, 'D'), through=through,
                second_through=second_through, local_clear_inputs=local))
        for key, collection, port in (('source', source, 'Q'), ('first', first, 'D')):
            selectors = group['selectors'][key]
            selectors = selectors if isinstance(selectors, list) else [selectors]
            union = set()
            for selector in selectors:
                actual = sorted(p + '/' + port for p, c in regs.items() if port in c['ports']
                                and fnmatch.fnmatchcase(p + '/' + port, selector))
                expected = sorted(p + '/' + port for p in collection.values()
                                  if fnmatch.fnmatchcase(p + '/' + port, selector))
                require(actual and actual == expected, 'selector expansion differs from exact bit inventory: ' + selector)
                resolved[selector] = actual
                union.update(actual)
            require(union == {p + '/' + port for p in collection.values()}, 'selector misses reviewed bits: ' + group['id'])
        rows.append(dict(**group, paths=paths, bit_identity_and_clock_verified=True))
    aliases, common_clear = [], None
    for direction, scope, stem, domain, consumer in BLE_RELEASE_ALIASES:
        chain = _register_bits(n, scope, stem, 3)
        for bit, p in chain.items():
            require(n.pin(p, 'CLK') == domains[domain], 'BLE release alias clock: ' + p)
            require(n.pin(p, 'D') == (n.pin(chain[bit - 1], 'Q') if bit else n.pin(p, 'CE')),
                    'BLE release alias shift: ' + p)
            require(n.pin(p, 'CE') in high, 'BLE release alias is not unconditional: ' + p)
            clear = n.pin(p, 'CLEAR')
            common_clear = common_clear or clear
            require(clear == common_clear, 'BLE release assertion differs')
        reset = n.pin('u_ble_pcm_cdc/' + consumer + '_s0', 'CLEAR')
        drivers = combinational[reset]
        require(len(drivers) == 1 and n.cells[drivers[0]]['kind'] == 'INV' and
                n.pin(drivers[0], 'I') == n.pin(chain[2], 'Q'), 'BLE release merged reset connectivity: ' + direction)
        selector = pattern(scope, stem, 'CLEAR', True)
        actual = sorted(p + '/CLEAR' for p, c in regs.items() if 'CLEAR' in c['ports']
                        and fnmatch.fnmatchcase(p + '/CLEAR', selector))
        require(actual == sorted(p + '/CLEAR' for p in chain.values()), 'BLE release alias selector: ' + direction)
        resolved[selector] = actual
        aliases.append(dict(direction=direction, registers=chain, clock=domains[domain],
                            assertion_net=clear, consumer='u_ble_pcm_cdc/' + consumer + '_s0/CLEAR',
                            inverter=drivers[0], consumer_assertion_net=reset))
    drivers = combinational[common_clear]
    require(len(drivers) == 1 and n.cells[drivers[0]]['kind'] == 'LUT2' and
            n.cells[drivers[0]]['parameters'].get('INIT') == "4'h7" and
            {n.pin(drivers[0], p) for p in ('I0', 'I1')} == {'reset_n', 'memory_guard_started'},
            'BLE alias common runtime reset assertion changed')
    require(not any('tf_run_meta' in p or 'tf_run_audio' in p for p in regs),
            'legacy TF run synchronizer unexpectedly active in native runtime')
    return dict(schema=1, policy=POLICY, scope='reviewed_21_gray_groups_and_ble_local_release_aliases',
        gray_groups=rows, gray_group_count=len(rows), gray_first_stage_bits=sum(len(x['paths']) for x in rows),
        ble_reset_aliases=aliases, resolved_pin_selectors=resolved,
        legacy_tf_run_pruned=True, reviewed_source_netlist_endpoints_verified=True,
        gray_encoding_behavior_verified=False,
        remaining_inventory_complete=False, held_payload_complete=False, fifo_payload_complete=False,
        single_bit_complete=False, reset_inventory_complete=False, constraints_complete=False,
        routed_propagation_verified=False, physical_cdc_accepted=False, sta_verified=False,
        tool_query_resolution_verified=False, hardware_tested=False, release_ready=False,
        deployment_allowed=False)


def validate_installed_constraints(root, sdc, result):
    """Check exact proposed lines and prohibit setup cuts on reviewed Gray data."""
    lines = sdc.splitlines()
    expected = runtime_cdc_bundle(root)['sdc'].splitlines()
    require(all(lines.count(line) == 1 for line in expected), 'reviewed runtime CDC constraints missing or duplicated')
    first_pins = {path for selector, paths in result['resolved_pin_selectors'].items()
                  if selector.endswith('/D') for path in paths}
    source_pins = {path for selector, paths in result['resolved_pin_selectors'].items()
                   if selector.endswith('/Q') for path in paths}

    def matches(line, side, pins):
        selected = re.findall(r'-' + side + r'\s+\[(get_pins|get_regs|get_ports)\s+\{([^}]+)\}\]', line)
        require(len(selected) <= 1, 'unsupported repeated timing query: ' + line)
        return not selected or any(
            fnmatch.fnmatchcase(p if kind == 'get_pins' else p.rsplit('/', 1)[0], selector)
            for kind, body in selected if kind != 'get_ports' for selector in body.split() for p in pins)

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        command = line.split()[0]
        require(command in ('create_clock', 'create_generated_clock', 'set_false_path',
                            'set_max_delay', 'set_min_delay', 'set_input_delay', 'report_timing'),
                'unreviewed SDC command: ' + line)
        require(not any(symbol in line for symbol in (';', '\\', '$')),
                'unsupported Tcl evaluation or continuation: ' + line)
        if command in ('set_min_delay', 'set_input_delay', 'report_timing'):
            require(line in PERIPHERAL_SDC, 'unreviewed peripheral SDC command: ' + line)
            continue
        if command in ('create_clock', 'create_generated_clock'):
            # run_audit separately requires the full exact clock declarations.
            continue
        queries = re.compile(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]')
        shape = queries.sub('QUERY', line)
        require('[' not in shape and ']' not in shape, 'unsupported timing query: ' + line)
        words, values, sides = shape.split()[1:], 0, set()
        while words:
            word = words.pop(0)
            if word in ('-from', '-to'):
                require(word not in sides and words and words.pop(0) == 'QUERY',
                        'unsupported timing endpoint syntax: ' + line)
                sides.add(word)
            elif command == 'set_false_path' and word in ('-hold', '-setup'):
                continue
            elif command == 'set_max_delay' and re.fullmatch(r'\d+(?:\.\d+)?', word):
                values += 1
            else:
                require(False, 'unsupported timing command shape: ' + line)
        require(values == (command == 'set_max_delay'), 'unsupported timing value: ' + line)
        if 'get_clocks' in line:
            require(line in MODE_EXCLUSIONS, 'whole-clock setup false path is forbidden')
            continue
        if line.startswith('set_false_path'):
            require(not ('-hold' in line.split() and '-setup' in line.split()),
                    'combined hold/setup false path is forbidden: ' + line)
            if '-hold' in line.split():
                if matches(line, 'to', first_pins) and matches(line, 'from', source_pins):
                    require(line in expected, 'unreviewed hold exception on reviewed Gray data: ' + line)
            else:
                require(not (matches(line, 'to', first_pins) and matches(line, 'from', source_pins)),
                        'setup false path masks reviewed Gray data: ' + line)
        elif matches(line, 'to', first_pins) and matches(line, 'from', source_pins):
            require(line in expected, 'unreviewed max delay overrides reviewed Gray data: ' + line)
    require(not any('tf_run_meta' in line for line in lines), 'legacy TF run selector remains in runtime SDC')
    return dict(reviewed_group_lines_installed=True, gray_setup_paths_not_false_pathed=True,
                tool_query_resolution_verified=False)


def run_audit(root, stage, evidence, *, endpoint_development=False):
    root, stage = Path(root), Path(stage)
    before = verify_synthesis_identity(stage, evidence)
    sources = {p: file_sha(root / p) for p in AUDIT_SOURCES}
    text = (stage / VG_RELATIVE).read_text()
    clocks = audit_runtime_clocks(root, stage, text)
    result = audit_runtime_cdc(root, text, clocks)
    sdc = (stage / 'constraints/custom_138k.sdc').read_text()
    result['candidate_constraints_installed'] = False
    if not endpoint_development:
        result['constraint_installation'] = validate_installed_constraints(root, sdc, result)
        result['candidate_constraints_installed'] = True
    result['endpoint_development_only'] = endpoint_development
    result['clock_audit'] = clocks
    after = verify_synthesis_identity(stage, evidence)
    require(before == after and sources == {p: file_sha(root / p) for p in AUDIT_SOURCES},
            'synthesis or audit inputs drifted during audit')
    identity = digest(json.dumps(dict(synthesis=before, audit_sources=sources,
                                     endpoint_development=endpoint_development), sort_keys=True).encode())
    result.update(identity='runtime-cdc-gray-reset-source-v1-' + identity[:16], source_set_sha256=identity,
                  synthesis=before, audit_source_sha256=sources, source_seal_before_and_after=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--synthesis-evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint-development', action='store_true',
                        help='Map an older sealed VG without claiming proposed constraints were installed')
    args = parser.parse_args()
    result = run_audit(ROOT, args.project, args.synthesis_evidence,
                       endpoint_development=args.endpoint_development)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('identity', 'gray_group_count', 'gray_first_stage_bits',
        'candidate_constraints_installed', 'endpoint_development_only', 'constraints_complete', 'physical_cdc_accepted')}))


if __name__ == '__main__':
    main()
