`timescale 1ns/1ps
// One stable local request slot per client; no BSRAM or audio storage.
module basic_pitch_ddr_client_queues #(
    parameter TAG_BITS=5
)(
    input wire clk,reset_n,bist_done,
    input wire bist_valid,bist_write,
    input wire [28:0] bist_address,
    input wire [255:0] bist_data,
    output wire bist_ready,bist_response,
    input wire scan_valid,
    input wire [28:0] scan_address,
    output wire scan_ready,scan_response,
    input wire display_valid,
    input wire [28:0] display_address,
    output wire display_ready,display_response,
    input wire audio_valid,audio_write,
    input wire [28:0] audio_address,
    input wire [255:0] audio_data,
    output wire audio_ready,audio_response,
    input wire music_valid,music_write,
    input wire [28:0] music_address,
    input wire [255:0] music_data,
    input wire [31:0] music_mask,
    output wire music_ready,music_response,
    input wire delay_valid,delay_write,
    input wire [28:0] delay_address,
    input wire [255:0] delay_data,
    output wire delay_ready,delay_response,
    input wire writer_valid,
    input wire [28:0] writer_address,
    input wire [255:0] writer_data,
    output wire writer_ready,
    input wire cpu_valid,cpu_write,
    input wire [28:0] cpu_address,
    input wire [255:0] cpu_data,
    input wire [31:0] cpu_mask,
    output wire cpu_ready,cpu_response,
    output wire [2:0] app_cmd,
    output wire app_en,app_wren,app_wend,
    output wire [28:0] app_address,
    output wire [255:0] app_data,
    output wire [31:0] app_mask,
    input wire app_ready,app_write_ready,app_response,
    input wire [255:0] app_response_data,
    output wire [255:0] response_data,
    output wire response_fault
);
    wire bist_qvalid,bist_qwrite,bist_qready;
    wire [28:0] bist_qaddress;
    wire [255:0] bist_qdata;
    wire [31:0] bist_qmask;
    basic_pitch_ddr_client_slot u_bist_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(bist_valid),
        .request_write(bist_write),.request_address(bist_address),
        .request_data(bist_data),.request_mask(32'd0),.request_ready(bist_ready),
        .queued_valid(bist_qvalid),.queued_write(bist_qwrite),
        .queued_address(bist_qaddress),.queued_data(bist_qdata),
        .queued_mask(bist_qmask),.queued_ready(bist_qready));
    wire scan_qvalid,scan_qwrite,scan_qready;
    wire [28:0] scan_qaddress;
    wire [255:0] scan_qdata;
    wire [31:0] scan_qmask;
    basic_pitch_ddr_client_slot u_scan_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(scan_valid),
        .request_write(1'b0),.request_address(scan_address),
        .request_data(256'd0),.request_mask(32'd0),.request_ready(scan_ready),
        .queued_valid(scan_qvalid),.queued_write(scan_qwrite),
        .queued_address(scan_qaddress),.queued_data(scan_qdata),
        .queued_mask(scan_qmask),.queued_ready(scan_qready));
    wire display_qvalid,display_qwrite,display_qready;
    wire [28:0] display_qaddress;
    wire [255:0] display_qdata;
    wire [31:0] display_qmask;
    basic_pitch_ddr_client_slot u_display_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(display_valid),
        .request_write(1'b0),.request_address(display_address),
        .request_data(256'd0),.request_mask(32'd0),.request_ready(display_ready),
        .queued_valid(display_qvalid),.queued_write(display_qwrite),
        .queued_address(display_qaddress),.queued_data(display_qdata),
        .queued_mask(display_qmask),.queued_ready(display_qready));
    wire audio_qvalid,audio_qwrite,audio_qready;
    wire [28:0] audio_qaddress;
    wire [255:0] audio_qdata;
    wire [31:0] audio_qmask;
    basic_pitch_ddr_client_slot u_audio_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(audio_valid),
        .request_write(audio_write),.request_address(audio_address),
        .request_data(audio_data),.request_mask(32'd0),.request_ready(audio_ready),
        .queued_valid(audio_qvalid),.queued_write(audio_qwrite),
        .queued_address(audio_qaddress),.queued_data(audio_qdata),
        .queued_mask(audio_qmask),.queued_ready(audio_qready));
    wire music_qvalid,music_qwrite,music_qready;
    wire [28:0] music_qaddress;
    wire [255:0] music_qdata;
    wire [31:0] music_qmask;
    basic_pitch_ddr_client_slot u_music_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(music_valid),
        .request_write(music_write),.request_address(music_address),
        .request_data(music_data),.request_mask(music_mask),.request_ready(music_ready),
        .queued_valid(music_qvalid),.queued_write(music_qwrite),
        .queued_address(music_qaddress),.queued_data(music_qdata),
        .queued_mask(music_qmask),.queued_ready(music_qready));
    wire delay_qvalid,delay_qwrite,delay_qready;
    wire [28:0] delay_qaddress;
    wire [255:0] delay_qdata;
    wire [31:0] delay_qmask;
    basic_pitch_ddr_client_slot u_delay_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(delay_valid),
        .request_write(delay_write),.request_address(delay_address),
        .request_data(delay_data),.request_mask(32'd0),.request_ready(delay_ready),
        .queued_valid(delay_qvalid),.queued_write(delay_qwrite),
        .queued_address(delay_qaddress),.queued_data(delay_qdata),
        .queued_mask(delay_qmask),.queued_ready(delay_qready));
    wire writer_qvalid,writer_qwrite,writer_qready;
    wire [28:0] writer_qaddress;
    wire [255:0] writer_qdata;
    wire [31:0] writer_qmask;
    basic_pitch_ddr_client_slot u_writer_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(writer_valid),
        .request_write(1'b1),.request_address(writer_address),
        .request_data(writer_data),.request_mask(32'd0),.request_ready(writer_ready),
        .queued_valid(writer_qvalid),.queued_write(writer_qwrite),
        .queued_address(writer_qaddress),.queued_data(writer_qdata),
        .queued_mask(writer_qmask),.queued_ready(writer_qready));
    wire cpu_qvalid,cpu_qwrite,cpu_qready;
    wire [28:0] cpu_qaddress;
    wire [255:0] cpu_qdata;
    wire [31:0] cpu_qmask;
    basic_pitch_ddr_client_slot u_cpu_slot(
        .clk(clk),.reset_n(reset_n),.request_valid(cpu_valid),
        .request_write(cpu_write),.request_address(cpu_address),
        .request_data(cpu_data),.request_mask(cpu_mask),.request_ready(cpu_ready),
        .queued_valid(cpu_qvalid),.queued_write(cpu_qwrite),
        .queued_address(cpu_qaddress),.queued_data(cpu_qdata),
        .queued_mask(cpu_qmask),.queued_ready(cpu_qready));
    basic_pitch_ddr_arbiter_pipeline #(.TAG_BITS(TAG_BITS),.REGISTER_GRANTS(1)) u_core(
        .clk(clk),
        .reset_n(reset_n),
        .bist_done(bist_done),
        .bist_valid(bist_qvalid),
        .bist_address(bist_qaddress),
        .bist_ready(bist_qready),
        .bist_write(bist_qwrite),
        .bist_data(bist_qdata),
        .bist_response(bist_response),
        .scan_valid(scan_qvalid),
        .scan_address(scan_qaddress),
        .scan_ready(scan_qready),
        .scan_response(scan_response),
        .display_valid(display_qvalid),
        .display_address(display_qaddress),
        .display_ready(display_qready),
        .display_response(display_response),
        .audio_valid(audio_qvalid),
        .audio_address(audio_qaddress),
        .audio_ready(audio_qready),
        .audio_write(audio_qwrite),
        .audio_data(audio_qdata),
        .audio_response(audio_response),
        .music_valid(music_qvalid),
        .music_address(music_qaddress),
        .music_ready(music_qready),
        .music_write(music_qwrite),
        .music_data(music_qdata),
        .music_mask(music_qmask),
        .music_response(music_response),
        .delay_valid(delay_qvalid),
        .delay_address(delay_qaddress),
        .delay_ready(delay_qready),
        .delay_write(delay_qwrite),
        .delay_data(delay_qdata),
        .delay_response(delay_response),
        .writer_valid(writer_qvalid),
        .writer_address(writer_qaddress),
        .writer_ready(writer_qready),
        .writer_data(writer_qdata),
        .cpu_valid(cpu_qvalid),
        .cpu_address(cpu_qaddress),
        .cpu_ready(cpu_qready),
        .cpu_write(cpu_qwrite),
        .cpu_data(cpu_qdata),
        .cpu_mask(cpu_qmask),
        .cpu_response(cpu_response),
        .app_cmd(app_cmd),
        .app_en(app_en),
        .app_wren(app_wren),
        .app_wend(app_wend),
        .app_address(app_address),
        .app_data(app_data),
        .app_mask(app_mask),
        .app_ready(app_ready),
        .app_write_ready(app_write_ready),
        .app_response(app_response),
        .app_response_data(app_response_data),
        .response_data(response_data),
        .response_fault(response_fault));
endmodule

module basic_pitch_ddr_client_slot(
    input wire clk,reset_n,request_valid,request_write,
    input wire [28:0] request_address,
    input wire [255:0] request_data,
    input wire [31:0] request_mask,
    output wire request_ready,queued_valid,
    output reg queued_write,
    output reg [28:0] queued_address,
    output reg [255:0] queued_data,
    output reg [31:0] queued_mask,
    input wire queued_ready
);
    reg full;
    assign request_ready=reset_n && !full;
    assign queued_valid=full;
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)full<=0;
        else if(full)begin if(queued_ready)full<=0;end
        else if(request_valid)full<=1;
    end
    // Valid guards the payload, so only the occupancy needs asynchronous
    // reset. Wide payload stays stable until the core accepts the slot.
    always @(posedge clk)begin
        if(request_ready && request_valid)begin
            queued_write<=request_write;queued_address<=request_address;
            queued_data<=request_data;queued_mask<=request_mask;
        end
    end
endmodule
