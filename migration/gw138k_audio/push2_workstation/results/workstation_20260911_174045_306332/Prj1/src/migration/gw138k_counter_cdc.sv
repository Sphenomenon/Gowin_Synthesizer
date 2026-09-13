// Source counter changes by at most one per MIDI byte (>=320us here).
// Register Gray at the source, constrain all bit flights, synchronize twice,
// then decode locally. The destination observes a delayed coherent count.
module gw138k_counter_cdc (
    input wire reset_n,source_clk,destination_clk,
    input wire [31:0] source_count,
    output reg [31:0] destination_count
);
    (* syn_preserve=1,syn_keep=1 *) reg [31:0] gray;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [31:0] meta,sync_value;
    reg [2:0] source_release,destination_release;
    always @(posedge source_clk or negedge reset_n)
        if(!reset_n) source_release<=0;else source_release<={source_release[1:0],1'b1};
    always @(posedge destination_clk or negedge reset_n)
        if(!reset_n) destination_release<=0;else destination_release<={destination_release[1:0],1'b1};
    wire source_reset_n=source_release[2],destination_reset_n=destination_release[2];
    always @(posedge source_clk or negedge source_reset_n)
        if(!source_reset_n) gray<=0;else gray<=source_count^(source_count>>1);
    always @(posedge destination_clk or negedge destination_reset_n)
        if(!destination_reset_n) begin meta<=0;sync_value<=0;end
        else begin meta<=gray;sync_value<=meta;end
    integer i;
    always @* begin
        destination_count[31]=sync_value[31];
        for(i=30;i>=0;i=i-1) destination_count[i]=destination_count[i+1]^sync_value[i];
    end
endmodule
