module workstation_usb2_soc #(
    parameter ROM_FILE = "usb2_cpu.hex",
    parameter integer CPU_FREQUENCY_HZ = 48000000,
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer BUS_TIMEOUT_CYCLES = 480000
)(
    input wire clk_cpu,
    input wire clk_ref,
    input wire clk_ulpi,
    input wire reset_n,
    input wire uart_rx_i,
    output wire uart_tx_o,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i,
    input wire ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o,
    output wire ulpi_stp_o,
    output wire service_valid_o,
    output wire service_write_o,
    output wire [7:0] service_address_o,
    output wire [31:0] service_write_data_o,
    output wire [3:0] service_mask_o,
    input wire service_ready_i,
    input wire service_error_i,
    input wire [31:0] service_read_data_i,
    output wire [3:0] cpu_fault_o,
    output wire [31:0] cpu_fault_address_o,
    output wire transaction_reset_n_o,
    output wire phy_ready_o,
    output wire failed_o,
    output wire high_speed_o,
    output wire traffic_enable_o,
    output wire [31:0] sof_count_o
);
    (* async_reg = "true" *) reg [1:0] cpu_release_q;
    wire cpu_reset_n = cpu_release_q[1];
    wire instruction_valid, instruction_ready, instruction_response, instruction_error;
    wire [31:0] instruction_address, instruction_data;
    wire data_valid, data_ready, data_write, data_response;
    wire [31:0] data_address, data_write_data, data_read_data;
    wire [3:0] data_mask;
    wire [1:0] unused_data_size;
    wire usb_cs, usb_write, usb_ack, usb_error, unused_usb_irq;
    wire [7:0] usb_address;
    wire [31:0] usb_write_data, usb_read_data;
    wire [3:0] usb_mask;
    always @(posedge clk_cpu or negedge reset_n)
        if (!reset_n) cpu_release_q <= 0;
        else cpu_release_q <= {cpu_release_q[0], 1'b1};

    VexRiscv cpu (
        .clk(clk_cpu), .reset(!cpu_reset_n),
        .iBus_cmd_valid(instruction_valid), .iBus_cmd_ready(instruction_ready), .iBus_cmd_payload_pc(instruction_address),
        .iBus_rsp_valid(instruction_response), .iBus_rsp_payload_error(instruction_error), .iBus_rsp_payload_inst(instruction_data),
        .timerInterrupt(1'b0), .externalInterrupt(1'b0), .softwareInterrupt(1'b0),
        .dBus_cmd_valid(data_valid), .dBus_cmd_ready(data_ready), .dBus_cmd_payload_wr(data_write),
        .dBus_cmd_payload_address(data_address), .dBus_cmd_payload_data(data_write_data),
        .dBus_cmd_payload_mask(data_mask), .dBus_cmd_payload_size(unused_data_size),
        .dBus_rsp_ready(data_response), .dBus_rsp_error(1'b0), .dBus_rsp_data(data_read_data)
    );
    workstation_usb2_cpu_bus #(.ROM_FILE(ROM_FILE), .CPU_FREQUENCY_HZ(CPU_FREQUENCY_HZ), .BUS_TIMEOUT_CYCLES(BUS_TIMEOUT_CYCLES)) bus (
        .clk_cpu(clk_cpu), .reset_n(cpu_reset_n),
        .instruction_valid_i(instruction_valid), .instruction_ready_o(instruction_ready), .instruction_address_i(instruction_address),
        .instruction_response_o(instruction_response), .instruction_error_o(instruction_error), .instruction_data_o(instruction_data),
        .data_valid_i(data_valid), .data_ready_o(data_ready), .data_write_i(data_write), .data_address_i(data_address),
        .data_write_data_i(data_write_data), .data_mask_i(data_mask), .data_response_o(data_response), .data_read_data_o(data_read_data),
        .uart_rx_i(uart_rx_i), .uart_tx_o(uart_tx_o),
        .usb_cs_o(usb_cs), .usb_write_o(usb_write), .usb_address_o(usb_address), .usb_write_data_o(usb_write_data), .usb_mask_o(usb_mask),
        .usb_ack_i(usb_ack), .usb_error_i(usb_error), .usb_read_data_i(usb_read_data),
        .service_valid_o(service_valid_o), .service_write_o(service_write_o), .service_address_o(service_address_o),
        .service_write_data_o(service_write_data_o), .service_mask_o(service_mask_o),
        .service_ready_i(service_ready_i), .service_error_i(service_error_i), .service_read_data_i(service_read_data_i),
        .fault_o(cpu_fault_o), .fault_address_o(cpu_fault_address_o)
    );
    workstation_usb2_host_mmio #(.ATTACH_DEBOUNCE_US(ATTACH_DEBOUNCE_US)) usb (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n),
        .reg_cs_i(usb_cs), .reg_wr_i(usb_write), .reg_addr_i(usb_address), .reg_wdata_i(usb_write_data), .reg_be_i(usb_mask),
        .reg_ack_o(usb_ack), .reg_error_o(usb_error), .reg_rdata_o(usb_read_data), .irq_o(unused_usb_irq),
        .ulpi_data_i(ulpi_data_i), .ulpi_dir_i(ulpi_dir_i), .ulpi_nxt_i(ulpi_nxt_i),
        .ulpi_data_o(ulpi_data_o), .ulpi_data_oe_o(ulpi_data_oe_o), .ulpi_stp_o(ulpi_stp_o),
        .transaction_reset_n_o(transaction_reset_n_o), .phy_ready_o(phy_ready_o), .failed_o(failed_o),
        .high_speed_o(high_speed_o), .traffic_enable_o(traffic_enable_o), .sof_count_o(sof_count_o)
    );
endmodule
