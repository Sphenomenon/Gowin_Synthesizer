// Real RTL8723DS UART8E1 / H5 / ROM-v2 / BLE MIDI peripheral host.
// Reset is synchronous active-high. UART names follow module viewpoint.
module midi_ble_link #(
    parameter CLK_HZ=50000000,
    parameter BAUD=115200,
    parameter DISABLE_MS=200,
    parameter STARTUP_MS=2000,
    parameter PATCH_FILE="rtl/ble_board/rtl8723ds_patch.mem"
)(
    input wire clk,reset,input wire module_uart_tx,
    output wire module_uart_rx,module_bt_dis_n,
    input wire value_tx_valid,output wire value_tx_ready,
    input wire [39:0] value_tx_data,input wire [2:0] value_tx_length,
    output wire value_rx_valid,input wire value_rx_ready,
    output wire [39:0] value_rx_data,output wire [2:0] value_rx_length,
    output wire online,initialized,output reg failed
);
    localparam MS_CYCLES=CLK_HZ/1000;
    reg [31:0] ms_divider,uptime_ms;
    wire resetn=!reset;
    wire start_ready=uptime_ms>=DISABLE_MS+STARTUP_MS && !failed;
    assign module_bt_dis_n=!reset && uptime_ms>=DISABLE_MS && !failed;
    wire link_up,tx_ready,tx_done,tx_error,rx_valid;
    wire [3:0] rx_type,init_tx_type,app_tx_type;
    wire [8:0] rx_length,tx_addr,rx_addr,init_rx_addr,app_rx_addr,init_tx_length,app_tx_length;
    wire [7:0] rx_data,tx_data,init_tx_data,app_tx_data;
    wire init_tx_start,app_tx_start,init_rx_consume,app_rx_consume,init_failed,app_failed;
    wire connected,subscribed;
    wire [47:0] local_address;
    assign online=connected && subscribed && initialized && !failed && !reset;
    assign tx_data=initialized?app_tx_data:init_tx_data;
    assign rx_addr=initialized?app_rx_addr:init_rx_addr;
    always @(posedge clk) begin
        if(reset) begin ms_divider<=0;uptime_ms<=0;failed<=0;end
        else begin
            if(ms_divider==MS_CYCLES-1) begin ms_divider<=0;
                if(uptime_ms<DISABLE_MS+STARTUP_MS+5000) uptime_ms<=uptime_ms+1'b1;
            end else ms_divider<=ms_divider+1'b1;
            if(init_failed || app_failed || (tx_error && initialized) ||
                (!link_up && !initialized && uptime_ms>=DISABLE_MS+STARTUP_MS+5000)) failed<=1;
        end
    end
    midi_ble_h5 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) transport(
        .clk(clk),.resetn(resetn),.enable(start_ready),.uart_rx(module_uart_tx),.uart_tx(module_uart_rx),
        .tx_start(initialized?app_tx_start:init_tx_start),.tx_type(initialized?app_tx_type:init_tx_type),
        .tx_length(initialized?app_tx_length:init_tx_length),.tx_payload_addr(tx_addr),.tx_payload_data(tx_data),
        .tx_ready(tx_ready),.tx_done(tx_done),.tx_error(tx_error),.rx_valid(rx_valid),.rx_type(rx_type),
        .rx_length(rx_length),.rx_payload_addr(rx_addr),.rx_payload_data(rx_data),
        .rx_consume(initialized?app_rx_consume:init_rx_consume),.link_up(link_up),
        .debug_state(),.rx_frames(),.tx_frames(),.retries(),.uart_errors(),.protocol_errors());
    midi_ble_hci_init #(.CLK_HZ(CLK_HZ),.PATCH_BYTES(30147),.PATCH_FILE(PATCH_FILE)) initializer(
        .clk(clk),.resetn(resetn),.enable(start_ready),.link_up(link_up),
        .tx_start(init_tx_start),.tx_type(init_tx_type),.tx_length(init_tx_length),
        .tx_ready(tx_ready&&!initialized),.tx_done(tx_done),.tx_error(tx_error),
        .tx_payload_addr(tx_addr),.tx_payload_data(init_tx_data),.rx_valid(rx_valid&&!initialized),
        .rx_type(rx_type),.rx_length(rx_length),.rx_payload_addr(init_rx_addr),.rx_payload_data(rx_data),
        .rx_consume(init_rx_consume),.initialized(initialized),.failed(init_failed),
        .debug_state(),.error_code(),.last_opcode(),.last_status(),.rom_version(),
        .command_count(),.patch_fragments(),.hci_valid_mask(),.bd_addr(local_address));
    midi_ble_gatt #(.CLK_HZ(CLK_HZ)) application(
        .clk(clk),.resetn(resetn),.enable(initialized&&!failed),.local_address(local_address),
        .rx_valid(rx_valid&&initialized),.rx_type(rx_type),.rx_length(rx_length),
        .rx_payload_addr(app_rx_addr),.rx_payload_data(rx_data),.rx_consume(app_rx_consume),
        .tx_start(app_tx_start),.tx_type(app_tx_type),.tx_length(app_tx_length),
        .tx_ready(tx_ready&&initialized),.tx_done(tx_done),.tx_error(tx_error),
        .tx_payload_addr(tx_addr),.tx_payload_data(app_tx_data),
        .value_tx_valid(value_tx_valid),.value_tx_ready(value_tx_ready),
        .value_tx_data(value_tx_data),.value_tx_length(value_tx_length),
        .value_rx_valid(value_rx_valid),.value_rx_ready(value_rx_ready),
        .value_rx_data(value_rx_data),.value_rx_length(value_rx_length),
        .connected(connected),.subscribed(subscribed),.failed(app_failed));
endmodule
