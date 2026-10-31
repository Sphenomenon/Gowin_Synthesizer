`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0;reg[31:0] address=0;reg[1:0] transfer=0;reg[2:0] size=3,burst=0;
reg[3:0] protection=4'hf;reg write=0;reg[63:0] wd=0;wire[63:0] rd;wire ready,response,unmapped;
workstation_ae350_cache_probe_memory dut(clk,rst,address,transfer,size,burst,protection,write,wd,rd,ready,response,unmapped);
integer n,k,b,base;reg[31:0] addr[0:15];reg[63:0] data[0:15];
task cycle(input[31:0] a,input[1:0] t,input[2:0] s,hb,input wr,input[63:0] value);
begin @(negedge clk);address=a;transfer=t;size=s;burst=hb;write=wr;wd=value;
@(posedge clk);#1;end endtask
task healthy;begin if(ready!==1||response!==0)$fatal(1,"valid transfer rejected addr=%h",address);end endtask
task idle;begin cycle(0,0,3,0,0,0);healthy;end endtask
task put(input[31:0] a,input[2:0] s,input[63:0] value);
begin cycle(a,2, s,0,1,64'hbad0);healthy;cycle(0,0,3,0,0,value);healthy;end endtask
task get(input[31:0] a,input[63:0] expected);
begin cycle(a,2,3,0,0,0);healthy;if(rd!==expected)$fatal(1,"read mismatch addr=%h expected=%h actual=%h",a,expected,rd);idle;end endtask
task error_at(input[31:0] a,input[1:0] t,input[2:0] s,hb);
begin cycle(a,t,s,hb,1,64'hdeadbeef);if(ready!==0||response!==1)$fatal(1,"ERROR first cycle");
// The master cancels the following transfer in the ERROR response.
cycle(0,0,3,0,0,0);if(ready!==1||response!==1)$fatal(1,"ERROR second cycle");
idle;if(unmapped!==1)$fatal(1,"fault sticky absent");end endtask
initial begin
#2;rst=0;#11;rst=1;idle;
// Independent reference layout exercises normal storage and explicit alias.
put('h1000,3,64'h1122334455667788);get('h4000,64'h1122334455667788);
put('h4000,3,64'hfedcba9876543210);get('h1000,64'hfedcba9876543210);
put('h1002,0,64'h0000000000ab0000);get('h4000,64'hfedcba9876ab3210);
put('h4004,1,64'h0000123400000000);get('h1000,64'hfedc123476ab3210);
put('h1004,2,64'h89abcdef00000000);get('h4000,64'h89abcdef76ab3210);
// INCR/WRAP4/8/16. Addresses come from burst length and byte-array offsets;
// WDATA intentionally changes one cycle after its corresponding address.
for(b=1;b<=7;b=b+1)begin
 if(b==1)n=6;else if(b<=3)n=4;else if(b<=5)n=8;else n=16;
 base='h1100+(b*128); // each burst remains in one 1KiB region
 if((b%2)==0)base=base+(n-1)*8;
 for(k=0;k<n;k=k+1)begin
  if(b==2||b==4||b==6)addr[k]=(base/(n*8))*(n*8)+((base%(n*8)+k*8)%(n*8));
  else addr[k]=base+k*8;
  data[k]=64'h9327a10011220000+(b*256)+k;
 end
 cycle(addr[0],2,3,b,1,64'h7777);healthy;
 for(k=1;k<n;k=k+1)begin
  // BUSY retains burst and completes the preceding write's data phase.
  if(k==2)begin cycle(addr[k],1,3,b,1,data[k-1]);healthy;
   cycle(addr[k],3,3,b,1,64'hbadbad);healthy;
  end else begin cycle(addr[k],3,3,b,1,data[k-1]);healthy;end
 end
 // Same-word write→read forwarding on the final pending write.
 cycle(addr[n-1],2,3,0,0,data[n-1]);healthy;
 if(rd!==data[n-1])$fatal(1,"same-word forwarding");idle;
 // Cache-line refill is a continuous 64-bit read burst.
 cycle(addr[0],2,3,b,0,0);healthy;
 if(rd!==data[0])$fatal(1,"burst first read");
 for(k=1;k<n;k=k+1)begin cycle(addr[k],3,3,b,0,0);healthy;
  if(rd!==data[k])$fatal(1,"burst read b=%d k=%d",b,k);end
 idle;
end
// Orphan SEQ, alignment, size, unmapped, changed burst/width/address,
// excess fixed-length beat, and crossing 1KiB all fail and then recover.
error_at('h1000,3,3,3);error_at('h1001,2,3,0);error_at('h1000,2,4,0);error_at('h8000,2,3,0);
cycle('h1000,2,3,3,0,0);healthy;error_at('h1008,3,3,5);
cycle('h1000,2,3,3,0,0);healthy;error_at('h1008,3,2,3);
cycle('h1000,2,3,3,0,0);healthy;error_at('h1010,3,3,3);
cycle('h1000,2,3,3,0,0);healthy;
cycle('h1008,3,3,3,0,0);healthy;cycle('h1010,3,3,3,0,0);healthy;cycle('h1018,3,3,3,0,0);healthy;
error_at('h1020,3,3,3);
cycle('h13f8,2,3,1,0,0);healthy;error_at('h1400,3,3,1);
// A reset after an accepted write address cancels its pending data phase.
put('h1000,3,64'h123456789abcdef0);
cycle('h1000,2,3,0,1,0);healthy;
@(negedge clk);rst=0;transfer=0;wd=64'hdeadbeefcafef00d;
@(posedge clk);#1;if(ready!==1||response!==0||unmapped!==0)$fatal(1,"reset controls");
@(negedge clk);rst=1;get('h4000,64'h123456789abcdef0);
$display("PASS cache probe AHB owner: phases masks aliases bursts BUSY ERROR reset");$finish;
end
initial begin #100000;$fatal(1,"timeout");end
endmodule
