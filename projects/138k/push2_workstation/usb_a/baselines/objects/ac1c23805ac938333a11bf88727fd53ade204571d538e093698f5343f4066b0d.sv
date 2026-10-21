// One outstanding USB-domain MMIO request. A downstream commit is reported
// only by the registered response; stalled CPU/screen requests cannot repeat it.
module gw138k_mmio_pipeline(
    input wire clk,reset_n,
    input wire select_i,write_i,
    input wire [7:0] address_i,
    input wire [31:0] wdata_i,
    output reg ready_o,
    output reg [31:0] rdata_o,
    output reg select_o,write_o,
    output reg [7:0] address_o,
    output reg [31:0] wdata_o,
    input wire ready_i,
    input wire [31:0] rdata_i
);
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin
            select_o<=0;write_o<=0;address_o<=0;wdata_o<=0;
            ready_o<=0;rdata_o<=0;
        end else if(ready_o)begin
            if(select_i)ready_o<=0;
        end else if(select_o)begin
            if(ready_i)begin
                select_o<=0;rdata_o<=rdata_i;ready_o<=1;
            end
        end else if(select_i)begin
            select_o<=1;write_o<=write_i;address_o<=address_i;wdata_o<=wdata_i;
        end
    end
endmodule
