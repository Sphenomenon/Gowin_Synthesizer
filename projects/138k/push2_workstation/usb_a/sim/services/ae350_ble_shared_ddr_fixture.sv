`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"
// Same owner5/6/8 queues and registered arbiter selected by W media memory.
// Other clients generate deterministic requests, not CNN or delay processing.
// The controller is a bounded behavioral model; BIST/PHY are outside scope.
module ae350_ble_shared_ddr_fixture #(
    parameter integer CAPACITY_FRAMES=2880000,
    parameter [28:0] BASE_APP=`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE
)(
    input wire clk,resetn,native_pause,
    output reg [31:0] native_writes_o,max_native_address_o,
    output reg [31:0] music_commands_o,delay_commands_o,
    input wire raw_start_valid_o,raw_clear_valid_o,
    output wire raw_start_ready_i,raw_start_done_i,raw_clear_ready_i,raw_clear_done_i,
    input wire raw_capture_valid_o,
    input wire [31:0] raw_capture_index_o,raw_capture_pcm_o,
    output wire raw_capture_ready_i,
    input wire raw_close_valid_o,
    output wire raw_close_ready_i,raw_drained_i,raw_fault_i,
    output wire raw_object_fault_i,raw_channel_fault_i,
    output wire [3:0] raw_failure_code_i,
    output wire [31:0] raw_accepted_frames_i,raw_committed_frames_i,
    input wire raw_fetch_valid_o,
    output wire raw_fetch_ready_i,
    input wire [31:0] raw_fetch_offset_o,
    input wire [13:0] raw_fetch_length_o,
    output wire raw_fetch_done_i,raw_fetch_fault_i,raw_cache_valid_i,
    input wire [31:0] raw_sample_addr_o,
    output wire [31:0] raw_sample_word_i
);
    reg memory_clk=0;
    always #7 memory_clk=~memory_clk;
    wire slot_valid,slot_ready,record_response,write_enable,transport_fault;
    wire [28:0] address;
    wire [255:0] write_data,response_data;
    wire [31:0] mask;
    wire [8:0] native_accept;
    workstation_ble_raw_ddr_store #(.CAPACITY_FRAMES(CAPACITY_FRAMES),.BASE_APP(BASE_APP)) store(
        .clk_i(clk),.memory_clk_i(memory_clk),.rst_ni(resetn),
        .start_valid_i(raw_start_valid_o),.start_ready_o(raw_start_ready_i),.start_done_o(raw_start_done_i),
        .clear_valid_i(raw_clear_valid_o),.clear_ready_o(raw_clear_ready_i),.clear_done_o(raw_clear_done_i),
        .capture_valid_i(raw_capture_valid_o),.capture_index_i(raw_capture_index_o),.capture_pcm_i(raw_capture_pcm_o),.capture_ready_o(raw_capture_ready_i),
        .close_valid_i(raw_close_valid_o),.close_ready_o(raw_close_ready_i),.drained_o(raw_drained_i),
        .fault_o(raw_fault_i),.object_fault_o(raw_object_fault_i),.channel_fault_o(raw_channel_fault_i),.failure_code_o(raw_failure_code_i),
        .accepted_frames_o(raw_accepted_frames_i),.committed_frames_o(raw_committed_frames_i),
        .fetch_valid_i(raw_fetch_valid_o),.fetch_ready_o(raw_fetch_ready_i),.fetch_offset_i(raw_fetch_offset_o),.fetch_length_i(raw_fetch_length_o),
        .fetch_done_o(raw_fetch_done_i),.fetch_fault_o(raw_fetch_fault_i),.cache_valid_o(raw_cache_valid_i),
        .sample_addr_i(raw_sample_addr_o),.sample_word_o(raw_sample_word_i),
        .slot_valid_o(slot_valid),.slot_ready_i(slot_ready),.native_accept_i(native_accept[8]),
        .ddr_write_o(write_enable),.ddr_address_o(address),.ddr_data_o(write_data),.ddr_mask_o(mask),
        .read_response_i(record_response),.read_data_i(response_data),.transport_fault_i(transport_fault),.native_protocol_fault_o());

    localparam [28:0] MUSIC_ADDR=`PRJ1_DDR_TASK3_W_CNN_PCM_APP_BASE;
    localparam [28:0] DELAY_ADDR=`PRJ1_DDR_DELAY_RING_APP_BASE;
    reg [1:0] music_phase,delay_phase;
    reg [31:0] music_index,delay_index;
    wire music_ready,music_response,delay_ready,delay_response;
    wire [255:0] music_data={8{32'hc5a50000^music_index}};
    wire [255:0] delay_data={8{32'hd6b60000^delay_index}};
    wire [2:0] app_cmd;
    wire app_en,app_wren,app_wend;
    wire [28:0] app_address;
    wire [255:0] app_data;
    wire [31:0] app_mask;
    reg app_response;
    reg [255:0] app_response_data;
    reg [31:0] memory_cycles;
    reg read_pending;
    reg [3:0] read_delay;
    reg [255:0] pending_data;
    // Independent command/write-ready stalls plus delayed ordered reads.
    wire app_ready=resetn && !native_pause && !read_pending && memory_cycles%7!=0;
    wire app_write_ready=resetn && !native_pause && memory_cycles%5!=0;
    workstation_recording_ddr_client_queues #(.TAG_BITS(5),.RECORDING_ENABLE(1)) fabric(
        .clk(memory_clk),.reset_n(resetn),.bist_done(1'b1),
        .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),.bist_ready(),.bist_response(),
        .scan_valid(1'b0),.scan_address(29'd0),.scan_ready(),.scan_response(),
        .display_valid(1'b0),.display_address(29'd0),.display_ready(),.display_response(),
        .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),.audio_ready(),.audio_response(),
        .music_valid(music_phase!=2),.music_write(music_phase==0),.music_address(MUSIC_ADDR),
        .music_data(music_data),.music_mask(32'd0),.music_ready(music_ready),.music_response(music_response),
        .delay_valid(delay_phase!=2),.delay_write(delay_phase==0),.delay_address(DELAY_ADDR),
        .delay_data(delay_data),.delay_ready(delay_ready),.delay_response(delay_response),
        .writer_valid(1'b0),.writer_address(29'd0),.writer_data(256'd0),.writer_ready(),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
        .recording_valid(slot_valid),.recording_write(write_enable),.recording_address(address),
        .recording_data(write_data),.recording_mask(mask),.recording_ready(slot_ready),.recording_response(record_response),
        .app_cmd(app_cmd),.app_en(app_en),.app_wren(app_wren),.app_wend(app_wend),
        .app_address(app_address),.app_data(app_data),.app_mask(app_mask),
        .app_ready(app_ready),.app_write_ready(app_write_ready),.app_response(app_response),.app_response_data(app_response_data),
        .response_data(response_data),.response_fault(),.slot_accept_o(),.core_accept_o(),.native_accept_o(native_accept),.transport_fault_o(transport_fault));

    localparam integer BEATS=(CAPACITY_FRAMES+7)/8;
    reg [255:0] memory[0:BEATS-1];
    reg [255:0] saved_music,saved_delay;
    integer beat;
    always @(posedge memory_clk or negedge resetn)begin
        if(!resetn)begin
            memory_cycles<=0;read_pending<=0;read_delay<=0;pending_data<=0;
            app_response<=0;app_response_data<=0;
            native_writes_o<=0;max_native_address_o<=0;music_commands_o<=0;delay_commands_o<=0;
            music_phase<=0;delay_phase<=0;music_index<=0;delay_index<=0;
            saved_music<=0;saved_delay<=0;
        end else begin
            memory_cycles<=memory_cycles+1'b1;
            app_response<=read_pending && read_delay==0;
            if(read_pending && read_delay!=0)read_delay<=read_delay-1'b1;
            if(read_pending && read_delay==0)begin app_response_data<=pending_data;read_pending<=0;end
            if(transport_fault)$fatal(1,"shared DDR transport fault");
            if(music_phase!=2 && music_ready)music_phase<=music_phase+1'b1;
            if(delay_phase!=2 && delay_ready)delay_phase<=delay_phase+1'b1;
            if(music_response)begin
                if(music_phase!=2 || response_data!==music_data)$fatal(1,"owner5 response identity/data");
                music_phase<=0;music_index<=music_index+1'b1;
            end
            if(delay_response)begin
                if(delay_phase!=2 || response_data!==delay_data)$fatal(1,"owner6 response identity/data");
                delay_phase<=0;delay_index<=delay_index+1'b1;
            end
            if(app_en)begin
                if(app_address[2:0]!=0 || app_wren!=(app_cmd==0) || app_wend!=app_wren)
                    $fatal(1,"native command/write contract");
                if(app_address==MUSIC_ADDR)begin
                    if(!native_accept[5])$fatal(1,"wrong owner5 native grant");
                    music_commands_o<=music_commands_o+1'b1;
                    if(app_wren)saved_music<=app_data;else pending_data<=saved_music;
                end else if(app_address==DELAY_ADDR)begin
                    if(!native_accept[6])$fatal(1,"wrong owner6 native grant");
                    delay_commands_o<=delay_commands_o+1'b1;
                    if(app_wren)saved_delay<=app_data;else pending_data<=saved_delay;
                end else begin
                    if(!native_accept[8] || app_address<BASE_APP || ((app_address-BASE_APP)>>3)>=BEATS)
                        $fatal(1,"recording native address/owner/allocation boundary");
                    beat=int'((app_address-BASE_APP)>>3);
                    if(32'(app_address)>max_native_address_o)max_native_address_o<=32'(app_address);
                    if(app_wren)begin
                        native_writes_o<=native_writes_o+1'b1;
                        for(integer i=0;i<32;i=i+1)if(!app_mask[i])memory[beat][i*8+:8]<=app_data[i*8+:8];
                    end else pending_data<=memory[beat];
                end
                if(!app_wren)begin read_pending<=1;read_delay<=4'(2+memory_cycles%4);end
            end
        end
    end
    final $display("SHARED_DDR music_commands=%0d delay_commands=%0d recording_writes=%0d cycles=%0d",music_commands_o,delay_commands_o,native_writes_o,memory_cycles);
endmodule
