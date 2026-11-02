`timescale 1ns/1ps
// Dedicated local-clock receive queue. Every offered packet is consumed,
// including malformed/over-credit input, so a slow stream cannot pin the
// shared transport. Only this stream fails. Credits reserve complete blocks.
module workstation_task3_pcm_block_rx #(
    parameter integer QUEUE_BLOCKS=8,
    parameter integer CREDIT_BATCH=4
)(
    input wire clk_i,reset_ni,live_i,start_i,cancel_i,
    input wire [31:0] token_i,first_index_i,
    input wire block_valid_i,input wire [255:0] block_payload_i,
    input wire [5:0] block_length_i,
    output wire frame_valid_o,input wire frame_ready_i,
    output wire [31:0] frame_index_o,frame_pcm_o,
    output wire credit_valid_o,input wire credit_ready_i,
    output wire [31:0] credit_token_o,credit_limit_o,
    output wire empty_o,output reg active_o,fault_o,
    output reg [31:0] accepted_blocks_o,delivered_frames_o
);
    localparam integer AW=$clog2(QUEUE_BLOCKS);
    (* ram_style="block" *) reg [223:0] blocks[0:QUEUE_BLOCKS-1];
    reg [2:0] lengths[0:QUEUE_BLOCKS-1];
    reg [AW-1:0] wr,rd;
    reg [AW:0] count;
    reg [2:0] position;
    reg [31:0] token,expected_index,consumed_blocks,published_limit,credit_held_limit;
    reg credit_pending;
    wire [2:0] incoming_count=3'((block_length_i-6'd8)>>2);
    wire shape_good=block_length_i>=12 && block_length_i<=32 && block_length_i[1:0]==0;
    reg tail_good;integer b;
    always @*begin
        tail_good=1;
        for(b=0;b<32;b=b+1)
            if(b>=block_length_i && block_payload_i[b*8+:8]!=0)tail_good=0;
    end
    wire usable=reset_ni && live_i && active_o && !fault_o && !cancel_i;
    wire pop=frame_valid_o && frame_ready_i;
    wire retire=pop && position+1'b1==lengths[rd];
    wire [32:0] next_index={1'b0,expected_index}+{30'd0,incoming_count};
    wire bad=block_valid_i && (!usable || !shape_good || !tail_good ||
        block_payload_i[31:0]!=token || block_payload_i[63:32]!=expected_index ||
        accepted_blocks_o>=published_limit || count==(AW+1)'(QUEUE_BLOCKS) || next_index[32]);
    wire push=block_valid_i && usable && !bad;
    wire [32:0] available_limit={1'b0,consumed_blocks}+33'(QUEUE_BLOCKS);
    assign frame_valid_o=usable && count!=0 && !bad;
    assign frame_index_o=blocks[rd][31:0]+{29'd0,position};
    assign frame_pcm_o=blocks[rd][32+position*32+:32];
    assign credit_token_o=token;
    assign credit_limit_o=credit_held_limit;
    // A fresh context advertises its reservation immediately. Later updates
    // return batches of slots, reducing reverse-direction packet overhead.
    assign credit_valid_o=usable && credit_pending && !bad && !available_limit[32];
    assign empty_o=count==0;
    initial if(QUEUE_BLOCKS<2 || (1<<AW)!=QUEUE_BLOCKS || CREDIT_BATCH<1 || CREDIT_BATCH>QUEUE_BLOCKS)
        $fatal(1,"invalid block RX bounds");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            active_o<=0;fault_o<=0;wr<=0;rd<=0;count<=0;position<=0;
            token<=0;expected_index<=0;consumed_blocks<=0;published_limit<=0;
            accepted_blocks_o<=0;delivered_frames_o<=0;credit_pending<=0;credit_held_limit<=0;
        end else if(!live_i || cancel_i)begin
            active_o<=0;fault_o<=0;wr<=0;rd<=0;count<=0;position<=0;published_limit<=0;credit_pending<=0;
        end else if(start_i)begin
            active_o<=token_i!=0;fault_o<=token_i==0;token<=token_i;expected_index<=first_index_i;
            wr<=0;rd<=0;count<=0;position<=0;consumed_blocks<=0;published_limit<=0;
            accepted_blocks_o<=0;delivered_frames_o<=0;credit_pending<=1;credit_held_limit<=32'(QUEUE_BLOCKS);
        end else begin
            if(credit_valid_o && credit_ready_i)begin published_limit<=credit_held_limit;credit_pending<=0;end
            if(usable && !credit_pending && !available_limit[32] &&
                available_limit>={1'b0,published_limit}+33'(CREDIT_BATCH))begin
                credit_pending<=1;credit_held_limit<=available_limit[31:0];
            end
            if(bad)begin active_o<=0;fault_o<=1;wr<=0;rd<=0;count<=0;position<=0;published_limit<=0;end
            else if(usable)begin
                if(push)begin
                    blocks[wr]<=block_payload_i[255:32];lengths[wr]<=incoming_count;
                    wr<=wr+1'b1;expected_index<=next_index[31:0];accepted_blocks_o<=accepted_blocks_o+1'b1;
                end
                if(pop)begin
                    delivered_frames_o<=delivered_frames_o+1'b1;
                    if(retire)begin rd<=rd+1'b1;position<=0;consumed_blocks<=consumed_blocks+1'b1;end
                    else position<=position+1'b1;
                end
                case({push,retire})
                    2'b10:count<=count+1'b1;
                    2'b01:count<=count-1'b1;
                    default:begin end
                endcase
                if(available_limit[32])begin active_o<=0;fault_o<=1;count<=0;published_limit<=0;end
            end
        end
    end
endmodule
