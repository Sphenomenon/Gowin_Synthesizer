`timescale 1ns/1ps
// Functional contest witness: live note events -> real HDL synth -> physical
// PT8211 serial pins -> independently reconstructed PCM16. No sample playback.
// This documents the existing PT8211 format, not standard I2S compliance.
module tb_realtime_synth;
  logic clk=0,rst_n=0;
  always #6.510416 clk=~clk; // nominal 76.8 MHz
  logic ev_valid=0;wire ev_ready;logic [17:0] ev=0;
  wire tick,valid;wire signed [31:0] left,right;
  wire [31:0] active,deadline,overflow,drops;wire [127:0] held;
  wire [5:0] count;wire [1:0] mode;wire [2:0] profile;
  wire bck,ws,din,pa,observed;wire [31:0] pair,underrun,frames;
  wire [15:0] gain;wire [2:0] effects;
  gw138k_event_workstation dut(.clk_i(clk),.rst_ni(rst_n),
    .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
    .held_notes_o(held),.applied_events_o(),.pc_overflow_o(),.control_options_o(),.panic_epoch_o(),
    .cpu_event_valid_i(ev_valid),.cpu_event_i(ev),.cpu_event_ready_o(ev_ready),
    .sample_ce_i(tick),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.sample_valid_o(valid),
    .left_o(left),.right_o(right),.synth_valid_o(),.synth_o(),.active_mask_o(active),
    .active_voice_count_o(count),.mode_o(mode),.pitch_q20_o(),.deadline_miss_o(deadline),
    .midi_overflow_o(overflow),.note_drop_o(drops),.clip_o(),.synth_gain_o(gain),.pcm_gain_o(),
    .route_o(),.profile_o(profile),.effect_mask_o(effects),.effect_order_o(),
    .panel_event_valid_o(),.panel_command_o(),.scope_status_o(),.tf_scope_control_o(),
    .delay_mem_clk_i(clk),.delay_mem_rst_ni(rst_n),.delay_dwr_valid_o(),.delay_dwr_data_o(),
    .delay_dwr_pop_i(1'b0),.delay_drd_push_i(1'b0),.delay_drd_data_i(65'd0),.delay_drd_ready_o());
  pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1)) tx(
    .clk(clk),.reset_n(rst_n),.sample_data(left),.sample_right(right),.sample_valid(valid),
    .sample_tick(tick),.hp_bck(bck),.hp_ws(ws),.hp_din(din),.pa_en(pa),
    .underrun_count(underrun),.frame_count(frames),.sample_revision(24'd0),
    .sample_nonzero_voices(active),.trace_dac_done(),.trace_dac_revision(),
    .trace_dac_nonzero_voices(),.sample_trigger_reference(32'd0),.frame_trigger_reference());
  pt8211_observer observer(.clk(clk),.reset_n(rst_n),.bck(bck),.ws(ws),.din(din),
    .frame_reference(32'd0),.pcm_pair(pair),.sample_valid(observed),.trigger_reference());
  integer cycles=0,last_tick=-1,last_observed=-1,max_render=0,render_start=-1;
  integer output_samples=0,pcm_file,base_underruns;
  logic capture=0;
  always @(posedge clk) if(rst_n) begin
    cycles++;
    if(tick) begin
      if(last_tick>=0 && cycles-last_tick!=1600) $fatal(1,"sample tick period");
      last_tick=cycles;render_start=cycles;
    end
    if(valid && render_start>=0) begin
      if(cycles-render_start>max_render)max_render=cycles-render_start;
      if(cycles-render_start>=1600)$fatal(1,"render exceeded frame");
    end
    if(observed) begin
      if(last_observed>=0 && cycles-last_observed!=1600)$fatal(1,"serial frame period");
      last_observed=cycles;
      if(capture) begin
        if(count!=32 || active!=32'hffffffff || effects || dut.scope_enable || dut.tf_scope_control_o[12])
          $fatal(1,"capture is not 32 dry live synthesized voices");
        $fwrite(pcm_file,"%0d %0d\n",$signed(pair[31:16]),$signed(pair[15:0]));
        output_samples++;
      end
    end
    if(deadline || overflow || drops)$fatal(1,"synth health fault %0d %0d %0d",deadline,overflow,drops);
  end
  task automatic send(input integer kind,a,b);
    @(negedge clk);ev={4'(kind),7'(a),7'(b)};ev_valid=1;
    do @(posedge clk);while(!ev_ready);
    @(negedge clk);ev_valid=0;
  endtask
  task automatic samples(input integer n);
    repeat(n) begin @(posedge observed);@(negedge clk);end
  endtask
  initial begin
    pcm_file=$fopen("serial_pcm16.txt","w");if(!pcm_file)$fatal(1,"cannot open PCM capture");
    repeat(6)@(negedge clk);rst_n=1;
    samples(520); // Existing DAC amplifier mute/startup is outside this witness.
    send(2,80,0);wait(mode==0 && !dut.mode_pending); // one sine component per voice
    for(integer n=60;n<92;n++)send(1,n,100);
    wait(count==32);samples(4800); // allow live envelopes to reach sustained level
    if(dut.engine.current_partial_count!=1)$fatal(1,"test requires one component per voice");
    for(integer i=0;i<32;i++)begin
      if(dut.engine.assigned_midi_note[i]!=60+i || dut.engine.envelope_level_q24[i]==0 ||
         dut.engine.slot_mem[i][47:16]==0 || dut.engine.slot_mem[i][15:0]==0)
        $fatal(1,"voice lacks independent note, envelope, step or gain: %0d",i);
      for(integer j=0;j<i;j++)
        if(dut.engine.slot_mem[i][47:16]==dut.engine.slot_mem[j][47:16])$fatal(1,"duplicate frequency");
    end
    base_underruns=underrun;
    @(negedge clk);capture=1;wait(output_samples==32768);@(negedge clk);capture=0;
    $fclose(pcm_file);
    if(underrun!=base_underruns)$fatal(1,"serial underrun during capture");
    // One note release must not change the other 31 envelopes to release.
    send(0,60,0);wait(dut.engine.envelope_state[0]==4);
    samples(2);
    for(integer i=1;i<32;i++)
      if(dut.engine.envelope_state[i]==4 || dut.engine.assigned_midi_note[i]!=60+i)
        $fatal(1,"per-voice release contaminated another voice");
    $display("METRIC voices=32 samples=%0d frame_cycles=1600 max_render_cycles=%0d capture_underruns=0 independent_release=1",output_samples,max_render);
    $display("PASS realtime_synth");$finish;
  end
  initial begin #1000000000;$fatal(1,"realtime witness timeout");end
endmodule
