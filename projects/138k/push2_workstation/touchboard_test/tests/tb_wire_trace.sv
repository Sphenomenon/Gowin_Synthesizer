`timescale 1ns/1ps
module tb_wire_trace;
    parameter RAW_WORDS=1, SAFE_GPIO=0, POWER_ADC=0, PROBE_SLIDER=0;
    reg clk=0;
    always #5 clk=~clk;
    tri1 scl1,sda1,scl2,sda2,scl3,sda3;
    wire uart,pa,ws;
    touchboard_wire_top #(.CLK_HZ(1000000),.RAW_WORDS(RAW_WORDS),.SAFE_GPIO(SAFE_GPIO),.POWER_ADC(POWER_ADC),.PROBE_SLIDER(PROBE_SLIDER)) dut(
      .clk_50m(clk),.button1_n(1'b1),.change_n(1'b1),.debug_uart_tx(uart),.pa_en(pa),.ws2812_din(ws),
      .scl1(scl1),.sda1(sda1),.scl2(scl2),.sda2(sda2),.scl3(scl3),.sda3(sda3));
    i2c_device_model u1(.scl(scl1),.sda(sda1),.enabled(1'b1));
    i2c_device_model u2(.scl(scl2),.sda(sda2),.enabled(1'b1));
    integer capture,bitnum,frames=0;
    reg [7:0] character;
    initial begin
      capture=$fopen("wire_uart.txt","w");
      forever begin
        @(negedge uart); repeat(5) @(posedge clk);
        if(uart!==0) $fatal(1,"start bit");
        for(bitnum=0;bitnum<8;bitnum=bitnum+1) begin
          repeat(9) @(posedge clk); character[bitnum]=uart;
        end
        repeat(9) @(posedge clk);
        if(uart!==1) $fatal(1,"stop bit");
        $fwrite(capture,"%c",character);
        if(character==10) frames=frames+1;
      end
    end
    initial begin
      force dut.boot=0;
      repeat(20) @(posedge clk);
      force dut.boot=20'hfffff;
      wait(PROBE_SLIDER ? dut.slider_probe.configured:dut.probe.configured);
      if(SAFE_GPIO && (PROBE_SLIDER ? u2.mem[73]:u1.mem[73])!=8'h1c) $fatal(1,"unused GPIO output readback");
      u1.mem[3]=8'hff;u1.mem[4]=8'hff;u2.mem[3]=8'hff;u2.mem[4]=8'hff;
      // Deliberately bad values must remain visible, never smoothed/hidden.
      u1.mem[100]=8'hc4;u1.mem[101]=8'h09;u2.mem[100]=8'hc4;u2.mem[101]=8'h09; // 2500
      wait(frames>=35);
      if(PROBE_SLIDER ? (scl1!==1 || sda1!==1):(scl2!==1 || sda2!==1)) $fatal(1,"inactive bus must be released");
      $fclose(capture);
      $display("PASS wire trace integration RAW_WORDS=%d UART frames=%d",RAW_WORDS,frames);
      $finish;
    end
    initial begin repeat(7000000) @(posedge clk); $fatal(1,"timeout frames=%d probe-state=%d",frames,dut.probe.state); end
endmodule
