`timescale 1ns/1ps
`default_nettype none
// One bounded W request/result slot around the maintained full-precision HDL
// reverb. Transport CRC/CDC is external. New session/generation/rate or a
// sequence gap clears history before any new frame reaches the real engine.
module workstation_remote_reverb_w #(
    parameter integer PROCESS_TIMEOUT_CYCLES=256
) (
    input wire clk_i,rst_ni,
    input wire link_ready_i,
    input wire [31:0] link_session_i,
    input wire req_valid_i,
    output wire req_ready_o,
    input wire [31:0] req_session_i,req_generation_i,req_sequence_i,
    input wire req_rate_44100_i,req_enabled_i,req_reset_gain_i,
    input wire signed [31:0] req_left_i,req_right_i,
    output wire rsp_valid_o,
    input wire rsp_ready_i,
    output wire [31:0] rsp_session_o,rsp_generation_o,rsp_sequence_o,
    output wire rsp_rate_44100_o,
    output reg rsp_active_o,rsp_clip_o,rsp_error_o,
    output reg signed [31:0] rsp_left_o,rsp_right_o,
    output reg [31:0] rejected_count_o,timeout_count_o
);
    localparam [2:0] IDLE=0,CLEAR=1,CONFIGURE=2,CONFIG_WAIT=3,SEND=4,WAIT=5,RESULT=6;
    localparam integer TIMER_BITS=PROCESS_TIMEOUT_CYCLES>1 ? $clog2(PROCESS_TIMEOUT_CYCLES) : 1;
    reg [2:0] state;
    reg [TIMER_BITS-1:0] timer;
    reg have_context,have_identity,rate,enabled;
    reg [31:0] session,generation,sequence_number,expected_sequence;
    reg signed [31:0] left_q,right_q;
    wire usable_link=link_ready_i && link_session_i!=0;
    wire context_matches=have_context && req_session_i==session && req_generation_i==generation &&
        req_rate_44100_i==rate && req_sequence_i==expected_sequence;
    wire reset_gain=!have_context || req_session_i!=session || req_reset_gain_i ||
        (req_generation_i==generation && req_sequence_i!=expected_sequence);
    // Serial-number arithmetic admits wrap while rejecting duplicates/stale
    // work. An ambiguous half-range jump is rejected, never guessed newer.
    function automatic serial_newer(input [31:0] value,reference_value);
        reg [31:0] distance;
        begin
            distance=value-reference_value;
            serial_newer=distance!=0 && !distance[31];
        end
    endfunction
    wire request_good=req_session_i==link_session_i && req_generation_i!=0 &&
        (!have_identity || req_session_i!=session ||
         (req_generation_i==generation ?
            (req_rate_44100_i==rate && (req_sequence_i==expected_sequence || serial_newer(req_sequence_i,expected_sequence))) :
            serial_newer(req_generation_i,generation)));
    wire abort_work=!usable_link || (state!=IDLE && session!=link_session_i);
    wire engine_ready,engine_valid,engine_active,engine_clip,engine_config_ready,engine_config_applied;
    wire signed [31:0] engine_left,engine_right;
    wire timeout_work=state!=IDLE && state!=RESULT && timer==TIMER_BITS'(PROCESS_TIMEOUT_CYCLES-1);
    assign req_ready_o=state==IDLE && usable_link;
    assign rsp_valid_o=state==RESULT && usable_link && session==link_session_i;
    assign rsp_session_o=session;
    assign rsp_generation_o=generation;
    assign rsp_sequence_o=sequence_number;
    assign rsp_rate_44100_o=rate;
    workstation_runtime_spatial_reverb reverb(
        .clk_i,.rst_ni,.clear_i(state==CLEAR || abort_work || timeout_work),
        .valid_i(state==SEND && !abort_work),.enabled_i(enabled),.left_i(left_q),.right_i(right_q),
        .ready_o(engine_ready),.active_o(engine_active),.valid_o(engine_valid),
        .left_o(engine_left),.right_o(engine_right),.clip_o(engine_clip),
        .config_valid_i(state==CONFIGURE && !abort_work),.rate_44100_i(rate),.history_clear_i(1'b0),
        .config_ready_o(engine_config_ready),.config_applied_o(engine_config_applied),
        .history_ready_o(),.history_done_o(),.quiescent_o(),.applied_rate_44100_o());
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            state<=IDLE;timer<=0;have_context<=0;have_identity<=0;rate<=0;enabled<=0;
            session<=0;generation<=0;sequence_number<=0;expected_sequence<=0;left_q<=0;right_q<=0;
            rsp_active_o<=0;rsp_clip_o<=0;rsp_error_o<=0;rsp_left_o<=0;rsp_right_o<=0;
            rejected_count_o<=0;timeout_count_o<=0;
        end else if(abort_work)begin
            state<=IDLE;timer<=0;have_context<=0;rsp_active_o<=0;rsp_error_o<=0;
        end else begin
            if(state==IDLE || state==RESULT)timer<=0;
            else timer<=timer+1'b1;
            if(timeout_work)begin
                have_context<=0;rsp_error_o<=1;rsp_active_o<=0;rsp_clip_o<=0;
                rsp_left_o<=left_q;rsp_right_o<=right_q;state<=RESULT;
                if(timeout_count_o!=32'hffff_ffff)timeout_count_o<=timeout_count_o+1'b1;
            end else case(state)
                IDLE:if(req_valid_i && req_ready_o)begin
                    if(request_good)begin
                        session<=req_session_i;generation<=req_generation_i;sequence_number<=req_sequence_i;
                        expected_sequence<=req_sequence_i+1'b1;rate<=req_rate_44100_i;enabled<=req_enabled_i;
                        left_q<=req_left_i;right_q<=req_right_i;rsp_error_o<=0;
                        have_context<=1;have_identity<=1;state<=context_matches ? SEND : reset_gain ? CLEAR : CONFIGURE;
                    end else if(rejected_count_o!=32'hffff_ffff)rejected_count_o<=rejected_count_o+1'b1;
                end
                CLEAR:state<=CONFIGURE;
                CONFIGURE:if(engine_config_ready)state<=CONFIG_WAIT;
                CONFIG_WAIT:if(engine_config_applied)state<=SEND;
                SEND:if(engine_ready)state<=WAIT;
                WAIT:if(engine_valid)begin
                    rsp_left_o<=engine_left;rsp_right_o<=engine_right;rsp_clip_o<=engine_clip;
                    rsp_active_o<=engine_active;rsp_error_o<=0;state<=RESULT;
                end
                RESULT:if(rsp_ready_i)state<=IDLE;
                default:begin state<=IDLE;have_context<=0;end
            endcase
        end
    end
`ifndef SYNTHESIS
    initial if(PROCESS_TIMEOUT_CYCLES<8)
        $fatal(1,"remote reverb worker timeout too short");
`endif
endmodule
`default_nettype wire
