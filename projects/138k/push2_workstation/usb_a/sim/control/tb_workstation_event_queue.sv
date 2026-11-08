module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,clear=0;reg [2:0] valid=0;reg ready=0;
reg[17:0] a=0,b=0,c=0;wire[2:0]take;wire ov;wire[17:0]word;
workstation_event_queue dut(.clk(clk),.reset_n(rst),.clear(clear),.g1_valid(valid[0]),.pc_valid(valid[1]),.cpu_valid(valid[2]),.g1_data(a),.pc_data(b),.cpu_data(c),.g1_ready(take[0]),.pc_ready(take[1]),.cpu_ready(take[2]),.event_valid(ov),.event_data(word),.event_ready(ready));
reg[17:0] queue[0:1];integer count=0,first=0,selected=0;integer i,j;integer pushes=0,pops=0,clears=0,simultaneous=0;integer seed=32'h20261108;reg [2:0] frozen;
task check;
begin
 if(dut.count!==count)$fatal(1,"occupancy mismatch");
 if(ov!==((count!=0)&&!clear))$fatal(1,"valid mismatch");
 if(ov && word!==queue[0])$fatal(1,"data mismatch");
 selected=(first+2)%3;
 for(j=2;j>=0;j=j-1)if(valid[(first+j)%3])selected=(first+j)%3;
 if(take!==((count<2&&!clear)?(3'b1<<selected):3'b0))$fatal(1,"RR or readiness mismatch");
 frozen=take;ready=!ready;#0.01;if(take!==frozen)$fatal(1,"output ready feeds source readiness");ready=!ready;#0.01;
end endtask
initial begin
 #1;rst=1;#1;rst=0;#1;rst=1;
 for(i=0;i<20000;i=i+1)begin
 @(negedge clk);valid=$random(seed);ready=$random(seed);clear=(i%23==0);a=$random(seed);b=$random(seed);c=$random(seed);#0.01;check;
 @(posedge clk);
 if(clear)begin count=0;clears=clears+1;end
 else begin
  if(ov&&ready)begin queue[0]=queue[1];count=count-1;pops=pops+1;end
  if(|(take&valid))begin queue[count]=selected==0?a:selected==1?b:c;count=count+1;first=(selected+1)%3;pushes=pushes+1;end
  if(ov&&ready&&|(take&valid))simultaneous=simultaneous+1;
 end
 #0.1;
 end
 if(pushes<1000||pops<1000||clears<500||simultaneous<500)$fatal(1,"coverage missing");
 $display("PASS event queue cycles=20000 accepted=%0d popped=%0d cancelled=%0d simultaneous=%0d ready-independent",pushes,pops,clears,simultaneous);$finish;
end
endmodule
