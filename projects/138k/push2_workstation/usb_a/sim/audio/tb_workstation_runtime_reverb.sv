`timescale 1ns/1ps
module tb_workstation_runtime_reverb;
  reg clk=0;always #7 clk=~clk;
  reg rst_n=0,clear_i=0,valid_i=0,enabled_i=1,config_valid=0,history_clear=0,rate_44=0;
  reg signed [31:0] left_i=0,right_i=0;
  wire ready,valid_o,active,clip,config_ready,config_applied,history_ready,history_done,quiet,rate;
  wire signed [31:0] left_o,right_o;
  workstation_runtime_spatial_reverb u_dut(
      .clk_i(clk),.rst_ni(rst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
      .left_i(left_i),.right_i(right_i),.ready_o(ready),.valid_o(valid_o),.active_o(active),
      .left_o(left_o),.right_o(right_o),.clip_o(clip),.config_valid_i(config_valid),
      .rate_44100_i(rate_44),.history_clear_i(history_clear),.config_ready_o(config_ready),
      .config_applied_o(config_applied),.history_ready_o(history_ready),.history_done_o(history_done),
      .quiescent_o(quiet),.applied_rate_44100_o(rate));
  wire ref_ready,ref_valid,ref_active,ref_clip;
  wire signed [31:0] ref_l,ref_r;
  serial_spatial_reverb u_ref(
      .clk_i(clk),.rst_ni(rst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
      .left_i(left_i),.right_i(right_i),.ready_o(ref_ready),.valid_o(ref_valid),
      .active_o(ref_active),.left_o(ref_l),.right_o(ref_r),.clip_o(ref_clip));
  reg compare48=0;
  integer outputs=0,compared=0,clips=0,acks=0,max_latency=0,frame_latency=0;
  always @(negedge clk)if(rst_n)begin
    if(config_applied || history_done)acks=acks+1;
    if(quiet && (u_dut.ram_write_tail || u_dut.early_ram.write_pending ||
       u_dut.g_fdn[0].ram.write_pending || u_dut.g_fdn[1].ram.write_pending ||
       u_dut.g_fdn[2].ram.write_pending || u_dut.g_fdn[3].ram.write_pending))
      $fatal(1,"quiescence exposed incomplete high-half RAM write");
    if(compare48)begin
      if({ready,valid_o,active}!={ref_ready,ref_valid,ref_active})$fatal(1,"48k control/latency mismatch");
      if(valid_o)begin
        if({left_o,right_o,clip}!={ref_l,ref_r,ref_clip})
          $fatal(1,"48k prepared reference mismatch frame %0d got%h,%h expected%h,%h",outputs,left_o,right_o,ref_l,ref_r);
        compared=compared+1;
      end
    end
    if(valid_o)begin outputs=outputs+1;if(clip)clips=clips+1;end
  end
  task automatic render(input logic signed [31:0] l,r,input logic enable,
      input logic check_pcm,input logic signed [31:0] expected_l,expected_r,input logic expected_clip);
    begin
      @(negedge clk);if(!ready)$fatal(1,"render refused");
      valid_i=1;left_i=l;right_i=r;enabled_i=enable;
      @(negedge clk);valid_i=0;frame_latency=1;
      while(!valid_o && frame_latency<150)begin @(negedge clk);frame_latency=frame_latency+1;end
      if(!valid_o)$fatal(1,"render hung waiting for RAM result");
      if(frame_latency>max_latency)max_latency=frame_latency;
      if(check_pcm && {left_o,right_o,clip}!={expected_l,expected_r,expected_clip})
        $fatal(1,"independent fixed point mismatch output %0d got%h,%h,%b expected%h,%h,%b",outputs,left_o,right_o,clip,expected_l,expected_r,expected_clip);
      repeat(3)@(negedge clk);
      if(!quiet)$fatal(1,"RAM write tail failed to drain");
    end
  endtask
  task automatic configure(input logic next_rate,input logic history_only);
    integer gain_before,fraction_before,acks_before;
    begin
      @(negedge clk);if(!config_ready || !history_ready)$fatal(1,"config not quiescent");
      gain_before=32'(u_dut.gain);fraction_before=32'(u_dut.gain_remainder);acks_before=acks;
      rate_44=next_rate;config_valid=!history_only;history_clear=history_only;
      @(negedge clk);config_valid=0;history_clear=0;repeat(2)@(negedge clk);
      if(acks!=acks_before+1 || u_dut.gain!=16'(gain_before) || u_dut.gain_remainder!=8'(fraction_before) ||
         u_dut.frames!=0 || u_dut.early_pointer!=0 || !quiet)$fatal(1,"config/history did not preserve gain or clear history");
      if(!history_only && rate!=next_rate)$fatal(1,"wrong applied rate");
      for(integer lane=0;lane<4;lane=lane+1)begin
        if(u_dut.pointer[lane]!=0 || u_dut.damping[lane]!=0 || u_dut.tail[lane]!=0)
          $fatal(1,"FDN history escaped configuration clear");
      end
    end
  endtask
  integer scenario=0,i,j,fd,records,fields,operation,enable_value,expected_clip_value;
  integer target_state,target_tap;
  reg signed [31:0] fixture_l,fixture_r,expected_l,expected_r;
  string vector_file;
  initial begin
    if(!$value$plusargs("SCENARIO=%d",scenario))scenario=0;
    repeat(10)@(negedge clk);rst_n=1;repeat(4)@(negedge clk);
    if(scenario<4)begin
      if(!$value$plusargs("VECTOR_FILE=%s",vector_file))$fatal(1,"missing model vector file");
      fd=$fopen(vector_file,"r");if(fd==0)$fatal(1,"cannot open model vector file");
      fields=$fscanf(fd,"%d\n",records);if(fields!=1)$fatal(1,"bad model record count");
      compare48=(scenario==0 || scenario==2);
      for(i=0;i<records;i=i+1)begin
        fields=$fscanf(fd,"%d %h %h %d %h %h %d\n",operation,fixture_l,fixture_r,enable_value,expected_l,expected_r,expected_clip_value);
        if(fields!=7)$fatal(1,"bad model record %0d",i);
        case(operation)
          0:render(fixture_l,fixture_r,1'(enable_value),1,expected_l,expected_r,1'(expected_clip_value));
          1:configure(1,0);
          2:configure(0,0);
          3:configure(0,1);
          4:begin
            compare48=0;@(negedge clk);clear_i=1;repeat(2)@(negedge clk);clear_i=0;repeat(2)@(negedge clk);
            if(scenario==0 || scenario==2)compare48=1;
          end
          default:$fatal(1,"bad model operation");
        endcase
      end
      $fclose(fd);
      if(outputs==0 || max_latency>100)$fatal(1,"no outputs or component latency regression");
      $display("PASS runtime Reverb model scenario=%0d frames=%0d reference48=%0d clips=%0d max_latency=%0d",scenario,outputs,compared,clips,max_latency);
    end else if(scenario==4)begin
      configure(1,0);
      for(i=0;i<16;i=i+1)begin
        repeat(20)render(32'sh12345678,-32'sh1234567,1,0,0,0,0);
        target_state=i<11 ? i : i-8;target_tap=i<11 ? 0 : 11;
        if(target_state==0)begin
          render(32'sh12345678,-32'sh1234567,1,0,0,0,0);
        end else begin
          @(negedge clk);valid_i=1;
          @(negedge clk);valid_i=0;
          while(!(u_dut.state==4'(target_state) &&
              (!(target_state>=3 && target_state<=6) || u_dut.tap==4'(target_tap))))@(negedge clk);
        end
        clear_i=1;repeat(2)@(negedge clk);
        if(valid_o || u_dut.state!=0 || u_dut.frames!=0 || u_dut.gain!=0 || u_dut.ram_write_tail)
          $fatal(1,"legacy clear did not cancel RAM/pipeline state%0d tap%0d",target_state,target_tap);
        clear_i=0;repeat(3)@(negedge clk);
        render(32'sh11223344,-32'sh11223344,1,1,32'sh11223344,-32'sh11223344,0);
      end
      $display("PASS runtime Reverb clear cancellation16 RAM/pipeline boundaries");
    end else if(scenario==5)begin
      @(negedge clk);valid_i=1;config_valid=1;history_clear=1;rate_44=1;
      #1;if(config_ready || history_ready)$fatal(1,"configuration raced PCM");
      @(negedge clk);valid_i=0;
      wait(config_applied);@(negedge clk);config_valid=0;history_clear=0;repeat(3)@(negedge clk);
      if(outputs!=1 || acks!=1 || !rate || !quiet)$fatal(1,"held config/history priority");
      $display("PASS runtime Reverb config backpressure and RAM write-tail fence");
    end else $fatal(1,"unknown scenario");
    $finish;
  end
  initial begin #1000000000;$fatal(1,"Reverb test watchdog");end
endmodule
