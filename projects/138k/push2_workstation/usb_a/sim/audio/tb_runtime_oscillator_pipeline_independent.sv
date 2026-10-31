`timescale 1ns/1ps
module tb_runtime_oscillator_pipeline_independent;
  logic clk=0;always #5 clk=~clk;
  logic rst=0,panic=0,ce=0,mode_valid=0,event_valid=0,note_on=0,expr_valid=0;
  logic commit=0,rate44=0;
  logic [1:0] mode=0;
  logic [2:0] profile=0;
  logic [6:0] note=60,off_note=60,velocity=100,pressure_note=60,pressure=127;
  logic [21:0] ratio=1048576;
  wire d_mode_ready,r_mode_ready,d_event_ready,r_event_ready,d_expr_ready,r_expr_ready;
  wire d_ready,r_ready,d_valid,r_valid,d_quiet,r_quiet,d_rate_ready,r_rate_ready,d_rate,r_rate;
  wire signed [31:0] d_sample,r_sample;
  wire [31:0] d_alloc,r_alloc,d_active,r_active;
  wire [5:0] d_count,r_count;
  wire [7:0] d_issued,r_issued;
  wire [1:0] d_mode,r_mode;
  wire d_load,r_load,d_mix,r_mix;
  integer frames=0,audible=0,compared_slots=0,panic_cases=0,max_latency=0,case_id=0;
  integer latency_matrix[0:1][0:2];
  integer frames_matrix[0:1][0:2];
  integer v,n,m,p,t,offset;
  logic [23:0] level,coefficient;
  `define COMMON_INPUTS \
    .clk_i(clk),.rst_ni(rst),.panic_i(panic),.sample_ce_i(ce), \
    .mode_set_valid_i(mode_valid),.mode_i(mode),.event_valid_i(event_valid), \
    .event_note_on_i(note_on),.event_profile_i(profile),.event_midi_note_i(note), \
    .event_off_note_i(off_note),.event_velocity_i(velocity), \
    .expression_valid_i(expr_valid),.expression_note_i(pressure_note), \
    .expression_value_i(pressure),.pitch_ratio_q20_i(ratio), \
    .rate_commit_i(commit),.rate_44100_i(rate44)
  workstation_runtime_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000),
    .SEPARATE_OFF_NOTE(1),.RUNTIME_RATE_ENABLE(1),.PIPELINED_ENVELOPE(1),.PIPELINED_RATE(1)) dut(
    `COMMON_INPUTS,.mode_set_ready_o(d_mode_ready),.current_mode_o(d_mode),
    .event_ready_o(d_event_ready),.expression_ready_o(d_expr_ready),
    .sample_ready_o(d_ready),.sample_valid_o(d_valid),.sample_o(d_sample),
    .allocated_mask_o(d_alloc),.active_mask_o(d_active),.active_voice_count_o(d_count),
    .load_busy_o(d_load),.mix_busy_o(d_mix),.issued_slot_count_o(d_issued),
    .rate_ready_o(d_rate_ready),.applied_rate_44100_o(d_rate),.quiescent_o(d_quiet));
  fc_reference_oscillator #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000),
    .SEPARATE_OFF_NOTE(1),.RUNTIME_RATE_ENABLE(1)) reference_engine(
    `COMMON_INPUTS,.mode_set_ready_o(r_mode_ready),.current_mode_o(r_mode),
    .event_ready_o(r_event_ready),.expression_ready_o(r_expr_ready),
    .sample_ready_o(r_ready),.sample_valid_o(r_valid),.sample_o(r_sample),
    .allocated_mask_o(r_alloc),.active_mask_o(r_active),.active_voice_count_o(r_count),
    .load_busy_o(r_load),.mix_busy_o(r_mix),.issued_slot_count_o(r_issued),
    .rate_ready_o(r_rate_ready),.applied_rate_44100_o(r_rate),.quiescent_o(r_quiet));
  `undef COMMON_INPUTS

  task automatic idle;
    integer ticks;
    begin
      @(negedge clk);ticks=0;
      while(!d_quiet || !r_quiet)begin
        @(negedge clk);ticks=ticks+1;
        if(ticks>1800)$fatal(1,"OSC_IDLE case=%0d quiet=%b/%b",case_id,d_quiet,r_quiet);
      end
    end
  endtask
  task automatic compare_state;
    begin
      if({d_alloc,d_active,d_count,d_mode,d_rate} !== {r_alloc,r_active,r_count,r_mode,r_rate})
        $fatal(1,"OSC_PUBLIC_STATE case=%0d frame=%0d",case_id,frames);
      for(integer i=0;i<1024;i=i+1)begin
        if(dut.slot_mem[i] !== reference_engine.slot_mem[i])
          $fatal(1,"OSC_SLOT case=%0d frame=%0d slot=%0d dut=%h ref=%h",case_id,frames,i,dut.slot_mem[i],reference_engine.slot_mem[i]);
        compared_slots=compared_slots+1;
      end
      for(integer i=0;i<32;i=i+1)begin
        if({dut.envelope_level_q24[i],dut.envelope_state[i],dut.expression_gain_q8[i]} !==
           {reference_engine.envelope_level_q24[i],reference_engine.envelope_state[i],reference_engine.expression_gain_q8[i]})
          $fatal(1,"OSC_ENVELOPE case=%0d frame=%0d voice=%0d dut=%h/%h ref=%h/%h",case_id,frames,i,dut.envelope_level_q24[i],dut.envelope_state[i],reference_engine.envelope_level_q24[i],reference_engine.envelope_state[i]);
      end
    end
  endtask
  task automatic render;
    integer ticks,dc,rc;
    logic signed [31:0] ds,rs;
    begin
      idle();if(!d_ready || !r_ready)$fatal(1,"OSC_READY");
      ce=1;@(negedge clk);ce=0;ticks=0;dc=0;rc=0;
      while(!d_quiet || !r_quiet || dc==0 || rc==0)begin
        if(d_valid)begin dc=dc+1;ds=d_sample;end
        if(r_valid)begin rc=rc+1;rs=r_sample;end
        @(negedge clk);ticks=ticks+1;
        if(ticks>1599)$fatal(1,"OSC_FRAME_DEADLINE case=%0d",case_id);
      end
      if(dc!=1 || rc!=1 || ds!==rs)
        $fatal(1,"OSC_PCM case=%0d frame=%0d count=%0d/%0d dut=%0d ref=%0d",case_id,frames,dc,rc,ds,rs);
      if(ds!=0)audible=audible+1;
      frames=frames+1;if(ticks>max_latency)max_latency=ticks;
      frames_matrix[d_rate][d_mode]=frames_matrix[d_rate][d_mode]+1;
      if(ticks>latency_matrix[d_rate][d_mode])latency_matrix[d_rate][d_mode]=ticks;
      compare_state();
    end
  endtask
  task automatic clear;
    begin idle();panic=1;@(negedge clk);
      if(dut.arithmetic_busy)$fatal(1,"OSC_PANIC_ARITHMETIC_FLUSH");
      panic=0;idle();end
  endtask
  task automatic setmode(input integer value);
    begin idle();mode=2'(value);mode_valid=1;@(negedge clk);mode_valid=0;idle();end
  endtask
  task automatic setrate(input bit value);
    begin
      idle();if(!d_rate_ready || !r_rate_ready)$fatal(1,"OSC_RATE_READY");
      rate44=value;commit=1;@(negedge clk);commit=0;idle();
      if(d_rate!==value || r_rate!==value)$fatal(1,"OSC_RATE_COMMIT");
    end
  endtask
  task automatic send(input bit on_value,input integer midi,input integer vel);
    begin
      idle();if(!d_event_ready || !r_event_ready)$fatal(1,"OSC_EVENT_READY");
      note=7'(midi);off_note=7'(midi);velocity=7'(vel);note_on=on_value;event_valid=1;
      @(negedge clk);event_valid=0;note_on=0;idle();
    end
  endtask
  task automatic load_all;
    begin
      for(integer i=0;i<32;i=i+1)send(1,48+i,40+(i*13)%88);
      if(d_alloc!=32'hffffffff || r_alloc!=32'hffffffff)$fatal(1,"OSC_ALLOCATION");
    end
  endtask
  task automatic seed_envelope_edges;
    logic [23:0] l,c;
    begin
      idle();
      for(integer i=0;i<32;i=i+1)begin
        case(i%8)
          0:begin l=0;c=0;end
          1:begin l=1;c=1;end
          2:begin l=24'hffffbf;c=73;end
          3:begin l=24'hffffc0;c=147;end
          4:begin l=24'h800000;c=24'hffffff;end
          5:begin l=24'h7fffff;c=24'hffffc0;end
          6:begin l=24'h400000;c=24'd154139;end
          default:begin l=24'h000093;c=24'd146;end
        endcase
        dut.envelope_level_q24[i]=l;reference_engine.envelope_level_q24[i]=l;
        dut.envelope_state[i]=3'(i%5);reference_engine.envelope_state[i]=3'(i%5);
        dut.attack_step_q24[i]=c;reference_engine.attack_step_q24[i]=c;
        dut.decay_step_q24[i]=c;reference_engine.decay_step_q24[i]=c;
        dut.release_step_q24[i]=c;reference_engine.release_step_q24[i]=c;
        dut.sustain_level_q24[i]=24'h400000;reference_engine.sustain_level_q24[i]=24'h400000;
      end
    end
  endtask
  task automatic cancel_and_reuse(input integer delay_cycles);
    begin
      idle();ce=1;@(negedge clk);ce=0;
      repeat(delay_cycles)@(negedge clk);
      panic=1;@(negedge clk);
      if(dut.arithmetic_busy)$fatal(1,"OSC_PANIC_ARITHMETIC_FLUSH");
      panic=0;idle();
      if(d_alloc!=0 || r_alloc!=0)$fatal(1,"OSC_PANIC_ALLOCATION");
      // Reload all reachable slots after cancellation. Cancelled frame's
      // partially advanced phase is deliberately unreachable after PANIC.
      load_all();render();render();panic_cases=panic_cases+1;
    end
  endtask

  always @(negedge clk)if(rst && d_quiet &&
      (dut.arithmetic_busy || dut.envelope_lane_busy || dut.sine_valid_o ||
       dut.gain_product_valid || dut.envelope_product_valid || dut.finalize_valid || d_valid))
    $fatal(1,"OSC_QUIESCENT_HIDDEN_TAIL");

  initial begin
    for(integer r=0;r<2;r=r+1)for(integer q=0;q<3;q=q+1)begin
      latency_matrix[r][q]=0;frames_matrix[r][q]=0;
    end
    repeat(5)@(negedge clk);rst=1;
    for(integer rate=0;rate<2;rate=rate+1)begin
      setrate(1'(rate));
      for(m=0;m<3;m=m+1)for(p=0;p<5;p=p+1)begin
        case_id=rate*100+m*10+p;
        clear();setmode(m);profile=3'(p);ratio=22'(1048576+p*14321);
        load_all();
        for(t=0;t<8;t=t+1)render();
        seed_envelope_edges();for(t=0;t<5;t=t+1)render();
        ratio=22'h3fffff;for(t=0;t<3;t=t+1)render();
        for(v=0;v<32;v=v+1)send(0,48+v,1);
        for(t=0;t<4;t=t+1)render();
      end
      clear();setmode(2);profile=0;ratio=22'd1048576;load_all();render();render();
      for(n=0;n<17;n=n+1)begin
        case(n)
          0:offset=0;1:offset=1;2:offset=2;3:offset=3;4:offset=4;
          5:offset=8;6:offset=16;7:offset=22;8:offset=24;
          9:offset=27;10:offset=31;11:offset=35;12:offset=63;
          13:offset=1022;14:offset=1023;15:offset=1024;default:offset=1040;
        endcase
        case_id=rate*1000+500+n;cancel_and_reuse(offset);
      end
    end
    if(frames<600 || audible<100 || panic_cases!=34 || max_latency>1599)
      $fatal(1,"OSC_COVERAGE frames=%0d audible=%0d panic=%0d max=%0d",frames,audible,panic_cases,max_latency);
    for(integer r=0;r<2;r=r+1)for(integer q=0;q<3;q=q+1)
      $display("OSC_LATENCY rate=%0d mode=%0d frames=%0d max_cycles=%0d",r!=0?44100:48000,q,frames_matrix[r][q],latency_matrix[r][q]);
    $display("OSC_PIPELINE_INDEPENDENT_PASS frames=%0d audible=%0d slots=%0d panic=%0d max_latency=%0d",frames,audible,compared_slots,panic_cases,max_latency);
    $finish;
  end
  initial begin #100000000; $fatal(1,"OSC_GLOBAL_TIMEOUT");end
endmodule
