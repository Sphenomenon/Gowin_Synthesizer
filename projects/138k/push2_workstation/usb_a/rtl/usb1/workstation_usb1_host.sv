module workstation_usb1_host #(
    parameter ROM_FILE = "push2_usb_a.hex"
)(
    input wire clk_usb, reset_n,
    inout wire usb_dp, usb_dm,
    input wire uart_rx_i,
    output wire uart_tx_o,
    output wire service_valid_o, service_write_o,
    output wire [7:0] service_address_o,
    output wire [31:0] service_write_data_o,
    output wire [3:0] service_mask_o,
    input wire service_ready_i, service_error_i,
    input wire [31:0] service_read_data_i,
    output wire [3:0] fault_o,
    output wire [31:0] fault_address_o,
    output wire [1:0] line_state_o,
    output reg session_valid_o
);
    wire instruction_valid, instruction_ready, instruction_response, instruction_error;
    wire [31:0] instruction_address, instruction_data;
    wire data_valid, data_ready, data_write, data_response;
    wire [31:0] data_address, data_write_data, data_read_data;
    wire [3:0] data_mask;
    wire usb_cs, usb_write, usb_ack;
    wire [7:0] usb_address;
    wire [31:0] usb_write_data, usb_read_data;
    wire [3:0] usb_mask;
    VexRiscv cpu (
        .clk(clk_usb), .reset(!reset_n),
        .iBus_cmd_valid(instruction_valid), .iBus_cmd_ready(instruction_ready), .iBus_cmd_payload_pc(instruction_address),
        .iBus_rsp_valid(instruction_response), .iBus_rsp_payload_error(instruction_error), .iBus_rsp_payload_inst(instruction_data),
        .timerInterrupt(1'b0), .externalInterrupt(1'b0), .softwareInterrupt(1'b0),
        .dBus_cmd_valid(data_valid), .dBus_cmd_ready(data_ready), .dBus_cmd_payload_wr(data_write),
        .dBus_cmd_payload_address(data_address), .dBus_cmd_payload_data(data_write_data),
        .dBus_cmd_payload_mask(data_mask), .dBus_cmd_payload_size(),
        .dBus_rsp_ready(data_response), .dBus_rsp_error(1'b0), .dBus_rsp_data(data_read_data)
    );
    workstation_usb2_cpu_bus #(.ROM_FILE(ROM_FILE)) bus (
        .clk_cpu(clk_usb), .reset_n(reset_n),
        .instruction_valid_i(instruction_valid), .instruction_ready_o(instruction_ready), .instruction_address_i(instruction_address),
        .instruction_response_o(instruction_response), .instruction_error_o(instruction_error), .instruction_data_o(instruction_data),
        .data_valid_i(data_valid), .data_ready_o(data_ready), .data_write_i(data_write), .data_address_i(data_address),
        .data_write_data_i(data_write_data), .data_mask_i(data_mask), .data_response_o(data_response), .data_read_data_o(data_read_data),
        .uart_rx_i(uart_rx_i), .uart_tx_o(uart_tx_o),
        .usb_cs_o(usb_cs), .usb_write_o(usb_write), .usb_address_o(usb_address), .usb_write_data_o(usb_write_data), .usb_mask_o(usb_mask),
        .usb_ack_i(usb_ack), .usb_error_i(1'b0), .usb_read_data_i(usb_read_data),
        .service_valid_o(service_valid_o), .service_write_o(service_write_o), .service_address_o(service_address_o),
        .service_write_data_o(service_write_data_o), .service_mask_o(service_mask_o),
        .service_ready_i(service_ready_i), .service_error_i(service_error_i), .service_read_data_i(service_read_data_i),
        .fault_o(fault_o), .fault_address_o(fault_address_o)
    );
    wire [7:0] rx_data, tx_data;
    wire rx_valid, rx_active, rx_error, tx_valid, tx_ready;
    wire [1:0] op_mode, xcvr_select;
    wire term_select, dp_pulldown, dm_pulldown;
    reg [15:0] se0_count_q;
    always @(posedge clk_usb or negedge reset_n)
        if (!reset_n) begin se0_count_q <= 0; session_valid_o <= 0; end
        else begin
            if (line_state_o != 0) se0_count_q <= 0;
            else if (se0_count_q < 48000) se0_count_q <= se0_count_q + 1'b1;
            if (se0_count_q >= 48000) session_valid_o <= 0;
            else if (line_state_o == 2'b01) session_valid_o <= 1;
        end
    usbh_core mac (
        .clk_i(clk_usb), .rstn_i(reset_n), .reg_cs(usb_cs), .reg_wr(usb_write),
        .reg_addr(usb_address[5:0]), .reg_wdata(usb_write_data), .reg_be(usb_mask), .reg_rdata(usb_read_data), .reg_ack(usb_ack),
        .utmi_data_in_i(rx_data), .utmi_txready_i(tx_ready), .utmi_rxvalid_i(rx_valid),
        .utmi_rxactive_i(rx_active), .utmi_rxerror_i(rx_error), .utmi_linestate_i(line_state_o),
        .intr_o(), .utmi_data_out_o(tx_data), .utmi_txvalid_o(tx_valid),
        .utmi_op_mode_o(op_mode), .utmi_xcvrselect_o(xcvr_select), .utmi_termselect_o(term_select),
        .utmi_dppulldown_o(dp_pulldown), .utmi_dmpulldown_o(dm_pulldown)
    );
    workstation_usb1_phy phy (
        .clk_usb(clk_usb), .reset_n(reset_n), .usb_dp(usb_dp), .usb_dm(usb_dm),
        .tx_data_i(tx_data), .tx_valid_i(tx_valid), .tx_ready_o(tx_ready),
        .rx_data_o(rx_data), .rx_valid_o(rx_valid), .rx_active_o(rx_active), .rx_error_o(rx_error),
        .line_state_o(line_state_o), .op_mode_i(op_mode), .xcvr_select_i(xcvr_select),
        .term_select_i(term_select), .dp_pulldown_i(dp_pulldown), .dm_pulldown_i(dm_pulldown)
    );
endmodule
