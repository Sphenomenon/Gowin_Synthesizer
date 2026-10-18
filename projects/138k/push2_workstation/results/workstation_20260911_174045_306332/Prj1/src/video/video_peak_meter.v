`default_nettype none

// Frame snapshot of peak |Q1.31|, plus an approximately 0.25 s decay tail.
// 0x80000000 has magnitude 0x80000000 and is deliberately not negated signed.
module video_peak_meter (
    input wire pixel_clk,
    input wire reset_n,
    input wire [31:0] sample_data,
    input wire sample_valid,
    input wire frame_start,
    output reg [31:0] level_data
);
    wire [31:0] magnitude = sample_data[31] ? (~sample_data + 1'b1) : sample_data;
    reg [31:0] frame_peak;
    wire [31:0] current_peak = (sample_valid && magnitude > frame_peak) ? magnitude : frame_peak;
    wire [31:0] decay_level = level_data - (level_data >> 4) - (level_data != 0);
    always @(posedge pixel_clk or negedge reset_n) begin
        if (!reset_n) begin
            frame_peak <= 0;
            level_data <= 0;
        end else if (frame_start) begin
            level_data <= (current_peak > decay_level) ? current_peak : decay_level;
            frame_peak <= 0;
        end else if (sample_valid && magnitude > frame_peak) begin
            frame_peak <= magnitude;
        end
    end
endmodule

`default_nettype wire
