// Derived from example/RTL8723DS_BLE/vendor/rtl8723ds_ble/rtl/bt_uart.v; see NOTICE.md.
// Full duplex 8E1 UART. RX samples each bit at its centre; a parity or stop
// error discards the byte. TX ready is high only between complete characters.
module midi_ble_uart #(
    parameter integer CLK_HZ = 50000000,
    parameter integer BAUD = 115200
) (
    input wire clk, input wire resetn, input wire enable,
    input wire rx, output wire tx,
    input wire [7:0] tx_data, input wire tx_valid,
    output wire tx_ready, output reg tx_done,
    output reg [7:0] rx_data, output reg rx_valid, output reg rx_error
);
    localparam integer DIV = (CLK_HZ + BAUD/2) / BAUD;
    (* ASYNC_REG = "TRUE" *) reg [1:0] rx_sync;
    reg [10:0] tx_shift;
    reg [3:0] tx_bits;
    reg [31:0] tx_count;
    reg tx_busy;
    reg [2:0] rx_state;
    reg [31:0] rx_count;
    reg [2:0] rx_bit;
    reg [7:0] rx_shift;
    reg rx_bad;
    assign tx = (enable && tx_busy) ? tx_shift[0] : 1'b1;
    assign tx_ready = enable && !tx_busy;

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            rx_sync <= 2'b11;
            tx_shift <= 11'h7ff; tx_bits <= 0; tx_count <= 0;
            tx_busy <= 0; tx_done <= 0;
            rx_state <= 0; rx_count <= 0; rx_bit <= 0;
            rx_shift <= 0; rx_data <= 0; rx_valid <= 0;
            rx_bad <= 0; rx_error <= 0;
        end else if (!enable) begin
            rx_sync <= 2'b11;
            tx_shift <= 11'h7ff; tx_bits <= 0; tx_count <= 0;
            tx_busy <= 0; tx_done <= 0;
            rx_state <= 0; rx_count <= 0; rx_bit <= 0;
            rx_shift <= 0; rx_valid <= 0; rx_error <= 0; rx_bad <= 0;
        end else begin
            rx_sync <= {rx_sync[0], rx};
            tx_done <= 0; rx_valid <= 0; rx_error <= 0;
            if (!tx_busy) begin
                if (tx_valid) begin
                    tx_shift <= {1'b1, ^tx_data, tx_data, 1'b0};
                    tx_count <= DIV-1; tx_bits <= 0; tx_busy <= 1;
                end
            end else if (tx_count != 0) tx_count <= tx_count - 1;
            else if (tx_bits == 10) begin
                tx_busy <= 0; tx_done <= 1;
            end else begin
                tx_shift <= {1'b1, tx_shift[10:1]};
                tx_bits <= tx_bits + 1; tx_count <= DIV-1;
            end

            case (rx_state)
                0: if (!rx_sync[1]) begin
                    rx_state <= 1; rx_count <= DIV/2-1; rx_bad <= 0;
                end
                1: if (rx_count != 0) rx_count <= rx_count - 1;
                   else if (rx_sync[1]) rx_state <= 0;
                   else begin rx_state <= 2; rx_count <= DIV-1; rx_bit <= 0; end
                2: if (rx_count != 0) rx_count <= rx_count - 1;
                   else begin
                       rx_shift[rx_bit] <= rx_sync[1]; rx_count <= DIV-1;
                       if (rx_bit == 7) rx_state <= 3;
                       else rx_bit <= rx_bit + 1;
                   end
                3: if (rx_count != 0) rx_count <= rx_count - 1;
                   else begin
                       rx_bad <= ((^rx_shift) != rx_sync[1]);
                       rx_count <= DIV-1; rx_state <= 4;
                   end
                4: if (rx_count != 0) rx_count <= rx_count - 1;
                   else begin
                       rx_state <= 0;
                       if (rx_bad || !rx_sync[1]) rx_error <= 1;
                       else begin rx_data <= rx_shift; rx_valid <= 1; end
                   end
                default: rx_state <= 0;
            endcase
        end
    end
endmodule
