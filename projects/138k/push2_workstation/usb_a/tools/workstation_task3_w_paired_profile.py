"""Explicit paired W role; keep the immutable media/demo source policies.

The native board owns one HCI recording object and one DDR fabric.  This role
replaces software PCM injection with typed CNN/record streams and routes both
PCM1 and clock commands to M.  Only staged top wiring is adapted, reversibly.
"""
from pathlib import Path
import hashlib
import json
import re
from tools import workstation_task3_w_media_profile as media

POLICY = 'task3_w_paired_exact_top_composition_v1'
NAME = 'custom138k-workstation-task3-w-paired-v1'
PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired.sv'
PHONE_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired_phone_blocks.sv'
BATCH_PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired_phone_batch.sv'
from tools.workstation_task3_w_banked96 import PROVIDER as BANKED96_PROVIDER
BATCH_MEDIA_POLICY = 'task3_pcm_block6_credit8_phone_window5_atomic_snapshot_batch_v3'
PHONE_BATCH_POLICY = 'full_key_atomic_owner_snapshot_command_v1'
REFERENCE = 'rtl/workstation/workstation_task3_w_paired_top_reference.json'
BOARD = 'rtl/workstation/workstation_task3_w_paired_board.svh'
HCI_PROVIDER = 'rtl/workstation/workstation_task3_w_paired_hci.sv'
HCI_SCOPED_SOURCES = ('rtl/bluetooth/workstation_bluetooth.sv',
    'native_bluetooth/bt_verilog_core.v', 'native_bluetooth/bt_gatt.v',
    'native_bluetooth/ble_protocol_command.v')
TOP = media.TOP
PARENT_TOP_SHA256 = '4b4a99f674a7033b032a3e82b98e553d7d7675689627ca4fb0cebf9746738d0f'
REFERENCE_SHA256 = 'f268c0d8466513c5f59fe79dcda7580eb7cc37dd2031564c32250c66bc0f0e95'
FIRMWARE_POLICY = 'task3_w_paired_media_single_recording_60s_v1'
BATCH_FIRMWARE_POLICY = 'task3_w_paired_phone_batch_single_recording_60s_v1'
SOURCES = tuple(s for s in media.SOURCES if s not in (
    'rtl/workstation/workstation_task3_w_media.sv', media.APB)) + (
    'rtl/workstation/workstation_task3_w_paired.sv',
    'rtl/workstation/workstation_task3_w_bus_endpoint.sv',
    'rtl/workstation/workstation_task3_phone_command_proxy.sv',
    'rtl/workstation/workstation_task3_phone_command_mux.sv',
    'rtl/workstation/workstation_task3_phone_window_tx.sv',
    'rtl/workstation/workstation_task3_phone_batch_w.sv',
    'rtl/workstation/workstation_task3_record_source_gate.sv',
    HCI_PROVIDER,
    'rtl/music/workstation_task3_cnn_stream_w.sv')
DEPENDENCIES = tuple(dict.fromkeys((*media.DEPENDENCIES,
    'tools/workstation_task3_w_fault_cdc.py',
    'tools/workstation_record_cancel_compare.py',
    'tools/workstation_record_peer_compare.py',
    'tools/workstation_w_identity_bytes.py',
    'rtl/workstation/workstation_w_identity_bytes_v1.adaptation.json',
    'rtl/workstation/workstation_record_peer_compare_v1.adaptation.json',
    'rtl/workstation/workstation_record_cancel_compare_v1.adaptation.json',
    'tools/workstation_w_context_compare.py',
    'tools/workstation_task3_w_paired_profile.py', PROVIDER, BATCH_PROVIDER, REFERENCE, BOARD,
    'tools/workstation_task3_w_paired_firmware.py',
    'tools/build_resource_rework.py',
    'tools/workstation_task3_w_paired_cdc_audit.py',
    'tools/workstation_task3_paired_board.py',
    'rtl/workstation/workstation_task3_paired_link_board.svh',
    'rtl/workstation/task3_paired_channels.vh',
    )))
# Only the explicitly selected new batch ELF consumes this separate review.
BATCH_DEPENDENCIES = ('tools/workstation_task3_w_phone_batch_firmware_review.json',)
RETIRED_SELECTORS = ('u_clock_service/', 'u_managed/runtime/cpu_pcm.',
    'u_task3_media_apb/',
    'u_managed/media_stop/request_toggle_s', 'u_managed/media_stop/hold_50_s',
    'u_managed/runtime/serializer/current_sequence_',
    'u_managed/runtime/clocks/transaction/pending_44k1_s',
    'u_managed/runtime/clocks/transaction/pending_epoch_',
    'u_managed/runtime/serial_rate_s',
    *(f'u_managed/runtime/serial_epoch_{bit}_s' for bit in range(1, 32)))
PAIRED_PIN_REBIND = tuple((scope + '/RESET', scope + '/CLEAR') for scope in (
    'u_managed/startup_compute_0_s*', 'u_managed/runtime/startup_compute_0_s*',
    'u_managed/runtime/startup_memory_0_s*', 'u_managed/runtime/startup_serial_0_s*'))


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def reference(root):
    payload = (Path(root) / REFERENCE).read_bytes()
    if digest(payload) != REFERENCE_SHA256:
        raise ValueError('W paired reference identity drift')
    data = json.loads(payload)
    if data.get('schema') != 1 or data.get('policy') != POLICY or data.get('parent_sha256') != PARENT_TOP_SHA256:
        raise ValueError('W paired reference schema/parent drift')
    return data


def apply_top(root, text):
    data = reference(root)
    if digest(text) != data['parent_sha256']:
        raise ValueError('W paired input top identity drift')
    for row in data['edits']:
        if text.count(row['parent']) != 1:
            raise ValueError('W paired forward anchor drift')
        text = text.replace(row['parent'], row['selected'], 1)
    if digest(text) != data['selected_sha256']:
        raise ValueError('W paired selected top identity drift')
    return text


adapt_top = apply_top


def inverse_top(root, text):
    if '`include "' + BOARD + '"' not in text:
        return text
    selected = text
    data = reference(root)
    if digest(text) != data['selected_sha256']:
        raise ValueError('W paired selected identity drift')
    for row in reversed(data['edits']):
        if text.count(row['selected']) != 1:
            raise ValueError('W paired inverse anchor drift')
        text = text.replace(row['selected'], row['parent'], 1)
    if digest(text) != data['parent_sha256'] or apply_top(root, text) != selected:
        raise ValueError('W paired inverse identity drift')
    return text


def prepare_top(root, stage):
    target = Path(stage) / TOP
    selected = apply_top(root, target.read_text())
    target.write_text(selected)
    return dict(policy=POLICY, reference_sha256=REFERENCE_SHA256,
                parent_sha256=PARENT_TOP_SHA256, selected_sha256=digest(selected),
                rtl_text_generation=False, hardware_accepted=False)


def retired_source(path):
    return media.retired_source(path) or path in ('rtl/workstation/workstation_task3_w_media.sv', media.APB)


def select_sources(stage, files):
    evidence = media.select_sources(stage, files)
    retired = {}
    for row in files:
        rel = row.get('path')
        if row.get('enable') == '1' and rel in ('rtl/workstation/workstation_task3_w_media.sv', media.APB):
            retired[rel] = media.sha(Path(stage) / rel)
            row.set('enable', '0')
    scoped = scope_hci_sources(stage, files)
    return dict(evidence, policy=POLICY, paired_retired_compilation_sha256=retired,
                paired_HCI_compilation=scoped)


def scope_hci_sources(stage, files):
    """Move only these existing HCI units under the paired-only macro scope."""
    for source in HCI_SCOPED_SOURCES:
        rows = [r for r in files if r.get('path') == source]
        if len(rows) != 1 or rows[0].get('enable') != '1':
            raise ValueError('W paired HCI standalone input owner drift: ' + source)
        rows[0].set('enable', '0')
    return verify_hci_scope(stage, files)


def verify_hci_scope(stage, files=None):
    from xml.etree import ElementTree as ET
    stage = Path(stage)
    if files is None:
        files = ET.parse(stage / 'Prj1.gprj').find('FileList')
    providers = [r for r in files if r.get('path') == HCI_PROVIDER]
    if len(providers) != 1 or providers[0].get('enable') != '1':
        raise ValueError('W paired HCI scoped compilation owner absent/drifted')
    provider = (stage / HCI_PROVIDER).read_text()
    begin, end = '`define WORKSTATION_TASK3_W_PAIRED', '`undef WORKSTATION_TASK3_W_PAIRED'
    if provider.count(begin) != 1 or provider.count(end) != 1:
        raise ValueError('W paired HCI macro scope drift')
    scoped = {}
    for source in HCI_SCOPED_SOURCES:
        rows = [r for r in files if r.get('path') == source]
        if len(rows) != 1 or rows[0].get('enable') != '0':
            raise ValueError('W paired HCI duplicate standalone compilation: ' + source)
        anchor = '`include "' + source + '"'
        if provider.count(anchor) != 1 or not (provider.index(begin) < provider.index(anchor) < provider.index(end)):
            raise ValueError('W paired HCI source outside paired macro scope: ' + source)
        scoped[source] = media.sha(stage / source)
    return dict(provider=HCI_PROVIDER, provider_sha256=media.sha(stage / HCI_PROVIDER),
                canonical_staged_sha256=scoped, standalone_compilation_disabled=True,
                canonical_source_bytes_preserved=True, scoped_macro='WORKSTATION_TASK3_W_PAIRED')


def _paired_constraints(text):
    lines, changes = [], []
    for index, line in enumerate(text.splitlines()):
        removed, rebound, empty = [], [], []
        def query(match):
            keep = []
            for old in match[2].split():
                selected = old.replace('u_task3_media/cnn_task/',
                                       'u_task3_media/cnn_stream/task_service/')
                selected = selected.replace('u_managed/pcm_apb.commands/', 'u_task3_pcm_control/')
                selected = selected.replace('u_task3_media/cnn_stream/task_service/cnn/model_memory_meta',
                                            'u_task3_media/cnn_stream/task_service/backend_meta')
                for before, after in PAIRED_PIN_REBIND:
                    if selected == before:
                        selected = after
                if selected.startswith(RETIRED_SELECTORS):
                    removed.append(old)
                else:
                    keep.append(selected)
                    if old != selected:
                        rebound.append(dict(original=old, selected=selected, query=match[1]))
            if not keep:
                empty.append(match[1])
            return '[' + match[1] + ' {' + ' '.join(keep) + '}]'
        selected = media.QUERY.sub(query, line)
        if removed or rebound:
            changes.append(dict(line_index=index, selected_line_index=len(lines), original=line,
                                selected=None if empty else selected,
                                removed_selectors=removed, rebound_selectors=rebound))
        if not empty:
            lines.append(selected)
    selected = '\n'.join(lines) + '\n'
    return selected, changes


def constraints(text):
    intermediate, delegated = media.constraints(text)
    selected, changes = _paired_constraints(intermediate)
    return selected, dict(policy=POLICY, original_sha256=digest(text),
        selected_sha256=digest(selected), delegated_media=delegated, changes=changes,
        clocks_or_budgets_relaxed=False, physical_cdc_accepted=False,
        netlist_resolution_required=True)


def scoped_constraints(text):
    """Project an existing scoped bundle through the same role selectors.

    Full board composition also appends media-owned constraints. They remain
    subject to the complete board inverse/roundtrip, rather than becoming new
    members of each caller's scoped source bundle.
    """
    selected, evidence = constraints(text)
    added, _ = _paired_constraints(media.added_sdc())
    if not selected.endswith(added):
        raise ValueError('W paired scoped SDC media suffix drift')
    return selected[:-len(added)], evidence


def restore_constraints(selected, evidence):
    if evidence.get('policy') != POLICY or evidence.get('selected_sha256') != digest(selected):
        raise ValueError('W paired SDC evidence absent/drifted')
    lines = selected.splitlines()
    for row in reversed(evidence['changes']):
        index = row['selected_line_index']
        if row['selected'] is None:
            lines.insert(index, row['original'])
        else:
            if lines[index] != row['selected']:
                raise ValueError('W paired SDC inverse drift')
            lines[index] = row['original']
    original = media.restore_constraints('\n'.join(lines) + '\n', evidence['delegated_media'])
    wanted, actual = constraints(original)
    if wanted != selected or actual != evidence:
        raise ValueError('W paired SDC roundtrip changed')
    return original


def cnn_memory_provider(provider=PROVIDER):
    if provider not in (PROVIDER, PHONE_PROVIDER, BATCH_PROVIDER, BANKED96_PROVIDER):
        raise ValueError('unregistered W paired CNN provider')
    return dict(policy='task3_w_signal_cqt_bsram_v1', USE_DDR_SIGNAL=0,
                USE_DDR_CQT_COEFF=0, USE_DDR_FRONT_COEFF=1, USE_ALL_DDR=0, provider=provider)


def cnn_memory_configuration(configuration):
    phone_policy = configuration.get('phone_window_policy')
    if phone_policy not in (None, 'posted_window5_single_inflight_applied_barrier_v1'):
        raise ValueError('W paired phone-window configuration drift')
    selected_batch = phone_batch_configuration(configuration)
    from tools.workstation_task3_w_banked96 import configured
    banked96=configured(configuration)
    selected = cnn_memory_provider(BANKED96_PROVIDER if banked96 else BATCH_PROVIDER if selected_batch else PHONE_PROVIDER if phone_policy else PROVIDER)
    if configuration.get('cnn_memory_policy', selected['policy']) != selected['policy']:
        raise ValueError('W paired CNN memory configuration drift')
    return selected


def phone_batch_configuration(configuration):
    """An exact opt-in combination, never inferred from the old window policy."""
    if 'phone_batch_policy' in configuration:
        expected = dict(phone_batch_policy=PHONE_BATCH_POLICY,
            phone_window_policy='posted_window5_single_inflight_applied_barrier_v1',
            interboard_media_policy=BATCH_MEDIA_POLICY,
            ae350_firmware_policy=BATCH_FIRMWARE_POLICY)
        if any(configuration.get(key) != value for key, value in expected.items()):
            raise ValueError('W paired phone-batch configuration drift')
        return True
    if (configuration.get('interboard_media_policy') == BATCH_MEDIA_POLICY or
            configuration.get('ae350_firmware_policy') == BATCH_FIRMWARE_POLICY):
        raise ValueError('W paired phone-batch policy omitted')
    return False


def verify_batch_provider(stage, provider):
    """Bind the actual batch macro scope and included role to this one provider."""
    if provider == BANKED96_PROVIDER:
        stage = Path(stage)
        expected = ['`define WORKSTATION_AE350_ROM96', '`include "' + BATCH_PROVIDER + '"',
                    '`undef WORKSTATION_AE350_ROM96']
        actual = [line.strip() for line in (stage/provider).read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith('//')]
        if actual != expected:
            raise ValueError('W paired banked96 macro scope drift')
        parent = verify_batch_provider(stage, BATCH_PROVIDER)
        return dict(parent, provider=provider, provider_sha256=media.sha(stage/provider),
            batch_provider=parent, physical_rom_bytes=98304)
    if provider != BATCH_PROVIDER:
        if provider not in (PROVIDER, PHONE_PROVIDER):
            raise ValueError('unregistered W paired provider')
        return dict(provider=provider, phone_batch=False)
    stage = Path(stage)
    expected = ['`define WORKSTATION_TASK3_PHONE_WINDOW_BLOCK',
        '`define WORKSTATION_TASK3_PHONE_BATCH', '`include "' + PROVIDER + '"',
        '`undef WORKSTATION_TASK3_PHONE_BATCH', '`undef WORKSTATION_TASK3_PHONE_WINDOW_BLOCK']
    actual = [line.strip() for line in (stage / provider).read_text().splitlines()
              if line.strip() and not line.lstrip().startswith('//')]
    if actual != expected:
        raise ValueError('W paired batch provider actual macro scope drift')
    if not (stage / PROVIDER).is_file():
        raise ValueError('W paired batch included provider absent')
    return dict(provider=provider, provider_sha256=media.sha(stage / provider),
        included_provider=PROVIDER, included_provider_sha256=media.sha(stage / PROVIDER),
        phone_batch=True, phone_window=True, media_version=3, media_features='0xc0080601')


def recording_metadata(root):
    return dict(media.recording_metadata(root), policy='task3_w_paired_single_C_BLE_recording_60s_v1',
        final_pcm_source='M final physical serializer tap through bounded typed record ingress',
        software_apb_base=None, software_injection_enabled=False,
        physical_M_tap_connected=True, physical_LCD_hardware_verified=False)


def raw_metadata(root):
    return dict(recording_metadata(root), policy='task3_w_paired_single_C_BLE_raw_ddr_60s_v1',
        full_HCI_Classic_GATT=True, second_business_object=False,
        source_is_W_local_DAC=False)


def build_firmware(root, evidence, prefix=None, phone_batch=False, physical_rom_bytes=131072):
    return media.build_firmware(root, evidence, prefix, paired_source=True, phone_batch=phone_batch, physical_rom_bytes=physical_rom_bytes)


verify_firmware = media.verify_firmware


def verify_source(root, stage):
    """Undo common wiring before the strict role inverse; retain every hash.

    The selected preprocessed text is inspected separately below. This check
    binds that evidence's raw staged top to both exact adaptation layers.
    """
    from tools import workstation_task3_paired_board as common
    root, stage = Path(root), Path(stage)
    selected = (stage / TOP).read_text()
    if selected.count('`include "' + common.BOARD + '"') != 1:
        raise ValueError('W paired common board composition absent')
    role_selected = common.inverse_top(root, selected, 'W')
    parent = inverse_top(root, role_selected)
    if digest(parent) != PARENT_TOP_SHA256 or apply_top(root, parent) != role_selected:
        raise ValueError('W paired common/role parent identity drift')
    return dict(policy=POLICY, common_policy=common.POLICY,
                selected_top_sha256=digest(selected),
                role_selected_top_sha256=digest(role_selected),
                parent_top_sha256=digest(parent), reference_sha256=REFERENCE_SHA256,
                common_then_role_inverse=True, hardware_accepted=False)


def selected_source_evidence(stage, text):
    from xml.etree import ElementTree as ET
    stage = Path(stage)
    top_identity = verify_source(stage, stage)
    hci_scope = verify_hci_scope(stage)
    enabled = [row.get('path') for row in ET.parse(stage / 'Prj1.gprj').find('FileList')
               if row.get('enable') == '1']
    providers = [path for path in enabled if path.startswith('rtl/workstation/workstation_profile_')]
    if providers not in ([PROVIDER], [PHONE_PROVIDER], [BATCH_PROVIDER], [BANKED96_PROVIDER]):
        raise ValueError('W paired actual provider must be unique')
    batch_provider = verify_batch_provider(stage, providers[0])
    def module(name):
        rows = re.findall(r'\bmodule\s+' + re.escape(name) + r'\b.*?\bendmodule\b', text, re.S)
        if len(rows) != 1:
            raise ValueError('W paired module must be unique: ' + name)
        return ''.join(rows[0].split())
    def once(body, anchor):
        if body.count(''.join(anchor.split())) != 1:
            raise ValueError('W paired actual binding drift: ' + anchor)
    top, native = module('workstation_custom_138k_top'), module('workstation_task3_w_paired')
    # Keep old sealed stages readable without certifying their direct DDR
    # fault bypass. New board bytes must bind the synchronized local fence.
    fault_boundary = {}
    stream = module('workstation_task3_cnn_stream_w')
    reset_release_selected = '.DOMAIN_RESET_RELEASE(1\'b1)' in stream
    if reset_release_selected:
        from tools.workstation_task3_cnn_reset import source_evidence
        fault_boundary['CNN_domain_reset_boundary'] = source_evidence(stage)
        once(stream, 'wire reset_request_n=reset_ni && memory_reset_ni;')
        once(stream, 'wire control_reset_n=control_release[2];')
        once(stream, '.reset_ni(control_reset_n),.memory_clk_i(memory_clk_i),.memory_reset_ni(memory_reset_ni)')
        task = module('workstation_cnn_task_service')
        once(task, 'assign control_reset_n=control_release[2];')
        once(task, 'assign native_reset_n=native_release[2];')
        once(task, 'wire live=control_reset_n && (DOMAIN_RESET_RELEASE || memory_reset_ni) && backend_sync && !fatal_o;')
        once(task, '.NATIVE_LIFETIME_RESET(DOMAIN_RESET_RELEASE)')
    if media.sha(stage / 'rtl/music/workstation_task3_cnn_stream_w.sv') != 'ba67f7d71b08d3ccf22a766b79bc1fa312d73c219758b45bac046d687eac94b0':
        once(stream, 'else transport_fault_control<={transport_fault_control[0],transport_fault_i};')
        once(stream, 'wire live='+('control_reset_n' if reset_release_selected else 'reset_ni')+' && link_ready_i && !transport_fault_control[1] && !panic_i;')
        once(stream, '.backend_ready_i(backend_ready_i),.transport_fault_i(transport_fault_i)')
        fault_boundary['CNN_fault_control_boundary'] = dict(
            policy='native_immediate_quarantine_CNN_control_fault_sync2_v1',
            control_sync_stages=2, native_broker_fault_binding_preserved=True,
            direct_memory_fault_to_CNN_control=False, source_binding_verified=True,
            mapped_CDC_verified=False, routed_timing_verified=False)
    if media.sha(stage / BOARD) != '0a58c9de4c8c47ce541918ad0b2b385b61accb7993d54b32eaee2b9a8d264d82':
        once(top, '.record_transport_fault_i(!recording_channel_ready50 || raw_channel_fault)')
        once(top, '.control_ready_o(recording_channel_ready50)')
        once(native, 'else ready_control<={ready_control[0],client_ready_o};')
        once(native, 'assign control_ready_o=ready_control[1];')
        once(module('workstation_media_memory'),
             'assign client_ready_o=client_reset_no && bist_done && !bist_failed && !transport_fault_o;')
        arbiter = module('workstation_recording_ddr_arbiter_pipeline')
        once(arbiter, 'assign transport_fault_o=response_fault || response_fault_now;')
        once(arbiter, 'if(response_fault_now)response_fault<=1;')
        fault_boundary['record_fault_control_boundary'] = dict(
            policy='native_immediate_quarantine_control_ready_sync2_v1',
            control_sync_stages=2, direct_memory_fault_to_record_ingress=False,
            native_fault_sticky_until_reset=True, source_binding_verified=True,
            mapped_CDC_verified=False, routed_timing_verified=False)
    once(top, "workstation_task3_paired_link #(.ROLE_M(1'b0),.EXPERIMENT_ENABLE(1'b1),.ALLOW_BUSINESS(1'b1)) u_task3_pair_link(")
    for anchor in ('.link_ready_o(task3_pair_link_ready)',
                   '.tx_valid_i(task3_pair_tx_valid)', '.rx_valid_o(task3_pair_rx_valid)',
                   '.clk_i(clk_50m),.reset_ni(reset_n),.link_ready_i(task3_pair_link_ready)',
                   'task3_pair_config_select?task3_pair_config_data:'):
        once(top, anchor)
    selected_batch=providers in ([BATCH_PROVIDER], [BANKED96_PROVIDER])
    selected_phone=providers in ([PHONE_PROVIDER], [BATCH_PROVIDER], [BANKED96_PROVIDER])
    once(top, "localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b" + ('1' if selected_phone else '0') + ";")
    once(top, "localparam bit TASK3_PHONE_BATCH=1'b" + ('1' if selected_batch else '0') + ";")
    batch_parameter=',.PHONE_BATCH(TASK3_PHONE_BATCH)' if selected_batch else ''
    once(top, "workstation_task3_w_bus_endpoint #(.BLOCK_PCM(1'b1),.PHONE_WINDOW_BLOCK(TASK3_PHONE_WINDOW_BLOCK)" + batch_parameter + ") u_task3_bus_endpoint(")
    if selected_batch:
        if enabled.count('rtl/workstation/workstation_task3_phone_batch_w.sv') != 1:
            raise ValueError('W paired batch adapter compilation owner absent/drifted')
        endpoint=module('workstation_task3_w_bus_endpoint')
        once(endpoint, "localparam [31:0] MEDIA_VERSION=PHONE_BATCH ? 32'd3:PHONE_WINDOW_BLOCK ? 32'd2:32'd1;")
        once(endpoint, "localparam [31:0] MEDIA_FEATURES=PHONE_BATCH ? 32'hc0080601:PHONE_WINDOW_BLOCK ? 32'h80080601:32'h00080601;")
        for anchor in ('generate if(PHONE_BATCH)begin:g_phone_batch',
                       'workstation_task3_phone_batch_w batch_w(',
                       '.local_valid_i(mux_valid && !mux_target)',
                       '.live_i(live && hci_classic_ready_i && phone_owner_ready_i && media_current && phone_proxy_armed && !phone_proxy_fault && !phone_window_fault)',
                       '.capability_i(media_current),.token_i(generation_i),.local_boot_i(local_boot_i),.peer_boot_i(peer_boot_i),.session_i(session_i),.generation_i(generation_i)',
                       '.request_valid_o(phone_batch_valid)',
                       '.response_valid_i(rx_valid_i && rx_ready_o && phone_batch_reply)',
                       '.window_busy_i(phone_window_busy),.window_flush_o(phone_window_flush)',
                       'workstation_task3_phone_window_tx #(.EXTERNAL_FLUSH_ENABLE(PHONE_BATCH)) window_tx(',
                       '.flush_i(phone_window_flush)'):
            once(endpoint, anchor)
        module('workstation_task3_phone_batch_w')
    once(top, "workstation_task3_w_paired #(.CNN_USE_DDR_SIGNAL(1'b0),.CNN_USE_DDR_CQT_COEFF(1'b0)) u_task3_media(")
    for anchor in ('gw138k_apb_cdc u_task3_pcm_control(', '.psel(pcm_select)',
                   '.command_valid_i({clock_command_valid,task3_pcm_valid})',
                   '.phone_owner_ready_i(task3_pcm_reset_n && clock_command_reset_n)',
                   '.record_object_idle_i(task3_record_object_idle && raw_start_ready && !raw_fault)',
                   '.record_object_idle_o(task3_record_object_idle)',
                   '.record_source_needed_o(task3_record_source_needed)',
                   '.record_source_needed_i(task3_record_source_needed)',
                   '.record_pcm_o(task3_record_pcm)', '.model_status_i(task3_actual_model_status)',
                   'assign ble_pcm_valid=task3_record_pcm_valid,ble_pcm=task3_record_pcm,ble_sequence=task3_record_sequence;',
                   '.source_allowed_i(task3_record_source_allowed && recording_channel_ready50)',
                   '.ENABLE_AE350_PCM(0)', '.pcm_psel_i(1\'b0)', '.output_mute_i(1\'b1)'):
        once(top, anchor)
    for absent in ('workstation_task3_media_apb_service', 'u_clock_service(',
                   'workstation_task3_w_media u_task3_media', 'recording_owner8(', 'recording_ble_store('):
        if ''.join(absent.split()) in top:
            raise ValueError('W paired retired owner survived: ' + absent)
    for anchor in ('workstation_media_memory #(', ') memory(',
                   'workstation_ble_raw_ddr_store #(', ') raw_store(',
                   'workstation_task3_cnn_stream_w #(', ') cnn_stream('):
        once(native, anchor)
    stream = module('workstation_task3_cnn_stream_w')
    once(stream, ') task_service(')
    once(stream, '.CNN_USE_DDR_SIGNAL(CNN_USE_DDR_SIGNAL)')
    once(stream, '.CNN_USE_DDR_CQT_COEFF(CNN_USE_DDR_CQT_COEFF)')
    task = module('workstation_cnn_task_service')
    pitch = module('basic_pitch_workstation_link')
    for key in ('USE_DDR_SIGNAL', 'USE_DDR_CQT_COEFF'):
        once(native, '.CNN_' + key + '(CNN_' + key + ')')
        once(task, '.' + key + '(CNN_' + key + ')')
        once(pitch, '.' + key + '(' + key + ')')
    for key in ('USE_DDR_FRONT_COEFF', 'USE_EXTERNAL_STATE', 'USE_EXTERNAL_PLANE',
                'USE_EXTERNAL_WEIGHTS', 'USE_EXTERNAL_FEATURES'):
        once(pitch, '.' + key + "(1'b1)")
    once(pitch, ".USE_ALL_DDR(1'b0)")
    expected = dict(WIN_LEN=44100, FRAME_LIMIT=8, OCTAVE_LIMIT=9, CQT_HOP_NUMERATOR=22050,
                    CQT_HOP_DENOMINATOR=4, FEATURE_TILE_COLS=16)
    for key, value in expected.items():
        once(stream, '.CNN_' + key + '(' + str(value) + ')')
        once(task, '.' + key + '(CNN_' + key + ')')
        once(pitch, '.' + key + '(' + key + ')')
        once(pitch, key + '=' + str(value) + ',')
    once(stream, ".CNN_COARSE_GUIDANCE(1'b1)")
    once(task, '.COARSE_GUIDANCE(CNN_COARSE_GUIDANCE)')
    once(pitch, '.COARSE_GUIDANCE(COARSE_GUIDANCE)')
    once(pitch, "COARSE_GUIDANCE=1'b1,")
    once(module('ble_protocol_command'), 'assign record_object_idle_o=record_state==0 && data_engine_idle && !data_mutation_hold;')
    once(module('ble_protocol_command'), 'workstation_task3_record_source_gate paired_record_source(')
    once(module('ble_protocol_command'), '.command_start(paired_record_engine_start)')
    for owner in ('workstation_bluetooth', 'workstation_hci_native_core', 'bt_gatt'):
        body = module(owner)
        once(body, '.record_object_idle_o(record_object_idle_o)')
        once(body, '.record_source_needed_o(record_source_needed_o)')
    core = module('workstation_hci_native_core')
    once(core, ') application (')
    if 'bt_gatt#(' not in core:
        raise ValueError('W paired actual full HCI/GATT application absent')
    once(task, '.USE_FLASH_WEIGHTS(1),.DRAIN_RESTART_ENABLE(1),.BOUNDED_EOF_PADDING(1)')
    return dict(policy=POLICY, normalized_preprocessed_text_sha256=digest(text.replace('\r\n','\n').replace('\r','\n')),
        top_source_identity=top_identity, actual_common_link_and_F808=True,
        actual_HCI_scoped_compilation=hci_scope,
        actual_phone_provider=batch_provider,
        single_memory_fabric=True, single_raw_store=True, single_C_BLE_recording_object=True,
        full_HCI_Classic_GATT=True, remote_PCM1_and_M_clock=True,
        actual_record_object_idle=True, software_injection_enabled=False,
        selected_CNN_memory=cnn_memory_provider(providers[0]), native_CNN_memory_parameters=True,
        selected_CNN_configuration=dict(**expected, COARSE_GUIDANCE=True),
        selected_CNN_configuration_origin='explicit paired native 4Hz defaults and W stream instance parameters',
        selected_CNN_parameter_chain=['W stream explicit geometry', 'task owner parameter forwarding',
                                      'link parameter forwarding', 'actual CNN pipeline'],
        native_default_43844_172_inference_evidence_transferred=False,
        W_local_DAC_is_recording_source=False,
        physical_CDC_accepted=False, hardware_accepted=False, **fault_boundary)


def source_negative_controls(stage, text):
    rows = []
    controls = [
        ('zero-recording-tap', '.record_pcm_o(task3_record_pcm)', '.record_pcm_o(disconnected_pcm)'),
        ('forged-empty-record-object', '.record_object_idle_i(task3_record_object_idle && raw_start_ready && !raw_fault)', ".record_object_idle_i(1'b1)"),
        ('drop-clock-proxy', '.command_valid_i({clock_command_valid,task3_pcm_valid})', ".command_valid_i({1'b0,task3_pcm_valid})"),
        ('fake-model-status', '.model_status_i(task3_actual_model_status)', ".model_status_i(4'd0)"),
        ('wrong-native-CNN-window', '.CNN_WIN_LEN(44100)', '.CNN_WIN_LEN(43844)'),
        ('drop-CNN-task-parameter', '.WIN_LEN(CNN_WIN_LEN)', '.WIN_LEN(43844)'),
        ('drop-CNN-pipeline-parameter', '.WIN_LEN(WIN_LEN)', '.WIN_LEN(43844)'),
        ('missing-native-store', ') raw_store(', ') removed_store(')]
    if media.sha(Path(stage) / BOARD) != '0a58c9de4c8c47ce541918ad0b2b385b61accb7993d54b32eaee2b9a8d264d82':
        controls += [
            ('direct-DDR-fault-bypass',
             '.record_transport_fault_i(!recording_channel_ready50 || raw_channel_fault)',
             '.record_transport_fault_i(!recording_channel_ready50 || raw_channel_fault || task3_memory_transport_fault)'),
            ('single-stage-readiness', 'assign control_ready_o=ready_control[1];',
             'assign control_ready_o=ready_control[0];'),
        ]
    if media.sha(Path(stage) / 'rtl/music/workstation_task3_cnn_stream_w.sv') != 'ba67f7d71b08d3ccf22a766b79bc1fa312d73c219758b45bac046d687eac94b0':
        controls += [
            ('direct-CNN-fault-bypass', '!transport_fault_control[1]', '!transport_fault_i'),
            ('first-stage-CNN-fault-consumer', '!transport_fault_control[1]', '!transport_fault_control[0]'),
            ('delayed-native-CNN-quarantine',
             '.backend_ready_i(backend_ready_i),.transport_fault_i(transport_fault_i)',
             '.backend_ready_i(backend_ready_i),.transport_fault_i(transport_fault_control[1])'),
        ]
    if '.DOMAIN_RESET_RELEASE(1\'b1)' in text:
        controls += [
            ('CNN-domain-reset-disabled', ".DOMAIN_RESET_RELEASE(1'b1)", ".DOMAIN_RESET_RELEASE(1'b0)"),
            ('CNN-first-control-release-consumer', 'wire control_reset_n=control_release[2];', 'wire control_reset_n=control_release[0];'),
            ('CNN-first-native-release-consumer', 'assign native_reset_n=native_release[2];', 'assign native_reset_n=native_release[0];'),
            ('CNN-raw-memory-reset-live', '(DOMAIN_RESET_RELEASE || memory_reset_ni)', 'memory_reset_ni'),
            ('CNN-native-ledger-release-disabled', '.NATIVE_LIFETIME_RESET(DOMAIN_RESET_RELEASE)', ".NATIVE_LIFETIME_RESET(1'b0)"),
            ('CNN-raw-wrapper-reset', '.reset_ni(control_reset_n),.memory_clk_i(memory_clk_i),.memory_reset_ni(memory_reset_ni)',
             '.reset_ni(reset_ni),.memory_clk_i(memory_clk_i),.memory_reset_ni(memory_reset_ni)'),
        ]
    if verify_batch_provider(stage, cnn_provider_from_stage(stage))['phone_batch']:
        controls += [
            ('batch-board-disabled', "localparam bit TASK3_PHONE_BATCH=1'b1;", "localparam bit TASK3_PHONE_BATCH=1'b0;"),
            ('batch-endpoint-disabled', '.PHONE_BATCH(TASK3_PHONE_BATCH)', ".PHONE_BATCH(1'b0)"),
            ('batch-window-disabled', "localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b1;", "localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b0;"),
            ('batch-version-downgraded', "MEDIA_VERSION=PHONE_BATCH ? 32'd3:", "MEDIA_VERSION=PHONE_BATCH ? 32'd2:"),
            ('batch-features-downgraded', "MEDIA_FEATURES=PHONE_BATCH ? 32'hc0080601:", "MEDIA_FEATURES=PHONE_BATCH ? 32'h80080601:"),
            ('batch-clock-lane-captured', '.local_valid_i(mux_valid && !mux_target)', '.local_valid_i(mux_valid)'),
            ('batch-flush-disabled', '.EXTERNAL_FLUSH_ENABLE(PHONE_BATCH)', ".EXTERNAL_FLUSH_ENABLE(1'b0)"),
            ('batch-response-unconsumed', '.response_valid_i(rx_valid_i && rx_ready_o && phone_batch_reply)', '.response_valid_i(rx_valid_i && phone_batch_reply)'),
            ('batch-identity-truncated', '.peer_boot_i(peer_boot_i),.session_i(session_i),.generation_i(generation_i)', '.peer_boot_i(peer_boot_i),.session_i(session_i),.generation_i(0)'),
        ]
    for name, before, after in controls:
        scope = text
        if name == 'drop-CNN-pipeline-parameter':
            modules = re.findall(r'\bmodule\s+basic_pitch_workstation_link\b.*?\bendmodule\b', text, re.S)
            if len(modules) != 1:
                raise ValueError('W paired negative module owner drift: ' + name)
            scope = modules[0]
        if scope.count(before) != 1:
            raise ValueError('W paired negative anchor drift: ' + name)
        mutated = text.replace(scope, scope.replace(before, after, 1), 1)
        try:
            selected_source_evidence(stage, mutated)
        except ValueError as error:
            rows.append(dict(name=name, rejected=True, error=str(error)))
        else:
            raise ValueError('W paired unsafe mutation survived: ' + name)
    return rows


def cnn_provider_from_stage(stage):
    from xml.etree import ElementTree as ET
    providers = [row.get('path') for row in ET.parse(Path(stage) / 'Prj1.gprj').find('FileList')
                 if row.get('enable') == '1' and row.get('path', '').startswith('rtl/workstation/workstation_profile_')]
    if len(providers) != 1 or providers[0] not in (PROVIDER, PHONE_PROVIDER, BATCH_PROVIDER, BANKED96_PROVIDER):
        raise ValueError('W paired actual provider must be unique')
    return providers[0]
