module workstation_input_fifo_timing_probe (
    input wire clk_cpu, clk_audio, reset,
    output reg observed
);
    reg [17:0] sequence_q = 0;
    wire write_ready, read_ready;
    wire [17:0] read_data;
    always @(posedge clk_cpu)
        if (reset) sequence_q <= 0;
        else if (write_ready) sequence_q <= sequence_q + 1'b1;
    always @(posedge clk_audio)
        if (reset) observed <= 0;
        else if (read_ready) observed <= ^read_data;
    gw138k_usb_event_fifo crossing (.usb_rst(reset), .usb_clk(clk_cpu), .audio_clk(clk_audio),
        .w_data(sequence_q), .w_en(!reset), .w_rdy(write_ready),
        .r_en(!reset), .r_data(read_data), .r_rdy(read_ready));
endmodule
