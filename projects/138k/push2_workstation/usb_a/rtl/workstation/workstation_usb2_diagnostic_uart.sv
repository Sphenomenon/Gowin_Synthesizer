module workstation_usb2_diagnostic_uart #(
    parameter integer CLOCK_HZ = 48000000,
    parameter integer BAUD = 115200,
    parameter integer REPORT_CYCLES = CLOCK_HZ / 4
) (
    input wire clk, reset_n,
    input wire [511:0] report_i,
    output wire uart_tx_o
);
    localparam integer TIMER_WIDTH = REPORT_CYCLES < 2 ? 1 : $clog2(REPORT_CYCLES);
    reg [TIMER_WIDTH-1:0] timer_q;
    reg [511:0] snapshot_q;
    reg busy_q;
    reg [2:0] phase_q;
    reg [3:0] words_left_q, digits_left_q;
    reg [7:0] character;
    wire uart_wait;
    wire [3:0] nibble = snapshot_q[511:508];
    always @* begin
        case (phase_q)
            0: character = "U";
            1: character = "2";
            2, 4: character = " ";
            3: character = nibble < 10 ? 8'd48 + {4'd0, nibble} : 8'd55 + {4'd0, nibble};
            5: character = 8'h0d;
            default: character = 8'h0a;
        endcase
    end
    simpleuart #(.DEFAULT_DIV((CLOCK_HZ + BAUD / 2) / BAUD - 2)) transmitter (
        .clk(clk), .resetn(reset_n), .ser_tx(uart_tx_o), .ser_rx(1'b1),
        .reg_div_we(4'd0), .reg_div_di(32'd0), .reg_div_do(),
        .reg_dat_we(busy_q), .reg_dat_re(1'b0), .reg_dat_di({24'd0, character}),
        .reg_dat_do(), .reg_dat_wait(uart_wait)
    );
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            timer_q <= 0;
            snapshot_q <= 0;
            busy_q <= 0;
            phase_q <= 0;
            words_left_q <= 0;
            digits_left_q <= 0;
        end else begin
            if (timer_q == REPORT_CYCLES - 1) begin
                timer_q <= 0;
                if (!busy_q) begin
                    snapshot_q <= report_i;
                    busy_q <= 1;
                    phase_q <= 0;
                    words_left_q <= 15;
                    digits_left_q <= 7;
                end
            end else timer_q <= timer_q + 1'b1;
            if (busy_q && !uart_wait) begin
                case (phase_q)
                    0, 1, 2: phase_q <= phase_q + 1'b1;
                    3: begin
                        snapshot_q <= {snapshot_q[507:0], 4'd0};
                        if (digits_left_q == 0) phase_q <= words_left_q == 0 ? 5 : 4;
                        else digits_left_q <= digits_left_q - 1'b1;
                    end
                    4: begin
                        words_left_q <= words_left_q - 1'b1;
                        digits_left_q <= 7;
                        phase_q <= 3;
                    end
                    5: phase_q <= 6;
                    default: busy_q <= 0;
                endcase
            end
        end
    end
endmodule
