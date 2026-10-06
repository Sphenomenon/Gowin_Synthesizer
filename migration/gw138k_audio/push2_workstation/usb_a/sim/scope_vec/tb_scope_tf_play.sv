`timescale 1ns/1ps
// Real bridge/FIFO, serial DAC pins and display mailbox. Card/DDR endpoint is
// procedural, so this validates entry/transport/injection, not SD hardware.
module tb_scope_tf_play;
 reg aclk=0,clk=0,rst_n=0,mode=0,run=0,manual=0,live=0;
 wire signed [31:0] left,right;
 wire active,source_active,tick,bck,ws,din,pa,selected,switching;
 wire tbck,tws,tdin,tpa,sbck,sws,sdin,spa,stick;
 wire [19:0] rate;
 wire analysis_valid,observed_valid,display_valid;
 wire [31:0] observed,display_pcm,observed_reference,display_reference,display_voices,display_health;
 reg check_tf=0;
 integer samples=0,analysed=0,paused=0,after_pause,paused_index;
 always #6.5 aclk=~aclk;
 always #10 clk=~clk;
 tf_workstation_audio_bridge bridge(.clk_50m(clk),.reset_n(rst_n),.audio_clk(aclk),.audio_reset_n(rst_n),
  .memory_clk(clk),.memory_reset_n(rst_n),.memory_ready(1'b1),.restart(1'b0),.track_index(4'd0),
  .sd_miso(1'b1),.sd_cs_n(),.sd_sck(),.sd_mosi(),.sample_ce(tick),.pcm_left(left),.pcm_right(right),
  .pcm_active(active),.source_active(source_active),.sample_rate_hz(rate),.format_ready(),.unsupported(),
  .ddr_error(),.file_size(),.track_count(),.playback_hold_i(manual && (!mode || !run)),
  .analysis_hold_i(!mode),.analysis_enable_i(!mode),.analysis_pcm_ready_i(1'b0),
  .card_lost(),.hotplug_debug(),.playlist_ready(),.playlist_name_addr(8'd0),.playlist_name_data(),
        .analysis_pcm_end(),.analysis_pcm_valid(analysis_valid),.analysis_pcm_left(),.analysis_pcm_right(),.analysis_sample_rate(),
  .ddr_valid(),.ddr_write(),.ddr_address(),.ddr_data(),.ddr_ready(1'b0),.ddr_response(1'b0),.ddr_response_data(256'd0));
 tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) tdac(
  .clk(aclk),.reset_n(rst_n),.sample_data(mode && !run ? 32'sd0 : left),
  .sample_right(mode && !run ? 32'sd0 : right),.sample_valid(active || (mode && !run)),.rate_hz(rate),
  .sample_tick(tick),.hp_bck(tbck),.hp_ws(tws),.hp_din(tdin),.pa_en(tpa),.underrun_count(),.frame_count(),
  .sample_revision(24'd0),.sample_nonzero_voices(32'd0),.trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
  .sample_trigger_reference(32'd0),.frame_trigger_reference());
 pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1)) sdac(.clk(aclk),.reset_n(rst_n),
  .sample_data(32'sh12340000),.sample_right(32'shfedc0000),.sample_valid(1'b1),.sample_tick(stick),
  .hp_bck(sbck),.hp_ws(sws),.hp_din(sdin),.pa_en(spa),.underrun_count(),.frame_count(),
  .sample_revision(24'd0),.sample_nonzero_voices(32'd0),.trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
  .sample_trigger_reference(32'd0),.frame_trigger_reference());
 scope_dac_select select_dac(.clk_i(aclk),.rst_ni(rst_n),.scope_enable_i(live),.tf_source_active_i(mode || (!manual && source_active)),
  .synth_frame_tick_i(stick),.tf_frame_tick_i(tick),.synth_bck_i(sbck),.synth_ws_i(sws),.synth_din_i(sdin),.synth_pa_i(spa),
  .tf_bck_i(tbck),.tf_ws_i(tws),.tf_din_i(tdin),.tf_pa_i(tpa),.hp_bck_o(bck),.hp_ws_o(ws),.hp_din_o(din),
  .pa_en_o(pa),.tf_selected_o(selected),.switching_o(switching));
 pt8211_observer observe(.clk(aclk),.reset_n(rst_n && !switching),.bck(bck),.ws(ws),.din(din),
  .frame_reference(selected ? 32'd0 : 32'h1234ab00),.pcm_pair(observed),
  .sample_valid(observed_valid),.trigger_reference(observed_reference));
 gw138k_stream_cdc #(.WIDTH(128)) display_cdc(.reset_n(rst_n),.source_clk(aclk),.destination_clk(clk),
  .source_valid(observed_valid && !switching),
  .source_data({observed,observed_reference,selected ? 32'd0 : 32'hfedc1234,32'h00120034}),
  .drop_count(),.destination_valid(display_valid),
  .destination_data({display_pcm,display_reference,display_voices,display_health}));
 always @(posedge clk) begin
  if(analysis_valid) analysed<=analysed+1;
  if(display_valid) begin
   samples<=samples+1;
   if(display_health!=32'h00120034) $fatal(1,"health tuple corrupt");
   if(display_pcm==32'h1234fedc) begin
    if(display_reference!=32'h1234ab00 || display_voices!=32'hfedc1234)
     $fatal(1,"synth frame metadata detached from physical PCM");
   end else if(display_reference!=0 || display_voices!=0)
    $fatal(1,"TF frame has stale synth metadata");
   if(check_tf && display_pcm[31:16]!=(~display_pcm[15:0])) $fatal(1,"TF stereo pair swapped/corrupt");
   if(paused) begin if(display_pcm!=0) $fatal(1,"paused DAC/display must be silent");paused_index<=paused_index+1;end
  end
 end
 initial begin
  paused_index=0;repeat(10) @(negedge clk);rst_n=1;
  repeat(200000) @(negedge clk);if(bridge.u_path.index!=0) $fatal(1,"NN backpressure baseline");
  mode=1;manual=1;run=1;repeat(10000) @(negedge clk);check_tf=1;
  repeat(300000) @(negedge clk);if(!selected || samples<100 || analysed!=0 || bridge.u_path.index<100) $fatal(1,"playback blocked by NN");
  check_tf=0;run=0;repeat(20000) @(negedge clk);paused=1;after_pause=bridge.u_path.index;
  repeat(80000) @(negedge clk);if(bridge.u_path.index!=after_pause || paused_index<50) $fatal(1,"pause advanced decoder cursor");
  paused=0;run=1;repeat(10000) @(negedge clk);check_tf=1;repeat(100000) @(negedge clk);if(bridge.u_path.index<=after_pause) $fatal(1,"resume");
  mode=0;check_tf=0;run=0;repeat(20000) @(negedge clk);if(selected || display_pcm!=32'h1234fedc) $fatal(1,"exit TF fallback remains selected");
  mode=1;run=1;live=1;repeat(20000) @(negedge clk);if(selected) $fatal(1,"live source priority");
  $display("M tf_play_display_pairs %0d",samples);$display("M tf_pause_zero_pairs %0d",paused_index);
  $display("PASS scope_tf_play");$finish;
 end
 initial begin #30000000;$fatal(1,"timeout");end
endmodule
