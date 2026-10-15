// 8N1 transmit adapter. Only data[7:0] is serialized.
module uart_tx #(
    parameter integer CLK_HZ = 50000000,
    parameter integer BAUD = 115200
) (
    input wire clk, input wire rst_n,
    input wire [31:0] data, input wire valid, output wire ready,
    output reg serial_out, output wire byte_done
);
    localparam integer BIT_CLKS = (CLK_HZ + BAUD/2) / BAUD;
    reg busy;
    reg [9:0] shift;
    reg [3:0] bit_index;
    reg [31:0] timer;
    assign ready = !busy;
    // Observation of the edge that ends the complete stop bit. It is not
    // the final byte's ready/valid handshake, which starts that byte.
    assign byte_done = busy && timer == 0 && bit_index == 9;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy <= 0; serial_out <= 1; shift <= 10'h3ff; bit_index <= 0; timer <= 0;
        end else if (!busy) begin
            serial_out <= 1;
            if (valid) begin
                shift <= {1'b1,data[7:0],1'b0}; serial_out <= 0;
                bit_index <= 0; timer <= BIT_CLKS-1; busy <= 1;
            end
        end else if (timer != 0) timer <= timer-1;
        else if (bit_index == 9) begin busy <= 0; serial_out <= 1; end
        else begin
            shift <= {1'b1,shift[9:1]}; serial_out <= shift[1];
            bit_index <= bit_index+1'b1; timer <= BIT_CLKS-1;
        end
    end
endmodule
