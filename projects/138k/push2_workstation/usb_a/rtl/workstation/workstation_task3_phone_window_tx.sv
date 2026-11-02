`timescale 1ns/1ps
// Explicit posted PCM-window transport. A local window-write completion means
// bounded queue admission; all other operations retain remote-completion scope.
module workstation_task3_phone_window_tx #(
    parameter integer TIMEOUT_CYCLES=50000,
    parameter integer PARTIAL_FLUSH_CYCLES=12500,
    parameter bit EXTERNAL_FLUSH_ENABLE=1'b0
)(
    input wire clk_i,reset_ni,session_live_i,armed_i,
    input wire flush_i,
    input wire [31:0] token_i,
    input wire local_valid_i,local_target_i,local_write_i,
    input wire [11:0] local_address_i,
    input wire [31:0] local_data_i,
    input wire [3:0] local_strobes_i,
    output wire local_ready_o,local_response_error_o,
    output wire [31:0] local_response_data_o,
    output wire proxy_valid_o,proxy_target_o,proxy_write_o,
    output wire [11:0] proxy_address_o,
    output wire [31:0] proxy_data_o,
    output wire [3:0] proxy_strobes_o,
    input wire proxy_ready_i,proxy_response_error_i,
    input wire [31:0] proxy_response_data_i,
    output wire block_valid_o,input wire block_ready_i,
    output wire [255:0] block_payload_o,
    output wire [5:0] block_length_o,
    input wire ack_valid_i,
    input wire [31:0] ack_first_sequence_i,ack_next_sequence_i,
    input wire ack_error_i,
    output wire busy_o,output reg fault_o
);
    localparam [1:0] FLIGHT_IDLE=0,FLIGHT_SEND=1,FLIGHT_ACK=2;
    reg armed_previous;
    reg [31:0] token,next_sequence;
    reg held,completed,held_posted;
    reg held_target,held_write,completion_error;
    reg [11:0] held_address;
    reg [31:0] held_data,completion_data;
    reg [3:0] held_strobes;
    reg [31:0] local_timer,partial_timer,flight_timer;
    reg [2:0] building_count,flight_count;
    reg [11:0] building_address;
    reg [31:0] building_first,flight_first;
    reg [159:0] building_words;
    reg [1:0] flight;
    reg [255:0] flight_payload;
    wire new_arm=session_live_i && armed_i && !armed_previous;
    wire active=session_live_i && armed_i && armed_previous && !fault_o && token_i==token;
    wire incoming_window=!local_target_i && local_write_i && local_strobes_i==4'hf &&
        local_address_i>=12'h800 && local_address_i[1:0]==0;
    wire pending=held && !completed;
    wire contiguous={1'b0,held_address}==({1'b0,building_address}+13'(building_count*4));
    wire appendable=building_count<5 && (building_count==0 || contiguous);
    wire wants_flush=building_count!=0 && (building_count==5 ||
        (EXTERNAL_FLUSH_ENABLE && flush_i) ||
        partial_timer>=32'(PARTIAL_FLUSH_CYCLES-1) ||
        (pending && (!held_posted || !appendable)));
    wire [32:0] expected_ack_next={1'b0,flight_first}+33'(flight_count);
    wire ack_good=flight==FLIGHT_ACK && ack_first_sequence_i==flight_first &&
        !expected_ack_next[32] && ack_next_sequence_i==expected_ack_next[31:0] && !ack_error_i;
    wire expired_flight=flight!=FLIGHT_IDLE && flight_timer>=32'(TIMEOUT_CYCLES-1);
    wire expired_local=pending && local_timer>=32'(TIMEOUT_CYCLES-1);
    wire fatal_context=armed_i && armed_previous && token_i!=token;
    wire fatal=session_live_i && !new_arm && !fault_o &&
        (fatal_context || (active && ack_valid_i && !ack_good) || expired_flight || expired_local ||
         (active && pending && held_posted && next_sequence==32'hffffffff));
    assign local_ready_o=reset_ni && held && completed;
    assign local_response_error_o=completion_error;
    assign local_response_data_o=completion_data;
    assign proxy_valid_o=reset_ni && session_live_i && !fault_o && pending && !held_posted &&
        building_count==0 && flight==FLIGHT_IDLE;
    assign proxy_target_o=held_target;
    assign proxy_write_o=held_write;
    assign proxy_address_o=held_address;
    assign proxy_data_o=held_data;
    assign proxy_strobes_o=held_strobes;
    assign block_valid_o=reset_ni && active && flight==FLIGHT_SEND;
    assign block_payload_o=flight_payload;
    assign block_length_o=6'd12+{1'b0,flight_count,2'b00};
    assign busy_o=held || building_count!=0 || flight!=FLIGHT_IDLE;
    initial if(TIMEOUT_CYCLES<2 || PARTIAL_FLUSH_CYCLES<1)
        $fatal(1,"invalid phone window TX timeout");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            armed_previous<=0;token<=0;next_sequence<=0;fault_o<=0;
            held<=0;completed<=0;held_posted<=0;held_target<=0;held_write<=0;
            held_address<=0;held_data<=0;held_strobes<=0;completion_error<=0;completion_data<=0;
            local_timer<=0;partial_timer<=0;flight_timer<=0;building_count<=0;
            building_address<=0;building_first<=0;building_words<=0;
            flight<=FLIGHT_IDLE;flight_count<=0;flight_first<=0;flight_payload<=0;
        end else begin
            armed_previous<=session_live_i && armed_i;
            if(!held && local_valid_i)begin
                held<=1;completed<=0;held_posted<=armed_i && incoming_window;
                held_target<=local_target_i;held_write<=local_write_i;
                held_address<=local_address_i;held_data<=local_data_i;held_strobes<=local_strobes_i;
                completion_error<=0;completion_data<=0;local_timer<=0;
            end else if(held && completed && !local_valid_i)begin
                held<=0;completed<=0;held_posted<=0;local_timer<=0;
            end else if(pending)local_timer<=local_timer+1'b1;

            // Remote-completion commands are unchanged. Queue emptiness here is
            // an applied watermark: a block leaves flight only on the M ACK.
            if(proxy_valid_o && proxy_ready_i)begin
                completed<=1;completion_error<=proxy_response_error_i;
                completion_data<=proxy_response_data_i;local_timer<=0;
            end
            if(!session_live_i || new_arm)begin
                token<=token_i;next_sequence<=0;
                fault_o<=new_arm && token_i==0;
                building_count<=0;building_words<=0;partial_timer<=0;
                flight<=FLIGHT_IDLE;flight_timer<=0;
                if(!session_live_i && pending)begin completed<=1;completion_error<=1;completion_data<=0;end
            end else if(fatal || fault_o)begin
                fault_o<=1;building_count<=0;building_words<=0;partial_timer<=0;
                flight<=FLIGHT_IDLE;flight_timer<=0;
                if(pending)begin completed<=1;completion_error<=1;completion_data<=0;end
            end else begin
                if(!armed_i)begin
                    building_count<=0;building_words<=0;partial_timer<=0;
                    flight<=FLIGHT_IDLE;flight_timer<=0;
                    if(pending && held_posted)begin completed<=1;completion_error<=1;completion_data<=0;end
                end else if(active)begin
                    if(building_count!=0)partial_timer<=partial_timer+1'b1;
                    else partial_timer<=0;
                    if(flight!=FLIGHT_IDLE)flight_timer<=flight_timer+1'b1;
                    else flight_timer<=0;
                    if(block_valid_o && block_ready_i)begin flight<=FLIGHT_ACK;flight_timer<=0;end
                    if(ack_valid_i && ack_good)begin flight<=FLIGHT_IDLE;flight_timer<=0;end
                    // Dispatch and append are mutually exclusive, avoiding a
                    // partial-block copy/clear race. At most ten words reside.
                    if(flight==FLIGHT_IDLE && wants_flush)begin
                        flight_payload<={building_words,{20'd0,building_address},building_first,token};
                        flight_count<=building_count;flight_first<=building_first;
                        flight<=FLIGHT_SEND;flight_timer<=0;
                        building_count<=0;building_words<=0;partial_timer<=0;
                    end else if(pending && held_posted && appendable)begin
                        if(building_count==0)begin building_address<=held_address;building_first<=next_sequence;end
                        building_words[building_count*32+:32]<=held_data;
                        building_count<=building_count+1'b1;next_sequence<=next_sequence+1'b1;
                        partial_timer<=0;completed<=1;completion_error<=0;completion_data<=0;local_timer<=0;
                    end
                end
            end
        end
    end
endmodule
