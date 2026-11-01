`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"

// Unselected task3 W-media composition. BIST and native owner/tag semantics
// are shared with the maintained memory boundaries. No graphics, CPU DDR,
// TF ring or second recording owner is instantiated here.
module workstation_media_memory #(
    parameter integer BIST_BURSTS=`PRJ1_DDR_BIST_BEATS,
    parameter integer TAG_BITS=5
) (
    input wire reset_ni,clk_50m_i,memory_clk_i,memory_reset_ni,
    input wire memory_calibrated_i,memory_pll_locked_i,
    output wire client_reset_no,client_ready_o,
    input wire music_valid_i,music_write_i,
    input wire [28:0] music_address_i,
    input wire [255:0] music_data_i,
    input wire [31:0] music_mask_i,
    output wire music_ready_o,music_response_o,
    input wire delay_valid_i,delay_write_i,
    input wire [28:0] delay_address_i,
    input wire [255:0] delay_data_i,
    output wire delay_ready_o,delay_response_o,
    input wire recording_valid_i,recording_write_i,
    input wire [28:0] recording_address_i,
    input wire [255:0] recording_data_i,
    input wire [31:0] recording_mask_i,
    output wire recording_ready_o,recording_response_o,
    output wire [2:0] app_cmd_o,
    output wire app_en_o,app_wren_o,app_wend_o,
    output wire [28:0] app_address_o,
    output wire [255:0] app_data_o,
    output wire [31:0] app_mask_o,
    input wire app_ready_i,app_write_ready_i,app_response_i,
    input wire [255:0] app_response_data_i,
    output wire [255:0] response_data_o,
    output wire [7:0] memory_flags_o,
    // These retain their distinct meanings: local slot, core buffer, native
    // command/write acceptance. In particular raw-store seal uses native[8].
    output wire [8:0] slot_accept_o,core_accept_o,native_accept_o,
    output wire transport_fault_o
);
    wire backend_release=reset_ni && memory_reset_ni &&
        memory_calibrated_i && memory_pll_locked_i;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] memory_release;
    always @(posedge memory_clk_i or negedge backend_release)
        if(!backend_release)memory_release<=0;
        else memory_release<={memory_release[1:0],1'b1};
    assign client_reset_no=memory_release[2];
    wire bist_valid,bist_write,bist_ready,bist_response,bist_done,bist_failed;
    wire [28:0] bist_address;
    wire [255:0] bist_data;
    wire music_slot_ready,delay_slot_ready,recording_slot_ready;
    wire music_response,delay_response,recording_response,response_fault;
    ddr3_bist #(.BURSTS(BIST_BURSTS)) u_bist(
        .clk(memory_clk_i),.rst_n(client_reset_no),
        .req_valid(bist_valid),.req_write(bist_write),.req_ready(bist_ready),
        .req_addr(bist_address),.req_wdata(bist_data),.rsp_valid(bist_response),
        .rsp_data(response_data_o),.done(bist_done),.failed(bist_failed),
        .error_count(),.first_error_addr());
    assign client_ready_o=client_reset_no && bist_done && !bist_failed && !transport_fault_o;
    // Do not expose an empty slot as successful acceptance while BIST/fault
    // fences its request. Old W21 audio_memory remains byte-identical.
    assign music_ready_o=client_ready_o && music_slot_ready;
    assign delay_ready_o=client_ready_o && delay_slot_ready;
    assign recording_ready_o=client_ready_o && recording_slot_ready;
    assign music_response_o=client_ready_o && music_response;
    assign delay_response_o=client_ready_o && delay_response;
    assign recording_response_o=client_ready_o && recording_response;
    workstation_recording_ddr_client_queues #(.TAG_BITS(TAG_BITS),.RECORDING_ENABLE(1)) u_arbiter(
        .clk(memory_clk_i),.reset_n(client_reset_no),.bist_done(bist_done),
        .bist_valid(bist_valid),.bist_write(bist_write),.bist_address(bist_address),
        .bist_data(bist_data),.bist_ready(bist_ready),.bist_response(bist_response),
        .scan_valid(1'b0),.scan_address(29'd0),.scan_ready(),.scan_response(),
        .display_valid(1'b0),.display_address(29'd0),.display_ready(),.display_response(),
        .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),
        .audio_ready(),.audio_response(),
        .music_valid(music_valid_i && client_ready_o),.music_write(music_write_i),
        .music_address(music_address_i),.music_data(music_data_i),.music_mask(music_mask_i),
        .music_ready(music_slot_ready),.music_response(music_response),
        .delay_valid(delay_valid_i && client_ready_o),.delay_write(delay_write_i),
        .delay_address(delay_address_i),.delay_data(delay_data_i),
        .delay_ready(delay_slot_ready),.delay_response(delay_response),
        .writer_valid(1'b0),.writer_address(29'd0),.writer_data(256'd0),.writer_ready(),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),
        .cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
        .recording_valid(recording_valid_i && client_ready_o),.recording_write(recording_write_i),
        .recording_address(recording_address_i),.recording_data(recording_data_i),.recording_mask(recording_mask_i),
        .recording_ready(recording_slot_ready),.recording_response(recording_response),
        .app_cmd(app_cmd_o),.app_en(app_en_o),.app_wren(app_wren_o),.app_wend(app_wend_o),
        .app_address(app_address_o),.app_data(app_data_o),.app_mask(app_mask_o),
        // An unowned return fences outstanding dispatch on this same edge.
        .app_ready(app_ready_i && !transport_fault_o),.app_write_ready(app_write_ready_i),
        .app_response(app_response_i),.app_response_data(app_response_data_i),
        .response_data(response_data_o),.response_fault(response_fault),
        .slot_accept_o(slot_accept_o),.core_accept_o(core_accept_o),.native_accept_o(native_accept_o),
        .transport_fault_o(transport_fault_o));
    // Established flag meanings: bit0 calibrated, bit1 BIST done, bit2 BIST
    // failed, bit4 native response fault, bit6 PLL locked; video bits are zero.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [7:0] flags_meta,flags_sync;
    always @(posedge clk_50m_i or negedge reset_ni)
        if(!reset_ni)begin flags_meta<=0;flags_sync<=0;end
        else begin
            flags_meta<={1'b0,memory_pll_locked_i,1'b0,response_fault,
                1'b0,bist_failed,bist_done,memory_calibrated_i};
            flags_sync<=flags_meta;
        end
    assign memory_flags_o=flags_sync;
endmodule
