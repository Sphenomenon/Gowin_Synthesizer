`timescale 1ns/1ps
`ifndef AUDIO_BEND_MEM_FILE
`define AUDIO_BEND_MEM_FILE "sim/data/audio_chain/pitch_bend_q20.mem"
`endif

module workstation_parameters #(
    parameter bit D_ONLY_ENABLE=0,
    parameter bit TF_CONTROL_ENABLE=1
) (
    input wire clk_i, rst_ni, commit_i, lifecycle_i, mode_applied_i,
    input wire [3:0] kind_i,
    input wire [6:0] address_i, value_i,
    input wire [1:0] mode_i,
    input wire [31:0] legacy_active_i,
    input wire [7:0] vector_active_i,
    input wire cue_running_i,
    output logic [1:0] requested_mode_o,
    output logic mode_pending_o,
    output logic [15:0] volume_o, expression_gain_o, pcm_gain_o,
    output wire [15:0] synth_gain_o,
    output logic [1:0] route_o,
    output logic [2:0] profile_o,
    output logic [2:0] effect_selected_o,
    output logic effect_master_o,
    output logic [1:0] effect_count_o,
    output wire [2:0] effect_mask_o,
    output logic [5:0] effect_order_o,
    output logic [21:0] target_ratio_o,
    output logic [15:0] glide_step_o,
    output logic [20:0] glide_div147_o,
    output logic [6:0] vibrato_depth_o, glide_cc_o,
    output logic [7:0] bend_index_o,
    output logic sustain_o,
    output wire [31:0] options_o, tf_control_o,
    output wire [31:0] effect_state_o,
    output logic panel_event_valid_o,
    output logic [6:0] panel_command_o,
    output logic scope_enable_o, scope_muted_o, scope_error_o,
    output logic [2:0] scope_morph_shape_o,
    output logic [6:0] scope_shape_o, scope_morph_o, scope_scale_o, scope_rotation_o,
    output logic [6:0] scope_cal_x_o, scope_cal_y_o, scope_offset_x_o, scope_offset_y_o,
    output logic [6:0] cue_speed_o,
    output logic [6:0] d_crush_o,d_drive_o,d_delay_send_o,
    output logic rejected_o
);
    logic [21:0] bend_rom [0:255];
    // A derived coefficient is committed with CC5 at the sole parameter
    // application point. No additional parameter or sample-edge latency.
    wire [15:0] glide_step_next = value_i == 0 ? 16'd0 : 16'd256 - ({9'd0,value_i} << 1);
    function automatic [20:0] glide_coefficient(input [6:0] cc);
        case(cc)
            7'd0:glide_coefficient={13'd0,8'd0};
            7'd1:glide_coefficient={13'd22,8'd68};
            7'd2:glide_coefficient={13'd22,8'd42};
            7'd3:glide_coefficient={13'd22,8'd16};
            7'd4:glide_coefficient={13'd21,8'd137};
            7'd5:glide_coefficient={13'd21,8'd111};
            7'd6:glide_coefficient={13'd21,8'd85};
            7'd7:glide_coefficient={13'd21,8'd59};
            7'd8:glide_coefficient={13'd21,8'd33};
            7'd9:glide_coefficient={13'd21,8'd7};
            7'd10:glide_coefficient={13'd20,8'd128};
            7'd11:glide_coefficient={13'd20,8'd102};
            7'd12:glide_coefficient={13'd20,8'd76};
            7'd13:glide_coefficient={13'd20,8'd50};
            7'd14:glide_coefficient={13'd20,8'd24};
            7'd15:glide_coefficient={13'd19,8'd145};
            7'd16:glide_coefficient={13'd19,8'd119};
            7'd17:glide_coefficient={13'd19,8'd93};
            7'd18:glide_coefficient={13'd19,8'd67};
            7'd19:glide_coefficient={13'd19,8'd41};
            7'd20:glide_coefficient={13'd19,8'd15};
            7'd21:glide_coefficient={13'd18,8'd136};
            7'd22:glide_coefficient={13'd18,8'd110};
            7'd23:glide_coefficient={13'd18,8'd84};
            7'd24:glide_coefficient={13'd18,8'd58};
            7'd25:glide_coefficient={13'd18,8'd32};
            7'd26:glide_coefficient={13'd18,8'd6};
            7'd27:glide_coefficient={13'd17,8'd127};
            7'd28:glide_coefficient={13'd17,8'd101};
            7'd29:glide_coefficient={13'd17,8'd75};
            7'd30:glide_coefficient={13'd17,8'd49};
            7'd31:glide_coefficient={13'd17,8'd23};
            7'd32:glide_coefficient={13'd16,8'd144};
            7'd33:glide_coefficient={13'd16,8'd118};
            7'd34:glide_coefficient={13'd16,8'd92};
            7'd35:glide_coefficient={13'd16,8'd66};
            7'd36:glide_coefficient={13'd16,8'd40};
            7'd37:glide_coefficient={13'd16,8'd14};
            7'd38:glide_coefficient={13'd15,8'd135};
            7'd39:glide_coefficient={13'd15,8'd109};
            7'd40:glide_coefficient={13'd15,8'd83};
            7'd41:glide_coefficient={13'd15,8'd57};
            7'd42:glide_coefficient={13'd15,8'd31};
            7'd43:glide_coefficient={13'd15,8'd5};
            7'd44:glide_coefficient={13'd14,8'd126};
            7'd45:glide_coefficient={13'd14,8'd100};
            7'd46:glide_coefficient={13'd14,8'd74};
            7'd47:glide_coefficient={13'd14,8'd48};
            7'd48:glide_coefficient={13'd14,8'd22};
            7'd49:glide_coefficient={13'd13,8'd143};
            7'd50:glide_coefficient={13'd13,8'd117};
            7'd51:glide_coefficient={13'd13,8'd91};
            7'd52:glide_coefficient={13'd13,8'd65};
            7'd53:glide_coefficient={13'd13,8'd39};
            7'd54:glide_coefficient={13'd13,8'd13};
            7'd55:glide_coefficient={13'd12,8'd134};
            7'd56:glide_coefficient={13'd12,8'd108};
            7'd57:glide_coefficient={13'd12,8'd82};
            7'd58:glide_coefficient={13'd12,8'd56};
            7'd59:glide_coefficient={13'd12,8'd30};
            7'd60:glide_coefficient={13'd12,8'd4};
            7'd61:glide_coefficient={13'd11,8'd125};
            7'd62:glide_coefficient={13'd11,8'd99};
            7'd63:glide_coefficient={13'd11,8'd73};
            7'd64:glide_coefficient={13'd11,8'd47};
            7'd65:glide_coefficient={13'd11,8'd21};
            7'd66:glide_coefficient={13'd10,8'd142};
            7'd67:glide_coefficient={13'd10,8'd116};
            7'd68:glide_coefficient={13'd10,8'd90};
            7'd69:glide_coefficient={13'd10,8'd64};
            7'd70:glide_coefficient={13'd10,8'd38};
            7'd71:glide_coefficient={13'd10,8'd12};
            7'd72:glide_coefficient={13'd9,8'd133};
            7'd73:glide_coefficient={13'd9,8'd107};
            7'd74:glide_coefficient={13'd9,8'd81};
            7'd75:glide_coefficient={13'd9,8'd55};
            7'd76:glide_coefficient={13'd9,8'd29};
            7'd77:glide_coefficient={13'd9,8'd3};
            7'd78:glide_coefficient={13'd8,8'd124};
            7'd79:glide_coefficient={13'd8,8'd98};
            7'd80:glide_coefficient={13'd8,8'd72};
            7'd81:glide_coefficient={13'd8,8'd46};
            7'd82:glide_coefficient={13'd8,8'd20};
            7'd83:glide_coefficient={13'd7,8'd141};
            7'd84:glide_coefficient={13'd7,8'd115};
            7'd85:glide_coefficient={13'd7,8'd89};
            7'd86:glide_coefficient={13'd7,8'd63};
            7'd87:glide_coefficient={13'd7,8'd37};
            7'd88:glide_coefficient={13'd7,8'd11};
            7'd89:glide_coefficient={13'd6,8'd132};
            7'd90:glide_coefficient={13'd6,8'd106};
            7'd91:glide_coefficient={13'd6,8'd80};
            7'd92:glide_coefficient={13'd6,8'd54};
            7'd93:glide_coefficient={13'd6,8'd28};
            7'd94:glide_coefficient={13'd6,8'd2};
            7'd95:glide_coefficient={13'd5,8'd123};
            7'd96:glide_coefficient={13'd5,8'd97};
            7'd97:glide_coefficient={13'd5,8'd71};
            7'd98:glide_coefficient={13'd5,8'd45};
            7'd99:glide_coefficient={13'd5,8'd19};
            7'd100:glide_coefficient={13'd4,8'd140};
            7'd101:glide_coefficient={13'd4,8'd114};
            7'd102:glide_coefficient={13'd4,8'd88};
            7'd103:glide_coefficient={13'd4,8'd62};
            7'd104:glide_coefficient={13'd4,8'd36};
            7'd105:glide_coefficient={13'd4,8'd10};
            7'd106:glide_coefficient={13'd3,8'd131};
            7'd107:glide_coefficient={13'd3,8'd105};
            7'd108:glide_coefficient={13'd3,8'd79};
            7'd109:glide_coefficient={13'd3,8'd53};
            7'd110:glide_coefficient={13'd3,8'd27};
            7'd111:glide_coefficient={13'd3,8'd1};
            7'd112:glide_coefficient={13'd2,8'd122};
            7'd113:glide_coefficient={13'd2,8'd96};
            7'd114:glide_coefficient={13'd2,8'd70};
            7'd115:glide_coefficient={13'd2,8'd44};
            7'd116:glide_coefficient={13'd2,8'd18};
            7'd117:glide_coefficient={13'd1,8'd139};
            7'd118:glide_coefficient={13'd1,8'd113};
            7'd119:glide_coefficient={13'd1,8'd87};
            7'd120:glide_coefficient={13'd1,8'd61};
            7'd121:glide_coefficient={13'd1,8'd35};
            7'd122:glide_coefficient={13'd1,8'd9};
            7'd123:glide_coefficient={13'd0,8'd130};
            7'd124:glide_coefficient={13'd0,8'd104};
            7'd125:glide_coefficient={13'd0,8'd78};
            7'd126:glide_coefficient={13'd0,8'd52};
            7'd127:glide_coefficient={13'd0,8'd26};
            default:glide_coefficient=21'bx;
        endcase
    endfunction
    logic [5:0] snapshot_request;
    wire [31:0] volume_product = volume_o * expression_gain_o;
    wire [1:0] mode_cycle_base = mode_pending_o ? requested_mode_o : mode_i;
    wire voices_idle = legacy_active_i == 0 && vector_active_i == 0;
    wire scope_target = value_i == 64 ? !scope_enable_o : value_i == 127;
    wire scope_transition_allowed =
        (value_i == 0 || value_i == 64 || value_i == 127) &&
        (scope_target == scope_enable_o || voices_idle);

    initial $readmemh(`AUDIO_BEND_MEM_FILE, bend_rom);
    assign synth_gain_o = volume_product[30:15];
    // Read-only CPU observation of the sole committed effect parameters.
    assign effect_state_o = {23'd0,effect_master_o,effect_count_o,effect_order_o};
    assign effect_mask_o = effect_master_o ? (effect_selected_o |
        (D_ONLY_ENABLE && d_delay_send_o!=0 ? 3'b001 : 3'b000)) : 3'b000;
    assign options_o = D_ONLY_ENABLE ? {11'd0,d_delay_send_o,d_drive_o,d_crush_o} :
        {snapshot_request, bend_index_o, glide_cc_o, vibrato_depth_o,
        sustain_o, target_ratio_o != 22'd1048576, glide_step_o != 0, vibrato_depth_o != 0};

    wire [31:0] tf_control_state;
    assign tf_control_o = TF_CONTROL_ENABLE ? tf_control_state : 32'd0;
    scope_tf_control tf_controls (
        .clk_i, .rst_ni, .event_valid_i(TF_CONTROL_ENABLE && (lifecycle_i || (commit_i && kind_i == 2))),
        .cc_i(lifecycle_i ? 7'd120 : address_i), .value_i(lifecycle_i ? 7'd0 : value_i),
        .live_enable_i(scope_enable_o), .voices_idle_i(voices_idle), .control_o(tf_control_state)
    );

    always_comb begin
        rejected_o = 0;
        if (commit_i && kind_i == 2) begin
            case (address_i)
                80,89: rejected_o = D_ONLY_ENABLE;
                90: rejected_o = D_ONLY_ENABLE || !scope_transition_allowed;
                91: rejected_o = value_i >= 8;
                95: rejected_o = value_i != 0 && value_i != 64 && value_i != 127;
                96: rejected_o = (value_i != 0 && value_i != 127) ||
                    (value_i == 127 && (tf_control_o[12] || cue_running_i ||
                    (!scope_enable_o && legacy_active_i != 0)));
                97: rejected_o = value_i >= 8 && value_i != 127;
                103: rejected_o = value_i == 0;
                // Session defaults include CC104=0. It remains an idempotent
                // off command; absent TF start/run/selection never succeeds.
                104: rejected_o = !TF_CONTROL_ENABLE && value_i != 0;
                105,106,108: rejected_o = !TF_CONTROL_ENABLE;
                default: rejected_o = 0;
            endcase
        end
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            profile_o <= 0;
            requested_mode_o <= 2;
            mode_pending_o <= 0;
            volume_o <= 32768;
            expression_gain_o <= 32768;
            pcm_gain_o <= D_ONLY_ENABLE ? 32768 : 0;
            d_crush_o<=0;d_drive_o<=0;d_delay_send_o<=0;
            route_o <= 0;
            target_ratio_o <= 1048576;
            glide_step_o <= 0;
            glide_div147_o <= 0;
            vibrato_depth_o <= 0;
            effect_selected_o <= 0;
            effect_master_o <= 1;
            effect_order_o <= 6'b10_01_00;
            effect_count_o <= 0;
            glide_cc_o <= 0;
            bend_index_o <= 128;
            snapshot_request <= 0;
            sustain_o <= 0;
            panel_event_valid_o <= 0;
            panel_command_o <= 0;
            cue_speed_o <= 64;
            scope_enable_o <= 0;
            scope_muted_o <= 0;
            scope_error_o <= 0;
            scope_morph_shape_o <= 0;
            scope_shape_o <= 127;
            scope_morph_o <= 0;
            scope_scale_o <= 127;
            scope_rotation_o <= 0;
            scope_cal_x_o <= 64;
            scope_cal_y_o <= 64;
            scope_offset_x_o <= 64;
            scope_offset_y_o <= 64;
        end else begin
            panel_event_valid_o <= 0;
            if (mode_applied_i) mode_pending_o <= 0;
            if (lifecycle_i) begin
                mode_pending_o <= 0;
                sustain_o <= 0;
                if(D_ONLY_ENABLE)begin
                    d_crush_o<=0;d_drive_o<=0;d_delay_send_o<=0;
                    effect_selected_o<=0;effect_count_o<=0;
                    effect_order_o<=6'b10_01_00;effect_master_o<=1;
                end
            end
            if (rejected_o) scope_error_o <= 1;
            if (commit_i) begin
                case (kind_i)
                    2: case (address_i)
                        1: vibrato_depth_o <= value_i;
                        5: begin
                            glide_cc_o <= value_i;
                            glide_step_o <= glide_step_next;
                            glide_div147_o <= glide_coefficient(value_i);
                        end
                        7: volume_o <= value_i == 127 ? 16'd32768 : {value_i, 8'd0};
                        11: expression_gain_o <= value_i == 127 ? 16'd32768 : {value_i, 8'd0};
                        16: pcm_gain_o <= value_i == 127 ? 16'd32768 : {value_i, 8'd0};
                        20: if(D_ONLY_ENABLE)d_crush_o<=value_i;
                        21: if(D_ONLY_ENABLE)d_drive_o<=value_i;
                        22: if(D_ONLY_ENABLE)d_delay_send_o<=value_i;
                        64: sustain_o <= value_i >= 64;
                        80: if (!D_ONLY_ENABLE && value_i < 3) begin
                            requested_mode_o <= value_i[1:0];
                            mode_pending_o <= 1;
                        end
                        81: begin
                            effect_selected_o <= value_i[2:0];
                            effect_master_o <= 1;
                            effect_count_o <= 0;
                            effect_order_o <= 6'b10_01_00;
                        end
                        82: if (value_i < 4) route_o <= value_i[1:0];
                        83: if (value_i == 127) snapshot_request <= snapshot_request + 1'b1;
                        84: if (value_i < 3) effect_order_o[1:0] <= value_i[1:0];
                        85: if (value_i < 3) effect_order_o[3:2] <= value_i[1:0];
                        86: if (value_i < 3) effect_order_o[5:4] <= value_i[1:0];
                        87: if (value_i < 3) begin
                            if (effect_count_o == 3) begin
                                effect_order_o <= 6'b11_11_11;
                                effect_selected_o <= 0;
                                effect_count_o <= 0;
                            end else if (effect_count_o == 0) begin
                                effect_order_o <= {4'b1111, value_i[1:0]};
                                effect_selected_o <= 3'b001 << value_i[1:0];
                                effect_count_o <= 1;
                                effect_master_o <= 1;
                            end else if (effect_order_o[1:0] != value_i[1:0] &&
                                (effect_count_o != 2 || effect_order_o[3:2] != value_i[1:0])) begin
                                if (effect_count_o == 1) begin
                                    effect_order_o[3:2] <= value_i[1:0];
                                    effect_count_o <= 2;
                                end else begin
                                    effect_order_o[5:4] <= value_i[1:0];
                                    effect_count_o <= 3;
                                end
                                effect_selected_o <= effect_selected_o | (3'b001 << value_i[1:0]);
                                effect_master_o <= 1;
                            end
                        end
                        88: effect_master_o <= ~effect_master_o;
                        89: if (!D_ONLY_ENABLE && value_i < 2) begin
                            requested_mode_o <= value_i[0] ?
                                (mode_cycle_base == 2 ? 0 : mode_cycle_base + 1'b1) :
                                (mode_cycle_base == 0 ? 2 : mode_cycle_base - 1'b1);
                            mode_pending_o <= 1;
                        end
                        90: if (!D_ONLY_ENABLE && scope_transition_allowed) begin
                            scope_enable_o <= scope_target;
                            scope_muted_o <= 0;
                            if (scope_target) begin effect_selected_o <= 0; effect_master_o <= 1; end
                        end
                        91: if (value_i < 8) scope_morph_shape_o <= value_i[2:0];
                        92: scope_morph_o <= value_i;
                        93: scope_scale_o <= value_i;
                        94: scope_rotation_o <= value_i;
                        95: if (!rejected_o) scope_muted_o <= value_i == 64 ? ~scope_muted_o : value_i == 127;
                        97: if (!rejected_o) scope_shape_o <= value_i;
                        98: scope_cal_x_o <= value_i;
                        99: scope_offset_x_o <= value_i;
                        100: scope_cal_y_o <= value_i;
                        101: scope_offset_y_o <= value_i;
                        103: if (value_i != 0) cue_speed_o <= value_i;
                        104: if (TF_CONTROL_ENABLE && (value_i == 64 || value_i == 127) &&
                            (tf_control_o[12] || voices_idle)) begin
                            scope_enable_o <= 0;
                            scope_muted_o <= 0;
                            effect_selected_o <= 0;
                            effect_master_o <= 1;
                        end
                        120, 123: begin sustain_o <= 0;
                            if(D_ONLY_ENABLE)begin
                                d_crush_o<=0;d_drive_o<=0;d_delay_send_o<=0;
                                effect_selected_o<=0;effect_count_o<=0;
                                effect_order_o<=6'b10_01_00;effect_master_o<=1;
                            end
                        end
                        default: begin end
                    endcase
                    3: begin
                        if (address_i < 8) profile_o <= 4;
                        else if (address_i < 16) profile_o <= 3;
                        else if (address_i >= 40 && address_i < 48) profile_o <= 1;
                        else if (address_i >= 56 && address_i < 64) profile_o <= 2;
                        else profile_o <= 0;
                    end
                    4: begin
                        target_ratio_o <= bend_rom[{value_i, address_i[6]}];
                        bend_index_o <= {value_i, address_i[6]};
                    end
                    6: begin panel_event_valid_o <= 1; panel_command_o <= address_i; end
                    default: begin end
                endcase
            end
        end
    end
endmodule
