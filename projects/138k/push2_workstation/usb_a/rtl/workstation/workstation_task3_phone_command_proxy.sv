`timescale 1ns/1ps
// W-side replacement for the LOCAL PCM1 command target in a paired profile.
// Connect the existing APB command CDC to cpu_command_*. command_ready_o means
// the remote M owner has returned a matched response, never local queue credit.
// No changes to pcm_media register encoding, SBC math or a138_hci_bus are needed.
module workstation_task3_phone_command_proxy #(
    parameter integer ROUND_TRIP_TIMEOUT_CYCLES=50000
) (
    input wire clk_i,reset_ni,link_ready_i,panic_i,
    input wire arm_valid_i,
    output wire arm_ready_o,
    input wire [31:0] arm_boot_i,arm_session_i,arm_generation_i,
    output reg arm_accepted_o,arm_rejected_o,
    output wire arm_tx_valid_o,
    input wire arm_tx_ready_i,arm_result_accepted_i,arm_result_rejected_i,
    output reg [31:0] boot_o,session_o,generation_o,
    output wire cancel_tx_valid_o,
    input wire cancel_tx_ready_i,
    input wire cancel_valid_i,
    input wire [31:0] cancel_session_i,cancel_generation_i,
    input wire cpu_command_valid_i,cpu_command_target_i,cpu_command_write_i,
    input wire [11:0] cpu_command_address_i,
    input wire [31:0] cpu_command_data_i,
    input wire [3:0] cpu_command_strobes_i,
    output wire cpu_command_ready_o,
    output reg [31:0] cpu_response_data_o,
    output reg cpu_response_error_o,
    output wire request_valid_o,
    input wire request_ready_i,
    output reg [31:0] request_sequence_o,
    output reg request_target_o,request_write_o,
    output reg [11:0] request_address_o,
    output reg [31:0] request_data_o,
    output reg [3:0] request_strobes_o,
    input wire response_valid_i,
    output wire response_ready_o,
    input wire [31:0] response_boot_i,response_session_i,response_generation_i,response_sequence_i,response_data_i,
    input wire response_error_i,
    output reg armed_o,fault_o,
    output reg [3:0] failure_code_o,
    output reg [31:0] completed_commands_o
);
    localparam [2:0] IDLE=0,SEND=1,WAIT_RESPONSE=2,COMPLETE=3,WAIT_RELEASE=4;
    localparam integer AGE_BITS=$clog2(ROUND_TRIP_TIMEOUT_CYCLES+1);
    reg [2:0] state;
    reg [1:0] arm_state;
    reg [AGE_BITS-1:0] age,arm_age;
    reg [31:0] retired_generation,next_sequence;
    reg cancel_pending;
    wire cancel_match=cancel_valid_i && cancel_session_i==session_o && cancel_generation_i==generation_o;
    wire fence=!link_ready_i || panic_i || cancel_match;
    wire live=reset_ni && armed_o && !fault_o && !fence;
    wire response_matches=response_boot_i==boot_o && response_session_i==session_o &&
        response_generation_i==generation_o && response_sequence_i==request_sequence_o;
    assign arm_ready_o=reset_ni && link_ready_i && !panic_i && !armed_o && arm_state==0 &&
        state==IDLE && !cancel_pending && retired_generation!=32'hffffffff;
    assign arm_tx_valid_o=reset_ni && !fence && arm_state==1;
    assign request_valid_o=live && state==SEND && age<AGE_BITS'(ROUND_TRIP_TIMEOUT_CYCLES);
    assign response_ready_o=reset_ni && state==WAIT_RESPONSE;
    assign cpu_command_ready_o=reset_ni && state==COMPLETE;
    assign cancel_tx_valid_o=reset_ni && cancel_pending;
    initial if(ROUND_TRIP_TIMEOUT_CYCLES<2)$fatal(1,"invalid remote PCM round-trip timeout");
    task automatic fail(input [3:0] code);
        begin
            armed_o<=0;fault_o<=1;failure_code_o<=code;arm_state<=0;cancel_pending<=1;
            if(state==SEND || state==WAIT_RESPONSE)begin
                cpu_response_data_o<=32'hffffffff;cpu_response_error_o<=1;state<=COMPLETE;
            end
        end
    endtask
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;arm_state<=0;age<=0;arm_age<=0;retired_generation<=0;next_sequence<=0;cancel_pending<=0;
            boot_o<=0;session_o<=0;generation_o<=0;arm_accepted_o<=0;arm_rejected_o<=0;
            request_sequence_o<=0;request_target_o<=0;request_write_o<=0;request_address_o<=0;request_data_o<=0;request_strobes_o<=0;
            armed_o<=0;fault_o<=0;failure_code_o<=0;cpu_response_data_o<=0;cpu_response_error_o<=0;completed_commands_o<=0;
        end else begin
            arm_accepted_o<=0;arm_rejected_o<=0;
            if(cancel_tx_valid_o && cancel_tx_ready_i)cancel_pending<=0;
            if(arm_valid_i)begin
                if(!arm_ready_o || arm_boot_i==0 || arm_session_i==0 || arm_generation_i==0 ||
                   arm_generation_i<=retired_generation)arm_rejected_o<=1;
                else begin
                    boot_o<=arm_boot_i;session_o<=arm_session_i;generation_o<=arm_generation_i;
                    retired_generation<=arm_generation_i;next_sequence<=0;completed_commands_o<=0;
                    arm_state<=1;arm_age<=0;fault_o<=0;failure_code_o<=0;
                end
            end
            if(arm_state!=0)begin
                if(fence || arm_result_rejected_i || arm_age==AGE_BITS'(ROUND_TRIP_TIMEOUT_CYCLES))begin
                    arm_state<=0;armed_o<=0;fault_o<=1;arm_rejected_o<=1;cancel_pending<=1;
                    failure_code_o<=panic_i?4'd5:cancel_match?4'd6:!link_ready_i?4'd3:arm_result_rejected_i?4'd2:4'd4;
                end else begin
                    arm_age<=arm_age+1'b1;
                    if(arm_tx_valid_o && arm_tx_ready_i)arm_state<=2;
                    if(arm_state==2 && arm_result_accepted_i)begin
                        arm_state<=0;armed_o<=1;arm_accepted_o<=1;
                    end
                end
            end
            if(armed_o && fence)fail(panic_i?4'd5:cancel_match?4'd6:4'd3);
            else case(state)
                IDLE:if(cpu_command_valid_i)begin
                    if(!live || &next_sequence)begin
                        cpu_response_data_o<=32'hffffffff;cpu_response_error_o<=1;state<=COMPLETE;
                    end else begin
                        request_sequence_o<=next_sequence;request_target_o<=cpu_command_target_i;request_write_o<=cpu_command_write_i;
                        request_address_o<=cpu_command_address_i;request_data_o<=cpu_command_data_i;
                        request_strobes_o<=cpu_command_strobes_i;age<=0;state<=SEND;
                    end
                end
                SEND:begin
                    if(age==AGE_BITS'(ROUND_TRIP_TIMEOUT_CYCLES))fail(4'd4);
                    else begin
                        age<=age+1'b1;
                        if(request_valid_o && request_ready_i)state<=WAIT_RESPONSE;
                    end
                end
                WAIT_RESPONSE:begin
                    if(response_valid_i && response_ready_o)begin
                        if(!response_matches)fail(4'd2);
                        else begin
                            cpu_response_data_o<=response_data_i;cpu_response_error_o<=response_error_i;
                            next_sequence<=next_sequence+1'b1;completed_commands_o<=completed_commands_o+1'b1;
                            state<=COMPLETE;
                        end
                    end else if(age==AGE_BITS'(ROUND_TRIP_TIMEOUT_CYCLES))fail(4'd4);
                    else age<=age+1'b1;
                end
                COMPLETE:if(cpu_command_valid_i && cpu_command_ready_o)state<=WAIT_RELEASE;
                WAIT_RELEASE:if(!cpu_command_valid_i)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
