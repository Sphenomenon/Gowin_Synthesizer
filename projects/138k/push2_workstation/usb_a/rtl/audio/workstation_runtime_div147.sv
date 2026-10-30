`timescale 1ns/1ps
`default_nettype none
// Exact unsigned division by147, one accepted item per clock. The high six
// (odd WIDTH: seven) input bits are already a remainder smaller than147.
// Every later register consumes two bits with three parallel ten-bit trial
// subtractions. There is no combinational divider or multiply in a stage.
// Payload, quotient and valid cross the same registers; flush kills all tags.
module workstation_runtime_div147 #(
    parameter integer WIDTH=42,
    parameter integer TAG_WIDTH=1
)(
    input wire clk_i,rst_ni,flush_i,valid_i,
    input wire [WIDTH-1:0] dividend_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire valid_o,
    output wire [WIDTH-1:0] quotient_o,
    output wire [TAG_WIDTH-1:0] tag_o,
    output wire quiescent_o
);
    localparam integer PREFIX_BITS=6+(WIDTH%2);
    localparam integer STAGES=(WIDTH-PREFIX_BITS)/2;
    reg [STAGES:0] valid;
    reg [WIDTH-1:0] dividend[0:STAGES],quotient[0:STAGES];
    reg [7:0] remainder[0:STAGES];
    reg [TAG_WIDTH-1:0] tag[0:STAGES];
    initial begin
        if(WIDTH<8 || TAG_WIDTH<1)$fatal(1,"div147 unsupported width");
    end
    assign valid_o=valid[STAGES] && !flush_i;
    assign quotient_o=quotient[STAGES];
    assign tag_o=tag[STAGES];
    assign quiescent_o=!(|valid);
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)valid<='0;
        else if(flush_i)valid<='0;
        else valid<={valid[STAGES-1:0],valid_i};
    end
    always @(posedge clk_i) if(valid_i && !flush_i) begin
        remainder[0]<={{(8-PREFIX_BITS){1'b0}},dividend_i[WIDTH-1 -: PREFIX_BITS]};
        dividend[0]<=dividend_i<<PREFIX_BITS;
        quotient[0]<='0;
        tag[0]<=tag_i;
    end
    for(genvar s=0;s<STAGES;s=s+1)begin:g_digit
        wire [9:0] trial={remainder[s],dividend[s][WIDTH-1 -: 2]};
        wire [10:0] minus1={1'b0,trial}-11'd147;
        wire [10:0] minus2={1'b0,trial}-11'd294;
        wire [10:0] minus3={1'b0,trial}-11'd441;
        wire [1:0] digit=!minus3[10] ? 2'd3 : !minus2[10] ? 2'd2 : !minus1[10] ? 2'd1 : 2'd0;
        wire [7:0] next_remainder=!minus3[10] ? minus3[7:0] :
            !minus2[10] ? minus2[7:0] : !minus1[10] ? minus1[7:0] : trial[7:0];
        always @(posedge clk_i) if(valid[s] && !flush_i) begin
            remainder[s+1]<=next_remainder;
            dividend[s+1]<=dividend[s]<<2;
            quotient[s+1]<={quotient[s][WIDTH-3:0],digit};
            tag[s+1]<=tag[s];
        end
`ifndef SYNTHESIS
        always @(posedge clk_i) if(rst_ni && valid[s] && !flush_i)
            if(remainder[s]>=8'd147)$fatal(1,"div147 remainder invariant");
`endif
    end
endmodule
`default_nettype wire
