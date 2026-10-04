`timescale 1ns/1ps
module tb_scope_push;
    reg clk=0;always #5 clk=~clk;
    reg rst=1,valid=0;
    reg [3:0] kind=0;
    reg [6:0] a=0,b=0;
    wire ready,event_valid;
    wire [17:0] event_data;
    wire [63:0] held;
    push2_controls dut(.clk(clk),.rst(rst),.connected(1'b1),.valid(valid),.ready(ready),.kind(kind),.cable(4'd0),.channel(4'd0),.a(a),.b(b),
        .actual_control(32'd0),.actual_options(32'd0),.actual_panic_epoch(10'd0),.event_valid(event_valid),.event_ready(1'b1),.event_data(event_data),
        .held(held),.last_note(),.last_velocity(),.mapped(),.ignored());
    task automatic send(input integer k,aa,bb,expected);
        begin
            kind=4'(k);a=7'(aa);b=7'(bb);valid=1;@(negedge clk);valid=0;
            if(!event_valid || event_data!=18'(expected))$fatal(1,"Push mapping %0d %0d got %h expected %h",aa,bb,event_data,expected);
            @(negedge clk);
        end
    endtask
    initial begin
        repeat(4)@(negedge clk);rst=0;repeat(4)@(negedge clk);
        send(11,51,127,(2<<14)|(104<<7)|64);
        send(11,87,127,(2<<14)|(105<<7)|64);
        send(11,88,127,(2<<14)|(105<<7)|127);
        send(11,44,127,(2<<14)|(108<<7));
        send(11,45,127,(2<<14)|(108<<7)|127);
        send(11,48,127,(2<<14)|(90<<7)|64);
        send(11,74,127,(2<<14)|(93<<7)|126);
        send(11,75,127,(2<<14)|(94<<7)|127); // signed relative encoder -1 wraps
        send(11,76,2,(2<<14)|(92<<7)|2);
        send(11,77,127,(2<<14)|(91<<7)|7);
        send(11,78,1,(2<<14)|(103<<7)|65);
        send(11,60,127,(2<<14)|(95<<7)|64);
        send(11,31,127,(2<<14)|(96<<7)|127);
        send(9,36,2,(1<<14)|(36<<7)|30);
        send(8,36,0,(0<<14)|(36<<7));
        send(14,0,64,(4<<14)|(0<<7)|64);
        send(11,29,127,(2<<14)|(120<<7));
        $display("PASS scope_push pads, existing force curve, signed knobs, mute, scene arm, bend");$finish;
    end
endmodule
