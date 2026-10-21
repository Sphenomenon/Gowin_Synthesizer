module workstation_usb3300_host_init #(
    parameter integer STARTUP_CYCLES = 600,
    parameter integer STAGE_TIMEOUT_CYCLES = 60000,
    parameter integer MAX_PREEMPT_RETRIES = 3
)(
    input wire clk_ulpi,
    input wire reset_n,
    input wire link_fatal_i,
    output wire csr_valid_o,
    input wire csr_ready_i,
    output reg csr_write_o,
    output reg [5:0] csr_address_o,
    output reg [7:0] csr_data_o,
    input wire csr_response_valid_i,
    output wire csr_response_ready_o,
    input wire [7:0] csr_response_data_i,
    input wire [2:0] csr_response_error_i,
    output wire ready_o,
    output wire failed_o,
    output reg [3:0] failure_code_o,
    output reg [4:0] stage_o,
    output reg [7:0] retry_count_o,
    output reg [7:0] last_data_o,
    output reg [2:0] last_error_o,
    output reg [15:0] vendor_id_o,
    output reg [15:0] product_id_o,
    output reg [7:0] function_control_o,
    output reg [7:0] interface_control_o,
    output reg [7:0] otg_control_o
);
    localparam [2:0] STARTUP = 0;
    localparam [2:0] REQUEST = 1;
    localparam [2:0] RESPONSE = 2;
    localparam [2:0] DONE = 3;
    localparam [2:0] FAILED = 4;
    localparam integer STARTUP_WIDTH = STARTUP_CYCLES < 2 ? 1 : $clog2(STARTUP_CYCLES);
    localparam integer TIMEOUT_WIDTH = STAGE_TIMEOUT_CYCLES < 2 ? 1 : $clog2(STAGE_TIMEOUT_CYCLES);
    localparam [STARTUP_WIDTH-1:0] STARTUP_LIMIT = STARTUP_WIDTH'(STARTUP_CYCLES - 1);
    localparam [TIMEOUT_WIDTH-1:0] TIMEOUT_LIMIT = TIMEOUT_WIDTH'(STAGE_TIMEOUT_CYCLES - 1);
    localparam [7:0] RETRY_LIMIT = 8'(MAX_PREEMPT_RETRIES);
    localparam [4:0] LAST_STAGE = 17;
    reg [2:0] state_q;
    reg [STARTUP_WIDTH-1:0] startup_q;
    reg [TIMEOUT_WIDTH-1:0] elapsed_q;
    reg [7:0] stage_retries_q;
    reg [7:0] expected_data;

    assign csr_valid_o = reset_n && !link_fatal_i && state_q == REQUEST;
    assign csr_response_ready_o = reset_n && state_q == RESPONSE;
    assign ready_o = reset_n && !link_fatal_i && state_q == DONE;
    assign failed_o = reset_n && state_q == FAILED;

    always @* begin
        csr_write_o = 1'b0;
        csr_address_o = 6'h00;
        csr_data_o = 8'h00;
        expected_data = 8'h00;
        case (stage_o)
            0: begin csr_address_o = 6'h00; expected_data = 8'h24; end
            1: begin csr_address_o = 6'h01; expected_data = 8'h04; end
            2: begin csr_address_o = 6'h02; expected_data = 8'h04; end
            3: begin csr_address_o = 6'h03; expected_data = 8'h00; end
            4: begin csr_write_o = 1'b1; csr_address_o = 6'h04; csr_data_o = 8'h49; end
            5: begin csr_address_o = 6'h04; expected_data = 8'h49; end
            6: begin csr_write_o = 1'b1; csr_address_o = 6'h07; csr_data_o = 8'h10; end
            7: begin csr_address_o = 6'h07; expected_data = 8'h10; end
            8: begin csr_write_o = 1'b1; csr_address_o = 6'h0a; csr_data_o = 8'h06; end
            9: begin csr_address_o = 6'h0a; expected_data = 8'h06; end
            10: begin csr_write_o = 1'b1; csr_address_o = 6'h16; csr_data_o = 8'h55; end
            11: begin csr_address_o = 6'h16; expected_data = 8'h55; end
            12: begin csr_write_o = 1'b1; csr_address_o = 6'h16; csr_data_o = 8'haa; end
            13: begin csr_address_o = 6'h16; expected_data = 8'haa; end
            14: begin csr_write_o = 1'b1; csr_address_o = 6'h16; csr_data_o = 8'h00; end
            15: begin csr_address_o = 6'h16; expected_data = 8'h00; end
            16: begin csr_write_o = 1'b1; csr_address_o = 6'h04; csr_data_o = 8'h41; end
            17: begin csr_address_o = 6'h04; expected_data = 8'h41; end
            default: begin end
        endcase
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= STARTUP;
            startup_q <= {STARTUP_WIDTH{1'b0}};
            elapsed_q <= {TIMEOUT_WIDTH{1'b0}};
            stage_retries_q <= 8'h00;
            failure_code_o <= 4'h0;
            stage_o <= 5'd0;
            retry_count_o <= 8'h00;
            last_data_o <= 8'h00;
            last_error_o <= 3'd0;
            vendor_id_o <= 16'h0000;
            product_id_o <= 16'h0000;
            function_control_o <= 8'h00;
            interface_control_o <= 8'h00;
            otg_control_o <= 8'h00;
        end else begin
            if (csr_response_valid_i && csr_response_ready_o) begin
                last_data_o <= csr_response_data_i;
                last_error_o <= csr_response_error_i;
            end
            if (link_fatal_i && state_q != FAILED) begin
                state_q <= FAILED;
                failure_code_o <= 4'd1;
            end else begin
                case (state_q)
                    STARTUP: begin
                        if (startup_q == STARTUP_LIMIT)
                            state_q <= REQUEST;
                        else
                            startup_q <= startup_q + 1'b1;
                    end
                    REQUEST, RESPONSE: begin
                        if (elapsed_q == TIMEOUT_LIMIT) begin
                            state_q <= FAILED;
                            failure_code_o <= 4'd2;
                        end else begin
                            elapsed_q <= elapsed_q + 1'b1;
                            if (state_q == REQUEST) begin
                                if (csr_valid_o && csr_ready_i)
                                    state_q <= RESPONSE;
                            end else if (csr_response_valid_i && csr_response_ready_o) begin
                                if (csr_response_error_i == 3'd2) begin
                                    if (stage_retries_q == RETRY_LIMIT) begin
                                        state_q <= FAILED;
                                        failure_code_o <= 4'd6;
                                    end else begin
                                        stage_retries_q <= stage_retries_q + 1'b1;
                                        if (retry_count_o != 8'hff)
                                            retry_count_o <= retry_count_o + 1'b1;
                                        state_q <= REQUEST;
                                    end
                                end else if (csr_response_error_i != 3'd0) begin
                                    state_q <= FAILED;
                                    failure_code_o <= 4'd3;
                                end else begin
                                    if (!csr_write_o) begin
                                        case (stage_o)
                                            0: vendor_id_o[7:0] <= csr_response_data_i;
                                            1: vendor_id_o[15:8] <= csr_response_data_i;
                                            2: product_id_o[7:0] <= csr_response_data_i;
                                            3: product_id_o[15:8] <= csr_response_data_i;
                                            5, 17: function_control_o <= csr_response_data_i;
                                            7: interface_control_o <= csr_response_data_i;
                                            9: otg_control_o <= csr_response_data_i;
                                            default: begin end
                                        endcase
                                    end
                                    if (!csr_write_o && csr_response_data_i != expected_data) begin
                                        state_q <= FAILED;
                                        failure_code_o <= stage_o < 4 ? 4'd4 : 4'd5;
                                    end else begin
                                        elapsed_q <= {TIMEOUT_WIDTH{1'b0}};
                                        stage_retries_q <= 8'h00;
                                        if (stage_o == LAST_STAGE)
                                            state_q <= DONE;
                                        else begin
                                            stage_o <= stage_o + 1'b1;
                                            state_q <= REQUEST;
                                        end
                                    end
                                end
                            end
                        end
                    end
                    DONE, FAILED: begin end
                    default: begin
                        state_q <= FAILED;
                        failure_code_o <= 4'd7;
                    end
                endcase
            end
        end
    end
endmodule
