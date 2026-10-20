`timescale 1ns/1ps
module tb_rice;
reg clk=0;always #5 clk=~clk;
reg resetn=0,enable=1,start=0;reg [12:0] pcm_length;
wire [12:0] sample_addr,write_addr,encoded_length;wire [7:0] write_data;
wire write_valid,done,use_rice,use_second;reg allow_second=1;reg [15:0] sample_data;reg [7:0] pcm[0:8111],expected[0:8111];
integer expected_length,expected_mode,count=0,cycles=0;
ble_rice_encoder dut(.*);
always @(posedge clk) sample_data<={pcm[sample_addr+1],pcm[sample_addr]};
always @(negedge clk) begin
 if(write_valid)begin
  if(write_addr!==count || write_data!==expected[count])$fatal(1,"encoded byte %0d addr=%0d got=%h expected=%h",count,write_addr,write_data,expected[count]);
  count=count+1;
 end
 cycles=cycles+1;if(cycles>300000)$fatal(1,"timeout");
end
initial begin
 $readmemh("/private/tmp/gw25k-rice-vectors/pcm.mem",pcm);$readmemh("/private/tmp/gw25k-rice-vectors/expected.mem",expected);
 pcm_length=8112;expected_length=3382;expected_mode=11;
 repeat(3)@(negedge clk);resetn=1;@(negedge clk);start=1;@(negedge clk);start=0;
 wait(done);@(negedge clk);
 if(use_second!==(expected_mode==11) || use_rice!==(expected_mode!=0) || encoded_length!=expected_length || count!=(expected_mode!=0 ? expected_length : 0))$fatal(1,"result mode=%d len=%d count=%d",use_rice,encoded_length,count);
 $display("PASS encoder bytes=%0d cycles=%0d",encoded_length,cycles);$finish;
end
endmodule
