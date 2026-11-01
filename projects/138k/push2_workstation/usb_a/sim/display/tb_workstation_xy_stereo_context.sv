`timescale 1ns/1ps
// Actual runtime CDC and producer, not a replacement mailbox/model.
module tb_workstation_xy_stereo_context;
 reg source_clk=0,clk=0,rst_n=0,frame_valid=0,vector_mode=0;
 reg [31:0] sequence_number=0,pcm=0;
 always #10 source_clk=~source_clk;
 always #5 clk=~clk;
 wire [31:0] reference_data=32'h10100000+sequence_number;
 wire [31:0] voices=32'h20200000+sequence_number,status=32'h30300000+sequence_number;
 wire [2:0] mask=sequence_number[2:0];wire [5:0] order=sequence_number[5:0];
 wire [31:0] drops;
 reg [204:0] expected[0:8191];
 integer sent=0,received=0,mode_revocations=0,point_checks=0;
 workstation_display_runtime #(.XY_TRACE_ENABLE(1),.XY_STEREO_ENABLE(1)) dut(
  .source_clk_i(source_clk),.source_reset_ni(rst_n),.clk_i(clk),.rst_ni(rst_n),.enabled_i(1'b0),
  .frame_valid_i(frame_valid),.frame_vector_i(vector_mode),.frame_44k1_i(1'b0),.frame_error_i(1'b0),.observation_trusted_i(1'b1),
  .frame_epoch_i(32'd1),.frame_sequence_i(sequence_number),.frame_pcm_i(pcm),.trigger_reference_i(reference_data),
  .active_voices_i(voices),.status_i(status),.effect_mask_i(mask),.effect_order_i(order),.observation_drop_o(drops),
  .memory_status_i(32'd0),.raster_busy_i(1'b0),.raster_start_i(1'b0),.raster_allowed_o(),.current_image_o(),.summary_publish_o(),
  .writer_busy_o(),.writer_done_o(),.writer_initialized_o(),.writer_req_o(),.writer_ready_i(1'b0),.writer_address_o(),.writer_data_o(),
  .reader_busy_o(),.reader_done_o(),.reader_valid_o(),.reader_fault_o(),.reader_req_o(),.reader_ready_i(1'b0),.reader_address_o(),
  .reader_response_i(1'b0),.reader_data_i(256'd0),.render_read_enable_i(1'b0),.render_wave_address_i(9'd0),
  .render_spectrum_column_i(9'd0),.render_image_address_i(16'd0),.render_wave_data_o(),.render_image_hit_o(),
  .render_spectrum_left_o(),.render_spectrum_right_o(),.render_meta_o(),.render_analysis_sequence_o(),.render_analysis_skipped_o(),
  .render_stereo_peaks_o(),.render_image_gain_o(),.render_analysis_valid_o(),.render_frame_sequence_o(),.render_sample_rate_o(),
  .render_epoch_o(),.writer_diagnostic_o(),.reader_diagnostic_o());
 task clocks(input integer count);repeat(count)@(negedge clk);endtask
 task send(input bit selected_vector,input integer left,input integer right);begin
  @(negedge source_clk);sequence_number=32'(sent);vector_mode=selected_vector;pcm={16'(left),16'(right)};
  expected[sent]={selected_vector,1'b1,1'b0,32'd1,32'(sent),1'b0,{16'(left),16'(right)},32'h10100000+32'(sent),32'h20200000+32'(sent),32'h30300000+32'(sent),3'(sent),6'(sent)};
  frame_valid=1;sent=sent+1;@(negedge source_clk);frame_valid=0;vector_mode=!selected_vector;repeat(7)@(negedge source_clk);
 end endtask
 task block_samples(input bit mode,input integer count);integer left,right;begin
  for(integer i=0;i<count;i=i+1)begin
   left=$rtoi(12000.0*$sin(6.283185307179586*7.0*i/2048.0));
   right=$rtoi(8000.0*$cos(6.283185307179586*5.0*i/2048.0));send(mode,left,right);
  end
 end endtask
 integer left_value,right_value,px,py,shift,side,mid;
 always @(negedge clk)if(rst_n)begin
  if(dut.tuple_valid)begin
   if(dut.tuple_sequence>=32'(sent) || dut.destination_tuple!==expected[dut.tuple_sequence] || dut.tuple_vector!==expected[dut.tuple_sequence][204])$fatal(1,"stereo 205bit tuple torn seq=%0d",dut.tuple_sequence);
   received=received+1;
   if(dut.producer.have_context && dut.tuple_vector!=dut.producer.vector_xy_q)begin
    if(!dut.producer.context_break || dut.source_valid || dut.producer.good_sample)$fatal(1,"stereo mode change admitted old/mixed context");
    mode_revocations=mode_revocations+1;
   end
  end
  if(dut.producer.analysis.state==dut.producer.analysis.IMAGE_WRITE)begin
   left_value=integer'($signed(dut.producer.analysis.captured[31:16]));
   right_value=integer'($signed(dut.producer.analysis.captured[15:0]));
   shift=9-integer'(dut.producer.analysis.work_image_gain);
   side=dut.producer.vector_xy_q ? left_value:(right_value-left_value)>>>1;
   mid=dut.producer.vector_xy_q ? right_value:(left_value+right_value)>>>1;
   px=128+(side>>>shift);py=128-(mid>>>shift);
   if(px<0)px=0;if(px>255)px=255;if(py<0)py=0;if(py>255)py=255;
   if(dut.producer.analysis.image_x!==8'(px) || dut.producer.analysis.image_y!==8'(py))$fatal(1,"stereo producer mapped wrong context");
   point_checks=point_checks+1;
  end
 end
 reg [31:0] old_generation;
 initial begin
  clocks(4);rst_n=1;clocks(30);
  send(0,0,0);block_samples(0,2300);wait(dut.producer.analysis_ready);clocks(5);
  if(!dut.producer.analysis.connected_xy.trace.history_valid || !dut.source_valid)$fatal(1,"stereo history not established");
  old_generation=dut.source_generation;send(1,12000,8000);clocks(3);
  if(dut.source_generation!=old_generation+1 || dut.producer.analysis_ready || dut.producer.analysis.front_valid || dut.producer.analysis.connected_xy.trace.history_valid || !dut.producer.vector_xy_q)$fatal(1,"stereo completed window/history survived vector switch");
  block_samples(1,1024);clocks(3);
  if(dut.producer.analysis.u_capture.index<1000 || dut.producer.analysis_ready)$fatal(1,"stereo partial capture not armed");
  old_generation=dut.source_generation;send(0,-32768,32767);clocks(3);
  if(dut.source_generation!=old_generation+1 || dut.producer.analysis.u_capture.index!=0 || dut.producer.analysis.connected_xy.trace.history_valid || dut.producer.vector_xy_q)$fatal(1,"stereo partial vector block survived normal switch");
  block_samples(0,2300);wait(dut.producer.analysis_ready);clocks(5);
  if(!dut.producer.analysis.connected_xy.trace.history_valid || point_checks<4096)$fatal(1,"stereo analysis did not recover after mode switch");
  // Toggle the committed selector alongside every real held-word payload.
  // Unsampled live selector changes must remain outside the held payload.
  for(integer i=0;i<64;i=i+1)begin send(1'(i),i*31,-i*17);if(i%3==0)@(negedge source_clk);end
  clocks(30);
  if(drops!=0 || received!=sent || mode_revocations<64)$fatal(1,"stereo tuple/revocation coverage incomplete sent=%0d received=%0d mode=%0d drops=%0d",sent,received,mode_revocations,drops);
  $display("PASS xy_stereo_context tuples=%0d mode_revocations=%0d points=%0d completed_history_revoke=1 partial_capture_revoke=1 recovery=1 actual_runtime_cdc=1",received,mode_revocations,point_checks);$finish;
 end
 initial begin #100000000;$fatal(1,"stereo context watchdog sent=%0d received=%0d",sent,received);end
endmodule
