module workstation_usb2_cpu_bridge #(
    parameter integer TRANSACTION_TIMEOUT_CYCLES = 120000
)(
    input wire clk_cpu,
    input wire clk_ulpi,
    input wire reset_n,
    input wire session_reset_n_i,
    input wire reg_cs_i,
    input wire reg_wr_i,
    input wire [7:0] reg_addr_i,
    input wire [31:0] reg_wdata_i,
    input wire [3:0] reg_be_i,
    output reg reg_ack_o,
    output reg reg_error_o,
    output reg [31:0] reg_rdata_o,
    output wire irq_o,
    output reg enable_o,
    output wire hs_enable_o,
    output reg reset_request_o,
    input wire [15:0] status_i,
    input wire [31:0] diagnostic_i,
    input wire [31:0] sof_count_i,
    input wire [2:0] reference_fault_i,
    output wire command_valid_o,
    input wire command_ready_i,
    output wire [7:0] command_pid_o,
    output wire [6:0] command_device_o,
    output wire [3:0] command_endpoint_o,
    output wire command_toggle_o,
    output wire [9:0] command_length_o,
    output wire [7:0] transmit_data_o,
    output wire transmit_valid_o,
    input wire transmit_ready_i,
    input wire result_valid_i,
    output wire result_ready_o,
    input wire [3:0] result_status_i,
    input wire [7:0] result_pid_i,
    input wire [9:0] result_length_i,
    input wire [7:0] receive_data_i,
    input wire receive_valid_i,
    output wire receive_ready_o,
    input wire receive_last_i
);
    localparam [2:0] IDLE = 0, COMMAND = 1, UPLOAD = 2, RESULT = 3,
                     RECEIVE = 4, PUBLISH = 5, RECOVERY = 6;
    localparam integer TIMER_WIDTH = TRANSACTION_TIMEOUT_CYCLES < 2 ? 1 : $clog2(TRANSACTION_TIMEOUT_CYCLES);
    (* async_reg = "true" *) reg [1:0] cpu_release_q, ulpi_release_q;
    (* async_reg = "true" *) reg [1:0] cpu_session_q, ulpi_session_q;
    (* async_reg = "true" *) reg [1:0] request_sync_q, result_sync_q;
    (* async_reg = "true" *) reg [1:0] reset_sync_q, reset_ack_sync_q, hs_sync_q;
    (* async_reg = "true" *) reg [1:0] snapshot_sync_q, snapshot_ack_sync_q;
    (* async_reg = "true" *) reg [2:0] reference_fault_meta_q, reference_fault_sync_q;
    reg hs_cpu_q, reset_toggle_q, reset_ack_q;
    reg served_q, previous_session_q, cancelled_q;
    reg [31:0] generation_q;
    reg [79:0] snapshot_mailbox_q, snapshot_cpu_q;
    reg snapshot_toggle_q, snapshot_ack_q, snapshot_valid_q;
    reg [7:0] transmit_memory [0:511];
    reg [7:0] receive_memory [0:511];
    reg [7:0] transmit_read_q, receive_read_q;
    reg [9:0] transmit_count_q, receive_index_q;
    reg [29:0] descriptor_cpu_q, descriptor_ulpi_q;
    reg request_toggle_q, result_toggle_q, busy_q, done_q;
    reg [21:0] result_mailbox_q, result_cpu_q;
    reg [2:0] state_q;
    reg [9:0] upload_index_q, receive_count_q;
    reg [TIMER_WIDTH-1:0] elapsed_q;
    reg recovery_q;
    reg access_error;
    reg [31:0] read_value;
    wire cpu_reset_n = cpu_release_q[1];
    wire ulpi_reset_n = ulpi_release_q[1];
    wire channel_reset_n = reset_n && enable_o && session_reset_n_i;
    wire cpu_session_ready = cpu_session_q[1];
    wire ulpi_session_ready = ulpi_session_q[1];
    wire reset_pending = reset_toggle_q != reset_ack_sync_q[1];
    wire access = cpu_reset_n && reg_cs_i && !served_q;
    wire write_access = access && reg_wr_i && !access_error;
    wire read_access = access && !reg_wr_i && !access_error;
    wire upload_write = write_access && reg_addr_i == 8'h10;
    wire receive_read = read_access && reg_addr_i == 8'h14;
    wire command_write = write_access && reg_addr_i == 8'h0c;
    wire action_write = write_access && reg_addr_i == 8'h1c;
    wire [9:0] requested_length = reg_wdata_i[29:20];
    wire requested_upload = reg_wdata_i[7:0] == 8'he1 || reg_wdata_i[7:0] == 8'h2d;
    wire [9:0] receive_remaining = done_q ? result_cpu_q[9:0] - receive_index_q : 10'd0;
    wire [8:0] transmit_address = transmit_valid_o && transmit_ready_i ?
                                  9'(upload_index_q + 10'd1) : upload_index_q[8:0];
    wire [8:0] receive_address = receive_read ? 9'(receive_index_q + 10'd1) : receive_index_q[8:0];
    wire receive_write = ulpi_session_ready && state_q == RECEIVE && receive_valid_i;
    wire active_transfer = state_q != IDLE && state_q != PUBLISH && state_q != RECOVERY;

    assign irq_o = done_q || cancelled_q;
    assign hs_enable_o = hs_sync_q[1];
    assign command_valid_o = ulpi_session_ready && state_q == COMMAND;
    assign command_pid_o = descriptor_ulpi_q[7:0];
    assign command_device_o = descriptor_ulpi_q[14:8];
    assign command_endpoint_o = descriptor_ulpi_q[18:15];
    assign command_toggle_o = descriptor_ulpi_q[19];
    assign command_length_o = descriptor_ulpi_q[29:20];
    assign transmit_valid_o = ulpi_session_ready && state_q == UPLOAD;
    assign transmit_data_o = transmit_read_q;
    assign result_ready_o = ulpi_session_ready && state_q == RESULT;
    assign receive_ready_o = ulpi_session_ready && state_q == RECEIVE;

    always @(posedge clk_cpu or negedge reset_n)
        if (!reset_n) cpu_release_q <= 0;
        else cpu_release_q <= {cpu_release_q[0], 1'b1};
    always @(posedge clk_ulpi or negedge reset_n)
        if (!reset_n) ulpi_release_q <= 0;
        else ulpi_release_q <= {ulpi_release_q[0], 1'b1};
    always @(posedge clk_cpu or negedge channel_reset_n)
        if (!channel_reset_n) cpu_session_q <= 0;
        else cpu_session_q <= {cpu_session_q[0], 1'b1};
    always @(posedge clk_ulpi or negedge channel_reset_n)
        if (!channel_reset_n) ulpi_session_q <= 0;
        else ulpi_session_q <= {ulpi_session_q[0], 1'b1};

    always @* begin
        access_error = reg_addr_i[1:0] != 0;
        read_value = 0;
        if (reg_wr_i) begin
            case (reg_addr_i)
                8'h04: access_error = reg_be_i != 4'hf || reg_wdata_i[31:3] != 0 ||
                    (enable_o && reg_wdata_i[1] != hs_cpu_q) ||
                    (reg_wdata_i[2] && (!enable_o || !reg_wdata_i[0] || reset_pending));
                8'h0c: access_error = reg_be_i != 4'hf || !cpu_session_ready || busy_q || done_q ||
                    reg_wdata_i[31:30] != 0 || requested_length > (snapshot_cpu_q[2] ? 10'd512 : 10'd64) ||
                    (requested_upload ? transmit_count_q != requested_length : transmit_count_q != 0) ||
                    !(reg_wdata_i[7:0] == 8'he1 || reg_wdata_i[7:0] == 8'h69 ||
                      reg_wdata_i[7:0] == 8'h2d || reg_wdata_i[7:0] == 8'hb4) ||
                    (reg_wdata_i[7:0] == 8'h2d && (requested_length != 8 || reg_wdata_i[19])) ||
                    (reg_wdata_i[7:0] == 8'hb4 && (!snapshot_cpu_q[2] || requested_length != 0));
                8'h10: access_error = !(reg_be_i == 4'h1 || reg_be_i == 4'hf) ||
                    !cpu_session_ready || busy_q || done_q || transmit_count_q == 512;
                8'h1c: access_error = reg_be_i != 4'hf || reg_wdata_i[31:3] != 0 || busy_q;
                default: access_error = 1;
            endcase
        end else begin
            case (reg_addr_i)
                8'h00: read_value = 32'h55324801;
                8'h04: read_value = {15'd0, reset_pending, 14'd0, hs_cpu_q, enable_o};
                8'h08: read_value = {10'd0, snapshot_valid_q, reset_pending, cancelled_q,
                                    done_q, busy_q, cpu_session_ready, snapshot_cpu_q[15:0]};
                8'h14: begin
                    read_value = {24'd0, receive_read_q};
                    access_error = !cpu_session_ready || !done_q || receive_remaining == 0;
                end
                8'h18: read_value = {done_q, 5'd0, result_cpu_q[9:0], result_cpu_q[17:10], 4'd0, result_cpu_q[21:18]};
                8'h20: read_value = {22'd0, transmit_count_q};
                8'h24: read_value = {22'd0, receive_remaining};
                8'h28: read_value = generation_q;
                8'h2c: read_value = snapshot_cpu_q[47:16];
                8'h30: read_value = snapshot_cpu_q[79:48];
                8'h34: read_value = {8'd0, 4'b1111, 10'd64, 10'd512};
                8'h38: read_value = {29'd0, reference_fault_sync_q};
                default: access_error = 1;
            endcase
        end
    end

    always @(posedge clk_cpu or negedge cpu_reset_n) begin
        if (!cpu_reset_n) begin
            reg_ack_o <= 0; reg_error_o <= 0; reg_rdata_o <= 0; served_q <= 0;
            enable_o <= 0; hs_cpu_q <= 1; reset_toggle_q <= 0; reset_ack_sync_q <= 0;
            snapshot_sync_q <= 0; snapshot_ack_q <= 0; snapshot_cpu_q <= 0; snapshot_valid_q <= 0;
            previous_session_q <= 0; generation_q <= 0; cancelled_q <= 0;
            reference_fault_meta_q <= 0; reference_fault_sync_q <= 0;
        end else begin
            reg_ack_o <= 0; reg_error_o <= 0;
            if (!reg_cs_i) served_q <= 0;
            reset_ack_sync_q <= {reset_ack_sync_q[0], reset_ack_q};
            reference_fault_meta_q <= reference_fault_i; reference_fault_sync_q <= reference_fault_meta_q;
            snapshot_sync_q <= {snapshot_sync_q[0], snapshot_toggle_q};
            if (snapshot_sync_q[1] != snapshot_ack_q) begin
                snapshot_cpu_q <= snapshot_mailbox_q; snapshot_ack_q <= snapshot_sync_q[1]; snapshot_valid_q <= 1;
            end
            if (access) begin
                served_q <= 1; reg_ack_o <= 1; reg_error_o <= access_error;
                reg_rdata_o <= access_error ? 32'd0 : read_value;
                if (write_access && reg_addr_i == 8'h04) begin
                    enable_o <= reg_wdata_i[0]; hs_cpu_q <= reg_wdata_i[1];
                    if (reg_wdata_i[2]) reset_toggle_q <= !reset_toggle_q;
                end
                if (action_write && reg_wdata_i[2]) cancelled_q <= 0;
            end
            previous_session_q <= cpu_session_ready;
            if (previous_session_q && !cpu_session_ready) begin
                generation_q <= generation_q + 1'b1; cancelled_q <= 1;
            end
        end
    end

    always @(posedge clk_cpu or negedge channel_reset_n) begin
        if (!channel_reset_n) begin
            transmit_count_q <= 0; receive_index_q <= 0; descriptor_cpu_q <= 0;
            request_toggle_q <= 0; result_sync_q <= 0; result_cpu_q <= 0; busy_q <= 0; done_q <= 0;
        end else if (cpu_session_ready) begin
            result_sync_q <= {result_sync_q[0], result_toggle_q};
            if (upload_write) transmit_count_q <= transmit_count_q + 1'b1;
            if (command_write) begin
                descriptor_cpu_q <= reg_wdata_i[29:0]; request_toggle_q <= !request_toggle_q; busy_q <= 1;
            end
            if (busy_q && result_sync_q[1] == request_toggle_q) begin
                result_cpu_q <= result_mailbox_q; busy_q <= 0; done_q <= 1; receive_index_q <= 0;
            end
            if (receive_read) receive_index_q <= receive_index_q + 1'b1;
            if (action_write) begin
                if (reg_wdata_i[0]) begin done_q <= 0; result_cpu_q <= 0; receive_index_q <= 0; transmit_count_q <= 0; end
                if (reg_wdata_i[1]) transmit_count_q <= 0;
            end
        end
    end

    always @(posedge clk_cpu) begin
        if (upload_write) transmit_memory[transmit_count_q[8:0]] <= reg_wdata_i[7:0];
        receive_read_q <= receive_memory[receive_address];
    end
    always @(posedge clk_ulpi) begin
        transmit_read_q <= transmit_memory[transmit_address];
        if (receive_write) receive_memory[receive_count_q[8:0]] <= receive_data_i;
    end

    always @(posedge clk_ulpi or negedge ulpi_reset_n) begin
        if (!ulpi_reset_n) begin
            hs_sync_q <= 0; reset_sync_q <= 0; reset_ack_q <= 0; reset_request_o <= 0;
            snapshot_ack_sync_q <= 0; snapshot_toggle_q <= 0; snapshot_mailbox_q <= 0;
        end else begin
            hs_sync_q <= {hs_sync_q[0], hs_cpu_q};
            reset_sync_q <= {reset_sync_q[0], reset_toggle_q};
            reset_request_o <= recovery_q;
            if (reset_sync_q[1] != reset_ack_q) begin
                reset_request_o <= 1; reset_ack_q <= reset_sync_q[1];
            end
            snapshot_ack_sync_q <= {snapshot_ack_sync_q[0], snapshot_ack_q};
            if (snapshot_ack_sync_q[1] == snapshot_toggle_q) begin
                snapshot_mailbox_q <= {sof_count_i, diagnostic_i, status_i}; snapshot_toggle_q <= !snapshot_toggle_q;
            end
        end
    end

    always @(posedge clk_ulpi or negedge channel_reset_n) begin
        if (!channel_reset_n) begin
            request_sync_q <= 0; result_toggle_q <= 0; result_mailbox_q <= 0; descriptor_ulpi_q <= 0;
            state_q <= IDLE; upload_index_q <= 0; receive_count_q <= 0; elapsed_q <= 0; recovery_q <= 0;
        end else if (ulpi_session_ready) begin
            request_sync_q <= {request_sync_q[0], request_toggle_q}; recovery_q <= 0;
            if (active_transfer) elapsed_q <= elapsed_q + 1'b1;
            else elapsed_q <= 0;
            case (state_q)
                IDLE: if (request_sync_q[1] != result_toggle_q) begin
                    descriptor_ulpi_q <= descriptor_cpu_q; upload_index_q <= 0; receive_count_q <= 0; state_q <= COMMAND;
                end
                COMMAND: if (command_ready_i) begin
                    state_q <= (command_pid_o == 8'he1 || command_pid_o == 8'h2d) && command_length_o != 0 ? UPLOAD : RESULT;
                end
                UPLOAD: if (transmit_ready_i) begin
                    if (upload_index_q + 10'd1 == command_length_o) state_q <= RESULT;
                    else upload_index_q <= upload_index_q + 1'b1;
                end
                RESULT: if (result_valid_i) begin
                    result_mailbox_q <= {result_status_i, result_pid_i, result_length_i};
                    state_q <= result_length_i == 0 ? PUBLISH : RECEIVE;
                    if (result_length_i > 512 || (result_status_i != 0 && result_length_i != 0)) begin
                        state_q <= RECOVERY; recovery_q <= 1;
                    end
                end
                RECEIVE: if (receive_valid_i) begin
                    receive_count_q <= receive_count_q + 1'b1;
                    if (receive_last_i != (receive_count_q + 10'd1 == result_mailbox_q[9:0])) begin
                        state_q <= RECOVERY; recovery_q <= 1;
                    end else if (receive_last_i) state_q <= PUBLISH;
                end
                PUBLISH: begin result_toggle_q <= request_sync_q[1]; state_q <= IDLE; end
                RECOVERY: begin end
                default: begin state_q <= RECOVERY; recovery_q <= 1; end
            endcase
            if (active_transfer && elapsed_q == TIMER_WIDTH'(TRANSACTION_TIMEOUT_CYCLES - 1)) begin
                state_q <= RECOVERY; recovery_q <= 1;
            end
        end
    end
endmodule
