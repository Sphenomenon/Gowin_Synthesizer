// Identity-gated configuration and polling for the netlist's two QT2160s.
module qt2160_probe #(
    parameter integer CLK_HZ=50000000,
    parameter integer I2C_HZ=100000,
    parameter SLIDER=0,
    parameter integer BOOT_MS=750,
    parameter integer POLL_MS=16,
    parameter integer RETRY_MS=500,
    parameter [7:0] BURST=2,
    parameter [7:0] THRESHOLD=10,
    parameter integer TIMEOUT_US=20000,
    parameter [15:0] KEY_MASK=16'hffff,
    parameter RAW_WORDS=0, AUDIT_CONFIG=0, SAFE_GPIO=0
)(
    input wire clk, rst_n, sample_taken, force_sleep,
    inout wire scl,sda,
    output reg online,configured,raw_valid,sleeping,
    output reg [3:0] last_error,
    output reg [55:0] status,
    output wire [31:0] raw,
    output reg [6:0] device_address,
    output reg [3:0] raw_index,
    // Read-only debug tap. The wire listener uses its own pad synchronizers.
    output wire trace_valid,trace_read,
    output wire [6:0] trace_length,
    output wire [7:0] trace_pointer,
    output wire [511:0] trace_rx,
    output wire [3:0] trace_error,
    output wire [4:0] trace_state,
    output wire [31:0] trace_peak
);
    localparam [4:0] WAIT_BOOT=0, ID_PTR=1, ID_READ=2, CONFIG=3,
      CHECK_PTR=4, CHECK_READ=5, CALIBRATE=6, POLL_WAIT=7,
      STATUS_PTR=8, STATUS_READ=9, RAW_PTR=10, RAW_READ=11, RETRY=12, PRE_CAL=13, SOFT_RESET=14, SLEEP_CMD=15, SLEEP_PTR=16, SLEEP_READ=17, GPIO_SET=18, GPIO_PTR=19, GPIO_READ=20;
    reg [4:0] state;
    reg [31:0] wait_count;
    reg [5:0] config_index;
    reg [4:0] raw_word;
    reg [511:0] raw_snapshot;
    reg raw_delivered;
    reg reset_done,config_audit;
    reg start,pending;
    reg read_mode;
    reg [6:0] length;
    reg [511:0] tx_data;
    wire [511:0] rx_data;
    wire busy,done;
    wire [3:0] error;
    assign trace_valid=pending && done;
    assign trace_read=read_mode;
    assign trace_length=length;
    assign trace_pointer=tx_data[7:0];
    assign trace_rx=rx_data;
    assign trace_error=error;
    assign trace_state=state;
    tb_i2c_master #(.CLK_HZ(CLK_HZ),.I2C_HZ(I2C_HZ),.TIMEOUT_US(TIMEOUT_US)) bus(
      .clk(clk),.rst_n(rst_n),.start(start),.address(device_address),.read_mode(read_mode),
      .length(length),.tx_data(tx_data),.rx_data(rx_data),.busy(busy),.done(done),
      .error(error),.scl(scl),.sda(sda),.pad_scl(1'b1),.pad_sda(1'b1),.drive_scl_low(),.drive_sda_low(),.peak_stretch(trace_peak));
    function automatic [7:0] config_value(input [7:0] addr);
      begin
        if(addr==12) config_value=1;
        else if(addr==13) config_value=1; // Four-burst averaging overran 16 ms on the real board.
        else if(addr==17) config_value=3; // Four consecutive threshold crossings (NDIL+1).
        else if(addr==15) config_value=20;
        else if(addr==16) config_value=5;
        else if(addr==18) config_value=255;
        else if(addr==19) config_value=25;
        else if(addr==20) config_value=SLIDER ? 8'h28 : 0;
        else if(addr==21) config_value=0; // full 8-bit slider position
        else if(addr>=22 && addr<=37) config_value=(SLIDER && addr<30) ? 1 : 0;
        else if(addr>=38 && addr<=53) config_value=THRESHOLD;
        else if(addr>=54 && addr<=69) config_value=(!KEY_MASK[addr-54] || (SLIDER && addr>=62)) ? 0 : BURST;
        else config_value=0;
      end
    endfunction
    integer k;
    reg config_match;
    always @* begin
      config_match=1;
      for(k=0;k<58;k=k+1)
        if(rx_data[k*8 +: 8]!=((sleeping && k==0) ? 8'd0:config_value(k[7:0]+8'd12))) config_match=0;
    end
    wire [7:0] config_addr=8'd12+{2'b00,config_index};
    function automatic [6:0] next_address(input [6:0] address);
      case(address)
        7'h0d:next_address=7'h17;
        7'h17:next_address=7'h44;
        7'h44:next_address=7'h6b;
        default:next_address=7'h0d;
      endcase
    endfunction
    // Read the contiguous 100..163 block once, then deliver all channels while
    // status polling continues independently. Never reset this bulk buffer;
    // raw_valid only becomes true after a complete successful read.
    always @(posedge clk) begin
      if(pending && done && error==0 && state==RAW_READ) begin
        if(RAW_WORDS) raw_snapshot[{raw_word,4'b0000} +: 16]<=rx_data[15:0];
        else raw_snapshot<=rx_data;
      end
    end
    assign raw=raw_valid ? {raw_snapshot[{1'b1,raw_index,4'b0000} +: 16],
                           raw_snapshot[{1'b0,raw_index,4'b0000} +: 16]} : 32'd0;
    always @(posedge clk or negedge rst_n) begin
      if(!rst_n) begin
        state<=WAIT_BOOT; wait_count<=CLK_HZ/1000*BOOT_MS-1;
        start<=0; pending<=0; read_mode<=0; length<=0; tx_data<=0;
        online<=0; configured<=0; raw_valid<=0; sleeping<=0; last_error<=0;
        status<=0; config_index<=0; raw_word<=0; raw_index<=0; raw_delivered<=0; device_address<=7'h0d; reset_done<=0; config_audit<=0;
      end else begin
        start<=0;
        if(sample_taken && raw_valid) begin
          if(raw_index==15) raw_delivered<=1;
          else raw_index<=raw_index+1'b1;
        end
        if(state==WAIT_BOOT || state==POLL_WAIT || state==RETRY || state==PRE_CAL) begin
          if(wait_count!=0) wait_count<=wait_count-1'b1;
          else if(state==POLL_WAIT) state<=force_sleep && !sleeping ? SLEEP_CMD:STATUS_PTR;
          else if(state==PRE_CAL) state<=CALIBRATE;
          else state<=ID_PTR;
        end else if(!pending && !busy) begin
          read_mode<=0; length<=1; tx_data<=0; start<=1; pending<=1;
          case(state)
            ID_PTR: tx_data[7:0]<=0;
            ID_READ: begin read_mode<=1; length<=7; end
            CONFIG: begin length<=2; tx_data[7:0]<=config_addr; tx_data[15:8]<=config_value(config_addr); end
            CHECK_PTR: tx_data[7:0]<=12;
            CHECK_READ: begin read_mode<=1; length<=58; end
            CALIBRATE: begin length<=2; tx_data[7:0]<=10; tx_data[15:8]<=1; end
            SOFT_RESET: begin length<=2; tx_data[7:0]<=11; tx_data[15:8]<=1; end
            GPIO_SET: begin length<=2; tx_data[7:0]<=73; tx_data[15:8]<=8'h1c; end
            GPIO_PTR: tx_data[7:0]<=73;
            GPIO_READ: begin read_mode<=1; length<=1; end
            SLEEP_CMD: begin length<=2; tx_data[7:0]<=12; tx_data[15:8]<=0; end
            SLEEP_PTR: tx_data[7:0]<=12;
            SLEEP_READ: begin read_mode<=1; length<=1; end
            STATUS_PTR: tx_data[7:0]<=0;
            STATUS_READ: begin read_mode<=1; length<=7; end
            RAW_PTR: tx_data[7:0]<=RAW_WORDS ? (8'd100+{2'b00,raw_word,1'b0}):8'd100;
            RAW_READ: begin read_mode<=1; length<=RAW_WORDS ? 2:64; end
            default: begin start<=0; pending<=0; state<=RETRY; wait_count<=CLK_HZ/1000*RETRY_MS-1; end
          endcase
        end else if(pending && done) begin
          pending<=0;
          if(error!=0) begin
            online<=0; configured<=0; raw_valid<=0; raw_delivered<=0; last_error<=error; reset_done<=0; sleeping<=0;
            if(state==ID_PTR && error==1) device_address<=next_address(device_address);
            state<=RETRY; wait_count<=CLK_HZ/1000*RETRY_MS-1;
          end else case(state)
            ID_PTR: state<=ID_READ;
            ID_READ: if(rx_data[7:0]==8'h11) begin
              online<=1; last_error<=0; status<=rx_data[55:0]; config_index<=0; config_audit<=0;
              state<=reset_done ? CONFIG : SOFT_RESET;
            end else begin
              online<=0; configured<=0; raw_valid<=0; last_error<=5;
              device_address<=next_address(device_address);
              state<=RETRY; wait_count<=CLK_HZ/1000*RETRY_MS-1;
            end
            CONFIG: if(config_index==57) state<=SAFE_GPIO ? GPIO_SET:CHECK_PTR;
                    else config_index<=config_index+1'b1;
            GPIO_SET: state<=GPIO_PTR;
            GPIO_PTR: state<=GPIO_READ;
            GPIO_READ: if(rx_data[7:0]==8'h1c) state<=CHECK_PTR;
              else begin online<=0; configured<=0; raw_valid<=0; reset_done<=0; last_error<=6; state<=RETRY; wait_count<=CLK_HZ/1000*RETRY_MS-1; end
            CHECK_PTR: state<=CHECK_READ;
            CHECK_READ: if(config_match) begin
                if(config_audit) begin
                  config_audit<=0;
                  if(!raw_valid || raw_delivered) begin raw_word<=0; state<=RAW_PTR; end
                  else begin state<=POLL_WAIT; wait_count<=CLK_HZ/1000*POLL_MS-1; end
                end else begin state<=PRE_CAL; wait_count<=CLK_HZ/10-1; end
              end
              else begin online<=0; configured<=0; raw_valid<=0; raw_delivered<=0; reset_done<=0; last_error<=6; state<=RETRY; wait_count<=CLK_HZ/1000*RETRY_MS-1; end
            SOFT_RESET: begin
              sleeping<=0; reset_done<=1; online<=0; configured<=0; raw_valid<=0;
              state<=WAIT_BOOT; wait_count<=CLK_HZ/1000*BOOT_MS-1;
            end
            CALIBRATE: begin configured<=1; state<=POLL_WAIT; wait_count<=CLK_HZ-1; raw_index<=0; raw_delivered<=0; end
            SLEEP_CMD: begin raw_valid<=0; raw_delivered<=0; state<=SLEEP_PTR; end
            SLEEP_PTR: state<=SLEEP_READ;
            SLEEP_READ: if(rx_data[7:0]==0) begin sleeping<=1; state<=STATUS_PTR; end
              else begin last_error<=6; configured<=0; state<=RETRY; reset_done<=0; wait_count<=CLK_HZ/1000*RETRY_MS-1; end
            STATUS_PTR: state<=STATUS_READ;
            STATUS_READ: if(rx_data[7:0]!=8'h11 || rx_data[23]) begin
              // Unexpected reset invalidates configuration; repeat ID/config.
              configured<=0; raw_valid<=0; state<=RETRY; last_error<=7; reset_done<=0;
              wait_count<=CLK_HZ/1000*RETRY_MS-1;
            end else begin
              online<=1; last_error<=0; status<=rx_data[55:0];
              if(AUDIT_CONFIG) begin config_audit<=1; state<=CHECK_PTR; end
              else if(!raw_valid || raw_delivered) begin raw_word<=0; state<=RAW_PTR; end
              else begin state<=POLL_WAIT; wait_count<=CLK_HZ/1000*POLL_MS-1; end
            end
            RAW_PTR: state<=RAW_READ;
            RAW_READ: if(RAW_WORDS && raw_word!=31) begin
              raw_word<=raw_word+1'b1; state<=RAW_PTR;
            end else begin
              raw_index<=0; raw_valid<=1; raw_delivered<=0;
              state<=POLL_WAIT; wait_count<=CLK_HZ/1000*POLL_MS-1;
            end
            default: state<=ID_PTR;
          endcase
        end
      end
    end
endmodule
