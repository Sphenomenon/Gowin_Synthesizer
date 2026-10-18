`timescale 1ns/1ps
module tb_diag_full;
 reg clk=0;always #5 clk=~clk;
 tri1 scl1,sda1,scl2,sda2,scl3,sda3,change_n,ws2812_din;
 wire tx,pa;
 touchboard_diag_top #(.CLK_HZ(1000000),.FULL_SCAN(1)) dut(.clk_50m(clk),.button1_n(1'b1),.debug_uart_tx(tx),.pa_en(pa),
 .scl1(scl1),.sda1(sda1),.scl2(scl2),.sda2(sda2),.scl3(scl3),.sda3(sda3),.change_n(change_n),.ws2812_din(ws2812_din));
 i2c_device_model #(.CHECK_PROTOCOL(0)) q1(.scl(scl1),.sda(sda1),.enabled(1'b1));
 i2c_device_model #(.ADDRESS(7'h52),.CHECK_PROTOCOL(0)) unknown(.scl(sda2),.sda(scl2),.enabled(1'b1));
 i2c_device_model #(.ADDRESS(7'h40),.CHECK_PROTOCOL(0)) pca(.scl(scl3),.sda(sda3),.enabled(1'b1));
 integer reports=0,gpio=0,acks=0,i;
 reg [6271:0] coverage=0;
 initial begin
   // UART framing/CRC is covered by tb_diag; accelerate only report sending.
   force dut.boot=0;repeat(20) @(posedge clk);force dut.boot=20'hfffff;
   force dut.uart_ready=1;
 end
 integer idx,rank;
 always @(posedge clk) if(dut.send) begin
   if(dut.report_kind==0) gpio=gpio+1;
   else begin
     if(dut.cl==dut.da || dut.target(dut.ai)<8 || dut.target(dut.ai)>119) $fatal(1,"full scan bounds");
     rank=dut.da<dut.cl ? dut.da:dut.da-1;
     idx=(dut.cl*7+rank)*112+dut.ai;
     if(coverage[idx]) $fatal(1,"duplicate address/pair");coverage[idx]=1;reports=reports+1;
     if(dut.report_kind==2 && dut.report_error==0) begin
       acks=acks+1;
       if(!((dut.cl==5 && dut.da==7 && dut.target(dut.ai)==7'h0d) ||
            (dut.cl==6 && dut.da==4 && dut.target(dut.ai)==7'h52) ||
            (dut.cl==2 && dut.da==0 && dut.target(dut.ai)==7'h40))) $fatal(1,"unexpected ACK pair");
     end
     if(reports==6272) begin
       if(coverage!=={6272{1'b1}} || gpio!=8 || acks!=3) $fatal(1,"full scan coverage/ACKs");
       $display("PASS all 56*112 pairs, bounds, exact coverage, normal/reversed/unexpected-address devices");$finish;
     end
   end
 end
 initial begin repeat(20000000) @(posedge clk);$fatal(1,"full diagnostic timeout reports=%d",reports);end
endmodule
