`timescale 1ns/1ps
module tb_workstation_demo_retirement;
  reg clk=0,rst_n=0,valid=0,write_i=0,stop_request=0;
  reg [11:0] address=0;reg [31:0] data_i=0;
  wire ready,error,record_enable,seal,score_start,score_stop,score_write,stop_done,stop_failed;
  wire [31:0] data_o;
  always #5 clk=~clk;
  gw138k_controlled_services #(.ENABLE_MEDIA_POLICY(1),.LOCAL_RECORD_ENABLE(0),.LOCAL_SCORE_ENABLE(0)) service(
    .clk,.reset_n(rst_n),.command_valid(valid),.command_write(write_i),.command_address(address),.command_data(data_i),.command_strobes(4'hf),
    .command_ready(ready),.response_data(data_o),.response_error(error),.cpu_event_ready(1'b1),
    .panel_event_valid(1'b0),.panel_command(7'd0),.control_state(32'd0),.control_pitch(32'd0),.control_options(32'd0),
    .applied_events(32'd0),.pc_health(32'd0),.held_notes(128'd0),.sample_valid(1'b0),.active_mask(32'd0),
    .deadline_miss(32'd0),.midi_overflow(32'd0),.note_drop(32'd0),.underrun_count(32'd0),.midi_cdc_drop(32'd0),
    .observation_drop(32'd0),.record_drop(32'd0),.record_enable,.record_valid(1'b0),.record_packet(96'd0),
    .score_write,.score_start,.score_stop,.score_running(1'b0),.score_done(1'b0),.led_mask(32'd0),.score_frame(32'd0),
    .media_stop_request_i(stop_request),.media_stop_hold_i(1'b0),.record_storage_reset_ni(rst_n),.record_seal_request_o(seal),
    .record_seal_done_i(1'b0),.record_seal_failed_i(1'b0),.record_start_ready_i(1'b0),
    .record_object_id_i(32'd0),.record_object_rate_i(32'd0),.record_object_epoch_i(32'd0),.record_object_frames_i(32'd0),
    .record_object_status_i(6'd0),.record_object_failure_i(3'd0),.record_seal_status_i(3'd0),.record_seal_count_i(32'd0),
    .score_cancelled_i(1'b0),.score_failed_i(1'b0),.media_stop_done_o(stop_done),.media_stop_failed_o(stop_failed));
  reg sample=0,rate44=0,changed=0,loss=0;reg [31:0] epoch=1;
  wire record_valid,score_running,fft_valid,fft_context,fft_rate;
  wire [95:0] packet;wire [31:0] object_id,fft_epoch,discard;
  integer fft_bins=0,retired_reads=0,retired_writes=0;
  workstation_observation_consumers #(.LOCAL_RECORD_ENABLE(0),.LOCAL_SCORE_ENABLE(0),.ENABLE_MEDIA_POLICY(1)) consumers(
    .clk_i(clk),.rst_ni(rst_n),.frame_valid_i(sample),.frame_44k1_i(rate44),.frame_error_i(1'b0),.stream_change_i(changed),
    .sequence_gap_i(1'b0),.observation_loss_i(loss),.media_switch_busy_i(1'b0),.frame_epoch_i(epoch),.left_i(32'd0),.right_i(32'd0),
    .record_enable_i(1'b1),.record_ready_i(1'b0),.record_valid_o(record_valid),.record_packet_o(packet),
    .fft_valid_o(fft_valid),.fft_context_valid_o(fft_context),.fft_44k1_o(fft_rate),.fft_epoch_o(fft_epoch),.fft_discard_count_o(discard),
    .score_write_i(1'b1),.score_address_i(8'd0),.score_data_i(64'hffffffffffffffff),.score_length_i(9'd256),
    .score_start_i(1'b1),.score_stop_i(1'b0),.score_running_o(score_running),.record_seal_i(1'b1),.record_object_id_o(object_id));
  always @(negedge clk)if(rst_n)begin
    if(fft_valid)begin
      fft_bins=fft_bins+1;
      if(!fft_context || fft_epoch!=epoch || fft_rate!=rate44)$fatal(1,"retirement broke FFT context");
    end
    if(record_valid || score_running || object_id!=0 || packet!=0)$fatal(1,"retired local object/cue resurrected");
    if(record_enable || seal || score_start || score_stop || score_write)$fatal(1,"retired interface issued request");
  end
  task clocks(input integer n);repeat(n)@(negedge clk);endtask
  task access(input bit wr,input [11:0] addr,input bit expect_error);begin
    address=addr;write_i=wr;data_i=1;clocks(1);valid=1;clocks(1);
    if(!ready || error!=expect_error)$fatal(1,"retired access error addr=%h wr=%b",addr,wr);
    if(!wr && addr==8 && data_o!=121)$fatal(1,"retired capability falsely advertised %h",data_o);
    valid=0;clocks(1);
  end endtask
  initial begin
    clocks(4);rst_n=1;clocks(4);access(0,8,0);
    for(integer addr=128;addr<=180;addr=addr+4)begin access(0,12'(addr),1);retired_reads++;access(1,12'(addr),1);retired_writes++;end
    for(integer addr=256;addr<=304;addr=addr+4)begin access(0,12'(addr),1);retired_reads++;access(1,12'(addr),1);retired_writes++;end
    stop_request=1;clocks(1);stop_request=0;
    begin integer waited=0;while(!stop_done)begin clocks(1);waited++;if(waited>10)$fatal(1,"waited for nonexistent local seal");end end
    if(stop_failed)$fatal(1,"empty local media stop failed");
    for(integer i=0;i<600;i=i+1)begin sample=1;clocks(1);sample=0;clocks(63);end
    if(fft_bins<128)$fatal(1,"retirement removed actual FFT");
    loss=1;clocks(1);loss=0;epoch=2;rate44=1;changed=1;sample=1;clocks(1);sample=0;changed=0;clocks(64);
    if(discard==0 || !fft_context || fft_epoch!=2 || !fft_rate)$fatal(1,"FFT context/error tracking removed");
    $display("PASS demo_retirement retired_reads=%0d retired_writes=%0d fft_bins=%0d",retired_reads,retired_writes,fft_bins);$finish;
  end
  initial begin #10000000;$fatal(1,"test watchdog");end
endmodule
