`timescale 1ns/1ps
module tb_diag;
 reg clk=0; always #5 clk=~clk;
 tri1 scl1,sda1,scl2,sda2,scl3,sda3,change_n,ws2812_din;
 wire tx,pa;
 touchboard_diag_top #(.CLK_HZ(1000000)) dut(.clk_50m(clk),.button1_n(1'b1),.debug_uart_tx(tx),.pa_en(pa),
 .scl1(scl1),.sda1(sda1),.scl2(scl2),.sda2(sda2),.scl3(scl3),.sda3(sda3),.change_n(change_n),.ws2812_din(ws2812_din));
 i2c_device_model #(.CHECK_PROTOCOL(0)) q1(.scl(scl1),.sda(sda1),.enabled(1'b1));
 // Deliberately reversed lines: discovery must report this actual pair.
 i2c_device_model #(.CHECK_PROTOCOL(0)) q2(.scl(sda2),.sda(scl2),.enabled(1'b1));
 i2c_device_model #(.ADDRESS(7'h40),.CHECK_PROTOCOL(0)) pca(.scl(scl3),.sda(sda3),.enabled(1'b1));
 // Wrong pad pairs intentionally create non-I2C edges on other devices.
 // Their model must tolerate these; normal test.py still enforces protocol.
 integer capture,bitnum,frames=0;
 reg [7:0] byte_value;
 initial begin
   capture=$fopen("diag_uart.txt","w");
   force dut.boot=0; repeat(20) @(posedge clk); force dut.boot=20'hfffff;
   forever begin
     @(negedge tx); repeat(4) @(posedge clk);
     if(tx!==0) $fatal(1,"start");
     for(bitnum=0;bitnum<8;bitnum=bitnum+1) begin repeat(9) @(posedge clk); byte_value[bitnum]=tx; end
     repeat(9) @(posedge clk); if(tx!==1) $fatal(1,"stop");
     $fwrite(capture,"%c",byte_value);
     if(byte_value==10) begin
       frames=frames+1;
       if(frames==344) begin $fclose(capture); $display("PASS diagnostic sweep 344 actual UART frames"); $finish; end
     end
   end
 end
 initial begin repeat(16000000) @(posedge clk); $fatal(1,"diagnostic sweep timeout state=%d cl=%d da=%d frames=%d",dut.state,dut.cl,dut.da,frames); end
endmodule
