`timescale 1ns/1ps
// One bounded block, replayed only through the existing PCM owner command path.
// ACK is emitted after every word has received the real owner completion.
module workstation_task3_phone_window_rx #(
    parameter integer TIMEOUT_CYCLES=50000
)(
    input wire clk_i,reset_ni,session_live_i,armed_i,
    input wire [31:0] token_i,
    input wire block_valid_i,
    input wire [255:0] block_payload_i,
    input wire [5:0] block_length_i,
    output wire command_valid_o,input wire command_ready_i,
    output wire [11:0] command_address_o,
    output wire [31:0] command_data_o,
    input wire command_response_error_i,
    output wire ack_valid_o,input wire ack_ready_i,
    output wire [31:0] ack_first_sequence_o,ack_next_sequence_o,
    output wire ack_error_o,busy_o,output reg fault_o
);
    localparam [2:0] IDLE=0,PREPARE=1,WAIT_OWNER=2,GAP=3,ACK=4;
    reg [2:0] state,count,position;
    reg armed_previous,ack_error;
    reg [31:0] token,expected_sequence,first_sequence,next_sequence,timer;
    reg [11:0] base_address;
    reg [159:0] words;
    wire new_arm=session_live_i && armed_i && !armed_previous;
    wire active=session_live_i && armed_i && armed_previous && !fault_o && token_i==token;
    wire [2:0] incoming_count=3'((block_length_i-6'd12)>>2);
    wire shape_good=block_length_i>=16 && block_length_i<=32 && block_length_i[1:0]==0;
    wire [32:0] incoming_end={1'b0,block_payload_i[95:64]}+33'(incoming_count*4)-33'd4;
    wire [32:0] incoming_next={1'b0,block_payload_i[63:32]}+33'(incoming_count);
    reg tail_good;integer b;
    always @*begin
        tail_good=1;
        for(b=0;b<32;b=b+1)
            if(b>=block_length_i && block_payload_i[b*8+:8]!=0)tail_good=0;
    end
    wire packet_good=active && state==IDLE && shape_good && tail_good &&
        block_payload_i[31:0]==token && block_payload_i[63:32]==expected_sequence &&
        block_payload_i[95:64]>=32'h800 && block_payload_i[95:64]<=32'hffc &&
        block_payload_i[65:64]==0 && !incoming_end[32] && incoming_end<=33'hffc && !incoming_next[32];
    wire expired=state!=IDLE && timer>=32'(TIMEOUT_CYCLES-1);
    wire wrong_context=armed_i && armed_previous && token_i!=token;
    assign command_valid_o=reset_ni && active && state==WAIT_OWNER;
    assign command_address_o=base_address+12'(position*4);
    assign command_data_o=words[position*32+:32];
    assign ack_valid_o=reset_ni && session_live_i && state==ACK;
    assign ack_first_sequence_o=first_sequence;
    assign ack_next_sequence_o=next_sequence;
    assign ack_error_o=ack_error;
    assign busy_o=state!=IDLE;
    initial if(TIMEOUT_CYCLES<2)$fatal(1,"invalid phone window RX timeout");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;count<=0;position<=0;armed_previous<=0;ack_error<=0;fault_o<=0;
            token<=0;expected_sequence<=0;first_sequence<=0;next_sequence<=0;
            base_address<=0;words<=0;timer<=0;
        end else begin
            armed_previous<=session_live_i && armed_i;
            if(!session_live_i || new_arm)begin
                state<=IDLE;count<=0;position<=0;ack_error<=0;
                token<=token_i;expected_sequence<=0;first_sequence<=0;next_sequence<=0;timer<=0;
                fault_o<=new_arm && token_i==0;
            end else if(expired || wrong_context || (block_valid_i && !packet_good))begin
                // Shared RX never waits. A malformed, unsolicited or busy
                // packet revokes this stream instead of pinning other traffic.
                fault_o<=1;timer<=0;
                if(block_valid_i && active)begin
                    first_sequence<=block_payload_i[63:32];next_sequence<=expected_sequence;
                    ack_error<=1;state<=ACK;
                end else state<=IDLE;
            end else if(fault_o)begin
                // Permit an error ACK to drain after revoking the owner.
                if(state==ACK)begin
                    timer<=timer+1'b1;
                    if(ack_ready_i)begin state<=IDLE;timer<=0;end
                end else begin state<=IDLE;timer<=0;end
            end else if(!armed_i)begin
                state<=IDLE;count<=0;position<=0;timer<=0;
            end else if(active)begin
                if(state!=IDLE)timer<=timer+1'b1;else timer<=0;
                case(state)
                    IDLE:if(block_valid_i)begin
                        words<=block_payload_i[255:96];base_address<=block_payload_i[75:64];
                        count<=incoming_count;position<=0;first_sequence<=block_payload_i[63:32];
                        next_sequence<=incoming_next[31:0];ack_error<=0;state<=PREPARE;timer<=0;
                    end
                    // Address/data are stable for a full cycle before valid.
                    // A previous held CDC response must release before reuse.
                    PREPARE:if(!command_ready_i)begin state<=WAIT_OWNER;timer<=0;end
                    WAIT_OWNER:if(command_ready_i)begin
                        timer<=0;
                        if(command_response_error_i)begin
                            fault_o<=1;ack_error<=1;
                            next_sequence<=first_sequence+{29'd0,position};state<=ACK;
                        end else state<=GAP;
                    end
                    GAP:if(!command_ready_i)begin
                        timer<=0;
                        if(position+1'b1==count)begin
                            expected_sequence<=next_sequence;state<=ACK;
                        end else begin position<=position+1'b1;state<=PREPARE;end
                    end
                    ACK:if(ack_ready_i)begin state<=IDLE;timer<=0;end
                    default:begin fault_o<=1;state<=IDLE;timer<=0;end
                endcase
            end
        end
    end
endmodule
