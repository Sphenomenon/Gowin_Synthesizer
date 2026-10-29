`timescale 1ns/1ps
// Diagnostic evidence only. Persistent-valid producers deliberately exceed the
// bounded real scan/TF arrival patterns. This does not implement a D01 gate or
// claim real-workload starvation; it exposes the selected arbiter's missing
// unconditional per-owner service bound. Count native issues, not slot ACKs.
module tb_ddr_budget;
reg clk=0,reset_n=0;always #5 clk=~clk;
reg [7:0] v=0;
wire [7:0] ready,rsp;
wire [2:0] cmd;
wire en,wren,wend,fault;
wire [28:0] address;
wire [255:0] data,rd;
wire [31:0] mask;
reg app_ready=1,app_write_ready=1,return_valid=0;
always @(posedge clk) return_valid<=reset_n && en && cmd==1;
basic_pitch_ddr_client_queues dut(
.clk(clk),.reset_n(reset_n),.bist_done(1'b1),
.bist_valid(v[0]),.bist_write(1'b1),.bist_address(29'd0),.bist_data(256'd0),.bist_ready(ready[0]),.bist_response(rsp[0]),
.scan_valid(v[1]),.scan_address(29'd8),.scan_ready(ready[1]),.scan_response(rsp[1]),
.display_valid(v[7]),.display_address(29'd56),.display_ready(ready[7]),.display_response(rsp[7]),
.audio_valid(v[4]),.audio_write(1'b1),.audio_address(29'd32),.audio_data(256'd0),.audio_ready(ready[4]),.audio_response(rsp[4]),
.music_valid(v[5]),.music_write(1'b1),.music_address(29'd40),.music_data(256'd0),.music_mask(32'd0),.music_ready(ready[5]),.music_response(rsp[5]),
.delay_valid(v[6]),.delay_write(1'b1),.delay_address(29'd48),.delay_data(256'd0),.delay_ready(ready[6]),.delay_response(rsp[6]),
.writer_valid(v[3]),.writer_address(29'd24),.writer_data(256'd0),.writer_ready(ready[3]),
.cpu_valid(v[2]),.cpu_write(1'b1),.cpu_address(29'd16),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(ready[2]),.cpu_response(rsp[2]),
.app_cmd(cmd),.app_en(en),.app_wren(wren),.app_wend(wend),.app_address(address),.app_data(data),.app_mask(mask),
.app_ready(app_ready),.app_write_ready(app_write_ready),.app_response(return_valid),.app_response_data(256'd0),.response_data(rd),.response_fault(fault));
integer counts[0:7];integer maxwait[0:7];integer waitage[0:7];integer i,j,phase;
task run(input integer id,input [7:0] inputs,input integer n);
begin
 reset_n=0;v=0;repeat(5)@(negedge clk);
 for(i=0;i<8;i=i+1)begin counts[i]=0;maxwait[i]=0;waitage[i]=0;end
 reset_n=1;v=inputs;
 for(j=0;j<n;j=j+1)begin
 @(posedge clk);
 for(i=0;i<8;i=i+1)begin
 if(v[i])begin waitage[i]=waitage[i]+1;if(waitage[i]>maxwait[i])maxwait[i]=waitage[i];end
 end
 if(en)begin counts[address>>3]=counts[address>>3]+1;waitage[address>>3]=0;end
 if(fault)$fatal(1,"response fault");
 end
 @(negedge clk);
 $display("PHASE %0d MASK %h CYCLES %0d ISSUES %0d %0d %0d %0d %0d %0d %0d %0d MAXWAIT %0d %0d %0d %0d %0d %0d %0d %0d",id,inputs,n,counts[0],counts[1],counts[2],counts[3],counts[4],counts[5],counts[6],counts[7],maxwait[0],maxwait[1],maxwait[2],maxwait[3],maxwait[4],maxwait[5],maxwait[6],maxwait[7]);
end endtask
initial begin
run(1,8'hfe,20000);
run(2,8'hfc,20000);
run(3,8'h6c,20000);
run(4,8'h68,20000);
run(5,8'h60,20000);
run(6,8'hfe,40000);
run(7,8'hfc,40000);
$finish;end
endmodule
