#!/usr/bin/env python3
"""Read-only revision2 raw-store/seal/authority CDC endpoint inventory.

Checks declared registered producers, receiving pairs and their complete first-Q
closures. Payloads and reset safety cones are inventoried, not accepted as a
complete handshake, RAM ownership, pulse-width or physical timing proof. No SDC
is emitted or installed and no EDA or board operation is performed.
"""
from pathlib import Path
import argparse
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_ble_ddr_cdc_scope import SCOPE, SOURCE_SHA256, validate_profile
from tools.workstation_ble_ddr_prefix_cdc_scope import (SCOPE as PREFIX_SCOPE,
    SOURCE_SHA256 as PREFIX_SOURCE_SHA256, validate_profile as validate_prefix_profile)
from tools.workstation_ble_ddr_prefix_cdc_endpoints import (RAW_ENDPOINT_SHA256 as PREFIX_ENDPOINT_SHA256,
    RAW_PAYLOADS as PREFIX_PAYLOADS, validate_synthesis_binding as validate_prefix_VG)
from tools.workstation_ble_ddr_chorus_cdc_scope import (SCOPE as CHORUS_SCOPE,
    SOURCE_SHA256 as CHORUS_SOURCE_SHA256, validate_profile as validate_chorus_profile,
    AUDIT_SOURCES as CHORUS_AUDIT_SOURCES)
from tools.workstation_display_load_222fb761_scope import (SCOPE as PITCH_FIFO_SCOPE,
    SOURCE_SHA256 as PITCH_FIFO_SOURCE_SHA256, validate_profile as validate_pitch_fifo_profile,
    AUDIT_SOURCES as PITCH_FIFO_AUDIT_SOURCES)
from tools.workstation_ble_ddr_chorus_cdc_endpoints import (RAW_ENDPOINT_SHA256 as CHORUS_ENDPOINT_SHA256,
    RAW_PAYLOADS as CHORUS_PAYLOADS, validate_synthesis_binding as validate_chorus_VG)
from tools.workstation_display_load_222fb761_endpoints import (RAW_ENDPOINT_SHA256 as PITCH_FIFO_ENDPOINT_SHA256,
    RAW_PAYLOADS as PITCH_FIFO_PAYLOADS, validate_synthesis_binding as validate_pitch_fifo_VG)
from tools.workstation_bluetooth_ddr import RAW_STORE_PATH, RAW_STORE_SHA256
from tools.workstation_display_load_222fb761_owner_reset import OwnerResetNetlist, _reg
from tools.workstation_runtime_pcm_cdc import Graph, TOP
from tools.workstation_display_load_222fb761_phase1 import complete_closure, digest
from tools.workstation_runtime_clock_audit import VG_RELATIVE, verify_synthesis_identity, file_sha

POLICY = 'ble-ddr-revision2-declared-cdc-inventory-v1'
B, F, A, S = ('recording_ble_store', 'recording_ble_store/capture_fifo',
               'recording_authority/guard', 'u_recording/seal_cdc')
# Actual revision2 mapped live bitmaps. Missing logical bits are reported
# separately; absence never silently removes a declared crossing.
PAYLOADS = {
    'command': (89, 'clk_50m', [('command_kind', 2, range(2)),
        ('command_generation', 32, range(32)), ('command_offset', 32, range(32)),
        ('command_length', 14, range(13)), ('command_event_target', 9, range(9))]),
    'completion': (70, 'memory_clk', [('completion_generation', 32, range(32)),
        ('completion_committed', 32, range(32)), ('completion_kind', 2, range(2)),
        ('completion_code', 4, range(4))]),
    'status': (70, 'memory_clk', [('status_payload', 70, range(70))]),
    'return': (299, 'memory_clk', [('return_data', 256, range(256)),
        ('return_generation', 32, range(32)), ('return_word', 11, range(3, 11))]),
}
# Complete source/closure identities are frozen only after explicit actual-VG
# review. These are separate from the legacy phase1 identities.
ENDPOINT_SHA256 = {'authority:heartbeat': 'fbda00056e5d3d1c2655c5d12da41f585de4551ccfd010efb8b91ac80392f24b',
 'authority:open': '3b65f0ef6dd5c37849ba0df5bb60aa0df05949da2b5f25018612639fa1b98449',
 'payload:command': 'af74cc779c5c118ec304b8670048c633663887a970cf945352a85781d1986e81',
 'payload:completion': '5cd702fbf28e7951c7f263669bfae864ef9a36ab7b7034f730775b6e296d1fbf',
 'payload:return': '8fe498ebb1912040fe845e41d8180d07825a2cf6695d819c5f8244b6e148b027',
 'payload:status': '86f61f1616777f8cf6af404c17ac5e4938ee71232e841c6f86d2258d9a9e0835',
 'raw:cancel': '90f490e4fd471473cc4cecc5f6f49f2e7b27baab7981827d51b798a13768eabd',
 'raw:command_ack': '47a2d069818fe9b30679f7f99170dbfda563c6d450551f7d82a65ac1ab3d2227',
 'raw:command_request': '79a42e222af354d2717365d34fcc8e31e9d3bb2b4afead59595919eb1b0f5f75',
 'raw:memory_up': '7fb07b57e74a26ff932d1de8772b91e94bd91ff70e74b3cf7d218505a72768fe',
 'raw:read_gray': 'a7678023e73555e7c552837abad9eb571da2a6a5fabdc46b5a0bb86d535ef2ee',
 'raw:return_ack': 'c4bdc5e338264311518704d9ef4a1dba409bccd041ea2090037a0c460ab02a56',
 'raw:return_request': '950b93737d927e6de425fbf8a78a0339ccff8305d2dcc83f3c44bd965dfa1666',
 'raw:status_ack': '3240c6bff5049ecf9c8ce4f357b5b4d452640c04b0289c0195ab6eefd7fc3c57',
 'raw:status_request': '2a0466ff96fdaef25fcc834edbd9d4c2568f46599d865f81dc1410fc96484df3',
 'raw:write_gray': '3749aad8442b4806343b41a9af4d09aa38449d064333b10fbb373d7b99cd8e30',
 'release:authority_control:0': 'b48db8aabb9470e22af672897d18ce41af6f984c46bb6040fc73753923368683',
 'release:authority_control:1': '1bcd62a1d701ce714d9decf9b75241dcb274ef86ed76e9e67eabf4ff327dc9e8',
 'release:authority_control:2': '15ad132703d8dfa61ff06a31e450468011475c7cd630aa190ecfa373d162cc5d',
 'release:authority_memory:0': '6e6c301ac48257e04b8428754995140ff8fa8f734c0825ac4e45844ef3d9c53a',
 'release:authority_memory:1': '91420c92acfc19de174202e61e9caea21934855c07d516f0c15d2e2937196ecd',
 'release:authority_memory:2': '731fffe6a008a25c90552faf2079687c14e3b64784f370ae63f1de17efb50f36',
 'release:authority_root:0': '77b8182b6e1d07a88c14e84f74691c2c147ceb593593e3000f84f98f38b68a04',
 'release:authority_root:1': '905001a667bff266bbb63450303b1335529b4e03486df01ffa8c6a6d82e809f6',
 'release:raw_control:0': '779786366b64026d4ce0460c62c64e171b286653f07d5c2eb5a494a26e49f3f6',
 'release:raw_control:1': '255fa09be1932a4d27b4ee0e8c687b10cd21c0990841658390ef24a470c313ff',
 'release:raw_memory:0': '68247721cf5fd199c51bcad7a79f0d1a846bc5ae64549cc3ca72ecab8133b2f8',
 'release:raw_memory:1': '7fb07b57e74a26ff932d1de8772b91e94bd91ff70e74b3cf7d218505a72768fe',
 'release:seal_destination:0': 'd3dc0501deda9e2f7f1d08d24d96fca184a5bf86bf442ea9eca3f91b7913ced5',
 'release:seal_destination:1': 'd9bd4c3836da365f6a7c7360379e80040f411dc7f3691ee552ccc5a7232627d9',
 'release:seal_source:0': '0749cb09d14c8a9d33ba40db48634ae701209e0c540f350fcb3819b2f995b725',
 'release:seal_source:1': '88ad7fb6b4f02f6e50b06aa8e71f31f39595296522902465820d6c78bf310018',
 'safety:authority_availability': '187a83545b2365b47d6ef516e329ab67209b1599e8f3ebf728a0adb0a56b4476',
 'safety:authority_boot': 'f1f60768ad17a1b4c4ec3bf5f44116cc99bf4e2321509c9d2531669719b0d65b',
 'safety:authority_grant': '49131502d456f3aab2db6f1d51f230aa6e0d537cc7c35623cad29d81925007d9',
 'safety:authority_survival': 'd813a75940613648c74c33ca44eea3e8ded6cb089c5922c607bdc750cfbd587d',
 'safety:qualified_channel': '51eac48d89a6c940177df71115106b413469a6c78f5da892b2b6ffaed6615a17',
 'seal:hold': '7ed8c74f5b5c8d972a7ce462c3c99777e30e1998fcc5bc8fde61aa3ed35f7df9',
 'seal:ready': 'ba0cec0621c383ccdb2cf8c844e1ad6ec0bc1134e27233142f9938790e080ddb',
 'seal:request': 'cd12c9bb9a910507cd690e34ff2919800a5373049b41fffe57d28225c4290d48',
 'seal:result': 'c12c74ce21d1bf77e29bee32c2cd4593c878c9818af4bda67466692657149e93',
 'seal:result_payload': '05036cc5c728e3828323d09db56da36061359b89f43864d6cedee6553543ae7a'}


def require(ok, message):
    if not ok:
        raise ValueError('revision2 BLE DDR CDC inventory: ' + message)


def ff(n, g, path, clock, *, unconditional=False):
    c = n.cells[path]
    require(c['kind'] == 'DFFCE' and n.pin(path, 'CLK') == clock
            and 'CLEAR' in c['ports'] and c['parameters'].get('INIT', "1'b0") == "1'b0",
            'declared FF kind/clock/reset/init changed: ' + path)
    require(g.drivers[n.pin(path, 'Q')] == [(path, 'Q')], 'ambiguous declared Q: ' + path)
    if unconditional:
        require(n.pin(path, 'CE') in g.high, 'conditional receiving CE: ' + path)
    return dict(path=path, clock=clock, clear=n.pin(path, 'CLEAR'),
                d=n.pin(path, 'D'), q=n.pin(path, 'Q'), ce=n.pin(path, 'CE'))


def audit_netlist(n, *, g=None, scope=SCOPE):
    require(scope in (SCOPE, PREFIX_SCOPE, CHORUS_SCOPE, PITCH_FIFO_SCOPE), 'unknown explicit scope')
    selected_scope = scope
    endpoint_sha256 = (PITCH_FIFO_ENDPOINT_SHA256 if scope == PITCH_FIFO_SCOPE else
                       CHORUS_ENDPOINT_SHA256 if scope == CHORUS_SCOPE else
                       PREFIX_ENDPOINT_SHA256 if scope == PREFIX_SCOPE else ENDPOINT_SHA256)
    payload_specs = (PITCH_FIFO_PAYLOADS if scope == PITCH_FIFO_SCOPE else
                       CHORUS_PAYLOADS if scope == CHORUS_SCOPE else
                     PREFIX_PAYLOADS if scope == PREFIX_SCOPE else PAYLOADS)
    require(bool(endpoint_sha256) and isinstance(payload_specs, dict), 'explicit reviewed endpoint/bitmap identities required')
    g = g or Graph(n)
    closures = {}

    def save(label, sources):
        closure = complete_closure(n, g, sources)
        shape = {key: closure[key] for key in ('ff_endpoints', 'primitive_endpoints', 'top_output_endpoints')}
        require(digest(shape) == endpoint_sha256.get(label), 'complete source endpoint identity changed: ' + label)
        closures[label] = dict(source_registers=sources, endpoint_sha256=digest(shape), **closure)

    def pair(label, scope, first, second, source, source_clock, destination_clock):
        a, b = g.register(scope, first), g.register(scope, second)
        producer = ff(n, g, source, source_clock)
        x, y = ff(n, g, a, destination_clock, unconditional=True), ff(n, g, b, destination_clock, unconditional=True)
        require(x['d'] == producer['q'] and y['d'] == x['q'] and x['clear'] == y['clear'],
                'declared producer/receiving shift/reset changed: ' + label)
        closure = complete_closure(n, g, [a])
        require(closure == dict(ff_endpoints={b + '/D': destination_clock}, primitive_endpoints={},
                combinational_cells=0, top_output_endpoints={}), 'first-Q complete fanout changed: ' + label)
        save(label, [source])
        return dict(id=label, source=producer, first=x, second=y, first_q_complete_fanout=closure)

    root_memory = [_reg(n, g, 'recording_memory_release_' + str(i)) for i in range(2)]
    ordinary = []
    for label, first, second, producer, sc, dc in (
        ('memory_up', 'memory_up_meta', 'memory_up_sync', root_memory[1], 'memory_clk', 'clk_50m'),
        ('command_request', 'command_req_meta', 'command_req_sync', g.register(B, 'command_req'), 'clk_50m', 'memory_clk'),
        ('command_ack', 'command_ack_meta', 'command_ack_sync', g.register(B, 'command_ack'), 'memory_clk', 'clk_50m'),
        ('cancel', 'cancel_meta', 'cancel_sync', g.register(B, 'cancel_toggle'), 'clk_50m', 'memory_clk'),
        ('status_request', 'status_req_meta', 'status_req_sync', g.register(B, 'status_req'), 'memory_clk', 'clk_50m'),
        ('status_ack', 'status_ack_meta', 'status_ack_sync', g.register(B, 'status_ack'), 'clk_50m', 'memory_clk'),
        ('return_request', 'return_req_meta', 'return_req_sync', g.register(B, 'return_req'), 'memory_clk', 'clk_50m'),
        ('return_ack', 'return_ack_meta', 'return_ack_sync', g.register(B, 'return_ack'), 'clk_50m', 'memory_clk'),
    ):
        ordinary.append(pair('raw:' + label, B, first, second, producer, sc, dc))
    for label, first, second, producer, sc, dc in (
        ('request', 'request_meta', 'request_sync', 'request_toggle', 'clk_50m', 'memory_clk'),
        ('hold', 'hold_meta', 'hold_sync', 'source_hold', 'clk_50m', 'memory_clk'),
        ('result', 'result_meta', 'result_sync', 'result_toggle', 'memory_clk', 'clk_50m'),
        ('ready', 'ready_meta', 'ready_sync', 'destination_ready', 'memory_clk', 'clk_50m'),
    ):
        ordinary.append(pair('seal:' + label, S, first, second, g.register(S, producer), sc, dc))
    ordinary.append(pair('authority:open', A, 'open_meta', 'open_ack',
        g.register(A, 'grant_release', 2), 'memory_clk', 'clk_50m'))
    top_first, top_second = _reg(n, g, 'recording_channel_meta'), _reg(n, g, 'recording_channel_ready50')
    channel_first = ff(n, g, top_first, 'clk_50m', unconditional=True)
    channel_second = ff(n, g, top_second, 'clk_50m', unconditional=True)
    channel_producers = [g.register(A, 'grant_release', 2), g.register('recording_authority', 'epoch_survived')]
    require(channel_second['d'] == channel_first['q'] and channel_second['clear'] == channel_first['clear'],
            'qualified channel receiving shift/reset changed')
    require(complete_closure(n, g, [top_first]) == dict(ff_endpoints={top_second + '/D': 'clk_50m'},
            primitive_endpoints={}, combinational_cells=0, top_output_endpoints={}),
            'qualified channel first-Q complete fanout changed')
    channel_proof = g.equivalent('declared qualified recording channel',
        [channel_first['d'], *(n.pin(p, 'Q') for p in channel_producers)],
        lambda v:v[0] == int(v[1] and v[2]))
    save('safety:qualified_channel', channel_producers)

    gray = []
    for label, scope, source, first, second, width, sc, dc, msb_alias in (
        ('raw:read_gray', F, 'read_gray', 'read_gray_meta', 'read_gray_sync', 9, 'memory_clk', 'clk_50m', 'read_binary'),
        ('raw:write_gray', F, 'write_gray', 'write_gray_meta', 'write_gray_sync', 9, 'clk_50m', 'memory_clk', 'write_binary'),
        ('authority:heartbeat', A, 'memory_gray', 'gray_meta', 'gray_sync', 32, 'memory_clk', 'clk_50m', None),
    ):
        sources = g.group(scope, source, width if msb_alias is None else width - 1)
        if msb_alias:
            sources.append(g.register(scope, msb_alias, width - 1))
        entries = []
        for i, src in enumerate(sources):
            x, y = g.register(scope, first, i), g.register(scope, second, i)
            producer = ff(n, g, src, sc)
            a, b = ff(n, g, x, dc, unconditional=True), ff(n, g, y, dc, unconditional=True)
            require(a['d'] == producer['q'] and b['d'] == a['q'] and a['clear'] == b['clear'],
                    'declared Gray producer/shift/reset changed: ' + label + ':' + str(i))
            closure = complete_closure(n, g, [x])
            require(closure == dict(ff_endpoints={y + '/D': dc}, primitive_endpoints={},
                combinational_cells=0, top_output_endpoints={}), 'Gray first-Q complete fanout changed: ' + label)
            entries.append(dict(bit=i, source=producer, first=a, second=b))
        save(label, sources)
        gray.append(dict(id=label, width=width, bits=entries, registered_sources=sources,
            MSB_alias=(msb_alias + '[' + str(width-1) + ']' if msb_alias else None),
            alias_basis='pinned binary/Gray source equations; binary and Gray MSB are equal',
            mapped_encoder_equivalence_or_physical_flight_verified=False))

    payloads = []
    for label, (logical_width, clock, fields) in payload_specs.items():
        sources, inventory = [], []
        for stem, width, bits in fields:
            bits = list(bits)
            registers = [g.register(B, stem, bit) for bit in bits]
            matched = {p for p in g.regs if re.fullmatch(re.escape(B + '/' + stem) + r'_\d+_s\d+', p)}
            require(matched == set(registers), 'payload mapped live bitmap changed: ' + stem)
            sources.extend(registers)
            inventory.append(dict(field=stem, logical_width=width, live_bits=bits,
                absent_bits=sorted(set(range(width)) - set(bits)),
                registers=[ff(n, g, p, clock) for p in registers]))
        save('payload:' + label, sources)
        payloads.append(dict(id=label, logical_width=logical_width, mapped_source_FF_count=len(sources), fields=inventory,
            held_stability_and_capture_protocol_verified=False, physical_bit_flight_verified=False))
    save('seal:result_payload', [g.register(S, 'result_failed')])

    # Exact observed root-only aliases. The two RTL state machines have the
    # same zero reset, clock, CE and constant-one shift, so their logical state
    # can share these physical flops. Every combined fanout stays inventoried.
    raw_control = [g.register('u_usb_pll/u_pll_init', 'enable_r', i) for i in range(2)]
    chains = [('raw_control', raw_control, 'clk_50m'), ('raw_memory', root_memory, 'memory_clk'),
        ('authority_root', g.group('recording_authority', 'root_release', 2), 'memory_clk'),
        ('authority_control', g.group(A, 'control_reset_pre', 2) + [g.register(A, 'control_reset_n')], 'clk_50m'),
        ('authority_memory', g.group(A, 'memory_reset_pre', 2) + [g.register(A, 'memory_reset_n')], 'memory_clk'),
        ('seal_source', [g.register(S, 'source_release_meta'), g.register(S, 'source_release_sync')], 'clk_50m'),
        ('seal_destination', g.group('u_recording/pcm_cdc/drops', 'destination_release', 3)[:2], 'memory_clk')]
    resets = []
    reset_assertion_proofs = []
    for label, paths, clock in chains:
        regs = [ff(n, g, p, clock, unconditional=True) for p in paths]
        require(len({x['clear'] for x in regs}) == 1 and regs[0]['d'] in g.high
                and all(regs[i]['d'] == regs[i-1]['q'] for i in range(1, len(regs))),
                'declared reset release shift changed: ' + label)
        assertion_source = n.pin(root_memory[1], 'Q') if label.startswith('seal_') else 'reset_n'
        reset_assertion_proofs.append(g.equivalent('declared root-only release assertion: ' + label,
            [regs[0]['clear'], assertion_source], lambda v:v[0] == 1-v[1]))
        for i, p in enumerate(paths):
            save('release:' + label + ':' + str(i), [p])
        resets.append(dict(id=label, registers=regs, physical_assertion_pulse_and_recovery_verified=False))

    safety = {}
    for label, paths in (
        ('authority_boot', [g.register('recording_authority', 'boot_seen')]),
        ('authority_survival', [g.register('recording_authority', 'epoch_survived')]),
        ('authority_availability', g.group(A, 'availability_release', 3)),
        ('authority_grant', g.group(A, 'grant_release', 3)),
    ):
        save('safety:' + label, paths)
        safety[label] = dict(registers=[ff(n, g, p, n.pin(p, 'CLK')) for p in paths],
            asynchronous_safety_assertion_cones_require_separate_review=True)
    return dict(schema=1, policy=POLICY, scope=selected_scope, ordinary_pairs=ordinary,
        ordinary_pair_count=13, raw_store_ordinary_pair_count=8, seal_ordinary_pair_count=4,
        gray_groups=gray, gray_bits=50, raw_store_gray_bits=18, authority_heartbeat_bits=32,
        raw_payload_groups=payloads, raw_payload_logical_bits=528, raw_payload_mapped_source_FFs=524,
        absent_raw_payload_bits=dict(command_length_13='pinned BLE adapter assigns {1b0,data_length}',
            return_word_0_1_2='pinned raw source initializes zero and publishes BL8 word positions in multiples of 8'),
        seal_result_payload=dict(logical_bits=5, mapped_source_FFs=1, live_field='result_failed',
            absent_field='result_code[3:0]', eliminated_code_constant_or_alias_accepted=False,
            complete_payload_handshake_accepted=False), reset_chains=resets,
        reset_assertion_boolean_proofs=reset_assertion_proofs, safety_state=safety,
        safety_qualified_channel_pair=dict(first=channel_first, second=channel_second,
            declared_producer_registers=channel_producers, boolean_proof=channel_proof,
            classified_as_safety_assertion=True, ordinary_registered_data_pair=False),
        complete_source_fanout=closures, source_endpoint_inventory_verified=True,
        reset_alias_semantics_physically_verified=False, raw_RAM_ownership_or_data_arcs_accepted=False,
        held_payload_capture_protocol_accepted=False, recording_cdc_complete=False,
        full_reset_accepted=False, constraints_complete=False, physical_cdc_accepted=False,
        routed_timing_verified=False, hardware_tested=False, deployment_allowed=False, release_ready=False)


def run_audit(root, stage, evidence, *, scope=SCOPE):
    root, stage = Path(root), Path(stage)
    require(scope in (SCOPE, PREFIX_SCOPE, CHORUS_SCOPE, PITCH_FIFO_SCOPE), 'unknown explicit scope')
    before = verify_synthesis_identity(stage, evidence)
    if scope == PITCH_FIFO_SCOPE:
        validate_pitch_fifo_VG(stage)
    elif scope == CHORUS_SCOPE:
        validate_chorus_VG(stage)
    elif scope == PREFIX_SCOPE:
        validate_prefix_VG(stage)
    profile = json.loads((stage.parents[1] / 'workstation_profile.json').read_text())
    source_validator = (validate_pitch_fifo_profile if scope == PITCH_FIFO_SCOPE else
                       validate_chorus_profile if scope == CHORUS_SCOPE else
                        validate_prefix_profile if scope == PREFIX_SCOPE else validate_profile)
    source_gate = source_validator(root, profile, stage=stage)
    require(file_sha(root / RAW_STORE_PATH) == RAW_STORE_SHA256
            and file_sha(stage / RAW_STORE_PATH) == RAW_STORE_SHA256, 'raw store source identity changed')
    helper_names = ('tools/workstation_display_load_222fb761_raw.py', 'tools/workstation_ble_ddr_cdc_scope.py',
        'tools/workstation_display_load_222fb761_phase1.py', 'tools/workstation_display_load_222fb761_owner_reset.py',
        'tools/workstation_runtime_pcm_cdc.py', 'tools/workstation_synthesis_netlist.py',
        'tools/workstation_runtime_clock_audit.py', 'tools/workstation_bluetooth_ddr.py',
        'tools/workstation_ble_recording_policy.py', 'tools/workstation_recording_policy.py')
    if scope == PREFIX_SCOPE:
        helper_names += ('tools/workstation_ble_ddr_prefix_cdc_scope.py',
                         'tools/workstation_ble_ddr_prefix_cdc_endpoints.py', 'tools/workstation_runtime_counter.py',
                         'sim/test_workstation_ble_ddr_prefix_cdc_scope.py')
    if scope == PITCH_FIFO_SCOPE:
        helper_names += PITCH_FIFO_AUDIT_SOURCES
    if scope == CHORUS_SCOPE:
        helper_names += CHORUS_AUDIT_SOURCES
    helpers = {p: file_sha(root / p) for p in helper_names}
    result = audit_netlist(OwnerResetNetlist((stage / VG_RELATIVE).read_text(), TOP), scope=scope)
    require(source_gate == source_validator(root, profile, stage=stage), 'source contract changed during inventory')
    require(before == verify_synthesis_identity(stage, evidence)
            and helpers == {p: file_sha(root / p) for p in helper_names}, 'sealed audit inputs changed')
    result.update(synthesis=before, source_gate=source_gate, audit_source_sha256=helpers,
        source_sha256=dict(PITCH_FIFO_SOURCE_SHA256 if scope == PITCH_FIFO_SCOPE else
                       CHORUS_SOURCE_SHA256 if scope == CHORUS_SCOPE else
                           PREFIX_SOURCE_SHA256 if scope == PREFIX_SCOPE else SOURCE_SHA256, **{RAW_STORE_PATH: RAW_STORE_SHA256}),
        source_seal_before_and_after=True, eda_invoked=False, hardware_operated=False,
        constraint_proposal_emitted=False, constraints_installed=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--synthesis-evidence', type=Path, required=True)
    parser.add_argument('--scope', choices=(SCOPE, PREFIX_SCOPE, CHORUS_SCOPE, PITCH_FIFO_SCOPE), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run_audit(ROOT, args.project, args.synthesis_evidence, scope=args.scope)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: result[k] for k in ('policy', 'scope', 'ordinary_pair_count', 'gray_bits',
        'raw_payload_logical_bits', 'raw_payload_mapped_source_FFs', 'recording_cdc_complete', 'deployment_allowed')}))


if __name__ == '__main__':
    main()
