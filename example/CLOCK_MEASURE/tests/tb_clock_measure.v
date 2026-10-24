`timescale 1ns/1ps
module tb_clock_measure;
    reg refclk=0, a=0, b=0, rst_n=0, b_run=1;
    always #5 refclk=~refclk;
    initial begin #3; forever #17 a=~a; end
    initial begin #7; forever begin #13; if(b_run) b=~b; else b=0; end end
    wire [31:0] id,ca,cb,ea,eb,hb;
    clock_measure #(.GATE_CYCLES(97),.WARMUP_CYCLES(16),.COUNTER_WIDTH(8)) dut (
        .clk_ref(refclk),.clk_a(a),.clk_b(b),.restart_n(rst_n),
        .window_id(id),.count_a(ca),.count_b(cb),.endpoint_a(ea),.endpoint_b(eb),.heartbeat(hb));
    integer windows=0, wraps=0;
    reg [31:0] old_id=0, old_ea=0;
    time last_window=0;
    always @(negedge refclk) begin
        if (id != old_id && id != 0) begin
            if (last_window != 0 && $time-last_window != 970) $fatal(1,"Reference gate length changed");
            if (ca < 28 || ca > 30) $fatal(1,"Wrong A edge count %d",ca);
            if (id <= 9 || id >= 17)
                if (cb < 36 || cb > 39) $fatal(1,"Wrong B edge count %d",cb);
            if (id >= 12 && id <= 14 && cb != 0) $fatal(1,"Stopped source not detected");
            if (ea < old_ea) wraps=wraps+1;
            old_ea=ea; old_id=id; last_window=$time; windows=windows+1;
            if(id==10) b_run=0;
            if(id==15) b_run=1;
        end
    end
    initial begin
        #41 rst_n=1;
        wait(id==24); #2;
        if(windows < 23 || wraps < 2) $fatal(1,"Missing gate/overflow coverage");
        rst_n=0; #200;
        if(id!=0 || ca!=0 || cb!=0) $fatal(1,"Reset did not clear result");
        old_id=0; last_window=0; rst_n=1;
        wait(id==2); #10;
        $display("PASS exact reference gates, asynchronous edge counts, counter wraps, stopped/restarted oscillator and reset");
        $finish;
    end
    initial begin #100000; $fatal(1,"Timeout"); end
endmodule
