`timescale 1ns/1ps
`default_nettype none
// Bounded worker queues around an EXTERNAL, exclusively leased existing
// effect engine. This module instantiates no reverb, DSP or history RAM.
// key/rate are committed by M, after the maintained transport/ARM boundary.
module workstation_remote_effect_stream_w #(
    parameter integer QUEUE_FRAMES=16,
    parameter integer PROCESS_TIMEOUT_CYCLES=512
)(
    input wire clk_i,reset_ni,clear_i,admitted_i,engine_lease_i,rate_44100_i,
    input wire [191:0] key_i,
    input wire req_valid_i,output wire req_ready_o,
    input wire [191:0] req_key_i,input wire req_rate_44100_i,req_enabled_i,
    input wire [31:0] req_sequence_i,
    input wire signed [31:0] req_left_i,req_right_i,
    output wire rsp_valid_o,input wire rsp_ready_i,
    output wire [191:0] rsp_key_o,output wire rsp_rate_44100_o,rsp_error_o,rsp_clip_o,
    output wire [31:0] rsp_sequence_o,
    output wire signed [31:0] rsp_left_o,rsp_right_o,
    output wire engine_claim_o,engine_clear_o,engine_config_valid_o,engine_rate_44100_o,
    input wire engine_config_ready_i,engine_config_applied_i,
    output wire engine_valid_o,engine_enabled_o,
    output wire signed [31:0] engine_left_o,engine_right_o,
    input wire engine_ready_i,engine_result_valid_i,engine_clip_i,
    input wire signed [31:0] engine_left_i,engine_right_i,
    output reg [31:0] rejected_count_o,timeout_count_o
);
    localparam integer Q=$clog2(QUEUE_FRAMES),T=$clog2(PROCESS_TIMEOUT_CYCLES);
    localparam [2:0] IDLE=0,CLEAR=1,CONFIGURE=2,CONFIG_WAIT=3,SEND=4,WAIT=5;
    reg [2:0] state;
    reg [T-1:0] timer;
    reg [191:0] key;
    reg rate,was_live,revoked,have_sequence,have_history,previous_enabled;
    reg [31:0] last_sequence,expected_sequence;
    reg [96:0] work[0:QUEUE_FRAMES-1];
    reg [97:0] results[0:QUEUE_FRAMES-1];
    reg [96:0] current;
    reg [Q-1:0] qread,qwrite,rread,rwrite;
    reg [Q:0] qcount,rcount;
    wire key_good=key[191:160]!=0 && key[159:128]!=0 && key[127:96]!=0 &&
                  key[95:64]!=0 && key[31:0]!=0;
    wire changed=key_i!=key || rate_44100_i!=rate;
    wire ownership=admitted_i && engine_lease_i;
    wire ownership_fell=was_live && !ownership;
    wire live=reset_ni && !clear_i && !changed && key_good && ownership && !revoked && !ownership_fell;
    wire request_good=req_key_i==key && req_rate_44100_i==rate &&
        (!have_sequence || req_sequence_i>last_sequence);
    wire rpop=rsp_valid_o && rsp_ready_i;
    // Reserve a result slot BEFORE starting the engine. A full result queue
    // stops background work, never an M sample or the engine's completion.
    wire qpop=live && state==IDLE && qcount!=0 && (rcount<(Q+1)'(QUEUE_FRAMES) || rpop);
    wire qpush=req_valid_i && req_ready_o && request_good;
    wire timeout_work=state!=IDLE && timer==T'(PROCESS_TIMEOUT_CYCLES-1);
    wire rpush=live && (timeout_work || (state==WAIT && engine_result_valid_i));
    assign req_ready_o=live && (!request_good || qcount<(Q+1)'(QUEUE_FRAMES) || qpop);
    assign rsp_valid_o=live && rcount!=0;
    assign rsp_key_o=key;
    assign rsp_rate_44100_o=rate;
    assign rsp_error_o=results[rread][97];
    assign rsp_clip_o=results[rread][96];
    assign rsp_sequence_o=results[rread][95:64];
    assign rsp_left_o=results[rread][63:32];
    assign rsp_right_o=results[rread][31:0];
    assign engine_claim_o=reset_ni && admitted_i && key_good && !clear_i && !changed && !revoked;
    assign engine_clear_o=engine_lease_i && (!live || state==CLEAR || timeout_work);
    assign engine_config_valid_o=live && state==CONFIGURE && !timeout_work;
    assign engine_rate_44100_o=rate;
    assign engine_valid_o=live && state==SEND && !timeout_work;
    assign engine_enabled_o=current[96];
    assign engine_left_o=current[63:32];
    assign engine_right_o=current[31:0];
    function automatic [31:0] increment(input [31:0] value);
        increment=value==32'hffffffff ? value : value+1'b1;
    endfunction
    initial if(QUEUE_FRAMES<2 || (QUEUE_FRAMES&(QUEUE_FRAMES-1))!=0 || PROCESS_TIMEOUT_CYCLES<16)
        $fatal(1,"invalid remote worker queue/timeout");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            key<=0;rate<=0;state<=IDLE;timer<=0;was_live<=0;revoked<=0;
            have_sequence<=0;have_history<=0;previous_enabled<=0;
            last_sequence<=0;expected_sequence<=0;current<=0;
            qread<=0;qwrite<=0;qcount<=0;rread<=0;rwrite<=0;rcount<=0;
            rejected_count_o<=0;timeout_count_o<=0;
        end else begin
            if(!clear_i)begin key<=key_i;rate<=rate_44100_i;end
            was_live<=ownership;
            if(clear_i)revoked<=1;
            else if(changed)revoked<=key_i==key;
            else if(ownership_fell)revoked<=1;
            if(!live)begin
                state<=IDLE;timer<=0;have_sequence<=0;have_history<=0;
                qread<=0;qwrite<=0;qcount<=0;rread<=0;rwrite<=0;rcount<=0;
            end else begin
                case({qpush,qpop})
                    2'b10:qcount<=qcount+1'b1;
                    2'b01:qcount<=qcount-1'b1;
                    default:begin end
                endcase
                if(req_valid_i && req_ready_o && !request_good)
                    rejected_count_o<=increment(rejected_count_o);
                if(qpush)begin
                    work[qwrite]<={req_enabled_i,req_sequence_i,req_left_i,req_right_i};
                    qwrite<=qwrite+1'b1;last_sequence<=req_sequence_i;have_sequence<=1;
                end
                case({rpush,rpop})
                    2'b10:rcount<=rcount+1'b1;
                    2'b01:rcount<=rcount-1'b1;
                    default:begin end
                endcase
                if(rpop)rread<=rread+1'b1;
                if(rpush)begin
                    results[rwrite]<={timeout_work,timeout_work ? 1'b0 : engine_clip_i,
                        current[95:64],timeout_work ? current[63:32] : engine_left_i,
                        timeout_work ? current[31:0] : engine_right_i};
                    rwrite<=rwrite+1'b1;
                end
                if(state==IDLE)timer<=0;else timer<=timer+1'b1;
                if(timeout_work)begin
                    state<=IDLE;have_history<=0;timeout_count_o<=increment(timeout_count_o);
                end else case(state)
                    IDLE:if(qpop)begin
                        current<=work[qread];qread<=qread+1'b1;
                        expected_sequence<=work[qread][95:64]+1'b1;
                        previous_enabled<=work[qread][96];have_history<=1;
                        state<=!have_history || work[qread][95:64]!=expected_sequence ||
                            work[qread][96]!=previous_enabled ? CLEAR : SEND;
                    end
                    CLEAR:state<=CONFIGURE;
                    CONFIGURE:if(engine_config_ready_i)state<=CONFIG_WAIT;
                    CONFIG_WAIT:if(engine_config_applied_i)state<=SEND;
                    SEND:if(engine_ready_i)state<=WAIT;
                    WAIT:if(engine_result_valid_i)state<=IDLE;
                    default:begin state<=IDLE;have_history<=0;end
                endcase
            end
        end
    end
endmodule
`default_nettype wire
