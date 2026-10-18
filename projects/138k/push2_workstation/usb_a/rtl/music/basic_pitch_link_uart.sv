module basic_pitch_link_uart (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire [31:0] bp_report_i,
    input  wire [31:0] tf_report_i,
    input  wire [31:0] nn_report_i,
    input  wire [31:0] sd_report_i,
    output wire        tick_o,
    output wire        sending_o,
    output wire        serial_o
);
    localparam integer INTERVAL_CYCLES = 25_000_000;
    reg [24:0] interval_count;
    reg sending;
    reg [5:0] character;
    reg [127:0] payload;
    wire tx_ready;
    reg [7:0] tx_byte;
    assign tick_o = !sending && interval_count == INTERVAL_CYCLES-1;
    assign sending_o = sending;

    function automatic [7:0] hex_digit(input [3:0] value);
        hex_digit = value < 10 ? 8'd48 + value : 8'd55 + value;
    endfunction

    always @* begin
        case (character)
            0: tx_byte = "B";
            1: tx_byte = "1";
            2: tx_byte = "3";
            3: tx_byte = "8";
            4, 13, 22, 31: tx_byte = " ";
            40: tx_byte = 8'd13;
            41: tx_byte = 8'd10;
            default: tx_byte = hex_digit(payload[127:124]);
        endcase
    end

    uart_tx #(.CLK_HZ(50_000_000), .BAUD(115200)) u_uart (
        .clk(clk_i), .rst_n(rst_ni), .data({24'd0, tx_byte}),
        .valid(sending), .ready(tx_ready), .serial_out(serial_o), .byte_done()
    );

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            interval_count <= 25'd12_500_000;
            sending <= 1'b0;
            character <= 0;
            payload <= 0;
        end else if (!sending) begin
            if (interval_count == INTERVAL_CYCLES-1) begin
                interval_count <= 0;
                payload <= {bp_report_i, tf_report_i, nn_report_i, sd_report_i};
                character <= 0;
                sending <= 1'b1;
            end else interval_count <= interval_count + 1'b1;
        end else if (tx_ready) begin
            if ((character >= 5 && character <= 12) ||
                (character >= 14 && character <= 21) ||
                (character >= 23 && character <= 30) ||
                (character >= 32 && character <= 39))
                payload <= {payload[123:0], 4'd0};
            if (character == 41) sending <= 1'b0;
            else character <= character + 1'b1;
        end
    end
endmodule
