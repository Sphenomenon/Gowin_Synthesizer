`timescale 1ns/1ps
// Boundary-only fixture: native file owner is a deterministic held cursor.
// Actual native SD/FAT/WAV and physical DSP/I2S are tested separately.
module workstation_tf_direct_native_v1 #(
 parameter SPI_CLK_DIV=100,SPI_CLK_DIV_FAST=12,TOKEN_WAIT_CLOCKS=1,WATCHDOG_CLOCKS=1,
 VERIFY_DATA_CRC=0,FAT_SECTOR_CACHE=0,BYTE_DEPTH=16,PCM_DEPTH=16,PREFILL_FRAMES=8
)(input wire clk_i,rst_ni,output wire spi_ssn_o,spi_sck_o,spi_mosi_o,input wire spi_miso_i,
 input wire request_valid_i,output wire request_ready_o,input wire [3:0] track_index_i,
 input wire [31:0] generation_i,input wire [19:0] expected_rate_i,input wire stop_i,pause_i,sample_request_i,
 output reg request_applied_o,output wire request_pending_o,output reg stop_completed_o,output wire stop_failed_o,
 output wire pcm_valid_o,input wire pcm_ready_i,output wire signed [15:0] pcm_left_o,pcm_right_o,output wire pcm_last_o,
 output wire [31:0] generation_o,output wire [19:0] session_rate_o,
 output wire active_o,prefill_ready_o,empty_o,ingress_failed_o,output wire [3:0] ingress_failure_code_o,
 output wire file_error_o,output wire [3:0] file_error_code_o,output wire scan_done_o,output wire [4:0] track_count_o,
 input wire [7:0] name_raddr_i,output wire [7:0] name_rdata_o);
 reg active;reg [15:0] cursor;reg [31:0] generation;reg [19:0] rate;
 assign spi_ssn_o=1;assign spi_sck_o=0;assign spi_mosi_o=0;
 assign request_ready_o=!active;assign request_pending_o=0;assign stop_failed_o=0;
 assign pcm_valid_o=active && !pause_i;assign pcm_left_o=cursor;assign pcm_right_o=16'h8000+cursor;assign pcm_last_o=cursor==9;
 assign generation_o=generation;assign session_rate_o=rate;assign active_o=active;assign prefill_ready_o=active;
 assign empty_o=0;assign ingress_failed_o=0;assign ingress_failure_code_o=0;assign file_error_o=0;assign file_error_code_o=0;
 assign scan_done_o=1;assign track_count_o=2;assign name_rdata_o=0;
 always @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin active<=0;cursor<=0;generation<=0;rate<=0;request_applied_o<=0;stop_completed_o<=0;end
  else begin
   request_applied_o<=0;stop_completed_o<=0;
   if(stop_i)begin active<=0;stop_completed_o<=1;end
   else if(request_valid_i && request_ready_o)begin active<=1;cursor<=0;generation<=generation_i;rate<=expected_rate_i;request_applied_o<=1;end
   else if(pcm_valid_o && pcm_ready_i)begin if(pcm_last_o)active<=0;else cursor<=cursor+1'b1;end
  end
 end
endmodule

module tb_workstation_tf_remote_analysis #(parameter bit LOCAL_NATIVE_HEAD_ENABLE=0,
 parameter bit PARALLEL_STATUS_COMPARE_ENABLE=0);
 reg clk=0,compute=0,reset=0;always #10 clk=!clk;always #6.5 compute=!compute;
 reg mode=0,restart=0,areq=0,acancel=0,astart_ready=1,pcm_ready=1,physical_eos=0;
 reg song_valid=0,service_cancel=0;
 wire service_enable;
 wire astart,avalid,alast,acancel_out,failed,busy,quiet,tfvalid,tfactive,tfbusy;
 wire [31:0] pcm;wire [3:0] failure;
 integer count=0,starts=0,checks=0,play_frames=0;
 workstation_tf_direct_runtime_service #(.REMOTE_ANALYSIS_ENABLE(1),.LOCAL_NATIVE_HEAD_ENABLE(LOCAL_NATIVE_HEAD_ENABLE),
 .PARALLEL_STATUS_COMPARE_ENABLE(PARALLEL_STATUS_COMPARE_ENABLE),.SEPARATE_COMMON_RESET(1),.QUIET_TIMEOUT_CYCLES(80)) dut(
  .rst_ni(reset),.common_reset_ni(reset),.clk_50m_i(clk),.compute_clk_i(compute),
  .mode_i(mode),.run_i(1'b1),.restart_i(restart),.cancel_i(service_cancel),.transport_error_i(1'b0),.track_index_i(4'd0),
  .runtime_valid_i(1'b1),.runtime_44k1_i(1'b0),.runtime_fault_i(1'b0),.runtime_busy_i(1'b0),.runtime_epoch_i(32'd1),
  .sd_miso_i(1'b1),.playlist_name_address_i(8'd0),.busy_50_o(busy),.failed_o(failed),.failure_code_o(failure),.media_quiescent_50_o(quiet),
  .tf_active_o(tfactive),.tf_busy_o(tfbusy),.tf_valid_o(tfvalid),.tf_ready_i(1'b1),
  .analysis_request_i(areq || service_enable),.analysis_cancel_i(acancel),.analysis_start_ready_i(astart_ready),.analysis_start_valid_o(astart),
  .analysis_pcm_valid_o(avalid),.analysis_pcm_last_o(alast),.analysis_pcm_ready_i(pcm_ready),.analysis_pcm_o(pcm),.analysis_cancel_o(acancel_out),
  .physical_eos_i(physical_eos),.physical_quiescent_i(1'b1),.physical_failed_i(1'b0),.physical_abort_i(1'b0),.stop_request_i(1'b0));
 workstation_playback_service #(.MODEL_SETTLE_CYCLES(3),.RECOVERY_TIMEOUT_CYCLES(100)) playback(
  .clk_i(clk),.rst_ni(reset),.model_status_i(4'd14),.tf_mode_i(mode),.tf_restart_i(1'b0),.cancel_i(service_cancel),
  .tf_track_i(4'd0),.song_valid_i(song_valid),.song_track_i(4'd0),.playlist_ready_i(1'b1),.track_count_i(4'd2),
  .card_lost_i(1'b0),.analysis_done_i(1'b0),.analysis_enable_o(service_enable));
 always @(posedge clk)if(reset)begin
  if(astart)starts=starts+1;
  if(avalid && pcm_ready)begin
   if(pcm!={16'h8000+16'(count),16'(count)})$fatal(1,"analysis cursor/order mismatch %0d %h",count,pcm);
   if(alast!=(count==9))$fatal(1,"real LAST mismatch");
   count=count+1;
  end
 end
 always @(posedge compute)if(reset && tfvalid)play_frames=play_frames+1;
 task automatic tick(input integer n);repeat(n)@(negedge clk);endtask
 task automatic request_analysis;
  begin areq=1;tick(1);areq=0;end
 endtask
 task automatic until_idle;
  integer t;begin t=0;while((busy || !quiet) && t<300)begin tick(1);t=t+1;end if(t==300)$fatal(1,"reader failed to release");end
 endtask
 initial begin
  tick(3);reset=1;tick(30);checks=checks+1;
  request_analysis();wait(count==3);@(negedge clk);pcm_ready=0;tick(7);
  if(count!=3 || pcm[15:0]!=3)$fatal(1,"offline cursor advanced during W stall");checks=checks+1;
  pcm_ready=1;wait(count==10);tick(3);until_idle();
  if(starts!=1 || failed || play_frames!=0 || tfactive)$fatal(1,"analysis leaked into playback or lost start");checks=checks+1;
  // Ready cannot remain an unbounded external prerequisite at native launch.
  astart_ready=0;request_analysis();tick(130);until_idle();
  if(!failed || failure!=7 || starts!=1)$fatal(1,"bounded launch timeout missing");checks=checks+1;
  // Sticky old failure cancellation is edge scoped, never a permanent veto.
  acancel=1;tick(3);astart_ready=1;count=0;request_analysis();wait(starts==2);tick(3);
  acancel=0;tick(2);acancel=1;tick(2);until_idle();
  if(!acancel_out && dut.state!=0)$fatal(1,"cancel failed to release native reader");checks=checks+1;
  acancel=0;mode=1;restart=1;tick(1);restart=0;tick(70);
  if(play_frames!=10)$fatal(1,"direct playback regression after analysis %0d",play_frames);checks=checks+1;
  physical_eos=1;tick(2);physical_eos=0;tick(3);
  if(!dut.eof_seen)$fatal(1,"physical EOS no longer authoritative for playback");checks=checks+1;
  mode=0;service_cancel=1;tick(2);service_cancel=0;until_idle();count=0;
  song_valid=1;tick(1);song_valid=0;wait(starts==3);wait(count==10);until_idle();checks=checks+1;
  service_cancel=1;tick(2);service_cancel=0;tick(100);
  if(starts!=3)$fatal(1,"playback cancellation manufactured an analysis launch");checks=checks+1;
  $display("PASS tf_remote_analysis checks=%0d scenarios=5 deterministic_native_cursor=1 actual_SPI_FAT_WAV=0 physical_CDC=0",checks);$finish;
 end
 initial begin #200000;$fatal(1,"timeout");end
endmodule
