module ddr_calibration_diagnostic (
    input wire clk_50m,
    output wire debug_uart_tx,
    output wire flash_clk, flash_cs_n, flash_mosi, flash_wp_n, flash_hold_n,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs, ddr_ras, ddr_cas, ddr_we,
    output wire ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs, ddr_dqs_n
);
    wire reset_n, ui_clk, ui_reset_n, calibrated, locked;
    wire request_valid, request_ready, request_write, app_ready, app_write_ready;
    wire response_valid, bist_done, bist_failed;
    wire [28:0] request_address, first_error_address;
    wire [255:0] request_data, response_data;
    wire [31:0] error_count;
    reset_release u_reset(.clk(clk_50m), .ext_reset_n(1'b1), .reset_n(reset_n));
    assign request_ready = app_ready && (!request_write || app_write_ready);
    ddr3_platform u_memory (
        .clk_50m(clk_50m), .rst_n(reset_n), .ui_clk(ui_clk), .ui_rst_n(ui_reset_n),
        .calib_done(calibrated), .pll_locked(locked),
        .app_cmd(request_write ? 3'd0 : 3'd1), .app_en(request_valid && request_ready),
        .app_addr(request_address), .app_rdy(app_ready),
        .app_wdata(request_data), .app_wmask(32'd0),
        .app_wren(request_valid && request_ready && request_write),
        .app_wend(1'b1), .app_wrdy(app_write_ready),
        .app_rdata(response_data), .app_rvalid(response_valid), .app_rend(),
        .ddr_addr(ddr_addr), .ddr_bank(ddr_bank), .ddr_cs(ddr_cs), .ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas), .ddr_we(ddr_we), .ddr_ck(ddr_ck), .ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke), .ddr_odt(ddr_odt), .ddr_reset_n(ddr_reset_n),
        .ddr_dm(ddr_dm), .ddr_dq(ddr_dq), .ddr_dqs(ddr_dqs), .ddr_dqs_n(ddr_dqs_n)
    );
    ddr3_bist u_bist (
        .clk(ui_clk), .rst_n(ui_reset_n), .req_valid(request_valid), .req_ready(request_ready),
        .req_write(request_write), .req_addr(request_address), .req_wdata(request_data),
        .rsp_valid(response_valid), .rsp_data(response_data), .done(bist_done),
        .failed(bist_failed), .error_count(error_count), .first_error_addr(first_error_address)
    );
    (* ASYNC_REG = "TRUE" *) reg [1:0] ui_release;
    always @(posedge ui_clk or negedge reset_n)
        if (!reset_n) ui_release <= 0;
        else ui_release <= {ui_release[0], 1'b1};
    reg [7:0] ui_counter, ui_counter_gray;
    always @(posedge ui_clk or negedge ui_release[1])
        if (!ui_release[1]) begin
            ui_counter <= 0;
            ui_counter_gray <= 0;
        end else begin
            ui_counter <= ui_counter + 1'b1;
            ui_counter_gray <= ui_counter ^ (ui_counter >> 1);
        end
    (* ASYNC_REG = "TRUE" *) reg [7:0] status_meta, status_sync;
    (* ASYNC_REG = "TRUE" *) reg [7:0] ui_gray_meta, ui_gray_sync;
    always @(posedge clk_50m or negedge reset_n)
        if (!reset_n) begin
            status_meta <= 0;
            status_sync <= 0;
            ui_gray_meta <= 0;
            ui_gray_sync <= 0;
        end else begin
            status_meta <= {app_write_ready, app_ready, bist_failed, bist_done,
                            ui_reset_n, calibrated, locked, reset_n};
            status_sync <= status_meta;
            ui_gray_meta <= ui_counter_gray;
            ui_gray_sync <= ui_gray_meta;
        end
    assign debug_uart_tx = ^{status_sync, ui_gray_sync, error_count, first_error_address};
    assign flash_clk = 1'b0;
    assign flash_cs_n = 1'b1;
    assign flash_mosi = 1'b0;
    assign flash_wp_n = 1'b1;
    assign flash_hold_n = 1'b1;
endmodule
