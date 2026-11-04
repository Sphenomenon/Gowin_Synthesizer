#!/usr/bin/env python3
"""Read-only owner8 PCM pointer/counter and APB mailbox structure review.

The emitted SDC is a proposal, never installed by this tool. FIFO RAM data,
seal, DDR owner8, complete reset and all physical acceptance remain separate.
"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import hashlib
import inspect
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_pcm_cdc import Graph, TOP, COMB
from tools.workstation_display_load_222fb761_owner_reset import OwnerResetNetlist, NO_LOCAL_PANEL_CONFIGURATION_SHA256, _reg
from tools.workstation_runtime_clock_audit import (
    verify_synthesis_identity, VG_RELATIVE, file_sha, audit_runtime_clocks, AUDIT_SOURCES as CLOCK_SOURCES,
)
from tools.workstation_recording_policy import metadata, verify_address_map
from tools.workstation_ble_ddr_cdc_scope import (SCOPE as BLE_DDR_SCOPE, LEGACY_SCOPE,
    validate_profile as validate_ble_ddr_profile)
from tools.workstation_ble_ddr_prefix_cdc_scope import (SCOPE as BLE_DDR_PREFIX_SCOPE,
    validate_profile as validate_ble_ddr_prefix_profile, COUNTER_SOURCE as PREFIX_COUNTER_SOURCE,
    COUNTER_SHA256 as PREFIX_COUNTER_SHA256)
from tools.workstation_ble_ddr_prefix_cdc_endpoints import (PHASE1_ENDPOINT_SHA256 as PREFIX_ENDPOINT_SHA256,
    PHASE1_RESET_ALIAS_SHA256 as PREFIX_RESET_ALIAS_SHA256, validate_synthesis_binding as validate_prefix_VG)
from tools.workstation_ble_ddr_chorus_cdc_scope import (SCOPE as BLE_DDR_CHORUS_SCOPE,
    validate_profile as validate_ble_ddr_chorus_profile, AUDIT_SOURCES as CHORUS_AUDIT_SOURCES)
from tools.workstation_display_load_222fb761_scope import (SCOPE as BLE_DDR_PITCH_FIFO_SCOPE,
    validate_profile as validate_ble_ddr_pitch_fifo_profile, AUDIT_SOURCES as PITCH_FIFO_AUDIT_SOURCES)
from tools.workstation_ble_ddr_chorus_cdc_endpoints import (PHASE1_ENDPOINT_SHA256 as CHORUS_ENDPOINT_SHA256,
    PHASE1_RESET_ALIAS_SHA256 as CHORUS_RESET_ALIAS_SHA256, validate_synthesis_binding as validate_chorus_VG)
from tools.workstation_display_load_222fb761_endpoints import (PHASE1_ENDPOINT_SHA256 as PITCH_FIFO_ENDPOINT_SHA256,
    PHASE1_RESET_ALIAS_SHA256 as PITCH_FIFO_RESET_ALIAS_SHA256, validate_synthesis_binding as validate_pitch_fifo_VG)
BLE_DDR_SCOPES = (BLE_DDR_SCOPE, BLE_DDR_PREFIX_SCOPE, BLE_DDR_CHORUS_SCOPE, BLE_DDR_PITCH_FIFO_SCOPE)

POLICY = 'owner8-recording-pcm-pointer-and-apb-mailbox-source-v1'
PROFILE = 'custom138k-workstation-r00-no-local-panel-v1'
PROFILE_SOURCE = 'boards/custom_138k/workstation_profile_r00_no_local_panel_v1.json'
P = 'u_recording/pcm_cdc'
F, D, A = P + '/frames', P + '/drops', 'u_recording/commands'
# Exact source revisions reviewed for the contracts below. A source change
# requires review; no private staging or alternate reconstruction is consulted.
SOURCE_SHA256 = {
    'rtl/workstation/workstation_recording_runtime.sv': '0d9508ab6684bff36b4c83a27911f1df0cc43300afa4500204f3e27eb2e599c0',
    'rtl/audio/workstation_pcm_observation_bridge.sv': '198dbf39ff6b6cfb6fe308444274849c507f222edcb0ea651abeb8d719f62c17',
    'rtl/music/music_async_fifo.sv': 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792',
    'src/migration/gw138k_apb_cdc.sv': '99eddbe61b57756f50e97cf108099cdfaf7324b55178808ab4d403bebf9818b7',
    'src/migration/gw138k_counter_cdc.sv': '1b6ff697ccd951995b7331ac483f3c7672a959a9a767465eb57d92d80f3afa8c',
}
V2_SOURCE_SHA256 = dict(SOURCE_SHA256, **{
    'rtl/workstation/workstation_recording_runtime.sv': 'cc784aa3d63899136d11f4cc53ec4c84cdc48de8d382212cf3194f17961036c9',
    'rtl/services/workstation_recording_seal_bridge.sv': '1512a14e01725845350a76d2ea78e521f0a99bc362015f8cf87d3db8d61883f4',
})
PREFIX_SOURCE_SHA256 = {k: v for k, v in V2_SOURCE_SHA256.items()
                        if k != 'src/migration/gw138k_counter_cdc.sv'}
PREFIX_SOURCE_SHA256[PREFIX_COUNTER_SOURCE] = PREFIX_COUNTER_SHA256

# Populated only from explicitly reviewed revision2 complete endpoint identities.
V2_ENDPOINT_SHA256 = {'command_ack_toggle': '9fbba2f426dba4f6580191631d7fb8f3bb785503eceeaf6b41ee2cb0e61f3d02',
 'command_request_payload': '06d6997e79e7e80f67d3fe8a64a1c3ee670bde1c1200692cd4e701e96cd7c9e5',
 'command_request_toggle': 'b126366ca92e26dce71ff20046b072b3729ba02a999264728acae2e44b19b049',
 'command_response_payload': '4eeb7266f15b47b171866df422bccb242810bc7ede933515a4628cf45a6e7293',
 'pcm_drop_gray': 'a9aaf60603102f995b19864f50b05f1a6a22c5c9aff760f8dbc608ff93410888',
 'pcm_read_gray': '8b96c660b57e8c13c91270430ccc159eba53043d90dd637e5437b290659d9767',
 'pcm_write_gray': '29c1f4f16688b4196edf8ec92d014c9f9dd2a7fbe7f14d1a1f3704932c8a6c01',
 'release:u_recording/commands/a_release': '405c113dd4022e83c28cd85e72d8fd8fc5d02179b27c9213f14eb198267bc20e',
 'release:u_recording/commands/p_release': 'b74142414f60a6f22abd3cbf1708cc041db48be317d13105758faa209888fd24',
 'release:u_recording/pcm_cdc/destination_release': 'd219fd4e80243a2fcf282bb634b584ec542421550c3b62e3d2d9d86e2534bbfe',
 'release:u_recording/pcm_cdc/drops/destination_release': 'f4874fbfedf57a4fd378cecd676944f6dee6d3ad9ef5e559944f51b4a08bf687',
 'release:u_recording/pcm_cdc/drops/source_release': '864e3b94ec264f1084bfec1bee46f5f33adb3e76fbc8c99c636e3ad2f5ec31f5',
 'release:u_recording/pcm_cdc/source_release': '0bc8db4caf1307a685298f1a615899515532d7dd3c645f942fa97e3a1ac39bb4'}
# Complete endpoint identities, including every same-domain FF and primitive
# consumer. Canonical JSON is documented below. Never replace these with a
# prefix/clock filter or rediscover an accepted producer from first-stage D.
# These source-shape declarations were reviewed on the sealed e855 candidate;
# another topology needs an explicit revision even if its CDC bit counts match.
ENDPOINT_SHA256 = {
    'command_ack_toggle': '7bd6981bd8d718df8fd7ef0c2125d06107b053f5848ed85e38cf8eccb7e378c8',
    'command_request_payload': '06d6997e79e7e80f67d3fe8a64a1c3ee670bde1c1200692cd4e701e96cd7c9e5',
    'command_request_toggle': 'b126366ca92e26dce71ff20046b072b3729ba02a999264728acae2e44b19b049',
    'command_response_payload': '4eeb7266f15b47b171866df422bccb242810bc7ede933515a4628cf45a6e7293',
    'pcm_drop_gray': 'a9aaf60603102f995b19864f50b05f1a6a22c5c9aff760f8dbc608ff93410888',
    'pcm_read_gray': '2780d97f8e1810a3a52e26f84067ffee233fa683b2475a72972c9b45ce4a41bc',
    'pcm_write_gray': '29c1f4f16688b4196edf8ec92d014c9f9dd2a7fbe7f14d1a1f3704932c8a6c01',
    'release:u_recording/commands/a_release': '09ede80c044159903f23c6fc17571afd93bee9aad46a9c5980d411d1cadeff46',
    'release:u_recording/commands/p_release': 'ddb2c82f2ce97bc58dc246f599920ac7e2299bb14884391be977a158960164aa',
    'release:u_recording/pcm_cdc/destination_release': 'fbf96775dc62fa2ca9f4a4d49559db6b72be49489c92677a9623aeef93532f72',
    'release:u_recording/pcm_cdc/drops/destination_release': 'f4874fbfedf57a4fd378cecd676944f6dee6d3ad9ef5e559944f51b4a08bf687',
    'release:u_recording/pcm_cdc/drops/source_release': '864e3b94ec264f1084bfec1bee46f5f33adb3e76fbc8c99c636e3ad2f5ec31f5',
    'release:u_recording/pcm_cdc/source_release': '0bc8db4caf1307a685298f1a615899515532d7dd3c645f942fa97e3a1ac39bb4',
}
RELEASES = ((P, 'source_release', 'selected'), (P, 'destination_release', 'memory'),
            (D, 'source_release', 'selected'), (D, 'destination_release', 'memory'),
            (A, 'p_release', 'apb'), (A, 'a_release', 'memory'))


def require(ok, message):
    if not ok:
        raise ValueError('owner8 phase1 CDC audit: ' + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def compact(text):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S))


def validate_sources(root, stage, profile, *, scope=LEGACY_SCOPE):
    require(scope in (LEGACY_SCOPE, *BLE_DDR_SCOPES), 'unknown explicit scope')
    v2 = scope in BLE_DDR_SCOPES
    if v2:
        (validate_ble_ddr_pitch_fifo_profile if scope == BLE_DDR_PITCH_FIFO_SCOPE else
         validate_ble_ddr_chorus_profile if scope == BLE_DDR_CHORUS_SCOPE else
         validate_ble_ddr_prefix_profile if scope == BLE_DDR_PREFIX_SCOPE else validate_ble_ddr_profile)(root, profile, stage=stage)
    reviewed_sources = PREFIX_SOURCE_SHA256 if scope in (BLE_DDR_PREFIX_SCOPE, BLE_DDR_CHORUS_SCOPE, BLE_DDR_PITCH_FIFO_SCOPE) else V2_SOURCE_SHA256 if v2 else SOURCE_SHA256
    require(profile.get('schema') == 1 and profile.get('profile') == PROFILE and
            profile.get('profile_source') == PROFILE_SOURCE and
            re.fullmatch(r'[0-9a-f]{64}', profile.get('profile_sha256', '')) is not None and
            (v2 or digest(profile.get('configuration')) == NO_LOCAL_PANEL_CONFIGURATION_SHA256),
            'explicit supported no-local-panel configuration required')
    recording = profile.get('recording', {})
    require({k:v for k,v in recording.items() if k != 'address_map'} == metadata(ble_raw_ddr=v2),
            'exact owner8 recording metadata required')
    verify_address_map(root, stage, recording.get('address_map'))
    for path, expected in reviewed_sources.items():
        require(file_sha(Path(stage) / path) == expected, 'reviewed staged source changed: ' + path)
        if path.startswith('rtl/'):
            require(file_sha(Path(root) / path) == expected, 'reviewed maintained source changed: ' + path)
    top = compact((Path(stage) / 'src/push2/gw138k_push_workstation_top.v').read_text())
    fragments = (
        ('workstation_recording_runtimeu_recording(`ifdefWORKSTATION_BLE_RAW_DDR'
         '.reset_ni(recording_memory_reset_n),.source_clk_i(dac_mclk),.memory_clk_i(memory_clk),'
         '.control_clk_i(clk_50m),.backend_ready_i(recording_channel_ready),' if v2 else
         'workstation_recording_runtimeu_recording(.reset_ni(reset_n&&ddr_client_reset_n),'
         '.source_clk_i(dac_mclk),.memory_clk_i(memory_clk),.control_clk_i(clk_50m)'),
        '.frame_epoch_i(physical_frame_epoch),.frame_sequence_i(physical_frame_sequence),.frame_pcm_i(physical_frame_pcm)',
        '.pclk(pclk),.preset_n(preset_n),.psel(recording_select),.penable(penable),.pwrite(pwrite)',
        '.APB_PPROT(),.APB_PSTRB(pstrb),.APB_PCLK(pclk),.APB_PRSTN(preset_n)',
    )
    require(all(top.count(x) == 1 for x in fragments), 'recording top source composition changed')
    return dict(scope=scope, input_sha256=reviewed_sources, top_composition_source='src/push2/gw138k_push_workstation_top.v',
                top_composition_sha256=file_sha(Path(stage) / 'src/push2/gw138k_push_workstation_top.v'),
                source_contract_verified=True, source_behavioral_simulation_verified=False)


def complete_closure(n, g, sources):
    """Inventory all endpoints; opaque CPU and RAM ports remain visible."""
    todo, seen, ends, primitives, comb, exports = [n.pin(p, 'Q') for p in sources], set(), {}, {}, set(), {}
    if not hasattr(g, '_recording_top_outputs'):
        g._recording_top_outputs = {n.canonical('', b): name for name, direction in n.directions[TOP].items()
            if direction in ('output', 'inout') for b in g.binding_bits('', name)}
    while todo:
        net = todo.pop()
        if net in seen:
            continue
        seen.add(net)
        if net in g._recording_top_outputs:
            exports[g._recording_top_outputs[net]] = net
        for p, pin, role in g.fan[net]:
            if role == 'ff':
                ends[p + '/' + pin] = n.pin(p, 'CLK')
            elif role == 'comb':
                comb.add(p)
                todo.extend(n.pin(p, out) for out in COMB[n.cells[p]['kind']])
            else:
                primitives[p + '/' + pin] = dict(kind=n.cells[p]['kind'],
                    clock_pins={x:n.pin(p,x) for x in n.cells[p]['ports'] if x in ('CLK', 'CLKA', 'CLKB')})
    return dict(ff_endpoints=dict(sorted(ends.items())), primitive_endpoints=dict(sorted(primitives.items())),
                combinational_cells=len(comb), top_output_endpoints=dict(sorted(exports.items())))


def source_groups(g):
    return dict(pcm_read_gray=g.group(F, 'read_gray', 4) + [g.register(F, 'read_binary', 4)],
        pcm_write_gray=g.group(F, 'write_gray', 5), pcm_drop_gray=g.group(D, 'gray', 32),
        command_request_payload=g.group(A, 'request_held', 49),
        command_response_payload=g.group(A, 'response_held', 33),
        command_request_toggle=[g.register(A, 'request_toggle')],
        command_ack_toggle=[g.register(A, 'acknowledge_toggle')],
        **{'release:' + s + '/' + t:[g.register(s, t, 2)] for s,t,_ in RELEASES})


def protocol_basis(*, scope=LEGACY_SCOPE):
    # This checks the code property of the exact reviewed RTL equations. It is
    # not a gate-level encoder-equivalence, formal FIFO or metastability proof.
    pointer_pairs=[]
    for current in range(32):
        following=(current+1)&31
        gray=lambda b:b^(b>>1)
        changed=gray(current)^gray(following)
        require(bin(changed).count('1')==1,'5-bit Gray modulo arithmetic property changed')
        pointer_pairs.append(dict(current=current,following=following,changed_bit=changed.bit_length()-1))
    carry_classes=[]
    for trailing_ones in range(32):
        binary_xor=(1<<(trailing_ones+1))-1
        gray_xor=binary_xor^(binary_xor>>1)
        require(gray_xor==1<<trailing_ones,'32-bit Gray increment carry identity changed')
        carry_classes.append(dict(trailing_ones=trailing_ones,changed_bit=trailing_ones))
    return dict(
        reviewed_source_revisions=(PREFIX_SOURCE_SHA256 if scope in (BLE_DDR_PREFIX_SCOPE, BLE_DDR_CHORUS_SCOPE, BLE_DDR_PITCH_FIFO_SCOPE) else
                                  V2_SOURCE_SHA256 if scope in BLE_DDR_SCOPES else SOURCE_SHA256),
        FIFO=dict(pointer_width=5,modulo_increment_cases=pointer_pairs,
            ownership='Only write_fire/read_fire increments its binary/registered-Gray pointer; otherwise both hold',
            payload='Write slot is immutable until synchronized read pointer returns ownership; destination waits for synchronized write pointer',
            memory_ownership_formally_proven=False,RAM_data_arcs_physically_verified=False),
        drop_counter=dict(width=32,increment_carry_classes=carry_classes,
            carry_identity='n xor (n+1)=(1<<(k+1))-1; Gray xor is 1<<k; higher bits cancel',
            saturation='At 0xffffffff next_drop remains unchanged; no wrap',
            same_source_edge='source_count is next_drop; registered Gray and source_drop_count commit the post-drop value on the same edge'),
        APB=dict(outstanding_transactions=1,
            request_launch='IDLE captures request_held and toggles request_toggle on the same pclk edge',
            request_stability='request_held is unchanged in WAIT_RESPONSE and COMPLETE; no new IDLE launch until roundtrip is complete',
            request_capture='req_meta, req_sync, req_settled; request_local captures at receiving edge 3, decode starts later',
            response_launch='command acceptance captures response_held and updates acknowledge_toggle on the same memory edge',
            response_stability='No new command acceptance before the next request roundtrip; response_held remains held',
            response_capture='ack_meta, ack_sync, ack_settled; WAIT_RESPONSE uses settled ACK at receiving edge 4'),
        minimum_observing_edges=dict(request_capture=3,response_capture=4),
        protocol_source_reviewed=True,protocol_formally_proven=False,
        synthesis_encoder_boolean_equivalence_verified=False,source_behavioral_simulation_verified=False,
        physical_held_stability_or_Gray_flight_verified=False)


def audit_netlist(n, *, g=None, scope=LEGACY_SCOPE):
    require(scope in (LEGACY_SCOPE, *BLE_DDR_SCOPES), 'unknown explicit scope')
    v2 = scope in BLE_DDR_SCOPES
    selected_scope = scope
    endpoint_sha256 = (PITCH_FIFO_ENDPOINT_SHA256 if scope == BLE_DDR_PITCH_FIFO_SCOPE else
                          CHORUS_ENDPOINT_SHA256 if scope == BLE_DDR_CHORUS_SCOPE else
                       PREFIX_ENDPOINT_SHA256 if scope == BLE_DDR_PREFIX_SCOPE else V2_ENDPOINT_SHA256 if v2 else ENDPOINT_SHA256)
    reset_alias_sha256 = (PITCH_FIFO_RESET_ALIAS_SHA256 if scope == BLE_DDR_PITCH_FIFO_SCOPE else
                          CHORUS_RESET_ALIAS_SHA256 if scope == BLE_DDR_CHORUS_SCOPE else
                          PREFIX_RESET_ALIAS_SHA256 if scope == BLE_DDR_PREFIX_SCOPE else '366f05b101f78e31ffad26dfba64ea15c7b6285d1dd4cffab4f753c078d7e70c')
    require(bool(endpoint_sha256) and (not v2 or reset_alias_sha256 is not None), 'explicit reviewed endpoint identities required')
    g = g or Graph(n)
    domains = dict(selected=n.pin('u_managed/runtime/clocks/selector', 'CLKOUT'),
                   apb=n.pin('u_cpu_pll/PLL_inst', 'CLKOUT0'), memory='memory_clk')
    require(domains == dict(selected='dac_mclk_d', apb='ram_clk', memory='memory_clk'),
            'selected MCLK/APB ram_clk/memory clock identities changed')
    reg = lambda s,t:g.register(s,t)
    q = lambda s,t:n.pin(reg(s,t), 'Q')
    raw = n.pin(g.register(P, 'source_release', 0), 'CLEAR')
    raw_apb = n.pin(g.register(A, 'p_release', 0), 'CLEAR')
    require(n.pin('u_reset/started_s0', 'Q') == 'reset_n' and
            n.pin('u_reset/started_s0', 'CLK') == 'clk_50m', 'common root reset producer changed')
    if v2:
        releases = [_reg(n, g, 'recording_memory_release_' + str(i)) for i in range(2)]
        root_clear = n.pin(releases[0], 'CLEAR')
        for i, p in enumerate(releases):
            require(n.cells[p]['kind'] == 'DFFCE' and n.pin(p, 'CLK') == 'memory_clk'
                    and n.pin(p, 'CE') in g.high and n.pin(p, 'CLEAR') == root_clear
                    and (n.pin(p, 'D') in g.high if i == 0 else n.pin(p, 'D') == n.pin(releases[0], 'Q')),
                    'declared root-only memory release changed: ' + p)
        proofs = [g.equivalent('root-only memory release assertion', [root_clear, 'reset_n'],
                              lambda v:v[0] == 1-v[1]),
                  g.equivalent('recording common assertion', [raw, n.pin(releases[1], 'Q')],
                              lambda v:v[0] == 1-v[1]),
                  g.equivalent('recording APB assertion', [raw_apb, n.pin(releases[1], 'Q'), 'preset_n'],
                              lambda v:v[0] == int(not all(v[1:])), cuts=('preset_n',))]
    else:
        require(n.pin('u_video/ui_reset_pipe_2_s0', 'Q') == 'ddr_client_reset_n' and
                n.pin('u_video/ui_reset_pipe_2_s0', 'CLK') == 'memory_clk', 'raw reset producer owner changed')
        proofs = [g.equivalent('recording common assertion', [raw, 'reset_n', 'ddr_client_reset_n'],
                              lambda v:v[0] == int(not(v[1] and v[2]))),
                  g.equivalent('recording APB assertion', [raw_apb, 'reset_n', 'ddr_client_reset_n', 'preset_n'],
                              lambda v:v[0] == int(not all(v[1:])), cuts=('preset_n',))]
    expected_regs, reset_chains, local_clear = set(), [], {}

    def ff(p, domain, clear):
        c = n.cells[p]
        require(c['kind'] == 'DFFCE' and n.pin(p,'CLK') == domains[domain] and
                n.pin(p,'CLEAR') == clear, 'FF primitive/clock/reset changed: ' + p)
        require(c['parameters'].get('INIT', "1'b0") == "1'b0", 'FF INIT changed: ' + p)
        expected_regs.add(p)

    for scope, stem, domain in RELEASES:
        rs = g.group(scope, stem, 3)
        clear = raw_apb if scope == A else raw
        for i,p in enumerate(rs):
            ff(p, domain, clear)
            require(n.pin(p,'CE') in g.high and (n.pin(p,'D') in g.high if i == 0 else
                    n.pin(p,'D') == n.pin(rs[i-1],'Q')), 'receiving reset release shift/CE changed: ' + p)
            if i < 2:
                c = complete_closure(n,g,[p])
                if v2 and (scope, stem, i) == (D, 'destination_release', 1):
                    # Exact observed merge: the seal's two-edge local release
                    # shares these first two common-root memory-clock stages.
                    # Pin the complete combined closure, including every seal
                    # functional CLEAR, rather than waiving intermediate fanout.
                    require(digest(c) == reset_alias_sha256,
                            'revision2 seal/reset alias complete closure changed')
                else:
                    require(c['ff_endpoints'] == {rs[i+1]+'/D':domains[domain]} and
                            not c['primitive_endpoints'] and not c['top_output_endpoints'] and
                            not c['combinational_cells'], 'reset intermediate Q complete fanout changed: ' + p)
        inverses = [n.pin(p,'O') for p,c in n.cells.items() if c['kind'] == 'INV' and
                    n.pin(p,'I') == n.pin(rs[2],'Q')]
        require(len(inverses) == 1, 'local reset final-Q inverse absent/ambiguous: ' + scope + '/' + stem)
        local_clear[(scope,stem)] = inverses[0]
        reset_chains.append(dict(scope=scope, stem=stem, domain=domain, registers=rs,
            assertion_net=clear, final_q=n.pin(rs[2],'Q'), functional_clear=inverses[0],
            raw_receiving_CLEAR_only_proposed_cut=True, functional_CLEAR_cut_proposed=False))

    sc, dc = local_clear[P,'source_release'], local_clear[P,'destination_release']
    dsc, ddc = local_clear[D,'source_release'], local_clear[D,'destination_release']
    pc, ac = local_clear[A,'p_release'], local_clear[A,'a_release']
    functional = [(P,'source_drop_count_o',32,'selected',sc),
        (P,'have_previous',None,'memory',dc), (P,'previous_rate',None,'memory',dc),
        (P,'previous_epoch',32,'memory',dc), (P,'previous_sequence',32,'memory',dc),
        (F,'write_binary',4,'selected',sc), (F,'write_gray',5,'selected',sc),
        (F,'read_binary',5,'memory',dc), (F,'read_gray',4,'memory',dc),
        (F,'read_gray_meta',5,'selected',sc), (F,'read_gray_sync',5,'selected',sc),
        (F,'write_gray_meta',5,'memory',dc), (F,'write_gray_sync',5,'memory',dc),
        (D,'gray',32,'selected',dsc), (D,'meta',32,'memory',ddc), (D,'sync_value',32,'memory',ddc)]
    functional += [(A,t,w,'apb',pc) for t,w in [('state',2),('request_held',49),('request_toggle',None),
        ('response_local',33),('ack_meta',None),('ack_sync',None),('ack_settled',None)]]
    functional += [(A,t,w,'memory',ac) for t,w in [('request_local',49),('response_held',33),
        ('req_meta',None),('req_sync',None),('req_settled',None),('request_decoded',None),('acknowledge_toggle',None)]]
    for scope,stem,width,domain,clear in functional:
        for p in g.group(scope,stem,width):
            ff(p,domain,clear)
    actual_regs = {p for p in g.regs if p.startswith(P+'/') or p.startswith(A+'/')}
    require(actual_regs == expected_regs and len(expected_regs) == 425, 'complete PCM/APB FF inventory changed')

    syncs = []
    def pair(first, second, source, destination):
        require(n.pin(first,'D') == n.pin(source,'Q') and n.pin(second,'D') == n.pin(first,'Q'),
                'synchronizer declared producer/shift changed: ' + first)
        require(n.pin(first,'CE') in g.high and n.pin(second,'CE') in g.high,
                'synchronizer conditional enable changed: ' + first)
        c = complete_closure(n,g,[first])
        require(c['ff_endpoints'] == {second+'/D':domains[destination]} and not c['primitive_endpoints']
                and not c['top_output_endpoints'] and not c['combinational_cells'],
                'synchronizer first-Q complete fanout changed: ' + first)
        syncs.append(dict(source=source,source_kind=n.cells[source]['kind'],source_clock=n.pin(source,'CLK'),
                          source_q=n.pin(source,'Q'),first_d=n.pin(first,'D'),second_d=n.pin(second,'D'),
                          first=first, second=second, destination_clock=domains[destination],
                          first_q_complete_fanout=c))

    for first, second, source, destination in [('req_meta','req_sync','request_toggle','memory'),
                                              ('ack_meta','ack_sync','acknowledge_toggle','apb')]:
        pair(reg(A,first),reg(A,second),reg(A,source),destination)
    for second,third in [('req_sync','req_settled'),('ack_sync','ack_settled')]:
        require(n.pin(reg(A,third),'D') == q(A,second) and n.pin(reg(A,third),'CE') in g.high,
                'APB third settling stage changed: ' + third)
    groups = source_groups(g)
    gray_groups = []
    for label,scope,first,second,dest in [('pcm_read_gray',F,'read_gray_meta','read_gray_sync','selected'),
        ('pcm_write_gray',F,'write_gray_meta','write_gray_sync','memory'),
        ('pcm_drop_gray',D,'meta','sync_value','memory')]:
        sources = groups[label]
        for i,source in enumerate(sources):
            pair(g.register(scope,first,i),g.register(scope,second,i),source,dest)
        gray_groups.append(dict(id=label,width=len(sources),sources=sources,destination_clock=domains[dest],
            read_MSB_alias=('read_binary[4]' if label=='pcm_read_gray' else None),
            source_Gray_sequence_behavior_verified=False, physical_bit_flight_verified=False))

    payloads=[]
    for label,source,capture,width,dest in [('command_request_payload','request_held','request_local',49,'memory'),
        ('command_response_payload','response_held','response_local',33,'apb')]:
        src,dst=g.group(A,source,width),g.group(A,capture,width)
        ces={n.pin(p,'CE') for p in dst}
        require(len(ces)==1,'payload capture CE differs: '+label)
        for p,z in zip(src,dst):
            require(n.pin(z,'D')==n.pin(p,'Q'),'held payload bit mapping changed: '+label)
        payloads.append(dict(id=label,width=width,source_registers=src,capture_registers=dst,
            capture_ce=next(iter(ces)),destination_clock=domains[dest],
            minimum_destination_edges=3 if label=='command_request_payload' else 4))
    request_ce=payloads[0]['capture_ce']
    proofs.append(g.equivalent('request capture only at third settling edge',
        [request_ce,q(A,'req_sync'),q(A,'req_settled')],lambda v:v[0]==(v[1]^v[2])))
    response_ce=payloads[1]['capture_ce']
    state0=n.pin(g.register(A,'state',0),'Q');state1=n.pin(g.register(A,'state',1),'Q')
    proofs.append(g.equivalent('response capture after third APB settling edge in WAIT_RESPONSE',
        [response_ce,state0,state1,q(A,'ack_settled'),q(A,'request_toggle')],
        lambda v:(v[1] and v[2]) or v[0]==int(v[1] and not v[2] and v[3]==v[4])))
    for held,toggle in [('request_held','request_toggle'),('response_held','acknowledge_toggle')]:
        source_ce={n.pin(p,'CE') for p in groups['command_request_payload' if held=='request_held' else 'command_response_payload']}
        require(source_ce=={n.pin(reg(A,toggle),'CE')},'payload/toggle common launch enable changed: '+held)
    proofs.append(g.equivalent('request toggle changes only with its held payload launch',
        [n.pin(reg(A,'request_toggle'),'D'),q(A,'request_toggle')],lambda v:v[0]==1-v[1]))
    require(n.pin(reg(A,'acknowledge_toggle'),'D')==q(A,'req_settled'),'acknowledge identity source changed')

    closures={}
    for label,sources in groups.items():
        c=complete_closure(n,g,sources)
        require(not c['top_output_endpoints'],'reviewed source exported to top output: '+label)
        shape={k:c[k] for k in ('ff_endpoints','primitive_endpoints')}
        require(digest(shape)==endpoint_sha256.get(label),'complete source endpoint shape changed: '+label)
        closures[label]=dict(source_registers=sources,endpoint_sha256=digest(shape),**c,
            endpoint_clock_counts=dict(Counter(c['ff_endpoints'].values())),
            primitive_semantics_accepted=False)
    storage={p:c for p,c in n.cells.items() if p.startswith(F+'/') and c['kind'] not in n.modules
        and not c['kind'].startswith('DFF') and c['kind'] not in COMB}
    require(len(storage)==25 and all(c['kind']=='RAM16SDP4' and n.pin(p,'CLK')==domains['selected']
            for p,c in storage.items()),'PCM 16x98 distributed storage primitive/clock inventory changed')
    return dict(policy=POLICY,scope=selected_scope,clock_domains=domains,complete_reviewed_FF_count=425,
        reset_receiving_chains=reset_chains,ordinary_first_stage_pairs=syncs[:2],
        gray_first_stage_pairs=syncs[2:],gray_groups=gray_groups,
        gray_first_stage_bits=42,payload_groups=payloads,payload_bits=82,
        complete_source_fanout=closures,boolean_proofs=proofs,
        source_protocol_basis=protocol_basis(scope=selected_scope),
        reviewed_reset_aliases=([dict(logical_scope='u_recording/seal_cdc',
            logical_stages=['destination_release_meta','destination_release_sync'],
            physical_stages=g.group(D,'destination_release',3)[:2],
            basis='same pinned common reset, memory clock, zero assertion and constant-one shift',
            combined_intermediate_complete_closure_sha256=reset_alias_sha256,
            physical_reset_acceptance=False)] if v2 else []),
        first_D_producers_are_declared_unique_registered_Qs=True,
        response_illegal_state_11_behavior_accepted=False,
        storage_inventory={p:dict(kind=c['kind'],clock=n.pin(p,'CLK')) for p,c in storage.items()},
        pcm_RAM_data_ownership_or_data_arcs_accepted=False,source_behavioral_simulation_verified=False,
        seal_cdc_accepted=False,native_commit_and_owner8_accepted=False,full_reset_accepted=False,
        recording_cdc_complete=False,physical_cdc_accepted=False,routed_timing_verified=False,
        constraints_complete=False,hardware_tested=False,deployment_allowed=False,release_ready=False)


def selector(p,pin):
    require(re.fullmatch(r'.*_s\d+',p) is not None,'selector register suffix changed')
    return p.rsplit('_s',1)[0]+'_s*/'+pin


def query(selectors):
    return '[get_pins {'+' '.join(selectors)+'}]'


def constraint_proposal(result):
    lines=[]
    def path(sources,captures,budget):
        p='-from '+query(sources)+' -to '+query(captures)
        lines.extend((f'set_max_delay {budget:.3f} '+p,'set_false_path -hold '+p))
    for chain in result['reset_receiving_chains']:
        rs=chain['registers']
        lines.append('set_false_path -to '+query([selector(p,'CLEAR') for p in rs]))
        for p,z in zip(rs,rs[1:]):
            lines.append('set_max_delay 2.000 -from '+query([selector(p,'Q')])+' -to '+query([selector(z,'D')]))
    for pair in result['ordinary_first_stage_pairs']:
        lines.append('set_false_path -to '+query([selector(pair['first'],'D')]))
        lines.append('set_max_delay 2.000 -from '+query([selector(pair['first'],'Q')])+
                     ' -to '+query([selector(pair['second'],'D')]))
    for group in result['gray_groups']:
        scope,stem,second=(F,'read_gray_meta','read_gray_sync') if group['id']=='pcm_read_gray' else (
            (F,'write_gray_meta','write_gray_sync') if group['id']=='pcm_write_gray' else (D,'meta','sync_value'))
        first=[scope+'/'+stem+'_'+str(i)+'_s*/D' for i in range(group['width'])]
        path([selector(p,'Q') for p in group['sources']],first,10.000)
        lines.append('set_max_delay 2.000 -from '+query([x.rsplit('/',1)[0]+'/Q' for x in first])+
            ' -to '+query([scope+'/'+second+'_'+str(i)+'_s*/D' for i in range(group['width'])]))
    for group in result['payload_groups']:
        path([selector(p,'Q') for p in group['source_registers']],
             [selector(p,'D') for p in group['capture_registers']],
             10.000 if group['id']=='command_request_payload' else 20.000)
    require(len(lines)==35,'proposal constraint count changed')
    return dict(policy=POLICY,proposal_only=True,sdc='\n'.join(lines)+'\n',constraint_count=len(lines),
        budget_basis=dict(gray_flight_ns=10.0,gray_minimum_source_period_ns=10.0,
            held_request_destination_period_ns=10.0,held_response_destination_period_ns=20.0,
            receiving_interstage_ns=2.0,interstage_budget_status='new proposal; routed resolution and MTBF not accepted'),
        no_functional_CLEAR_cut=True,no_whole_clock_domain_cut=True,
        source_hold_or_RAM_data_constraints_complete=False,tool_query_resolution_verified=False,
        constraints_complete=False,physical_cdc_accepted=False,deployment_allowed=False)


def audit_proposal_queries(n,result,proposal):
    items={item for body in re.findall(r'\[get_pins \{([^}]+)\}\]',proposal['sdc']) for item in body.split()}
    wanted={}
    for item in items:
        m=re.fullmatch(r'([^*?\[\]]+)_s\*/([A-Za-z0-9_]+)',item)
        require(m is not None,'proposal selector outside exact reviewed suffix grammar: '+item)
        wanted[item]=(m[1],m[2])
    stems={stem for stem,_ in wanted.values()}
    matches=defaultdict(list)
    # Index every occurrence of _s in every leaf path, not only numeric suffix
    # paths. Thus a new stem_sfoo or stem_s1_extra_s2 overmatch also fails.
    for p,c in n.cells.items():
        if c['kind'] in n.modules:
            continue
        for m in re.finditer('_s',p):
            stem=p[:m.start()]
            if stem in stems:
                for pin in c['ports']:
                    matches[stem,pin].append(p+'/'+pin)
    queries={}
    for item,key in sorted(wanted.items()):
        found=sorted(matches[key])
        require(len(found)==1,'proposal selector not one exact pin: '+item)
        queries[item]=found
    cut_clear={queries[item][0] for line in proposal['sdc'].splitlines()
        if line.startswith('set_false_path -to ') for body in re.findall(r'\[get_pins \{([^}]+)\}\]',line)
        for item in body.split() if item.endswith('/CLEAR')}
    receiving_clear={p+'/CLEAR' for chain in result['reset_receiving_chains'] for p in chain['registers']}
    require(cut_clear==receiving_clear and len(cut_clear)==18,'proposal raw CLEAR cut scope changed')
    require(not any('get_clocks' in line or 'get_regs' in line for line in proposal['sdc'].splitlines()),
            'proposal contains non-pin or whole-domain query')
    return dict(source_netlist_selectors=queries,source_netlist_resolution_verified=True,
        receiving_CLEAR_pins=sorted(cut_clear),tool_query_resolution_verified=False,
        Gowin_Tcl_command_resolution_verified=False,proposal_installed=False)


def run_audit(root,stage,evidence,*,scope=LEGACY_SCOPE):
    root,stage=Path(root),Path(stage)
    before=verify_synthesis_identity(stage,evidence)
    if scope == BLE_DDR_PITCH_FIFO_SCOPE:
        validate_pitch_fifo_VG(stage)
    elif scope == BLE_DDR_CHORUS_SCOPE:
        validate_chorus_VG(stage)
    elif scope == BLE_DDR_PREFIX_SCOPE:
        validate_prefix_VG(stage)
    profile=json.loads((stage.parents[1]/'workstation_profile.json').read_text())
    helper_paths={Path(__file__).resolve(),*(Path(inspect.getsourcefile(f)).resolve() for f in
        (Graph,OwnerResetNetlist,verify_synthesis_identity,audit_runtime_clocks,metadata,verify_address_map,
         validate_ble_ddr_profile))}
    helper_paths.update(root/p for p in CLOCK_SOURCES)
    helper_paths.update((ROOT/'sim/test_workstation_recording_phase1_cdc.py'))
    if scope in BLE_DDR_SCOPES:
        helper_paths.add(ROOT/'sim/test_workstation_ble_ddr_cdc_scope.py')
    if scope == BLE_DDR_PREFIX_SCOPE:
        helper_paths.update(ROOT/p for p in ('tools/workstation_ble_ddr_prefix_cdc_scope.py',
            'tools/workstation_ble_ddr_prefix_cdc_endpoints.py', 'tools/workstation_runtime_counter.py',
            'sim/test_workstation_ble_ddr_prefix_cdc_scope.py'))
    if scope == BLE_DDR_PITCH_FIFO_SCOPE:
        helper_paths.update(root/p for p in PITCH_FIFO_AUDIT_SOURCES)
    if scope == BLE_DDR_CHORUS_SCOPE:
        helper_paths.update(root/p for p in CHORUS_AUDIT_SOURCES)
    helpers={str(p):file_sha(p) for p in sorted(helper_paths)}
    sources=validate_sources(root,stage,profile,scope=scope)
    text=(stage/VG_RELATIVE).read_text()
    n=OwnerResetNetlist(text,TOP)
    result=audit_netlist(n,scope=scope)
    proposal=constraint_proposal(result)
    result.update(schema=1,synthesis=before,sources=sources,clock_audit=audit_runtime_clocks(root,stage,text),
        constraint_proposal=proposal,proposal_query_audit=audit_proposal_queries(n,result,proposal),
        audit_source_sha256=helpers,implementation_path=str(Path(__file__).resolve()),
        source_seal_before_and_after=True,eda_invoked=False,hardware_operated=False)
    if scope in BLE_DDR_SCOPES:
        require(sources == validate_sources(root,stage,profile,scope=scope), 'revision2 source contract changed during audit')
    require(before==verify_synthesis_identity(stage,evidence) and
            helpers=={str(p):file_sha(p) for p in sorted(helper_paths)},'synthesis/audit inputs changed')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--synthesis-evidence',type=Path,required=True)
    parser.add_argument('--scope',choices=(LEGACY_SCOPE,*BLE_DDR_SCOPES),default=LEGACY_SCOPE)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--proposal-output',type=Path,required=True)
    args=parser.parse_args()
    result=run_audit(ROOT,args.project,args.synthesis_evidence,scope=args.scope)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    args.proposal_output.parent.mkdir(parents=True,exist_ok=True)
    args.proposal_output.write_text(result['constraint_proposal']['sdc'])
    print(json.dumps({k:result[k] for k in ('policy','complete_reviewed_FF_count','gray_first_stage_bits',
        'payload_bits','recording_cdc_complete','constraints_complete','deployment_allowed')}))


if __name__=='__main__':
    main()
