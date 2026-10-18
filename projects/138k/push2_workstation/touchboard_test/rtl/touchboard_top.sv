module touchboard_top #(parameter integer CLK_HZ=50000000,
    PROBE_BURST=1, PROBE_POLL_MS=16, PROBE_I2C_HZ=100000, SLEEP_AFTER_MS=0,
    parameter [15:0] PROBE_KEY_MASK=16'hffff,
    parameter BLACK_LEDS=1, RAW_WORDS=0, AUDIT_CONFIG=0, SAFE_GPIO=1,
    parameter ISOLATE_U1=0, FRAME_HZ=50)(
    input wire clk_50m,button1_n,
    output wire debug_uart_tx,
    inout wire scl1,sda1,scl2,sda2,scl3,sda3,
    input wire change_n,
    output wire ws2812_din,
    output wire pa_en
);
    assign pa_en=1'b1; // Disable the audio power amplifier in this standalone probe.
    reg [19:0] boot_count=0;
    reg button_meta=1,button_sync=1;
    reg change_meta=1,change_sync=1;
    reg [7:0] io_meta=8'hff,io_sync=8'hff;
    always @(posedge clk_50m) begin
      button_meta<=button1_n; button_sync<=button_meta;
      change_meta<=change_n; change_sync<=change_meta;
      io_meta<={sda1,sda2,scl1,scl2,ws2812_din,scl3,change_n,sda3};
      io_sync<=io_meta;
      if(!button_sync) boot_count<=0;
      else if(!(&boot_count)) boot_count<=boot_count+1'b1;
    end
    wire rst_n=&boot_count;
    ws2812_black #(.CLK_HZ(CLK_HZ)) black_frame(.clk(clk_50m),.rst_n(rst_n),.enable(BLACK_LEDS!=0),.din(ws2812_din),.complete());
    wire [1:0] online,configured,raw_valid,sleeping;
    reg [31:0] sleep_count;
    always @(posedge clk_50m or negedge rst_n) begin
      if(!rst_n) sleep_count<=0;
      else if(SLEEP_AFTER_MS!=0 && sleep_count<CLK_HZ/1000*SLEEP_AFTER_MS) sleep_count<=sleep_count+1'b1;
    end
    wire force_sleep=SLEEP_AFTER_MS!=0 && sleep_count>=CLK_HZ/1000*SLEEP_AFTER_MS;
    wire sample_taken;
    wire [3:0] error1,error2,error3;
    wire [55:0] status1,status2;
    wire [31:0] raw1,raw2;
    wire [3:0] raw_index1,raw_index2;
    wire [6:0] address1,address2;
    wire [127:0] scan;
    qt2160_probe #(.CLK_HZ(CLK_HZ),.SLIDER(0),.AUDIT_CONFIG(AUDIT_CONFIG),.SAFE_GPIO(SAFE_GPIO),.RAW_WORDS(RAW_WORDS),.KEY_MASK(PROBE_KEY_MASK),.BURST(PROBE_BURST[7:0]),.POLL_MS(PROBE_POLL_MS),.I2C_HZ(PROBE_I2C_HZ)) keys(
      .clk(clk_50m),.rst_n(rst_n),.sample_taken(sample_taken),.force_sleep(force_sleep),.sleeping(sleeping[0]),.scl(scl1),.sda(sda1),.online(online[0]),
      .configured(configured[0]),.raw_valid(raw_valid[0]),.last_error(error1),.status(status1),.raw(raw1),.raw_index(raw_index1),.device_address(address1));
    qt2160_probe #(.CLK_HZ(CLK_HZ),.SLIDER(1),.AUDIT_CONFIG(AUDIT_CONFIG),.SAFE_GPIO(SAFE_GPIO),.RAW_WORDS(RAW_WORDS),.KEY_MASK(PROBE_KEY_MASK),.BURST(PROBE_BURST[7:0]),.POLL_MS(PROBE_POLL_MS),.I2C_HZ(PROBE_I2C_HZ)) slider(
      .clk(clk_50m),.rst_n(rst_n && !ISOLATE_U1),.sample_taken(sample_taken),.force_sleep(force_sleep),.sleeping(sleeping[1]),.scl(scl2),.sda(sda2),.online(online[1]),
      .configured(configured[1]),.raw_valid(raw_valid[1]),.last_error(error2),.status(status2),.raw(raw2),.raw_index(raw_index2),.device_address(address2));
    tb_i2c_scan #(.CLK_HZ(CLK_HZ)) leds(
      .clk(clk_50m),.rst_n(rst_n && !ISOLATE_U1),.scl(scl3),.sda(sda3),.acknowledgements(scan),.last_error(error3));

    // 52 byte packet, little endian integers. Hex transport is terminal-safe.
    // Flags: bit0/1 config, bit4/5 raw_valid. error3 is in error1/2 high nibbles.
    localparam integer BYTES=52;
    localparam [9:0] DATA_END=10'd108, CRC_0=10'd109, CRC_1=10'd110,
      CRC_2=10'd111, CRC_3=10'd112, CR_POS=10'd113, LF_POS=10'd114;
    localparam [8:0] LAST_BYTE=9'd51;
    reg [BYTES*8-1:0] payload;
    reg [31:0] frame_sequence,timer;
    reg [15:0] crc;
    reg [8:0] crc_index;
    reg [9:0] char_index;
    reg [1:0] state;
    assign sample_taken=rst_n && state==0 && timer==0;
    wire uart_ready;
    wire uart_valid=state==2;
    reg [7:0] character;
    function automatic [7:0] hexchar(input [3:0] n);
      hexchar=(n<10) ? 8'd48+{4'd0,n} : 8'd55+{4'd0,n};
    endfunction
    function automatic [15:0] crc_byte(input [15:0] initial_crc,input [7:0] value);
      reg [15:0] c;
      integer j;
      begin
        c=initial_crc^{value,8'd0};
        for(j=0;j<8;j=j+1) c=c[15] ? (c<<1)^16'h1021 : (c<<1);
        crc_byte=c;
      end
    endfunction
    reg [7:0] b;
    always @* begin
      character=8'd32; b=0;
      case(char_index)
        0:character="T"; 1:character="B"; 2:character="2"; 3:character=" ";
        default: if(char_index<DATA_END) begin
          b=payload[((char_index-4)>>1)*8 +: 8];
          character=hexchar(char_index[0] ? b[3:0] : b[7:4]);
        end else if(char_index==DATA_END) character=" ";
        else if(char_index==CRC_0) character=hexchar(crc[15:12]);
        else if(char_index==CRC_1) character=hexchar(crc[11:8]);
        else if(char_index==CRC_2) character=hexchar(crc[7:4]);
        else if(char_index==CRC_3) character=hexchar(crc[3:0]);
        else if(char_index==CR_POS) character=13;
        else character=10;
      endcase
    end
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(115200)) uart(
      .clk(clk_50m),.rst_n(rst_n),.data({24'd0,character}),.valid(uart_valid),
      .ready(uart_ready),.serial_out(debug_uart_tx),.byte_done());
    // The complete snapshot is written before CRC/transmit starts. Keeping
    // this buffer off the reset tree reduces thousands of reset endpoints.
    always @(posedge clk_50m) begin
      if(state==0 && timer==0) begin
        payload<={scan,raw2,raw1,1'b0,address2,1'b0,address1,4'd0,raw_index2,4'd0,raw_index1,status2,status1,
              2'b00,raw_valid,sleeping,configured,
              error3,error2,4'b0000,error1,6'b000000,online,
              7'd0,change_sync,io_sync,frame_sequence};
      end
    end
    always @(posedge clk_50m or negedge rst_n) begin
      if(!rst_n) begin frame_sequence<=0; timer<=0; crc<=16'hffff; crc_index<=0; char_index<=0; state<=0; end
      else begin
        if(timer!=0) timer<=timer-1'b1;
        case(state)
          0: if(timer==0) begin
            frame_sequence<=frame_sequence+1'b1; crc<=16'hffff; crc_index<=0;
            timer<=CLK_HZ/FRAME_HZ-1; state<=1;
          end
          1: begin
            crc<=crc_byte(crc,payload[crc_index*8 +: 8]);
            if(crc_index==LAST_BYTE) begin char_index<=0; state<=2; end
            else crc_index<=crc_index+1'b1;
          end
          2: if(uart_ready) begin
            if(char_index==LF_POS) state<=0;
            else char_index<=char_index+1'b1;
          end
          default: state<=0;
        endcase
      end
    end
endmodule
