`timescale 1ns/1ps
module ae350_ble_business_cosim #(
 parameter integer CAPACITY_FRAMES=16384,
 parameter bit FAST_CAPTURE=0,
 parameter bit DUAL_RATE_RECORDING=0,
 parameter [28:0] BASE_APP=0
)(
 input wire clk,resetn,owner_resetn,enable,pcm_run,test_native_pause,
 input wire [7:0] test_source_format,
 input wire test_source_ready,test_source_fault,
 input wire psel,penable,pwrite,input wire [11:0] paddr,
 input wire [31:0] pwdata,input wire [3:0] pstrb,
 output wire pready,pslverr,output wire [31:0] prdata,
 input wire fragment_write,input wire [4:0] fragment_addr,input wire [7:0] fragment_data,
 input wire fragment_start,input wire [4:0] fragment_length,
 output wire fragment_done,output wire [7:0] fragment_error,
 output wire response_valid,output wire [6:0] response_length,
 input wire [6:0] response_addr,output wire [7:0] response_data,input wire response_consume,
 output wire transfer_valid,output wire [12:0] transfer_length,
 input wire [12:0] transfer_addr,output wire [7:0] transfer_data,input wire transfer_consume,
 input wire seal_hold,seal_request,
 input wire [31:0] test_time_bias,
 input wire [8:0] test_att_limit,
 output wire [31:0] elapsed_ms_o,
 output wire transfer_compact,transfer_bulk,transfer_direct,
 output wire seal_ready,seal_done,seal_failed,
 output wire [2:0] capture_phase,
 output wire [3:0] engine_phase,
 output wire [2:0] codec_phase,
 output wire [3:0] fetch_debug,
 output wire [31:0] object_id,frames,record_state,
 output wire [31:0] native_writes,max_native_address,native_committed,
 output wire [31:0] competing_music_commands,competing_delay_commands,
 output wire source_pcm_valid_o
);
assign engine_phase=endpoint.recording.state;
assign codec_phase=endpoint.recording.encoder.phase;
assign fetch_debug={raw_fetch_valid_o,raw_fetch_ready_i,raw_fetch_done_i,raw_cache_valid_i};
wire raw_start_valid_o;
wire raw_start_ready_i,raw_start_done_i;
wire raw_clear_valid_o;
wire raw_clear_ready_i,raw_clear_done_i;
wire raw_capture_valid_o;
wire [31:0] raw_capture_index_o,raw_capture_pcm_o;
wire raw_capture_ready_i;
wire raw_close_valid_o;
wire raw_close_ready_i,raw_drained_i,raw_fault_i;
wire raw_object_fault_i,raw_channel_fault_i;
wire [3:0] raw_failure_code_i;
wire [31:0] raw_accepted_frames_i,raw_committed_frames_i;
wire raw_fetch_valid_o;
wire raw_fetch_ready_i;
wire [31:0] raw_fetch_offset_o;
wire [13:0] raw_fetch_length_o;
wire raw_fetch_done_i,raw_fetch_fault_i,raw_cache_valid_i;
wire [31:0] raw_sample_addr_o;
wire [31:0] raw_sample_word_i;

wire command_reset,command_valid,command_ready,command_write,response_error;
wire [11:0] command_address;wire [31:0] command_data,bus_response_data;
wire [3:0] command_strobes;
gw138k_apb_cdc bus_bridge(.reset_n(owner_resetn && resetn),.pclk(clk),.audio_clk(clk),
 .psel(psel),.penable(penable),.pwrite(pwrite),.paddr(paddr),.pwdata(pwdata),.pstrb(pstrb),
 .pready(pready),.pslverr(pslverr),.prdata(prdata),.command_reset_n(command_reset),
 .command_valid(command_valid),.command_ready(command_ready),.command_write(command_write),
 .command_address(command_address),.command_data(command_data),.command_strobes(command_strobes),
 .response_data(bus_response_data),.response_error(response_error));
reg [31:0] phase=0,ms_count=0,ms_divider=0;
assign elapsed_ms_o=ms_count+test_time_bias;
wire [31:0] fixture_rate=DUAL_RATE_RECORDING && test_source_format==2 ? 32'd44100:32'd48000;
wire tick=FAST_CAPTURE ? phase[2:0]==7 : phase+fixture_rate>=32'd50000000;
wire test_pcm_valid;
assign source_pcm_valid_o=test_pcm_valid;
wire [31:0] test_pcm_pair;
reg [31:0] rate_source_sequence;
always @(posedge clk)begin
 if(!resetn || raw_start_done_i)rate_source_sequence<=0;
 else if(tick && pcm_run)rate_source_sequence<=rate_source_sequence+1'b1;
end
`ifdef TASK3_SHARED_RECORD_DDR
// Advance the source independently of the recorder. A missed delivery must
// change the sealed bytes/CRC instead of silently repeating its frame index.
reg [31:0] source_sequence;
always @(posedge clk)begin
 if(!resetn || raw_start_done_i)source_sequence<=0;
 else if(tick && pcm_run)source_sequence<=source_sequence+1'b1;
end
assign test_pcm_pair=32'h9e370b5a ^ (source_sequence*32'h0010203);
`ifdef TASK3_SHARED_DROP_PCM
assign test_pcm_valid=tick && pcm_run && source_sequence!=17000;
`else
assign test_pcm_valid=tick && pcm_run;
`endif
`else
assign test_pcm_valid=tick && pcm_run;
assign test_pcm_pair=DUAL_RATE_RECORDING ? 32'h9e370b5a ^ (rate_source_sequence*32'h0010203) :
    FAST_CAPTURE ? 32'h9e370b5a ^ (frames*32'h0010203) : 32'h22221111;
`endif
always @(posedge clk)if(!resetn)begin phase<=0;ms_count<=0;ms_divider<=0;end
else begin
 phase<=FAST_CAPTURE ? phase+1'b1 : tick ? phase+fixture_rate-32'd50000000:phase+fixture_rate;
 if(ms_divider==49999)begin ms_divider<=0;ms_count<=ms_count+1'b1;end else ms_divider<=ms_divider+1'b1;
end
ble_protocol_command #(
`ifdef WORKSTATION_SINGLE_BLE_RECORDING
 .SINGLE_BLE_RECORDING(1),
`endif
`ifdef TASK3_RECORD_FORMAT_TEST
 .DUAL_RATE_RECORDING(DUAL_RATE_RECORDING),
`endif
 .EXTERNAL_PCM(1),.CAPACITY_FRAMES(CAPACITY_FRAMES),.EXTERNAL_SEAL_PROTOCOL(1),
 .EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(5000000)) endpoint(
 .clk(clk),.resetn(resetn),.enable(enable),
 .business_owner_reset_ni(command_reset),.business_command_valid_i(command_valid),
 .business_command_write_i(command_write),.business_command_address_i(command_address),
 .business_command_data_i(command_data),.business_command_strobes_i(command_strobes),
 .business_command_ready_o(command_ready),.business_response_error_o(response_error),
 .business_response_data_o(bus_response_data),
 .pcm_valid_i(test_pcm_valid),.source_ready_i(DUAL_RATE_RECORDING ? test_source_ready:1'b1),
 .source_fault_i(DUAL_RATE_RECORDING && test_source_fault),
`ifdef TASK3_RECORD_FORMAT_TEST
 .source_format_i(test_source_format),
`endif
 .pcm_pair_i(test_pcm_pair),
 .boot_id(64'h1122334455667788),.att_value_limit(test_att_limit),.boot_valid(1'b1),
 .response_subscribed(1'b1),.control_open(1'b1),.recording_enable(1'b1),.transfer_subscribed(1'b1),
 .elapsed_ms(ms_count+test_time_bias),.fragment_write(fragment_write),.fragment_addr(fragment_addr),.fragment_data(fragment_data),
 .fragment_start(fragment_start),.fragment_length(fragment_length),.busy(),.fragment_done(fragment_done),.fragment_error(fragment_error),
 .response_valid(response_valid),.response_length(response_length),.response_addr(response_addr),.response_data(response_data),
 .response_consume(response_consume),.transfer_valid(transfer_valid),.transfer_compact(transfer_compact),.transfer_bulk(transfer_bulk),.transfer_direct(transfer_direct),
 .response_is_data(),.transfer_length(transfer_length),.transfer_addr(transfer_addr),.transfer_data(transfer_data),
 .transfer_consume(transfer_consume),.summary_latch(1'b0),.summary(),.session_active(),.accepted_count(),.crc_reject_count(),
 .seal_hold_i(seal_hold),.seal_request_i(seal_request),.seal_ready_o(seal_ready),.seal_pending_o(),
 .seal_done_o(seal_done),.seal_failed_o(seal_failed),.seal_failure_code_o(),
 .seal_record_state_o(),.seal_recording_id_o(),.seal_frames_o(),.seal_crc_o(),
        .raw_start_valid_o(raw_start_valid_o),
        .raw_start_ready_i(raw_start_ready_i),
        .raw_start_done_i(raw_start_done_i),
        .raw_clear_valid_o(raw_clear_valid_o),
        .raw_clear_ready_i(raw_clear_ready_i),
        .raw_clear_done_i(raw_clear_done_i),
        .raw_capture_valid_o(raw_capture_valid_o),
        .raw_capture_index_o(raw_capture_index_o),
        .raw_capture_pcm_o(raw_capture_pcm_o),
        .raw_capture_ready_i(raw_capture_ready_i),
        .raw_close_valid_o(raw_close_valid_o),
        .raw_close_ready_i(raw_close_ready_i),
        .raw_drained_i(raw_drained_i),
        .raw_fault_i(raw_fault_i),
        .raw_object_fault_i(raw_object_fault_i),
        .raw_channel_fault_i(raw_channel_fault_i),
        .raw_failure_code_i(raw_failure_code_i),
        .raw_accepted_frames_i(raw_accepted_frames_i),
        .raw_committed_frames_i(raw_committed_frames_i),
        .raw_fetch_valid_o(raw_fetch_valid_o),
        .raw_fetch_ready_i(raw_fetch_ready_i),
        .raw_fetch_offset_o(raw_fetch_offset_o),
        .raw_fetch_length_o(raw_fetch_length_o),
        .raw_fetch_done_i(raw_fetch_done_i),
        .raw_fetch_fault_i(raw_fetch_fault_i),
        .raw_cache_valid_i(raw_cache_valid_i),
        .raw_sample_addr_o(raw_sample_addr_o),
        .raw_sample_word_i(raw_sample_word_i));
assign capture_phase=endpoint.recording.capture_state;
assign object_id=endpoint.recording_id,frames=endpoint.recorded_frames,record_state={24'd0,endpoint.record_state};
assign native_committed=raw_committed_frames_i;
`ifdef TASK3_SHARED_RECORD_DDR
ae350_ble_shared_ddr_fixture #(.CAPACITY_FRAMES(CAPACITY_FRAMES),.BASE_APP(BASE_APP)) backing(
        .music_commands_o(competing_music_commands),.delay_commands_o(competing_delay_commands),
`else
assign competing_music_commands=0,competing_delay_commands=0;
ble_raw_ddr_fixture #(.CAPACITY_FRAMES(CAPACITY_FRAMES),.BASE_APP(BASE_APP)) backing(
`endif
        .native_writes_o(native_writes),.max_native_address_o(max_native_address),
        .clk(clk),.resetn(resetn),.native_pause(test_native_pause),        .raw_start_valid_o(raw_start_valid_o),
        .raw_start_ready_i(raw_start_ready_i),
        .raw_start_done_i(raw_start_done_i),
        .raw_clear_valid_o(raw_clear_valid_o),
        .raw_clear_ready_i(raw_clear_ready_i),
        .raw_clear_done_i(raw_clear_done_i),
        .raw_capture_valid_o(raw_capture_valid_o),
        .raw_capture_index_o(raw_capture_index_o),
        .raw_capture_pcm_o(raw_capture_pcm_o),
        .raw_capture_ready_i(raw_capture_ready_i),
        .raw_close_valid_o(raw_close_valid_o),
        .raw_close_ready_i(raw_close_ready_i),
        .raw_drained_i(raw_drained_i),
        .raw_fault_i(raw_fault_i),
        .raw_object_fault_i(raw_object_fault_i),
        .raw_channel_fault_i(raw_channel_fault_i),
        .raw_failure_code_i(raw_failure_code_i),
        .raw_accepted_frames_i(raw_accepted_frames_i),
        .raw_committed_frames_i(raw_committed_frames_i),
        .raw_fetch_valid_o(raw_fetch_valid_o),
        .raw_fetch_ready_i(raw_fetch_ready_i),
        .raw_fetch_offset_o(raw_fetch_offset_o),
        .raw_fetch_length_o(raw_fetch_length_o),
        .raw_fetch_done_i(raw_fetch_done_i),
        .raw_fetch_fault_i(raw_fetch_fault_i),
        .raw_cache_valid_i(raw_cache_valid_i),
        .raw_sample_addr_o(raw_sample_addr_o),
        .raw_sample_word_i(raw_sample_word_i));
endmodule
`timescale 1ns/1ps
module ble_raw_ddr_fixture #(
    parameter integer CAPACITY_FRAMES=16384,
    parameter [28:0] BASE_APP=0
)(input wire clk,resetn,native_pause,
    output reg [31:0] native_writes_o,max_native_address_o,
    // clk / clk_i raw storage only; object/task/CRC/wire ownership stays here.
    input wire raw_start_valid_o,
    output wire raw_start_ready_i,raw_start_done_i,
    input wire raw_clear_valid_o,
    output wire raw_clear_ready_i,raw_clear_done_i,
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
    reg memory_clk=0;always #7 memory_clk=~memory_clk;
    wire slot_valid,slot_ready,native_accept,write_enable;
    wire [28:0] address;wire [255:0] write_data;wire [31:0] mask;
    reg response=0;reg [255:0] response_data=0;
    workstation_ble_raw_ddr_store #(.CAPACITY_FRAMES(CAPACITY_FRAMES),.BASE_APP(BASE_APP)) store(
        .clk_i(clk),.memory_clk_i(memory_clk),.rst_ni(resetn),.start_valid_i(raw_start_valid_o),.start_ready_o(raw_start_ready_i),.start_done_o(raw_start_done_i),.clear_valid_i(raw_clear_valid_o),.clear_ready_o(raw_clear_ready_i),.clear_done_o(raw_clear_done_i),.capture_valid_i(raw_capture_valid_o),.capture_index_i(raw_capture_index_o),.capture_pcm_i(raw_capture_pcm_o),.capture_ready_o(raw_capture_ready_i),.close_valid_i(raw_close_valid_o),.close_ready_o(raw_close_ready_i),.drained_o(raw_drained_i),.fault_o(raw_fault_i),.object_fault_o(raw_object_fault_i),.channel_fault_o(raw_channel_fault_i),.failure_code_o(raw_failure_code_i),.accepted_frames_o(raw_accepted_frames_i),.committed_frames_o(raw_committed_frames_i),.fetch_valid_i(raw_fetch_valid_o),.fetch_ready_o(raw_fetch_ready_i),.fetch_offset_i(raw_fetch_offset_o),.fetch_length_i(raw_fetch_length_o),.fetch_done_o(raw_fetch_done_i),.fetch_fault_o(raw_fetch_fault_i),.cache_valid_o(raw_cache_valid_i),.sample_addr_i(raw_sample_addr_o),.sample_word_o(raw_sample_word_i),
        .slot_valid_o(slot_valid),.slot_ready_i(slot_ready),.native_accept_i(native_accept),.ddr_write_o(write_enable),
        .ddr_address_o(address),.ddr_data_o(write_data),.ddr_mask_o(mask),.read_response_i(response),.read_data_i(response_data),
        .transport_fault_i(1'b0),.native_protocol_fault_o());
    reg submitted=0,read_pending=0,write_q=0,native=0;
    reg [28:0] address_q=0,read_address_q=0;
    reg [255:0] data_q=0;reg [31:0] mask_q=0;
    integer delay=0,read_delay=0,i;
    localparam integer BEATS=(CAPACITY_FRAMES+7)/8;
    reg [255:0] memory[0:BEATS-1];
    assign slot_ready=!submitted && !read_pending;
    assign native_accept=native;
    always @(negedge memory_clk)begin
        native=resetn && submitted && delay==0 && !native_pause;
        response=resetn && read_pending && read_delay==0;
        response_data=read_pending ? memory[(read_address_q-BASE_APP)>>3] : 256'd0;
    end
    always @(posedge memory_clk or negedge resetn)begin
        if(!resetn)begin submitted<=0;read_pending<=0;delay<=0;read_delay<=0;native_writes_o<=0;max_native_address_o<=0;end
        else begin
            if(slot_valid && slot_ready)begin
                if(address[2:0]!=0 || address<BASE_APP || ((address-BASE_APP)>>3)>=BEATS)
                    $fatal(1,"recording native byte/word/allocation boundary");
                submitted<=1;address_q<=address;write_q<=write_enable;data_q<=write_data;mask_q<=mask;delay<=2;
            end
            if(submitted && delay>0)delay<=delay-1;
            if(native)begin
                submitted<=0;
                if(address_q>max_native_address_o)max_native_address_o<=address_q;
                if(write_q)begin
                    native_writes_o<=native_writes_o+1'b1;
                    for(i=0;i<32;i=i+1)if(!mask_q[i])memory[(address_q-BASE_APP)>>3][i*8+:8]<=data_q[i*8+:8];end
                else begin read_pending<=1;read_address_q<=address_q;read_delay<=3;end
            end
            if(read_pending && read_delay>0)read_delay<=read_delay-1;
            if(response)read_pending<=0;
        end
    end
endmodule
