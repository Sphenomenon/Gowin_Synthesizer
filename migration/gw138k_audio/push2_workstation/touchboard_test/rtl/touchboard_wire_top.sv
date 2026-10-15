// Temporary U1/U2 wire audit. Other I2C pads are released; no values are filtered.
module touchboard_wire_top #(parameter integer CLK_HZ=50000000,
    PROBE_BURST=1, PROBE_POLL_MS=32, PROBE_I2C_HZ=100000,
    parameter RAW_WORDS=1, SAFE_GPIO=0, POWER_ADC=0, PROBE_SLIDER=0)(
    input wire clk_50m,button1_n,change_n,
    output wire debug_uart_tx,pa_en,ws2812_din,
    inout wire scl1,sda1,scl2,sda2,scl3,sda3
);
    assign pa_en=1;
    assign scl3=1'bz; assign sda3=1'bz;
    reg [19:0] boot=0;
    reg btn_meta=1,btn_sync=1;
    reg [7:0] io_meta=8'hff,io_sync=8'hff;
    always @(posedge clk_50m) begin
      btn_meta<=button1_n; btn_sync<=btn_meta;
      io_meta<={sda1,sda2,scl1,scl2,ws2812_din,scl3,change_n,sda3};
      io_sync<=io_meta;
      if(!btn_sync) boot<=0; else if(!(&boot)) boot<=boot+1'b1;
    end
    wire rst_n=&boot;
    ws2812_black #(.CLK_HZ(CLK_HZ)) black(.clk(clk_50m),.rst_n(rst_n),.enable(1'b1),.din(ws2812_din),.complete());
    wire trace_valid,trace_read;
    wire [6:0] trace_length;
    wire [7:0] trace_pointer;
    wire [511:0] trace_rx;
    wire [3:0] trace_error;
    wire [4:0] trace_state;
    wire [31:0] trace_peak;
    wire trace_valid0,trace_read0,trace_valid1,trace_read1;
    wire [6:0] trace_length0,trace_length1;
    wire [7:0] trace_pointer0,trace_pointer1;
    wire [511:0] trace_rx0,trace_rx1;
    wire [3:0] trace_error0,trace_error1;
    wire [4:0] trace_state0,trace_state1;
    wire [31:0] trace_peak0,trace_peak1;
    qt2160_probe #(.CLK_HZ(CLK_HZ),.SLIDER(0),.BURST(PROBE_BURST[7:0]),.POLL_MS(PROBE_POLL_MS),
      .I2C_HZ(PROBE_I2C_HZ),.RAW_WORDS(RAW_WORDS),.AUDIT_CONFIG(1),.SAFE_GPIO(SAFE_GPIO)) probe(
      .clk(clk_50m),.rst_n(rst_n && !PROBE_SLIDER),.sample_taken(1'b1),.force_sleep(1'b0),.scl(scl1),.sda(sda1),
      .online(),.configured(),.raw_valid(),.sleeping(),.last_error(),.status(),.raw(),.device_address(),.raw_index(),
      .trace_valid(trace_valid0),.trace_read(trace_read0),.trace_length(trace_length0),
      .trace_pointer(trace_pointer0),.trace_rx(trace_rx0),.trace_error(trace_error0),.trace_state(trace_state0),.trace_peak(trace_peak0));
    qt2160_probe #(.CLK_HZ(CLK_HZ),.SLIDER(1),.BURST(PROBE_BURST[7:0]),.POLL_MS(PROBE_POLL_MS),
      .I2C_HZ(PROBE_I2C_HZ),.RAW_WORDS(RAW_WORDS),.AUDIT_CONFIG(1),.SAFE_GPIO(SAFE_GPIO)) slider_probe(
      .clk(clk_50m),.rst_n(rst_n && PROBE_SLIDER),.sample_taken(1'b1),.force_sleep(1'b0),.scl(scl2),.sda(sda2),
      .online(),.configured(),.raw_valid(),.sleeping(),.last_error(),.status(),.raw(),.device_address(),.raw_index(),
      .trace_valid(trace_valid1),.trace_read(trace_read1),.trace_length(trace_length1),
      .trace_pointer(trace_pointer1),.trace_rx(trace_rx1),.trace_error(trace_error1),.trace_state(trace_state1),.trace_peak(trace_peak1));
    assign trace_valid=PROBE_SLIDER ? trace_valid1:trace_valid0;
    assign trace_read=PROBE_SLIDER ? trace_read1:trace_read0;
    assign trace_length=PROBE_SLIDER ? trace_length1:trace_length0;
    assign trace_pointer=PROBE_SLIDER ? trace_pointer1:trace_pointer0;
    assign trace_rx=PROBE_SLIDER ? trace_rx1:trace_rx0;
    assign trace_error=PROBE_SLIDER ? trace_error1:trace_error0;
    assign trace_state=PROBE_SLIDER ? trace_state1:trace_state0;
    assign trace_peak=PROBE_SLIDER ? trace_peak1:trace_peak0;
    wire [519:0] sniff_rise,sniff_late;
    wire [64:0] sniff_nack;
    wire [6:0] sniff_count;
    wire sniff_stop,sniff_overflow,sniff_disagree;
    wire [31:0] sniff_gap;
    tb_i2c_listener listener(.clk(clk_50m),.rst_n(rst_n),.scl(PROBE_SLIDER ? scl2:scl1),.sda(PROBE_SLIDER ? sda2:sda1),
      .bytes_rise(sniff_rise),.bytes_late(sniff_late),.nack_bits(sniff_nack),.byte_count(sniff_count),
      .stopped(sniff_stop),.overflow(sniff_overflow),.disagreement(sniff_disagree),.start_gap(sniff_gap));
    reg [7:0] pointer_master,pointer_wire;
    always @(posedge clk_50m or negedge rst_n) begin
      if(!rst_n) begin pointer_master<=0; pointer_wire<=0; end
      else if(trace_valid && !trace_read && trace_error==0) begin
        pointer_master<=trace_pointer;
        pointer_wire<=sniff_count>=2 ? sniff_rise[15:8]:8'hff;
      end
    end
    wire [13:0] adc_last,adc_minimum,adc_maximum;
    wire [31:0] adc_count,adc_timeouts,adc_age,adc_duration;
    wire [7:0] adc_flags;
    generate if(POWER_ADC) begin:power_monitor
      tb_power_monitor #(.CLK_HZ(CLK_HZ)) power(.clk(clk_50m),.rst_n(rst_n),
        .last(adc_last),.minimum(adc_minimum),.maximum(adc_maximum),.count(adc_count),
        .timeouts(adc_timeouts),.age(adc_age),.duration(adc_duration),.flags(adc_flags));
    end else begin:no_power_monitor
      assign adc_last=0;assign adc_minimum=0;assign adc_maximum=0;
      assign adc_count=0;assign adc_timeouts=0;assign adc_age=0;assign adc_duration=0;assign adc_flags=0;
    end endgenerate
    localparam integer BYTES=POWER_ADC ? 249:225, DATA_END=4+BYTES*2;
    reg [BYTES*8-1:0] packet;
    reg [31:0] seq;
    reg [5:0] selection;
    wire [7:0] wanted_pointer=selection==0 ? 8'd0 : selection==1 ? 8'd12 : 8'd100+((selection-2)<<1);
    wire selected_trace=trace_read && pointer_master==wanted_pointer;
    reg [15:0] crc;
        reg [9:0] ci;
    reg [1:0] tx_state;
    integer j;
    wire uart_ready;
    wire uart_valid=tx_state==2;
    function automatic [7:0] hexchar(input [3:0] n);
      hexchar=n<10 ? 8'd48+{4'd0,n}:8'd55+{4'd0,n};
    endfunction
    function automatic [15:0] crc_byte(input [15:0] initial_crc,input [7:0] value);
      reg [15:0] c; integer j;
      begin c=initial_crc^{value,8'd0}; for(j=0;j<8;j=j+1) c=c[15] ? (c<<1)^16'h1021:(c<<1); crc_byte=c; end
    endfunction
    reg [7:0] character,byte_value;
    always @* begin
      character=32; byte_value=0;
      case(ci)
        0:character="T"; 1:character=POWER_ADC ? "A":"W"; 2:character="1"; 3:character=32;
        default:if(ci<DATA_END) begin
          byte_value=packet[7:0];
          character=hexchar(ci[0] ? byte_value[3:0]:byte_value[7:4]);
        end else if(ci==DATA_END) character=32;
        else if(ci==DATA_END+1) character=hexchar(crc[15:12]);
        else if(ci==DATA_END+2) character=hexchar(crc[11:8]);
        else if(ci==DATA_END+3) character=hexchar(crc[7:4]);
        else if(ci==DATA_END+4) character=hexchar(crc[3:0]);
        else if(ci==DATA_END+5) character=13; else character=10;
      endcase
    end
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(115200)) uart(.clk(clk_50m),.rst_n(rst_n),
      .data({24'd0,character}),.valid(uart_valid),.ready(uart_ready),.serial_out(debug_uart_tx),.byte_done());
    always @(posedge clk_50m or negedge rst_n) begin
      if(!rst_n) begin tx_state<=0; packet<=0; seq<=0; selection<=0; crc<=16'hffff; ci<=0; end
      else case(tx_state)
        0:if(trace_valid && selected_trace) begin
          packet<=0;
          packet[31:0]<=seq;
          packet[4*8 +: 8]<=pointer_master;
          packet[5*8 +: 8]<=pointer_wire;
          packet[6*8 +: 8]<={3'd0,trace_state};
          packet[7*8 +: 8]<={4'd0,trace_error};
          packet[8*8 +: 8]<={1'b0,trace_length};
          packet[9*8 +: 8]<={1'b0,sniff_count};
          packet[10*8 +: 8]<={3'd0,sniff_disagree,sniff_overflow,sniff_stop,trace_read,1'b0};
          packet[11*8 +: 8]<=io_sync;
          packet[12*8 +: 8]<=PROBE_BURST[7:0];
          packet[13*8 +: 8]<={PROBE_SLIDER!=0,6'd0,RAW_WORDS!=0};
          packet[14*8 +: 32]<=trace_peak;
          packet[18*8 +: 32]<=sniff_gap;
          for(j=0;j<64;j=j+1)
            packet[(22+j)*8 +: 8]<=j<trace_length ? trace_rx[j*8 +: 8]:8'd0;
          packet[86*8 +: 520]<=sniff_rise;
          packet[151*8 +: 520]<=sniff_late;
          packet[216*8 +: 72]<={7'd0,sniff_nack};
          if(POWER_ADC) begin
            packet[225*8 +: 16]<={2'd0,adc_last};
            packet[227*8 +: 16]<={2'd0,adc_minimum};
            packet[229*8 +: 16]<={2'd0,adc_maximum};
            packet[231*8 +: 32]<=adc_count;
            packet[235*8 +: 32]<=adc_timeouts;
            packet[239*8 +: 32]<=adc_age;
            packet[243*8 +: 32]<=adc_duration;
            packet[247*8 +: 8]<=adc_flags;
            packet[248*8 +: 8]<=8'd4; // VCCIO4, divider 8; SOM rail, separate from PMOD supply.
          end
          selection<=selection==(RAW_WORDS ? 33:2) ? 0:selection+1'b1;
          seq<=seq+1'b1; crc<=16'hffff; ci<=0; tx_state<=2;
        end
        // Shift one byte after its low hex nibble is accepted. This avoids
        // two large 225:1 byte multiplexers in the diagnostic UART path.
        2:if(uart_ready) begin
          if(ci>=4 && ci<DATA_END) begin
            if(!ci[0]) crc<=crc_byte(crc,packet[7:0]);
            else packet<=packet>>8;
          end
          if(ci==DATA_END+6) tx_state<=3; else ci<=ci+1'b1;
        end
        3:tx_state<=0;
      endcase
    end
endmodule
