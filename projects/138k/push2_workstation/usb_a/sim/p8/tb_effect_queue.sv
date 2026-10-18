`timescale 1ns/1ps
module tb_effect_queue;
reg clk=0,rst=0,valid=0;
always #5 clk=~clk;
reg [6:0] a=0,b=0;
wire ready,ev,er;
wire [17:0] event_data;
wire [2:0] mask;
wire [5:0] order;
wire [31:0] applied;
push2_controls push(.clk(clk),.rst(!rst),.connected(1'b1),.valid(valid),.ready(ready),.kind(4'd11),.cable(4'd0),.channel(4'd0),.a(a),.b(b),
 .actual_control({29'd0,mask}),.actual_options(32'd0),.event_valid(ev),.event_ready(er),.event_data(event_data));
gw138k_event_workstation dut(.clk_i(clk),.rst_ni(rst),.midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
 .cpu_event_valid_i(ev),.cpu_event_i(event_data),.cpu_event_ready_o(er),.sample_ce_i(1'b0),.pcm_left_i(32'd0),.pcm_right_i(32'd0),
 .effect_mask_o(mask),.effect_order_o(order),.applied_events_o(applied));
integer count=0;
task send(input integer id, velocity);
 begin
  @(negedge clk);a=7'(20+id);b=7'(velocity);valid=1;
  do @(posedge clk);while(!ready);
  @(negedge clk);valid=0;repeat(12) @(posedge clk);
 end
endtask
task press(input integer id);
 begin send(id,127);send(id,0);count++;if(applied!=count)$fatal(1,"unified event not applied exactly once");end
endtask
task check(input [2:0] m,input [5:0] o,input integer slots);
 begin if(mask!==m || order!==o || dut.effect_count!=slots)$fatal(1,"queue mask=%h order=%h slots=%0d wanted %h %h %0d",mask,order,dut.effect_count,m,o,slots);end
endtask
initial begin
 #12;rst=1;repeat(20) @(posedge clk);
 for(integer i=0;i<3;i++) for(integer j=0;j<3;j++) if(i!=j) begin
  automatic integer k=3-i-j;
  press(i);check(3'(1<<i),{4'b1111,2'(i)},1);
  repeat(3) begin press(i);check(3'(1<<i),{4'b1111,2'(i)},1);end
  press(j);check(3'((1<<i)|(1<<j)),{2'b11,2'(j),2'(i)},2);
  press(i);press(j);check(3'((1<<i)|(1<<j)),{2'b11,2'(j),2'(i)},2);
  press(k);check(7,{2'(k),2'(j),2'(i)},3);
 end
 press(2);check(4,6'b11_11_10,1);
 $display("PASS Push CC20-22 -> unified event arbitration -> effect queue: 6 permutations, duplicate presses leave 1/2 slots unchanged, full-queue restart; %0d presses",count);$finish;
end
initial begin #1000000;$fatal(1,"timeout");end
endmodule
