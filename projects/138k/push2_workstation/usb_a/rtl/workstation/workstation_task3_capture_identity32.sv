// Full-width capture identity. No state, truncation, latency or owner change.
module workstation_task3_capture_identity32 (
    input wire [31:0] response_i,capture_i,
    output wire matches_o
);
    (* syn_keep=1 *) wire [3:0] byte_equal;
    for(genvar capture_byte=0;capture_byte<4;capture_byte=capture_byte+1)begin:g_byte
        assign byte_equal[capture_byte]=response_i[capture_byte*8+:8]==capture_i[capture_byte*8+:8];
    end
    assign matches_o=&byte_equal;
endmodule
