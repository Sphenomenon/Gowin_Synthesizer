module workstation_usb2_cpu_bus #(
    parameter ROM_FILE = "",
    parameter integer CPU_FREQUENCY_HZ = 48000000,
    parameter integer BUS_TIMEOUT_CYCLES = 480000
)(
    input wire clk_cpu,
    input wire reset_n,
    input wire instruction_valid_i,
    output wire instruction_ready_o,
    input wire [31:0] instruction_address_i,
    output reg instruction_response_o,
    output reg instruction_error_o,
    output wire [31:0] instruction_data_o,
    input wire data_valid_i,
    output wire data_ready_o,
    input wire data_write_i,
    input wire [31:0] data_address_i,
    input wire [31:0] data_write_data_i,
    input wire [3:0] data_mask_i,
    output reg data_response_o,
    output wire [31:0] data_read_data_o,
    input wire uart_rx_i,
    output wire uart_tx_o,
    output wire usb_cs_o,
    output wire usb_write_o,
    output wire [7:0] usb_address_o,
    output wire [31:0] usb_write_data_o,
    output wire [3:0] usb_mask_o,
    input wire usb_ack_i,
    input wire usb_error_i,
    input wire [31:0] usb_read_data_i,
    output wire service_valid_o,
    output wire service_write_o,
    output wire [7:0] service_address_o,
    output wire [31:0] service_write_data_o,
    output wire [3:0] service_mask_o,
    input wire service_ready_i,
    input wire service_error_i,
    input wire [31:0] service_read_data_i,
    output reg [3:0] fault_o,
    output reg [31:0] fault_address_o
);
    localparam [2:0] IDLE = 0, USB = 1, USB_RELEASE = 2, SERVICE = 3, UART = 4;
    localparam integer TIMER_WIDTH = BUS_TIMEOUT_CYCLES < 2 ? 1 : $clog2(BUS_TIMEOUT_CYCLES);
    localparam integer MILLISECOND_CYCLES = CPU_FREQUENCY_HZ / 1000;
    localparam integer DIVIDER_WIDTH = MILLISECOND_CYCLES < 2 ? 1 : $clog2(MILLISECOND_CYCLES);
    reg [31:0] memory [0:16383];
    reg [31:0] memory_read_q, peripheral_read_q;
    reg memory_response_q, bootstrap_response_q;
    reg [2:0] state_q;
    reg [31:0] address_q, write_data_q;
    reg write_q;
    reg [3:0] mask_q;
    reg [TIMER_WIDTH-1:0] elapsed_q;
    reg [DIVIDER_WIDTH-1:0] millisecond_divider_q;
    reg [31:0] milliseconds_q, cycles_q;
    wire data_accept = data_valid_i && data_ready_o;
    wire data_memory = data_address_i[31:16] == 0;
    wire data_usb = data_address_i[31:8] == 24'h020001;
    wire data_service = data_address_i[31:8] == 24'h020002;
    wire data_uart = data_address_i == 32'h02000014;
    wire data_local = data_address_i == 32'h02000010 || data_address_i == 32'h02000050 ||
                      data_address_i == 32'h02000054 || data_address_i == 32'h02000058 ||
                      data_address_i == 32'h0200005c || data_address_i == 32'h02000060;
    wire data_memory_accept = data_accept && data_memory;
    wire instruction_accept = instruction_valid_i && instruction_ready_o;
    wire instruction_bootstrap = instruction_address_i[31:6] == 26'h2000000;
    wire bad_instruction = instruction_accept && instruction_address_i[31:16] != 0 && !instruction_bootstrap;
    wire invalid_local_write = data_local && data_write_i && data_address_i != 32'h02000010 && data_address_i != 32'h02000058;
    wire invalid_data = data_accept && ((!data_memory && !data_usb && !data_service && !data_uart && !data_local) || invalid_local_write);
    wire [13:0] memory_address = data_memory_accept ? data_address_i[15:2] : instruction_address_i[15:2];
    wire [31:0] uart_divider, uart_data;
    wire uart_wait;
    wire target_done = state_q == USB ? usb_ack_i : state_q == SERVICE ? service_ready_i : state_q == UART && !uart_wait;
    wire target_error = target_done && ((state_q == USB && usb_error_i) || (state_q == SERVICE && service_error_i));
    wire bus_timeout = (state_q == USB || state_q == SERVICE || state_q == UART) && !target_done &&
                       elapsed_q == TIMER_WIDTH'(BUS_TIMEOUT_CYCLES - 1);
    wire [3:0] new_faults = {bad_instruction, bus_timeout, target_error, invalid_data};
    wire clear_fault = data_accept && data_write_i && data_address_i == 32'h02000058 && data_mask_i[0];
    wire [3:0] fault_clear_mask = clear_fault ? data_write_data_i[3:0] : 4'd0;

    initial if (ROM_FILE != "") $readmemh(ROM_FILE, memory);
    assign data_ready_o = reset_n && state_q == IDLE;
    assign instruction_ready_o = reset_n && !data_memory_accept;
    assign instruction_data_o = bootstrap_response_q ? 32'h00000067 : memory_read_q;
    assign data_read_data_o = memory_response_q ? memory_read_q : peripheral_read_q;
    assign usb_cs_o = reset_n && state_q == USB;
    assign usb_write_o = write_q;
    assign usb_address_o = address_q[7:0];
    assign usb_write_data_o = write_data_q;
    assign usb_mask_o = mask_q;
    assign service_valid_o = reset_n && state_q == SERVICE;
    assign service_write_o = write_q;
    assign service_address_o = address_q[7:0];
    assign service_write_data_o = write_data_q;
    assign service_mask_o = mask_q;

    always @(posedge clk_cpu) begin
        memory_read_q <= memory[memory_address];
        if (data_memory_accept && data_write_i) begin
            if (data_mask_i[0]) memory[data_address_i[15:2]][7:0] <= data_write_data_i[7:0];
            if (data_mask_i[1]) memory[data_address_i[15:2]][15:8] <= data_write_data_i[15:8];
            if (data_mask_i[2]) memory[data_address_i[15:2]][23:16] <= data_write_data_i[23:16];
            if (data_mask_i[3]) memory[data_address_i[15:2]][31:24] <= data_write_data_i[31:24];
        end
    end

    simpleuart #(.DEFAULT_DIV(CPU_FREQUENCY_HZ / 115200)) uart (
        .clk(clk_cpu), .resetn(reset_n), .ser_rx(uart_rx_i), .ser_tx(uart_tx_o),
        .reg_div_we(data_accept && data_write_i && data_address_i == 32'h02000010 ? data_mask_i : 4'd0),
        .reg_div_di(data_write_data_i), .reg_div_do(uart_divider),
        .reg_dat_we(state_q == UART && write_q && mask_q[0]), .reg_dat_re(state_q == UART && !write_q),
        .reg_dat_di(write_data_q), .reg_dat_do(uart_data), .reg_dat_wait(uart_wait)
    );

    always @(posedge clk_cpu or negedge reset_n) begin
        if (!reset_n) begin
            millisecond_divider_q <= 0; milliseconds_q <= 0; cycles_q <= 0;
            fault_o <= 0; fault_address_o <= 0;
        end else begin
            cycles_q <= cycles_q + 1'b1;
            if (millisecond_divider_q == DIVIDER_WIDTH'(MILLISECOND_CYCLES - 1)) begin
                millisecond_divider_q <= 0; milliseconds_q <= milliseconds_q + 1'b1;
            end else millisecond_divider_q <= millisecond_divider_q + 1'b1;
            fault_o <= (fault_o & ~fault_clear_mask) | new_faults;
            if (|new_faults) fault_address_o <= bad_instruction ? instruction_address_i : invalid_data ? data_address_i : address_q;
        end
    end

    always @(posedge clk_cpu or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= IDLE; address_q <= 0; write_data_q <= 0; write_q <= 0; mask_q <= 0; elapsed_q <= 0;
            instruction_response_o <= 0; instruction_error_o <= 0; bootstrap_response_q <= 0;
            data_response_o <= 0; memory_response_q <= 0; peripheral_read_q <= 0;
        end else begin
            instruction_response_o <= instruction_accept; instruction_error_o <= bad_instruction;
            bootstrap_response_q <= instruction_accept && instruction_bootstrap;
            data_response_o <= 0; memory_response_q <= 0;
            if (state_q == IDLE || state_q == USB_RELEASE) elapsed_q <= 0;
            else elapsed_q <= elapsed_q + 1'b1;
            if (data_accept) begin
                address_q <= data_address_i; write_data_q <= data_write_data_i; write_q <= data_write_i; mask_q <= data_mask_i;
                if (data_usb) state_q <= USB;
                else if (data_service) state_q <= SERVICE;
                else if (data_uart) state_q <= UART;
                else if (!data_write_i) begin
                    data_response_o <= 1; memory_response_q <= data_memory; peripheral_read_q <= 0;
                    case (data_address_i)
                        32'h02000010: peripheral_read_q <= uart_divider;
                        32'h02000050: peripheral_read_q <= milliseconds_q;
                        32'h02000054: peripheral_read_q <= cycles_q;
                        32'h02000058: peripheral_read_q <= {28'd0, fault_o};
                        32'h0200005c: peripheral_read_q <= fault_address_o;
                        32'h02000060: peripheral_read_q <= 32'h55324301;
                        default: begin end
                    endcase
                end
            end
            if (target_done || bus_timeout) begin
                if (!write_q) begin
                    data_response_o <= 1;
                    peripheral_read_q <= target_error || bus_timeout ? 32'd0 :
                                         state_q == USB ? usb_read_data_i : state_q == UART ? uart_data : service_read_data_i;
                end
                state_q <= state_q == USB ? USB_RELEASE : IDLE;
            end else if (state_q == USB_RELEASE) state_q <= IDLE;
        end
    end
endmodule
