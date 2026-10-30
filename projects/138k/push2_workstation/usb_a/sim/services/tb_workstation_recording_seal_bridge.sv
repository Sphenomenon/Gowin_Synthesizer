`timescale 1ns/1ps
module tb_workstation_recording_seal_bridge;
parameter integer CASE=0;
reg source_clk=0,destination_clk=0,source_running=1,destination_running=1;
always #13 if(source_running)source_clk=~source_clk;
always #5 if(destination_running)destination_clk=~destination_clk;
reg reset_n=1,request=0,hold=0;
reg backend_ready=0,backend_done=0,backend_failed=0;
reg [3:0] backend_code=0;
wire ready,done,failed,destination_hold,destination_request;
wire [3:0] code;
workstation_recording_seal_bridge dut(
 .reset_ni(reset_n),.source_clk_i(source_clk),.destination_clk_i(destination_clk),
 .request_i(request),.hold_i(hold),.ready_o(ready),.done_o(done),.failed_o(failed),.failure_code_o(code),
 .destination_hold_o(destination_hold),.destination_request_o(destination_request),
 .destination_ready_i(backend_ready),.destination_done_i(backend_done),
 .destination_failed_i(backend_failed),.destination_failure_code_i(backend_code));
integer source_edges=0,destination_edges=0,delivered=0,terminals=0;
reg reject_ready_pulse=0,require_pending_hold=0,expect_no_terminal=0;
always @(posedge source_clk or negedge reset_n)begin
 if(!reset_n)source_edges=0;
 else begin
  source_edges=source_edges+1;
  #0.01;
  if(source_edges<=2 && (dut.source_hold!==0 || dut.request_toggle!==0 || dut.source_pending!==0 ||
    dut.result_seen!==0 || dut.result_meta!==0 || dut.result_sync!==0 || dut.ready_meta!==0 ||
    dut.ready_sync!==0 || done!==0 || failed!==0 || code!==0))
   $fatal(1,"source functional FF escaped local release");
  if(reject_ready_pulse && ready)$fatal(1,"unregistered destination ready pulse crossed domains");
  if(expect_no_terminal && (done || failed))$fatal(1,"pending seal completed before backend terminal");
 end
end
always @(posedge destination_clk or negedge reset_n)begin
 if(!reset_n)destination_edges=0;
 else begin
  destination_edges=destination_edges+1;
  #0.01;
  if(destination_edges<=2 && (dut.request_meta!==0 || dut.request_sync!==0 || dut.hold_meta!==0 ||
    dut.hold_sync!==0 || dut.request_seen!==0 || dut.destination_pending!==0 || destination_request!==0 ||
    dut.destination_ready!==0 || dut.result_toggle!==0 || dut.result_failed!==0 || dut.result_code!==0))
   $fatal(1,"destination functional FF escaped local release");
  if(require_pending_hold && dut.destination_pending && !destination_hold)
   $fatal(1,"accepted seal lost backend hold before real terminal");
 end
end
always @(negedge destination_clk)if(reset_n && destination_request)delivered=delivered+1;
always @(negedge source_clk)if(reset_n && (done || failed))terminals=terminals+1;
task automatic source_wait(input integer count);repeat(count)@(negedge source_clk);endtask
task automatic memory_wait(input integer count);repeat(count)@(negedge destination_clk);endtask
task automatic assert_reset;
 begin
  reset_n=0;#0.1;
  if(ready!==0 || done!==0 || failed!==0 || code!==0 || destination_request!==0 || destination_hold!==0 ||
    dut.source_pending!==0 || dut.destination_pending!==0 || dut.destination_ready!==0 ||
    dut.request_toggle!==0 || dut.result_toggle!==0 ||
    {dut.source_release_sync,dut.source_release_meta}!==0 ||
    {dut.destination_release_sync,dut.destination_release_meta}!==0)
   $fatal(1,"common reset did not asynchronously clear seal channel");
 end
endtask
task automatic await_ready;
 integer n;
 begin
  n=0;while(!ready && n<100)begin source_wait(1);n=n+1;end
  if(!ready)$fatal(1,"seal ready deadline");
 end
endtask
task automatic accept_request;
 begin
  await_ready();@(negedge source_clk);hold=1;request=1;
  @(negedge source_clk);request=0;
  if(!dut.source_pending || ready)$fatal(1,"same-edge hold request was not accepted");
 end
endtask
task automatic await_delivery;
 integer n;
 begin
  n=0;while(!destination_request && n<100)begin memory_wait(1);n=n+1;end
  if(!destination_request)$fatal(1,"backend request deadline");
  if(!destination_hold)$fatal(1,"backend request preceded registered hold");
 end
endtask
task automatic terminal(input bit is_failed,input [3:0] reason);
 begin
  memory_wait(3);backend_done=!is_failed;backend_failed=is_failed;backend_code=reason;
  memory_wait(1);backend_done=0;backend_failed=0;backend_code=15;
 end
endtask
task automatic await_terminal(input bit want_failed,input [3:0] reason);
 integer n;
 begin
  n=0;while(!done && !failed && n<100)begin source_wait(1);n=n+1;end
  if(!done && !failed)$fatal(1,"real seal terminal was lost");
  if(failed!==want_failed || done===want_failed || code!==reason)
   $fatal(1,"seal terminal/failure mismatch done=%b failed=%b code=%d",done,failed,code);
  source_wait(1);
  if(done || failed)$fatal(1,"seal terminal must pulse once");
 end
endtask
integer before_delivered,before_terminal;
initial begin
 #1;assert_reset();
 if(CASE==0)begin
  // Before/after unrelated domain edges, including fractional phase offsets.
  hold=1;backend_ready=1;
  for(integer phase=0;phase<7;phase=phase+1)begin
   #(phase+0.2);reset_n=1;source_wait(5);memory_wait(4);
   if(ready || delivered!=0 || terminals!=0)$fatal(1,"reset startup fabricated admission or terminal");
   assert_reset();
  end
  hold=0;reset_n=1;await_ready();
 end else if(CASE==1)begin
  backend_ready=1;#2.3;reset_n=1;expect_no_terminal=1;accept_request();await_delivery();
  require_pending_hold=1;hold=0;source_wait(12);
  if(!dut.source_pending || done || failed || ready || delivered!=1)
   $fatal(1,"pending seal completed before backend terminal");
  expect_no_terminal=0;terminal(0,0);await_terminal(0,0);require_pending_hold=0;await_ready();
  source_wait(5);if(delivered!=1 || terminals!=1)$fatal(1,"seal transaction duplicated");
 end else if(CASE==2)begin
  backend_ready=1;#6.7;reset_n=1;accept_request();await_delivery();
  terminal(1,6);await_terminal(1,6);source_wait(12);
  if(code!=6 || ready)$fatal(1,"seal failure was not retained under hold");
  hold=0;await_ready();accept_request();
  if(code!=0)$fatal(1,"new seal did not clear previous failure detail");
  await_delivery();terminal(0,7);await_terminal(0,0);
  hold=0;await_ready();if(delivered!=2 || terminals!=2)$fatal(1,"failure recovery duplicated transaction");
 end else if(CASE==3)begin
  backend_ready=1;reset_n=1;accept_request();await_delivery();memory_wait(3);
  backend_done=1;backend_failed=1;backend_code=9;memory_wait(1);backend_done=0;backend_failed=0;backend_code=0;
  await_terminal(1,9);source_wait(8);if(code!=9)$fatal(1,"simultaneous terminal failure was lost");
 end else if(CASE==4)begin
  backend_ready=1;reset_n=1;await_ready();
  @(negedge source_clk);backend_ready=0;hold=1;request=1;
  @(negedge source_clk);request=0;
  if(!dut.source_pending)$fatal(1,"ready race lost accepted request");
  await_terminal(1,11);if(delivered!=0)$fatal(1,"unready backend received seal");
  hold=0;source_wait(8);if(ready)$fatal(1,"ready race falsely reopened backend");
 end else if(CASE==5)begin
  reset_n=1;source_wait(8);reject_ready_pulse=1;
  // 26n+13 source edges sweep the 10ns destination phase. Select phase9:
  // a 2ns ready pulse straddles source sampling but no destination edge.
  while(($time%10)!=6)@(negedge source_clk);
  #12;backend_ready=1;#2;backend_ready=0;
  source_wait(7);reject_ready_pulse=0;
  backend_ready=1;await_ready();
 end else if(CASE==6)begin
  backend_ready=1;reset_n=1;accept_request();await_delivery();
  @(negedge destination_clk);destination_running=0;assert_reset();hold=0;backend_done=1;
  #3.1;reset_n=1;source_wait(10);
  if(ready || done || failed || {dut.destination_release_sync,dut.destination_release_meta}!=0)
   $fatal(1,"stopped memory clock released seal channel");
  backend_done=0;destination_running=1;await_ready();
  if(terminals!=0)$fatal(1,"common reset replayed old pending result");
  accept_request();await_delivery();terminal(0,0);await_terminal(0,0);
  if(delivered!=2 || terminals!=1)$fatal(1,"reset channel did not accept exactly one new seal");
 end else if(CASE==7)begin
  backend_ready=1;reset_n=1;accept_request();await_delivery();
  @(negedge source_clk);source_running=0;assert_reset();hold=0;
  #1.9;reset_n=1;memory_wait(10);backend_done=1;memory_wait(2);backend_done=0;
  if(ready || done || failed || {dut.source_release_sync,dut.source_release_meta}!=0)
   $fatal(1,"stopped source clock released seal channel");
  source_running=1;await_ready();source_wait(4);
  if(terminals!=0)$fatal(1,"source restart replayed reset backend result");
  accept_request();await_delivery();terminal(1,4);await_terminal(1,4);
 end else if(CASE==8)begin
  backend_ready=1;request=1;
  // NBA deassertion exactly at a receiving edge is deliberately deterministic:
  // that edge still samples reset asserted; two following local edges release.
  @(posedge source_clk);reset_n<=1;source_wait(12);request=0;
  if(delivered!=1 || !dut.source_pending || done || failed)$fatal(1,"exact-edge release duplicated/lost held request");
  terminal(0,0);await_terminal(0,0);
  assert_reset();request=0;hold=1;@(posedge destination_clk);reset_n<=1;
  source_wait(10);if(ready || done || failed)$fatal(1,"destination-edge reset release fabricated result");
 end else if(CASE==9)begin
  backend_ready=1;reset_n=1;accept_request();await_delivery();
  // A stale owner terminal at delivery must not answer this new request.
  backend_done=1;memory_wait(1);backend_done=0;source_wait(6);
  if(done || failed || !dut.source_pending)$fatal(1,"stale delivery-edge terminal completed new seal");
  terminal(1,3);await_terminal(1,3);
 end else if(CASE==10)begin
  backend_ready=1;reset_n=1;accept_request();await_delivery();
  before_delivered=delivered;request=1;source_wait(6);request=0;
  if(delivered!=before_delivered || done || failed)$fatal(1,"pending bridge accepted a second request");
  terminal(1,5);await_terminal(1,5);hold=0;await_ready();
  if(delivered!=1 || terminals!=1 || code!=5)$fatal(1,"ignored pending request disturbed result");
 end
 $display("PASS seal bridge case=%0d delivered=%0d terminals=%0d",CASE,delivered,terminals);$finish;
end
initial begin #100000;$fatal(1,"seal bridge fixture deadline");end
endmodule
