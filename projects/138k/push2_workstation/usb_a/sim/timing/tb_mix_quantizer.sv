`timescale 1ns/1ps
module tb_mix_quantizer;
  reg clk=0,rstn=0,panic=0,valid=0;
  always #5 clk=~clk;
  reg signed [63:0] mix=0;
  reg [1:0] mode=0;
  wire out_valid;
  wire signed [31:0] sample_value;
  unified_mix_quantizer dut(.clk_i(clk),.rst_ni(rstn),.panic_i(panic),
      .valid_i(valid),.mix_i(mix),.mode_i(mode),.valid_o(out_valid),.sample_o(sample_value));
  reg signed [31:0] expected[0:20000];
  integer sent_cycle[0:20000];
  integer head=0,tail=0,cycle=0,checked=0,flushes=0;
  function automatic signed [31:0] oracle(input signed [63:0] value,input [1:0] m);
    reg signed [127:0] wide,result_value;
    reg [127:0] magnitude,rounded;
    integer shift_bits;
    begin
      wide={{64{value[63]}},value};
      magnitude=wide<0 ? -wide : wide;
      shift_bits=m==2 ? 28 : 31;
      rounded=(magnitude*128'd3+(128'd1<<(shift_bits-1)))>>shift_bits;
      result_value=wide<0 ? -$signed(rounded) : $signed(rounded);
      if(result_value>128'sd2147483647) oracle=32'sh7fffffff;
      else if(result_value < -128'sd2147483648) oracle=32'sh80000000;
      else oracle=result_value[31:0];
    end
  endfunction
  always @(posedge clk) begin
    cycle=cycle+1;
    if(!rstn || panic) begin
      head=0;tail=0;flushes=flushes+1;
      #1;
      if(out_valid || sample_value!==0)$fatal(1,"PANIC/reset did not cancel quantizer");
    end else begin
      if(valid)begin expected[tail]=oracle(mix,mode);sent_cycle[tail]=cycle;tail=tail+1;end
      #1;
      if(out_valid)begin
        if(head>=tail)$fatal(1,"unexpected quantizer output");
        if(sample_value!==expected[head])$fatal(1,"quantizer value got=%h expected=%h",sample_value,expected[head]);
        if(cycle-sent_cycle[head]!=5)$fatal(1,"unexpected quantizer latency");
        head=head+1;checked=checked+1;
      end
    end
  end
  task automatic send(input signed [63:0] value,input [1:0] m,input bit enable,input bit p);
    @(negedge clk);mix=value;mode=m;valid=enable;panic=p;
  endtask
  integer m,k,i;
  reg signed [63:0] boundary,value;
  initial begin
    repeat(4)@(negedge clk);rstn=1;
    for(m=0;m<4;m=m+1)begin
      send(0,m[1:0],1,0);send(1,m[1:0],1,0);send(-1,m[1:0],1,0);
      send(64'sh8000000000000000,m[1:0],1,0);
      send(64'sh7fffffffffffffff,m[1:0],1,0);
      boundary=(64'sd2147483647<<(m==2?28:31))/3;
      for(k=-8;k<=8;k=k+1)begin
        send(boundary+k,m[1:0],1,0);send(-boundary+k,m[1:0],1,0);
        send((64'sd1<<(m==2?27:30))/3+k,m[1:0],1,0);
      end
    end
    for(i=0;i<10000;i=i+1)begin
      value={$random,$random};
      case(i%4)
        1:value=value>>>7;
        2:value=value>>>16;
        3:value=($signed(value[15:0])*64'sd268435456)/3+(i%9)-4;
      endcase
      send(value,i[1:0],i%7!=0,i%997==0);
    end
    send(0,0,0,0);repeat(8)@(negedge clk);
    if(head!=tail || checked<8000)$fatal(1,"lost quantizer results");
    $display("PASS mix_quantizer: %0d exact 128-bit-oracle results, 4 modes, limits/rounding/PANIC, flushes=%0d",checked,flushes);
    $finish;
  end
  initial begin #2000000;$fatal(1,"quantizer timeout");end
endmodule
