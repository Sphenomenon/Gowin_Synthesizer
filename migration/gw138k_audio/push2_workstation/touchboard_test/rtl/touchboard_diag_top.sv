// Temporary diagnosis: every ordered pair of the eight PMOD GPIOs, low/Z only.
// No touch configuration is written. Transactions only set register pointer 0
// and read 7 bytes at QT2160/PCA9685 addresses, preserving arbitrary pin wiring.
module touchboard_diag_top #(parameter integer CLK_HZ=50000000, FULL_SCAN=0)(
    input wire clk_50m,button1_n,
    output wire debug_uart_tx,pa_en,
    inout wire scl1,sda1,scl2,sda2,scl3,sda3,change_n,ws2812_din
);
    assign pa_en=1'b1;
    wire [7:0] pads;
    reg [7:0] lows;
    assign pads={sda1,sda2,scl1,scl2,ws2812_din,scl3,change_n,sda3};
    assign sda3=lows[0] ? 1'b0:1'bz;
    assign change_n=lows[1] ? 1'b0:1'bz;
    assign scl3=lows[2] ? 1'b0:1'bz;
    assign ws2812_din=lows[3] ? 1'b0:1'bz;
    assign scl2=lows[4] ? 1'b0:1'bz;
    assign scl1=lows[5] ? 1'b0:1'bz;
    assign sda2=lows[6] ? 1'b0:1'bz;
    assign sda1=lows[7] ? 1'b0:1'bz;
    reg [7:0] pad_meta=8'hff,pad_sync=8'hff;
    reg [19:0] boot=0;
    reg btn_meta=1,btn_sync=1;
    always @(posedge clk_50m) begin
      btn_meta<=button1_n; btn_sync<=btn_meta;
      pad_meta<=pads; pad_sync<=pad_meta;
      if(!btn_sync) boot<=0;
      else if(!(&boot)) boot<=boot+1'b1;
    end
    wire rst_n=&boot;
    reg [2:0] cl,da,gp;
    reg [6:0] ai;
    reg [7:0] state;
    reg [31:0] timer,report_seq,rise_ticks;
    reg rise_seen;
    reg start,reading;
    wire busy,done,drive_cl,drive_da;
    wire [3:0] error;
    wire [31:0] peak;
    wire [511:0] rx;
    wire nc_cl,nc_da;
    reg [7:0] idle_value,low_value,release_value;
    reg [7:0] report_kind,report_error;
    reg [55:0] report_rx;
    reg [31:0] report_peak;
    reg [7:0] gpio_drive;
    function automatic [6:0] target(input [6:0] index);
      if(FULL_SCAN) target=7'd8+index;
      else case(index)
        0:target=7'h0d; 1:target=7'h17; 2:target=7'h44;
        3:target=7'h6b; 4:target=7'h40; default:target=7'h70;
      endcase
    endfunction
    tb_i2c_master #(.CLK_HZ(CLK_HZ),.I2C_HZ(50000),.TIMEOUT_US(50000),.EXTERNAL_PADS(1)) bus(
      .clk(clk_50m),.rst_n(rst_n),.start(start),.address(target(ai)),.read_mode(reading),
      .length(reading ? 7'd7:7'd1),.tx_data(512'd0),.rx_data(rx),.busy(busy),.done(done),.error(error),
      .scl(nc_cl),.sda(nc_da),.pad_scl(pads[cl]),.pad_sda(pads[da]),
      .drive_scl_low(drive_cl),.drive_sda_low(drive_da),.peak_stretch(peak));
    always @* begin
      lows=gpio_drive;
      if(state>=10 && state<=14) begin
        if(drive_cl) lows[cl]=1;
        if(drive_da) lows[da]=1;
      end
    end
    reg send;
    wire sent;
    // State 20 waits until a report is completely sent before changing pins.
    always @(posedge clk_50m or negedge rst_n) begin
      if(!rst_n) begin
        state<=0; timer<=CLK_HZ/2-1; report_seq<=0; gp<=0; cl<=0; da<=1; ai<=0;
        start<=0; reading<=0; gpio_drive<=0; idle_value<=0; low_value<=0; release_value<=0;
        report_kind<=0; report_error<=0; report_rx<=0; report_peak<=0; send<=0; rise_ticks<=0; rise_seen<=0;
      end else begin
        start<=0; send<=0;
        if(state==2 && !rise_seen) begin
          if(pad_sync[gp]) rise_seen<=1; else rise_ticks<=rise_ticks+1'b1;
        end
        if(timer!=0) timer<=timer-1'b1;
        else case(state)
          0:begin idle_value<=pad_sync; gpio_drive<=8'b1<<gp; timer<=CLK_HZ/1000-1; state<=1; end
          1:begin low_value<=pad_sync; gpio_drive<=0; rise_ticks<=0; rise_seen<=0; timer<=CLK_HZ/1000-1; state<=2; end
          2:begin release_value<=pad_sync; report_kind<=0; report_rx<=0; report_error<=pad_sync[gp] ? 0:8; report_peak<=rise_ticks; state<=19; end
          10:begin idle_value<=pad_sync; reading<=0; start<=1; state<=11; end
          11:if(done) begin
            report_error<={4'd0,error}; report_peak<=peak; report_rx<=0; report_kind<=1;
            if(error==0) begin reading<=1; state<=12; end else state<=19;
          end
          12:if(!busy) begin start<=1; state<=13; end
          13:if(done) begin report_error<={4'd0,error}; report_peak<=peak; report_rx<=rx[55:0]; report_kind<=2; state<=19; end
          19:begin report_seq<=report_seq+1; send<=1; state<=20; end
          20:if(sent) begin
            if(report_kind==0) begin
              if(gp==7) begin gp<=0; cl<=0; da<=1; ai<=0; state<=10; end
              else begin gp<=gp+1'b1; state<=0; end
            end else if(ai<(FULL_SCAN ? 111:5)) begin ai<=ai+1'b1; state<=10; end
            else begin
              ai<=0;
              if(da<7) begin
                if(da+1'b1==cl) begin
                  if(cl==7) begin cl<=0; da<=1; gp<=0; timer<=CLK_HZ-1; state<=0; end
                  else begin da<=da+2'd2; state<=10; end
                end else begin da<=da+1'b1; state<=10; end
              end else if(cl<7) begin cl<=cl+1'b1; da<=0; state<=10; end
              else begin cl<=0; da<=1; gp<=0; timer<=CLK_HZ-1; state<=0; end
            end
          end
          default:state<=0;
        endcase
      end
    end
    // DG1: 32-byte little-endian payload with the same CRC16 as TB2.
    // 0 seq32, 4 kind, 5 SCL index (or GPIO index), 6 SDA index, 7 address,
    // 8 error, 9 idle levels, 10 low levels, 11 released levels, 12..18 rx7,
    // 20..23 maximum consecutive stretched clocks, 24 profile clock Hz.
    reg [255:0] packet;
    reg [1:0] tx_state;
    reg [6:0] ci;
    reg [5:0] bi;
    reg [15:0] crc;
    wire uart_ready;
    wire uart_valid=tx_state==2;
    assign sent=tx_state==3;
    function automatic [7:0] hexchar(input [3:0] n);
      hexchar=(n<10) ? 8'd48+{4'd0,n}:8'd55+{4'd0,n};
    endfunction
    function automatic [15:0] crc_byte(input [15:0] initial_crc,input [7:0] value);
      reg [15:0] c; integer j;
      begin c=initial_crc^{value,8'd0}; for(j=0;j<8;j=j+1) c=c[15] ? (c<<1)^16'h1021:(c<<1); crc_byte=c; end
    endfunction
    reg [7:0] character,byte_value;
    always @* begin
      character=32; byte_value=0;
      case(ci)
        0:character="D"; 1:character="G"; 2:character="1"; 3:character=" ";
        default:if(ci<68) begin byte_value=packet[((ci-4)>>1)*8 +: 8]; character=hexchar(ci[0] ? byte_value[3:0]:byte_value[7:4]); end
        else if(ci==68) character=32;
        else if(ci==69) character=hexchar(crc[15:12]);
        else if(ci==70) character=hexchar(crc[11:8]);
        else if(ci==71) character=hexchar(crc[7:4]);
        else if(ci==72) character=hexchar(crc[3:0]);
        else if(ci==73) character=13; else character=10;
      endcase
    end
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(115200)) uart(.clk(clk_50m),.rst_n(rst_n),.data({24'd0,character}),.valid(uart_valid),.ready(uart_ready),.serial_out(debug_uart_tx),.byte_done());
    always @(posedge clk_50m or negedge rst_n) begin
      if(!rst_n) begin tx_state<=0; packet<=0; crc<=16'hffff; bi<=0; ci<=0; end
      else case(tx_state)
        0:if(send) begin
          packet<={32'd0,32'd50000,report_peak,8'd0,report_rx,release_value,low_value,idle_value,report_error,
                    1'b0,target(ai),5'd0,da,5'd0,(report_kind==0 ? gp:cl),report_kind,report_seq};
          crc<=16'hffff; bi<=0; tx_state<=1;
        end
        1:begin crc<=crc_byte(crc,packet[bi*8 +: 8]); if(bi==31) begin ci<=0; tx_state<=2; end else bi<=bi+1'b1; end
        2:if(uart_ready) begin if(ci==74) tx_state<=3; else ci<=ci+1'b1; end
        3:tx_state<=0;
      endcase
    end
endmodule
