`timescale 1ns/1ps
module tb_push2_lights_snapshot;
  reg clk=0,rst=1,ready=1;
  always #5 clk=~clk;
  reg [63:0] held=0,guide_mask=0;
  reg [31:0] control=0,score_mask=0;
  reg score_running=0,record_enabled=0,guide_mode=0;
  wire [1:0] valid;
  wire [1:0] kind[0:1];
  wire [6:0] index[0:1];
  wire [7:0] value[0:1];
  push2_lights_reference reference_lights(.clk,.rst,.held,.control,.score_mask,.score_running,
      .record_enabled,.guide_mode,.guide_mask,.ready,.valid(valid[0]),.kind(kind[0]),.index(index[0]),.value(value[0]));
  push2_lights dut(.clk,.rst,.held,.control,.score_mask,.score_running,
      .record_enabled,.guide_mode,.guide_mask,.ready,.valid(valid[1]),.kind(kind[1]),.index(index[1]),.value(value[1]));
  reg [6:0] pads[0:1][0:127],buttons[0:1][0:127];
  reg was_stalled[0:1];
  reg [16:0] stalled_payload[0:1];
  reg [31:0] rng=32'h23a58901;
  integer starts[0:1],messages[0:1],checks=0,cycles=0,cleared_scans=0;
  integer max_sample_delay=0;

  task tick;begin @(negedge clk);#1;end endtask
  task randomize_inputs;
    begin
      rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
      guide_mode=rng[0];guide_mask={rng,rng^32'had604ec1};
      held={rng^32'h01234567,rng};control=rng;score_mask=~rng;
      score_running=rng[1];record_enabled=rng[2];
    end
  endtask
  function [6:0] expected_color(input integer s);
    reg [6:0] c;
    begin
      c=0;
      if(guide_mode)begin if(s<64 && guide_mask[s])c=126;end
      else if(s<64)begin
        case(s%8)
          0:c=126;1:c=15;2:c=125;3:c=22;4:c=25;5:c=3;6:c=8;default:c=127;
        endcase
        if(score_running && s<32 && score_mask[s])c=126;
        if(held[s])c=122;
      end else if(s<67)c=control[4:3]==s-64?126:1;
      else if(s<72)c=control[9:7]==s-67?15:1;
      else if(s<75)c=control[s-72]?126:1;
      else if(s<79)c=control[6:5]==s-75?15:1;
      else if(s==79)c=3;
      else if(s==80)c=(|control[2:0])?126:1;
      else if(s==81)c=score_running?126:1;
      else if(s==82)c=record_enabled?5:1;
      else c=3;
      expected_color=c;
    end
  endfunction
  function integer destination(input integer s);
    begin
      if(s<64)destination=s+36;
      else if(s<72)destination=s+38;
      else if(s<79)destination=s-52;
      else case(s)
        79:destination=27;80:destination=28;81:destination=85;82:destination=86;
        83:destination=62;default:destination=63;
      endcase
    end
  endfunction
  task settle_and_check;
    integer n;
    reg [6:0] expected;
    begin
      // Finite arbitrary stalls followed by fair ready have a bounded final
      // result. No equality of transient packet order is assumed.
      for(integer t=0;t<1600;t++)begin ready=(t%7)!=0 && (t%11)!=0;tick();end
      ready=1;repeat(500)tick();
      for(integer s=0;s<85;s++)begin
        n=destination(s);expected=expected_color(s);
        if(s<64)begin
          if(pads[0][n]!==expected || pads[1][n]!==expected)
            $fatal(1,"pad final mismatch scan=%0d old=%0d new=%0d expected=%0d",s,pads[0][n],pads[1][n],expected);
        end else if(buttons[0][n]!==expected || buttons[1][n]!==expected)
          $fatal(1,"button final mismatch scan=%0d old=%0d new=%0d expected=%0d",s,buttons[0][n],buttons[1][n],expected);
      end
      if(starts[0]!=5 || starts[1]!=5)$fatal(1,"startup sequence not complete");
      if(dut.guide_mode_q!==guide_mode || dut.guide_mask_q!==guide_mask)
        $fatal(1,"stable guide snapshot incoherent");
      checks++;
    end
  endtask
  always @(posedge clk)begin
    cycles++;
    for(integer p=0;p<2;p++)begin
      if(rst)begin starts[p]=0;was_stalled[p]=0;end
      else begin
        if(was_stalled[p] && (!valid[p] || {kind[p],index[p],value[p]}!==stalled_payload[p]))
          $fatal(1,"valid/ready stalled payload changed side=%0d",p);
        was_stalled[p]=valid[p] && !ready;
        stalled_payload[p]={kind[p],index[p],value[p]};
        if(valid[p] && ready)begin
          if(starts[p]<5)begin
            case(starts[p])
              0:if({kind[p],index[p],value[p]}!=={2'd3,7'd127,8'd0})$fatal(1,"startup0");
              1:if({kind[p],index[p],value[p]}!=={2'd1,7'd0,8'd64})$fatal(1,"startup1");
              2:if({kind[p],index[p],value[p]}!=={2'd2,7'd0,8'd160})$fatal(1,"startup2");
              3:if({kind[p],index[p],value[p]}!=={2'd3,7'd126,8'd104})$fatal(1,"startup3");
              4:if({kind[p],index[p],value[p]}!=={2'd3,7'd125,8'd1})$fatal(1,"startup4");
            endcase
            starts[p]++;
          end else if(kind[p]==0)pads[p][index[p]]=value[p][6:0];
          else if(kind[p]==3)buttons[p][index[p]]=value[p][6:0];
          messages[p]++;
        end
      end
    end
    if(!rst && dut.clear_guide && dut.scan==84 && !valid[1] && !dut.guide_changed)
      cleared_scans++;
  end
  initial begin
    for(integer p=0;p<2;p++)begin
      starts[p]=0;messages[p]=0;was_stalled[p]=0;
      for(integer n=0;n<128;n++)begin pads[p][n]=7'h7f;buttons[p][n]=7'h7f;end
    end
    repeat(4)tick();rst=0;
    settle_and_check();
    for(integer t=0;t<12;t++)begin randomize_inputs();guide_mode=0;settle_and_check();end
    guide_mode=1;guide_mask=64'hffffffffffffffff;settle_and_check();
    guide_mask=64'h8000000000000000;settle_and_check();
    guide_mask=0;settle_and_check();
    // Continuously changing snapshots and arbitrary deterministic stalls.
    for(integer t=0;t<3000;t++)begin randomize_inputs();ready=rng[3] && rng[4];tick();end
    guide_mode=1;guide_mask=64'd1<<24;settle_and_check();
    // Hold an actual unaccepted packet while all guide inputs change.
    ready=1;guide_mask=64'd1<<63;
    while(!valid[1])tick();ready=0;
    for(integer t=0;t<300;t++)begin randomize_inputs();tick();end
    guide_mode=1;guide_mask=64'd1;settle_and_check();
    // Reset during stalls; external LEDs retain their prior state until the
    // new startup and complete scan overwrite them.
    for(integer t=0;t<8;t++)begin
      ready=0;randomize_inputs();repeat(3)tick();rst=1;repeat(3)tick();rst=0;
      for(integer n=0;n<53;n++)begin randomize_inputs();ready=rng[5];tick();end
      guide_mode=t%2;guide_mask=64'd1<<(t*7);settle_and_check();
    end
    if(cleared_scans<5)$fatal(1,"guide clear/full-rescan was not exercised");
    $display("PASS lights snapshot final_states=%0d startup5 exact stalled_payload stable clear_scans=%0d packets_old=%0d new=%0d cycles=%0d",checks,cleared_scans,messages[0],messages[1],cycles);
    $finish;
  end
  initial begin #2000000;$fatal(1,"lights snapshot watchdog");end
endmodule
