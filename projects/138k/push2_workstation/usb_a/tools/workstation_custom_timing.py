"""Checked native-board timing adaptations; never change frozen inputs."""

import hashlib
import re

from tools.workstation_synthesis_netlist import SynthesisNetlist


INPUTS = {
    'src/migration/gw138k_audio_clock.v': 'ea421ccc44dbb6b81f85645cd79a307e6750e2140c2a070057756f781c9c8d54',
    'legacy/rtl/audio/sine_interp.sv': '1085c7ebba307faa6ea7d10d99c6111a253d1f383e13fefef81c595a7d8b2b61',
    'src/storage/tf_audio_ddr_dma.v': 'd37ff20c676049fe8cc53adfb7db43e30553f3824e62e57c58493a1042649e3b',
    'legacy/rtl/audio/unified_oscillator_engine.sv': '2bf573382c5c93212a196de483703ff5edc5cd4f1d67983841c28f64bc851423',
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
    return once(text, original, replacement)


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


TRANSFORMS = dict(zip(INPUTS, (audio_pll, sine_address, byte_increment, voice_controls)))


def apply(stage):
    evidence = {}
    for relative, expected in INPUTS.items():
        source = stage / relative
        before = source.read_bytes()
        if hashlib.sha256(before).hexdigest() != expected:
            raise ValueError('native timing adaptation input identity drifted: ' + relative)
        after = TRANSFORMS[relative](before.decode()).encode()
        source.write_bytes(after)
        evidence[relative] = dict(before=expected, after=hashlib.sha256(after).hexdigest(),
                                  transform=TRANSFORMS[relative].__name__)
    return evidence


def constraints():
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
    phy = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
    lines.append(f'set_min_delay 0.800 -from [get_pins {{{phy}/ddr_init_internal_r_s0/Q}}] -to [get_pins {{{phy}/wloadn_3_s0/D}}]')
    for kind in ('setup', 'hold', 'recovery', 'removal'):
        lines.append(f'report_timing -{kind} -max_paths 2000 -max_common_paths 1')
    return '\n'.join(lines) + '\n'


def audit_resets(text, clocks):
    netlist = SynthesisNetlist(text, 'workstation_custom_138k_top')
    constants = {"1'b1"} | {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    evidence = dict(resets={}, levels={})

    def register(stem):
        matches = [name for name, cell in netlist.cells.items()
                   if cell['kind'].startswith('DFF') and re.fullmatch(re.escape(stem) + r'_s\d+', name)]
        if len(matches) != 1:
            raise ValueError('native USB synchronizer inventory changed: ' + stem)
        return matches[0]

    chains = [(prefix, prefix + '_0', prefix + '_1', clock, True, True) for prefix, clock in RESET_CHAINS.items()]
    chains += [(prefix + ':' + str(stage), prefix + '_' + str(stage), prefix + '_' + str(stage+1), clock, True, stage==0)
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
