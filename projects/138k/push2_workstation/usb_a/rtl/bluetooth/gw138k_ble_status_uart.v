// Coherent, read-only ASCII snapshot on a separate 115200 8N1 status UART.
// Line: BLE1 + space + 24 words (8 uppercase hex digits each, word 0 first) + LF.
module gw138k_ble_status_uart #(
    parameter integer CLK_HZ = 50000000,
    parameter integer REPORT_MS = 1000
) (
    input wire clk, resetn,
    input wire [767:0] debug,
    output wire serial_out
);
    localparam integer REPORT_TICKS = (CLK_HZ/1000)*REPORT_MS;
    reg [31:0] divider;
    reg sending;
    reg [7:0] index;
    reg [767:0] snapshot;
    wire ready;
    reg [7:0] data;
    reg [3:0] digit;
    integer offset;
    always @* begin
        data = 8'h0a;
        digit = 0;
        offset = 0;
        case (index)
            0: data = "B";
            1: data = "L";
            2: data = "E";
            3: data = "1";
            4: data = " ";
            default: if (index < 197) begin
                // Each word is big-endian text; words ascend from debug[31:0].
                offset = ((index-5)/8)*32 + (7-((index-5)%8))*4;
                digit = snapshot[offset +: 4];
                data = digit < 10 ? 8'h30 + {4'd0,digit} : 8'h41 + {4'd0,digit} - 8'd10;
            end
        endcase
    end
    uart_tx #(.CLK_HZ(CLK_HZ), .BAUD(115200)) u_uart (
        .clk(clk), .rst_n(resetn), .data({24'd0,data}), .valid(sending),
        .ready(ready), .serial_out(serial_out), .byte_done()
    );
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            divider <= 0; sending <= 0; index <= 0; snapshot <= 0;
        end else begin
            if (!sending) begin
                if (divider == REPORT_TICKS-1) begin
                    divider <= 0; snapshot <= debug; index <= 0; sending <= 1;
                end else divider <= divider+1'b1;
            end else if (ready) begin
                if (index == 197) begin sending <= 0; index <= 0; end
                else index <= index+1'b1;
            end
        end
    end
endmodule
