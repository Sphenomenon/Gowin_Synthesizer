`timescale 1ns/1ps
`default_nettype none
// Experimental reservation inside the effects owner's existing barrier.
// PANIC may clear children while a reserved command waits; it cannot retract
// an accepted rate. Dispatch waits for all children, including the DDR fence.
// This component owns only held command data, never committed public state.
module workstation_effects_config_dispatch (
    input wire clk_i,rst_ni,
    input wire reserve_config_i,reserve_history_i,rate_44100_i,
    input wire clear_i,fault_i,
    input wire all_config_ready_i,all_history_ready_i,all_quiet_i,
    output reg pending_o,
    output wire config_valid_o,history_valid_o,
    output reg rate_44100_o
);
    reg is_config;
    wire eligible=pending_o && !clear_i && !fault_i && all_quiet_i;
    assign config_valid_o=eligible && is_config && all_config_ready_i;
    assign history_valid_o=eligible && !is_config && all_history_ready_i;
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin pending_o<=0;is_config<=0;rate_44100_o<=0;end
        else if(reserve_config_i || reserve_history_i)begin
            pending_o<=1;is_config<=reserve_config_i;rate_44100_o<=rate_44100_i;
        end else if(config_valid_o || history_valid_o)pending_o<=0;
    end
endmodule
`default_nettype wire
