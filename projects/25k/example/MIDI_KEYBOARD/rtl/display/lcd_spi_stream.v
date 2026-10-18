`timescale 1ns/1ps
// 50 MHz mode-0 SPI from a 50 MHz core clock, MSB first.
// A token transfers on valid && ready at the rising core-clock edge. The
// first token asserts CS; last closes CS after that byte. Keep valid,
// data, data_dc and last stable until their handshake. With continuous
// valid, tokens are accepted every eight clocks with no gap between bytes.
// Missing tokens pause SCK low with CS asserted. idle includes the physical
// ODDRC pipeline drain, so it is safe to start a panel delay when idle rises.
// Reset clears SCK immediately and releases CS within three running clocks.
// A short reset pulse also blocks ready until the CS pipeline has drained.
module lcd_spi_stream (
    input wire clk,
    input wire reset,
    input wire valid,
    input wire [7:0] data,
    input wire data_dc,
    input wire last,
    output wire ready,
    output wire idle,
    output wire lcd_sck,
    output wire lcd_mosi,
    output wire lcd_dc,
    output wire lcd_ncs
);
    localparam [2:0] ST_IDLE=0, ST_SEND=1, ST_WAIT=2,
                     ST_HOLD=3, ST_RELEASE=4;
    reg [2:0] state=ST_IDLE;
    reg [7:0] shift=0;
    reg [2:0] bit_index=0;
    reg byte_dc=0, byte_last=0;
    reg pin_clock_enable=0, pin_mosi=0, pin_dc=0, pin_ncs=1;
    // The ODDRC D input is sampled one edge after pin_ncs's NBA update,
    // then passes d0_reg_0 -> d0_reg_1 -> d0_reg_2 before Q0 observes it.
    // Five guard stages therefore ensure idle cannot lead physical CS.
    reg [4:0] ncs_pipeline=5'b11111;
    wire cs_released=ncs_pipeline[4];

    assign idle = !reset && (state==ST_IDLE) && cs_released;
    assign ready = !reset && ((state==ST_IDLE && cs_released) ||
                             state==ST_WAIT ||
                             (state==ST_SEND && bit_index==0 && !byte_last));

    // GW5A ODDRC samples a pair at posedge CLK and emits it two core clocks
    // later: D0 at posedge, D1 at negedge. All pins use the same pipeline.
    // SCK rises at negedge CLK, 10 ns after MOSI/DC change at posedge CLK.
    // Dedicated DDR outputs must connect directly to the I/O buffers, with
    // no inversion or fabric feedback after Q0. CS uses INIT=1 and shifts
    // ones on reset: CLEAR must stay low because it always forces Q0 low.
    ODDRC clock_oddr(.Q0(lcd_sck),.Q1(),.D0(1'b0),
        .D1(pin_clock_enable),.TX(1'b0),.CLK(clk),.CLEAR(reset));
    ODDRC mosi_oddr(.Q0(lcd_mosi),.Q1(),.D0(pin_mosi),
        .D1(pin_mosi),.TX(1'b0),.CLK(clk),.CLEAR(reset));
    ODDRC dc_oddr(.Q0(lcd_dc),.Q1(),.D0(pin_dc),
        .D1(pin_dc),.TX(1'b0),.CLK(clk),.CLEAR(reset));
    ODDRC #(.INIT(1'b1)) cs_oddr(.Q0(lcd_ncs),.Q1(),.D0(pin_ncs),
        .D1(pin_ncs),.TX(1'b0),.CLK(clk),.CLEAR(1'b0));

    // Mirror the three edges from the source register through the ODDRC
    // pair pipeline. Resetting this guard low prevents a queued assertion
    // from being mistaken for idle even if reset lasts less than one clock.
    always @(posedge clk or posedge reset) begin
        if(reset)ncs_pipeline<=5'b00000;
        else ncs_pipeline<={ncs_pipeline[3:0],pin_ncs};
    end

    always @(posedge clk or posedge reset) begin
        if(reset) begin
            state<=ST_IDLE;
            shift<=0;
            bit_index<=0;
            byte_dc<=0;
            byte_last<=0;
            pin_clock_enable<=0;
            pin_mosi<=0;
            pin_dc<=0;
            pin_ncs<=1;
        end else begin
            case(state)
                ST_IDLE: begin
                    pin_clock_enable<=0;
                    pin_ncs<=1;
                    if(valid && ready) begin
                        shift<=data;
                        bit_index<=7;
                        byte_dc<=data_dc;
                        byte_last<=last;
                        pin_mosi<=data[7];
                        pin_dc<=data_dc;
                        pin_ncs<=0;
                        state<=ST_SEND;
                    end
                end
                ST_SEND: begin
                    pin_clock_enable<=1;
                    pin_mosi<=shift[7];
                    pin_dc<=byte_dc;
                    shift<={shift[6:0],1'b0};
                    if(bit_index!=0) begin
                        bit_index<=bit_index-1'b1;
                    end else if(byte_last) begin
                        state<=ST_HOLD;
                    end else if(valid) begin
                        shift<=data;
                        bit_index<=7;
                        byte_dc<=data_dc;
                        byte_last<=last;
                    end else begin
                        state<=ST_WAIT;
                    end
                end
                ST_WAIT: begin
                    pin_clock_enable<=0;
                    if(valid) begin
                        shift<=data;
                        bit_index<=7;
                        byte_dc<=data_dc;
                        byte_last<=last;
                        pin_mosi<=data[7];
                        pin_dc<=data_dc;
                        state<=ST_SEND;
                    end
                end
                ST_HOLD: begin
                    // Last SCK sample to CS release is 30 ns: one full
                    // low-SCK pair, then release at the next pair boundary.
                    pin_clock_enable<=0;
                    state<=ST_RELEASE;
                end
                ST_RELEASE: begin
                    pin_clock_enable<=0;
                    pin_ncs<=1;
                    state<=ST_IDLE;
                end
                default: begin
                    state<=ST_IDLE;
                    pin_clock_enable<=0;
                    pin_ncs<=1;
                end
            endcase
        end
    end
endmodule
