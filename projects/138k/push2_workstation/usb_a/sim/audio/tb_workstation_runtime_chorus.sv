`timescale 1ns/1ps
module tb_workstation_runtime_chorus;
  reg clk=0;always #7 clk=~clk;
  reg rst_n=0,clear_i=0,valid_i=0,enabled_i=1;
  reg signed [31:0] left_i=0,right_i=0;
  reg config_valid=0,history_clear=0,rate_44=0;
  wire ready,valid_o,active,clip,config_ready,config_applied,history_ready,history_done,quiet,rate;
  wire signed [31:0] left_o,right_o;
  workstation_runtime_chorus_effect u_dut(
      .clk_i(clk),.rst_ni(rst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
      .left_i(left_i),.right_i(right_i),.ready_o(ready),.valid_o(valid_o),.active_o(active),
      .left_o(left_o),.right_o(right_o),.clip_o(clip),.config_valid_i(config_valid),
      .rate_44100_i(rate_44),.history_clear_i(history_clear),.config_ready_o(config_ready),
      .config_applied_o(config_applied),.history_ready_o(history_ready),.history_done_o(history_done),
      .quiescent_o(quiet),.applied_rate_44100_o(rate));
  wire old_ready,old_valid,old_active,old_clip,old_config_ready,old_config_applied;
  wire old_history_ready,old_history_done,old_quiet,old_rate;
  wire signed [31:0] old_left,old_right;
  workstation_before_affine44_chorus_effect u_before_affine44(
      .clk_i(clk),.rst_ni(rst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
      .left_i(left_i),.right_i(right_i),.ready_o(old_ready),.valid_o(old_valid),.active_o(old_active),
      .left_o(old_left),.right_o(old_right),.clip_o(old_clip),.config_valid_i(config_valid),
      .rate_44100_i(rate_44),.history_clear_i(history_clear),.config_ready_o(old_config_ready),
      .config_applied_o(old_config_applied),.history_ready_o(old_history_ready),.history_done_o(old_history_done),
      .quiescent_o(old_quiet),.applied_rate_44100_o(old_rate));
  integer exact_half_cycles=0;
  // The exact whole M12 module receives every input, including reset/cancel.
  // Check both edges after NBA settling, including held PCM when valid is low.
  always @(clk)begin
    #1;
    if({ready,valid_o,active,left_o,right_o,clip,config_ready,config_applied,
        history_ready,history_done,quiet,rate} !==
       {old_ready,old_valid,old_active,old_left,old_right,old_clip,old_config_ready,old_config_applied,
        old_history_ready,old_history_done,old_quiet,old_rate})
      $fatal(1,"M12/new public output mismatch");
    if({u_dut.pointer,u_dut.read_address,u_dut.frames,u_dut.state,u_dut.gain,u_dut.lfo,
        u_dut.chorus_delay,u_dut.gain_remainder,u_dut.lfo_remainder,u_dut.input_l,u_dut.input_r,
        u_dut.read_l,u_dut.read_r,u_dut.product_l,u_dut.product_r,u_dut.mixed_l,u_dut.mixed_r} !==
       {u_before_affine44.pointer,u_before_affine44.read_address,u_before_affine44.frames,
        u_before_affine44.state,u_before_affine44.gain,u_before_affine44.lfo,
        u_before_affine44.chorus_delay,u_before_affine44.gain_remainder,u_before_affine44.lfo_remainder,
        u_before_affine44.input_l,u_before_affine44.input_r,u_before_affine44.read_l,u_before_affine44.read_r,
        u_before_affine44.product_l,u_before_affine44.product_r,u_before_affine44.mixed_l,u_before_affine44.mixed_r})
      $fatal(1,"M12/new complete Chorus state mismatch");
    exact_half_cycles=exact_half_cycles+1;
  end
  wire ref_ready,ref_valid,ref_active,ref_clip;
  wire signed [31:0] ref_l,ref_r;
  serial_chorus_effect u_ref(
      .clk_i(clk),.rst_ni(rst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
      .left_i(left_i),.right_i(right_i),.ready_o(ref_ready),.valid_o(ref_valid),
      .active_o(ref_active),.left_o(ref_l),.right_o(ref_r),.clip_o(ref_clip));

  reg compare48=0,model_on=0,model_rate=0,expected_pending=0;
  integer outputs=0,compared=0,clips=0,model_frames=0,model_pointer=0;
  integer model_gain=0,gain_fraction=0,lfo_fraction=0,model_phase=0;
  integer triangle_value,delay_frames,gain_step,lfo_step,index;
  integer min_delay=10000,max_delay=0,lfo_wraps=0,acks=0;
  reg signed [31:0] memory_l[0:1023],memory_r[0:1023],expected_l,expected_r;
  reg expected_clip;
  longint signed wet_l,wet_r,mix_l,mix_r,physical_q16;
  function automatic longint signed rounded(input longint signed value,input integer shift);
    longint signed magnitude;
    begin
      magnitude=value<0 ? -value : value;
      magnitude=(magnitude+(64'sd1<<(shift-1)))>>>shift;
      rounded=value<0 ? -magnitude : magnitude;
    end
  endfunction
  function automatic logic signed [31:0] saturated(input longint signed value);
    if(value>2147483647)saturated=32'sh7fffffff;
    else if(value< -64'sd2147483648)saturated=32'sh80000000;
    else saturated=32'(value);
  endfunction
  always @(posedge clk)if(rst_n && model_on)begin
    if(clear_i || (config_valid && config_ready) || (history_clear && history_ready))begin
      model_frames=0;model_pointer=0;expected_pending=0;
      if(clear_i)begin model_gain=0;gain_fraction=0;end
      if(config_valid && config_ready)model_rate=rate_44;
    end else if(valid_i && ready)begin
      if(expected_pending)$fatal(1,"missing model output");
      triangle_value=(model_phase>>7)&65535;if((model_phase&8388608)!=0)triangle_value=65535-triangle_value;
      physical_q16=64'sd480*65536+64'(triangle_value)*96;
      // Independent integer nearest conversion of physical time;48k is the
      // exact original integer tap rule,44.1 rounds the continuous Q16 delay.
      if(model_rate)delay_frames=32'((physical_q16*44100+64'sd1572864000)/(64'sd48000*65536));
      else delay_frames=480+(triangle_value*96)/65536;
      if(delay_frames<min_delay)min_delay=delay_frames;
      if(delay_frames>max_delay)max_delay=delay_frames;
      gain_step=128;lfo_step=349;
      if(model_rate)begin
        gain_fraction=gain_fraction+47;gain_step=139;
        if(gain_fraction>=147)begin gain_fraction=gain_fraction-147;gain_step=140;end
        lfo_fraction=lfo_fraction+127;lfo_step=379;
        if(lfo_fraction>=147)begin lfo_fraction=lfo_fraction-147;lfo_step=380;end
      end
      if(enabled_i)model_gain=model_gain+gain_step>8192 ? 8192 : model_gain+gain_step;
      else model_gain=model_gain<gain_step ? 0 : model_gain-gain_step;
      index=(model_pointer-delay_frames+1024)%1024;
      wet_l=model_frames>=delay_frames ? 64'(memory_l[index]) : 0;
      wet_r=model_frames>=delay_frames ? 64'(memory_r[index]) : 0;
      mix_l=64'(left_i)+rounded(wet_l*64'(model_gain),15);
      mix_r=64'(right_i)+rounded(wet_r*64'(model_gain),15);
      expected_l=saturated(mix_l);expected_r=saturated(mix_r);
      expected_clip=mix_l>2147483647 || mix_l< -64'sd2147483648 ||
          mix_r>2147483647 || mix_r< -64'sd2147483648;
      memory_l[model_pointer]=left_i;memory_r[model_pointer]=right_i;
      model_frames=model_frames+1;model_pointer=(model_pointer+1)%1024;
      model_phase=model_phase+lfo_step;
      if(model_phase>=16777216)lfo_wraps=lfo_wraps+1;
      model_phase=model_phase%16777216;expected_pending=1;
    end
  end
  always @(negedge clk)if(rst_n)begin
    if(config_applied || history_done)acks=acks+1;
    if(compare48)begin
      if({ready,valid_o,active}!={ref_ready,ref_valid,ref_active})$fatal(1,"48k control mismatch");
      if(valid_o)begin
        if({left_o,right_o,clip}!={ref_l,ref_r,ref_clip})$fatal(1,"48k PCM/clip mismatch");
        if(u_dut.lfo!=u_ref.lfo || u_dut.chorus_delay!=u_ref.chorus_delay)$fatal(1,"48k phase/tap mismatch");
        compared=compared+1;
      end
    end
    if(valid_o)begin
      outputs=outputs+1;if(clip)clips=clips+1;
      if(model_on)begin
        if(!expected_pending || {left_o,right_o,clip}!={expected_l,expected_r,expected_clip})
          $fatal(1,"model PCM/clip mismatch frame %0d rate%0d got %h,%h expected%h,%h",model_frames,model_rate,left_o,right_o,expected_l,expected_r);
        if(u_dut.lfo!=24'(model_phase) || u_dut.chorus_delay!=16'(delay_frames) ||
           u_dut.gain!=16'(model_gain) || u_dut.gain_remainder!=8'(gain_fraction) ||
           u_dut.lfo_remainder!=8'(lfo_fraction))$fatal(1,"model phase/tap/slew state mismatch");
        expected_pending=0;compared=compared+1;
      end
    end
  end
  reg [31:0] random_state=32'h625ab114;
  task automatic frame(input logic signed [31:0] l,r,input logic enable);
    begin
      @(negedge clk);if(!ready)$fatal(1,"frame refused");
      left_i=l;right_i=r;enabled_i=enable;valid_i=1;
      @(negedge clk);valid_i=0;repeat(10)@(negedge clk);
    end
  endtask
  task automatic random_frame;
    reg signed [31:0] l,r;reg en;
    begin
      random_state=(random_state>>1)^(random_state[0]?32'h80200003:0);l=32'(random_state);
      random_state=(random_state>>1)^(random_state[0]?32'h80200003:0);r=32'(random_state);
      en=random_state[7];frame(l,r,en);
    end
  endtask
  task automatic configure(input logic next_rate,input logic history_only);
    integer saved_gain,saved_phase,saved_gain_frac,saved_lfo_frac,previous_acks;
    begin
      @(negedge clk);
      if(!config_ready || !history_ready)$fatal(1,"request outside quiescence");
      saved_gain=32'(u_dut.gain);saved_phase=32'(u_dut.lfo);
      saved_gain_frac=32'(u_dut.gain_remainder);saved_lfo_frac=32'(u_dut.lfo_remainder);
      previous_acks=acks;
      rate_44=next_rate;config_valid=!history_only;history_clear=history_only;
      @(negedge clk);config_valid=0;history_clear=0;
      repeat(2)@(negedge clk);
      if(acks!=previous_acks+1 || u_dut.frames!=0 || u_dut.pointer!=0 ||
         u_dut.gain!=16'(saved_gain) || u_dut.lfo!=24'(saved_phase) ||
         u_dut.gain_remainder!=8'(saved_gain_frac) || u_dut.lfo_remainder!=8'(saved_lfo_frac))
        $fatal(1,"configuration/history changed preserved state");
      if(!history_only && rate!=next_rate)$fatal(1,"wrong committed rate");
    end
  endtask
  integer scenario=0,i,saved_phase,saved_gain_frac,saved_lfo_frac;
  initial begin
    if(!$value$plusargs("SCENARIO=%d",scenario))scenario=0;
    repeat(10)@(negedge clk);rst_n=1;repeat(4)@(negedge clk);
    case(scenario)
      0:begin
        compare48=1;
        for(i=0;i<60000;i=i+1)begin
          random_frame();
          if(i==9999)begin
            compare48=0;clear_i=1;@(negedge clk);clear_i=0;
            repeat(2)@(negedge clk);compare48=1;
          end
        end
        if(compared!=60000 || clips==0)$fatal(1,"48k reference coverage");
        $display("PASS runtime Chorus48k per-cycle frames=%0d clips=%0d",compared,clips);
      end
      1:begin
        model_on=1;configure(1,0);
        for(i=0;i<60000;i=i+1)random_frame();
        if(compared!=60000 || lfo_wraps<1 || min_delay!=441 || max_delay!=529 || clips==0)
          $fatal(1,"44.1 model coverage");
        $display("PASS runtime Chorus44.1 fixed point frames=%0d lfo_wraps=%0d delay=%0d..%0d clips=%0d",compared,lfo_wraps,min_delay,max_delay,clips);
      end
      2:begin
        model_on=1;
        for(i=0;i<1200;i=i+1)random_frame();
        configure(1,0);
        for(i=0;i<1200;i=i+1)random_frame();
        configure(0,1);
        for(i=0;i<1200;i=i+1)random_frame();
        configure(0,0);
        for(i=0;i<1200;i=i+1)random_frame();
        configure(1,0);
        for(i=0;i<1200;i=i+1)random_frame();
        if(compared!=6000 || acks!=4)$fatal(1,"switch coverage");
        $display("PASS runtime Chorus switches/history preserve phase gain fractions frames=%0d",compared);
      end
      3:begin
        configure(1,0);
        for(i=0;i<5;i=i+1)begin
          repeat(20)frame(32'sh12345678,-32'sh23456789,1);
          @(negedge clk);valid_i=1;@(negedge clk);valid_i=0;
          repeat(i)@(negedge clk);
          saved_phase=32'(u_dut.lfo);saved_lfo_frac=32'(u_dut.lfo_remainder);
          clear_i=1;repeat(2)@(negedge clk);
          if(valid_o || u_dut.state!=0 || u_dut.frames!=0 || u_dut.gain!=0 ||
             u_dut.lfo!=24'(saved_phase) || u_dut.lfo_remainder!=8'(saved_lfo_frac))
            $fatal(1,"legacy clear cancellation/phase changed");
          clear_i=0;repeat(2)@(negedge clk);
          frame(32'sh12345678,-32'sh23456789,1);
          if(left_o!=32'sh12345678 || right_o!=-32'sh23456789)$fatal(1,"history leaked after clear");
        end
        $display("PASS runtime Chorus legacy clear aborts five FSM states and retains LFO phase");
      end
      4:begin
        @(negedge clk);valid_i=1;config_valid=1;history_clear=1;rate_44=1;
        #1;if(config_ready || history_ready)$fatal(1,"configuration raced accepted sample");
        @(negedge clk);valid_i=0;
        wait(config_applied);@(negedge clk);config_valid=0;history_clear=0;
        repeat(3)@(negedge clk);
        if(acks!=1 || outputs!=1 || !rate)$fatal(1,"held config/history priority failure");
        $display("PASS runtime Chorus configuration backpressure and history priority");
      end
      default:$fatal(1,"unknown scenario");
    endcase
    $display("PASS exact M12/new complete Chorus half-cycle comparisons=%0d public_outputs=12",exact_half_cycles);
    $finish;
  end
  initial begin #100000000;$fatal(1,"Chorus verification watchdog");end
endmodule
