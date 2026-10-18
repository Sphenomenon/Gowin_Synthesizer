// Send one all-zero 16-pixel frame at startup, then hold DIN low.
// At 50 MHz: T0H=300ns, T0L=960ns, reset/latch low >=1ms.
module ws2812_black #(parameter integer CLK_HZ=50000000, PIXELS=16)(
 input wire clk,rst_n, input wire enable, output wire din, output wire complete
);
 localparam integer PERIOD=(CLK_HZ+799999)/800000;
 localparam integer HIGH_RAW=CLK_HZ/1000000*3/10;
 localparam integer HIGH_TICKS=HIGH_RAW<1 ? 1:HIGH_RAW;
 reg [1:0] state;
 reg [31:0] timer;
 reg [15:0] bit_count;
 assign din=enable && state==1 && timer<HIGH_TICKS;
 assign complete=!enable || state==3;
 always @(posedge clk or negedge rst_n) begin
   if(!rst_n) begin state<=0; timer<=CLK_HZ/1000-1; bit_count<=0; end
   else if(!enable) begin state<=3; timer<=0; end
   else case(state)
     0:if(timer!=0) timer<=timer-1'b1; else begin state<=1; timer<=0; end
     1:if(timer==PERIOD-1) begin
       if(bit_count==PIXELS*24-1) begin state<=2; timer<=CLK_HZ/1000-1; end
       else begin bit_count<=bit_count+1'b1; timer<=0; end
     end else timer<=timer+1'b1;
     2:if(timer!=0) timer<=timer-1'b1; else state<=3;
     default:state<=3;
   endcase
 end
endmodule
