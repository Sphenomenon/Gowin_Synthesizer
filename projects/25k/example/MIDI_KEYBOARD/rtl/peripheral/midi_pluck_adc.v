`timescale 1ns/1ps
`default_nettype none
module midi_pluck_adc #(
 parameter integer CLK_HZ=50000000,
 parameter integer SAMPLE_HZ=4000,
 parameter integer HALF_CYCLES=10,
 parameter integer CONV_CYCLES=100,
 parameter integer TIMEOUT_CYCLES=5000
)(
 input wire clk,reset,
 input wire adc_busy,adc_douta,adc_doutb,
 output reg adc_convst,adc_cs_n,adc_sclk,
 output reg sample_valid,online,
 output reg [127:0] samples,
 output reg [31:0] sample_count,
 output reg [15:0] timeouts,
 output wire busy_observed
);
 localparam integer PERIOD=CLK_HZ/SAMPLE_HZ;
 function integer width_for;
  input integer maximum;
  integer remaining;
  begin
   remaining=maximum;width_for=0;
   while(remaining>0)begin width_for=width_for+1;remaining=remaining>>1;end
   if(width_for<1)width_for=1;
  end
 endfunction
 localparam integer TIMER_MAX=TIMEOUT_CYCLES>CONV_CYCLES ?
  (TIMEOUT_CYCLES>HALF_CYCLES ? TIMEOUT_CYCLES : HALF_CYCLES) :
  (CONV_CYCLES>HALF_CYCLES ? CONV_CYCLES : HALF_CYCLES);
 localparam [2:0] IDLE=0,CONVERT=1,WAIT_HIGH=2,WAIT_LOW=3,SELECT=4,SHIFT=5,FINISH=6;
 reg [2:0] state;
 reg busy_meta,busy_sync,douta_meta,douta_sync,doutb_meta,doutb_sync;
 reg [width_for(PERIOD-1)-1:0] period_count;
 reg [width_for(TIMER_MAX-1)-1:0] timer;
 reg [5:0] bit_count;
 reg [63:0] shift_a,shift_b;
 assign busy_observed=busy_sync;
 always @(posedge clk)begin
  if(!reset && state==SHIFT && timer==HALF_CYCLES-1 && adc_sclk)begin
   shift_a<={shift_a[62:0],douta_sync};shift_b<={shift_b[62:0],doutb_sync};
  end
 end
 always @(posedge clk)begin
  if(reset)begin
   busy_meta<=0;busy_sync<=0;douta_meta<=0;douta_sync<=0;doutb_meta<=0;doutb_sync<=0;
  end else begin
   busy_meta<=adc_busy;busy_sync<=busy_meta;
   douta_meta<=adc_douta;douta_sync<=douta_meta;
   doutb_meta<=adc_doutb;doutb_sync<=doutb_meta;
  end
 end
 always @(posedge clk)begin
  if(reset)begin
   state<=IDLE;period_count<=0;timer<=0;bit_count<=0;
   adc_convst<=0;adc_cs_n<=1;adc_sclk<=1;sample_valid<=0;online<=0;
   samples<=0;sample_count<=0;timeouts<=0;
  end else begin
   sample_valid<=0;
   if(period_count==PERIOD-1)period_count<=0;
   else period_count<=period_count+1'b1;
   case(state)
    IDLE: if(period_count==0)begin
     if(busy_sync)begin
      online<=0;
      if(timeouts!=16'hffff)timeouts<=timeouts+1'b1;
     end else begin adc_convst<=1;timer<=0;state<=CONVERT;end
    end
    CONVERT: if(timer==CONV_CYCLES-1)begin
     adc_convst<=0;timer<=0;state<=busy_sync ? WAIT_LOW : WAIT_HIGH;
    end else timer<=timer+1'b1;
    WAIT_HIGH,WAIT_LOW: begin
     if(state==WAIT_HIGH && busy_sync)begin timer<=0;state<=WAIT_LOW;end
     else if(state==WAIT_LOW && !busy_sync)begin
      adc_cs_n<=0;adc_sclk<=1;timer<=0;bit_count<=0;state<=SELECT;
     end else if(timer==TIMEOUT_CYCLES-1)begin
      online<=0;state<=IDLE;timer<=0;
      if(timeouts!=16'hffff)timeouts<=timeouts+1'b1;
     end else timer<=timer+1'b1;
    end
    SELECT: if(timer==HALF_CYCLES-1)begin timer<=0;state<=SHIFT;end
            else timer<=timer+1'b1;
    SHIFT: if(timer==HALF_CYCLES-1)begin
     timer<=0;adc_sclk<=!adc_sclk;
     if(adc_sclk)begin
      if(bit_count==63)state<=FINISH;
      else bit_count<=bit_count+1'b1;
     end
    end else timer<=timer+1'b1;
    FINISH: if(timer==HALF_CYCLES-1)begin
     adc_sclk<=1;adc_cs_n<=1;state<=IDLE;timer<=0;
     samples<={shift_b[15:0],shift_b[31:16],shift_b[47:32],shift_b[63:48],
               shift_a[15:0],shift_a[31:16],shift_a[47:32],shift_a[63:48]};
     sample_valid<=1;online<=1;sample_count<=sample_count+1'b1;
    end else timer<=timer+1'b1;
    default:begin state<=IDLE;adc_convst<=0;adc_cs_n<=1;adc_sclk<=1;online<=0;end
   endcase
  end
 end
endmodule
`default_nettype wire
