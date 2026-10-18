// Audio byte FIFO, 4096x8 (two BSRAM), synchronous read (data one cycle
// after rd). `sector_allow` tells the SD player there is room for a whole
// 512-byte sector plus margin. `clear` empties it on track changes.
module audio_fifo #(
    parameter DEPTH = 2048   // power of two
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        clear,
    input  wire        wr,
    input  wire [7:0]  wdata,
    input  wire        rd,
    output reg  [7:0]  rdata,        // valid 1 cycle after rd
    output wire [11:0] count,
    output wire        empty,
    output wire        sector_allow
);
    localparam AW = $clog2(DEPTH);

    reg [7:0]  mem [0:DEPTH-1];
    reg [AW:0] wptr, rptr;
    wire [AW:0] count_full = wptr - rptr;

    assign count        = count_full[11:0];
    assign empty        = (wptr == rptr);
    assign sector_allow = (DEPTH[AW:0] - count_full) >= 640;

    // memory access in sync-only blocks (RAM inference)
    always @(posedge clk) begin
        if (wr)
            mem[wptr[AW-1:0]] <= wdata;
        if (rd)
            rdata <= mem[rptr[AW-1:0]];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wptr <= 0;
            rptr <= 0;
        end else if (clear) begin
            wptr <= 0;
            rptr <= 0;
        end else begin
            if (wr) wptr <= wptr + 1'b1;
            if (rd) rptr <= rptr + 1'b1;
        end
    end
endmodule
