`timescale 1ns/1ps
module tb_workstation_demo_d_only;
`include "sim/audio/fixtures/d_process_before_exact_mask.svh"
  reg clk=0,mclk=0,rst_n=0,mrst_n=0,run_memory=1;
  always #7 clk=~clk;
  always #10 if(run_memory)mclk=~mclk;
  reg request=0,rate=0,event_valid=0,config_valid=0,config_rate=0,history_clear=0,hold_fence=0;
  reg [17:0] event_data=0;
  reg signed [31:0] pcm_l=0,pcm_r=0;
  wire ready,done,error,busy,sample_ce,event_ready,config_ready,config_applied,history_ready,history_done,quiet,fault,applied_rate;
  wire signed [31:0] left_o,right_o;
  wire [127:0] held;
  wire [31:0] active,applied,deadline,note_drops,unsupported,duplicates;
  wire [9:0] epoch;
  wire muted;
  wire [1:0] mode;wire [31:0] options,effect_state;wire [2:0] mask;
  wire dwr_valid,dwr_pop,drd_push,drd_ready,ddr_req,ddr_write,ddr_response,dma_fault,audio_hb,memory_hb;
  wire [64:0] dwr_data,drd_data;
  wire [28:0] ddr_addr;
  wire [255:0] ddr_wdata,ddr_rdata;
  workstation_audio_render_service #(.RUNTIME_RATE_ENABLE(1),.RUNTIME_EFFECTS_ENABLE(1),.SYNTH_ENGINES_ENABLE(0),.D_ONLY_ENABLE(1)) dut(
      .clk_i(clk),.rst_ni(rst_n),.render_request_i(request),.render_44k1_i(rate),
      .render_ready_o(ready),.render_done_o(done),.render_error_o(error),.render_left_o(left_o),.render_right_o(right_o),
      .render_busy_o(busy),.sample_ce_o(sample_ce),.rejected_request_count_o(),.unsupported_rate_count_o(unsupported),
      .cancelled_response_count_o(),.drained_result_count_o(),
      .config_valid_i(config_valid),.config_rate_44100_i(config_rate),.history_clear_i(history_clear),
      .config_ready_o(config_ready),.config_applied_o(config_applied),.history_ready_o(history_ready),.history_done_o(history_done),
      .quiescent_o(quiet),.fault_o(fault),.applied_rate_44100_o(applied_rate),
      .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
      .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(event_ready),
      .pcm_left_i(pcm_l),.pcm_right_i(pcm_r),.held_notes_o(held),.applied_events_o(applied),
      .panic_epoch_o(epoch),.panic_muted_o(muted),.active_mask_o(active),.mode_o(mode),.control_options_o(options),.effect_mask_o(mask),.effect_state_o(effect_state),
      .deadline_miss_o(deadline),.note_drop_o(note_drops),.delivery_duplicate_count_o(duplicates),
      .delay_mem_clk_i(mclk),.delay_mem_rst_ni(mrst_n),.delay_dwr_valid_o(dwr_valid),.delay_dwr_data_o(dwr_data),
      .delay_dwr_pop_i(dwr_pop),.delay_drd_push_i(drd_push),.delay_drd_data_i(drd_data),.delay_drd_ready_o(drd_ready),
      .delay_peer_heartbeat_i(memory_hb),.delay_dma_fault_i(dma_fault),.delay_heartbeat_o(audio_hb));
  workstation_runtime_delay_ddr_dma dma(
      .clk_i(mclk),.rst_ni(mrst_n),.dwr_valid_i(dwr_valid),.dwr_data_i(dwr_data),.dwr_pop_o(dwr_pop),
      .drd_push_o(drd_push),.drd_data_o(drd_data),.drd_ready_i(drd_ready),.ddr_req_o(ddr_req),
      .ddr_write_o(ddr_write),.ddr_address_o(ddr_addr),.ddr_data_o(ddr_wdata),.ddr_mask_o(),
      .ddr_ready_i(1'b1),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_rdata),.debug_status_o(),
      .flush_done_o(),.fault_o(dma_fault),.applied_rate_44100_o(),.applied_transaction_o(),
      .peer_heartbeat_i(audio_hb),.heartbeat_o(memory_hb));
  runtime_effects_memory_model memory_model(.clk(mclk),.rst_n(mrst_n),.req(ddr_req),.write_i(ddr_write),
      .ready_i(1'b1),.hold_fence,.address_i(ddr_addr),.data_i(ddr_wdata),.is_fence(dma.state==8),
      .response_o(ddr_response),.data_o(ddr_rdata));
  integer frames=0,events=0,waited=0,max_render_cycles=0,pitch_fd=0,pitch_captures=0,pitch_clear_checks=0,pitch_cancels=0,responses=0;
  reg last_error;
  reg signed [31:0] last_left,last_right;
  string pitch_pcm_path;
  always @(posedge clk)if(rst_n && done)begin responses=responses+1;last_error=error;last_left=left_o;last_right=right_o;end
  integer old_function_snapshots=0,delayed_parameter_frames=0;
  reg signed [31:0] expected_capture_l,expected_capture_r;
  always @(posedge clk)if(rst_n && dut.workstation.core_ce)begin
    expected_capture_l=d_process_old_reference(dut.workstation.pcm_left_i,dut.workstation.d_crush,dut.workstation.d_drive);
    expected_capture_r=d_process_old_reference(dut.workstation.pcm_right_i,dut.workstation.d_crush,dut.workstation.d_drive);
    old_function_snapshots=old_function_snapshots+1;
  end
  always @(posedge clk)if(rst_n && dut.workstation.pcm_pitch_valid && dut.workstation.frame_inflight)begin
    expected_capture_l=d_process_old_reference(dut.workstation.pcm_pitch_left,dut.workstation.pcm_crush,dut.workstation.pcm_drive);
    expected_capture_r=d_process_old_reference(dut.workstation.pcm_pitch_right,dut.workstation.pcm_crush,dut.workstation.pcm_drive);
    #1;
    if(dut.workstation.held_pcm_l!==expected_capture_l || dut.workstation.held_pcm_r!==expected_capture_r)
      $fatal(1,"D core_ce depth snapshot changed across streaming Pitch");
  end
  task clocks(input integer n);repeat(n)@(negedge clk);endtask
  task event_send(input [17:0] data);begin
    event_data=data;event_valid=1;waited=0;
    // Consume exactly one valid/ready edge, including non-idempotent CC87/88.
    do begin @(posedge clk);waited=waited+1;if(waited>3000)$fatal(1,"event timeout");end while(!event_ready);
    @(negedge clk);event_valid=0;clocks(12);events=events+1;
  end endtask
  task cc(input [6:0] address,value);event_send({4'd2,address,value});endtask
  task frame(input signed [31:0] l,r);begin
    while(!ready)begin clocks(1);if(fault)$fatal(1,"render fault waiting ready");end
    pcm_l=l;pcm_r=r;request=1;clocks(1);request=0;waited=0;
    while(!done)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"render timeout");end
    if(error || fault || active!=0 || mode!=3)$fatal(1,"D-only state/error/voices");
    if(waited>max_render_cycles)max_render_cycles=waited;
    if(waited>1500)$fatal(1,"D effects plus Pitch missed the 48k sample budget");
    frames=frames+1;clocks(2);
  end endtask
  task change_rate(input reg next_rate);begin
    while(!config_ready)clocks(1);config_rate=next_rate;config_valid=1;clocks(1);config_valid=0;waited=0;
    while(!config_applied)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"config timeout");end
    if(applied_rate!=next_rate || fault)$fatal(1,"config ACK before all-rate agreement");rate=next_rate;clocks(2);
  end endtask
  task delayed_parameter_frame(input signed [31:0] l,r,input [6:0] crush,drive);
    reg signed [31:0] expected_l,expected_r;
    begin
      while(!ready)clocks(1);
      // Hold the real DDR config fence, accept one immutable PCM slot, then
      // change both controls while that pending sample awaits its new rate.
      hold_fence=1;rate=!rate;pcm_l=l;pcm_r=r;request=1;clocks(1);request=0;
      wait(dut.workstation.runtime_configuration.busy);
      pcm_l=32'sh76543210;pcm_r=-32'sh76543210;
      cc(20,crush);cc(21,drive);
      if(!dut.workstation.runtime_configuration.busy || !dut.workstation.pending)
        $fatal(1,"D deferred parameter case did not retain a pending sample");
      expected_l=d_process_old_reference(l,crush,drive);
      expected_r=d_process_old_reference(r,crush,drive);
      hold_fence=0;waited=0;
      while(!done)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"deferred parameter timeout");end
      if(error || left_o!==expected_l || right_o!==expected_r)
        $fatal(1,"D moved accepted PCM or core_ce parameter sampling across config drain");
      delayed_parameter_frames=delayed_parameter_frames+1;frames=frames+1;clocks(2);
    end
  endtask
  task pitch_capture(input bit next_rate,input bit down);
    integer fs;
    reg signed [31:0] l,r;
    real angle;
    begin
      change_rate(next_rate);cc(81,0);cc(20,0);cc(21,0);cc(22,0);
      event_send({4'd4,down ? 7'd0:7'd127,down ? 7'd0:7'd127});
      if(options[28:21]!=(down ? 8'd0:8'd255) || dut.workstation.pitch_q20_o==22'd1048576)
        $fatal(1,"Pitch actual parameter/index feedback stayed unity");
      fs=next_rate ? 44100:48000;
      for(integer n=0;n<12288;n=n+1)begin
        angle=6.283185307179586*n/fs;
        l=32'($rtoi($sin(angle*997.0)*67108864.0));
        r=32'($rtoi($sin(angle*1451.0)*50331648.0));
        frame(l,r);
        if(n>=4096)$fwrite(pitch_fd,"%0d %0d %0d %0d %0d\n",next_rate,down,n-4096,left_o,right_o);
      end
      pitch_captures=pitch_captures+1;
    end
  endtask
  task clear_pitch_history;
    begin
      @(negedge clk);history_clear=1;waited=0;
      do begin @(posedge clk);waited=waited+1;if(waited>3000)$fatal(1,"Pitch history accept timeout");end while(!history_ready);
      @(negedge clk);history_clear=0;waited=0;
      while(!history_done)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"Pitch history done timeout");end
      if(dut.workstation.streaming_pcm_pitch.pitch.filled!=0 || dut.workstation.streaming_pcm_pitch.pitch.phase!=0)
        $fatal(1,"PCM session history did not clear actual Pitch history");
      for(integer n=0;n<1100;n=n+1)begin frame(0,0);if(left_o!==0 || right_o!==0)$fatal(1,"old Pitch PCM replayed after source history clear");end
      pitch_clear_checks=pitch_clear_checks+1;
    end
  endtask
  task cancel_inflight_pitch(input bit lifecycle);
    integer before_responses;
    begin
      event_send({4'd4,7'd127,7'd127});
      while(!ready)clocks(1);
      before_responses=responses;pcm_l=32'sh31415926;pcm_r=-32'sh27182818;
      @(negedge clk);request=1;clocks(1);request=0;
      while(dut.workstation.streaming_pcm_pitch.pitch.quiescent_o)clocks(1);
      // Cancel inside the real new stage, before its joined PCM is available.
      clocks(2);event_send(lifecycle ? {4'd15,7'd0,7'd0}:{4'd2,7'd120,7'd0});waited=0;
      while(responses==before_responses)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"cancelled Pitch result did not complete");end
      if(responses!=before_responses+1 || !last_error || last_left!==0 || last_right!==0)
        $fatal(1,"cancelled Pitch leaked a stale or duplicate result");
      waited=0;while(!quiet)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"cancelled Pitch failed to drain");end
      if(dut.workstation.streaming_pcm_pitch.pitch.filled!=0 || options[28:21]!=128)
        $fatal(1,"cancelled Pitch retained history or committed bend");
      frames=frames+1;pitch_cancels=pitch_cancels+1;
      for(integer n=0;n<80;n=n+1)begin frame(0,0);if(left_o!==0 || right_o!==0)$fatal(1,"cancelled Pitch replayed PCM");end
    end
  endtask
  initial begin
    clocks(4);rst_n=1;mrst_n=1;clocks(10);
    if(mode!=3 || dut.workstation.pcm_gain_o!=32768)$fatal(1,"D-only startup not actual PCM unity/modeD");
    for(integer i=0;i<300;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"dry real PCM not bit-exact");
    cc(21,16);frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh2468acf0 || right_o!=-32'sh2468acf0 || options[13:7]!=16)$fatal(1,"committed drive disagrees with output");
    cc(20,127);frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh20000000 || right_o!=32'shd0000000 || options[6:0]!=127)$fatal(1,"committed crush disagrees with output");
    cc(20,0);cc(21,0);cc(22,127);
    for(integer i=0;i<100;i=i+1)frame(32'sh10000000,32'sh08000000);
    if(mask!=1 || options[20:14]!=127 || dut.workstation.runtime_effects.effects.delay_stage.gain!=8192)
      $fatal(1,"CC22 did not control unique runtime Delay wet");
    cc(22,64);for(integer i=0;i<40;i=i+1)frame(0,0);
    if(dut.workstation.runtime_effects.effects.delay_stage.gain!=4096)$fatal(1,"CC22 depth was only boolean");
    cc(22,0);for(integer i=0;i<50;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"D momentary release lost dry PCM");
    delayed_parameter_frame(32'sh12345678,-32'sh12345678,7'd31,7'd17);
    delayed_parameter_frame(32'sh23456789,-32'sh23456789,7'd84,7'd32);
    cc(20,0);cc(21,0);
    change_rate(1);for(integer i=0;i<300;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"44.1 dry PCM");
    cc(81,7);for(integer i=0;i<1200;i=i+1)frame(32'sh10000000,32'sh08000000);
    if(mask!=7 || fault)$fatal(1,"full effect chain not retained");
    if(effect_state!=32'h124)$fatal(1,"default effect feedback disagrees with committed owner");
    cc(87,2);if(effect_state!=32'h17e)$fatal(1,"reverb first feedback");
    cc(87,0);if(effect_state!=32'h1b2)$fatal(1,"delay second feedback");
    cc(87,1);if(effect_state!=32'h1d2)$fatal(1,"chorus third feedback got=%h",effect_state);
    cc(88,127);if(effect_state!=32'h0d2 || mask!=0)$fatal(1,"effect master feedback");
    cc(81,7);
    cc(20,100);cc(21,100);cc(22,100);
    event_send({4'd15,7'd1,7'd1});
    waited=0;while(dut.workstation.attach_initializing)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"D attach waited for nonexistent C engine");end
    if(options[20:0]!=0 || muted || mode!=3)$fatal(1,"D attach left stale controls/mute");
    for(integer i=0;i<300;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"D did not resume after25K attach withoutNoteOn");
    if(deadline!=0 || unsupported!=0 || duplicates!=0 || note_drops!=0)$fatal(1,"D health counters");
    if(!$value$plusargs("PITCH_PCM=%s",pitch_pcm_path))$fatal(1,"missing integrated Pitch output capture");
    pitch_fd=$fopen(pitch_pcm_path,"w");if(!pitch_fd)$fatal(1,"cannot create integrated Pitch output capture");
    pitch_capture(0,0);clear_pitch_history();
    pitch_capture(1,1);clear_pitch_history();
    $fclose(pitch_fd);
    cancel_inflight_pitch(0);cancel_inflight_pitch(1);
    event_send({4'd4,7'd0,7'd64});
    for(integer n=0;n<80;n=n+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!==32'sh12345678 || right_o!==-32'sh12345678 || options[28:21]!=128)
      $fatal(1,"Pitch release did not restore exact full-width dry PCM");
    if(deadline || unsupported || duplicates || note_drops || fault || pitch_captures!=2 || pitch_clear_checks!=2 || pitch_cancels!=2)
      $fatal(1,"continuous Pitch integration health/coverage");
    if(old_function_snapshots!=frames || delayed_parameter_frames!=2)$fatal(1,"D old-function/config sampling coverage");
    $display("PASS demo_d_only frames=%0d events=%0d rate44=%0d full_effects=1 no_instrument_engines=1 old_function_snapshots=%0d deferred_parameter_frames=%0d pitch_captures=%0d pitch_clear_checks=%0d pitch_cancels=%0d max_render_cycles=%0d",frames,events,rate,old_function_snapshots,delayed_parameter_frames,pitch_captures,pitch_clear_checks,pitch_cancels,max_render_cycles);$finish;
  end
  initial begin #100000000;$fatal(1,"test watchdog");end
endmodule
