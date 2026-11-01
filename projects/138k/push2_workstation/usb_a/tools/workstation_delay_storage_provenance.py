"""Exact prepared/native lineage for explicit runtime delay FIFO storage."""
from pathlib import Path
import hashlib
import json

STRICT_POLICY = 'locked_native_v1'
STORAGE_POLICY = 'native_delay_fifo_block_ram_v1'
SOURCE = 'rtl/audio/workstation_runtime_stereo_effects.sv'
PROVENANCE = 'rtl/audio/workstation_runtime_stereo_effects.provenance.json'
ADAPTATION = 'rtl/audio/workstation_runtime_stereo_effects.delay_fifo_storage.json'
PROVENANCE_SHA256 = '5af689e1adc920524e83d0ae9da87382a75a6bc2868c08fc246abb47814df68c'
ADAPTATION_SHA256 = '5590b0082117f53247f5d30236d5547ac2f358ee66e7b874c3ce6199ec13fe51'
FIFO = 'rtl/music/music_async_fifo.sv'
FIFO_SHA256 = 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792'
REFERENCE = 'rtl/workstation/gw138k_push_workstation_top.v'
# The reviewed native RTC/PCM, ROM and business observation composition changes
# this maintained reference. Original effects provenance/adaptation bytes and
# both non-runtime FIFO selectors remain locked; no effects lineage is rebased.
# W21 adds only explicit audio-only composition branches; the two legacy
# non-runtime selectors and all effects provenance remain byte-identical.
REFERENCE_SHA256 = '2c4376b7754a9b98486501fb91e258f5b70b4183b4ec5f687b2a588132ba7007'
TF_MENU_REFERENCE_SHA256 = 'dfe698e7bcde7c47c9263224a6615e5269e19b0e1509cda709420f626df94e0d'
DIRECT_REFERENCE = 'rtl/workstation/workstation_task3_direct_reference.json'
DIRECT_REFERENCE_SHA256 = '8e88000687825c6a6894378546febe1d4d3d6b281ea405363132b06b21c17879'
DIRECT_TOP_SHA256 = '2bd14a9c81c28817dc0fd2bf39a87d208f0344f7f1c8f06571953bc2550f3cd0'
# Optional TF menu selection is unrelated to the two non-runtime storage
# defparams. Reverse only its exact two insertions; retain the original lock.
TF_MENU_REFERENCE_INSERTIONS = (
    "`ifdef WORKSTATION_TF_MENU_WITHOUT_CNN\n"
    "`ifndef WORKSTATION_DEMO_NO_TF\n"
    "    gw138k_stream_cdc #(.WIDTH(4)) u_song_command_cdc(\n"
    "        .reset_n(reset_n && usb_reset_n),.source_clk(usb_clk),.destination_clk(clk_50m),\n"
    "        .source_valid(push_track_launch),.source_data(push_track_index),.drop_count(),\n"
    "        .destination_valid(song_cmd_valid),.destination_data(song_cmd_index));\n"
    "`else\n"
    "    assign song_cmd_valid=1'b0;\n"
    "    assign song_cmd_index=4'd0;\n"
    "`endif\n"
    "`else\n",
    "`ifdef WORKSTATION_TF_MENU_WITHOUT_CNN\n"
    "`ifndef WORKSTATION_DEMO_NO_TF\n"
    "        ,.TF_MENU_ENABLE(1'b1)\n"
    "`endif\n"
    "`endif\n",
)
PREPARED_SOURCE = 'rtl/audio/stereo_effects.sv'

# Current scratch data is written in state2 before every state3 consumer.
# Keep the historical native/provenance chain byte-for-byte and reverse only
# this identity-bound reset removal before applying that original chain.
DELAY_SCRATCH_SOURCE_SHA256 = 'cf43513f998e182075e8c6dd61de20dfd1872c8570c88baa0dfb67955650b1fd'
DELAY_SCRATCH_PARENT_SHA256 = '879a5d93fb3ee547cd517344a495452f7cb37f28c0605ceee2cb625f2126c62d'
DELAY_SCRATCH_EDITS = (("      else begin read_l<=32'sd0;read_r<=32'sd0;end\n    end\n  end\n\n",
  "      else begin read_l<=32'sd0;read_r<=32'sd0;end\n"
  '    end\n'
  '    // State3 consumes only the products written by the preceding state2.\n'
  '    // Control reset/clear invalidates that state, not these private DSP values.\n'
  '    if(!local_history_clear && state==2) begin\n'
  "      product_l<=$signed(frames>=echo_samples?read_l:32'sd0)*$signed({1'b0,gain});\n"
  "      product_r<=$signed(frames>=echo_samples?read_r:32'sd0)*$signed({1'b0,gain});\n"
  '    end\n'
  '  end\n'
  '\n'),
 ('      frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;\n'
  '      input_l<=0;input_r<=0;feedback_l<=0;feedback_r<=0;\n'
  '      '
  'product_l<=0;product_r<=0;feedback_wide_l<=0;feedback_wide_r<=0;mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;\n'
  '    end else begin\n'
  '      valid_o<=0;clip_o<=0;\n',
  '      frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;\n'
  '      input_l<=0;input_r<=0;feedback_l<=0;feedback_r<=0;\n'
  '      feedback_wide_l<=0;feedback_wide_r<=0;mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;\n'
  '    end else begin\n'
  '      valid_o<=0;clip_o<=0;\n'),
 ('        1:state<=2;\n'
  '        2:begin\n'
  "          product_l<=$signed(frames>=echo_samples?read_l:32'sd0)*$signed({1'b0,gain});\n"
  "          product_r<=$signed(frames>=echo_samples?read_r:32'sd0)*$signed({1'b0,gain});\n"
  "          feedback_wide_l<=$signed(input_l)+rshift($signed(frames>=echo_samples?read_l:32'sd0),1);\n"
  '          '
  "feedback_wide_r<=$signed(input_r)+rshift($signed(frames>=echo_samples?read_r:32'sd0),1);state<=3;\n",
  '        1:state<=2;\n'
  '        2:begin\n'
  "          feedback_wide_l<=$signed(input_l)+rshift($signed(frames>=echo_samples?read_l:32'sd0),1);\n"
  '          '
  "feedback_wide_r<=$signed(input_r)+rshift($signed(frames>=echo_samples?read_r:32'sd0),1);state<=3;\n"))

DELAY_SCRATCH_SOURCE = 'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv'
DELAY_SCRATCH_PROVENANCE = 'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.provenance.json'
DELAY_SCRATCH_PROVENANCE_SHA256 = 'e19a665b94b99b65616c470ca8b4ad9b3de826f6d329b7da51ce66bf01016886'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


REMOTE_REVERB_ADAPTATION = 'rtl/audio/workstation_runtime_stereo_effects.remote_reverb_partition.json'
REMOTE_REVERB_ADAPTATION_SHA256 = '20345a57c4000cacabad2daf89c6c70592cda77699fc0cd3c44cf0b021c2830f'
REMOTE_REVERB_SOURCE_SHA256 = '50d18332d820f8bc11f272726b6ed51190cd3ec4acde666c9ef4d0c511ab4e13'
REMOTE_REVERB_PARENT_SHA256 = '99095afee6425a42fab993575a09f6e1c6b8beb05619b9b46fc0a311bdcdc2c9'


def restore_remote_reverb_partition(source, adaptation=None):
    """Undo only the opt-in partition; the original effects lineage stays locked."""
    if sha(source) != REMOTE_REVERB_SOURCE_SHA256:
        # Historical inputs continue through their original strict checks.
        return source
    if adaptation is None:
        adaptation = (Path(__file__).resolve().parents[1] / REMOTE_REVERB_ADAPTATION).read_bytes()
    if sha(adaptation) != REMOTE_REVERB_ADAPTATION_SHA256:
        raise ValueError('Remote Reverb partition adaptation bytes changed')
    bridge = json.loads(adaptation)
    if (bridge['schema'] != 1 or bridge['policy'] != 'explicit_remote_reverb_partition_v1' or
            bridge['source'] != SOURCE or bridge['macro'] != 'WORKSTATION_REMOTE_REVERB_PARTITION' or
            bridge['parent_source_sha256'] != REMOTE_REVERB_PARENT_SHA256 or
            bridge['current_source_sha256'] != sha(source) or
            bridge['default_macro_off'] is not True or len(bridge['exact_changes']) != 3):
        raise ValueError('Remote Reverb partition identity changed')
    current = source.decode()
    for edit in reversed(bridge['exact_changes']):
        if edit['count'] != 1 or not edit['after'] or current.count(edit['after']) != 1:
            raise ValueError('Remote Reverb partition reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
    restored = current.encode()
    if sha(restored) != REMOTE_REVERB_PARENT_SHA256:
        raise ValueError('Remote Reverb partition parent identity changed')
    for edit in bridge['exact_changes']:
        if not edit['before'] or current.count(edit['before']) != 1:
            raise ValueError('Remote Reverb partition forward anchor drift')
        current = current.replace(edit['before'], edit['after'])
    if current.encode() != source:
        raise ValueError('Remote Reverb partition round trip changed bytes')
    return restored


# W momentary effects stop mixing a released stage immediately. The default
# retains the existing M tail selection; maintenance/history logic is unchanged.
# Reverse only the two reviewed bytes before the unchanged slot/D/storage chain.
EFFECT_RELEASE_SOURCE_SHA256 = '99095afee6425a42fab993575a09f6e1c6b8beb05619b9b46fc0a311bdcdc2c9'
EFFECT_RELEASE_PARENT_SHA256 = 'e93558569813b97ca10caf31a44496e6dc232e752434a9f94bbd64fb7fe71c50'
EFFECT_RELEASE_EDITS = (('    parameter bit D_DELAY_SEND_ENABLE=0,\n', '    parameter bit D_DELAY_SEND_ENABLE=0,\n    parameter bit RELEASE_TAILS_ENABLE=1,\n'), ('selected_id<3&&(frame_mask[selected_id]||selected_active)&&!processed[selected_id]', 'selected_id<3&&(frame_mask[selected_id]||(RELEASE_TAILS_ENABLE&&selected_active))&&!processed[selected_id]'))


def restore_effect_release_policy(source):
    """Reverse only the hash-bound opt-in D release policy and check round trip."""
    if sha(source) != EFFECT_RELEASE_SOURCE_SHA256:
        return source
    current = source.decode()
    for before, after in reversed(EFFECT_RELEASE_EDITS):
        if current.count(after) != 1:
            raise ValueError('Effects release policy reverse anchor drift')
        current = current.replace(after, before)
    restored = current.encode()
    if sha(restored) != EFFECT_RELEASE_PARENT_SHA256:
        raise ValueError('Effects release policy parent identity changed')
    for before, after in EFFECT_RELEASE_EDITS:
        if current.count(before) != 1:
            raise ValueError('Effects release policy forward anchor drift')
        current = current.replace(before, after)
    if current.encode() != source:
        raise ValueError('Effects release policy round trip changed bytes')
    return restored


# Read-only stored-slot observation added after the reviewed D-control source.
# Undo only these hash-bound bytes before the unchanged D/storage/provenance
# chain; neither the original manifests nor the D adaptations are rebased.
EFFECT_SLOT_SOURCE_SHA256 = 'e93558569813b97ca10caf31a44496e6dc232e752434a9f94bbd64fb7fe71c50'
EFFECT_SLOT_PARENT_SHA256 = '7bd9a9f547f82bb30f9f015610f9ac448c1ae374fe87366e1d37d52f2093b826'
EFFECT_SLOT_EDITS = (
    ('    output logic ready_o,valid_o,\n',
     '    output logic ready_o,valid_o,\n'
     '    // Stored slot state only. The owning sample scheduler must separately\n'
     '    // veto fault, clear and accepted configuration/history transactions.\n'
     '    output wire sample_slot_ready_o,\n'),
    ('  assign ready_o=state==IDLE && !barrier_busy && !fault_o && !clear_i && !config_accept && !history_accept;\n',
     '  assign sample_slot_ready_o=state==IDLE && !barrier_busy;\n'
     '  assign ready_o=state==IDLE && !barrier_busy && !fault_o && !clear_i && !config_accept && !history_accept;\n'),
)


def restore_effect_sample_slot(source):
    """Reverse only the exact read-only slot addition, then keep prior gates."""
    if sha(source) != EFFECT_SLOT_SOURCE_SHA256:
        # Existing historical/D source identities are still enforced by the
        # original downstream adapter; unrecognized bytes cannot bypass it.
        return source
    current = source.decode()
    for before, after in reversed(EFFECT_SLOT_EDITS):
        if current.count(after) != 1:
            raise ValueError('Effects sample slot reverse anchor drift')
        current = current.replace(after, before)
    restored = current.encode()
    if sha(restored) != EFFECT_SLOT_PARENT_SHA256:
        raise ValueError('Effects sample slot parent identity changed')
    for before, after in EFFECT_SLOT_EDITS:
        if current.count(before) != 1:
            raise ValueError('Effects sample slot forward anchor drift')
        current = current.replace(before, after)
    if current.encode() != source:
        raise ValueError('Effects sample slot round trip changed bytes')
    return restored


# D-DEMO adds only opt-in committed CC22 wet depth plumbing. Reversing
# these exact identity-bound edits restores the E8-compatible default runtime
# source before its unchanged scratch/FIFO/original prepared provenance chain.
D_CONTROL_ADAPTATIONS = {'rtl/audio/workstation_runtime_stereo_effects.sv': {'parent_sha256': 'ca9f50cd0c70add7c04fe6230686510dbbd128561aebf7a0920d1eb463c5686f',
                                                     'source_sha256': '7bd9a9f547f82bb30f9f015610f9ac448c1ae374fe87366e1d37d52f2093b826',
                                                     'edits': [('module workstation_runtime_stereo_effects '
                                                                '#(\n'
                                                                '    parameter integer VECTOR_ENABLE=0,\n'
                                                                '    parameter integer DELAY_BITS=14,\n'
                                                                '    parameter integer ECHO_SAMPLES=9600,\n',
                                                                'module workstation_runtime_stereo_effects '
                                                                '#(\n'
                                                                '    parameter integer VECTOR_ENABLE=0,\n'
                                                                '    parameter bit D_DELAY_SEND_ENABLE=0,\n'
                                                                '    parameter integer DELAY_BITS=14,\n'
                                                                '    parameter integer ECHO_SAMPLES=9600,\n'),
                                                               ('    input logic [2:0] effect_mask_i,\n'
                                                                '    input logic [5:0] effect_order_i,\n'
                                                                '    output logic ready_o,valid_o,\n'
                                                                '    output logic signed [31:0] '
                                                                'left_o,right_o,\n',
                                                                '    input logic [2:0] effect_mask_i,\n'
                                                                '    input logic [5:0] effect_order_i,\n'
                                                                '    input logic [6:0] delay_send_i,\n'
                                                                '    output logic ready_o,valid_o,\n'
                                                                '    output logic signed [31:0] '
                                                                'left_o,right_o,\n'),
                                                               ('  defparam '
                                                                'delay_stage.u_write_fifo.RAM_STYLE="block_ram";\n'
                                                                '  defparam '
                                                                'delay_stage.u_read_fifo.RAM_STYLE="block_ram";\n'
                                                                '  workstation_runtime_delay_effect_ddr '
                                                                '#(.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES),\n'
                                                                '      '
                                                                '.FIFO_ADDRESS_BITS(FIFO_ADDRESS_BITS),.TRANSACTION_TIMEOUT_CYCLES(TRANSACTION_TIMEOUT_CYCLES),\n'
                                                                '      '
                                                                '.PEER_TIMEOUT_CYCLES(PEER_TIMEOUT_CYCLES)) '
                                                                'delay_stage(\n'
                                                                '      '
                                                                '.clk_i,.rst_ni,.clear_i,.valid_i(state==SEND&&work_id==0),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),\n'
                                                                '      '
                                                                '.ready_o(delay_ready),.valid_o(delay_valid),.active_o(delay_active),.left_o(delay_l),.right_o(delay_r),.clip_o(delay_clip),\n'
                                                                '      .mem_clk_i,.mem_rst_ni,\n',
                                                                '  defparam '
                                                                'delay_stage.u_write_fifo.RAM_STYLE="block_ram";\n'
                                                                '  defparam '
                                                                'delay_stage.u_read_fifo.RAM_STYLE="block_ram";\n'
                                                                '  workstation_runtime_delay_effect_ddr '
                                                                '#(.D_DELAY_SEND_ENABLE(D_DELAY_SEND_ENABLE),.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES),\n'
                                                                '      '
                                                                '.FIFO_ADDRESS_BITS(FIFO_ADDRESS_BITS),.TRANSACTION_TIMEOUT_CYCLES(TRANSACTION_TIMEOUT_CYCLES),\n'
                                                                '      '
                                                                '.PEER_TIMEOUT_CYCLES(PEER_TIMEOUT_CYCLES)) '
                                                                'delay_stage(\n'
                                                                '      '
                                                                '.clk_i,.rst_ni,.clear_i,.valid_i(state==SEND&&work_id==0),.enabled_i(work_enabled),\n'
                                                                '      '
                                                                '.delay_send_i(delay_send_i),.left_i(work_l),.right_i(work_r),\n'
                                                                '      '
                                                                '.ready_o(delay_ready),.valid_o(delay_valid),.active_o(delay_active),.left_o(delay_l),.right_o(delay_r),.clip_o(delay_clip),\n'
                                                                '      .mem_clk_i,.mem_rst_ni,\n')]},
 'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv': {'parent_sha256': 'cf43513f998e182075e8c6dd61de20dfd1872c8570c88baa0dfb67955650b1fd',
                                                                 'source_sha256': 'f1366c86f721e0ac1befb2ccc84e1532528201c1eafb9b1b9ff45c8a01d1eca3',
                                                                 'edits': [('module '
                                                                            'workstation_runtime_delay_effect_ddr '
                                                                            '#(\n'
                                                                            '    parameter integer '
                                                                            'DELAY_BITS=14,\n'
                                                                            '    parameter integer '
                                                                            'ECHO_SAMPLES=9600,\n'
                                                                            '    parameter integer '
                                                                            'FIFO_ADDRESS_BITS=9,\n',
                                                                            'module '
                                                                            'workstation_runtime_delay_effect_ddr '
                                                                            '#(\n'
                                                                            '    parameter integer '
                                                                            'DELAY_BITS=14,\n'
                                                                            '    parameter bit '
                                                                            'D_DELAY_SEND_ENABLE=0,\n'
                                                                            '    parameter integer '
                                                                            'ECHO_SAMPLES=9600,\n'
                                                                            '    parameter integer '
                                                                            'FIFO_ADDRESS_BITS=9,\n'),
                                                                           ('    input logic '
                                                                            'clk_i,rst_ni,clear_i,valid_i,enabled_i,\n'
                                                                            '    input logic signed [31:0] '
                                                                            'left_i,right_i,\n'
                                                                            '    output logic '
                                                                            'ready_o,valid_o,active_o,\n'
                                                                            '    output logic signed [31:0] '
                                                                            'left_o,right_o,\n',
                                                                            '    input logic '
                                                                            'clk_i,rst_ni,clear_i,valid_i,enabled_i,\n'
                                                                            '    input logic signed [31:0] '
                                                                            'left_i,right_i,\n'
                                                                            '    input logic [6:0] '
                                                                            'delay_send_i,\n'
                                                                            '    output logic '
                                                                            'ready_o,valid_o,active_o,\n'
                                                                            '    output logic signed [31:0] '
                                                                            'left_o,right_o,\n'),
                                                                           ('        0:if(valid_i && '
                                                                            'ready_o) begin\n'
                                                                            '          '
                                                                            'input_l<=left_i;input_r<=right_i;\n'
                                                                            '          '
                                                                            "gain<=wet_slew(gain,enabled_i?16'd8192:16'd0,gain_delta);state<=1;\n"
                                                                            '        end\n'
                                                                            '        1:state<=2;\n',
                                                                            '        0:if(valid_i && '
                                                                            'ready_o) begin\n'
                                                                            '          '
                                                                            'input_l<=left_i;input_r<=right_i;\n'
                                                                            '          '
                                                                            'gain<=wet_slew(gain,enabled_i '
                                                                            '?\n'
                                                                            '              '
                                                                            '(D_DELAY_SEND_ENABLE ? '
                                                                            "(delay_send_i==127 ? 16'd8192 : "
                                                                            "{3'd0,delay_send_i,6'd0}) : "
                                                                            "16'd8192) : "
                                                                            "16'd0,gain_delta);state<=1;\n"
                                                                            '        end\n'
                                                                            '        1:state<=2;\n')]}}


def restore_demo_d_controls(source, path):
    policy = D_CONTROL_ADAPTATIONS[path]
    identity = sha(source)
    historical_native = {SOURCE: 'd8a0d2c787bc8c222bf4dde74069db41163988a646fd70c32774387bfe23a689',
                         DELAY_SCRATCH_SOURCE: DELAY_SCRATCH_PARENT_SHA256}
    if identity in (policy['parent_sha256'], historical_native[path]):
        return source
    if identity != policy['source_sha256']:
        raise ValueError('D control source identity changed: ' + path)
    current = source.decode()
    for before, after in reversed(policy['edits']):
        if current.count(after) != 1:
            raise ValueError('D control reverse anchor drift: ' + path)
        current = current.replace(after, before)
    restored = current.encode()
    if sha(restored) != policy['parent_sha256']:
        raise ValueError('D control parent identity changed: ' + path)
    for before, after in policy['edits']:
        if current.count(before) != 1:
            raise ValueError('D control forward anchor drift: ' + path)
        current = current.replace(before, after)
    if current.encode() != source:
        raise ValueError('D control round trip changed bytes: ' + path)
    return restored


def restore_delay_native(source, provenance):
    """Restore exactly the former native Delay before its unchanged lineage."""
    if sha(provenance) != DELAY_SCRATCH_PROVENANCE_SHA256:
        raise ValueError('Original Delay provenance bytes changed')
    source = restore_demo_d_controls(source, DELAY_SCRATCH_SOURCE)
    original = json.loads(provenance)
    if original['native_sha256'] != DELAY_SCRATCH_PARENT_SHA256:
        raise ValueError('Original native Delay identity changed')
    if sha(source) == DELAY_SCRATCH_PARENT_SHA256:
        return source
    if sha(source) != DELAY_SCRATCH_SOURCE_SHA256:
        raise ValueError('Current Delay scratch source identity changed')
    current = source.decode()
    for before, after in reversed(DELAY_SCRATCH_EDITS):
        if current.count(after) != 1:
            raise ValueError('Delay scratch reverse anchor drift')
        current = current.replace(after, before)
    if sha(current.encode()) != DELAY_SCRATCH_PARENT_SHA256:
        raise ValueError('Delay scratch parent identity changed')
    restored = current
    for before, after in DELAY_SCRATCH_EDITS:
        if current.count(before) != 1:
            raise ValueError('Delay scratch forward anchor drift')
        current = current.replace(before, after)
    if current.encode() != source:
        raise ValueError('Delay scratch round trip changed bytes')
    return restored.encode()


def restore_native(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Remove only the separately authorized storage statements, exactly."""
    if policy not in (STRICT_POLICY, STORAGE_POLICY):
        raise ValueError('Unknown delay storage provenance policy')
    if sha(provenance) != PROVENANCE_SHA256:
        raise ValueError('Original effects provenance bytes changed')
    original = json.loads(provenance)
    source = restore_remote_reverb_partition(source)
    source = restore_effect_release_policy(source)
    source = restore_effect_sample_slot(source)
    source = restore_demo_d_controls(source, SOURCE)
    current = source.decode()
    if policy == STORAGE_POLICY:
        if adaptation is None or sha(adaptation) != ADAPTATION_SHA256:
            raise ValueError('Delay storage adaptation changed or missing')
        bridge = json.loads(adaptation)
        if (bridge['schema'] != 1 or bridge['policy'] != policy or bridge['source'] != SOURCE or
                bridge['original_provenance'] != PROVENANCE or
                bridge['original_provenance_sha256'] != sha(provenance) or
                bridge['parent_source_sha256'] != original['native_sha256'] or
                bridge['current_source_sha256'] != sha(source) or len(bridge['exact_changes']) != 1):
            raise ValueError('Delay storage source identity changed')
        edit = bridge['exact_changes'][0]
        if edit['count'] != 1 or not edit['after'] or current.count(edit['after']) != 1:
            raise ValueError('Delay storage reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
        if (not edit['before'] or current.count(edit['before']) != 1 or
                current.replace(edit['before'], edit['after']) != source.decode()):
            raise ValueError('Delay storage exact round trip changed bytes')
    elif adaptation is not None:
        raise ValueError('Delay storage adaptation needs explicit policy')
    if sha(current.encode()) != original['native_sha256']:
        raise ValueError('Original native effects identity changed')
    return current


def verify(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Restore the previous native bytes, then their unchanged prepared slice."""
    current = restore_native(source, provenance, policy, adaptation)
    info = json.loads(provenance)
    for edit in reversed(info['forward_edits']):
        if not edit['after'] or current.count(edit['after']) != edit['count']:
            raise ValueError('Original effects reverse provenance anchor drift')
        current = current.replace(edit['after'], edit['before'])
    if sha(current.encode()) != info['prepared_sha256']:
        raise ValueError('Original prepared effects identity changed')
    return current, dict(policy=policy, source=SOURCE, current_source_sha256=sha(source),
        original_native_sha256=info['native_sha256'], original_provenance_sha256=sha(provenance),
        adaptation_sha256=sha(adaptation) if adaptation is not None else None,
        original_prepared_source_sha256=info['prepared_source_sha256'], exact_prepared_sha256=sha(current.encode()),
        original_provenance_unchanged=True, FIFO_source=FIFO, FIFO_sha256=FIFO_SHA256,
        RAM_STYLE='block_ram' if policy == STORAGE_POLICY else 'distributed_ram',
        storage_instances=['delay_stage.u_write_fifo', 'delay_stage.u_read_fifo'],
        large_bank_attribute_condition='WIDTH == 65 && ADDRESS_BITS >= 8',
        default_WIDTH=65, default_ADDRESS_BITS=9, default_depth_per_fifo=512,
        small_head_branch_unchanged=True, added_clock_latency=0,
        physical_ram_mapping_verified=False, physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    """Select only maintained native profiles and recheck both source chains."""
    root = Path(root)
    source, provenance, adaptation = ((root / p).read_bytes() for p in (SOURCE, PROVENANCE, ADAPTATION))
    prepared, evidence = verify(source, provenance, STORAGE_POLICY, adaptation)
    if sha(source) == REMOTE_REVERB_SOURCE_SHA256:
        partition = (root / REMOTE_REVERB_ADAPTATION).read_bytes()
        restore_remote_reverb_partition(source, partition)
        evidence['remote_reverb_partition'] = dict(
            adaptation=REMOTE_REVERB_ADAPTATION, adaptation_sha256=sha(partition),
            parent_source_sha256=REMOTE_REVERB_PARENT_SHA256,
            macro='WORKSTATION_REMOTE_REVERB_PARTITION', default_macro_off=True,
            exact_inverse_round_trip_verified=True,
            whole_workstation_selected=False, physical_transport_verified=False)
    if sha((root / FIFO).read_bytes()) != FIFO_SHA256:
        raise ValueError('Delay FIFO source bytes changed')
    selected_reference = (root / REFERENCE).read_bytes()
    from tools.workstation_task3_w_media_profile import inverse_top
    reference = inverse_top(root, selected_reference.decode()).encode()
    if reference != selected_reference:
        evidence['task3_w_media_reference'] = dict(parent_sha256=sha(reference),
            current_sha256=sha(selected_reference), exact_inverse_round_trip_verified=True,default_macro_off=True)
    restored_reference = reference
    if sha(reference) == DIRECT_TOP_SHA256:
        payload = (root / DIRECT_REFERENCE).read_bytes()
        if sha(payload) != DIRECT_REFERENCE_SHA256:
            raise ValueError('Direct TF reference adaptation bytes changed')
        direct = json.loads(payload)
        if (direct.get('schema') != 1 or direct.get('policy') != 'task3_direct_tf_default_off_reference_v1'
                or direct.get('source') != REFERENCE or direct.get('parent_source_sha256') != TF_MENU_REFERENCE_SHA256
                or direct.get('current_source_sha256') != DIRECT_TOP_SHA256 or direct.get('default_macro_off') is not True
                or len(direct.get('exact_changes', [])) != 10):
            raise ValueError('Direct TF reference adaptation identity changed')
        text = reference.decode()
        for edit in reversed(direct['exact_changes']):
            if edit['count'] != 1 or not edit['before'] or not edit['after'] or text.count(edit['after']) != 1:
                raise ValueError('Direct TF inverse reference anchor changed')
            text = text.replace(edit['after'], edit['before'], 1)
        restored_reference = text.encode()
        if sha(restored_reference) != TF_MENU_REFERENCE_SHA256:
            raise ValueError('Direct TF parent reference identity changed')
        forward = text
        for edit in direct['exact_changes']:
            if forward.count(edit['before']) != 1:
                raise ValueError('Direct TF forward reference anchor changed')
            forward = forward.replace(edit['before'], edit['after'], 1)
        if forward.encode() != reference:
            raise ValueError('Direct TF reference inverse round trip failed')
        evidence['direct_tf_reference'] = dict(adaptation=DIRECT_REFERENCE, adaptation_sha256=sha(payload),
            parent_sha256=TF_MENU_REFERENCE_SHA256, current_sha256=sha(reference),
            exact_inverse_round_trip_verified=True, default_macro_off=True)
    if sha(restored_reference) == TF_MENU_REFERENCE_SHA256:
        text = restored_reference.decode()
        if any(text.count(insertion) != 1 for insertion in TF_MENU_REFERENCE_INSERTIONS):
            raise ValueError('TF menu reference insertion identity changed')
        text = text.replace(TF_MENU_REFERENCE_INSERTIONS[0], '', 1)
        # Remove the matching extra endif after the old no-CNN assignments.
        tail = "    assign song_cmd_index=4'd0;\n`endif\n    assign music_score_ready=1'b1;"
        if text.count(tail) != 1:
            raise ValueError('TF menu reference closing anchor changed')
        text = text.replace(tail, tail.replace('`endif\n', '', 1), 1)
        text = text.replace(TF_MENU_REFERENCE_INSERTIONS[1], '', 1)
        restored_reference = text.encode()
        evidence['tf_menu_reference'] = dict(current_sha256=sha(reference),
            parent_sha256=REFERENCE_SHA256, exact_inverse_round_trip_verified=True)
    if sha(restored_reference) != REFERENCE_SHA256:
        raise ValueError('Maintained non-runtime storage policy reference changed')
    bridge = json.loads(adaptation)
    for selector in bridge['policy_reference']['selectors']:
        if reference.decode().count('defparam ' + selector + '="block_ram";') != 1:
            raise ValueError('Maintained non-runtime storage policy selector changed')
    # This is the original locked prepared composition, not an assertion that
    # accepted_full83 used block RAM. The mapping policy is a later source choice.
    info = json.loads(provenance)
    payload = (root / PREPARED_SOURCE).read_bytes()
    if sha(payload) != info['prepared_source_sha256']:
        raise ValueError('Original locked effects source changed')
    text = payload.decode()
    begin = text.index('module stereo_effects #(')
    end = text.index('endmodule', begin) + len('endmodule')
    if text[begin:end] != prepared:
        raise ValueError('Exact original prepared effects slice changed')
    delay_source = (root / DELAY_SCRATCH_SOURCE).read_bytes()
    delay_provenance = (root / DELAY_SCRATCH_PROVENANCE).read_bytes()
    delay_parent = restore_delay_native(delay_source, delay_provenance)
    evidence.update(effect_release_policy=dict(current_source_sha256=sha(source),
        parent_source_sha256=EFFECT_RELEASE_PARENT_SHA256, default_release_tails_enable=1,
        d_only_release_tails_enable=0, exact_inverse_round_trip_verified=True,
        maintenance_history_and_nba_unchanged=True),
        delay_scratch_reset=dict(source=DELAY_SCRATCH_SOURCE,
        current_source_sha256=sha(delay_source), original_native_sha256=sha(delay_parent),
        original_provenance_sha256=sha(delay_provenance),
        scratch_products_without_reset=sha(restore_demo_d_controls(delay_source, DELAY_SCRATCH_SOURCE)) == DELAY_SCRATCH_SOURCE_SHA256),
        demo_d_controls={path: {key: value for key, value in item.items() if key!='edits'}
                         for path,item in D_CONTROL_ADAPTATIONS.items()},
        original_locked_prepared_slice_verified=True,
        storage_policy_reference=REFERENCE, storage_policy_reference_sha256=sha(selected_reference),
        original_prepared_source=PREPARED_SOURCE, original_prepared_identity=info['prepared_source_identity'],
        accepted_baseline_storage_selection_inherited=False)
    return evidence
