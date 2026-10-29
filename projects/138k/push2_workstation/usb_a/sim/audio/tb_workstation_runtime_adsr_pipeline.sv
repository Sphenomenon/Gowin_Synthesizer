`timescale 1ns/1ps
module tb_workstation_runtime_adsr_pipeline;
  logic clk=0;
  always #5 clk=~clk;
  logic rst=0,panic=0,mode_valid=0,event_valid=0,note_on=0;
  logic expression_valid=0,sample_ce=0,rate_commit=0,rate44=0;
  logic [1:0] mode=0;
  logic [2:0] profile=0;
  logic [6:0] note=60,velocity=100,pressure_note=60,pressure=127;
  logic [21:0] ratio=22'd1048576;
  wire [1:0] mode_ready,event_ready,expression_ready,sample_ready,sample_valid;
  wire [1:0] quiet,rate_ready,applied44,load_busy,mix_busy;
  wire [1:0] current_mode[0:1];
  wire signed [31:0] sample[0:1];
  wire [31:0] allocated[0:1],active[0:1];
  wire [5:0] active_count[0:1];
  wire [7:0] issued[0:1];
`define ENGINE(N,P) \
  workstation_runtime_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000), \
      .SEPARATE_OFF_NOTE(1),.RUNTIME_RATE_ENABLE(1),.PIPELINED_ENVELOPE(P)) N( \
      .clk_i(clk),.rst_ni(rst),.panic_i(panic),.mode_set_valid_i(mode_valid), \
      .mode_set_ready_o(mode_ready[P]),.mode_i(mode),.current_mode_o(current_mode[P]), \
      .event_valid_i(event_valid),.event_ready_o(event_ready[P]),.event_note_on_i(note_on), \
      .expression_valid_i(expression_valid),.expression_ready_o(expression_ready[P]), \
      .expression_note_i(pressure_note),.expression_value_i(pressure), \
      .event_profile_i(profile),.event_midi_note_i(note),.event_velocity_i(velocity), \
      .event_off_note_i(note),.pitch_ratio_q20_i(ratio),.sample_ce_i(sample_ce), \
      .sample_ready_o(sample_ready[P]),.sample_valid_o(sample_valid[P]),.sample_o(sample[P]), \
      .allocated_mask_o(allocated[P]),.active_mask_o(active[P]),.active_voice_count_o(active_count[P]), \
      .load_busy_o(load_busy[P]),.mix_busy_o(mix_busy[P]),.issued_slot_count_o(issued[P]), \
      .rate_commit_i(rate_commit),.rate_44100_i(rate44),.rate_ready_o(rate_ready[P]), \
      .applied_rate_44100_o(applied44[P]),.quiescent_o(quiet[P]));
  `ENGINE(before_engine,0)
  `ENGINE(dut,1)
`undef ENGINE

  integer scenario=0,cycles=0,frames=0,paired=0;
  integer outputs[0:1]='{0,0};
  integer last_output_cycle[0:1]='{0,0};
  integer max_latency[0:1]='{0,0};
  integer max_adsr_finish=0,frame_start=0,last_write_cycle=0;
  integer old_adsr_finish=0,old_last_write_cycle=0;
  integer rate_mode_latency[0:1][0:2];
  integer write_count=0,next_write_index=0;
  logic cancelled=0;
  logic signed [31:0] observed[0:1][0:4095];
  logic [31:0] random_state=32'h9013bc27;

  task automatic tick;
    @(negedge clk); #1;
  endtask
  task automatic drain;
    integer timeout;
    begin
      timeout=0;tick();
      while(quiet!==2'b11) begin tick();timeout++;
        if(timeout>1800)$fatal(1,"ADSR engine did not drain");end
      if(outputs[0]!=outputs[1] || paired!=outputs[0])
        $fatal(1,"output transaction lost at drain old=%0d new=%0d",outputs[0],outputs[1]);
    end
  endtask
  task automatic compare_frame;
    begin
      if(allocated[0]!==allocated[1] || active[0]!==active[1] ||
          active_count[0]!==active_count[1] || current_mode[0]!==current_mode[1])
        $fatal(1,"drained voice/control state mismatch");
      for(integer v=0;v<32;v++)begin
        if(allocated[1][v] && (dut.envelope_level_q24[v]!==before_engine.envelope_level_q24[v] ||
            dut.envelope_level_q18[v]!==before_engine.envelope_level_q18[v] ||
            dut.envelope_state[v]!==before_engine.envelope_state[v] ||
            dut.expression_gain_q8[v]!==before_engine.expression_gain_q8[v] ||
            dut.assigned_midi_note[v]!==before_engine.assigned_midi_note[v]))
          $fatal(1,"drained ADSR/voice mismatch voice=%0d",v);
      end
      for(integer s=0;s<1024;s++)
        if(dut.slot_mem[s]!==before_engine.slot_mem[s])$fatal(1,"canonical slot mismatch slot=%0d",s);
    end
  endtask
  task automatic hard_panic;
    begin tick();panic=1;tick();panic=0;drain();end
  endtask
  task automatic set_mode(input integer m);
    begin
      drain();mode=2'(m);mode_valid=1;tick();mode_valid=0;
      if(current_mode[1]!=2'(m))$fatal(1,"mode not applied");
    end
  endtask
  task automatic commit_rate(input logic value);
    begin
      drain();rate44=value;
      if(rate_ready!==2'b11)$fatal(1,"rate blocked after true drain");
      rate_commit=1;tick();rate_commit=0;
      if(applied44!={2{value}})$fatal(1,"rate not applied");
    end
  endtask
  task automatic send_note(input integer p,input integer n,input logic on_value);
    begin
      tick();while(event_ready!==2'b11)tick();
      profile=3'(p);note=7'(n);note_on=on_value;velocity=127;event_valid=1;
      tick();event_valid=0;note_on=0;drain();
    end
  endtask
  task automatic render;
    integer old_count[0:1];
    integer deadline;
    begin
      drain();compare_frame();
      old_count[0]=outputs[0];old_count[1]=outputs[1];
      if(sample_ready!==2'b11)$fatal(1,"frame not admissible");
      frame_start=cycles;sample_ce=1;tick();sample_ce=0;
      while(outputs[0]==old_count[0] || outputs[1]==old_count[1])tick();
      for(integer p=0;p<2;p++)
        if(last_output_cycle[p]-frame_start>max_latency[p])
          max_latency[p]=last_output_cycle[p]-frame_start;
      if(last_output_cycle[1]-frame_start>rate_mode_latency[applied44[1]][current_mode[1]])
        rate_mode_latency[applied44[1]][current_mode[1]]=last_output_cycle[1]-frame_start;
      drain();compare_frame();
      if(write_count!=32 || next_write_index!=32)$fatal(1,"not exactly32 ordered ADSR writes");
      if(last_write_cycle-frame_start>max_adsr_finish)max_adsr_finish=last_write_cycle-frame_start;
      if(old_last_write_cycle-frame_start>old_adsr_finish)old_adsr_finish=old_last_write_cycle-frame_start;
      deadline=applied44[1]?1741:1600;
      if(max_latency[1]>=deadline || last_write_cycle-frame_start>=deadline)
        $fatal(1,"component exceeded sample clock budget");
      frames++;
    end
  endtask

  always @(negedge clk)begin
    cycles++;
    if(rst)begin
      // Match ordered PCM transactions, allowing control/write cycle changes.
      for(integer p=0;p<2;p++)if(sample_valid[p])begin
        if(outputs[p]>=4096)$fatal(1,"scoreboard capacity");
        observed[p][outputs[p]]=sample[p];outputs[p]++;last_output_cycle[p]=cycles;
      end
      while(paired<outputs[0] && paired<outputs[1])begin
        if(observed[0][paired]!==observed[1][paired])
          $fatal(1,"PCM transaction mismatch output=%0d old=%0d new=%0d",paired,observed[0][paired],observed[1][paired]);
        paired++;
      end
      if(quiet[1] && (dut.g_envelope_pipeline.scale_valid || dut.g_envelope_pipeline.math_valid ||
          dut.g_envelope_pipeline.result_valid || dut.envelope_update_active || dut.envelope_update_valid ||
          dut.u_sine_interp.valid_s0 || dut.u_sine_interp.valid_s1 || dut.u_sine_interp.valid_s2 ||
          dut.u_sine_interp.valid_s3 || dut.u_sine_interp.valid_o || dut.gain_product_valid ||
          dut.envelope_product_valid || dut.finalize_valid || dut.quantizer.valid_o))
        $fatal(1,"true quiescent hid a valid token");
      if(dut.envelope_lane_busy && (sample_ready[1] || expression_ready[1] || event_ready[1]))
        $fatal(1,"accepted state-changing work before envelope pipeline drain");
    end
  end
  always @(posedge clk)if(rst)begin
    if(sample_ce && sample_ready[1])begin write_count=0;next_write_index=0;cancelled=0;end
    if(panic)cancelled=1;
    if(before_engine.envelope_update_valid && !panic)old_last_write_cycle=cycles+1;
    if(dut.envelope_write_valid && !panic)begin
      if(cancelled)$fatal(1,"cancelled ADSR token wrote after PANIC");
      if(dut.envelope_write_index!=5'(next_write_index))$fatal(1,"ADSR index/tag reordered");
      write_count++;next_write_index++;last_write_cycle=cycles+1;
    end
  end

  task automatic unity_and_rates;
    begin
      for(integer m=0;m<3;m++)begin
        hard_panic();set_mode(m);commit_rate(0);
        for(integer v=0;v<32;v++)send_note(v%5,48+v,1);
        repeat(24)render();commit_rate(1);
        repeat(24)render();commit_rate(0);
        pressure_note=60;pressure=29;expression_valid=1;tick();expression_valid=0;
        repeat(8)render();
        for(integer v=0;v<32;v++)send_note(v%5,48+v,0);
        repeat(32)render();
      end
      $display("PASS ADSR pipeline transactions frames=%0d PCM=%0d max_latency_old=%0d new=%0d ADSR_finish_old=%0d new=%0d",frames,paired,max_latency[0],max_latency[1],old_adsr_finish,max_adsr_finish);
      $display("RATE_MODE_LATENCY 48000 A=%0d B=%0d C=%0d 44100 A=%0d B=%0d C=%0d",rate_mode_latency[0][0],rate_mode_latency[0][1],rate_mode_latency[0][2],rate_mode_latency[1][0],rate_mode_latency[1][1],rate_mode_latency[1][2]);
    end
  endtask

`define SET_VOICE(N,V,S,L,A,D,U,R) \
  N.envelope_state[V]=S; N.envelope_level_q24[V]=L; N.envelope_level_q18[V]=L[23:6]; \
  N.attack_step_q24[V]=A; N.decay_step_q24[V]=D; N.sustain_level_q24[V]=U; N.release_step_q24[V]=R;
  task automatic arithmetic_boundaries;
    logic [23:0] level_value,a,d,u,r;
    logic [2:0] state_value;
    begin
      set_mode(0);for(integer v=0;v<32;v++)send_note(v%5,48+v,1);
      for(integer f=0;f<128;f++)begin
        if(f==64)commit_rate(1);
        drain();
        before_engine.allocated_mask_o=32'hffffffff;dut.allocated_mask_o=32'hffffffff;
        before_engine.voice_started_mask=32'hffffffff;dut.voice_started_mask=32'hffffffff;
        for(integer v=0;v<32;v++)begin
          random_state=random_state^(random_state<<13);random_state=random_state^(random_state>>17);
          random_state=random_state^(random_state<<5);
          level_value=random_state[23:0];a=24'(random_state*17);d=24'(random_state*31);
          u=24'(random_state*7);r=24'(random_state*13);state_value=3'((v+f)%5);
          case((v+f)%12)
            0:begin level_value=0;a=0;d=0;r=0;end
            1:begin level_value=24'hffffc0;a=1;d=1;u=24'hffffbf;r=1;end
            2:begin level_value=24'hffffbf;a=1;d=1;u=24'hffffbe;r=24'hffffbf;end
            3:begin level_value=1;a=24'hffffff;d=24'hffffff;u=24'hffffff;r=2;end
            4:begin level_value=u;d=1;r=0;end
            5:begin level_value=24'hffffff;a=24'hffffff;d=24'hffffff;u=0;r=24'hffffff;end
            default:begin end
          endcase
          `SET_VOICE(before_engine,v,state_value,level_value,a,d,u,r)
          `SET_VOICE(dut,v,state_value,level_value,a,d,u,r)
        end
        render();
        for(integer v=0;v<32;v++)
          if(dut.envelope_level_q24[v]!==before_engine.envelope_level_q24[v] ||
             dut.envelope_state[v]!==before_engine.envelope_state[v])
            $fatal(1,"edge/random arithmetic mismatch frame=%0d voice=%0d",f,v);
      end
      $display("PASS ADSR pipeline arithmetic4096 voices both rates ADSR_finish=%0d",max_adsr_finish);
    end
  endtask
`undef SET_VOICE
  task automatic cancellation;
    integer offset_value;
    begin
      for(integer t=0;t<47;t++)begin
        hard_panic();set_mode(t<40?0:2);send_note(t%5,60,1);
        sample_ce=1;tick();sample_ce=0;
        offset_value=t<40?t:1020+(t-40)*4;
        repeat(offset_value)tick();panic=1;tick();panic=0;drain();
        repeat(24)begin tick();if(sample_valid[1])$fatal(1,"post-quiescent cancelled PCM");end
        send_note((t+1)%5,61,1);render();
      end
      $display("PASS ADSR pipeline PANIC47 offsets and fresh-note reuse");
    end
  endtask
  initial begin
    if(!$value$plusargs("SCENARIO=%d",scenario))scenario=0;
    for(integer r=0;r<2;r++)for(integer m=0;m<3;m++)rate_mode_latency[r][m]=0;
    repeat(5)tick();rst=1;repeat(3)tick();
    case(scenario)
      0:unity_and_rates();
      1:arithmetic_boundaries();
      2:cancellation();
    endcase
    drain();$finish;
  end
  initial begin #100000000;$fatal(1,"ADSR pipeline watchdog");end
endmodule
