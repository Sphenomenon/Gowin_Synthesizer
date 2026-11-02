`timescale 1ns/1ps
// Paired-only acquisition in front of the SAME physical recording engine.
// Existing command/payload remains held by the single data service. This gate
// never completes the command or owns a second object. Timeout releases the
// original command to its engine, whose actual source check returns failure.
module workstation_task3_record_source_gate #(
    parameter integer WAIT_CYCLES=2500000
) (
    input wire clk_i,reset_ni,command_start_i,
    input wire [7:0] command_opcode_i,
    input wire object_idle_i,source_ready_i,source_fault_i,engine_done_i,
    input wire [7:0] record_state_i,
    output wire engine_start_o,source_needed_o,
    output reg timed_out_o
);
    localparam integer AGE_BITS=$clog2(WAIT_CYCLES+1);
    reg pending,released,release_pulse;
    reg [AGE_BITS-1:0] age;
    wire acquire=command_start_i && command_opcode_i==8'h20 && object_idle_i;
    wire recording_active=record_state_i>=1 && record_state_i<=3;
    assign engine_start_o=(command_start_i && !acquire) || release_pulse;
    assign source_needed_o=reset_ni && (pending || released || recording_active);
    initial if(WAIT_CYCLES<16)$fatal(1,"record acquisition wait must be bounded");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin pending<=0;released<=0;release_pulse<=0;age<=0;timed_out_o<=0;end
        else begin
            release_pulse<=0;
            if(acquire && !pending && !released)begin pending<=1;age<=0;timed_out_o<=0;end
            if(pending)begin
                if((source_ready_i && !source_fault_i) || age==AGE_BITS'(WAIT_CYCLES))begin
                    pending<=0;released<=1;release_pulse<=1;
                    timed_out_o<=!(source_ready_i && !source_fault_i);
                end else age<=age+1'b1;
            end
            if(released && engine_done_i)released<=0;
        end
    end
endmodule
