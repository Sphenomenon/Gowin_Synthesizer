module clock_measure_top (
    input wire clk_50mhz, clk_12m288, clk_16m9344, restart_n
);
    wire [31:0] window_id, count_a, count_b, endpoint_a, endpoint_b, heartbeat;
    clock_measure meter (
        .clk_ref(clk_50mhz), .clk_a(clk_12m288), .clk_b(clk_16m9344), .restart_n(restart_n),
        .window_id(window_id), .count_a(count_a), .count_b(count_b),
        .endpoint_a(endpoint_a), .endpoint_b(endpoint_b), .heartbeat(heartbeat)
    );
    // Low word first: FREQ, window, A count, B count, gate, heartbeat, A end, B end.
    (* syn_keep=1, syn_preserve=1 *) reg [255:0] frequency_debug = 0;
    always @(posedge clk_50mhz)
        frequency_debug <= {endpoint_b,endpoint_a,heartbeat,32'd500000000,
                            count_b,count_a,window_id,32'h46524551};
endmodule
