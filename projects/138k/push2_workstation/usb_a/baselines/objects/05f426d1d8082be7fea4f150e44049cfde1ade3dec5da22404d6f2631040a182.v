// Shared spectra RAM: both channels of one granule, 576 coefficients each.
//
// Address is {ch, index}. Q29 signed, matching mp3_requant's output format.
//
// This exists because everything from stereo onwards is an IN-PLACE transform
// on the granule, and giving each stage its own 1152-word buffer would burn
// two BSRAM per stage for no benefit. One write port and one read port are
// enough: every stage that needs two operands (MS stereo needs L and R, the
// antialias butterfly needs a value from each side of a band boundary) reads
// them on consecutive cycles rather than simultaneously.
//
// One write + one read in a single clocked block is the shape apicula maps to
// a BSRAM in dual-port mode. Do not add an asynchronous read: an async-read
// 1152x32 array is the exact trap that cost 9.7k LUT4 on the Nano 9K.
module mp3_spectra (
    input  wire        clk,

    input  wire        wr_en,
    input  wire [10:0] wr_addr,
    input  wire signed [31:0] wr_data,

    input  wire [10:0] rd_addr,
    output reg  signed [31:0] rd_data
);
    reg signed [31:0] mem [0:1151];

    // {ch, index} is 11 bits, but channel 1 then starts at 1024 while the array
    // ends at 1151 -- so ch1 coefficients above 127 fell off the end and read as
    // X. Mono streams never touch ch1, which is why every mono vector passed
    // while stereo lost everything past coefficient 127. Pack the two channels
    // instead of leaving a 448-word hole; the alternative, a 2048-word array,
    // would burn two extra BSRAM to hold nothing.
    wire [10:0] wa = wr_addr[10] ? (11'd576 + {1'b0, wr_addr[9:0]})
                                 : {1'b0, wr_addr[9:0]};
    wire [10:0] ra = rd_addr[10] ? (11'd576 + {1'b0, rd_addr[9:0]})
                                 : {1'b0, rd_addr[9:0]};

    always @(posedge clk) begin
        if (wr_en) mem[wa] <= wr_data;
        rd_data <= mem[ra];
    end
endmodule
