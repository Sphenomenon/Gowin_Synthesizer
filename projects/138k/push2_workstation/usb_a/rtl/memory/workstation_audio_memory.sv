`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"

// Explicit W audio-only memory composition. The existing native controller,
// BIST, bounded client slots and owner-6 delay service remain the owners.
// No display clock, framebuffer, CPU DDR window or recording client exists.
module workstation_audio_memory #(parameter integer BIST_BURSTS=`PRJ1_DDR_BIST_BEATS) (
    input wire reset_ni,clk_50m_i,memory_clk_i,memory_reset_ni,
    input wire memory_calibrated_i,memory_pll_locked_i,
    output wire client_reset_no,client_ready_o,
    input wire delay_valid_i,delay_write_i,
    input wire [28:0] delay_address_i,
    input wire [255:0] delay_data_i,
    output wire delay_ready_o,delay_response_o,
    output wire [2:0] app_cmd_o,
    output wire app_en_o,app_wren_o,app_wend_o,
    output wire [28:0] app_address_o,
    output wire [255:0] app_data_o,
    output wire [31:0] app_mask_o,
    input wire app_ready_i,app_write_ready_i,app_response_i,
    input wire [255:0] app_response_data_i,
    output wire [255:0] response_data_o,
    output wire [7:0] memory_flags_o
);
    wire backend_release=reset_ni && memory_reset_ni &&
        memory_calibrated_i && memory_pll_locked_i;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] memory_release;
    always @(posedge memory_clk_i or negedge backend_release)
        if(!backend_release)memory_release<=0;
        else memory_release<={memory_release[1:0],1'b1};
    assign client_reset_no=memory_release[2];
    wire bist_valid,bist_write,bist_ready,bist_response,bist_done,bist_failed;
    wire response_fault;
    wire [28:0] bist_address;
    wire [255:0] bist_data;
    ddr3_bist #(.BURSTS(BIST_BURSTS)) u_bist(
        .clk(memory_clk_i),.rst_n(client_reset_no),
        .req_valid(bist_valid),.req_write(bist_write),.req_ready(bist_ready),
        .req_addr(bist_address),.req_wdata(bist_data),.rsp_valid(bist_response),
        .rsp_data(response_data_o),.done(bist_done),.failed(bist_failed),
        .error_count(),.first_error_addr());
    assign client_ready_o=client_reset_no && bist_done && !bist_failed && !response_fault;
    // Preserve the established native owner/tag protocol. Absent clients have
    // no requests or exposed interfaces; their idle slots are synthesis dead.
    basic_pitch_ddr_client_queues u_arbiter(
        .clk(memory_clk_i),.reset_n(client_reset_no),.bist_done(bist_done),
        .bist_valid(bist_valid),.bist_write(bist_write),.bist_address(bist_address),
        .bist_data(bist_data),.bist_ready(bist_ready),.bist_response(bist_response),
        .scan_valid(1'b0),.scan_address(29'd0),.scan_ready(),.scan_response(),
        .display_valid(1'b0),.display_address(29'd0),.display_ready(),.display_response(),
        .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),
        .audio_ready(),.audio_response(),
        .music_valid(1'b0),.music_write(1'b0),.music_address(29'd0),
        .music_data(256'd0),.music_mask(32'd0),.music_ready(),.music_response(),
        .delay_valid(delay_valid_i && client_ready_o),.delay_write(delay_write_i),
        .delay_address(delay_address_i),.delay_data(delay_data_i),
        .delay_ready(delay_ready_o),.delay_response(delay_response_o),
        .writer_valid(1'b0),.writer_address(29'd0),.writer_data(256'd0),.writer_ready(),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),
        .cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
        .app_cmd(app_cmd_o),.app_en(app_en_o),.app_wren(app_wren_o),.app_wend(app_wend_o),
        .app_address(app_address_o),.app_data(app_data_o),.app_mask(app_mask_o),
        .app_ready(app_ready_i),.app_write_ready(app_write_ready_i),
        .app_response(app_response_i),.app_response_data(app_response_data_i),
        .response_data(response_data_o),.response_fault(response_fault));
    // The boot status keeps its established bit meanings; video bits are zero.
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
