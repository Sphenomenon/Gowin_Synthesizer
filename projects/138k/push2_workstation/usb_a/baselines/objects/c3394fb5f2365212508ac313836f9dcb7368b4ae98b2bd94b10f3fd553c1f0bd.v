// Synchronous-read ROM initialised from a $readmemh file.
//
// THE house idiom for every lookup table in this project. MP3 needs roughly
// fifteen of them, and the temptation is always to write an async-read array
// or a wide combinational `case`. Do not: an async-read `sector_content[0:511]`
// in the vendor SD core synthesized to ~9.7k LUT4 on a chip with 8640
// (see ../tang_fm_transmitter/docs/bringup_log.md). A registered read port is
// what lets yosys infer BSRAM instead of distributed logic.
//
// Cost of the idiom: data is valid ONE clock after addr. Every consumer here
// is a state machine with cycles to spare -- a frame is 26.1 ms and the
// decoder needs ~310k of 2.1M cycles -- so this is free in practice.
module sync_rom #(
    parameter AW   = 8,        // address width; depth is 1<<AW
    parameter DW   = 16,       // data width
    parameter INIT = ""        // path to a .memh, relative to the make cwd
) (
    input  wire          clk,
    input  wire [AW-1:0] addr,
    output reg  [DW-1:0] data
);
    reg [DW-1:0] mem [0:(1<<AW)-1];

    initial begin
        if (INIT != "") $readmemh(INIT, mem);
    end

    always @(posedge clk)
        data <= mem[addr];
endmodule
