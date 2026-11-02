`timescale 1ns/1ps
`ifndef AUDIO_BEND_MEM_FILE
`define AUDIO_BEND_MEM_FILE "sim/data/audio_chain/pitch_bend_q20.mem"
`endif

module workstation_parameters #(
    parameter bit D_ONLY_ENABLE=0,
    parameter bit TF_CONTROL_ENABLE=1,
    parameter bit CNN_DEMO_MINIMAL=0
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
    assign options_o = D_ONLY_ENABLE ? {3'd0,bend_index_o,d_delay_send_o,d_drive_o,d_crush_o} :
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
        // The filming profile has one basic instrument and a dry output. Keep
        // unsupported controls out of this sole committed parameter state.
        if (CNN_DEMO_MINIMAL && commit_i) begin
            if (kind_i == 3 || kind_i == 4) rejected_o = 1;
            if (kind_i == 2 && (address_i == 1 || address_i == 5 ||
                (address_i >= 80 && address_i <= 103))) rejected_o = 1;
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
                    target_ratio_o<=22'd1048576;bend_index_o<=8'd128;
                    effect_selected_o<=0;effect_count_o<=0;
                    effect_order_o<=6'b10_01_00;effect_master_o<=1;
                end
            end
            if (rejected_o) scope_error_o <= 1;
            if (commit_i && !(CNN_DEMO_MINIMAL && rejected_o)) begin
                case (kind_i)
                    2: case (address_i)
                        1: vibrato_depth_o <= value_i;
                        5: begin
                            glide_cc_o <= value_i;
                            glide_step_o <= value_i == 0 ? 16'd0 : 16'd256 - ({9'd0, value_i} << 1);
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
                                target_ratio_o<=22'd1048576;bend_index_o<=8'd128;
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
