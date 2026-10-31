`timescale 1ns/1ps
module tb_workstation_runtime_render_service;
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
  wire dwr_valid,dwr_pop,drd_push,drd_ready,ddr_req,ddr_write,ddr_response,dma_fault,audio_hb,memory_hb;
  wire [64:0] dwr_data,drd_data;
  wire [28:0] ddr_addr;
  wire [255:0] ddr_wdata,ddr_rdata;
  workstation_audio_render_service #(.RUNTIME_RATE_ENABLE(1),.RUNTIME_EFFECTS_ENABLE(1)) dut(
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
      .panic_epoch_o(epoch),.panic_muted_o(muted),.active_mask_o(active),
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
  integer trace_file,requests=0,responses=0,frames=0,configs=0,histories=0,cancels=0,max_latency=0;
  integer wet48=0,wet44=0,engine_samples48=0,engine_samples44=0,pitch_checks=0;
  integer pending_count=0,posted_writes=0,ordered_fences=0;
  integer max_steady_latency=0,max_auto_config_latency=0,max_loader_latency=0;
  integer vector_dispatch_cycles=0,vector_accepted_events=0,vector_release_cases=0;
  integer epoch_equality_checks=0,epoch_advances=0,epoch_wraps=0,epoch_match_returns=0;
  integer simultaneous_request_panic=0,epoch_wrap_cases=0;
  real pitch_error_hz;
  reg trace_on=1,allow_fault=0,old_rate=0;
  string trace_path;
  // Independent old-state oracle. Check both sides of every real clock edge,
  // including inactive slots, not only PCM responses that happened to cancel.
  always @(posedge clk)if(rst_n)begin: epoch_equivalence
    reg [9:0] expected_epoch,expected_snapshot;
    reg old_match,advance;
    old_match=epoch==dut.request_cancel_epoch;
    advance=dut.workstation.usb_lifecycle ||
        (dut.workstation.event_valid && dut.workstation.event_ready &&
         dut.workstation.kind==2 && dut.workstation.a==120);
    if(dut.panic_accept!==advance || dut.request_epoch_match!==old_match ||
       dut.cancelled!==(epoch!=dut.request_cancel_epoch ||
                       (muted && !dut.request_muted)))
      $fatal(1,"registered epoch proof differs from original cancellation formula before edge");
    expected_epoch=epoch+10'(advance);
    expected_snapshot=dut.accepted ? epoch : dut.request_cancel_epoch;
    if(advance)begin
      epoch_advances=epoch_advances+1;
      if(epoch==10'h3ff)epoch_wraps=epoch_wraps+1;
    end
    if(advance && dut.accepted)simultaneous_request_panic=simultaneous_request_panic+1;
    #1;
    if(epoch!==expected_epoch || dut.request_cancel_epoch!==expected_snapshot ||
       dut.request_epoch_match!==(expected_epoch==expected_snapshot) ||
       dut.cancelled!==(epoch!=dut.request_cancel_epoch ||
                       (muted && !dut.request_muted)))
      $fatal(1,"registered epoch proof differs from original next-state cancellation formula");
    if(!old_match && expected_epoch==expected_snapshot)epoch_match_returns=epoch_match_returns+1;
    epoch_equality_checks=epoch_equality_checks+2;
  end
  always @(posedge clk)if(rst_n)begin
    // Prove the local timing factorization against the real vector engine,
    // including pending samples, rate barriers and release-sweep traffic.
    if(dut.workstation.dispatch && dut.workstation.core_ce)
      $fatal(1,"event dispatch overlapped a real engine sample");
    if(dut.workstation.dispatch)begin
      if(dut.workstation.vec_dispatch_ready!==dut.workstation.vec_event_ready)
        $fatal(1,"dispatch state-ready differs from real vector acceptance");
      if(dut.workstation.scope_enable)vector_dispatch_cycles=vector_dispatch_cycles+1;
    end
    if(dut.workstation.scope_enable && dut.workstation.core_event_valid &&
       dut.workstation.vec_dispatch_ready)begin
      if(!dut.workstation.vec_event_ready)
        $fatal(1,"held/release state advanced without a real vector handshake");
      vector_accepted_events=vector_accepted_events+1;
    end
    if(request && ready)begin requests=requests+1;pending_count=pending_count+1;end
    if(dut.workstation.core_ce)begin
      if(applied_rate!=rate || dut.workstation.engine_rate!=applied_rate ||
         dut.workstation.fx_rate!=applied_rate || dut.workstation.rate_busy_o)
        $fatal(1,"render started before whole-chain rate commit");
      if(applied_rate)engine_samples44=engine_samples44+1;else engine_samples48=engine_samples48+1;
    end
    if(trace_on && dut.workstation.panic_accept)$fdisplay(trace_file,"C 4");
    if(dut.workstation.runtime_engines.engines.oscillator.pitch_write_valid)begin
      // Invariant in physical Hz, independently expressed from the RTL rate
      // division: nearest-step quantization is bounded by half a phase LSB.
      pitch_error_hz=real'(dut.workstation.runtime_engines.engines.oscillator.pitch_step_rounded)*
          (applied_rate ? 44100.0 : 48000.0)/4294967296.0-
          real'(dut.workstation.runtime_engines.engines.oscillator.pitch_product)*48000.0/4503599627370496.0;
      if(pitch_error_hz>0.000006 || pitch_error_hz< -0.000006)$fatal(1,"actual oscillator changed physical pitch across rate switch");
      if(dut.workstation.runtime_engines.engines.oscillator.frame_rate_44100!=applied_rate)
        $fatal(1,"engine frame captured wrong applied rate");
      pitch_checks=pitch_checks+1;
    end
    if(dut.workstation.effects_valid && dut.workstation.fx_ready &&
       {dut.workstation.held_pcm_l,dut.workstation.held_pcm_r}!={dut.held_pcm_left,dut.held_pcm_right})
      $fatal(1,"pending render lost accepted PCM identity");
    if(trace_on && dut.workstation.effects_valid && dut.workstation.fx_ready && !dut.workstation.panic_accept)
      $fdisplay(trace_file,"F %0d %0d %0d %0d %0d %0d %0d %0d %0d",$signed(dut.workstation.held_synth),
        $signed(dut.workstation.held_pcm_l),$signed(dut.workstation.held_pcm_r),$signed(dut.workstation.held_vec_l),
        $signed(dut.workstation.held_vec_r),dut.workstation.expression_gain,dut.pcm_gain_o,dut.effect_mask_o,dut.effect_order_o);
  end
  always @(negedge clk)if(rst_n)begin
    if(done)begin
      responses=responses+1;pending_count=pending_count-1;
      if(pending_count!=0)$fatal(1,"duplicate or missing request identity");
      if(error)begin cancels=cancels+1;if(left_o!=0 || right_o!=0)$fatal(1,"cancel was not zero");end
      else if(trace_on)begin $fdisplay(trace_file,"O %0d %0d",left_o,right_o);frames=frames+1;end
    end
    if(config_applied)begin
      configs=configs+1;
      if(fault || dut.workstation.engine_rate!=applied_rate || dut.workstation.fx_rate!=applied_rate || dut.workstation.rate_busy_o)
        $fatal(1,"public config ACK before every subsystem applied");
    end
    if(history_done)begin histories=histories+1;if(trace_on)$fdisplay(trace_file,"C %0d",config_applied ? (applied_rate ? 1 : 2) : 3);end
    if(applied_rate!=old_rate && !config_applied)$fatal(1,"public rate changed without all-ACK");
    old_rate=applied_rate;
    if(dut.workstation.runtime_effects.effects.delay_stage.read_l!=0 || dut.workstation.runtime_effects.effects.delay_stage.read_r!=0)begin
      if(applied_rate)wet44=wet44+1;else wet48=wet48+1;
    end
    if(fault && !allow_fault)$fatal(1,"unexpected sticky runtime fault");
  end
  task automatic send(input integer kind,address,value);
    begin
      @(negedge clk);event_data={4'(kind),7'(address),7'(value)};event_valid=1;
      do @(posedge clk);while(!event_ready);
      @(negedge clk);event_valid=0;repeat(3)@(negedge clk);
    end
  endtask
  task automatic idle;
    integer timeout;
    begin timeout=0;while(!quiet && timeout<2000000)begin @(negedge clk);timeout=timeout+1;end
      if(!quiet)$fatal(1,"failed to drain real render/config pipelines");end
  endtask
  task automatic configure(input logic next_rate,input logic history_only);
    integer before_count,timeout;
    begin
      idle();@(negedge clk);before_count=histories;config_rate=next_rate;
      config_valid=!history_only;history_clear=history_only;
      // Config/history has priority even when a sample is offered on the
      // same edge. Passive idle must not become permission to admit it.
      request=1;rate=next_rate;
      do @(posedge clk);while(history_only ? !history_ready : !config_ready);
      if(ready || sample_ce)$fatal(1,"configuration admitted competing frame");
      @(negedge clk);request=0;config_valid=0;history_clear=0;timeout=0;
      while(histories==before_count && timeout<2000000)begin @(negedge clk);timeout=timeout+1;end
      if(histories!=before_count+1 || applied_rate!=next_rate)$fatal(1,"config/history commit failed");
      idle();
    end
  endtask
  task automatic offer(input logic next_rate);
    begin wait(ready);@(negedge clk);rate=next_rate;request=1;@(negedge clk);request=0;end
  endtask
  task automatic render(input logic next_rate,input integer index);
    integer before_count,latency;
    logic needs_config,loader_pending;
    begin
      before_count=responses;needs_config=next_rate!=applied_rate;loader_pending=dut.workstation.load_busy;pcm_l=32'sh12340000+$signed(32'(index*7919));pcm_r=-pcm_l;
      offer(next_rate);pcm_l=~pcm_l;pcm_r=~pcm_r;latency=0;
      while(responses==before_count && latency<2000000)begin @(negedge clk);latency=latency+1;end
      if(responses!=before_count+1 || error)$fatal(1,"render completion failed");
      if(latency>max_latency)max_latency=latency;
      if(needs_config)begin if(latency>max_auto_config_latency)max_auto_config_latency=latency;end
      else if(loader_pending)begin if(latency>max_loader_latency)max_loader_latency=latency;end
      else if(latency>max_steady_latency)max_steady_latency=latency;
      idle();
    end
  endtask
  integer orders[0:5];
  initial begin
    if(!$value$plusargs("TRACE=%s",trace_path))$fatal(1,"TRACE required");
    trace_file=$fopen(trace_path,"w");if(!trace_file)$fatal(1,"trace open failed");
    orders[0]=6'b10_01_00;orders[1]=6'b01_10_00;orders[2]=6'b10_00_01;
    orders[3]=6'b00_10_01;orders[4]=6'b01_00_10;orders[5]=6'b00_01_10;
    repeat(8)@(negedge clk);rst_n=1;mrst_n=1;repeat(100)@(negedge clk);
    configure(0,0);send(2,16,127);send(2,81,7);send(1,69,100);
    for(integer rate_index=0;rate_index<2;rate_index=rate_index+1)begin
      // The first 44.1 request must retain its PCM and auto-configure.
      for(integer n=0;n<12000;n=n+1)render(1'(rate_index),n);
      if(!held[69] || active==0)$fatal(1,"held note lost during rate change");
      for(integer permutation=0;permutation<6;permutation=permutation+1)begin
        for(integer mask=0;mask<8;mask=mask+1)begin
          send(2,81,mask);send(2,84,orders[permutation]&3);send(2,85,(orders[permutation]>>2)&3);send(2,86,(orders[permutation]>>4)&3);
          for(integer n=0;n<256;n=n+1)render(1'(rate_index),n+permutation*256+mask*65536);
        end
      end
    end
    configure(0,0);render(0,1);configure(0,1);render(0,2);configure(1,0);render(1,3);
    if(wet48==0 || wet44==0 || engine_samples48==0 || engine_samples44==0 || pitch_checks==0)
      $fatal(1,"missing real engine/effect/rate coverage");
    // Exercise full synth A/B/C allocation and vector joins at both rates.
    for(integer source=0;source<4;source=source+1)begin
      send(2,120,0);idle();send(2,90,0);send(2,80,source<3 ? source : 2);
      wait(dut.mode_o==2'(source<3 ? source : 2));if(source==3)send(2,90,127);
      for(integer n=0;n<(source==3 ? 8 : 32);n=n+1)send(1,48+n,100);
      for(integer rate_index=0;rate_index<2;rate_index=rate_index+1)begin
        configure(1'(rate_index),0);
        for(integer n=0;n<8;n=n+1)render(1'(rate_index),n);
        if(held==0 || active==0)$fatal(1,"engine mode lost held allocation");
      end
    end
    // Release two deferred real vector notes while a new-rate sample is
    // offered. Neither the held map nor release cursor may outrun the engine.
    if(!dut.workstation.scope_enable)$fatal(1,"vector release fixture lost source");
    send(2,64,127);send(0,48,0);send(0,49,0);
    wait(dut.workstation.deferred[48] && dut.workstation.deferred[49]);
    fork
      begin render(0,901);end
      begin send(2,64,0);end
    join
    wait(!dut.workstation.releasing);
    if(dut.workstation.deferred!=0 || held[48] || held[49])
      $fatal(1,"vector sustain release left deferred/held notes");
    vector_release_cases=vector_release_cases+1;
    // Lifecycle cancellation bypasses the ordinary queue during a second
    // real vector release sweep and must clear its private cursor immediately.
    send(2,64,127);send(0,50,0);wait(dut.workstation.deferred[50]);
    send(2,123,0);wait(dut.workstation.releasing);send(15,0,0);
    if(held!=0 || dut.workstation.deferred!=0 || dut.workstation.releasing)
      $fatal(1,"lifecycle did not cancel real vector release state");
    vector_release_cases=vector_release_cases+1;
    if(vector_dispatch_cycles==0 || vector_accepted_events<10)
      $fatal(1,"missing real vector dispatch coverage");
    send(2,120,0);idle();send(2,90,0);send(2,80,0);wait(dut.mode_o==0);send(1,69,100);render(1,0);
    trace_on=0;
    // Keep one real accepted request snapshot while lifecycle cancellations
    // traverse all 1024 epoch identities. The old equality becomes true again;
    // a sticky cancellation bit would silently change this historical meaning.
    send(2,120,0);idle();offer(1);wait(done);idle();
    begin: full_epoch_turn
      reg [9:0] snapshot;
      snapshot=epoch;
      if(dut.request_cancel_epoch!=snapshot || !dut.request_epoch_match)
        $fatal(1,"wrap test did not capture a real request snapshot");
      for(integer n=0;n<1024;n=n+1)send(15,0,0);
      if(epoch!=snapshot || dut.request_cancel_epoch!=snapshot || !dut.request_epoch_match)
        $fatal(1,"1024 real lifecycle cancellations did not restore old epoch equality");
      epoch_wrap_cases=epoch_wrap_cases+1;idle();
    end
    // Unlike dispatched CC120, the real USB lifecycle bypass can coincide
    // with sample admission. Snapshot sees the old epoch and must mismatch on
    // the very first post-edge cycle, with one explicit cancellation response.
    wait(ready);@(negedge clk);request=1;rate=1;event_valid=1;event_data={4'd15,7'd0,7'd0};
    @(posedge clk);if(!ready || !dut.panic_accept)$fatal(1,"missing true accepted/PANIC overlap");
    @(negedge clk);request=0;event_valid=0;
    wait(responses==requests);if(!error)$fatal(1,"same-edge lifecycle failed to cancel new snapshot");idle();
    // An already-muted accepted slot is a deterministic good zero, even if a
    // later NoteOn unmutes the workstation while that slot is rendering.
    send(2,120,0);idle();offer(1);wait(dut.workstation.frame_inflight && !dut.workstation.pending);send(1,60,100);
    wait(done);if(error || left_o!=0 || right_o!=0)$fatal(1,"accepted muted identity changed after NoteOn");
    idle();if(muted)$fatal(1,"NoteOn did not restore real source after intentional silence");
    // A new cancellation epoch after a muted slot was accepted still cancels
    // that slot exactly once; intentional silence is not immunity to PANIC.
    send(2,120,0);idle();offer(1);wait(dut.workstation.frame_inflight && !dut.workstation.pending);send(2,120,0);
    wait(done);if(!error)$fatal(1,"new PANIC did not cancel an accepted muted request");idle();
    send(1,69,100);render(1,0);
    // Hold the actual ordered fence after posted writes. NoteOff must pass
    // through the original event loader while the registered render waits.
    hold_fence=1;offer(0);wait(dut.workstation.rate_busy_o);send(0,69,0);
    if(held[69])$fatal(1,"NoteOff starved behind a switching render");
    @(negedge clk);config_valid=1;history_clear=1;config_rate=1;
    repeat(200)begin @(negedge clk);if(config_ready || history_ready)$fatal(1,"busy render accepted competing config/history");end
    config_valid=0;history_clear=0;
    if(done || applied_rate!=1 || ready || !busy)$fatal(1,"partial apply escaped the closed transaction");
    hold_fence=0;wait(done);idle();
    // PANIC coalesces with the accepted config and returns exactly one zero.
    hold_fence=1;offer(1);wait(dut.workstation.rate_busy_o);send(2,120,0);
    wait(responses==requests);if(!muted || !busy)$fatal(1,"PANIC must cancel response and retain real drain");
    hold_fence=0;idle();if(applied_rate!=1)$fatal(1,"PANIC retracted accepted rate change");
    send(1,60,100);render(1,4);
    // USB lifecycle is the bypass cancellation path and clears held state.
    hold_fence=1;offer(0);wait(dut.workstation.rate_busy_o);send(15,0,0);
    wait(responses==requests);hold_fence=0;idle();if(held!=0)$fatal(1,"lifecycle failed to clear held state");
    // An old autonomous clear completion may coincide with acceptance of a
    // new external config. It must not count as that new transaction's ACK.
    send(2,120,0);wait(dut.workstation.fx_history_done);
    @(negedge clk);config_rate=1;config_valid=1;
    do @(posedge clk);while(!config_ready);
    @(negedge clk);config_valid=0;hold_fence=1;repeat(200)@(negedge clk);
    if(ready || !busy || history_done)$fatal(1,"old history ACK reopened new config slot");
    hold_fence=0;wait(config_applied);idle();
    configure(0,0);
    // Missing ordered response fails closed; late data cannot restore ready.
    allow_fault=1;hold_fence=1;offer(1);wait(fault);wait(responses==requests);
    if(ready || quiet || !error)$fatal(1,"fault exposed pseudo ready");
    hold_fence=0;repeat(200)@(negedge clk);if(!fault || ready)$fatal(1,"late fence cleared sticky failure");
    posted_writes=memory_model.accepted_writes;ordered_fences=memory_model.fence_returns;
    if(posted_writes==0 || ordered_fences==0)$fatal(1,"missing real DDR transactions");
    @(negedge clk);rst_n=0;mrst_n=0;repeat(8)@(negedge clk);rst_n=1;mrst_n=1;
    repeat(100)@(negedge clk);allow_fault=0;old_rate=0;idle();if(applied_rate || fault)$fatal(1,"coordinated reset recovery failed");
    if(epoch_wrap_cases!=1 || epoch_wraps==0 || epoch_match_returns==0 || simultaneous_request_panic==0)
      $fatal(1,"missing real cancellation epoch boundary coverage");
    $display("PASS runtime_render_service: requests=%0d responses=%0d modeled_frames=%0d configs=%0d histories=%0d cancels=%0d wet48=%0d wet44=%0d pitch_checks=%0d max_latency=%0d max_steady_latency=%0d max_auto_config_latency=%0d max_loader_latency=%0d posted_writes=%0d ordered_fences=%0d vector_dispatch_cycles=%0d vector_accepted_events=%0d vector_release_cases=%0d epoch_equality_checks=%0d epoch_advances=%0d epoch_wraps=%0d epoch_match_returns=%0d simultaneous_request_panic=%0d epoch_wrap_cases=%0d",requests,responses,frames,configs,histories,cancels,wet48,wet44,pitch_checks,max_latency,max_steady_latency,max_auto_config_latency,max_loader_latency,posted_writes,ordered_fences,vector_dispatch_cycles,vector_accepted_events,vector_release_cases,epoch_equality_checks,epoch_advances,epoch_wraps,epoch_match_returns,simultaneous_request_panic,epoch_wrap_cases);
    $fclose(trace_file);$finish;
  end
  initial begin #2000000000;$fatal(1,"test timeout");end
endmodule
