"""Exact Session top inverse for the unchanged legacy delay storage reference.

This adapter proves ancestry in memory; it never rewrites a top, baseline or
original provenance manifest. No other maintained top identity is accepted.
"""
import hashlib

POLICY = 'session_push_rate_top_storage_reference_v1'
SOURCE = 'rtl/workstation/gw138k_push_workstation_top.v'
TOOL = 'tools/workstation_top_session_reference.py'
SOURCE_COMMIT = 'bfac338acbb078d64ee23f5702115cdcb29be261'
PARENT_REFERENCE_COMMIT = '31cfd3b4'
SOURCE_SHA256 = '1d2288097f12e19944bbe78350fa003559e960f96fe8bf591943b782a79ee331'
PARENT_SHA256 = '2c4376b7754a9b98486501fb91e258f5b70b4183b4ec5f687b2a588132ba7007'
SELECTORS = (
    'u_managed.u_audio.u_workstation.effects.delay_stage.u_write_fifo.RAM_STYLE',
    'u_managed.u_audio.u_workstation.effects.delay_stage.u_read_fifo.RAM_STYLE',
)
EXACT_CHANGES = (('    workstation_audio_clock_service #(.RESERVE_ZERO_EPOCH(1),.ENABLE_MEDIA_POLICY(1)) '
  'u_clock_service(\n',
  '`ifdef WORKSTATION_PUSH_RATE_CONTROL\n'
  '    wire push_rate_usb_ready,push_rate_usb_toggle,push_rate_toggle,push_rate_ready;\n'
  '    wire clock_service_busy,clock_service_fault;\n'
  '    wire [31:0] push_rate_generation,push_rate_command_generation;\n'
  '    workstation_push_rate_bridge u_push_rate_bridge(\n'
  '        .reset_ni(clock_command_reset_n && '
  'usb_reset_n),.usb_clk_i(usb_clk),.control_clk_i(clk_50m),\n'
  '        .service_ready_i(push_rate_ready),.service_generation_i(push_rate_generation),\n'
  '        .usb_ready_o(push_rate_usb_ready),.usb_toggle_i(push_rate_usb_toggle),\n'
  '        '
  '.service_toggle_o(push_rate_toggle),.service_generation_o(push_rate_command_generation));\n'
  '`endif\n'
  '    workstation_audio_clock_service #(.RESERVE_ZERO_EPOCH(1),.ENABLE_MEDIA_POLICY(1)\n'
  '`ifdef WORKSTATION_PUSH_RATE_CONTROL\n'
  '        ,.ENABLE_PUSH_RATE_CONTROL(1)\n'
  '`endif\n'
  '    ) u_clock_service(\n'
  '`ifdef WORKSTATION_PUSH_RATE_CONTROL\n'
  '        .push_toggle_i(push_rate_toggle),.push_generation_i(push_rate_command_generation),\n'
  '        '
  '.push_ready_o(push_rate_ready),.push_generation_o(push_rate_generation),.push_rejected_o(),\n'
  '        .service_busy_o(clock_service_busy),.service_fault_o(clock_service_fault),\n'
  '`endif\n'),
 ('    workstation_usb2_input #(.FEEDBACK_AUDIO_DOMAIN(1)\n',
  '    workstation_usb2_input #(.FEEDBACK_AUDIO_DOMAIN(1)\n'
  '`ifdef WORKSTATION_PUSH_RATE_CONTROL\n'
  "        ,.PUSH_RATE_CONTROL_ENABLE(1'b1)\n"
  '`endif\n'),
 ('    ) u_native_usb (\n',
  '    ) u_native_usb (\n'
  '`ifdef WORKSTATION_PUSH_RATE_CONTROL\n'
  '        '
  '.rate_control_ready_i(push_rate_usb_ready),.rate_toggle_o(push_rate_usb_toggle),.rate_rejected_o(),\n'
  '`endif\n'),
 ('    hdmi_display u_video (\n',
  '    hdmi_display u_video (\n'
  '`ifdef WORKSTATION_PUSH_RATE_CONTROL\n'
  '        // Independent of PCM observations: a stopped/muted audio stream must\n'
  '        // not freeze switching/fault feedback. Bit0 is the committed rate.\n'
  '        .audio_clock_status_i({rate_fault || rate_dsp_fault || memory_guard_fault || '
  'clock_service_fault,\n'
  '            rate_busy || clock_service_busy,rate_valid,rate44}),\n'
  '`endif\n'))


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def replace_once(text, before, after, label):
    if not before or text.count(before) != 1:
        raise ValueError('Session top storage reference '+label+' anchor drift')
    return text.replace(before, after)


def restore_parent(source, policy=POLICY):
    """Require the known Session bytes, then prove both exact directions."""
    if policy != POLICY:
        raise ValueError('Unknown Session top storage reference policy')
    if sha(source) != SOURCE_SHA256:
        raise ValueError('Session top storage reference source identity changed')
    current = source.decode()
    for index, (before, after) in reversed(list(enumerate(EXACT_CHANGES))):
        current = replace_once(current, after, before, 'reverse '+str(index))
    parent = current.encode()
    if sha(parent) != PARENT_SHA256:
        raise ValueError('Session top storage reference parent identity changed')
    for index, (before, after) in enumerate(EXACT_CHANGES):
        current = replace_once(current, before, after, 'forward '+str(index))
    round_trip = current.encode()
    if round_trip != source or sha(round_trip) != SOURCE_SHA256:
        raise ValueError('Session top storage reference exact round trip changed bytes')
    for selector in SELECTORS:
        statement = 'defparam '+selector+'="block_ram";'
        if source.decode().count(statement) != 1 or parent.decode().count(statement) != 1:
            raise ValueError('Session top storage reference legacy FIFO selector changed')
    return parent, dict(policy=POLICY, source=SOURCE, source_commit=SOURCE_COMMIT,
        parent_reference_commit=PARENT_REFERENCE_COMMIT,
        current_source_sha256=sha(source), restored_parent_sha256=sha(parent),
        round_trip_source_sha256=sha(round_trip), exact_inverse_edits=len(EXACT_CHANGES),
        every_reverse_and_forward_anchor_unique=True, exact_round_trip_verified=True,
        legacy_fifo_selectors=list(SELECTORS), legacy_fifo_selector_bytes_unchanged=True,
        original_reference_lock_unchanged=True, original_provenance_unchanged=True,
        input_source_rewritten=False, source_policy='identity_bound_in_memory_inverse_only',
        hardware_acceptance_inherited=False)
