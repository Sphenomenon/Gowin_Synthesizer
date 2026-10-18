`timescale 1ns/1ps
// Final pin ownership only: both producers and TF->Basic Pitch keep running.
// All inputs are in the 76.8 MHz audio domain. Scope mode owns the synth DAC
// even while muted/idle, so a live mute never falls back to prerecorded TF.
module scope_dac_select (
    input wire clk_i,rst_ni,
    input wire scope_enable_i,tf_source_active_i,
    input wire synth_frame_tick_i,tf_frame_tick_i,
    input wire synth_bck_i,synth_ws_i,synth_din_i,synth_pa_i,
    input wire tf_bck_i,tf_ws_i,tf_din_i,tf_pa_i,
    output wire hp_bck_o,hp_ws_o,hp_din_o,pa_en_o,
    output wire tf_selected_o,switching_o
);
    localparam [1:0] ACTIVE=0,WAIT_FRAME=1,SETTLE=2;
    reg [1:0] state;
    reg selected_tf,settle_frame;
    wire requested_tf=tf_source_active_i && !scope_enable_i;
    wire current_bck=selected_tf ? tf_bck_i : synth_bck_i;
    wire current_tick=selected_tf ? tf_frame_tick_i : synth_frame_tick_i;
    wire target_bck=requested_tf ? tf_bck_i : synth_bck_i;
    wire target_tick=requested_tf ? tf_frame_tick_i : synth_frame_tick_i;
    assign tf_selected_o=selected_tf;
    assign switching_o=state!=ACTIVE;
    // Quiesce only after the previous producer's falling BCK edge; reconnect
    // at the new producer's right-slot MSB. Never create a mux-induced rising
    // edge or expose a partial stereo pair through the amplifier. NS4263
    // shutdown is HIGH. Two complete target frames settle before unmuting.
    assign hp_bck_o=(!rst_ni || state==WAIT_FRAME) ? 1'b0 : current_bck;
    assign hp_ws_o=(!rst_ni || state==WAIT_FRAME) ? 1'b1 :
        (selected_tf ? tf_ws_i : synth_ws_i);
    assign hp_din_o=(!rst_ni || state==WAIT_FRAME) ? 1'b0 :
        (selected_tf ? tf_din_i : synth_din_i);
    assign pa_en_o=!rst_ni || state!=ACTIVE ||
        (selected_tf ? tf_pa_i : synth_pa_i);
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin state<=WAIT_FRAME;selected_tf<=0;settle_frame<=0;end
        else case(state)
            ACTIVE: if(requested_tf!=selected_tf && !current_bck)
                state<=WAIT_FRAME;
            WAIT_FRAME: if(target_tick && !target_bck) begin
                selected_tf<=requested_tf;settle_frame<=0;state<=SETTLE;
            end
            SETTLE: begin
                if(requested_tf!=selected_tf && !current_bck) state<=WAIT_FRAME;
                else if(requested_tf==selected_tf && current_tick) begin
                    if(settle_frame) state<=ACTIVE;
                    else settle_frame<=1;
                end
            end
            default: begin state<=WAIT_FRAME;settle_frame<=0;end
        endcase
    end
endmodule
