module workstation_tmds_serializer #(
    parameter POLARITY_INVERT=1'b1
)(
    input wire pixel_clock,ddr_bit_clock,reset,
    input wire [9:0] data,
    output wire [1:0] lane
);
    wire serialized;
    wire [9:0] serial_word=data ^ {10{POLARITY_INVERT}};
    OSER10 serializer (
        .Q(serialized),.D0(serial_word[0]),.D1(serial_word[1]),.D2(serial_word[2]),.D3(serial_word[3]),.D4(serial_word[4]),
        .D5(serial_word[5]),.D6(serial_word[6]),.D7(serial_word[7]),.D8(serial_word[8]),.D9(serial_word[9]),
        .PCLK(pixel_clock),.FCLK(ddr_bit_clock),.RESET(reset)
    );
    ELVDS_OBUF differential (.I(serialized),.O(lane[1]),.OB(lane[0]));
endmodule

module dvi_tx_top (
    input wire pixel_clock,ddr_bit_clock,reset,serializer_reset,
    input wire den,hsync,vsync,
    input wire [23:0] pixel_data,
    output wire [1:0] tmds_clk,tmds_d0,tmds_d1,tmds_d2
);
    wire [29:0] encoded;
    wire [5:0] control_bits={4'b0000,vsync,hsync};
    wire [1:0] lanes [0:2];
    assign tmds_d0=lanes[0];
    assign tmds_d1=lanes[1];
    assign tmds_d2=lanes[2];
    genvar channel;
    generate for(channel=0;channel<3;channel=channel+1) begin: data_lanes
        dvi_tx_tmds_enc encoder (
            .clock(pixel_clock),.reset(reset),.den(den),.data(pixel_data[channel*8+:8]),
            .ctrl(control_bits[channel*2+:2]),.tmds(encoded[channel*10+:10])
        );
        workstation_tmds_serializer serializer (
            .pixel_clock(pixel_clock),.ddr_bit_clock(ddr_bit_clock),.reset(serializer_reset),
            .data(encoded[channel*10+:10]),.lane(lanes[channel])
        );
    end endgenerate
    workstation_tmds_serializer clock_lane (
        .pixel_clock(pixel_clock),.ddr_bit_clock(ddr_bit_clock),.reset(serializer_reset),
        .data(10'b1111100000),.lane(tmds_clk)
    );
endmodule
