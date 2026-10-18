`timescale 1ns/1ps
module tb_touchboard;
    reg clk=0;
    always #5 clk=~clk;
    reg button=1,enabled1=1,enabled2=1;
    tri1 scl1,sda1,scl2,sda2,scl3,sda3;
    wire uart,pa;
    tri0 ws;
    touchboard_top #(.CLK_HZ(1000000)) dut(
      .clk_50m(clk),.button1_n(button),.debug_uart_tx(uart),
      .scl1(scl1),.sda1(sda1),.scl2(scl2),.sda2(sda2),.scl3(scl3),.sda3(sda3),
      .change_n(1'b0),.ws2812_din(ws),.pa_en(pa));
    i2c_device_model u1(.scl(scl1),.sda(sda1),.enabled(enabled1));
    i2c_device_model u2(.scl(scl2),.sda(sda2),.enabled(enabled2));
    i2c_device_model #(.ADDRESS(7'h40)) u3(.scl(scl3),.sda(sda3),.enabled(1'b1));
    integer capture;
    integer received=0;
    integer bitnum;
    reg [7:0] byte_value;
    time last_lf=0;
    time touch_started;
    initial begin
      capture=$fopen("uart.txt","w");
      forever begin
        @(negedge uart);
        // Rounded BIT_CLKS=9 at the accelerated 1 MHz model clock.
        repeat(4) @(posedge clk);
        if(uart!==0) $fatal(1,"UART start bit");
        for(bitnum=0;bitnum<8;bitnum=bitnum+1) begin
          repeat(9) @(posedge clk); byte_value[bitnum]=uart;
        end
        repeat(9) @(posedge clk);
        if(uart!==1) $fatal(1,"UART stop bit");
        if(byte_value==10) begin
          if(last_lf!=0 && ($time-last_lf<199900 || $time-last_lf>200100)) $fatal(1,"UART must publish at 50 Hz");
          last_lf=$time;
        end
        $fwrite(capture,"%c",byte_value); received=received+1;
      end
    end
    initial begin
      force dut.boot_count=0;
      repeat(20) @(posedge clk);
      u1.mem[0]=8'h22;
      force dut.boot_count=20'hfffff;
      wait(dut.error1==5);
      if(dut.online[0] || dut.configured[0] || u1.mem[12]!=0) $fatal(1,"unknown ID must not configure");
      u1.mem[0]=8'h11;
      wait(dut.keys.state==5);
      u1.mem[54]=3;
      wait(dut.error1==6);
      if(dut.configured[0] || u1.mem[10]!=0) $fatal(1,"readback mismatch must not calibrate/claim ready");
      wait(dut.configured==3);
      if(u1.mem[20]!=0 || u2.mem[20]!=8'h28 || u2.mem[21]!=0) $fatal(1,"slider config");
      if(u1.mem[54]!=1 || u1.mem[69]!=1 || u2.mem[61]!=1 || u2.mem[62]!=0 || u2.mem[69]!=0) $fatal(1,"burst config");
      if(u1.mem[22]!=0 || u2.mem[22]!=1 || u2.mem[29]!=1) $fatal(1,"AKS config");
      if(u1.mem[38]!=10 || u2.mem[53]!=10 || u1.mem[12]!=1 || u2.mem[13]!=1 || u2.mem[17]!=3) $fatal(1,"threshold/LP/BREP/DI config");
      wait(dut.raw_valid==3); // Exclude the intentional startup calibration delay.
      u1.mem[3]=8'h05; u1.mem[4]=8'h80;
      u2.mem[2][0]=1; u2.mem[3]=8'h03; u2.mem[5]=173;
      touch_started=$time;
      wait(dut.status1[39:24]==16'h8005 && dut.status2[47:40]==173);
      $display("STATUS_LATENCY_MODEL_NS=%0d",$time-touch_started);
      if($time-touch_started>400000) $fatal(1,"status update must not wait for 16 diagnostic channels");
      if(dut.raw1[15:0]!=1000-dut.raw_index1 || dut.raw1[31:16]!=1000 || dut.raw2[31:16]!=1000) $fatal(1,"raw signal/reference read offset");
      repeat(1000000) @(posedge clk);
      u1.mem[3]=0; u1.mem[4]=0; u2.mem[2][0]=0;
      wait(dut.status1[39:24]==0 && dut.status2[16]==0);
      repeat(100000) @(posedge clk);
      if(dut.AUDIT_CONFIG) begin
        wait(dut.keys.state==7);
        u1.mem[38]=255;
        wait(dut.error1==6);
        if(dut.configured[0] || dut.raw_valid[0]) $fatal(1,"runtime config mismatch must invalidate ready/raw");
        wait(dut.configured==3 && dut.raw_valid==3);
        if(u1.mem[38]!=10) $fatal(1,"runtime mismatch recovery must restore config");
      end
      enabled1=0;
      wait(!dut.online[0]);
      if(dut.error1!=1 || dut.configured[0]!=0 || dut.raw_valid[0]!=0) $fatal(1,"NACK invalidation");
      repeat(100000) @(posedge clk);
      u1.slave_address=7'h17;
      enabled1=1;
      wait(dut.configured==3 && dut.online==3);
      if(dut.address1!=7'h17) $fatal(1,"alternate QT2160 address discovery");
      repeat(150000) @(posedge clk);
      force dut.force_sleep=1'b1;
      wait(dut.sleeping==3);
      if(u1.mem[12]!=0 || u2.mem[12]!=0) $fatal(1,"sleep command/readback");
      repeat(150000) @(posedge clk);
      if(received<1000) $fatal(1,"UART frame coverage");
      if(u1.stop_count<100 || u2.stop_count<60) $fatal(1,"STOP coverage");
      $fclose(capture);
      $display("PASS top: wrong-ID guard, bad-readback guard, identity/config readback, LP/BREP/DI, 16 keys, slider, contiguous signal/reference, release, NACK/reconnect, alternate address discovery, UART8N1, STOP gaps");
      $finish;
    end
    initial begin repeat(12000000) @(posedge clk); $fatal(1,"timeout state1=%d state2=%d err1=%d err2=%d",dut.keys.state,dut.slider.state,dut.error1,dut.error2); end
endmodule
