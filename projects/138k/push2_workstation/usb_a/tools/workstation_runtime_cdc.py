"""Reviewed runtime CDC constraints and sealed source-netlist checks.

Second tranche: 21 direct Gray groups, shared BLE reset release aliases,
held media-stop request/result and native USB stopped-compute queue fencing.
This does not close the historical 150-record or newer additive inventories.
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
POLICY = 'native-runtime-cdc-gray-media-fence-v2'
MEDIA = 'u_managed/media_stop'
USB_INPUT = 'u_native_usb/input_owner'
MEDIA_CONTROLS = (
    ('media-stop-request', 'request_toggle', 'request_compute', 2, 'control', 'compute'),
    ('media-stop-acknowledge', 'acknowledge_toggle', 'acknowledge_50', 3, 'compute', 'control'),
    ('media-stop-held-failure', 'compute_failure', 'failed_50', 2, 'compute', 'control'),
)
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
    ('tf-byte-capture-wptr', 'u_tf_audio/path/g_runtime_capture.u_capture_fifo', 'wr_gray', 'wr_gray_r1', 'wr_gray_r2', 13, 'control', 'memory'),
    ('tf-byte-capture-rptr', 'u_tf_audio/path/g_runtime_capture.u_capture_fifo', 'rd_gray', 'rd_gray_w1', 'rd_gray_w2', 13, 'memory', 'control'),
    ('tf-byte-playback-wptr', 'u_tf_audio/path/g_runtime_playback.u_playback_fifo', 'wr_gray', 'wr_gray_r1', 'wr_gray_r2', 13, 'memory', 'control'),
    ('tf-byte-playback-rptr', 'u_tf_audio/path/g_runtime_playback.u_playback_fifo', 'rd_gray', 'rd_gray_w1', 'rd_gray_w2', 13, 'control', 'memory'),
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
BLE_RELEASE_SEPARATE_COMMON = (
    ('source', 'u_ble_pcm_cdc', 'source_release', 'selected', 'ack_meta'),
    ('destination', 'u_ble_pcm_cdc', 'destination_release', 'control', 'req_meta'),
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
NATIVE_PERIPHERAL_SDC = (
    # Keep the sealed historical native candidate's 1.800 ns request and
    # the current 3.500 ns physical hold repair as separate exact commands.
    PERIPHERAL_SDC[0].replace('0.800', '1.800', 1),
    PERIPHERAL_SDC[0].replace('0.800', '3.500', 1),
    *PERIPHERAL_SDC[1:],
    *(f'report_timing -{kind} -from_clock [get_clocks {{cpu_core100}}] '
      '-to_clock [get_clocks {cpu_core100}] -max_paths 8 -max_common_paths 1'
      for kind in ('setup', 'hold')),
    *(f'report_timing -{kind} {origin}-to_clock [get_clocks {{clk_50m}}] '
      '-max_paths 100 -max_common_paths 1'
      for origin in ('-from_clock [get_clocks {clk_50m}] ', '')
      for kind in ('setup', 'hold')),
)
AUDIT_SOURCES = tuple(dict.fromkeys((*CLOCK_AUDIT_SOURCES,
    'tools/workstation_runtime_cdc.py', 'tools/workstation_runtime_profile.py',
    'tools/workstation_custom_board.py', 'tools/workstation_custom_usb2_cdc.py',
    'sim/test_workstation_runtime_cdc.py', 'sim/test_workstation_runtime_sources.py',
    'sim/test_workstation_custom_board.py')))


def require(condition, message):
    if not condition:
        raise ValueError('runtime CDC audit: ' + message)


def custom_board_header(text):
    """Stop at the custom-board outer else, allowing nested parameter guards."""
    marker = 'module workstation_custom_138k_top'
    require(text.count(marker) == 1, 'staged custom-board header missing/duplicate')
    lines = text[text.index(marker):].splitlines(keepends=True)
    depth, selected = 0, []
    for line in lines:
        directive = re.match(r'\s*`(ifdef|ifndef|endif|else|elsif)\b', line)
        if directive:
            kind = directive[1]
            if kind in ('else', 'elsif') and depth == 0:
                return ''.join(selected)
            if kind in ('ifdef', 'ifndef'):
                depth += 1
            elif kind == 'endif':
                depth -= 1
                require(depth >= 0, 'staged custom-board header nesting changed')
        selected.append(line)
    raise ValueError('runtime CDC audit: staged custom-board outer else missing')


def prepared_ble_reset_policy(stage):
    """Select only the explicit common-reset wiring in a sealed staged top."""
    relative = 'rtl/workstation/gw138k_push_workstation_top.v'
    text = (Path(stage) / relative).read_text()
    instances = re.findall(r'workstation_runtime_controlled\s*#\((.*?)\)\s*u_managed\s*\((.*?)\);', text, re.S)
    require(len(instances) == 1, 'staged runtime instance missing/duplicate')
    parameters, ports = instances[0]
    selected = re.findall(r'\.SEPARATE_COMMON_RESET\s*\(\s*([^()]+)\s*\)', parameters)
    if not selected or selected == ['0']:
        return dict(mode='legacy-shared-release', raw_common_reset=False)
    require(selected == ['1'], 'staged common-reset selection is not explicit')
    custom = custom_board_header(text)
    require('module workstation_custom_138k_top' in custom and
            len(re.findall(r"\bwire\s+button1_n\s*=\s*1'b1\s*;", custom)) == 1 and
            len(re.findall(r'\.common_reset_ni\s*\(\s*button1_n\s*\)', ports)) == 1 and
            len(re.findall(r'\.rst_ni\s*\(\s*runtime_reset_n\s*\)', ports)) == 1 and
            len(re.findall(r'\bwire\s+runtime_reset_n\s*=\s*reset_n\s*&&\s*memory_guard_started\s*;', text)) == 1,
            'staged raw button/common assertion or startup grant changed')
    mailboxes = re.findall(r'gw138k_stream_cdc\s*#\(\s*\.WIDTH\s*\(\s*98\s*\)\s*\)\s*u_ble_pcm_cdc\s*\((.*?)\);', text, re.S)
    require(len(mailboxes) == 1 and
            len(re.findall(r'\.reset_n\s*\(\s*runtime_reset_n\s*\)', mailboxes[0])) == 1 and
            len(re.findall(r'\.source_clk\s*\(\s*ble_frame_clock\s*\)', mailboxes[0])) == 1 and
            len(re.findall(r'\.destination_clk\s*\(\s*clk_50m\s*\)', mailboxes[0])) == 1,
            'staged BLE runtime-reset or clock wiring changed')
    controlled_relative = 'rtl/workstation/workstation_runtime_controlled.sv'
    controlled = (Path(stage) / controlled_relative).read_text()
    media = re.findall(r'workstation_runtime_media_stop_bridge\s*#\((.*?)\)\s*media_stop\s*\((.*?)\);', controlled, re.S)
    require(len(media) == 1 and
            re.findall(r'\.SEPARATE_DOMAIN_RESETS\s*\(\s*([^()]+)\s*\)', media[0][0]) == ['SEPARATE_COMMON_RESET'] and
            all(len(re.findall(r'\.' + port + r'\s*\(\s*' + signal + r'\s*\)', media[0][1])) == 1
                for port, signal in (('reset_ni', 'common_reset_n'), ('control_reset_ni', 'reset_50_n'),
                                     ('compute_reset_ni', 'reset_compute_n'))),
            'staged media domain-reset selection or wiring changed')
    media_modules = re.findall(r'module\s+workstation_runtime_media_stop_bridge\b(.*?)endmodule', controlled, re.S)
    require(len(media_modules) == 1 and
            all(len(re.findall(r'\bwire\s+local_' + domain + r'_reset_n\s*=\s*SEPARATE_DOMAIN_RESETS\s*\?\s*' +
                               domain + r'_reset_ni\s*:\s*reset_ni\s*;', media_modules[0])) == 1
                for domain in ('control', 'compute')) and
            len(re.findall(r'\bwire\s+common_reset_n\s*=\s*SEPARATE_COMMON_RESET\s*\?\s*common_reset_ni\s*:\s*rst_ni\s*;', controlled)) == 1,
            'staged media/common assertion changed')
    return dict(mode='separate-common-own-ble-release', raw_common_reset=True,
                raw_button_constant=1, ble_reset='runtime_reset_n',
                source_sha256={p: file_sha(Path(stage) / p) for p in (relative, controlled_relative)})


def runtime_cdc_bundle(root, *, raw_common_reset=False):
    require(type(raw_common_reset) is bool, 'raw common reset selection must be boolean')
    clocks = clock_bundle(root)['plan']
    frequencies = {x['name']: x['frequency_hz'] for x in (*clocks['primary'], *clocks['generated'])}
    frequencies = dict(control=frequencies['clk_50m'], compute=frequencies['audio_76m8'],
                       memory=frequencies['ddr_ui100'], usb=frequencies['usb_48m'], reference48=frequencies['dac_ref12m288'],
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
    # The raw-common native composition no longer shares BLE release FFs with
    # the physical-drop counter or constant MIDI adapter. Those aliases retire;
    # the BLE mailbox retains its own actual source/destination CLEAR pins.
    releases = BLE_RELEASE_SEPARATE_COMMON if raw_common_reset else BLE_RELEASE_ALIASES
    reset_selectors = [pattern(scope, stem, 'CLEAR', True)
                       for _, scope, stem, _, _ in releases]
    lines.append('set_false_path -to ' + query(' '.join(reset_selectors)))
    media_groups = []
    for identity, source, receiver, stages, origin, destination in MEDIA_CONTROLS:
        delay = math.floor(1e12 / frequencies[origin]) / 1000
        selectors = dict(source=[pattern(MEDIA, source, 'Q')],
                         first=[pattern(MEDIA, receiver + '_0', 'D')])
        path = f"-from {query(' '.join(selectors['source']))} -to {query(' '.join(selectors['first']))}"
        lines += [f'set_max_delay {delay:.3f} {path}', f'set_false_path -hold {path}']
        media_groups.append(dict(id=identity, source=source, receiver=receiver, stages=stages,
            source_domain=origin, destination_domain=destination, selectors=selectors,
            max_delay_ns=delay, source_period_ns=1e9 / frequencies[origin], setup_false_path=False,
            payload_contract='Held failure uses two stages; ACK uses three and changes on the same producer event.'))
    hold_selectors = dict(source=[pattern(MEDIA, 'hold_50', 'Q')],
                          assertion=[pattern(MEDIA, 'hold_compute', 'PRESET', True)])
    lines.append('set_max_delay 20.000 -from ' + query(' '.join(hold_selectors['source'])) +
                 ' -to ' + query(' '.join(hold_selectors['assertion'])))
    return_selectors = dict(source=[pattern(USB_INPUT, 'stopped_clock_queue_fence.drain_release_5', 'Q'),
                                   pattern(USB_INPUT, 'queue_release_5', 'Q')],
                            first=[pattern(USB_INPUT, 'queue_write_release_0', 'D')])
    path = f"-from {query(' '.join(return_selectors['source']))} -to {query(' '.join(return_selectors['first']))}"
    lines += [f'set_max_delay 13.020 {path}', f'set_false_path -hold {path}']
    assertion_selectors = dict(source=[pattern(USB_INPUT, 'queue_release_5', 'Q')],
        assertion=[pattern(USB_INPUT, 'stopped_clock_queue_fence.drain_release', 'CLEAR', True)])
    lines.append('set_max_delay 13.020 -from ' + query(' '.join(assertion_selectors['source'])) +
                 ' -to ' + query(' '.join(assertion_selectors['assertion'])))
    return dict(policy=POLICY, source='tools/workstation_runtime_cdc.py',
        source_sha256=file_sha(Path(root) / 'tools/workstation_runtime_cdc.py'),
        gray_groups=groups, ble_reset_alias_selectors=reset_selectors,
        raw_common_reset=raw_common_reset,
        media_control_groups=media_groups,
        media_hold_assertion=dict(selectors=hold_selectors, max_delay_ns=20.0, recovery_removal_cut=False),
        usb_queue_fence=dict(return_selectors=return_selectors, assertion_selectors=assertion_selectors,
            max_delay_ns=13.020, recovery_removal_cut=False), sdc='\n'.join(lines) + '\n',
        source_inventory_group_count=150, reviewed_gray_group_count=21, reviewed_gray_bits=400,
        reviewed_reset_alias_group='ble-physical-tuple-reset', remaining_inventory_complete=False,
        constraints_complete=False, physical_cdc_accepted=False, routed_propagation_verified=False,
        remaining=['Non-Gray held payload capture, identity comparison and enable endpoints',
                   'FIFO memory ownership/collision and restart clear/drain contracts',
                   'Other level/pulse and local release groups; USB input-reset source flight/pulse and full reset inventory',
                   'Tool-side selector resolution and routed max flight/skew/reset acceptance'])


def _register_bits(n, scope, stem, width):
    require(scope in n.frames, 'Gray or reset scope missing: ' + scope)
    found = {}
    prefix = scope + '/' + stem + '_'
    matcher = re.compile(re.escape(scope + '/' + stem) + r'_(\d+)_s\d+')
    for path, c in n.cells.items():
        if not path.startswith(prefix):
            continue
        m = matcher.fullmatch(path)
        if m and c['kind'].startswith('DFF'):
            bit = int(m[1])
            require(bit not in found, 'duplicate register bit: ' + scope + '/' + stem)
            found[bit] = path
    require(set(found) == set(range(width)), 'exact register bit inventory: ' + scope + '/' + stem)
    return found


def _register_scalar(n, scope, stem):
    prefix = scope + '/' + stem + '_s'
    matcher = re.compile(re.escape(scope + '/' + stem) + r'_s\d+')
    paths = [p for p, c in n.cells.items() if p.startswith(prefix) and
             c['kind'].startswith('DFF') and matcher.fullmatch(p)]
    require(len(paths) == 1, 'exact scalar register inventory: ' + scope + '/' + stem)
    return paths[0]


def _audit_media_and_usb_fence(n, bundle, domains, regs, q_drivers, combinational,
                             consumers, high, common_clear, resolved, *, raw_common_reset=False):
    """Strict source topology for held stop result and stopped-compute fence.

    Maximum flights are proposals. No async preset/clear hold/recovery/removal
    path is cut here; full reset inventory and physical pulse/recovery proof
    remain separate. Boolean equivalence is exhaustive over the small actual
    LUT/INV cone, not a permissive source-net or primitive-name guess.
    """
    low = {"1'b0"} | {n.pin(p, 'G') for p, c in n.cells.items() if c['kind'] == 'GND'}

    def pins(p):
        return dict(cell=p, kind=n.cells[p]['kind'],
                    pins={port: n.pin(p, port) for port in n.cells[p]['ports']})

    def exact_selectors(selectors, expected, port):
        union = set()
        for selector in selectors:
            actual = sorted(p + '/' + port for p, c in regs.items() if port in c['ports'] and
                            fnmatch.fnmatchcase(p + '/' + port, selector))
            wanted = sorted(p + '/' + port for p in expected if fnmatch.fnmatchcase(p + '/' + port, selector))
            require(actual and actual == wanted, 'media/fence selector expansion differs: ' + selector)
            resolved[selector] = actual
            union.update(actual)
        require(union == {p + '/' + port for p in expected}, 'media/fence selector misses endpoints')

    def cone(net, active=()):
        if net in high or net in low:
            return set()
        require(net not in active, 'media/fence combinational cycle: ' + net)
        drivers = combinational[net]
        if not drivers:
            return {net}
        require(len(drivers) == 1, 'media/fence ambiguous combinational driver: ' + net)
        p = drivers[0]
        c = n.cells[p]
        if c['kind'] == 'INV':
            return cone(n.pin(p, 'I'), (*active, net))
        require(re.fullmatch(r'LUT[1-6]', c['kind']) is not None,
                'media/fence unsupported Boolean cell: ' + p)
        return set().union(*(cone(n.pin(p, 'I' + str(i)), (*active, net))
                             for i in range(int(c['kind'][3:]))))

    def value(net, assignment):
        if net in high:
            return 1
        if net in low:
            return 0
        if net in assignment:
            return assignment[net]
        p = combinational[net][0]
        c = n.cells[p]
        if c['kind'] == 'INV':
            return 1 - value(n.pin(p, 'I'), assignment)
        count = int(c['kind'][3:])
        init = re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)", c['parameters'].get('INIT', ''))
        require(init is not None and int(init[1]) == 1 << count,
                'media/fence LUT truth table format: ' + p)
        index = sum(value(n.pin(p, 'I' + str(i)), assignment) << i for i in range(count))
        return (int(init[2], 16) >> index) & 1

    def equivalent(label, outputs, predicate):
        support = sorted(set().union(*(cone(net) for net in outputs)))
        require(len(support) <= 12, 'media/fence Boolean cone exceeds reviewed bound: ' + label)
        for pattern_bits in range(1 << len(support)):
            assignment = {net: (pattern_bits >> bit) & 1 for bit, net in enumerate(support)}
            require(predicate([value(net, assignment) for net in outputs]),
                    'media/fence Boolean function changed: ' + label)
        return dict(function=label, support=support, exhaustive_assignments=1 << len(support))

    def shift(scope, stem, width, clock, kind, async_pin, assertion, initial):
        chain = _register_bits(n, scope, stem, width)
        for bit, p in chain.items():
            require(n.cells[p]['kind'] == kind, 'media/fence release primitive kind: ' + p)
            require(n.pin(p, 'CLK') == clock and n.pin(p, 'CE') in high,
                    'media/fence release clock or conditional enable: ' + p)
            require(n.pin(p, async_pin) == assertion,
                    'media/fence release assertion differs: ' + p)
            require(n.pin(p, 'D') == (n.pin(chain[bit - 1], 'Q') if bit else initial),
                    'media/fence release shift: ' + p)
            if bit < width - 1:
                require(consumers[n.pin(p, 'Q')] == [(chain[bit + 1], 'D')],
                        'media/fence release intermediate fanout: ' + p)
        return chain

    media, usb = 'u_managed/media_stop', 'u_native_usb/input_owner'
    assertions = dict(control=common_clear, compute=common_clear)
    domain_resets = []
    if raw_common_reset:
        require('button1_n' not in n.directions[TOP], 'managed raw button assertion changed')

        def next_q(p, domain, inputs, predicate):
            cell = n.cells[p]
            require(cell['kind'] in ('DFFCE', 'DFFRE') and n.pin(p, 'CLK') == domains[domain] and
                    n.pin(p, 'CE') in high and q_drivers[n.pin(p, 'Q')] == [p],
                    'managed startup/release primitive/clock/CE/producer changed: ' + p)
            reset = n.pin(p, 'RESET' if cell['kind'] == 'DFFRE' else 'CLEAR')
            if cell['kind'] == 'DFFCE':
                require(reset in low, 'managed raw common assertion changed: ' + p)
            named = set(inputs) | {n.pin(p, 'Q')}
            require(cone(n.pin(p, 'D')) | cone(reset) <= named,
                    'managed startup/release unexpected next-Q input: ' + p)
            proof = equivalent('managed startup/release effective next-Q: ' + p,
                [n.pin(p, 'D'), reset, *inputs],
                lambda values: (values[0] and not values[1]) == predicate(values[2:]))
            return dict(register=p, primitive=cell['kind'], effective_next_q_verified=True, **proof)

        for domain, startup_stem, release_stem, consumer in (
                ('control', 'startup_control', 'reset_50_pipe', 'request_toggle'),
                ('compute', 'startup_compute', 'reset_compute_pipe', 'acknowledge_toggle')):
            startup = _register_bits(n, 'u_managed', startup_stem, 2)
            release = _register_bits(n, 'u_managed', release_stem, 3)
            proofs = [next_q(startup[0], domain, ['reset_n', 'memory_guard_started'], lambda values: values[0] and values[1])]
            require(consumers[n.pin(startup[0], 'Q')] == [(startup[1], 'D')],
                    'managed startup first-stage fanout changed: ' + startup[0])
            proofs.append(next_q(startup[1], domain, [n.pin(startup[0], 'Q')], lambda values: values[0]))
            grant = n.pin(startup[1], 'Q')
            for bit, p in release.items():
                previous = n.pin(release[bit - 1], 'Q') if bit else grant
                require(n.pin(p, 'D') == previous, 'managed reset release shift changed: ' + p)
                proofs.append(next_q(p, domain, [grant, previous], lambda values: values[0] and values[1]))
                if bit < 2:
                    require(consumers[n.pin(p, 'Q')] == [(release[bit + 1], 'D')],
                            'managed reset release intermediate fanout changed: ' + p)
            assertion = n.pin(_register_scalar(n, media, consumer), 'CLEAR')
            drivers = combinational[assertion]
            require(len(drivers) == 1 and n.cells[drivers[0]]['kind'] == 'INV' and
                    n.pin(drivers[0], 'I') == n.pin(release[2], 'Q'),
                    'media local domain reset inverse changed: ' + domain)
            assertions[domain] = assertion
            domain_resets.append(dict(domain=domain, startup=startup, release=release,
                assertion_net=assertion, inverter=drivers[0], effective_next_q_proofs=proofs))
    control_rows = []
    for group in bundle['media_control_groups']:
        source = _register_scalar(n, media, group['source'])
        chain = _register_bits(n, media, group['receiver'], group['stages'])
        require(n.pin(source, 'CLK') == domains[group['source_domain']],
                'media source clock: ' + source)
        if raw_common_reset:
            require(n.cells[source]['kind'] == 'DFFCE' and n.pin(source, 'CLEAR') == assertions[group['source_domain']],
                    'media source domain reset or primitive changed: ' + source)
        for bit, p in chain.items():
            require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CLEAR') == assertions[group['destination_domain']],
                    'media receiver reset or primitive kind: ' + p)
            require(n.pin(p, 'CLK') == domains[group['destination_domain']],
                    'media destination clock: ' + p)
            require(n.pin(p, 'CE') in high, 'media receiver conditional enable: ' + p)
            prior = source if bit == 0 else chain[bit - 1]
            require(n.pin(p, 'D') == n.pin(prior, 'Q') and q_drivers[n.pin(p, 'D')] == [prior],
                    'media receiver source identity or stage connection: ' + p)
            if bit < group['stages'] - 1:
                require(consumers[n.pin(p, 'Q')] == [(chain[bit + 1], 'D')],
                        'media first/settle stage functional fanout: ' + p)
        exact_selectors(group['selectors']['source'], [source], 'Q')
        exact_selectors(group['selectors']['first'], [chain[0]], 'D')
        control_rows.append(dict(**group, source_register=pins(source),
                                 receiver_registers=[pins(chain[i]) for i in range(group['stages'])]))
    failure = _register_scalar(n, media, 'compute_failure')
    ack = _register_scalar(n, media, 'acknowledge_toggle')
    require(n.cells[failure]['kind'] == n.cells[ack]['kind'] == 'DFFCE' and
            n.pin(failure, 'CLEAR') == assertions['compute'] and n.pin(ack, 'CLEAR') == assertions['compute'],
            'media result producer reset or primitive changed')
    # Gowin can encode the same toggle event in the D cone or in CE. Compare
    # the actual enabled state transition, not one particular mapped shape.
    result_correlation = equivalent('held failure changes exactly when ACK toggles',
        [n.pin(ack, 'D'), n.pin(ack, 'Q'), n.pin(ack, 'CE'), n.pin(failure, 'CE')],
        lambda values: ((values[0] ^ values[1]) & values[2]) == values[3])

    hold_source = _register_scalar(n, media, 'hold_50')
    require(n.pin(hold_source, 'CLK') == domains['control'] and
            n.pin(hold_source, 'CLEAR') == assertions['control'], 'media hold source identity/reset/clock')
    hold = _register_bits(n, media, 'hold_compute', 2)
    require(all(n.cells[p]['kind'] == 'DFFPE' for p in hold.values()),
            'media hold requires exactly two preset release flops')
    assertion = n.pin(hold[0], 'PRESET')
    hold_function = equivalent('common reset OR hold asserts preset',
        [assertion, assertions['compute'], n.pin(hold_source, 'Q')],
        lambda values: values[0] == (values[1] | values[2]))
    hold = shift(media, 'hold_compute', 2, domains['compute'], 'DFFPE', 'PRESET', assertion,
                 n.pin(hold[0], 'D'))
    require(n.pin(hold[0], 'D') in low, 'media hold release does not shift zero')
    hold_selectors = bundle['media_hold_assertion']['selectors']
    exact_selectors(hold_selectors['source'], [hold_source], 'Q')
    exact_selectors(hold_selectors['assertion'], list(hold.values()), 'PRESET')

    release = _register_bits(n, usb, 'queue_release', 6)
    input_reset = n.pin(release[0], 'CLEAR')
    release = shift(usb, 'queue_release', 6, domains['compute'], 'DFFCE', 'CLEAR', input_reset,
                    n.pin(release[0], 'D'))
    require(n.pin(release[0], 'D') in high, 'USB queue release does not shift one')
    connected = _register_scalar(n, usb, 'connected')
    panic = _register_scalar(n, usb, 'panic_flush')
    events = _register_bits(n, usb, 'event_release', 3)
    require(all(n.pin(p, 'CLK') == domains['usb'] for p in [connected, panic, *events.values()]),
            'USB input-reset source clocks changed')
    input_reset_function = equivalent('USB input reset event/connection/panic identity',
        [input_reset, n.pin(events[2], 'Q'), n.pin(connected, 'Q'), n.pin(panic, 'Q')],
        lambda values: values[0] == ((1 - values[1]) | (1 - values[2]) | values[3]))
    drain = _register_bits(n, usb, 'stopped_clock_queue_fence.drain_release', 6)
    fifo_reset = n.pin(drain[0], 'CLEAR')
    fifo_reset_function = equivalent('USB FIFO reset held until six real compute edges',
        [fifo_reset, input_reset, n.pin(release[5], 'Q')],
        lambda values: values[0] == (values[1] | (1 - values[2])))
    drain = shift(usb, 'stopped_clock_queue_fence.drain_release', 6, domains['compute'],
                  'DFFCE', 'CLEAR', fifo_reset, n.pin(drain[0], 'D'))
    require(n.pin(drain[0], 'D') in high, 'USB drain release does not shift one')
    writer = _register_bits(n, usb, 'queue_write_release', 2)
    for bit, p in writer.items():
        require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CLK') == domains['usb'] and
                n.pin(p, 'CE') in high and n.pin(p, 'CLEAR') == input_reset,
                'USB write-release clock/reset/enable: ' + p)
    require(n.pin(writer[1], 'D') == n.pin(writer[0], 'Q') and
            consumers[n.pin(writer[0], 'Q')] == [(writer[1], 'D')],
            'USB write-release first stage or fanout')
    ready_function = equivalent('USB queue ready requires actual drain and FIFO reset release',
        [n.pin(writer[0], 'D'), n.pin(drain[5], 'Q'), fifo_reset],
        lambda values: values[0] == (values[1] & (1 - values[2])))
    return_selectors = bundle['usb_queue_fence']['return_selectors']
    exact_selectors(return_selectors['source'], [drain[5], release[5]], 'Q')
    exact_selectors(return_selectors['first'], [writer[0]], 'D')
    assertion_selectors = bundle['usb_queue_fence']['assertion_selectors']
    exact_selectors(assertion_selectors['source'], [release[5]], 'Q')
    exact_selectors(assertion_selectors['assertion'], list(drain.values()), 'CLEAR')
    return dict(media_control_groups=control_rows, media_domain_resets=domain_resets,
        media_result_correlation=result_correlation,
        media_hold=dict(source=pins(hold_source), release=[pins(hold[i]) for i in range(2)],
                        assertion_function=hold_function, async_recovery_removal_verified=False),
        usb_queue_fence=dict(queue_release=[pins(release[i]) for i in range(6)],
            drain_release=[pins(drain[i]) for i in range(6)], write_release=[pins(writer[i]) for i in range(2)],
            input_reset_function=input_reset_function, fifo_reset_function=fifo_reset_function,
            queue_ready_function=ready_function, intermediate_first_stage_isolation_verified=True,
            input_reset_all_source_flight_or_pulse_verified=False, recovery_removal_verified=False),
        protected_async_pins=sorted([p + '/PRESET' for p in hold.values()] +
                                    [p + '/CLEAR' for p in drain.values()]))


def audit_runtime_cdc(root, netlist_text, clock_audit, *, raw_common_reset=False):
    """Map every reviewed bit and reset alias; physical gates remain false."""
    bundle = runtime_cdc_bundle(root, raw_common_reset=raw_common_reset)
    n = SynthesisNetlist(netlist_text, TOP)
    clocks = clock_audit.get('base_clock_audit', clock_audit.get('base_13_clock_audit'))['clocks']
    domains = {k: clocks[v]['net'] for k, v in
               dict(control='clk_50m', compute='audio_76m8', memory='ddr_ui100', reference48='dac_ref12m288').items()}
    domains.update(reference44='clk_16m9344', selected=clock_audit['dcs']['output_net'],
                   usb=clocks['usb_48m']['net'])
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

    rows, resolved = [], {}
    for group in bundle['gray_groups']:
        width, scope = group['width'], group['scope']
        alias = GRAY_MSB_ALIASES.get(group['id'])
        source = _register_bits(n, scope, group['source'], width - bool(alias))
        if alias:
            paths = [p for p, c in regs.items() if re.fullmatch(
                re.escape(scope + '/' + alias + '_' + str(width - 1)) + r'_s\d+', p)
                if p.startswith(scope + '/' + alias + '_')]
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
    releases = BLE_RELEASE_SEPARATE_COMMON if raw_common_reset else BLE_RELEASE_ALIASES
    for direction, scope, stem, domain, consumer in releases:
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
    media_fence = _audit_media_and_usb_fence(n, bundle, domains, regs, q_drivers,
        combinational, consumers, high, common_clear, resolved, raw_common_reset=raw_common_reset)
    return dict(schema=2, policy=POLICY, scope='reviewed_21_direct_gray_ble_release_media_stop_and_usb_queue_fence',
        **media_fence,
        gray_groups=rows, gray_group_count=len(rows), gray_first_stage_bits=sum(len(x['paths']) for x in rows),
        ble_reset_aliases=aliases, raw_common_reset=raw_common_reset, resolved_pin_selectors=resolved,
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
    expected = runtime_cdc_bundle(root, raw_common_reset=result.get('raw_common_reset', False))['sdc'].splitlines()
    peripheral = NATIVE_PERIPHERAL_SDC if result.get('raw_common_reset', False) else PERIPHERAL_SDC
    require(all(lines.count(line) == 1 for line in expected), 'reviewed runtime CDC constraints missing or duplicated')
    first_pins = {path for selector, paths in result['resolved_pin_selectors'].items()
                  if selector.endswith('/D') for path in paths} | set(result['protected_async_pins'])
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
            require(line in peripheral, 'unreviewed peripheral SDC command: ' + line)
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
        # Recovery/removal endpoints have no false-path allowance. Every
        # explicit delay to them must be a reviewed exact assertion bound;
        # an arbitrary source filter cannot bypass this target protection.
        if matches(line, 'to', set(result['protected_async_pins'])):
            require(command == 'set_max_delay' and line in expected,
                    'unreviewed timing exception targets protected asynchronous control: ' + line)
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
    reset_policy = prepared_ble_reset_policy(stage)
    result = audit_runtime_cdc(root, text, clocks, raw_common_reset=reset_policy['raw_common_reset'])
    result['ble_reset_source_policy'] = reset_policy
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
    result.update(identity='runtime-cdc-gray-media-fence-source-v2-' + identity[:16], source_set_sha256=identity,
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
