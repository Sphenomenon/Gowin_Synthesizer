// One STOP-terminated transaction. Lines are only driven low, never high.
// Separate pointer-write and read transactions are required by QT2160.
module tb_i2c_master #(
    parameter integer CLK_HZ=50000000,
    parameter integer I2C_HZ=100000,
    parameter integer FREE_US=100,
    parameter integer TIMEOUT_US=2000,
    parameter EXTERNAL_PADS=0
)(
    input wire clk, rst_n, start,
    input wire [6:0] address,
    input wire read_mode,
    input wire [6:0] length,
    input wire [511:0] tx_data,
    output reg [511:0] rx_data,
    output reg busy, done,
    output reg [3:0] error,
    inout wire scl, sda,
    input wire pad_scl, pad_sda,
    output wire drive_scl_low, drive_sda_low,
    output reg [31:0] peak_stretch
);
    localparam integer HALF=CLK_HZ/(2*I2C_HZ);
    localparam integer FREE_TICKS=CLK_HZ/1000000*FREE_US;
    localparam integer TIMEOUT=CLK_HZ/1000000*TIMEOUT_US;
    localparam [4:0] IDLE=0, FREE=1, START_A=2, START_B=3,
      TX_LOW=4, TX_HIGH=5, TX_END=6, ACK_LOW=7, ACK_HIGH=8, ACK_END=9,
      RX_LOW=10, RX_HIGH=11, RX_END=12, MACK_LOW=13, MACK_HIGH=14, MACK_END=15,
      STOP_LOW=16, STOP_HIGH=17, STOP_RELEASE=18, FINISH=19,
      REC_LOW=20, REC_HIGH=21, REC_END=22;
    reg [4:0] state;
    reg scl_low, sda_low;
    reg [31:0] timer, stretch;
    reg scl_meta, scl_sync, sda_meta, sda_sync;
    reg [31:0] free_high_ticks;
    // QT2160 erratum: count uninterrupted pad-level bus idle, not just
    // elapsed controller time. A SCL/SDA disturbance restarts this guard.
    always @(posedge clk or negedge rst_n) begin
      if(!rst_n) free_high_ticks<=0;
      else if(state==FREE && scl_sync && sda_sync) begin
        if(free_high_ticks<FREE_TICKS) free_high_ticks<=free_high_ticks+1'b1;
      end else free_high_ticks<=0;
    end
    reg [7:0] shift;
    reg [2:0] bit_index;
    reg [6:0] byte_index, count;
    reg direction, address_phase, ack_bad;
    reg [511:0] tx_latched;
    reg [3:0] recovery;
    assign scl=(!EXTERNAL_PADS && scl_low) ? 1'b0 : 1'bz;
    assign sda=(!EXTERNAL_PADS && sda_low) ? 1'b0 : 1'bz;
    assign drive_scl_low=scl_low;
    assign drive_sda_low=sda_low;
    always @(posedge clk) begin
        scl_meta<=EXTERNAL_PADS ? pad_scl : scl; scl_sync<=scl_meta;
        sda_meta<=EXTERNAL_PADS ? pad_sda : sda; sda_sync<=sda_meta;
    end
    wire high_wait=(state==TX_HIGH || state==ACK_HIGH || state==RX_HIGH ||
      state==MACK_HIGH || state==STOP_HIGH || state==REC_HIGH || state==FREE);
    // A successful read writes every byte the caller will consume. Data from
    // failed/partial transactions is never consumed; no bulk reset is needed.
    always @(posedge clk) begin
      if(state==RX_END && bit_index==0) rx_data[byte_index*8 +: 8]<=shift;
    end
    always @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
        state<=IDLE; scl_low<=0; sda_low<=0; busy<=0; done<=0; error<=0;
        timer<=0; stretch<=0; shift<=0; bit_index<=7; byte_index<=0;
        count<=0; direction<=0; address_phase<=1; ack_bad<=0;
        tx_latched<=0; recovery<=0; peak_stretch<=0;
      end else begin
        done<=0;
        if (high_wait && !scl_sync) begin
          if(stretch+1>peak_stretch) peak_stretch<=stretch+1;
          if (stretch==TIMEOUT-1) begin
            // Stuck SCL cannot produce a legal STOP. Release both and report.
            error<=3; scl_low<=0; sda_low<=0; state<=FINISH; timer<=FREE_TICKS-1;
            stretch<=0;
          end else stretch<=stretch+1'b1;
        end else begin
          stretch<=0;
          if (timer!=0) timer<=timer-1'b1;
          else case(state)
            IDLE: if(start) begin
              busy<=1; error<=0; peak_stretch<=0; count<=length; direction<=read_mode;
              tx_latched<=tx_data; shift<={address,read_mode}; address_phase<=1;
              bit_index<=7; byte_index<=0; scl_low<=0; sda_low<=0;
              timer<=FREE_TICKS-1; state<=FREE;
            end
            FREE: if(!sda_sync) begin
              recovery<=0; scl_low<=1; sda_low<=0; timer<=HALF-1; state<=REC_LOW;
            end else if(free_high_ticks>=FREE_TICKS-1) begin
              sda_low<=1; timer<=HALF-1; state<=START_A;
            end
            START_A: begin scl_low<=1; timer<=HALF-1; state<=START_B; end
            START_B: begin sda_low<=!shift[7]; timer<=HALF-1; state<=TX_LOW; end
            TX_LOW: begin scl_low<=0; timer<=HALF-1; state<=TX_HIGH; end
            TX_HIGH: begin scl_low<=1; timer<=HALF-1; state<=TX_END; end
            TX_END: if(bit_index==0) begin
              sda_low<=0; timer<=HALF-1; state<=ACK_LOW;
            end else begin
              bit_index<=bit_index-1'b1; shift<={shift[6:0],1'b0};
              sda_low<=!shift[6]; timer<=HALF-1; state<=TX_LOW;
            end
            ACK_LOW: begin scl_low<=0; timer<=HALF-1; state<=ACK_HIGH; end
            ACK_HIGH: begin ack_bad<=sda_sync; scl_low<=1; timer<=HALF-1; state<=ACK_END; end
            ACK_END: if(ack_bad || count==0) begin
              if(ack_bad) error<=address_phase ? 1 : 2;
              sda_low<=1; timer<=HALF-1; state<=STOP_LOW;
            end else if(address_phase) begin
              address_phase<=0; bit_index<=7;
              if(direction) begin sda_low<=0; shift<=0; timer<=HALF-1; state<=RX_LOW; end
              else begin shift<=tx_latched[7:0]; sda_low<=!tx_latched[7]; timer<=HALF-1; state<=TX_LOW; end
            end else if(byte_index+1>=count) begin
              sda_low<=1; timer<=HALF-1; state<=STOP_LOW;
            end else begin
              byte_index<=byte_index+1'b1; bit_index<=7;
              shift<=tx_latched[(byte_index+1)*8 +: 8];
              sda_low<=!tx_latched[(byte_index+1)*8+7]; timer<=HALF-1; state<=TX_LOW;
            end
            RX_LOW: begin scl_low<=0; timer<=HALF-1; state<=RX_HIGH; end
            RX_HIGH: begin shift<={shift[6:0],sda_sync}; scl_low<=1; timer<=HALF-1; state<=RX_END; end
            RX_END: if(bit_index==0) begin
              // ACK every received byte except the final byte, which is NACKed.
              sda_low<=(byte_index+1<count); timer<=HALF-1; state<=MACK_LOW;
            end else begin bit_index<=bit_index-1'b1; timer<=HALF-1; state<=RX_LOW; end
            MACK_LOW: begin scl_low<=0; timer<=HALF-1; state<=MACK_HIGH; end
            MACK_HIGH: begin scl_low<=1; timer<=HALF-1; state<=MACK_END; end
            MACK_END: if(byte_index+1>=count) begin
              sda_low<=1; timer<=HALF-1; state<=STOP_LOW;
            end else begin
              byte_index<=byte_index+1'b1; bit_index<=7; shift<=0; sda_low<=0;
              timer<=HALF-1; state<=RX_LOW;
            end
            STOP_LOW: begin scl_low<=0; timer<=HALF-1; state<=STOP_HIGH; end
            STOP_HIGH: begin sda_low<=0; timer<=FREE_TICKS-1; state<=STOP_RELEASE; end
            STOP_RELEASE: begin timer<=0; state<=FINISH; end
            FINISH: begin busy<=0; done<=1; state<=IDLE; end
            REC_LOW: begin scl_low<=0; timer<=HALF-1; state<=REC_HIGH; end
            REC_HIGH: begin scl_low<=1; timer<=HALF-1; state<=REC_END; end
            REC_END: if(recovery==8) begin
              error<=4; sda_low<=1; timer<=HALF-1; state<=STOP_LOW;
            end else begin recovery<=recovery+1'b1; timer<=HALF-1; state<=REC_LOW; end
            default: state<=IDLE;
          endcase
        end
      end
    end
endmodule
