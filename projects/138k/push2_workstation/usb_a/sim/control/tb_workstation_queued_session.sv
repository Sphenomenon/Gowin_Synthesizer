`timescale 1ns/1ps
module queued_session;
reg clk=0;always #5 clk=~clk;
reg rst=0,cpu_valid=0,consume=0;reg [17:0] cpu_event=0;
wire cpu_ready,internal_event,lifecycle,initializing;
wire fifo_valid,fifo_ready,event_valid,event_ready,arbiter_ready;
wire [17:0] fifo_event,event_word;wire [3:0] step;
assign event_ready=consume && !lifecycle;
workstation_event_queue queue(.clk(clk),.reset_n(rst),.clear(lifecycle),
 .g1_valid(1'b0),.pc_valid(1'b0),.cpu_valid(cpu_valid && !internal_event && !initializing),
 .g1_data(18'd0),.pc_data(18'd0),.cpu_data(cpu_event),
 .g1_ready(),.pc_ready(),.cpu_ready(arbiter_ready),
 .event_valid(fifo_valid),.event_ready(fifo_ready),.event_data(fifo_event));
workstation_session session(.clk_i(clk),.rst_ni(rst),
 .cpu_valid_i(cpu_valid),.cpu_event_i(cpu_event),.arbiter_ready_i(arbiter_ready),
 .cpu_ready_o(cpu_ready),.internal_o(internal_event),.lifecycle_o(lifecycle),
 .fifo_valid_i(fifo_valid),.fifo_event_i(fifo_event),.fifo_ready_o(fifo_ready),
 .cue_valid_i(1'b0),.cue_stop_i(lifecycle),.cue_event_i(18'd0),.cue_ready_o(),
 .event_ready_i(event_ready),.event_valid_o(event_valid),.event_o(event_word),
 .mode_pending_i(1'b0),.mode_i(2'd2),.initializing_o(initializing),.initialization_step_o(step));
reg [17:0] observed[0:63];integer seen=0;
always @(posedge clk)if(rst && event_valid && event_ready)begin
 observed[seen]=event_word;seen=seen+1;
end
task send(input [17:0] word);integer waits;begin
 @(negedge clk);cpu_event=word;cpu_valid=1;waits=0;#0.1;
 while(!cpu_ready)begin @(negedge clk);#0.1;waits=waits+1;if(waits>100)$fatal(1,"CPU admission stalled");end
 @(posedge clk);#0.1;@(negedge clk);cpu_valid=0;
end endtask
task drain(input integer target);integer waits;begin
 consume=1;waits=0;
 while(seen<target)begin @(negedge clk);waits=waits+1;if(waits>100)$fatal(1,"drain stalled");end
 repeat(5)@(negedge clk);
 if(seen!=target)$fatal(1,"stale or duplicate event target=%0d seen=%0d",target,seen);
end endtask
initial begin
 #1;rst=1;#1;rst=0;#1;rst=1;
 // All three accepted words (session plus queue) must be cancelled, including
 // a full tail word which the historical one-slot drain could not remove.
 send({4'd1,7'd60,7'd80});send({4'd2,7'd5,7'd73});send({4'd0,7'd60,7'd0});
 if(queue.count!==2 || !event_valid)$fatal(1,"did not fill session and queue");
 send({4'd15,7'd0,7'd0});
 if(queue.count!==0 || event_valid)$fatal(1,"detach failed to atomically purge old words");
 consume=1;repeat(8)@(negedge clk);if(seen!=0)$fatal(1,"cancelled event escaped");consume=0;
 // PANIC is a normal ordered event. A later note belongs after that PANIC
 // and must survive; queue cancellation only comes from session lifecycle.
 send({4'd2,7'd120,7'd0});send({4'd1,7'd64,7'd99});send({4'd0,7'd64,7'd0});
 drain(3);
 if(observed[0]!=={4'd2,7'd120,7'd0} || observed[1]!=={4'd1,7'd64,7'd99} ||
    observed[2]!=={4'd0,7'd64,7'd0})$fatal(1,"PANIC/note ordering changed");
 consume=0;send({4'd1,7'd66,7'd88});send({4'd1,7'd67,7'd89});send({4'd1,7'd68,7'd90});
 // Attach with initialization cancels every queued old word first. The real
 // session owner then emits its thirteen existing initialization commands.
 send({4'd15,7'd1,7'd1});
 if(queue.count!==0 || event_valid || !initializing)$fatal(1,"attach did not fence old events");
 drain(16);
 if(observed[3]!=={4'd2,7'd96,7'd0} || observed[10]!=={4'd2,7'd5,7'd0} ||
    observed[15]!=={4'd2,7'd81,7'd0} || initializing)$fatal(1,"attach initialization changed");
 consume=0;send({4'd1,7'd72,7'd100});drain(17);
 if(observed[16]!=={4'd1,7'd72,7'd100})$fatal(1,"new session note missing");
 rst=0;#0.1;if(event_valid || queue.count!==0)$fatal(1,"reset did not clear pending events");
 $display("PASS queued session full detach/attach cancellation, 13 initialization commands, PANIC/note order, reset");$finish;
end
initial begin #200000;$fatal(1,"queued session watchdog");end
endmodule
