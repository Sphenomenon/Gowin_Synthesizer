"""Explicit direct-TF source/CDC selection; never a production promotion.

Replace the locked legacy TF bundle and explicit root-reset mapping. Retain
the FIFO/Gray bounds. New held mailboxes have directional setup bounds;
only their asynchronous first receivers and held-payload hold paths are cut.
Synthesis endpoint resolution and physical CDC acceptance remain separate.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET

POLICY = 'task3_m_native_direct_tf_v1'
STORAGE_POLICY = 'direct_sd_crc16_validated_fat_cache_v1'
SDC_REVISION = 3
TOOL = 'tools/workstation_task3_tf_direct.py'
LEGACY = 'boards/custom_138k/task3_tf_direct_legacy_cdc_v1.json'
LEGACY_SHA256 = '5766ce220bae56e2d7d6db787250b94e879cb53af04a982092a05adfc9658bfd'
SOURCES = tuple('rtl/tf_audio/' + path for path in (
    'workstation_tf_direct_runtime_service.sv', 'workstation_tf_direct_native_v1.sv',
    'workstation_tf_direct_ingress_v1.sv', 'workstation_tf_frame_bridge_v2.sv',
    'workstation_tf_physical_tail_v1.sv', 'storage/workstation_tf_file_reader.sv',
    'storage/workstation_tf_sd_sector_reader.sv', 'storage/workstation_tf_spi_session.sv',
    'storage/workstation_tf_sd_crc16_v1.sv', 'storage/workstation_tf_fat_sector_cache_v1.sv',
    'storage/workstation_tf_wav_pcm_decoder_v1.sv', 'storage/workstation_tf_wav_chunk_parser_v1.sv'))
RETIRED_SOURCES = (
    'rtl/tf_audio/workstation_tf_frame_bridge.sv',
    'rtl/tf_audio/workstation_tf_runtime_service.sv',
    'rtl/tf_audio/workstation_tf_runtime_byte_fifo.sv',
    'rtl/tf_audio/workstation_tf_runtime_dma.sv',
    'rtl/tf_audio/storage/tf_audio_ddr_path.v')
UNSELECTED_WORKER_SOURCES = ('rtl/music/workstation_cnn_ddr_broker.sv',
                             'rtl/music/workstation_cnn_task_service.sv')
DEPENDENCIES = (TOOL, LEGACY,
    'tools/workstation_task3_tf_storage_selection.py',
    'tools/workstation_task3_tf_analysis_provenance.py',
    'rtl/tf_audio/workstation_tf_remote_analysis_v1.adaptation.json',
    'rtl/workstation/workstation_task3_tf_storage_top_reference.json',
    'tools/workstation_tf_sd_crc16_provenance.py',
    'tools/workstation_tf_fat_cache_provenance.py',
    'rtl/tf_audio/storage/workstation_tf_sd_crc16_v1.adaptation.json',
    'rtl/tf_audio/storage/workstation_tf_fat_sector_cache_v1.adaptation.json',
    'rtl/tf_audio/storage/WORKSTATION_TF_SD_CRC16_V1_CONTRACT.md',
    'rtl/tf_audio/storage/WORKSTATION_TF_FAT_SECTOR_CACHE_V1_CONTRACT.md',
    'rtl/tf_audio/storage/workstation_tf_sd_sector_reader.provenance.json',
    'rtl/tf_audio/storage/workstation_tf_file_reader.provenance.json',
    'rtl/tf_audio/storage/tang_mp3/vendor/tf_sd_spi_sector_reader.v',
    'rtl/tf_audio/storage/tang_mp3/vendor/tf_spi_session.v',
    'rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v',
    'tools/workstation_task3_root_reset_audit.py',
    'tools/workstation_task3_native_held.py',
    'tools/workstation_task3_peripheral_releases_audit.py',
    'tools/workstation_task3_tf_startup_audit.py',
    'tools/workstation_task3_receipt_audit.py',
    'tools/workstation_task3_tf_sdc_audit.py',
    'tools/workstation_task3_clock_release_audit.py',
    'tools/workstation_task3_tf_frame_cdc_audit.py',
    'tools/workstation_task3_tf_tail_cdc_audit.py',
    'tools/workstation_task3_tf_tail_retirement_audit.py',
    'tools/workstation_task3_w_media_profile.py',
    'rtl/workstation/workstation_task3_w_media_top_reference.json',
    *tuple('rtl/tf_audio/' + name for name in (
    'WORKSTATION_TF_DIRECT_NATIVE_V1_CONTRACT.md',
    'WORKSTATION_TF_DIRECT_INGRESS_V1_CONTRACT.md',
    'WORKSTATION_TF_FRAME_BRIDGE_V2_CONTRACT.md',
    'WORKSTATION_TF_PHYSICAL_TAIL_V1_CONTRACT.md')))


def root_constraint_mappings():
    """Exact mapping seen in the real-root Gowin synthesis, never a glob waiver.

    Equal clock/reset release flops coalesce across mailboxes. The dedicated
    direct native audit must prove the actual chains and consumers. Existing
    profiles retain their original names and reset primitive policy.
    """
    rows = []
    old = 'set_false_path -to [get_pins {u_runtime/u_cpu_cdc/source_release*/CLEAR u_runtime/u_cpu_cdc/destination_release*/CLEAR}]'
    rows.append((old, old.replace('u_runtime/u_cpu_cdc/source_release*/CLEAR',
                                'u_managed/control_cdc/p_release*/CLEAR')))
    for scope, stem in (('u_managed', 'startup_compute'),
                        ('u_managed/runtime', 'startup_compute'),
                        ('u_managed/runtime', 'startup_memory'),
                        ('u_managed/runtime', 'startup_serial'),
                        ('', 'output_safe_sync'),
                        ('u_runtime', 'g_usb_cdc_reset.usb_ready')):
        target = (scope + '/' if scope else '') + stem + '_0_s*/'
        rows.append(('set_false_path -to [get_pins {' + target + 'RESET}]',
                     'set_false_path -to [get_pins {' + target + 'CLEAR}]'))
    from tools.workstation_performance_reset import proposed_constraints
    for old in proposed_constraints().splitlines():
        selected = old.replace('u_runtime/u_performance_cdc/source_release_',
                               'u_tf_control_cdc/source_release_').replace(
                                   'u_runtime/u_performance_cdc/destination_release_',
                                   'u_tf_control_cdc/destination_release_')
        rows.append((old, selected))
    return tuple(rows)


def paired_release_constraint_mappings():
    """Four separately proved M paired synthesis aliases; DIRECT r3 is unchanged.

    Apply only in the paired stage adapter, after DIRECT r3 reconstruction.
    All selected pins remain release-shift FF CLEARs, never functional state.
    """
    return (
        ('u_managed/control_cdc/p_release*/CLEAR',
         'u_task3_pair_link/config_cdc/p_release_*_s*/CLEAR'),
        ('u_runtime/u_cpu_cdc/destination_release*/CLEAR',
         'u_task3_pair_link/config_cdc/a_release_*_s*/CLEAR'),
        ('u_managed/runtime/g_direct_tf.transport_health_mailbox/source_release_*_s*/CLEAR',
         'u_task3_m_final_tap/source_release_*_s*/CLEAR'),
        ('u_managed/midi_bytes/destination_release_*_s*/CLEAR',
         'u_task3_m_pcm_commands/a_release_*_s*/CLEAR'),
    )


def adapt_paired_release_constraints(sdc):
    selected = sdc
    for before, after in paired_release_constraint_mappings():
        if selected.count(before) != 1 or after in selected:
            raise ValueError('M paired release constraint exact anchor drift: ' + before)
        selected = selected.replace(before, after, 1)
    return selected, dict(policy='task3_m_paired_real_release_aliases_v1',
        input_sha256=digest(sdc), output_sha256=digest(selected),
        mappings=[dict(before=a, after=b) for a, b in paired_release_constraint_mappings()],
        actual_alias_and_consumer_proof_required=True, added_exceptions=0,
        physical_recovery_removal_verified=False)


def restore_paired_release_constraints(sdc, evidence):
    restored = sdc
    for before, after in reversed(paired_release_constraint_mappings()):
        if restored.count(after) != 1 or before in restored:
            raise ValueError('M paired release constraint inverse anchor drift: ' + after)
        restored = restored.replace(after, before, 1)
    selected, expected = adapt_paired_release_constraints(restored)
    if selected != sdc or evidence != expected:
        raise ValueError('M paired release constraint reconstruction evidence drift')
    return restored


def root_display_retired_constraints():
    # The real-root candidate retains an actual held FF for every display bit;
    # observation RAM no longer directly drives these destination D pins.
    # The native direct audit requires that exact 230-bit FF correspondence.
    source = 'u_managed/observation/frames/*g_small_head.memory_g_small_head.memory_0_*_s/DO*'
    sinks = ' '.join(f'u_managed/display/destination_data_{bit}_s*/D' for bit in range(105, 203))
    path = '-from [get_pins {' + source + '}] -to [get_pins {' + sinks + '}]'
    return ('set_max_delay 20.000 ' + path, 'set_false_path -hold ' + path)


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def selected_direct_top(stage, text):
    """Select only DIRECT conditionals for a registered compilation provider.

    Other preprocessor branches remain for their existing strict validators.
    The real compiler still consumes the unmodified, fully hashed source.
    """
    stage=Path(stage)
    from tools.workstation_task3_tf_storage_selection import inverse_top as inverse_storage_top
    from tools.workstation_task3_w_media_profile import inverse_top
    text=inverse_top(stage,inverse_storage_top(stage,text))
    project=stage/'Prj1.gprj'
    selected=[row.get('path') for row in ET.parse(project).find('FileList') if row.get('enable')=='1'] if project.is_file() else []
    from tools.workstation_profile import PROFILE_REGISTRY
    providers={spec['provider'] for spec in PROFILE_REGISTRY.values() if spec.get('tf_direct_enabled',False)}
    actual=providers.intersection(selected)
    if len(actual)>1:raise ValueError('direct TF provider is not uniquely selected')
    direct_enabled=bool(actual)
    provider=next(iter(actual)) if direct_enabled else None
    if direct_enabled and any(spec['provider'] in selected and spec['provider']!=provider
            for spec in PROFILE_REGISTRY.values()):
        raise ValueError('direct TF cannot select another registered profile provider')
    if 'WORKSTATION_TF_DIRECT_NATIVE' not in text:
        if direct_enabled:raise ValueError('direct TF top branch missing')
        return text, False
    source=(stage/provider).read_text().splitlines() if direct_enabled else []
    if direct_enabled and (source.count('`define WORKSTATION_TF_DIRECT_NATIVE')!=1 or
            source.count('`define WORKSTATION_NO_CNN')!=1 or
            '`define WORKSTATION_DEMO_NO_TF' in source):
        raise ValueError('direct TF provider reset selection drift')
    if direct_enabled and set(selected).intersection(UNSELECTED_WORKER_SOURCES):
        raise ValueError('direct M cannot compile unselected W CNN task inputs')
    stack=[];output=[]
    for row in text.splitlines(keepends=True):
        token=re.match(r'\s*`(ifdef|ifndef|else|elsif|endif)\b(?:\s+(\w+))?',row)
        active=all(item[1] for item in stack if item[0])
        if token and token[1] in ('ifdef','ifndef'):
            direct=token[2]=='WORKSTATION_TF_DIRECT_NATIVE'
            if active and not direct:output.append(row)
            stack.append([direct,(direct_enabled if token[1]=='ifdef' else not direct_enabled) if direct else True])
        elif token and token[1]=='else':
            if not stack:raise ValueError('direct TF unbalanced preprocessor else')
            if stack[-1][0]:stack[-1][1]=not stack[-1][1]
            elif active:output.append(row)
        elif token and token[1]=='endif':
            if not stack:raise ValueError('direct TF unbalanced preprocessor endif')
            direct=stack[-1][0];stack.pop()
            if not direct and active:output.append(row)
        elif token and token[1]=='elsif' and stack and stack[-1][0]:
            raise ValueError('direct TF unsupported conditional selector')
        elif active:output.append(row)
    if stack:raise ValueError('direct TF unclosed preprocessor conditional')
    result=''.join(output)
    if direct_enabled and result.count('wire runtime_common_reset_n=reset_n;')!=1:
        raise ValueError('direct TF requires real root startup reset')
    return result, direct_enabled


def legacy(root):
    payload = (Path(root) / LEGACY).read_bytes()
    if digest(payload) != LEGACY_SHA256:
        raise ValueError('direct TF legacy CDC identity changed')
    record = json.loads(payload)
    if (record['schema'] != 1 or record['policy'] != 'task3_direct_tf_replaces_legacy_cdc_v1'
            or len(record['lines']) != 63 or record['retained_fifo_gray_lines'] != 8
            or digest(''.join(record['lines'])) != record['subset_sha256']):
        raise ValueError('direct TF legacy CDC inventory changed')
    return record


def new_constraints(*, revision=3):
    if revision not in (1, 2, 3):
        raise ValueError('unsupported direct TF constraint revision')
    lines = []

    def path(source, destination):
        return '-from [get_pins {' + source + '}] -to [get_pins {' + destination + '}]'

    def held(source, destination, budget):
        query = path(source, destination)
        lines.extend((f'set_max_delay {budget:.3f} ' + query, 'set_false_path -hold ' + query))

    def level(source, scope, first, second):
        # Do not let producer foo_s* also match foo_sync_* receivers.
        suffix = '_s[0-9]*/Q' if revision >= 2 else '_s*/Q'
        lines.extend(('set_false_path ' + path(source + suffix, scope + '/' + first + '_s*/D'),
                      'set_max_delay 2.000 ' + path(scope + '/' + first + '_s*/Q', scope + '/' + second + '_s*/D')))

    tf = 'u_tf_audio'
    bridge = tf + '/frames'
    runtime = 'u_managed/runtime'
    generated = runtime + '/g_direct_tf.'
    tail = generated + 'tail'
    held(tf + '/held_status_*_s*/Q', tf + '/compute_status_*_s*/D', 13.020)
    # The real-root revision captures the complete held reply before local
    # business processing. Legacy candidates preserve their original bundle
    # and are recorded as rejected until that complete remote cone is bounded.
    receipt_sinks = (tf + '/receipt_local_*_s*/D' if revision >= 2 else
        ' '.join(tf + '/' + stem + '_s*/D' for stem in (
            'state_*', 'failed', 'pending_start',
            'session_applied', 'quiet_wait_*', 'native_quiet', 'stop_pending_o',
            'stop_done_o', 'stop_failed_o', 'stop_failure_code_o_*')))
    held(tf + '/receipt_payload_*_s*/Q', receipt_sinks, 20.000)
    for name, source in (('status_request', tf + '/status_request'),
                         ('status_ack', tf + '/status_ack'),
                         ('receipt_request', tf + '/receipt_request'),
                         ('receipt_ack', tf + '/receipt_ack')):
        if revision >= 2 and name == 'receipt_ack':
            source = tf + '/receipt_seen'
        level(source, tf, name + '_sync_0', name + '_sync_1')
    level(generated + 'quiet_published', tf, 'physical_quiet_sync_0', 'physical_quiet_sync_1')
    for name, source in (('source_alive', bridge + '/source_seen_edge'),
                         ('expected_valid', bridge + '/expected_generation_valid_o'),
                         ('quiesce', tf + '/source_quiesce_level'),
                         ('quiet', bridge + '/quiet_published'),
                         ('quiesce_return', bridge + '/quiesce_sync_1')):
        if revision >= 2 and name == 'source_alive':
            # source_seen_edge is exactly the first root-released clk50 edge;
            # Gowin coalesces it with the PLL enable shift register's first FF.
            source = 'u_usb_pll/u_pll_init/enable_r_0'
        level(source, bridge, name + '_sync_0', name + '_sync_1')
    for first, second in (('generation_meta', 'generation_sync'), ('ack_meta', 'ack_sync')):
        lines.append('set_max_delay 2.000 ' + path(bridge + '/' + first + '_*_s*/Q', bridge + '/' + second + '_*_s*/D'))
    for first, second in (('write_gray_meta', 'write_gray_sync'), ('read_gray_meta', 'read_gray_sync')):
        lines.append('set_max_delay 2.000 ' + path(bridge + '/frames_0/' + first + '_*_s*/Q', bridge + '/frames_0/' + second + '_*_s*/D'))
    held(tail + '/held_request_*_s*/Q', tail + '/serial_token_*_s*/D', 20.000)
    # The reply remains immutable until the returned request; there is no
    # combinational acknowledgement. Bound only actual compute reply consumers.
    sinks = ('arm_pending', 'armed_o', 'baseline_drops_o_*', 'failed_o',
             'failure_code_o_*', 'tail_drops_o_*', 'tail_receipted')
    if revision >= 2:
        # These diagnostic outputs have no top-level consumers. Do not retain
        # phantom endpoints; all functional reply-dependent state stays bounded.
        sinks = tuple(stem for stem in sinks if stem not in ('failure_code_o_*', 'tail_drops_o_*'))
    if revision >= 3:
        # Real v11/v13 consumer closure: 32 data plus 36 enables. The four
        # scalar D pins in r2 do not consume held_reply; keep every real CE.
        reply_sinks = ' '.join([tail + '/baseline_drops_o_*_s*/D',
            tail + '/baseline_drops_o_*_s*/CE',
            *(tail + '/' + stem + '_s*/CE' for stem in
              ('arm_pending', 'armed_o', 'failed_o', 'tail_receipted'))])
    else:
        reply_sinks = ' '.join(tail + '/' + stem + '_s*/D' for stem in sinks)
    held(tail + '/held_reply_*_s*/Q', reply_sinks, 13.020)
    if revision >= 3:
        # These are finite data bounds, with ordinary hold checks retained.
        # Physical RAM vector-pin/arc resolution and FIFO ownership are still
        # explicit acceptance gates; lexical resolution is not STA evidence.
        ram = bridge + '/frames_0/g_small_head.memory_g_small_head.memory_0_*_s'
        captures = ' '.join(bridge + '/' + stem + '_s*/' + pin
            for stem in ('held_packet_*', 'held_valid') for pin in ('D', 'CE'))
        lines.append('set_max_delay 13.020 ' + path(ram + '/DO', captures))
        read_address = ' '.join(bridge + '/frames_0/read_binary_' + str(bit) + '_s*/Q'
                                for bit in range(4))
        lines.append('set_max_delay 13.020 ' + path(read_address, ram + '/RAD'))
    level(tail + '/request_toggle', tail, 'request_sync_0', 'request_sync_1')
    level(tail + '/reply_toggle', tail, 'reply_sync_0', 'reply_sync_1')
    held(tail + '/fence_gray_*_s*/Q', tail + '/fence_meta_*_s*/D', 13.020)
    lines.append('set_max_delay 2.000 ' + path(tail + '/fence_meta_*_s*/Q', tail + '/fence_sync_*_s*/D'))
    level(runtime + '/serializer/serial_quiescent_o', runtime, 'g_direct_tf.serial_quiet_compute_0', 'g_direct_tf.serial_quiet_compute_1')
    mailbox = generated + 'transport_health_mailbox'
    held(mailbox + '/held_data_*_s*/Q', mailbox + '/destination_data_*_s*/D', 13.020)
    level(mailbox + '/request_toggle', mailbox, 'req_meta', 'req_sync')
    level(mailbox + '/acknowledge_toggle', mailbox, 'ack_meta', 'ack_sync')
    # Only reset-release shift-register CLEAR pins, never native file/DSP state.
    releases = ' '.join(scope + '/' + name + '_*_s*/CLEAR' for scope in (tf, bridge)
                        for name in ('source_release', 'compute_release'))
    releases += ' ' + mailbox + '/source_release_*_s*/CLEAR'
    releases += ' ' + (mailbox + '/destination_release_*_s*/CLEAR' if revision == 1 else
                       'u_managed/midi_bytes/destination_release_*_s*/CLEAR')
    lines.append('set_false_path -to [get_pins {' + releases + '}]')
    lines.append('set_max_delay 2.000 ' + path(tf + '/startup_source_0_s*/Q', tf + '/startup_source_1_s*/D'))
    lines.append('set_false_path -to [get_pins {' + tf + '/startup_compute_0_s*/D}]')
    lines.append('set_max_delay 2.000 ' + path(tf + '/startup_compute_0_s*/Q', tf + '/startup_compute_1_s*/D'))
    return ''.join(line + '\n' for line in lines)


def adapt_constraints(root, sdc, *, revision=3):
    record = legacy(root)
    old = record['lines']
    actual = [row for row in sdc.splitlines(keepends=True) if 'u_tf_audio/' in row]
    if actual != old:
        raise ValueError('direct TF requires the exact complete legacy TF CDC subset')
    selected = sdc
    retired = list(old)
    if revision >= 2:
        for before, after in root_constraint_mappings():
            if selected.splitlines().count(before) != 1:
                raise ValueError('direct TF root constraint anchor changed: ' + before)
            selected = selected.replace(before + '\n', after + '\n')
        for row in root_display_retired_constraints():
            if selected.splitlines().count(row) != 1:
                raise ValueError('direct TF old display RAM constraint anchor changed: ' + row)
            retired.append(row + '\n')
    selected = ''.join(row for row in selected.splitlines(keepends=True) if row not in retired)
    added = ''.join(old[:8]) + new_constraints(revision=revision)
    selected += added
    evidence = dict(policy=POLICY, input_sha256=digest(sdc), output_sha256=digest(selected),
        legacy_manifest=LEGACY, legacy_manifest_sha256=LEGACY_SHA256,
        retired=[dict(line=row, line_number=index + 1) for index, row in enumerate(sdc.splitlines(keepends=True)) if row in retired],
        added=added, added_sha256=digest(added), retained_fifo_gray_lines=8,
        non_tf_constraints_unchanged=revision == 1, synthesis_queries_verified=False, physical_cdc_verified=False)
    if revision >= 2:
        evidence.update(constraint_revision=revision,
            root_reset_mappings=[dict(before=before, after=after) for before, after in root_constraint_mappings()],
            display_RAM_direct_capture_retired=list(root_display_retired_constraints()),
            actual_alias_and_consumer_proof_required=True,
            legacy_synthesis_candidate='custom138k-workstation-task3-m-direct-tf-v1-552092038e6c90e3')
    return selected, evidence


def restore_constraints(root, sdc, evidence):
    added = evidence.get('added', '')
    if not added or not sdc.endswith(added):
        raise ValueError('direct TF CDC installation changed')
    original = sdc[:-len(added)].splitlines(keepends=True)
    for row in evidence.get('retired', []):
        index = row['line_number'] - 1
        if index < 0 or index > len(original):
            raise ValueError('direct TF CDC retirement position changed')
        original.insert(index, row['line'])
    restored = ''.join(original)
    revision = evidence.get('constraint_revision', 1)
    if revision >= 2:
        for before, after in root_constraint_mappings():
            if restored.splitlines().count(after) != 1:
                raise ValueError('direct TF root constraint mapping changed: ' + after)
            restored = restored.replace(after + '\n', before + '\n')
    selected, expected = adapt_constraints(root, restored, revision=revision)
    if selected != sdc or expected != evidence:
        raise ValueError('direct TF CDC evidence changed')
    return restored
