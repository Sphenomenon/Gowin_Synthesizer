`include "native_bluetooth/patch_path.vh"

module workstation_bluetooth #(
    parameter CLK_HZ=50000000,
    parameter CAPACITY_FRAMES=16384,
    parameter DISABLE_MS=200,
    parameter STARTUP_MS=2000,
    parameter EXTERNAL_SEAL_PROTOCOL=0
) (
    input wire clk_i, rst_ni, module_uart_tx_i,
    input wire pcm_valid_i, source_allowed_i,
    input wire [31:0] pcm_pair_i, pcm_sequence_i,
    output wire module_uart_rx_o, module_bt_dis_no, module_wl_dis_no, outputs_active_o,
    output wire initialized_o, connected_o, subscribed_o, failed_o,
    output wire [767:0] status_o,
    input wire seal_hold_i, seal_request_i,
    output wire seal_ready_o, seal_pending_o, seal_done_o, seal_failed_o,
    output wire [3:0] seal_failure_code_o,
    output wire [7:0] seal_record_state_o,
    output wire [31:0] seal_recording_id_o, seal_frames_o, seal_crc_o
);
    wire reset_n;
    reset_release_sync u_reset (.clk(clk_i),.arstn(rst_ni),.resetn(reset_n));
    reg sample_seen;
    reg [31:0] sample_age, previous_sequence;
    wire source_fault = pcm_valid_i && sample_seen && pcm_sequence_i != previous_sequence+1'b1;
    always @(posedge clk_i or negedge reset_n) begin
        if(!reset_n) begin
            sample_seen<=0;sample_age<=CLK_HZ/250;previous_sequence<=0;
        end else begin
            if(pcm_valid_i) begin sample_seen<=1;sample_age<=0;previous_sequence<=pcm_sequence_i;end
            else if(sample_age<CLK_HZ/250) sample_age<=sample_age+1'b1;
        end
    end
    wire core_active;
    bt_verilog_core #(
        .CLK_HZ(CLK_HZ),.EXTERNAL_PCM(1),.EXTERNAL_SEAL_PROTOCOL(EXTERNAL_SEAL_PROTOCOL),.CAPACITY_FRAMES(CAPACITY_FRAMES),.DEVICE_NAME("GW138K-MAIN"),
        .CACHE_METADATA_RAM_STYLE("distributed_ram"),
        .DISABLE_MS(DISABLE_MS),.STARTUP_MS(STARTUP_MS),.SESSION_MS(0),
        .PATCH_FILE(`WORKSTATION_BLE_PATCH_FILE)
    ) u_core (
        .clk(clk_i),.resetn(reset_n),.enable(reset_n),.uart_rx(module_uart_tx_i),
        .seal_hold_i(seal_hold_i),.seal_request_i(seal_request_i),
        .seal_ready_o(seal_ready_o),.seal_pending_o(seal_pending_o),.seal_done_o(seal_done_o),.seal_failed_o(seal_failed_o),
        .seal_failure_code_o(seal_failure_code_o),.seal_record_state_o(seal_record_state_o),
        .seal_recording_id_o(seal_recording_id_o),.seal_frames_o(seal_frames_o),.seal_crc_o(seal_crc_o),
        .pcm_valid_i(pcm_valid_i),.pcm_pair_i({pcm_pair_i[15:0],pcm_pair_i[31:16]}),
        .source_ready_i(source_allowed_i && sample_seen && sample_age<CLK_HZ/250),
        .source_fault_i(source_fault),.uart_tx(module_uart_rx_o),.bt_enable(module_bt_dis_no),
        .outputs_active(core_active),.initialized(initialized_o),.connected(connected_o),
        .subscribed(subscribed_o),.failed(failed_o),.debug(status_o)
    );
    assign outputs_active_o = rst_ni && reset_n && core_active;
    assign module_wl_dis_no = 1'b0;
endmodule
