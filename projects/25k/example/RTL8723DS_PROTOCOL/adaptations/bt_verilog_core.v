// Business test adaptation; vendor remains frozen.
module bt_verilog_core #(
    parameter [87:0] DEVICE_NAME="GW25K-PROTO",
    parameter EXTERNAL_PCM=0, parameter CAPACITY_FRAMES=48000,
    parameter CLK_HZ=50000000,
    parameter AUDIO_FILE="audio/test_tone.mem",
    parameter BAUD=115200,
    parameter FAST_BAUD=921600,
    parameter DISABLE_MS=200,
    parameter STARTUP_MS=2000,
    parameter SESSION_MS=0,
    parameter PATCH_BYTES=30147,
    parameter PATCH_FILE="rtl8723ds_patch.mem",
    parameter NOTIFY_MS=500
) (
    input wire clk, resetn, enable, uart_rx,
    input wire pcm_valid_i, source_ready_i, source_fault_i,
    input wire [31:0] pcm_pair_i,
    output wire uart_tx, bt_enable, outputs_active,
    output wire initialized, connected, subscribed,
    output reg failed,
    output wire [767:0] debug
);
    localparam MS_TICKS=CLK_HZ/1000;
    reg [31:0] ms_div, uptime_ms;
    reg [7:0] core_error;
    wire init_failed;
    wire fast_mode, baud_idle;
    wire link_up, tx_ready, tx_done, tx_error, rx_valid;
    wire sub_resetn = resetn && enable;
    wire start_ready = enable && uptime_ms >= DISABLE_MS+STARTUP_MS;
    wire session_ended = (SESSION_MS != 0) && uptime_ms >= SESSION_MS;
    assign outputs_active = enable && !failed && !session_ended;
    assign bt_enable = uptime_ms >= DISABLE_MS && outputs_active;
    always @(posedge clk) begin
        if(!resetn || !enable) begin ms_div<=0; uptime_ms<=0; failed<=0; core_error<=0; end
        else begin
            // Saturate so a long-lived session cannot repeat startup after wrap.
            if(ms_div==MS_TICKS-1) begin ms_div<=0; if(!session_ended && uptime_ms != 32'hffffffff) uptime_ms<=uptime_ms+1; end
            else ms_div<=ms_div+1;
            if(init_failed) failed<=1;
            if(!link_up && uptime_ms >= DISABLE_MS+STARTUP_MS+5000 && !initialized) begin
                failed<=1; core_error<=8;
            end
            if(tx_error && initialized) begin failed<=1; core_error<=9; end
        end
    end
    wire [3:0] rx_type;
    wire [8:0] rx_length, rx_addr, tx_addr;
    wire [7:0] rx_data, tx_data, h5_state;
    wire [31:0] rx_frames,tx_frames,retries,uart_errors,protocol_errors;
    wire init_tx_start,init_rx_consume;
    wire [3:0] init_tx_type;
    wire [8:0] init_tx_length, init_rx_addr;
    wire [7:0] init_tx_data,init_state,init_error,last_status,rom_version;
    wire [15:0] last_opcode;
    wire [31:0] command_count,patch_fragments;
    wire [2:0] hci_valid_mask;
    wire [7:0] acl_packet_count;
    wire [47:0] bd_addr;
    wire [63:0] boot_id;
    wire app_tx_start,app_rx_consume;
    wire [3:0] app_tx_type;
    wire [8:0] app_tx_length,app_rx_addr;
    wire [7:0] app_tx_data,app_state;
    wire [11:0] handle;
    wire [31:0] notification_count,acl_rx_count,att_request_count,completed_packets,app_errors,app_elapsed;
    wire bridge_tx_start,bridge_rx_consume;
    wire [3:0] bridge_tx_type,app_rx_type;
    wire [8:0] bridge_tx_length,bridge_rx_addr,app_payload_addr,app_rx_length;
    wire [7:0] bridge_tx_data,app_rx_data;
    wire app_tx_ready,app_tx_done,app_tx_error,app_rx_valid;
    bt_acl_bridge #(.CLK_HZ(CLK_HZ)) acl_bridge (
        .clk(clk),.resetn(sub_resetn),.enable(initialized && outputs_active),
        .connected(connected),.connection_handle(handle),.acl_packet_count(acl_packet_count),
        .app_tx_start(app_tx_start),.app_tx_type(app_tx_type),.app_tx_length(app_tx_length),
        .app_tx_addr(app_payload_addr),.app_tx_data(app_tx_data),.app_tx_ready(app_tx_ready),
        .app_tx_done(app_tx_done),.app_tx_error(app_tx_error),
        .app_rx_valid(app_rx_valid),.app_rx_type(app_rx_type),.app_rx_length(app_rx_length),
        .app_rx_addr(app_rx_addr),.app_rx_data(app_rx_data),.app_rx_consume(app_rx_consume),
        .h5_tx_start(bridge_tx_start),.h5_tx_type(bridge_tx_type),.h5_tx_length(bridge_tx_length),
        .h5_tx_addr(tx_addr),.h5_tx_data(bridge_tx_data),.h5_tx_ready(tx_ready),.h5_tx_done(tx_done),.h5_tx_error(tx_error),
        .h5_rx_valid(rx_valid),.h5_rx_type(rx_type),.h5_rx_length(rx_length),
        .h5_rx_addr(bridge_rx_addr),.h5_rx_data(rx_data),.h5_rx_consume(bridge_rx_consume)
    );
    assign tx_data = initialized ? bridge_tx_data : init_tx_data;
    assign rx_addr = initialized ? bridge_rx_addr : init_rx_addr;
    bt_h5_transport #(.CLK_HZ(CLK_HZ),.BAUD(BAUD),.FAST_BAUD(FAST_BAUD)) transport (
        .clk(clk),.resetn(sub_resetn),.enable(start_ready),.uart_rx(uart_rx),.uart_tx(uart_tx),
        .fast_mode(fast_mode),.baud_idle(baud_idle),
        .tx_start((initialized ? bridge_tx_start : init_tx_start) && outputs_active),
        .tx_type(initialized ? bridge_tx_type : init_tx_type),
        .tx_length(initialized ? bridge_tx_length : init_tx_length),
        .tx_payload_addr(tx_addr),.tx_payload_data(tx_data),.tx_ready(tx_ready),
        .tx_done(tx_done),.tx_error(tx_error),.rx_valid(rx_valid),.rx_type(rx_type),
        .rx_length(rx_length),.rx_payload_addr(rx_addr),.rx_payload_data(rx_data),
        .rx_consume(initialized ? bridge_rx_consume : init_rx_consume),.link_up(link_up),
        .debug_state(h5_state),.rx_frames(rx_frames),.tx_frames(tx_frames),.retries(retries),
        .uart_errors(uart_errors),.protocol_errors(protocol_errors)
    );
    bt_hci_init #(.CLK_HZ(CLK_HZ),.PATCH_BYTES(PATCH_BYTES),.PATCH_FILE(PATCH_FILE),.BAUD(BAUD),.FAST_BAUD(FAST_BAUD),.DEVICE_NAME(DEVICE_NAME)) initializer (
        .clk(clk),.resetn(sub_resetn),.enable(start_ready),.link_up(link_up),
        .fast_mode(fast_mode),.baud_idle(baud_idle),
        .tx_start(init_tx_start),.tx_type(init_tx_type),.tx_length(init_tx_length),
        .tx_ready(tx_ready && outputs_active && !initialized),.tx_done(tx_done),.tx_error(tx_error),
        .tx_payload_addr(tx_addr),.tx_payload_data(init_tx_data),.rx_valid(rx_valid && !initialized),
        .rx_type(rx_type),.rx_length(rx_length),.rx_payload_addr(init_rx_addr),
        .rx_payload_data(rx_data),.rx_consume(init_rx_consume),.initialized(initialized),
        .failed(init_failed),.debug_state(init_state),.error_code(init_error),
        .last_opcode(last_opcode),.last_status(last_status),.rom_version(rom_version),
        .command_count(command_count),.patch_fragments(patch_fragments),
        .hci_valid_mask(hci_valid_mask),.bd_addr(bd_addr),.boot_id(boot_id),.acl_packet_count(acl_packet_count)
    );
    bt_gatt #(.CLK_HZ(CLK_HZ),.AUDIO_FILE(AUDIO_FILE),.NOTIFY_MS(NOTIFY_MS),.EXTERNAL_PCM(EXTERNAL_PCM),.CAPACITY_FRAMES(CAPACITY_FRAMES),.DEVICE_NAME(DEVICE_NAME)) application (
        .clk(clk),.resetn(sub_resetn),.enable(enable && initialized && outputs_active),
        .pcm_valid_i(pcm_valid_i),.pcm_pair_i(pcm_pair_i),.source_ready_i(source_ready_i),.source_fault_i(source_fault_i),
        .boot_id(boot_id),.acl_packet_count(acl_packet_count),
        .rx_valid(app_rx_valid),.rx_type(app_rx_type),.rx_length(app_rx_length),
        .rx_payload_addr(app_rx_addr),.rx_payload_data(app_rx_data),.rx_consume(app_rx_consume),
        .tx_start(app_tx_start),.tx_type(app_tx_type),.tx_length(app_tx_length),
        .tx_ready(app_tx_ready),.tx_done(app_tx_done),.tx_error(app_tx_error),
        .tx_payload_addr(app_payload_addr),.tx_payload_data(app_tx_data),.connected(connected),
        .subscribed(subscribed),.connection_handle(handle),.notification_count(notification_count),
        .acl_rx_count(acl_rx_count),.att_request_count(att_request_count),.completed_packets(completed_packets),
        .debug_state(app_state),.error_count(app_errors),.elapsed_ms(app_elapsed)
    );
    assign debug[0*32+:32]=32'h42545647;
    assign debug[1*32+:32]=32'd1;
    assign debug[2*32+:32]={20'd0,hci_valid_mask,2'd0,session_ended,failed,subscribed,connected,initialized,link_up,outputs_active};
    assign debug[3*32+:32]=uptime_ms;
    assign debug[4*32+:32]={8'd0,app_state,init_state,h5_state};
    assign debug[5*32+:32]={core_error != 0 ? core_error : init_error,last_status,last_opcode};
    assign debug[6*32+:32]=command_count;
    assign debug[7*32+:32]=patch_fragments;
    assign debug[8*32+:32]=rx_frames;
    assign debug[9*32+:32]=tx_frames;
    assign debug[10*32+:32]=retries;
    assign debug[11*32+:32]=uart_errors;
    assign debug[12*32+:32]=protocol_errors;
    assign debug[13*32+:32]=notification_count;
    assign debug[14*32+:32]=acl_rx_count;
    assign debug[15*32+:32]=att_request_count;
    assign debug[16*32+:32]=completed_packets;
    assign debug[17*32+:32]=app_errors;
    assign debug[18*32+:32]=bd_addr[31:0];
    assign debug[19*32+:32]={16'd0,bd_addr[47:32]};
    assign debug[20*32+:32]={12'd0,handle,rom_version};
    assign debug[21*32+:32]=app_elapsed;
    assign debug[22*32+:32]=CLK_HZ;
    assign debug[23*32+:32]=fast_mode ? FAST_BAUD : BAUD;
endmodule
