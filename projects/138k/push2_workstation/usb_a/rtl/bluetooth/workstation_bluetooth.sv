`include "native_bluetooth/patch_path.vh"

module workstation_bluetooth #(
    parameter CLK_HZ=50000000,
    parameter CAPACITY_FRAMES=16384,
    parameter STORAGE_DDR=0,
    parameter DISABLE_MS=200,
    parameter STARTUP_MS=2000,
    parameter EXTERNAL_SEAL_PROTOCOL=0
) (
    input wire clk_i, rst_ni, module_uart_tx_i,
    input wire pcm_valid_i, source_allowed_i,
    input wire [31:0] pcm_pair_i, pcm_sequence_i,
    input wire memory_clk_i, memory_rst_ni, memory_ready_i,
    output wire memory_req_o, memory_write_o,
    output wire [28:0] memory_address_o,
    output wire [255:0] memory_data_o,
    output wire [31:0] memory_mask_o,
    input wire memory_req_ready_i, memory_response_i,
    input wire [255:0] memory_read_data_i,
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
    localparam integer SAMPLE_MAX=CLK_HZ/250;
    localparam integer AGE_BITS=SAMPLE_MAX<2 ? 1 : $clog2(SAMPLE_MAX+1);
    reg [AGE_BITS-1:0] sample_age;
    reg [31:0] previous_sequence;
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
    wire store_write,store_fetch,store_fetched,store_ready,store_fault;
    wire [13:0] store_write_frame,store_read_frame;
    wire [31:0] store_write_pcm,store_read_pcm,store_fetch_byte;
    wire [12:0] store_fetch_bytes;
    generate if(STORAGE_DDR) begin: g_store
        if(CAPACITY_FRAMES>16384) begin: g_bad_capacity
            initial $error("BLE DDR allocation holds at most 16384 PCM frames");
        end
        workstation_ble_pcm_store u_store (
            .clk_i(clk_i),.rst_ni(reset_n),.memory_clk_i(memory_clk_i),.memory_rst_ni(memory_rst_ni),
            .memory_ready_i(memory_ready_i),.write_i(store_write),.write_frame_i(store_write_frame),
            .write_pcm_i(store_write_pcm),.fetch_i(store_fetch),.fetch_byte_i(store_fetch_byte),
            .fetch_bytes_i(store_fetch_bytes),.fetched_o(store_fetched),.ready_o(store_ready),.fault_o(store_fault),
            .read_frame_i(store_read_frame),.read_pcm_o(store_read_pcm),
            .req_o(memory_req_o),.write_o(memory_write_o),.address_o(memory_address_o),
            .data_o(memory_data_o),.mask_o(memory_mask_o),.req_ready_i(memory_req_ready_i),
            .response_i(memory_response_i),.response_data_i(memory_read_data_i));
    end else begin: g_local_store
        assign store_fetched=1'b1;assign store_ready=1'b1;assign store_fault=1'b0;assign store_read_pcm=0;
        assign memory_req_o=0;assign memory_write_o=0;assign memory_address_o=0;assign memory_data_o=0;assign memory_mask_o=0;
    end endgenerate
    bt_verilog_core #(
        .CLK_HZ(CLK_HZ),.EXTERNAL_PCM(1),.EXTERNAL_SEAL_PROTOCOL(EXTERNAL_SEAL_PROTOCOL),.CAPACITY_FRAMES(CAPACITY_FRAMES),.STORAGE_DDR(STORAGE_DDR),.DEVICE_NAME("GW138K-MAIN"),
        .CACHE_METADATA_RAM_STYLE("distributed_ram"),.CACHE_ENTRIES(1),.CACHE_EXPIRY_MS(0),
        .DISABLE_MS(DISABLE_MS),.STARTUP_MS(STARTUP_MS),.SESSION_MS(0),
        .PATCH_FILE(`WORKSTATION_BLE_PATCH_FILE)
    ) u_core (
        .clk(clk_i),.resetn(reset_n),.enable(reset_n),.uart_rx(module_uart_tx_i),
        .seal_hold_i(seal_hold_i),.seal_request_i(seal_request_i),
        .seal_ready_o(seal_ready_o),.seal_pending_o(seal_pending_o),.seal_done_o(seal_done_o),.seal_failed_o(seal_failed_o),
        .seal_failure_code_o(seal_failure_code_o),.seal_record_state_o(seal_record_state_o),
        .seal_recording_id_o(seal_recording_id_o),.seal_frames_o(seal_frames_o),.seal_crc_o(seal_crc_o),
        .pcm_valid_i(pcm_valid_i),.pcm_pair_i({pcm_pair_i[15:0],pcm_pair_i[31:16]}),
        .source_ready_i(source_allowed_i && store_ready && sample_seen && sample_age<CLK_HZ/250),
        .source_fault_i(source_fault || store_fault),
        .pcm_store_write_o(store_write),.pcm_store_write_frame_o(store_write_frame),
        .pcm_store_write_data_o(store_write_pcm),.pcm_store_read_frame_o(store_read_frame),
        .pcm_store_fetch_o(store_fetch),.pcm_store_fetch_byte_o(store_fetch_byte),
        .pcm_store_fetch_bytes_o(store_fetch_bytes),.pcm_store_read_data_i(store_read_pcm),
        .pcm_store_fetched_i(store_fetched),.pcm_store_ready_i(store_ready),.pcm_store_fault_i(store_fault),.uart_tx(module_uart_rx_o),.bt_enable(module_bt_dis_no),
        .outputs_active(core_active),.initialized(initialized_o),.connected(connected_o),
        .subscribed(subscribed_o),.failed(failed_o),.debug(status_o)
    );
    assign outputs_active_o = rst_ni && reset_n && core_active;
    assign module_wl_dis_no = 1'b0;
endmodule
