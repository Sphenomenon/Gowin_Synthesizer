"""Exact lineage for coefficients committed with the authoritative CC5 state.

Production RTL is versioned in its owners. This read-only adapter reverses
only the complete coefficient change for the existing dispatch provenance;
it never generates or changes RTL, and grants no physical acceptance.
"""
import hashlib
from pathlib import Path

PARENT_SHA256 = {'rtl/audio/gw138k_event_workstation.sv': '3082f2411b658903a869a77a78f19987f07577a11f42271c9155599c643d1d87',
 'rtl/audio/workstation_rate_pitch_expression.sv': 'cee08fb91740f874fd25eea1702bcb3dae59da0c6aabea4bba0c0ec8957170a9',
 'rtl/audio/workstation_runtime_render_engines.sv': '56a9d0719f0896fd61c16e274168d1b54ad6b5710d4cd9f781762ee6f47a9d57',
 'rtl/control/workstation_parameters.sv': '47437fb03ad79e55cb3836df73ec0b66772bab8f2d315be366cb02964a0468a2'}
SELECTED_SHA256 = {'rtl/audio/gw138k_event_workstation.sv': '029f9e767698a932fcef746ef1a0fb6a83e937330ba0685cd73e3943fb9fb180',
 'rtl/audio/workstation_rate_pitch_expression.sv': '22ceb7fad98bbef4a13dfdfa854caad9fe439fa87474280cd20cd5730405467b',
 'rtl/audio/workstation_runtime_render_engines.sv': '437d0b973162aea7f300683df5d34ba002b06f2fed5bb09696881bf4601783b0',
 'rtl/control/workstation_parameters.sv': '507a0729e7e48811b2d1786c60a542e0f17b14bf2fa84467771de9806cb51ae2'}
HUNKS = {'rtl/audio/gw138k_event_workstation.sv': [('  logic [15:0] glide_step;\n'
                                            '  logic [6:0] vibrato_depth, glide_cc;\n',
                                            '  logic [15:0] glide_step;\n'
                                            '  wire [20:0] glide_div147;\n'
                                            '  logic [6:0] vibrato_depth, glide_cc;\n'),
                                           ('      .glide_step_o(glide_step),\n'
                                            '      .vibrato_depth_o(vibrato_depth),\n',
                                            '      .glide_step_o(glide_step),\n'
                                            '      .glide_div147_o(glide_div147),\n'
                                            '      .vibrato_depth_o(vibrato_depth),\n'),
                                           ('  end else if(RUNTIME_RATE_ENABLE) begin: runtime_engines\n'
                                            '    workstation_runtime_render_engines '
                                            '#(.RUNTIME_RATE_ENABLE(1)) engines(\n'
                                            '      '
                                            '.clk_i,.rst_ni,.panic_i(engine_clear),.sample_ce_i(core_ce),\n',
                                            '  end else if(RUNTIME_RATE_ENABLE) begin: runtime_engines\n'
                                            '    workstation_runtime_render_engines '
                                            '#(.RUNTIME_RATE_ENABLE(1),.COMMITTED_GLIDE_COEFFICIENT(1)) '
                                            'engines(\n'
                                            '      '
                                            '.clk_i,.rst_ni,.panic_i(engine_clear),.sample_ce_i(core_ce),\n'),
                                           ('      '
                                            '.target_ratio_q20_i(target_ratio),.glide_step_q20_i(glide_step),\n'
                                            '      .vibrato_depth_i(vibrato_depth),.pitch_q20_o,\n',
                                            '      '
                                            '.target_ratio_q20_i(target_ratio),.glide_step_q20_i(glide_step),\n'
                                            '      .glide_div147_i(glide_div147),\n'
                                            '      .vibrato_depth_i(vibrato_depth),.pitch_q20_o,\n')],
 'rtl/audio/workstation_rate_pitch_expression.sv': [('// the same committed value as the oscillator at each '
                                                     'sample enable.\n'
                                                     'module workstation_rate_pitch_expression (\n'
                                                     '    input logic clk_i, rst_ni, sample_ce_i, '
                                                     'rate_44k1_i,\n',
                                                     '// the same committed value as the oscillator at each '
                                                     'sample enable.\n'
                                                     'module workstation_rate_pitch_expression #(\n'
                                                     '    parameter bit COMMITTED_GLIDE_COEFFICIENT=0\n'
                                                     ') (\n'
                                                     '    input logic clk_i, rst_ni, sample_ce_i, '
                                                     'rate_44k1_i,\n'),
                                                    ('    input logic [15:0] glide_step_q20_i,\n'
                                                     '    input logic [6:0] vibrato_depth_i,\n',
                                                     '    input logic [15:0] glide_step_q20_i,\n'
                                                     '    input logic [20:0] glide_div147_i,\n'
                                                     '    input logic [6:0] vibrato_depth_i,\n'),
                                                    ('    wire [9:0] '
                                                     "glide_remainder_high={2'd0,glide_digit_remainder[2]}+{2'd0,glide_digit_remainder[3]};\n"
                                                     '    wire [9:0] '
                                                     "glide_remainder_sum=glide_remainder_low+glide_remainder_high+{2'd0,glide_remainder};\n"
                                                     '    wire [10:0] glide_trial[1:5];\n',
                                                     '    wire [9:0] '
                                                     "glide_remainder_high={2'd0,glide_digit_remainder[2]}+{2'd0,glide_digit_remainder[3]};\n"
                                                     '    wire [9:0] '
                                                     'glide_remainder_sum=COMMITTED_GLIDE_COEFFICIENT\n'
                                                     '        ? '
                                                     "{2'd0,glide_div147_i[7:0]}+{2'd0,glide_remainder}\n"
                                                     '        : '
                                                     "glide_remainder_low+glide_remainder_high+{2'd0,glide_remainder};\n"
                                                     '    wire [10:0] glide_trial[1:5];\n'),
                                                    ("        !glide_trial[3][10] ? 3'd3 : "
                                                     "!glide_trial[2][10] ? 3'd2 : !glide_trial[1][10] ? "
                                                     "3'd1 : 3'd0;\n"
                                                     '    wire [12:0] '
                                                     "glide_extra_step=glide_quotient_low+glide_quotient_high+{10'd0,glide_carry};\n"
                                                     '    wire [7:0] '
                                                     'next_glide_remainder=!glide_trial[5][10] ? '
                                                     'glide_trial[5][7:0] :\n',
                                                     "        !glide_trial[3][10] ? 3'd3 : "
                                                     "!glide_trial[2][10] ? 3'd2 : !glide_trial[1][10] ? "
                                                     "3'd1 : 3'd0;\n"
                                                     '    wire [12:0] '
                                                     'glide_extra_step=COMMITTED_GLIDE_COEFFICIENT\n'
                                                     "        ? glide_div147_i[20:8]+{10'd0,glide_carry}\n"
                                                     '        : '
                                                     "glide_quotient_low+glide_quotient_high+{10'd0,glide_carry};\n"
                                                     '    wire [7:0] '
                                                     'next_glide_remainder=!glide_trial[5][10] ? '
                                                     'glide_trial[5][7:0] :\n')],
 'rtl/audio/workstation_runtime_render_engines.sv': [('module workstation_runtime_render_engines #(\n'
                                                      '    parameter bit RUNTIME_RATE_ENABLE=0\n'
                                                      ') (\n',
                                                      'module workstation_runtime_render_engines #(\n'
                                                      '    parameter bit RUNTIME_RATE_ENABLE=0,\n'
                                                      '    parameter bit COMMITTED_GLIDE_COEFFICIENT=0\n'
                                                      ') (\n'),
                                                     ('    input logic [15:0] glide_step_q20_i,\n'
                                                      '    input logic [6:0] vibrato_depth_i,\n',
                                                      '    input logic [15:0] glide_step_q20_i,\n'
                                                      '    input logic [20:0] glide_div147_i,\n'
                                                      '    input logic [6:0] vibrato_depth_i,\n'),
                                                     ('\n'
                                                      '    workstation_rate_pitch_expression pitch (\n'
                                                      '        .clk_i, .rst_ni, .sample_ce_i, '
                                                      '.rate_44k1_i(applied_rate_44100_o),\n',
                                                      '\n'
                                                      '    workstation_rate_pitch_expression '
                                                      '#(.COMMITTED_GLIDE_COEFFICIENT(COMMITTED_GLIDE_COEFFICIENT)) '
                                                      'pitch (\n'
                                                      '        .clk_i, .rst_ni, .sample_ce_i, '
                                                      '.rate_44k1_i(applied_rate_44100_o),\n'),
                                                     ('        .clk_i, .rst_ni, .sample_ce_i, '
                                                      '.rate_44k1_i(applied_rate_44100_o),\n'
                                                      '        .target_ratio_q20_i, .glide_step_q20_i, '
                                                      '.vibrato_depth_i,\n'
                                                      '        .ratio_q20_o(pitch_q20_o)\n',
                                                      '        .clk_i, .rst_ni, .sample_ce_i, '
                                                      '.rate_44k1_i(applied_rate_44100_o),\n'
                                                      '        .target_ratio_q20_i, .glide_step_q20_i, '
                                                      '.glide_div147_i, .vibrato_depth_i,\n'
                                                      '        .ratio_q20_o(pitch_q20_o)\n')],
 'rtl/control/workstation_parameters.sv': [('    output logic [15:0] glide_step_o,\n'
                                            '    output logic [6:0] vibrato_depth_o, glide_cc_o,\n',
                                            '    output logic [15:0] glide_step_o,\n'
                                            '    output logic [20:0] glide_div147_o,\n'
                                            '    output logic [6:0] vibrato_depth_o, glide_cc_o,\n'),
                                           ('    logic [21:0] bend_rom [0:255];\n'
                                            '    logic [5:0] snapshot_request;\n',
                                            '    logic [21:0] bend_rom [0:255];\n'
                                            '    // A derived coefficient is committed with CC5 at the sole '
                                            'parameter\n'
                                            '    // application point. No additional parameter or '
                                            'sample-edge latency.\n'
                                            "    wire [15:0] glide_step_next = value_i == 0 ? 16'd0 : "
                                            "16'd256 - ({9'd0,value_i} << 1);\n"
                                            '    function automatic [20:0] glide_coefficient(input [6:0] '
                                            'cc);\n'
                                            '        case(cc)\n'
                                            "            7'd0:glide_coefficient={13'd0,8'd0};\n"
                                            "            7'd1:glide_coefficient={13'd22,8'd68};\n"
                                            "            7'd2:glide_coefficient={13'd22,8'd42};\n"
                                            "            7'd3:glide_coefficient={13'd22,8'd16};\n"
                                            "            7'd4:glide_coefficient={13'd21,8'd137};\n"
                                            "            7'd5:glide_coefficient={13'd21,8'd111};\n"
                                            "            7'd6:glide_coefficient={13'd21,8'd85};\n"
                                            "            7'd7:glide_coefficient={13'd21,8'd59};\n"
                                            "            7'd8:glide_coefficient={13'd21,8'd33};\n"
                                            "            7'd9:glide_coefficient={13'd21,8'd7};\n"
                                            "            7'd10:glide_coefficient={13'd20,8'd128};\n"
                                            "            7'd11:glide_coefficient={13'd20,8'd102};\n"
                                            "            7'd12:glide_coefficient={13'd20,8'd76};\n"
                                            "            7'd13:glide_coefficient={13'd20,8'd50};\n"
                                            "            7'd14:glide_coefficient={13'd20,8'd24};\n"
                                            "            7'd15:glide_coefficient={13'd19,8'd145};\n"
                                            "            7'd16:glide_coefficient={13'd19,8'd119};\n"
                                            "            7'd17:glide_coefficient={13'd19,8'd93};\n"
                                            "            7'd18:glide_coefficient={13'd19,8'd67};\n"
                                            "            7'd19:glide_coefficient={13'd19,8'd41};\n"
                                            "            7'd20:glide_coefficient={13'd19,8'd15};\n"
                                            "            7'd21:glide_coefficient={13'd18,8'd136};\n"
                                            "            7'd22:glide_coefficient={13'd18,8'd110};\n"
                                            "            7'd23:glide_coefficient={13'd18,8'd84};\n"
                                            "            7'd24:glide_coefficient={13'd18,8'd58};\n"
                                            "            7'd25:glide_coefficient={13'd18,8'd32};\n"
                                            "            7'd26:glide_coefficient={13'd18,8'd6};\n"
                                            "            7'd27:glide_coefficient={13'd17,8'd127};\n"
                                            "            7'd28:glide_coefficient={13'd17,8'd101};\n"
                                            "            7'd29:glide_coefficient={13'd17,8'd75};\n"
                                            "            7'd30:glide_coefficient={13'd17,8'd49};\n"
                                            "            7'd31:glide_coefficient={13'd17,8'd23};\n"
                                            "            7'd32:glide_coefficient={13'd16,8'd144};\n"
                                            "            7'd33:glide_coefficient={13'd16,8'd118};\n"
                                            "            7'd34:glide_coefficient={13'd16,8'd92};\n"
                                            "            7'd35:glide_coefficient={13'd16,8'd66};\n"
                                            "            7'd36:glide_coefficient={13'd16,8'd40};\n"
                                            "            7'd37:glide_coefficient={13'd16,8'd14};\n"
                                            "            7'd38:glide_coefficient={13'd15,8'd135};\n"
                                            "            7'd39:glide_coefficient={13'd15,8'd109};\n"
                                            "            7'd40:glide_coefficient={13'd15,8'd83};\n"
                                            "            7'd41:glide_coefficient={13'd15,8'd57};\n"
                                            "            7'd42:glide_coefficient={13'd15,8'd31};\n"
                                            "            7'd43:glide_coefficient={13'd15,8'd5};\n"
                                            "            7'd44:glide_coefficient={13'd14,8'd126};\n"
                                            "            7'd45:glide_coefficient={13'd14,8'd100};\n"
                                            "            7'd46:glide_coefficient={13'd14,8'd74};\n"
                                            "            7'd47:glide_coefficient={13'd14,8'd48};\n"
                                            "            7'd48:glide_coefficient={13'd14,8'd22};\n"
                                            "            7'd49:glide_coefficient={13'd13,8'd143};\n"
                                            "            7'd50:glide_coefficient={13'd13,8'd117};\n"
                                            "            7'd51:glide_coefficient={13'd13,8'd91};\n"
                                            "            7'd52:glide_coefficient={13'd13,8'd65};\n"
                                            "            7'd53:glide_coefficient={13'd13,8'd39};\n"
                                            "            7'd54:glide_coefficient={13'd13,8'd13};\n"
                                            "            7'd55:glide_coefficient={13'd12,8'd134};\n"
                                            "            7'd56:glide_coefficient={13'd12,8'd108};\n"
                                            "            7'd57:glide_coefficient={13'd12,8'd82};\n"
                                            "            7'd58:glide_coefficient={13'd12,8'd56};\n"
                                            "            7'd59:glide_coefficient={13'd12,8'd30};\n"
                                            "            7'd60:glide_coefficient={13'd12,8'd4};\n"
                                            "            7'd61:glide_coefficient={13'd11,8'd125};\n"
                                            "            7'd62:glide_coefficient={13'd11,8'd99};\n"
                                            "            7'd63:glide_coefficient={13'd11,8'd73};\n"
                                            "            7'd64:glide_coefficient={13'd11,8'd47};\n"
                                            "            7'd65:glide_coefficient={13'd11,8'd21};\n"
                                            "            7'd66:glide_coefficient={13'd10,8'd142};\n"
                                            "            7'd67:glide_coefficient={13'd10,8'd116};\n"
                                            "            7'd68:glide_coefficient={13'd10,8'd90};\n"
                                            "            7'd69:glide_coefficient={13'd10,8'd64};\n"
                                            "            7'd70:glide_coefficient={13'd10,8'd38};\n"
                                            "            7'd71:glide_coefficient={13'd10,8'd12};\n"
                                            "            7'd72:glide_coefficient={13'd9,8'd133};\n"
                                            "            7'd73:glide_coefficient={13'd9,8'd107};\n"
                                            "            7'd74:glide_coefficient={13'd9,8'd81};\n"
                                            "            7'd75:glide_coefficient={13'd9,8'd55};\n"
                                            "            7'd76:glide_coefficient={13'd9,8'd29};\n"
                                            "            7'd77:glide_coefficient={13'd9,8'd3};\n"
                                            "            7'd78:glide_coefficient={13'd8,8'd124};\n"
                                            "            7'd79:glide_coefficient={13'd8,8'd98};\n"
                                            "            7'd80:glide_coefficient={13'd8,8'd72};\n"
                                            "            7'd81:glide_coefficient={13'd8,8'd46};\n"
                                            "            7'd82:glide_coefficient={13'd8,8'd20};\n"
                                            "            7'd83:glide_coefficient={13'd7,8'd141};\n"
                                            "            7'd84:glide_coefficient={13'd7,8'd115};\n"
                                            "            7'd85:glide_coefficient={13'd7,8'd89};\n"
                                            "            7'd86:glide_coefficient={13'd7,8'd63};\n"
                                            "            7'd87:glide_coefficient={13'd7,8'd37};\n"
                                            "            7'd88:glide_coefficient={13'd7,8'd11};\n"
                                            "            7'd89:glide_coefficient={13'd6,8'd132};\n"
                                            "            7'd90:glide_coefficient={13'd6,8'd106};\n"
                                            "            7'd91:glide_coefficient={13'd6,8'd80};\n"
                                            "            7'd92:glide_coefficient={13'd6,8'd54};\n"
                                            "            7'd93:glide_coefficient={13'd6,8'd28};\n"
                                            "            7'd94:glide_coefficient={13'd6,8'd2};\n"
                                            "            7'd95:glide_coefficient={13'd5,8'd123};\n"
                                            "            7'd96:glide_coefficient={13'd5,8'd97};\n"
                                            "            7'd97:glide_coefficient={13'd5,8'd71};\n"
                                            "            7'd98:glide_coefficient={13'd5,8'd45};\n"
                                            "            7'd99:glide_coefficient={13'd5,8'd19};\n"
                                            "            7'd100:glide_coefficient={13'd4,8'd140};\n"
                                            "            7'd101:glide_coefficient={13'd4,8'd114};\n"
                                            "            7'd102:glide_coefficient={13'd4,8'd88};\n"
                                            "            7'd103:glide_coefficient={13'd4,8'd62};\n"
                                            "            7'd104:glide_coefficient={13'd4,8'd36};\n"
                                            "            7'd105:glide_coefficient={13'd4,8'd10};\n"
                                            "            7'd106:glide_coefficient={13'd3,8'd131};\n"
                                            "            7'd107:glide_coefficient={13'd3,8'd105};\n"
                                            "            7'd108:glide_coefficient={13'd3,8'd79};\n"
                                            "            7'd109:glide_coefficient={13'd3,8'd53};\n"
                                            "            7'd110:glide_coefficient={13'd3,8'd27};\n"
                                            "            7'd111:glide_coefficient={13'd3,8'd1};\n"
                                            "            7'd112:glide_coefficient={13'd2,8'd122};\n"
                                            "            7'd113:glide_coefficient={13'd2,8'd96};\n"
                                            "            7'd114:glide_coefficient={13'd2,8'd70};\n"
                                            "            7'd115:glide_coefficient={13'd2,8'd44};\n"
                                            "            7'd116:glide_coefficient={13'd2,8'd18};\n"
                                            "            7'd117:glide_coefficient={13'd1,8'd139};\n"
                                            "            7'd118:glide_coefficient={13'd1,8'd113};\n"
                                            "            7'd119:glide_coefficient={13'd1,8'd87};\n"
                                            "            7'd120:glide_coefficient={13'd1,8'd61};\n"
                                            "            7'd121:glide_coefficient={13'd1,8'd35};\n"
                                            "            7'd122:glide_coefficient={13'd1,8'd9};\n"
                                            "            7'd123:glide_coefficient={13'd0,8'd130};\n"
                                            "            7'd124:glide_coefficient={13'd0,8'd104};\n"
                                            "            7'd125:glide_coefficient={13'd0,8'd78};\n"
                                            "            7'd126:glide_coefficient={13'd0,8'd52};\n"
                                            "            7'd127:glide_coefficient={13'd0,8'd26};\n"
                                            "            default:glide_coefficient=21'bx;\n"
                                            '        endcase\n'
                                            '    endfunction\n'
                                            '    logic [5:0] snapshot_request;\n'),
                                           ('            glide_step_o <= 0;\n'
                                            '            vibrato_depth_o <= 0;\n',
                                            '            glide_step_o <= 0;\n'
                                            '            glide_div147_o <= 0;\n'
                                            '            vibrato_depth_o <= 0;\n'),
                                           ('                            glide_cc_o <= value_i;\n'
                                            '                            glide_step_o <= value_i == 0 ? '
                                            "16'd0 : 16'd256 - ({9'd0, value_i} << 1);\n"
                                            '                        end\n',
                                            '                            glide_cc_o <= value_i;\n'
                                            '                            glide_step_o <= glide_step_next;\n'
                                            '                            glide_div147_o <= '
                                            'glide_coefficient(value_i);\n'
                                            '                        end\n')]}

def normalize(relative, source):
    relative = str(relative)
    try:
        from tools.workstation_inner_event_queue import restore as queue_parent
    except ModuleNotFoundError:
        from workstation_inner_event_queue import restore as queue_parent
    source=queue_parent(relative,source)
    if relative not in PARENT_SHA256:
        return source
    digest = hashlib.sha256(source).hexdigest()
    if digest == PARENT_SHA256[relative]:
        return source
    if digest != SELECTED_SHA256[relative]:
        raise ValueError('committed glide source drift: ' + relative)
    text = source.decode()
    for before, after in reversed(HUNKS[relative]):
        if text.count(after) != 1:
            raise ValueError('committed glide inverse anchor drift: ' + relative)
        text = text.replace(after, before, 1)
    parent = text.encode()
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256[relative]:
        raise ValueError('committed glide parent drift: ' + relative)
    for before, after in HUNKS[relative]:
        if text.count(before) != 1:
            raise ValueError('committed glide forward anchor drift: ' + relative)
        text = text.replace(before, after, 1)
    if text.encode() != source:
        raise ValueError('committed glide roundtrip drift: ' + relative)
    return parent


def source_bundle(root):
    rows = {}
    for relative in PARENT_SHA256:
        source = (Path(root)/relative).read_bytes()
        parent = normalize(relative, source)
        rows[relative] = dict(selected_sha256=hashlib.sha256(source).hexdigest(),
            parent_sha256=hashlib.sha256(parent).hexdigest(), exact_inverse=True)
    return dict(policy='authoritative_CC5_div147_coefficient_commit_v1', owners=rows,
        additional_sample_latency_clocks=0, second_parameter_authority=False,
        timing_closed=False, hardware_tested=False)
