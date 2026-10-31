// Actual native owner and MMIO, with the synchronous H5 RAM ABI at its outer
// physical packet boundary. The independent UART bench covers the real H5.
module workstation_hci_native_cosim (
    input wire clk_i,reset_ni,observer_reset_ni,
    input wire command_valid_i,command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    output wire command_ready_o,response_error_o,
    output wire [31:0] response_data_o,
    input wire rx_write_i,
    input wire [8:0] rx_write_address_i,
    input wire [7:0] rx_write_data_i,
    input wire rx_valid_i,
    input wire [3:0] rx_type_i,
    input wire [8:0] rx_length_i,
    output wire rx_consume_o,
    input wire hold_transport_i,
    output reg packet_copied_o,
    output reg [3:0] packet_type_o,
    output reg [8:0] packet_length_o,
    input wire [8:0] packet_address_i,
    output wire [7:0] packet_data_o,
    output wire ready_o,fault_o,fenced_o,classic_ready_o,
    output wire [31:0] epoch_o,generation_o,
    output wire [15:0] br_available_o,le_available_o,host_budget_o
);
    wire tx_start,tx_ready;
    wire [3:0] tx_type;
    wire [8:0] tx_length,rx_address;
    reg [8:0] tx_address;
    wire [7:0] tx_data;
    reg [7:0] rx_data;
    reg [7:0] incoming [0:279],outgoing [0:279];
    reg pending,copying,wait_read,transport_done;
    assign tx_ready=!pending;
    assign packet_data_o=outgoing[packet_address_i];
    assign br_available_o=owner.br_available,le_available_o=owner.le_available,host_budget_o=owner.host_budget;
    always @(posedge clk_i)begin
        if(rx_write_i)incoming[rx_write_address_i]<=rx_write_data_i;
        rx_data<=incoming[rx_address];
        packet_copied_o<=0;transport_done<=0;
        if(!reset_ni)begin
            pending<=0;copying<=0;wait_read<=1;tx_address<=0;packet_type_o<=0;packet_length_o<=0;
        end else begin
            if(tx_start)begin
                pending<=1;copying<=1;wait_read<=1;tx_address<=0;packet_type_o<=tx_type;packet_length_o<=tx_length;
            end
            if(copying)begin
                if(wait_read)wait_read<=0;
                else begin
                    outgoing[tx_address]<=tx_data;wait_read<=1;
                    if(tx_address+1'b1==packet_length_o)begin copying<=0;packet_copied_o<=1;end
                    else tx_address<=tx_address+1'b1;
                end
            end else if(pending && !hold_transport_i)begin pending<=0;transport_done<=1;end
        end
    end
    workstation_hci_native_transport #(.CLK_HZ(1000),.BOOTSTRAP_TIMEOUT_CYCLES(10000),.COMMAND_TIMEOUT_CYCLES(20000)) owner (
        .clk_i(clk_i),.reset_ni(reset_ni),.enable_i(1'b1),.observer_reset_ni(observer_reset_ni),
        .link_up_i(1'b1),.physical_fault_i(1'b0),.boot_id_i(64'h8877665544332211),
        .initializer_handoff_i(1'b1),.initialized_i(ready_o),.host_flow_ready_o(ready_o),
        .controller_epoch_o(epoch_o),.classic_generation_o(generation_o),.classic_active_o(),.classic_ready_o(classic_ready_o),
        .fault_o(fault_o),.classic_fenced_o(fenced_o),.ble_acl_limit_o(),
        .init_tx_start_i(1'b0),.init_tx_type_i(4'd1),.init_tx_length_i(9'd3),.init_tx_address_o(),
        .init_tx_data_i(8'd0),.init_tx_ready_o(),.init_tx_done_o(),.init_tx_error_o(),
        .init_rx_valid_o(),.init_rx_type_o(),.init_rx_length_o(),.init_rx_address_i(9'd0),.init_rx_data_o(),.init_rx_consume_i(1'b0),
        .ble_tx_start_i(1'b0),.ble_tx_type_i(4'd1),.ble_tx_length_i(9'd0),.ble_tx_address_o(),.ble_tx_data_i(8'd0),
        .ble_tx_ready_o(),.ble_tx_done_o(),.ble_tx_error_o(),.ble_rx_valid_o(),.ble_rx_type_o(),.ble_rx_length_o(),
        .ble_rx_address_i(9'd0),.ble_rx_data_o(),.ble_rx_consume_i(1'b1),
        .h5_tx_start_o(tx_start),.h5_tx_type_o(tx_type),.h5_tx_length_o(tx_length),.h5_tx_address_i(tx_address),
        .h5_tx_data_o(tx_data),.h5_tx_ready_i(tx_ready),.h5_tx_done_i(transport_done),.h5_tx_error_i(1'b0),
        .h5_rx_valid_i(rx_valid_i),.h5_rx_type_i(rx_type_i),.h5_rx_length_i(rx_length_i),
        .h5_rx_address_o(rx_address),.h5_rx_data_i(rx_data),.h5_rx_consume_o(rx_consume_o),
        .command_valid_i(command_valid_i),.command_write_i(command_write_i),.command_address_i(command_address_i),
        .command_data_i(command_data_i),.command_strobes_i(4'hf),.command_ready_o(command_ready_o),
        .response_error_o(response_error_o),.response_data_o(response_data_o)
    );
endmodule
