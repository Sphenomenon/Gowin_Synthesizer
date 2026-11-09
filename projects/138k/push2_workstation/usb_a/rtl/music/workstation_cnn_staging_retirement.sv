`timescale 1ns/1ps
// Memory-domain retirement for the single outstanding CNN staging command.
// commit_i is actual native acceptance. The FIFO head retires one edge later;
// busy_o prevents the broker from capturing that same head a second time.
// A returned beat is held until the completion FIFO takes it. This boundary
// never generates a native acknowledgement and never gates an audio clock.
module workstation_cnn_staging_retirement (
    input wire clk_i,reset_ni,
    input wire commit_i,write_i,response_i,
    input wire [255:0] response_data_i,
    input wire completion_ready_i,
    output reg request_retire_o,
    output reg completion_valid_o,
    output reg [256:0] completion_data_o,
    output wire busy_o,
    output reg fault_o
);
    wire write_complete=commit_i && write_i;
    wire completed=write_complete || response_i;
    assign busy_o=request_retire_o || completion_valid_o;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            request_retire_o<=0;completion_valid_o<=0;
            completion_data_o<=0;fault_o<=0;
        end else begin
            request_retire_o<=commit_i;
            if(completion_valid_o && completion_ready_i)completion_valid_o<=0;
            if(completed)begin
                // Concurrent return/write or overwrite is a protocol failure.
                // Preserve an older stalled completion rather than losing it.
                if((write_complete && response_i) ||
                   (completion_valid_o && !completion_ready_i))fault_o<=1;
                else begin
                    completion_valid_o<=1;
                    completion_data_o<={write_complete,response_data_i};
                end
            end
        end
    end
endmodule
