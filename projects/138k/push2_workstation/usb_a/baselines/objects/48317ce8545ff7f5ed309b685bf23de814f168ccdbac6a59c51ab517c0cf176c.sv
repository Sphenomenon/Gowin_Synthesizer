// Independent diagnostic levels; no pulse count or coherent multi-bit word.
module gw138k_level_cdc #(parameter integer WIDTH=1)(
    input wire clk,reset_n,
    input wire [WIDTH-1:0] data_i,
    output wire [WIDTH-1:0] data_o
);
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [WIDTH-1:0] meta,sync;
    always @(posedge clk or negedge reset_n)
        if(!reset_n)begin meta<=0;sync<=0;end
        else begin meta<=data_i;sync<=meta;end
    assign data_o=sync;
endmodule
