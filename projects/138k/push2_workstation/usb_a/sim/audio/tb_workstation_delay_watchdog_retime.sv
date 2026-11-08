module tb;
parameter T=2;
reg clk=0,rst=0;always #5 clk=~clk;
reg valid=0,ready=0,response=0,rdready=0,hb=0;
reg [64:0] data=0;reg [255:0] rddata=0;
wire [428:0] x,y;
`define CONNECT .clk_i(clk),.rst_ni(rst),.dwr_valid_i(valid),.dwr_data_i(data),.drd_ready_i(rdready),.ddr_ready_i(ready),.ddr_response_i(response),.ddr_read_data_i(rddata),.peer_heartbeat_i(hb)
`define OUTPUTS(z) .dwr_pop_o(z[0]),.drd_push_o(z[1]),.drd_data_o(z[66:2]),.ddr_req_o(z[67]),.ddr_write_o(z[68]),.ddr_address_o(z[97:69]),.ddr_data_o(z[353:98]),.ddr_mask_o(z[385:354]),.debug_status_o(z[393:386]),.flush_done_o(z[394]),.fault_o(z[395]),.applied_rate_44100_o(z[396]),.applied_transaction_o(z[428:397]),.heartbeat_o()
delay_original #(.TRANSACTION_TIMEOUT_CYCLES(T),.PEER_TIMEOUT_CYCLES(128)) refdut(`CONNECT,`OUTPUTS(x));
workstation_runtime_delay_ddr_dma #(.TRANSACTION_TIMEOUT_CYCLES(T),.PEER_TIMEOUT_CYCLES(128)) dut(`CONNECT,`OUTPUTS(y));
integer i,j;reg [31:0] expected;integer seed=21;
task check;
begin
 if(x!==y)$fatal(1,"output mismatch T=%0d cycle=%0d x=%h y=%h",T,i,x,y);
 expected=dut.watchdog_reset_delay ? 0 : (dut.wait_cycles<T ? dut.wait_cycles+1: dut.wait_cycles);
 if(refdut.wait_cycles!==expected)$fatal(1,"counter correspondence T=%0d cycle=%0d ref=%h projected=%h",T,i,refdut.wait_cycles,expected);
end endtask
initial begin
 #1;rst=1;#1;rst=0;#1;
 for(j=0;j<12;j=j+1)begin
 @(negedge clk);rst=0;@(negedge clk);rst=1;
 // Exercise every legal/illegal state and arbitrary counter histories via
 // real clocks, without forcing counter state. Inputs include X/Z markers.
 for(i=0;i<500;i=i+1)begin
  @(negedge clk);
  valid=$random(seed);rdready=$random(seed);ready=$random(seed);response=$random(seed);hb=$random(seed);
  data={$random(seed),$random(seed),1'b0};rddata={$random(seed),$random(seed)};
  if(i%7==0)data[64]=1'bx;
  if(i%11==0)ready=1'bx;
  if(i%13==0)response=1'bz;
  if(i%17==0)rdready=1'bx;
  dut.state=4'(i%16);refdut.state=4'(i%16);
  @(posedge clk);#1;check;
 end
 // Sustained no-progress state reaches the exact timeout edge.
 @(negedge clk);rst=0;@(negedge clk);rst=1;valid=0;response=0;ready=0;rdready=0;
 dut.state=4'd3;refdut.state=4'd3;
 for(i=0;i<(T<32?T+3:64);i=i+1)begin @(posedge clk);#1;check;@(negedge clk);end
 end
 $display("PASS watchdog retime T=%0d all429 output bits and counter invariant",T);$finish;
end
endmodule
