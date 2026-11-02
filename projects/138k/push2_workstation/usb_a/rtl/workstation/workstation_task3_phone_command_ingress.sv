`timescale 1ns/1ps
// Logical remote bus into M's EXISTING workstation_ae350_pcm_owner. W keeps
// using pcm_media's native PCM1 register/window contract; decoded samples enter
// M BEFORE D effects and final master gain. This adapter owns no audio queue,
// interpolation, parameters, recording object or replacement PCM owner.
module workstation_task3_phone_command_ingress #(
    parameter integer OWNER_TIMEOUT_CYCLES=10000
) (
    input wire clk_i,reset_ni,link_ready_i,panic_i,owner_idle_i,
    input wire arm_valid_i,
    output wire arm_ready_o,
    input wire [31:0] arm_boot_i,arm_session_i,arm_generation_i,
    output reg arm_accepted_o,arm_rejected_o,
    input wire cancel_valid_i,
    input wire [31:0] cancel_session_i,cancel_generation_i,
    input wire request_valid_i,
    output wire request_ready_o,
    input wire [31:0] request_boot_i,request_session_i,request_generation_i,request_sequence_i,
    input wire request_target_i,request_write_i,
    input wire [11:0] request_address_i,
    input wire [31:0] request_data_i,
    input wire [3:0] request_strobes_i,
    output wire response_valid_o,
    input wire response_ready_i,
    output reg [31:0] response_boot_o,response_session_o,response_generation_o,response_sequence_o,response_data_o,
    output reg response_error_o,
    output wire owner_live_o,
    output wire command_valid_o,
    input wire command_ready_i,
    output reg command_target_o,command_write_o,
    output reg [11:0] command_address_o,
    output reg [31:0] command_data_o,
    output reg [3:0] command_strobes_o,
    input wire [31:0] command_response_data_i,
    input wire command_response_error_i,
    output reg armed_o,fault_o,
    output reg [3:0] failure_code_o,
    output reg [31:0] accepted_commands_o,applied_commands_o
);
    localparam [1:0] IDLE=0,WAIT_OWNER=1,RESPONSE=2,PREPARE=3;
    localparam integer AGE_BITS=$clog2(OWNER_TIMEOUT_CYCLES+1);
    reg [1:0] state;
    reg [AGE_BITS-1:0] age;
    reg [31:0] boot,session,generation,retired_generation,expected_sequence;
    wire cancel_match=cancel_valid_i && cancel_session_i==session && cancel_generation_i==generation;
    wire external_fence=!link_ready_i || panic_i || cancel_match;
    wire request_bad=request_boot_i!=boot || request_session_i!=session ||
        request_generation_i!=generation || request_sequence_i!=expected_sequence || &expected_sequence;
    // Revocation is immediate at the original owner's session boundary. It
    // cannot wait behind a response/download and cannot undo an applied command.
    assign owner_live_o=reset_ni && armed_o && !fault_o && !external_fence;
    assign arm_ready_o=reset_ni && link_ready_i && !panic_i && !armed_o &&
        state==IDLE && owner_idle_i && retired_generation!=32'hffffffff;
    assign request_ready_o=owner_live_o && state==IDLE;
    assign command_valid_o=owner_live_o && state==WAIT_OWNER && age<AGE_BITS'(OWNER_TIMEOUT_CYCLES);
    assign response_valid_o=reset_ni && state==RESPONSE;
    initial if(OWNER_TIMEOUT_CYCLES<2)$fatal(1,"invalid phone command timeout");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;age<=0;boot<=0;session<=0;generation<=0;retired_generation<=0;expected_sequence<=0;
            armed_o<=0;fault_o<=0;failure_code_o<=0;arm_accepted_o<=0;arm_rejected_o<=0;
            command_target_o<=0;command_write_o<=0;command_address_o<=0;command_data_o<=0;command_strobes_o<=0;
            response_boot_o<=0;response_session_o<=0;response_generation_o<=0;response_sequence_o<=0;
            response_data_o<=0;response_error_o<=0;accepted_commands_o<=0;applied_commands_o<=0;
        end else begin
            arm_accepted_o<=0;arm_rejected_o<=0;
            if(response_valid_o && response_ready_i)state<=IDLE;
            if(arm_valid_i)begin
                if(!arm_ready_o || arm_boot_i==0 || arm_session_i==0 || arm_generation_i==0 ||
                   arm_generation_i<=retired_generation)arm_rejected_o<=1;
                else begin
                    boot<=arm_boot_i;session<=arm_session_i;generation<=arm_generation_i;
                    retired_generation<=arm_generation_i;expected_sequence<=0;
                    armed_o<=1;fault_o<=0;failure_code_o<=0;arm_accepted_o<=1;
                    accepted_commands_o<=0;applied_commands_o<=0;
                end
            end
            if(armed_o && external_fence)begin
                armed_o<=0;fault_o<=1;failure_code_o<=panic_i?4'd5:cancel_match?4'd6:4'd3;
                if(state==WAIT_OWNER || state==PREPARE)begin
                    response_error_o<=1;response_data_o<=32'hffffffff;state<=RESPONSE;
                end
            end else if(request_valid_i && request_ready_o)begin
                response_boot_o<=request_boot_i;response_session_o<=request_session_i;
                response_generation_o<=request_generation_i;response_sequence_o<=request_sequence_i;
                command_target_o<=request_target_i;command_write_o<=request_write_i;command_address_o<=request_address_i;
                command_data_o<=request_data_i;command_strobes_o<=request_strobes_i;age<=0;
                accepted_commands_o<=accepted_commands_o+1'b1;
                if(request_bad)begin
                    armed_o<=0;fault_o<=1;failure_code_o<=4'd2;
                    response_error_o<=1;response_data_o<=32'hffffffff;state<=RESPONSE;
                end else begin expected_sequence<=expected_sequence+1'b1;state<=PREPARE;end
            end else if(state==PREPARE && owner_live_o)begin
                // The maintained clock service predecodes the held address
                // for one edge, just like its original APB command CDC.
                state<=WAIT_OWNER;
            end else if(state==WAIT_OWNER && owner_live_o)begin
                if(command_valid_o && command_ready_i)begin
                    response_data_o<=command_response_data_i;response_error_o<=command_response_error_i;
                    applied_commands_o<=applied_commands_o+1'b1;state<=RESPONSE;
                end else if(age==AGE_BITS'(OWNER_TIMEOUT_CYCLES))begin
                    armed_o<=0;fault_o<=1;failure_code_o<=4'd4;
                    response_error_o<=1;response_data_o<=32'hffffffff;state<=RESPONSE;
                end else age<=age+1'b1;
            end
        end
    end
endmodule
