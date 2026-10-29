`timescale 1ns/1ps
module tb_workstation_runtime_oscillator;
  logic clk=0;
  always #5 clk=~clk;
  logic rst=0,panic=0,mode_valid=0,event_valid=0,note_on=0;
  logic expression_valid=0,sample_ce=0,rate_commit=0,rate44=0;
  logic [1:0] mode=0;
  logic [2:0] profile=0;
  logic [6:0] note=60,velocity=100,pressure_note=60,pressure=127,off_note=60;
  logic [21:0] ratio=22'd1048576;
  wire mode_ready,ref_mode_ready,event_ready,ref_event_ready;
  wire expression_ready,ref_expression_ready,sample_ready,ref_sample_ready;
  wire sample_valid,ref_sample_valid,load_busy,ref_load_busy,mix_busy,ref_mix_busy;
  wire [1:0] current_mode,ref_current_mode;
  wire signed [31:0] sample,ref_sample;
  wire [31:0] allocated,ref_allocated,active,ref_active;
  wire [5:0] active_count,ref_active_count;
  wire [7:0] issued,ref_issued;
  wire rate_ready,applied44,quiet;
  logic check_equal=1,watch_enabled=0;
  integer scenario=0,cycles=0,frames=0,max_latency=0,watch_slot=31;
  integer muted=0,audible=0;
  integer frame_latency,last_frame_latency;
  logic [31:0] saved_phase,saved_step,saved_mask;
  logic [15:0] saved_gain;
  logic [23:0] saved_level;
  logic [34:0] expected_step;
  logic [63:0] wide;
  logic [23:0] prior_levels[0:31];
  logic [31:0] prior_phases[0:31];
  wire signed [31:0] plain_sample,plain_ref_sample;
  wire plain_valid,plain_ref_valid;

  unified_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000),
      .SEPARATE_OFF_NOTE(1)) reference_engine(
      .clk_i(clk),.rst_ni(rst),.panic_i(panic),.mode_set_valid_i(mode_valid),
      .mode_set_ready_o(ref_mode_ready),.mode_i(mode),.current_mode_o(ref_current_mode),
      .event_valid_i(event_valid),.event_ready_o(ref_event_ready),.event_note_on_i(note_on),
      .expression_valid_i(expression_valid),.expression_ready_o(ref_expression_ready),
      .expression_note_i(pressure_note),.expression_value_i(pressure),
      .event_profile_i(profile),.event_midi_note_i(note),.event_velocity_i(velocity),
      .event_off_note_i(off_note),.pitch_ratio_q20_i(ratio),.sample_ce_i(sample_ce),
      .sample_ready_o(ref_sample_ready),.sample_valid_o(ref_sample_valid),.sample_o(ref_sample),
      .allocated_mask_o(ref_allocated),.active_mask_o(ref_active),
      .active_voice_count_o(ref_active_count),.load_busy_o(ref_load_busy),
      .mix_busy_o(ref_mix_busy),.issued_slot_count_o(ref_issued));
  workstation_runtime_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000),
      .SEPARATE_OFF_NOTE(1),.RUNTIME_RATE_ENABLE(1)) dut(
      .clk_i(clk),.rst_ni(rst),.panic_i(panic),.mode_set_valid_i(mode_valid),
      .mode_set_ready_o(mode_ready),.mode_i(mode),.current_mode_o(current_mode),
      .event_valid_i(event_valid),.event_ready_o(event_ready),.event_note_on_i(note_on),
      .expression_valid_i(expression_valid),.expression_ready_o(expression_ready),
      .expression_note_i(pressure_note),.expression_value_i(pressure),
      .event_profile_i(profile),.event_midi_note_i(note),.event_velocity_i(velocity),
      .event_off_note_i(off_note),.pitch_ratio_q20_i(ratio),.sample_ce_i(sample_ce),
      .sample_ready_o(sample_ready),.sample_valid_o(sample_valid),.sample_o(sample),
      .allocated_mask_o(allocated),.active_mask_o(active),.active_voice_count_o(active_count),
      .load_busy_o(load_busy),.mix_busy_o(mix_busy),.issued_slot_count_o(issued),
      .rate_commit_i(rate_commit),.rate_44100_i(rate44),.rate_ready_o(rate_ready),
      .applied_rate_44100_o(applied44),.quiescent_o(quiet));

  unified_oscillator_engine #(.EXPRESSION_ENABLE(0),.SAMPLE_RATE_HZ(48000),
      .SEPARATE_OFF_NOTE(1)) plain_reference(
      .clk_i(clk),.rst_ni(rst),.panic_i(panic),.mode_set_valid_i(mode_valid),
      .mode_set_ready_o(),.mode_i(mode),.current_mode_o(),
      .event_valid_i(event_valid),.event_ready_o(),.event_note_on_i(note_on),
      .expression_valid_i(expression_valid),.expression_ready_o(),
      .expression_note_i(pressure_note),.expression_value_i(pressure),
      .event_profile_i(profile),.event_midi_note_i(note),.event_velocity_i(velocity),
      .event_off_note_i(off_note),.pitch_ratio_q20_i(ratio),.sample_ce_i(sample_ce),
      .sample_ready_o(),.sample_valid_o(plain_ref_valid),.sample_o(plain_ref_sample),
      .allocated_mask_o(),.active_mask_o(),
      .active_voice_count_o(),.load_busy_o(),
      .mix_busy_o(),.issued_slot_count_o());
  workstation_runtime_oscillator_engine #(.EXPRESSION_ENABLE(0),.SAMPLE_RATE_HZ(48000),
      .SEPARATE_OFF_NOTE(1),.RUNTIME_RATE_ENABLE(1)) plain_runtime(
      .clk_i(clk),.rst_ni(rst),.panic_i(panic),.mode_set_valid_i(mode_valid),
      .mode_set_ready_o(),.mode_i(mode),.current_mode_o(),
      .event_valid_i(event_valid),.event_ready_o(),.event_note_on_i(note_on),
      .expression_valid_i(expression_valid),.expression_ready_o(),
      .expression_note_i(pressure_note),.expression_value_i(pressure),
      .event_profile_i(profile),.event_midi_note_i(note),.event_velocity_i(velocity),
      .event_off_note_i(off_note),.pitch_ratio_q20_i(ratio),.sample_ce_i(sample_ce),
      .sample_ready_o(),.sample_valid_o(plain_valid),.sample_o(plain_sample),
      .allocated_mask_o(),.active_mask_o(),.active_voice_count_o(),
      .load_busy_o(),.mix_busy_o(),.issued_slot_count_o(),
      .rate_commit_i(rate_commit),.rate_44100_i(rate44),.rate_ready_o(),
      .applied_rate_44100_o(),.quiescent_o());

  // Legacy callers may omit the new inputs: default RUNTIME_RATE_ENABLE=0
  // never reads their X/Z values. Elaborate and compare this exact call form.
  wire default_sample_valid;
  wire signed [31:0] default_sample;
  workstation_runtime_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000),
      .SEPARATE_OFF_NOTE(1)) default_call(
      .clk_i(clk),.rst_ni(rst),.panic_i(panic),.mode_set_valid_i(mode_valid),
      .mode_i(mode),.event_valid_i(event_valid),.event_note_on_i(note_on),
      .expression_valid_i(expression_valid),.expression_note_i(pressure_note),
      .expression_value_i(pressure),.event_profile_i(profile),.event_midi_note_i(note),
      .event_velocity_i(velocity),.event_off_note_i(off_note),.pitch_ratio_q20_i(ratio),
      .sample_ce_i(sample_ce),.sample_valid_o(default_sample_valid),.sample_o(default_sample),
      .mode_set_ready_o(),.current_mode_o(),.event_ready_o(),.expression_ready_o(),
      .sample_ready_o(),.allocated_mask_o(),.active_mask_o(),.active_voice_count_o(),
      .load_busy_o(),.mix_busy_o(),.issued_slot_count_o(),.rate_ready_o(),
      .applied_rate_44100_o(),.quiescent_o());

  always @(negedge clk) begin
    cycles=cycles+1;
    if(rst && check_equal) begin
      if ({mode_ready,event_ready,expression_ready,sample_ready,sample_valid,
           current_mode,allocated,active,active_count,load_busy,mix_busy,issued} !==
          {ref_mode_ready,ref_event_ready,ref_expression_ready,ref_sample_ready,ref_sample_valid,
           ref_current_mode,ref_allocated,ref_active,ref_active_count,ref_load_busy,ref_mix_busy,ref_issued})
        $fatal(1,"48k control mismatch cycle=%0d",cycles);
      if(sample !== ref_sample || default_sample !== ref_sample ||
          default_sample_valid !== ref_sample_valid)
        $fatal(1,"48k output mismatch cycle=%0d dut=%0d ref=%0d",cycles,sample,ref_sample);
      if(plain_valid !== plain_ref_valid || plain_sample !== plain_ref_sample)
        $fatal(1,"48k no-expression output mismatch cycle=%0d",cycles);
      for(integer v=0;v<32;v=v+1) begin
        if(dut.envelope_level_q24[v] !== reference_engine.envelope_level_q24[v] ||
           dut.envelope_state[v] !== reference_engine.envelope_state[v] ||
           dut.expression_gain_q8[v] !== reference_engine.expression_gain_q8[v])
          $fatal(1,"48k state mismatch voice=%0d cycle=%0d",v,cycles);
      end
    end
    if(rst) begin
      // This checks actual submodule valid registers independently of the
      // new mirror. An asserted quiescent may never hide a future tail.
      if(quiet && (dut.u_sine_interp.valid_s0 || dut.u_sine_interp.valid_s1 ||
          dut.u_sine_interp.valid_s2 || dut.u_sine_interp.valid_s3 ||
          dut.u_sine_interp.valid_o || dut.gain_product_valid ||
          dut.envelope_product_valid || dut.finalize_valid ||
          dut.quantizer.magnitude_low_valid || dut.quantizer.magnitude_valid ||
          dut.quantizer.scale_low_valid || dut.quantizer.scaled_valid ||
          dut.quantizer.rounded_valid || dut.quantizer.valid_o))
        $fatal(1,"quiescent hid an actual valid pipeline");
      if(dut.sine_pending_valid !== {dut.u_sine_interp.valid_s3,dut.u_sine_interp.valid_s2,
          dut.u_sine_interp.valid_s1,dut.u_sine_interp.valid_s0})
        $fatal(1,"sine valid mirror differs from actual pipeline");
    end
  end
  always @(posedge clk) begin
    if(rst && watch_enabled && dut.pitch_write_valid && dut.pitch_write_index==watch_slot[9:0]) begin
      if(dut.pitch_step_rounded >= 35'd1932735283) begin
        #1;
        if(dut.gain_pipe[1] !== 0) $fatal(1,"final effective step not muted");
        muted=muted+1;
      end else begin
        #1;
        if(dut.gain_pipe[1] != 0) audible=audible+1;
      end
    end
  end
  task automatic wait_idle;
    integer timeout;
    begin
      @(negedge clk);timeout=0;
      while(!quiet) begin @(negedge clk);timeout=timeout+1;
        if(timeout>1800)$fatal(1,"oscillator did not drain");end
    end
  endtask
  task automatic change_mode(input integer value);
    begin
      wait_idle();mode=value[1:0];mode_valid=1;
      @(negedge clk);mode_valid=0;
      if(current_mode!=value[1:0])$fatal(1,"mode did not apply");
    end
  endtask
  task automatic send_note(input integer prof,input integer midi,input integer vel,input logic on_value);
    begin
      @(negedge clk);while(!event_ready)@(negedge clk);
      profile=prof[2:0];note=midi[6:0];off_note=midi[6:0];velocity=vel[6:0];
      note_on=on_value;event_valid=1;
      @(negedge clk);event_valid=0;note_on=0;
      while(!event_ready)@(negedge clk);
    end
  endtask
  task automatic send_pressure(input integer midi,input integer value);
    begin
      @(negedge clk);while(!expression_ready)@(negedge clk);
      pressure_note=midi[6:0];pressure=value[6:0];expression_valid=1;
      @(negedge clk);expression_valid=0;
    end
  endtask
  task automatic render;
    begin
      @(negedge clk);while(!sample_ready)@(negedge clk);
      sample_ce=1;@(negedge clk);sample_ce=0;frame_latency=1;
      if(scenario==1 && applied44)rate44=~rate44;
      while(!sample_valid)begin @(negedge clk);frame_latency=frame_latency+1;
        if(frame_latency>1600)$fatal(1,"1600-clock frame budget missed");end
      frames=frames+1;last_frame_latency=frame_latency;
      if(frame_latency>max_latency)max_latency=frame_latency;
      @(negedge clk);
    end
  endtask
  task automatic hard_panic;
    begin
      @(negedge clk);panic=1;@(negedge clk);panic=0;
      wait_idle();repeat(2)@(negedge clk);
      if(allocated!=0)$fatal(1,"PANIC allocation semantics changed");
    end
  endtask
  task automatic commit_rate(input logic value);
    logic [79:0] slots_before[0:1023];
    logic [23:0] levels_before[0:31];
    logic [2:0] states_before[0:31];
    logic [6:0] notes_before[0:31];
    logic [7:0] expression_before[0:31];
    begin
      wait_idle();while(!rate_ready)@(negedge clk);
      saved_mask=allocated;saved_level=dut.envelope_level_q24[0];
      saved_phase=dut.slot_mem[0][79:48];
      for(integer slot=0;slot<1024;slot=slot+1)slots_before[slot]=dut.slot_mem[slot];
      for(integer v=0;v<32;v=v+1)begin
        levels_before[v]=dut.envelope_level_q24[v];states_before[v]=dut.envelope_state[v];
        notes_before[v]=dut.assigned_midi_note[v];expression_before[v]=dut.expression_gain_q8[v];
      end
      rate44=value;rate_commit=1;@(negedge clk);rate_commit=0;
      if(applied44!==value || allocated!==saved_mask ||
          dut.envelope_level_q24[0]!==saved_level || dut.slot_mem[0][79:48]!==saved_phase)
        $fatal(1,"rate commit retriggered or changed voice state");
      for(integer slot=0;slot<1024;slot=slot+1)
        if(dut.slot_mem[slot]!==slots_before[slot])$fatal(1,"rate commit rewrote slot state");
      for(integer v=0;v<32;v=v+1)
        if(dut.envelope_level_q24[v]!==levels_before[v] || dut.envelope_state[v]!==states_before[v] ||
            dut.assigned_midi_note[v]!==notes_before[v] || dut.expression_gain_q8[v]!==expression_before[v])
          $fatal(1,"rate commit changed held state voice=%0d",v);
    end
  endtask
  task automatic unity_suite;
    begin
      for(integer m=0;m<3;m=m+1) begin
        for(integer p=0;p<5;p=p+1) begin
          hard_panic();change_mode(m);
          for(integer v=0;v<32;v=v+1)send_note(p,48+v,40+(v*13)%88,1);
          if(allocated!==32'hffffffff)$fatal(1,"32 voice allocation lost");
          for(integer f=0;f<12;f=f+1)begin
            case(f%4)
              0:ratio=22'd1048576;
              1:ratio=22'd2097152;
              2:ratio=22'd524288;
              3:ratio=22'd1310720;
            endcase
            render();
          end
          send_pressure(48,0);render();send_pressure(48,127);render();
          for(integer v=0;v<32;v=v+1)send_note(p,48+v,0,0);
          repeat(3)render();
        end
      end
      // Baseline comparison at every ADSR branch and saturation boundary.
      hard_panic();change_mode(0);send_note(0,60,127,1);ratio=22'd1048576;
      for(integer st=0;st<5;st=st+1)begin
        for(integer boundary=0;boundary<4;boundary=boundary+1)begin
          wait_idle();
          dut.envelope_state[0]=st[2:0];reference_engine.envelope_state[0]=st[2:0];default_call.envelope_state[0]=st[2:0];plain_reference.envelope_state[0]=st[2:0];plain_runtime.envelope_state[0]=st[2:0];
          dut.envelope_level_q24[0]=boundary==0 ? 0 :
              boundary==1 ? 24'hffffbf : boundary==2 ? 24'hffffc0 : 24'd1672;
          reference_engine.envelope_level_q24[0]=dut.envelope_level_q24[0];default_call.envelope_level_q24[0]=dut.envelope_level_q24[0];plain_reference.envelope_level_q24[0]=dut.envelope_level_q24[0];plain_runtime.envelope_level_q24[0]=dut.envelope_level_q24[0];
          render();
        end
      end
      $display("PASS runtime oscillator unity cycles=%0d frames=%0d max_latency=%0d",cycles,frames,max_latency);
    end
  endtask
  task automatic switching_suite;
    integer effective_attack,previous_muted,previous_audible;
    begin
      check_equal=0;hard_panic();change_mode(2);ratio=22'd1048576;
      // Flute note75 partial31 crosses0.45Fs at44.1 but remains valid at48.
      send_note(0,75,127,1);repeat(6)render();watch_enabled=1;watch_slot=31;
      saved_step=dut.slot_mem[31][47:16];saved_gain=dut.slot_mem[31][15:0];
      if(saved_step!=32'd1781707008 || saved_gain==0)$fatal(1,"cross-boundary fixture drift");
      commit_rate(1);previous_muted=muted;
      repeat(8)begin
        saved_phase=dut.slot_mem[0][79:48];
        wide=64'(dut.slot_mem[0][47:16])*64'(ratio)*64'd160;
        expected_step=35'((wide+64'd77070336)/64'd154140672);
        render();
        if(dut.slot_mem[0][79:48]!==saved_phase+expected_step[31:0])
          $fatal(1,"44.1 DDS exact rational mismatch");
        if(dut.slot_mem[31][47:16]!==saved_step || dut.slot_mem[31][15:0]!==saved_gain)
          $fatal(1,"temporary cutoff destroyed canonical slot");
      end
      if(muted==previous_muted)$fatal(1,"crossed partial was never muted");
      commit_rate(0);previous_audible=audible;
      repeat(4)render();
      if(audible==previous_audible)$fatal(1,"reverse switch failed to restore partial");
      if(dut.slot_mem[31][47:16]!==saved_step || dut.slot_mem[31][15:0]!==saved_gain)
        $fatal(1,"reverse switch changed canonical state");
      // Preserve a held attack level and change only its per-frame delta.
      hard_panic();change_mode(0);send_note(0,69,127,1);repeat(3)render();
      commit_rate(1);saved_level=dut.envelope_level_q24[0];
      effective_attack=int'((64'(dut.attack_step_q24[0])*160+73)/147);
      render();
      if({8'd0,dut.envelope_level_q24[0]}!=={8'd0,saved_level}+effective_attack)
        $fatal(1,"44.1 ADSR did not preserve level and scale step");
      if(dut.slot_mem[0][47:16]!==32'd39370532)
        $fatal(1,"A4 canonical48 step changed");
      commit_rate(0);send_pressure(69,0);render();send_pressure(69,127);render();
      send_note(0,69,0,0);render();
      if(dut.envelope_state[0]!=4)$fatal(1,"held-note release semantics changed");
      // Held32 voices cover all five ADSR tables after a runtime commit.
      hard_panic();change_mode(0);commit_rate(0);ratio=22'd1048576;
      for(integer v=0;v<32;v=v+1)send_note(v%5,48+v,127,1);
      repeat(3)render();commit_rate(1);
      for(integer f=0;f<8;f=f+1)begin
        for(integer v=0;v<32;v=v+1)begin
          prior_levels[v]=dut.envelope_level_q24[v];
          prior_phases[v]=dut.slot_mem[v][79:48];
        end
        render();
        if(allocated!==32'hffffffff)$fatal(1,"runtime switch lost held voices");
        for(integer v=0;v<32;v=v+1)begin
          effective_attack=int'((64'(dut.attack_step_q24[v])*160+73)/147);
          if({8'd0,dut.envelope_level_q24[v]}!=={8'd0,prior_levels[v]}+effective_attack)
            $fatal(1,"five-profile runtime ADSR mismatch voice=%0d",v);
          wide=64'(dut.slot_mem[v][47:16])*64'd1048576*64'd160;
          expected_step=35'((wide+64'd77070336)/64'd154140672);
          if(dut.slot_mem[v][79:48]!==prior_phases[v]+expected_step[31:0] ||
              plain_runtime.slot_mem[v][79:48]!==dut.slot_mem[v][79:48])
            $fatal(1,"32voice DDS or no-expression scaling mismatch voice=%0d",v);
        end
      end
      commit_rate(0);render();
      for(integer v=0;v<32;v=v+1)send_note(v%5,48+v,0,0);
      render();
      for(integer v=0;v<32;v=v+1)
        if(dut.envelope_state[v]!=4)$fatal(1,"runtime 32voice release changed");
      // Full-width overflow/cutoff must survive the rate multiplication.
      if(dut.rate_pitch_step(54'h3fffffffffffff,1)<35'd1932735283)
        $fatal(1,"high effective step overflowed before cutoff");
      $display("PASS runtime oscillator held switch frames=%0d mute=%0d restore=%0d max_latency=%0d",frames,muted,audible,max_latency);
    end
  endtask
  task automatic panic_tail_suite;
    integer offsets[0:11];
    begin
      offsets='{0,1,2,3,4,1020,1023,1024,1025,1028,1032,1040};
      for(integer t=0;t<12;t=t+1)begin
        hard_panic();change_mode(2);send_note(t%5,60+t,127,1);
        @(negedge clk);sample_ce=1;@(negedge clk);sample_ce=0;
        repeat(offsets[t])@(negedge clk);
        panic=1;@(negedge clk);panic=0;wait_idle();
        repeat(24)begin @(negedge clk);
          if(sample_valid)$fatal(1,"quiescent asserted before cancelled tail drained");end
      end
      $display("PASS runtime oscillator PANIC quiescent 12 pipeline offsets");
    end
  endtask
  initial begin
    if(!$value$plusargs("SCENARIO=%d",scenario))scenario=0;
    repeat(5)@(negedge clk);rst=1;repeat(3)@(negedge clk);
    case(scenario)
      0:unity_suite();
      1:switching_suite();
      2:panic_tail_suite();
      3:begin
        change_mode(2);send_note(0,60,127,1);
        @(negedge clk);sample_ce=1;@(negedge clk);sample_ce=0;
        rate44=1;rate_commit=1;@(negedge clk);
        $fatal(1,"negative commit test did not reject busy commit");
      end
    endcase
    $finish;
  end
  initial begin #200000000;$fatal(1,"test watchdog");end
endmodule
