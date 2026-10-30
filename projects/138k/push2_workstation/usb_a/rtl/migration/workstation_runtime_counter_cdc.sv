// Native runtime implementation of the locked counter CDC contract.
// The source must advance by at most one per source edge. Register Gray at
// the source, retain its bit-flight constraints and two destination stages,
// then decode locally without adding a destination clock of latency.
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
    // Inclusive suffix XOR by parallel prefix: after span k, each bit covers
    // the next 2*k Gray bits. Five combinational levels cover all32 bits.
    wire [31:0] prefix1=sync_value^(sync_value>>1);
    wire [31:0] prefix2=prefix1^(prefix1>>2);
    wire [31:0] prefix4=prefix2^(prefix2>>4);
    wire [31:0] prefix8=prefix4^(prefix4>>8);
    wire [31:0] prefix16=prefix8^(prefix8>>16);
    always @* begin
        destination_count[31]=sync_value[31];
        destination_count[30:0]=prefix16[30:0];
    end
endmodule
