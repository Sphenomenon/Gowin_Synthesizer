`timescale 1ns/1ps
module tb_startup_panic;
    parameter integer BIT_CLOCKS=16;
    parameter integer CLK_HZ=BIT_CLOCKS==434?50_000_000:BIT_CLOCKS*115200;
    reg clk=0,rst=0,ready=0,serial_in=1;
    wire serial_out,done;
    integer bytes=0,boots=0;
    reg [7:0] decoded;
    always #10 clk=~clk;
    basic_pitch_startup_panic #(.CLK_HZ(CLK_HZ),.BAUD(115200)) dut(
        .clk_i(clk),.rst_ni(rst),.system_ready_i(ready),.serial_i(serial_in),.serial_o(serial_out),.done_o(done));
    task tick;begin @(posedge clk);#1;end endtask
    // Independent bit-center decoder; no use of transmitter index or payload.
    initial forever begin
        @(negedge serial_out);
        if(dut.state==1) begin
        repeat(BIT_CLOCKS/2)tick();if(serial_out!==0)$fatal(1,"bad start bit");
        for(integer bitno=0;bitno<8;bitno=bitno+1)begin
            repeat(BIT_CLOCKS)tick();decoded[bitno]=serial_out;
        end
        repeat(BIT_CLOCKS)tick();if(serial_out!==1)$fatal(1,"bad stop bit");
        case(bytes%3)
            0:if(decoded!==8'hb0)$fatal(1,"bad control status");
            1:if(decoded!==8'd120)$fatal(1,"bad Panic CC");
            2:if(decoded!==8'd0)$fatal(1,"bad Panic value");
        endcase
        if(done)$fatal(1,"done before final stop bit finished");
        bytes=bytes+1;
        end
    end
    task passthrough;
        begin
            for(integer i=0;i<20;i=i+1)begin
                serial_in=i[0];tick();if(serial_out!==serial_in)$fatal(1,"passthrough modified input");
            end
            serial_in=1;
        end
    endtask
    task startup;
        integer previous;
        begin
            previous=bytes;rst=0;repeat(3)tick();rst=1;ready=0;
            passthrough();if(done)$fatal(1,"completed without ready");
            ready=1;repeat(5)tick();ready=0;repeat(40)tick();
            if(done || bytes!=previous || dut.state!=0)$fatal(1,"short ready pulse started boot Panic");
            ready=1;
            repeat(BIT_CLOCKS*35+100)tick();
            if(!done || bytes!=previous+3)$fatal(1,"did not emit exactly one complete Panic");
            ready=0;passthrough();ready=1;passthrough();
            if(bytes!=previous+3)$fatal(1,"ready loss/recovery repeated Panic");
        end
    endtask
    initial begin
        startup();startup();
        $display("PASS startup Panic bits=%0d two global resets,6 exact control bytes,short readiness rejected,stop timing,pass-through",BIT_CLOCKS);$finish;
    end
endmodule
