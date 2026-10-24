// Coherent snapshot, 115200 8N1: RF13 <32 words, eight hex digits each> LF.
// Words 0..23 are the frozen BLE status ABI; words 24..31 are SDIO discovery.
module radio_status_uart #(
    parameter integer CLK_HZ=50000000,
    parameter integer REPORT_MS=500
)(input wire clk, resetn, input wire [1023:0] debug, output wire serial_out);
    localparam integer REPORT_TICKS=(CLK_HZ/1000)*REPORT_MS;
    reg [31:0] divider;
    reg sending;
    reg [8:0] index;
    reg [1023:0] snapshot;
    wire ready;
    reg [7:0] data;
    reg [3:0] digit;
    integer offset;
    always @* begin
        data=8'h0a; digit=0; offset=0;
        case(index)
            0: data="R"; 1: data="F"; 2: data="1"; 3: data="3"; 4: data=" ";
            default: if(index<261) begin
                offset=((index-5)/8)*32+(7-((index-5)%8))*4;
                digit=snapshot[offset +: 4];
                data=digit<10 ? 8'h30+digit : 8'h41+digit-10;
            end
        endcase
    end
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(115200)) tx(
        .clk(clk),.rst_n(resetn),.data({24'd0,data}),.valid(sending),
        .ready(ready),.serial_out(serial_out),.byte_done());
    always @(posedge clk) begin
        if(!resetn) begin divider<=0; sending<=0; index<=0; snapshot<=0; end
        else if(!sending) begin
            if(divider==REPORT_TICKS-1) begin
                divider<=0; snapshot<=debug; index<=0; sending<=1;
            end else divider<=divider+1'b1;
        end else if(ready) begin
            if(index==261) begin sending<=0; index<=0; end
            else index<=index+1'b1;
        end
    end
endmodule
