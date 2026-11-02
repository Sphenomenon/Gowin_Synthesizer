"""Checked native-board timing adaptations; never change frozen inputs."""

import hashlib
import re

from tools.workstation_synthesis_netlist import SynthesisNetlist


INPUTS = {
    'src/migration/gw138k_audio_clock.v': 'ea421ccc44dbb6b81f85645cd79a307e6750e2140c2a070057756f781c9c8d54',
    'legacy/rtl/audio/sine_interp.sv': '1085c7ebba307faa6ea7d10d99c6111a253d1f383e13fefef81c595a7d8b2b61',
    'src/storage/tf_audio_ddr_dma.v': 'd37ff20c676049fe8cc53adfb7db43e30553f3824e62e57c58493a1042649e3b',
    'legacy/rtl/audio/unified_oscillator_engine.sv': '2bf573382c5c93212a196de483703ff5edc5cd4f1d67983841c28f64bc851423',
    'src/push2/gw138k_push_performance_uart.sv': '877bb5e0d22ee03fb8c6dc35eb15f09695bbddbc5375935e8e8bed168f74f41f',
}
HOST = 'u_native_usb/host/usb'
SUPERVISOR = HOST + '/controller/phy/physical_link/supervisor'
RESET_CHAINS = {
    'u_native_usb/cpu_release_q': 'usb_48m',
    'u_native_usb/session_release_q': 'usb_48m',
    'u_native_usb/feedback_release_q': 'clk_50m',
    HOST + '/reference_release_q': 'clk_50m',
    HOST + '/status_release_q': 'ulpi_60m',
    HOST + '/bridge/ulpi_release_q': 'ulpi_60m',
    HOST + '/bridge/cpu_session_q': 'usb_48m',
    HOST + '/bridge/ulpi_session_q': 'ulpi_60m',
    HOST + '/controller/fault_release_q': 'ulpi_60m',
    HOST + '/controller/phy/mac_release_q': 'ulpi_60m',
    SUPERVISOR + '/release_q': 'ulpi_60m',
    SUPERVISOR + '/heartbeat_release_q': 'ulpi_60m',
}
THREE_STAGE_RESET_CHAINS = {
    'u_native_usb/input_owner/feedback/source_release': 'clk_50m',
    'u_native_usb/input_owner/feedback/destination_release': 'usb_48m',
}
LEVEL_CHAINS = [
    (HOST + '/enable_ref_q_0', HOST + '/enable_ref_q_1', 'clk_50m'),
    (HOST + '/controller/fatal_sync_q_0', HOST + '/controller/fatal_sync_q_1', 'clk_50m'),
    (SUPERVISOR + '/heartbeat_meta_q', SUPERVISOR + '/heartbeat_sync_q', 'clk_50m'),
    *((HOST + '/failure_meta_q_' + str(bit), HOST + '/failure_sync_q_' + str(bit), 'ulpi_60m')
      for bit in range(5)),
]
# Native runtime only. Each two-flop chain receives a held startup/safety
# level; an asynchronous input is excepted only at bit 0. Same-50-MHz inputs
# remain normally timed. Both selected-clock modes use the same local chain.
# (exact synthesis stem, source domain(s), consuming domain)
RUNTIME_GRANT_CHAINS = (
    ('u_managed/startup_control', 'clk_50m', 'clk_50m'),
    ('u_managed/startup_compute', 'clk_50m', 'audio_76m8'),
    ('u_managed/runtime/startup_control', 'clk_50m', 'clk_50m'),
    ('u_managed/runtime/startup_compute', 'clk_50m', 'audio_76m8'),
    ('u_managed/runtime/startup_memory', 'clk_50m', 'ddr_ui100'),
    ('u_managed/runtime/startup_serial', 'clk_50m', 'selected48/selected44'),
    ('u_managed/runtime/clocks/startup_control', 'clk_50m', 'clk_50m'),
    ('u_managed/runtime/clocks/reference_48_monitor/startup_source', 'clk_50m', 'dac_ref12m288'),
    ('u_managed/runtime/clocks/reference_44_monitor/startup_source', 'clk_50m', 'dac_ref16m9344'),
    ('u_managed/runtime/clocks/selected_monitor/startup_source', 'clk_50m', 'selected48/selected44'),
    ('u_tf_audio/startup_source', 'clk_50m', 'clk_50m'),
    ('u_tf_audio/startup_compute', 'clk_50m', 'audio_76m8'),
    ('u_tf_audio/startup_memory', 'clk_50m', 'ddr_ui100'),
    ('u_tf_audio/frames/startup_source', 'clk_50m', 'clk_50m'),
    ('u_tf_audio/frames/startup_compute', 'clk_50m', 'audio_76m8'),
    ('output_safe_sync', 'clk_50m+audio_76m8', 'audio_76m8'),
    ('u_runtime/g_usb_cdc_reset.usb_ready', 'clk_50m+usb_48m', 'usb_48m'),
)
# Actual v3 VG maps these first receivers to DFFRE: part of their asynchronous
# level expression enters synchronous RESET, which is a data/setup input.
# Include only the nine asynchronous/mixed receivers; same-clock and later
# RESET inputs retain their timing checks. This is not an async CLEAR cut.
RUNTIME_GRANT_RESET_INPUTS = (
    'u_managed/startup_compute',
    'u_managed/runtime/startup_compute',
    'u_managed/runtime/startup_memory',
    'u_managed/runtime/startup_serial',
    'u_tf_audio/startup_compute',
    'u_tf_audio/startup_memory',
    'u_tf_audio/frames/startup_compute',
    'output_safe_sync',
    'u_runtime/g_usb_cdc_reset.usb_ready',
)
# ENABLE_MEDIA_POLICY uses the completed stop/held-start contract before any
# real change or recovery. Busy is then held status crossing through D only;
# retain timing on every later stage and on all asynchronous reset pins.
RUNTIME_MEDIA_STATUS_CHAINS = (
    ('u_managed/switch_busy_compute', 2),
    ('u_managed/media_busy_50', 3),
)
# These are reset-release synchronizers, not functional state registers. Only
# their asynchronous assertion inputs are excepted; the final stage's reset
# distribution to the display owners remains subject to recovery/removal.
RUNTIME_DISPLAY_RESET_CHAINS = (
    'u_video/u_runtime_display/source_release',
    'u_video/u_runtime_display/memory_release',
)
RECORDING_SURVIVAL_CHAIN = 'recording_authority/survived_control'


def once(text, original, replacement):
    if text.count(original) != 1:
        raise ValueError('native timing adaptation anchor drifted: ' + original[:80])
    return text.replace(original, replacement)


def audio_pll(text):
    text = once(text, '.O_RST(pll_reset), .ICPSEL(pll_icpsel), .LPFRES(pll_lpfres), .O_LOCK(lock)',
                '.O_RST(helper_reset), .ICPSEL(helper_icpsel), .LPFRES(helper_lpfres), .O_LOCK(lock)')
    return once(text, 'wire [2:0] pll_lpfres;\n', '''wire [2:0] pll_lpfres;
wire helper_reset;
wire [5:0] helper_icpsel;
wire [2:0] helper_lpfres;
(* syn_preserve=1 *) reg [9:0] pll_control=10'b1000000000;
always @(posedge init_clk or posedge reset)
    if(reset) pll_control<=10'b1000000000;
    else pll_control<={helper_reset,helper_icpsel,helper_lpfres};
assign {pll_reset,pll_icpsel,pll_lpfres}=pll_control;
''')


def sine_address(text):
    bits = [f'(phase_i[{bit}] ^ (&phase_i[{bit-1}:21]))' for bit in range(31, 21, -1)]
    bits.append('~phase_i[21]')
    return once(text, "next_address_s0 <= phase_i[31:21] + 11'd1;",
                'next_address_s0 <= {' + ', '.join(bits) + '};')


def legacy_byte_increment(text):
    start = text.index('    function [31:0] add_byte_count;')
    end = text.index('    endfunction', start) + len('    endfunction')
    original = text[start:end]
    replacement = '''    function [31:0] add_byte_count;
        input [31:0] value;
        input [5:0] increment;
        reg [6:0] carries;
        begin
            carries[0] = 1'b0;
'''
    for bit in range(1, 7):
        terms = []
        for generate_bit in range(bit):
            factors = [f'(value[{generate_bit}] && increment[{generate_bit}])']
            factors += [f'(value[{propagate_bit}] ^ increment[{propagate_bit}])'
                        for propagate_bit in range(generate_bit+1, bit)]
            terms.append('(' + ' && '.join(factors) + ')')
        replacement += f'            carries[{bit}] = ' + ' || '.join(terms) + ';\n'
    for bit in range(6):
        replacement += f'            add_byte_count[{bit}] = value[{bit}] ^ increment[{bit}] ^ carries[{bit}];\n'
    replacement += '            add_byte_count[6] = value[6] ^ carries[6];\n'
    for bit in range(7, 32):
        replacement += f'            add_byte_count[{bit}] = value[{bit}] ^ (carries[6] && (&value[{bit-1}:6]));\n'
    replacement += '        end\n    endfunction'
    return once(text, original, replacement)


def byte_increment(text):
    start = text.index('    function [31:0] add_byte_count;')
    end = text.index('    endfunction', start) + len('    endfunction')
    original = text[start:end]
    replacement = '''    function [31:0] add_byte_count;
        input [31:0] value;
        input [5:0] increment;
        reg [6:0] carries;
        begin
            carries[0] = 1'b0;
'''
    for bit in range(1, 7):
        terms = []
        for generate_bit in range(bit):
            factors = [f'(value[{generate_bit}] && increment[{generate_bit}])']
            factors += [f'(value[{propagate_bit}] ^ increment[{propagate_bit}])'
                        for propagate_bit in range(generate_bit+1, bit)]
            terms.append('(' + ' && '.join(factors) + ')')
        replacement += f'            carries[{bit}] = ' + ' || '.join(terms) + ';\n'
    for bit in range(6):
        replacement += f'            add_byte_count[{bit}] = value[{bit}] ^ increment[{bit}] ^ carries[{bit}];\n'
    replacement += '            add_byte_count[6] = value[6] ^ carries[6];\n'
    for bit in range(7, 32):
        replacement += f'            add_byte_count[{bit}] = value[{bit}] ^ (carries[6] && (&value[{bit-1}:6]));\n'
    replacement += '        end\n    endfunction'
    text = once(text, original, replacement)
    # The ring advances by the same 32-byte DDR beat. Reuse the bounded
    # increment network rather than synthesizing another long carry chain.
    start = text.index('    function [31:0] advance_ring;')
    end = text.index('    endfunction', start) + len('    endfunction')
    original_ring = text[start:end]
    if len(re.findall(r"offset\s*\+\s*32'd32", original_ring)) != 4:
        raise ValueError('native ring increment anchor drifted')
    ring = once(original_ring, '        input [31:0] offset;\n        begin',
                '        input [31:0] offset;\n        reg [31:0] next_offset;\n        begin\n'
                "            next_offset = add_byte_count(offset, 6'd32);")
    ring = re.sub(r"offset\s*\+\s*32'd32", 'next_offset', ring)
    return once(text, original_ring, ring)


def voice_controls(text):
    text = once(text, '        expression_gain_q8[voice_index] <= 8\'d128;\n', '')
    text = once(text, '''        expression_gain_q8[allocation_index] <= 8'd128;
      end else if (accepted_expression) begin
        for(integer ev=0;ev<32;ev=ev+1)
          if(expression_select[ev]) expression_gain_q8[ev]<=
              expression_value_i == 7'd127 ? 8'd128 : {1'b0, expression_value_i};
      end else begin''', '''      end else if (!accepted_expression) begin''')
    text = once(text, '''    allocation_found = 1'b0;
    allocation_index = '0;
''', '')
    text = once(text, '''      if (!allocation_found && index <= maximum_voice_index &&
          !allocated_mask_o[index]) begin
        allocation_found = 1'b1;
        allocation_index = index[4:0];
      end
''', '')
    prefix = '''  wire [31:0] allocation_candidates, allocation_selected;
  for (genvar voice_number=0;voice_number<32;voice_number=voice_number+1) begin: g_native_voice_control
    assign allocation_candidates[voice_number]=voice_number<=maximum_voice_index && !allocated_mask_o[voice_number];
    if(voice_number==0) assign allocation_selected[voice_number]=allocation_candidates[voice_number];
    else assign allocation_selected[voice_number]=allocation_candidates[voice_number] && !(|allocation_candidates[voice_number-1:0]);
    always @(posedge clk_i or negedge rst_ni) begin
      if(!rst_ni) expression_gain_q8[voice_number]<=8'd128;
      else if(accepted_event && event_note_on_i && allocation_index==voice_number)
        expression_gain_q8[voice_number]<=8'd128;
      else if(!(accepted_event && event_note_on_i) && accepted_expression && expression_select[voice_number])
        expression_gain_q8[voice_number]<=expression_value_i==7'd127 ? 8'd128 : {1'b0,expression_value_i};
    end
  end
  assign allocation_found=|allocation_candidates;
'''
    for bit in range(5):
        mask = sum(1 << voice for voice in range(32) if voice & (1 << bit))
        prefix += f"  assign allocation_index[{bit}]=|(allocation_selected & 32'h{mask:08x});\n"
    declarations = '  logic allocation_found;\n  logic [4:0] allocation_index;\n'
    return once(text, declarations, declarations + prefix)


def envelope_arithmetic(text):
    """Bound carry depth in the shared ADSR lane without adding a cycle.

    This checked overlay is limited to the frozen engine until that engine is
    migrated to native source. Keep its 25-bit attack overflow and unsigned
    decay/release comparisons, including inputs outside normal ADSR ranges.
    """
    helper = '''  function automatic [24:0] envelope_add24;
    input [23:0] a, b;
    input carry_in;
    reg [6:0] part0, part1, part2, part3;
    reg [3:0] propagate, generate_carry;
    reg [4:0] carry;
    begin
      part0 = {1'b0,a[5:0]} + {1'b0,b[5:0]};
      part1 = {1'b0,a[11:6]} + {1'b0,b[11:6]};
      part2 = {1'b0,a[17:12]} + {1'b0,b[17:12]};
      part3 = {1'b0,a[23:18]} + {1'b0,b[23:18]};
      propagate = {&(a[23:18]^b[23:18]), &(a[17:12]^b[17:12]),
                   &(a[11:6]^b[11:6]), &(a[5:0]^b[5:0])};
      generate_carry = {part3[6],part2[6],part1[6],part0[6]};
      carry[0] = carry_in;
      carry[1] = generate_carry[0] | (propagate[0] & carry_in);
      carry[2] = generate_carry[1] | (propagate[1] & generate_carry[0]) |
                 ((&propagate[1:0]) & carry_in);
      carry[3] = generate_carry[2] | (propagate[2] & generate_carry[1]) |
                 ((&propagate[2:1]) & generate_carry[0]) | ((&propagate[2:0]) & carry_in);
      carry[4] = generate_carry[3] | (propagate[3] & generate_carry[2]) |
                 ((&propagate[3:2]) & generate_carry[1]) |
                 ((&propagate[3:1]) & generate_carry[0]) | ((&propagate[3:0]) & carry_in);
      envelope_add24[5:0] = part0[5:0] + carry[0];
      envelope_add24[11:6] = part1[5:0] + carry[1];
      envelope_add24[17:12] = part2[5:0] + carry[2];
      envelope_add24[23:18] = part3[5:0] + carry[3];
      envelope_add24[24] = carry[4];
    end
  endfunction
  function automatic envelope_le24;
    input [23:0] a, b;
    begin
      envelope_le24 = (a[23:18] < b[23:18]) |
          ((a[23:18] == b[23:18]) & (a[17:12] < b[17:12])) |
          ((a[23:12] == b[23:12]) & (a[11:6] < b[11:6])) |
          ((a[23:6] == b[23:6]) & (a[5:0] <= b[5:0]));
    end
  endfunction
  wire [23:0] envelope_above_sustain =
      envelope_add24(envelope_update_level_q24, ~envelope_update_sustain_q24, 1'b1);
'''
    text = once(text, '  assign envelope_update_attack_sum =\n'
                "      {1'b0, envelope_update_level_q24} +\n"
                "      {1'b0, envelope_update_attack_q24};",
                helper + '  assign envelope_update_attack_sum =\n'
                "      envelope_add24(envelope_update_level_q24, envelope_update_attack_q24, 1'b0);")
    substitutions = [
        ("envelope_update_attack_sum >= {1'b0, MAXIMUM_LEVEL_Q24}",
         '(envelope_update_attack_sum[24] || (&envelope_update_attack_sum[23:6]))'),
        ('envelope_update_level_q24 <= envelope_update_sustain_q24',
         'envelope_le24(envelope_update_level_q24, envelope_update_sustain_q24)'),
        ('envelope_update_level_q24 - envelope_update_sustain_q24 <=\n'
         '                envelope_update_decay_q24',
         'envelope_le24(envelope_above_sustain, envelope_update_decay_q24)'),
        ('envelope_update_level_q24 -\n              envelope_update_decay_q24',
         "envelope_add24(envelope_update_level_q24, ~envelope_update_decay_q24, 1'b1)"),
        ('envelope_update_level_q24 <= envelope_update_release_q24',
         'envelope_le24(envelope_update_level_q24, envelope_update_release_q24)'),
        ('envelope_update_level_q24 -\n              envelope_update_release_q24',
         "envelope_add24(envelope_update_level_q24, ~envelope_update_release_q24, 1'b1)"),
    ]
    for original, replacement in substitutions:
        text = once(text, original, replacement)
    return text


def oscillator_timing(text):
    return envelope_arithmetic(voice_controls(text))


def telemetry_usb_reset(text):
    text = once(text, '    parameter integer CPU_SNAPSHOT_BITS=16\n',
                '    parameter integer CPU_SNAPSHOT_BITS=16,\n    parameter integer USB_CDC_SEPARATE_RESET=0\n')
    text = once(text, '    output wire serial_out\n',
                '    output wire serial_out,\n    input wire usb_cdc_assert_ni\n')
    text = once(text, '''    reg [15:0] usb_divider;
    always @(posedge usb_clk or negedge usb_reset_n)
        if(!usb_reset_n)usb_divider<=0;else usb_divider<=usb_divider+1'b1;
''', '''    reg [15:0] usb_divider;
    wire usb_cdc_reset_n,usb_divider_reset_n,usb_snapshot_ready;
    generate if(USB_CDC_SEPARATE_RESET)begin:g_usb_cdc_reset
        // Assertion is common/raw; readiness crosses only as a USB-domain
        // level. No reference-domain release drives a mailbox async clear.
        (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] usb_ready;
        always @(posedge usb_clk or negedge usb_cdc_assert_ni)
            if(!usb_cdc_assert_ni)usb_ready<=0;
            else usb_ready<={usb_ready[0],reset_n && usb_reset_n};
        assign usb_cdc_reset_n=usb_cdc_assert_ni;
        assign usb_divider_reset_n=usb_cdc_assert_ni;
        assign usb_snapshot_ready=usb_ready[1];
    end else begin:g_usb_cdc_legacy_reset
        assign usb_cdc_reset_n=reset_n && usb_reset_n;
        assign usb_divider_reset_n=usb_reset_n;
        assign usb_snapshot_ready=1'b1;
    end endgenerate
    always @(posedge usb_clk or negedge usb_divider_reset_n)
        if(!usb_divider_reset_n)usb_divider<=0;
        else if(!usb_snapshot_ready)usb_divider<=0;
        else usb_divider<=usb_divider+1'b1;
''')
    return once(text, '''    gw138k_stream_cdc #(.WIDTH(224)) u_usb_cdc(
        .reset_n(reset_n && usb_reset_n),.source_clk(usb_clk),.destination_clk(clk_50m),
        .source_valid(&usb_divider),.source_data(usb_words),.drop_count(),
''', '''    gw138k_stream_cdc #(.WIDTH(224)) u_usb_cdc(
        .reset_n(usb_cdc_reset_n),.source_clk(usb_clk),.destination_clk(clk_50m),
        .source_valid(usb_snapshot_ready && (&usb_divider)),.source_data(usb_words),.drop_count(),
''')


TRANSFORMS = dict(zip(INPUTS, (audio_pll, sine_address, byte_increment, oscillator_timing, telemetry_usb_reset)))


def apply(stage, *, resource_optimized=False):
    if type(resource_optimized) is not bool:
        raise ValueError("resource arithmetic selection must be boolean")
    transforms = dict(TRANSFORMS)
    if not resource_optimized:
        transforms["src/storage/tf_audio_ddr_dma.v"] = legacy_byte_increment
        transforms["legacy/rtl/audio/unified_oscillator_engine.sv"] = voice_controls
    evidence = {}
    for relative, expected in INPUTS.items():
        source = stage / relative
        before = source.read_bytes()
        if hashlib.sha256(before).hexdigest() != expected:
            raise ValueError('native timing adaptation input identity drifted: ' + relative)
        transform = transforms[relative]
        after = transform(before.decode()).encode()
        source.write_bytes(after)
        evidence[relative] = dict(before=expected, after=hashlib.sha256(after).hexdigest(),
                                  transform="byte_increment" if transform is legacy_byte_increment else transform.__name__)
    return evidence


def constraints(*, runtime_reset=False, recording_authority=False):
    if type(runtime_reset) is not bool:
        raise ValueError('native runtime reset selection must be boolean')
    if type(recording_authority) is not bool or (recording_authority and not runtime_reset):
        raise ValueError('recording authority selection requires a boolean runtime selection')
    lines = []
    for prefix in RESET_CHAINS:
        lines.append(f'set_false_path -to [get_pins {{{prefix}_*/CLEAR}}]')
        lines.append(f'set_max_delay 2.000 -from [get_pins {{{prefix}_0_s*/Q}}] -to [get_pins {{{prefix}_1_s*/D}}]')
    for prefix in THREE_STAGE_RESET_CHAINS:
        lines.append(f'set_false_path -to [get_pins {{{prefix}_*_s*/CLEAR}}]')
        for stage in range(2):
            lines.append(f'set_max_delay 2.000 -from [get_pins {{{prefix}_{stage}_s*/Q}}] -to [get_pins {{{prefix}_{stage+1}_s*/D}}]')
    for first, second, _ in LEVEL_CHAINS:
        lines.append(f'set_false_path -to [get_pins {{{first}_s*/D}}]')
        lines.append(f'set_max_delay 2.000 -from [get_pins {{{first}_s*/Q}}] -to [get_pins {{{second}_s*/D}}]')
    if runtime_reset:
        for prefix, source, destination in RUNTIME_GRANT_CHAINS:
            if source != destination:
                lines.append(f'set_false_path -to [get_pins {{{prefix}_0_s*/D}}]')
            lines.append(f'set_max_delay 2.000 -from [get_pins {{{prefix}_0_s*/Q}}] '
                         f'-to [get_pins {{{prefix}_1_s*/D}}]')
        for prefix in RUNTIME_GRANT_RESET_INPUTS:
            lines.append(f'set_false_path -to [get_pins {{{prefix}_0_s*/RESET}}]')
        for prefix, stages in RUNTIME_MEDIA_STATUS_CHAINS:
            lines.append(f'set_false_path -to [get_pins {{{prefix}_0_s*/D}}]')
            for stage in range(stages - 1):
                lines.append(f'set_max_delay 2.000 -from [get_pins {{{prefix}_{stage}_s*/Q}}] '
                             f'-to [get_pins {{{prefix}_{stage+1}_s*/D}}]')
        for prefix in RUNTIME_DISPLAY_RESET_CHAINS:
            for stage in range(3):
                lines.append(f'set_false_path -to [get_pins {{{prefix}_{stage}_s*/CLEAR}}]')
            for stage in range(2):
                lines.append(f'set_max_delay 2.000 -from [get_pins {{{prefix}_{stage}_s*/Q}}] '
                             f'-to [get_pins {{{prefix}_{stage+1}_s*/D}}]')
        if recording_authority:
            prefix = RECORDING_SURVIVAL_CHAIN
            lines.append(f'set_false_path -to [get_pins {{{prefix}_0_s*/D}}]')
            lines.append(f'set_max_delay 2.000 -from [get_pins {{{prefix}_0_s*/Q}}] '
                         f'-to [get_pins {{{prefix}_1_s*/D}}]')
            guard = 'recording_authority/guard'
            lines.append(f'set_false_path -to [get_pins {{{guard}/open_meta_s*/D}}]')
            lines.append(f'set_max_delay 2.000 -from [get_pins {{{guard}/open_meta_s*/Q}}] '
                         f'-to [get_pins {{{guard}/open_ack_s*/D}}]')
            # Existing one-outstanding seal toggles/held hold/registered ready
            # and the root-epoch channel status cross through two FFs. Only
            # their first D receives the asynchronous-level exception.
            recording_levels = (
                ('u_recording/seal_cdc/ready_meta', 'u_recording/seal_cdc/ready_sync'),
                ('u_recording/seal_cdc/result_meta', 'u_recording/seal_cdc/result_sync'),
                ('u_recording/seal_cdc/request_meta', 'u_recording/seal_cdc/request_sync'),
                ('u_recording/seal_cdc/hold_meta', 'u_recording/seal_cdc/hold_sync'),
                ('recording_channel_meta', 'recording_channel_ready50'),
            )
            for first, second in recording_levels:
                lines.append(f'set_false_path -to [get_pins {{{first}_s*/D}}]')
                lines.append(f'set_max_delay 2.000 -from [get_pins {{{first}_s*/Q}}] '
                             f'-to [get_pins {{{second}_s*/D}}]')
            # Result status changes with result_toggle and remains held until
            # a later request. The two result synchronizer stages precede its
            # capture into these two source-domain terminal flags.
            result_path = ('-from [get_pins {u_recording/seal_cdc/result_failed_s*/Q}] '
                           '-to [get_pins {u_recording/seal_cdc/failed_o_s*/D '
                           'u_recording/seal_cdc/done_o_s*/D}]')
            lines.append('set_max_delay 10.000 ' + result_path)
            lines.append('set_false_path -hold ' + result_path)
            # These are the same reviewed memory-guard heartbeat and FIFO
            # Gray protocols used elsewhere in the runtime. Preserve a full
            # source-period flight/skew bound. Only the first asynchronous
            # capture loses a clock-phase hold check; all later stages retain
            # setup/hold and receive a 2ns routing bound. FIFO bit 8's Gray MSB
            # is physically the corresponding binary MSB in Gowin's netlist.
            gray_groups = (
                (guard, 'memory_gray', 'gray_meta', 'gray_sync', 32, 10.000, None),
                ('recording_ble_store/capture_fifo', 'read_gray', 'read_gray_meta', 'read_gray_sync',
                 9, 10.000, 'read_binary'),
                ('recording_ble_store/capture_fifo', 'write_gray', 'write_gray_meta', 'write_gray_sync',
                 9, 20.000, 'write_binary'),
            )
            for scope, source, first, second, width, budget, msb in gray_groups:
                sources = ' '.join(f'{scope}/{msb if msb and bit==width-1 else source}_{bit}_s*/Q'
                                   for bit in range(width))
                captures = ' '.join(f'{scope}/{first}_{bit}_s*/D' for bit in range(width))
                path = f'-from [get_pins {{{sources}}}] -to [get_pins {{{captures}}}]'
                lines.append(f'set_max_delay {budget:.3f} {path}')
                lines.append('set_false_path -hold ' + path)
                first_q = ' '.join(f'{scope}/{first}_{bit}_s*/Q' for bit in range(width))
                second_d = ' '.join(f'{scope}/{second}_{bit}_s*/D' for bit in range(width))
                lines.append(f'set_max_delay 2.000 -from [get_pins {{{first_q}}}] '
                             f'-to [get_pins {{{second_d}}}]')
    phy = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
    # EF still misses capture hold by 1.537 ns with the 1.800 ns floor.
    # Request additional routed delay; retain the actual setup/hold checks.
    lines.append(f'set_min_delay 3.500 -from [get_pins {{{phy}/ddr_init_internal_r_s0/Q}}] -to [get_pins {{{phy}/wloadn_3_s0/D}}]')
    for kind in ('setup', 'hold', 'recovery', 'removal'):
        lines.append(f'report_timing -{kind} -max_paths 2000 -max_common_paths 1')
    # The global worst paths can omit every noncritical hard-CPU clock path.
    # Report the real routed CLKOUT1 tree as well as requesting its CST site.
    for kind in ('setup', 'hold'):
        lines.append(f'report_timing -{kind} -from_clock [get_clocks {{cpu_core100}}] '
                     '-to_clock [get_clocks {cpu_core100}] -max_paths 8 -max_common_paths 1')
    return '\n'.join(lines) + '\n'


def audit_resets(text, clocks, *, feedback_source_clock='clk_50m', top='workstation_custom_138k_top'):
    if feedback_source_clock not in ('clk_50m', 'audio_76m8'):
        raise ValueError('unreviewed native feedback source clock')
    netlist = SynthesisNetlist(text, top)
    constants = {"1'b1"} | {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    evidence = dict(resets={}, levels={})

    def register(stem):
        matches = [name for name, cell in netlist.cells.items()
                   if cell['kind'].startswith('DFF') and re.fullmatch(re.escape(stem) + r'_s\d+', name)]
        if len(matches) != 1:
            raise ValueError('native USB synchronizer inventory changed: ' + stem)
        return matches[0]

    chains = [(prefix, prefix + '_0', prefix + '_1', clock, True, True) for prefix, clock in RESET_CHAINS.items()]
    chains += [(prefix + ':' + str(stage), prefix + '_' + str(stage), prefix + '_' + str(stage+1),
                feedback_source_clock if prefix == 'u_native_usb/input_owner/feedback/source_release' else clock,
                True, stage==0)
               for prefix, clock in THREE_STAGE_RESET_CHAINS.items() for stage in range(2)]
    chains += [(first, first, second, clock, False, False) for first, second, clock in LEVEL_CHAINS]
    for label, first_stem, second_stem, clock, reset_chain, starts_constant in chains:
        first, second = register(first_stem), register(second_stem)
        expected = clocks['clocks'][clock]['net']
        if (any(netlist.pin(name, 'CLK') != expected or netlist.pin(name, 'CE') not in constants for name in (first, second)) or
                netlist.pin(second, 'D') != netlist.pin(first, 'Q') or
                netlist.pin(first, 'CLEAR') != netlist.pin(second, 'CLEAR')):
            raise ValueError('native USB two-stage release/level topology changed: ' + label)
        if starts_constant and netlist.pin(first, 'D') not in constants:
            raise ValueError('native USB reset release no longer starts at a constant: ' + label)
        scope = netlist.scopes[first]
        local_output = netlist.cells[first]['ports']['Q']
        output_stem = local_output.split('[')[0]
        selected_bit = re.fullmatch(r'.+\[(\d+)\]', local_output)
        reference = re.compile(r'(?<![\w$])' + re.escape(output_stem) + r'(?:\[(\d+)(?::(\d+))?\])?(?![\w$])')
        def uses_first(value):
            for match in reference.finditer(value):
                if selected_bit is None or match[1] is None:
                    return True
                high, low = int(match[1]), int(match[2] or match[1])
                if min(high, low) <= int(selected_bit[1]) <= max(high, low):
                    return True
            return False
        if output_stem in netlist.directions[netlist.frames[scope]['kind']]:
            raise ValueError('native USB first synchronizer stage is exported: ' + label)
        consumers = set()
        for name, cell in netlist.cells.items():
            if netlist.scopes[name] != scope:
                continue
            for pin, value in cell['ports'].items():
                if pin == 'Q':
                    continue
                if cell['kind'] in netlist.modules:
                    if uses_first(value):
                        raise ValueError('native USB first stage escapes into a child module: ' + label)
                elif uses_first(value):
                    consumers.add((name, pin))
        if consumers != {(second, 'D')}:
            raise ValueError('native USB first synchronizer stage has functional fanout: ' + label)
        evidence['resets' if reset_chain else 'levels'][label] = dict(first=first, second=second,
                                                                    clock=clock, maximum_stage_flight_ns=2)
    return evidence
