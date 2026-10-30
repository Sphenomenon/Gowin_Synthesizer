`timescale 1ns/1ps
module tb_runtime_vector_pipeline_independent;
  logic clk=0;always #5 clk=~clk;
  logic rst=0,panic=0,ce=0,rate44=0,ev=0,note_on=0;
  logic [6:0] note=69,off_note=69,velocity=127,rotation=0;
  logic [2:0] shape=0,destination=1,profile=0;
  logic [21:0] pitch=1048576,own_pitch=1048576;
  logic [15:0] morph=0,scale=32768;
  logic signed [15:0] cal_x=16384,cal_y=16384;
  logic signed [31:0] offset_x=0,offset_y=0;
  wire dr,rr,dv,rv,der,rer,db,rb;
  wire signed [31:0] dl,rl,dy,ry;
  wire [7:0] da,ra;
  wire [3:0] dc,rc;
  wire [31:0] dj,rj;
  wire de,re,df,rf,dclip,rclip;
  integer frames=0,audible=0,voice_checks=0,cache_checks=0,panic_cases=0,max_latency=0,case_id=0;
  integer p,n,t,v,offset;
  bit reloading=0;
  `define COMMON_INPUTS \
    .clk_i(clk),.rst_ni(rst),.panic_i(panic),.sample_ce_i(ce),.rate_44k1_i(rate44), \
    .event_valid_i(ev),.event_note_on_i(note_on),.event_note_i(note),.event_off_note_i(off_note), \
    .event_velocity_i(velocity),.event_shape_i(shape),.event_morph_shape_i(destination), \
    .event_profile_i(profile),.event_pitch_q20_i(own_pitch),.pitch_q20_i(pitch), \
    .morph_q15_i(morph),.scale_q15_i(scale),.rotation_i(rotation), \
    .cal_x_q14_i(cal_x),.cal_y_q14_i(cal_y),.offset_x_i(offset_x),.offset_y_i(offset_y)
  workstation_runtime_scope_vec #(.SEPARATE_OFF_NOTE(1),.PIPELINED_RATE(1)) dut(
    `COMMON_INPUTS,.sample_ready_o(dr),.sample_valid_o(dv),.left_o(dl),.right_o(dy),
    .event_ready_o(der),.busy_o(db),.active_mask_o(da),.active_count_o(dc),
    .rejected_events_o(dj),.config_error_o(de),.frequency_error_o(df),.clip_o(dclip));
  fc_reference_vector #(.SEPARATE_OFF_NOTE(1)) reference_engine(
    `COMMON_INPUTS,.sample_ready_o(rr),.sample_valid_o(rv),.left_o(rl),.right_o(ry),
    .event_ready_o(rer),.busy_o(rb),.active_mask_o(ra),.active_count_o(rc),
    .rejected_events_o(rj),.config_error_o(re),.frequency_error_o(rf),.clip_o(rclip));
  `undef COMMON_INPUTS

  task automatic idle;
    integer ticks;
    begin
      @(negedge clk);ticks=0;
      while(!dr || !rr || dv || rv || db || rb)begin
        @(negedge clk);ticks=ticks+1;if(ticks>1600)$fatal(1,"VEC_IDLE case=%0d",case_id);
      end
    end
  endtask
  task automatic compare_state;
    begin
      if({da,dc,dj,de,df} !== {ra,rc,rj,re,rf})
        $fatal(1,"VEC_PUBLIC_STATE case=%0d frame=%0d dut=%h/%h/%h/%b/%b ref=%h/%h/%h/%b/%b",case_id,frames,da,dc,dj,de,df,ra,rc,rj,re,rf);
      for(integer i=0;i<8;i=i+1)begin
        if({dut.phase[i],dut.base_step[i],dut.own_pitch[i],dut.note[i],dut.shape[i],dut.morph_shape[i],
            dut.envelope[i],dut.env_state[i],dut.attack[i],dut.decay[i],dut.sustain[i],dut.release_step[i],dut.velocity[i]} !==
           {reference_engine.phase[i],reference_engine.base_step[i],reference_engine.own_pitch[i],reference_engine.note[i],
            reference_engine.shape[i],reference_engine.morph_shape[i],reference_engine.envelope[i],reference_engine.env_state[i],
            reference_engine.attack[i],reference_engine.decay[i],reference_engine.sustain[i],reference_engine.release_step[i],reference_engine.velocity[i]})
          $fatal(1,"VEC_VOICE case=%0d frame=%0d voice=%0d phase=%h/%h env=%h/%h",case_id,frames,i,dut.phase[i],reference_engine.phase[i],dut.envelope[i],reference_engine.envelope[i]);
        if({dut.attack_44[i],dut.decay_44[i],dut.release_44[i]} !==
           {reference_engine.attack_44[i],reference_engine.decay_44[i],reference_engine.release_44[i]})
          $fatal(1,"VEC_COEFFICIENT case=%0d voice=%0d",case_id,i);
        voice_checks=voice_checks+1;cache_checks=cache_checks+3;
      end
      if({dut.morph,dut.scale,dut.rotation,dut.slew_remainder,dut.rotation_remainder} !==
         {reference_engine.morph,reference_engine.scale,reference_engine.rotation,reference_engine.slew_remainder,reference_engine.rotation_remainder})
        $fatal(1,"VEC_HELD_CONTROL case=%0d frame=%0d",case_id,frames);
    end
  endtask
  task automatic render(input bit perturb);
    integer ticks,dseen,rseen;
    logic signed [31:0] dx,rx,dy1,ry1;
    logic dcl,rcl,original_rate;
    begin
      idle();original_rate=rate44;ce=1;@(negedge clk);ce=0;ticks=0;dseen=0;rseen=0;
      while(!dr || !rr || dv || rv || db || rb || dseen==0 || rseen==0)begin
        if(dv)begin dseen=dseen+1;dx=dl;dy1=dy;dcl=dclip;end
        if(rv)begin rseen=rseen+1;rx=rl;ry1=ry;rcl=rclip;end
        if(perturb && ticks==7)rate44=~rate44;
        @(negedge clk);ticks=ticks+1;if(ticks>1599)$fatal(1,"VEC_FRAME_DEADLINE case=%0d",case_id);
      end
      rate44=original_rate;
      if(dseen!=1 || rseen!=1 || {dx,dy1,dcl} !== {rx,ry1,rcl})
        $fatal(1,"VEC_PCM case=%0d frame=%0d count=%0d/%0d x=%0d/%0d y=%0d/%0d clip=%b/%b",case_id,frames,dseen,rseen,dx,rx,dy1,ry1,dcl,rcl);
      if(dx!=0 || dy1!=0)audible=audible+1;
      frames=frames+1;if(ticks>max_latency)max_latency=ticks;compare_state();
    end
  endtask
  task automatic clear;
    begin idle();panic=1;@(negedge clk);panic=0;idle();end
  endtask
  task automatic send(input bit on_value,input integer midi);
    begin
      idle();if(!der || !rer)$fatal(1,"VEC_EVENT_READY");
      note=7'(midi);off_note=7'(midi);note_on=on_value;ev=1;
      @(negedge clk);ev=0;note_on=0;idle();if(!reloading)compare_state();
    end
  endtask
  task automatic load_all;
    begin
      reloading=1;
      for(integer i=0;i<8;i=i+1)begin
        shape=3'(i);destination=3'((i+3)%8);velocity=7'(32+i*11);own_pitch=22'(1048576+i*1234);send(1,60+i);
      end
      if(da!=8'hff || ra!=8'hff)$fatal(1,"VEC_ALLOCATION");
      reloading=0;compare_state();
    end
  endtask
  task automatic cancel_and_reuse(input integer delay_cycles);
    begin
      idle();ce=1;@(negedge clk);ce=0;repeat(delay_cycles)@(negedge clk);
      panic=1;@(negedge clk);panic=0;idle();
      if(da!=0 || ra!=0)$fatal(1,"VEC_PANIC_ALLOCATION");
      load_all();render(0);render(1);panic_cases=panic_cases+1;
    end
  endtask
  task automatic cancel_note_and_reuse(input integer delay_cycles);
    begin
      clear();idle();note=69;off_note=69;velocity=127;own_pitch=1048576;shape=0;destination=1;
      ev=1;note_on=1;@(negedge clk);ev=0;note_on=0;
      repeat(delay_cycles)@(negedge clk);
      panic=1;@(negedge clk);panic=0;idle();
      if(da!=0 || ra!=0)$fatal(1,"VEC_NOTE_PANIC_ALLOCATION");
      load_all();render(0);render(1);panic_cases=panic_cases+1;
    end
  endtask

  always @(negedge clk)if(rst && dr && !dut.pipeline_quiet)
    $fatal(1,"VEC_READY_HIDDEN_PIPELINE");

  initial begin
    repeat(5)@(negedge clk);rst=1;
    for(integer rate=0;rate<2;rate=rate+1)begin
      idle();rate44=1'(rate);
      for(p=0;p<5;p=p+1)begin
        case_id=rate*100+p;clear();profile=3'(p);pitch=22'd1048576;
        morph=16'(p*7000);rotation=7'(p*23);scale=16'(32768-p*1000);
        offset_x=32'sd12345*p;offset_y=-32'sd23456*p;load_all();
        for(t=0;t<32;t=t+1)render(1'(t%2));
        pitch=22'h3fffff;for(t=0;t<8;t=t+1)render(0);
        pitch=22'd1;for(t=0;t<4;t=t+1)render(0);
        // Exact zero/overflow/limit decisions for active and inactive voices.
        idle();dut.base_step[0]=0;reference_engine.base_step[0]=0;render(0);
        idle();dut.base_step[0]=32'hffffffff;reference_engine.base_step[0]=32'hffffffff;
        dut.own_pitch[0]=22'h3fffff;reference_engine.own_pitch[0]=22'h3fffff;
        pitch=22'h3fffff;render(0);
        for(v=0;v<8;v=v+1)send(0,60+v);
        for(t=0;t<12;t=t+1)render(0);
      end
      clear();profile=0;pitch=22'd1048576;load_all();render(0);render(0);
      for(n=0;n<14;n=n+1)begin
        case(n)
          0:offset=0;1:offset=1;2:offset=2;3:offset=3;4:offset=4;5:offset=8;
          6:offset=13;7:offset=18;8:offset=21;9:offset=23;10:offset=30;
          11:offset=100;12:offset=250;default:offset=280;
        endcase
        case_id=rate*1000+500+n;cancel_and_reuse(offset);
      end
      for(n=0;n<6;n=n+1)begin
        case(n)
          0:offset=0;1:offset=1;2:offset=6;3:offset=12;4:offset=14;default:offset=16;
        endcase
        case_id=rate*1000+600+n;cancel_note_and_reuse(offset);
      end
    end
    if(frames<600 || audible<100 || panic_cases!=40 || max_latency>1599)
      $fatal(1,"VEC_COVERAGE frames=%0d audible=%0d panic=%0d max=%0d",frames,audible,panic_cases,max_latency);
    $display("VECTOR_PIPELINE_INDEPENDENT_PASS frames=%0d audible=%0d voices=%0d coeff=%0d panic=%0d max_latency=%0d",frames,audible,voice_checks,cache_checks,panic_cases,max_latency);
    $finish;
  end
  initial begin #100000000;$fatal(1,"VEC_GLOBAL_TIMEOUT");end
endmodule
