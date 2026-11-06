`timescale 1ns/1ps
`default_nettype none
// Optional effect boundary, not a wire protocol. Every input frame has a
// fixed DELAY_FRAMES local dry deadline; transport never supplies ready_o.
// key={Mboot,Wboot,linkSession,mediaGeneration,parameterRevision,audioEpoch}.
// All sidebands are local-clock signals; transport validation/CDC is external.
module workstation_remote_effect_stream_m #(
    parameter integer DELAY_FRAMES=64,
    parameter integer QUEUE_FRAMES=16
)(
    input wire clk_i,reset_ni,clear_i,admitted_i,rate_44100_i,enabled_i,
    input wire [191:0] key_i,
    input wire valid_i,input wire signed [31:0] left_i,right_i,
    output wire ready_o,output reg valid_o,
    output reg signed [31:0] left_o,right_o,output reg clip_o,
    output wire req_valid_o,input wire req_ready_i,
    output wire [191:0] req_key_o,output wire req_rate_44100_o,req_enabled_o,
    output wire [31:0] req_sequence_o,
    output wire signed [31:0] req_left_o,req_right_o,
    input wire rsp_valid_i,output wire rsp_ready_o,
    input wire [191:0] rsp_key_i,input wire rsp_rate_44100_i,rsp_error_i,rsp_clip_i,
    input wire [31:0] rsp_sequence_i,
    input wire signed [31:0] rsp_left_i,rsp_right_i,
    output reg [31:0] overflow_count_o,expired_count_o,fallback_count_o,rejected_count_o,
    output wire revoked_o,exhausted_o
);
    localparam integer D=$clog2(DELAY_FRAMES),Q=$clog2(QUEUE_FRAMES);
    reg [191:0] key;
    reg rate,was_admitted,revoked,exhausted;
    reg [31:0] sequence_number;
    reg [D-1:0] cursor;
    reg [D:0] filled;
    reg signed [31:0] dry_l[0:DELAY_FRAMES-1],dry_r[0:DELAY_FRAMES-1];
    reg signed [31:0] wet_l[0:DELAY_FRAMES-1],wet_r[0:DELAY_FRAMES-1];
    reg [31:0] tags[0:DELAY_FRAMES-1];
    reg [DELAY_FRAMES-1:0] issued,wet_valid,wet_clip,frame_enabled;
    reg [96:0] queue[0:QUEUE_FRAMES-1];
    reg [Q-1:0] qread,qwrite;
    reg [Q:0] qcount;
    wire changed=key_i!=key || rate_44100_i!=rate;
    wire key_good=key[191:160]!=0 && key[159:128]!=0 && key[127:96]!=0 &&
                  key[95:64]!=0 && key[31:0]!=0;
    wire primed=filled==(D+1)'(DELAY_FRAMES);
    wire link_fell=was_admitted && !admitted_i;
    wire live=reset_ni && !clear_i && !changed && key_good && admitted_i && !revoked && !link_fell;
    wire [96:0] head=queue[qread];
    wire [31:0] head_sequence=head[95:64];
    wire [D-1:0] head_slot=head_sequence[D-1:0];
    wire head_live=tags[head_slot]==head_sequence &&
        !(valid_i && primed && cursor==head_slot);
    wire discard_head=live && qcount!=0 && !head_live;
    wire pop=(req_valid_o && req_ready_i) || discard_head;
    wire enqueue=live && valid_i && !exhausted;
    wire push=enqueue && (qcount<(Q+1)'(QUEUE_FRAMES) || pop);
    wire [D-1:0] response_slot=rsp_sequence_i[D-1:0];
    wire response_good=live && rsp_key_i==key && rsp_rate_44100_i==rate &&
        tags[response_slot]==rsp_sequence_i && issued[response_slot] &&
        !wet_valid[response_slot] && !rsp_error_i;
    wire deadline_response=rsp_valid_i && response_good && response_slot==cursor;
    assign ready_o=1'b1;
    assign rsp_ready_o=1'b1; // drain stale/failed responses without backpressure
    assign req_valid_o=live && qcount!=0 && head_live;
    assign req_key_o=key;
    assign req_rate_44100_o=rate;
    assign req_enabled_o=head[96];
    assign req_sequence_o=head_sequence;
    assign req_left_o=head[63:32];
    assign req_right_o=head[31:0];
    assign revoked_o=revoked;
    assign exhausted_o=exhausted;
    function automatic [31:0] increment(input [31:0] value);
        increment=value==32'hffffffff ? value : value+1'b1;
    endfunction
    initial if(DELAY_FRAMES<8 || (DELAY_FRAMES&(DELAY_FRAMES-1))!=0 ||
        QUEUE_FRAMES<2 || (QUEUE_FRAMES&(QUEUE_FRAMES-1))!=0 || QUEUE_FRAMES>=DELAY_FRAMES)
        $fatal(1,"invalid bounded remote effect window");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            key<=0;rate<=0;was_admitted<=0;revoked<=0;exhausted<=0;
            sequence_number<=0;cursor<=0;filled<=0;
            issued<=0;wet_valid<=0;wet_clip<=0;frame_enabled<=0;
            qread<=0;qwrite<=0;qcount<=0;
            valid_o<=0;left_o<=0;right_o<=0;clip_o<=0;
            overflow_count_o<=0;expired_count_o<=0;fallback_count_o<=0;rejected_count_o<=0;
        end else begin
            valid_o<=valid_i && !clear_i;clip_o<=0;
            was_admitted<=admitted_i;
            if(clear_i || changed)begin
                // Parameter/epoch changes cancel the previous timeline. The
                // local sampler still gets a bounded, silent completion.
                // Clear revokes the current key. Do not consume a new key
                // while clear is held: it can arm only after cancellation.
                if(!clear_i)begin key<=key_i;rate<=rate_44100_i;end
                // A rate-only change also needs a new key: switching away
                // and back must not reuse an old (key,rate,sequence) tuple.
                revoked<=clear_i || key_i==key;exhausted<=0;
                sequence_number<=0;cursor<=0;filled<=0;
                issued<=0;wet_valid<=0;wet_clip<=0;frame_enabled<=0;
                qread<=0;qwrite<=0;qcount<=0;left_o<=0;right_o<=0;
            end else begin
                if(link_fell)revoked<=1;
                if(!live)begin
                    qread<=0;qwrite<=0;qcount<=0;issued<=0;wet_valid<=0;
                    if(rsp_valid_i)rejected_count_o<=increment(rejected_count_o);
                end else begin
                    case({push,pop})
                        2'b10:qcount<=qcount+1'b1;
                        2'b01:qcount<=qcount-1'b1;
                        default:begin end
                    endcase
                    if(pop)qread<=qread+1'b1;
                    if(discard_head)expired_count_o<=increment(expired_count_o);
                    if(req_valid_o && req_ready_i)issued[head_slot]<=1;
                    if(push)begin
                        queue[qwrite]<={enabled_i,sequence_number,left_i,right_i};
                        qwrite<=qwrite+1'b1;
                    end
                    if(enqueue && !push)overflow_count_o<=increment(overflow_count_o);
                    if(rsp_valid_i)begin
                        if(response_good)begin
                            wet_l[response_slot]<=rsp_left_i;wet_r[response_slot]<=rsp_right_i;
                            wet_clip[response_slot]<=rsp_clip_i;wet_valid[response_slot]<=1;
                        end else rejected_count_o<=increment(rejected_count_o);
                    end
                end
                if(valid_i)begin
                    if(primed)begin
                        if(live && enabled_i && frame_enabled[cursor] &&
                           (wet_valid[cursor] || deadline_response))begin
                            left_o<=wet_valid[cursor] ? wet_l[cursor] : rsp_left_i;
                            right_o<=wet_valid[cursor] ? wet_r[cursor] : rsp_right_i;
                            clip_o<=wet_valid[cursor] ? wet_clip[cursor] : rsp_clip_i;
                        end else begin
                            left_o<=dry_l[cursor];right_o<=dry_r[cursor];
                            if(enabled_i)fallback_count_o<=increment(fallback_count_o);
                        end
                    end else begin
                        filled<=filled+1'b1;left_o<=0;right_o<=0;
                    end
                    dry_l[cursor]<=left_i;dry_r[cursor]<=right_i;
                    tags[cursor]<=sequence_number;frame_enabled[cursor]<=enabled_i;
                    issued[cursor]<=0;wet_valid[cursor]<=0;
                    cursor<=cursor+1'b1;
                    // Never reuse a transmitted sequence under the same key.
                    // Exhaustion disables remote work; dry scheduling continues.
                    if(sequence_number==32'hffffffff)exhausted<=1;
                    else sequence_number<=sequence_number+1'b1;
                end
            end
        end
    end
endmodule
`default_nettype wire
