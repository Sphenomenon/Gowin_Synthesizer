`timescale 1ns/1ps
// One physical Gowin semi-dual-port block. Bypass read: one registered read
// address, no extra output register. Clients own same-address forwarding and
// cross-clock ownership; the RAM itself is intentionally never reset.
module workstation_sdp #(
    parameter integer DATA_WIDTH=32,
    parameter integer ADDR_WIDTH=(DATA_WIDTH==32 ? 9 : 10)
) (
    input wire write_clk_i, write_enable_i,
    input wire [ADDR_WIDTH-1:0] write_addr_i,
    input wire [DATA_WIDTH-1:0] write_data_i,
    input wire read_clk_i, read_enable_i,
    input wire [ADDR_WIDTH-1:0] read_addr_i,
    output wire [DATA_WIDTH-1:0] read_data_o
);
`ifdef __ICARUS__
`define WORKSTATION_SDP_SIM
`endif
`ifdef VERILATOR
`define WORKSTATION_SDP_SIM
`endif
// Opt in to the actual Gowin simulation primitive for mapping/latency tests.
`ifdef WORKSTATION_SDP_VENDOR_SIM
`undef WORKSTATION_SDP_SIM
`endif
`ifndef WORKSTATION_SDP_SIM
    wire [31:0] data_out;
    wire [31:0] data_in={{(32-DATA_WIDTH){1'b0}},write_data_i};
    localparam integer ALIGN=$clog2(DATA_WIDTH);
    // GW5A uses low ADA bits as per-byte write enables in 16/32-bit mode.
    // Keep the word address aligned while enabling every byte of this write.
    localparam [ALIGN-1:0] BYTE_ENABLE=ALIGN'((1<<(DATA_WIDTH/8))-1);
    wire [13:0] write_address={{(14-ADDR_WIDTH-ALIGN){1'b0}},write_addr_i,BYTE_ENABLE};
    wire [13:0] read_address={{(14-ADDR_WIDTH-ALIGN){1'b0}},read_addr_i,{ALIGN{1'b0}}};
    SDPB #(.READ_MODE(1'b0),.BIT_WIDTH_0(DATA_WIDTH),.BIT_WIDTH_1(DATA_WIDTH),
           .BLK_SEL_0(3'b000),.BLK_SEL_1(3'b000),.RESET_MODE("SYNC")) ram (
        .DO(data_out),.DI(data_in),.ADA(write_address),.ADB(read_address),
        .CLKA(write_clk_i),.CEA(write_enable_i),.CLKB(read_clk_i),.CEB(read_enable_i),
        .OCE(1'b1),.RESET(1'b0),.BLKSELA(3'b000),.BLKSELB(3'b000));
    assign read_data_o=data_out[DATA_WIDTH-1:0];
`else
    reg [DATA_WIDTH-1:0] memory [0:(1<<ADDR_WIDTH)-1];
    reg [DATA_WIDTH-1:0] data_q;
    always @(posedge write_clk_i) if(write_enable_i) memory[write_addr_i]<=write_data_i;
    always @(posedge read_clk_i) if(read_enable_i) data_q<=memory[read_addr_i];
    assign read_data_o=data_q;
    initial begin
        if (!((DATA_WIDTH==16 && ADDR_WIDTH<=10) || (DATA_WIDTH==32 && ADDR_WIDTH<=9)))
            $fatal(1,"unsupported workstation_sdp geometry");
    end
`endif
`ifdef WORKSTATION_SDP_SIM
`undef WORKSTATION_SDP_SIM
`endif
endmodule
