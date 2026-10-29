`timescale 1ns/1ps
`default_nettype none

// Admission belongs before stable per-client slots. Never gate a queued
// command or its completion: already accepted work must drain exactly once.
// Both valid and ready are masked so a blocked producer cannot see a false ACK.
module workstation_ddr_scan_window #(
    parameter bit ENABLE=1'b0
) (
    input wire scan_fetch_busy_i,
    input wire writer_valid_i,
    output wire writer_ready_o,
    output wire writer_valid_o,
    input wire writer_ready_i,
    input wire cpu_valid_i,cpu_write_i,
    output wire cpu_ready_o,
    output wire cpu_valid_o,
    input wire cpu_ready_i
);
    wire blocked=ENABLE && scan_fetch_busy_i;
    wire cpu_allowed=!blocked || !cpu_write_i;
    assign writer_valid_o=writer_valid_i && !blocked;
    assign writer_ready_o=writer_ready_i && !blocked;
    assign cpu_valid_o=cpu_valid_i && cpu_allowed;
    assign cpu_ready_o=cpu_ready_i && cpu_allowed;
endmodule

`default_nettype wire
