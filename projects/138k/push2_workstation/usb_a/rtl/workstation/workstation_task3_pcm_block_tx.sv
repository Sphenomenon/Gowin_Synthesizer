`timescale 1ns/1ps
// Local-clock media packer. The full context is established by the endpoint;
// token is never an independent session authority. Credits count BLOCK slots.
module workstation_task3_pcm_block_tx #(
    parameter integer QUEUE_BLOCKS=8,
    parameter integer PARTIAL_TIMEOUT_CYCLES=12500
)(
    input wire clk_i,reset_ni,live_i,start_i,cancel_i,flush_i,
    input wire [31:0] token_i,first_index_i,
    input wire frame_valid_i,output wire frame_ready_o,
    input wire [31:0] frame_index_i,frame_pcm_i,
    input wire credit_valid_i,input wire [31:0] credit_token_i,credit_limit_i,
    output wire block_valid_o,input wire block_ready_i,
    output wire [255:0] block_payload_o,output wire [5:0] block_length_o,
    output wire empty_o,output reg active_o,fault_o,
    output reg [31:0] sent_blocks_o
);
    reg [31:0] token,expected_index,first_index,granted;
    reg [191:0] samples;
    reg [2:0] count;
    reg sealed;
    reg [$clog2(PARTIAL_TIMEOUT_CYCLES+1)-1:0] age;
    wire usable=reset_ni && live_i && active_o && !cancel_i && !fault_o;
    wire credit_bad=credit_valid_i && credit_token_i==token &&
        {1'b0,credit_limit_i}>{1'b0,sent_blocks_o}+33'(QUEUE_BLOCKS);
    wire frame_bad=frame_valid_i && !sealed && count<6 &&
        (frame_index_i!=expected_index || expected_index==32'hffffffff);
    wire immediate_fault=credit_bad || frame_bad;
    wire fire=frame_valid_i && frame_ready_o;
    wire pop=block_valid_o && block_ready_i;
    assign frame_ready_o=usable && !sealed && count<6 && !immediate_fault;
    assign block_valid_o=usable && sealed && sent_blocks_o<granted && !immediate_fault;
    assign block_payload_o={samples,first_index,token};
    assign block_length_o=6'd8+{1'b0,count,2'b00};
    assign empty_o=count==0 && !sealed;
    initial if(QUEUE_BLOCKS<2 || QUEUE_BLOCKS>64 || PARTIAL_TIMEOUT_CYCLES<8)
        $fatal(1,"invalid block TX bounds");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            active_o<=0;fault_o<=0;token<=0;expected_index<=0;first_index<=0;
            granted<=0;samples<=0;count<=0;sealed<=0;age<=0;sent_blocks_o<=0;
        end else if(!live_i || cancel_i)begin
            active_o<=0;fault_o<=0;samples<=0;count<=0;sealed<=0;age<=0;granted<=0;
        end else if(start_i)begin
            active_o<=token_i!=0;fault_o<=token_i==0;token<=token_i;
            expected_index<=first_index_i;first_index<=first_index_i;
            granted<=0;samples<=0;count<=0;sealed<=0;age<=0;sent_blocks_o<=0;
        end else if(usable && immediate_fault)begin
            fault_o<=1;active_o<=0;count<=0;sealed<=0;samples<=0;age<=0;granted<=0;
        end else if(usable)begin
            // Duplicate or lower grants are idempotent and do not mint credit.
            if(credit_valid_i && credit_token_i==token && credit_limit_i>granted)
                granted<=credit_limit_i;
            if(!sealed && count!=0)begin
                if(flush_i || age==$clog2(PARTIAL_TIMEOUT_CYCLES+1)'(PARTIAL_TIMEOUT_CYCLES-1))sealed<=1;
                else age<=age+1'b1;
            end
            if(fire)begin
                if(count==0)begin first_index<=frame_index_i;age<=0;end
                samples[count*32+:32]<=frame_pcm_i;count<=count+1'b1;
                expected_index<=expected_index+1'b1;
                if(count==5)sealed<=1;
            end
            if(pop)begin
                if(sent_blocks_o==32'hfffffffe)begin fault_o<=1;active_o<=0;end
                sent_blocks_o<=sent_blocks_o+1'b1;samples<=0;count<=0;sealed<=0;age<=0;
            end
        end
    end
endmodule
