`timescale 1ns/1ps
`default_nettype none
// The producer holds one published native command until real owner8 commit.
// A local-slot/core-buffer ACK must never retire the producer's command.
module workstation_recording_ddr_native_bridge (
    input wire clk_i,rst_ni,
    input wire published_valid_i,
    input wire slot_ready_i,native_accept_i,transport_fault_i,
    output wire slot_valid_o,native_ready_o,transport_fault_o,
    output reg submitted_o,protocol_fault_o
);
    assign slot_valid_o=published_valid_i && !submitted_o;
    assign native_ready_o=native_accept_i && submitted_o;
    wire protocol_fault_now=(native_accept_i && (!submitted_o || !published_valid_i)) ||
        (submitted_o && !published_valid_i);
    assign transport_fault_o=transport_fault_i || protocol_fault_o || protocol_fault_now;
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin submitted_o<=0;protocol_fault_o<=0;end
        else begin
            if(native_accept_i)begin
                submitted_o<=0;
            end else if(slot_valid_o && slot_ready_i)submitted_o<=1;
            if(protocol_fault_now)protocol_fault_o<=1;
        end
    end
endmodule
`default_nettype wire
