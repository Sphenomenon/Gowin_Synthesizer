// Internal VCCIO4 ADC only. No PMOD pad is repurposed as an analog input.
// 100Hz requests, explicit ready-low->ready-high guard, 50ms timeout.
module tb_power_monitor #(parameter integer CLK_HZ=50000000)(
    input wire clk,rst_n,
    output reg [13:0] last,minimum,maximum,
    output reg [31:0] count,timeouts,age,duration,
    output wire [7:0] flags
);
    wire ready;
    wire [13:0] value;
    reg request;
    reg ready_meta,ready_sync;
    reg [13:0] value_meta,value_sync;
    reg [1:0] state;
    reg [31:0] timer,elapsed;
    reg seen_low;
    assign flags={5'd0,(timeouts!=0),(state!=0),(count!=0)};
    touch_power_adc adc(.adcrdy(ready),.adcvalue(value),.drstn(rst_n),.adcreqi(request),
      .fscal_value(10'd653),.offset_value(12'd0));
    always @(posedge clk or negedge rst_n) begin
      if(!rst_n) begin
        ready_meta<=0;ready_sync<=0;value_meta<=0;value_sync<=0;
        request<=0;state<=0;timer<=CLK_HZ/100-1;elapsed<=0;seen_low<=0;
        last<=0;minimum<=14'h3fff;maximum<=0;count<=0;timeouts<=0;age<=0;duration<=0;
      end else begin
        ready_meta<=ready;ready_sync<=ready_meta;value_meta<=value;value_sync<=value_meta;
        if(age!=32'hffffffff) age<=age+1'b1;
        case(state)
          0:if(timer!=0) timer<=timer-1'b1;
            else begin request<=1;state<=1;timer<=CLK_HZ/50000-1;
              // 20us covers asynchronous 1.25MHz ADC clock.
              elapsed<=0;seen_low<=!ready_sync; end
          1:begin
            elapsed<=elapsed+1'b1;
            if(!ready_sync) seen_low<=1;
            if(timer!=0) timer<=timer-1'b1;
            else begin request<=0;state<=2; end
          end
          2:begin
            elapsed<=elapsed+1'b1;
            if(!ready_sync) seen_low<=1;
            if(seen_low && ready_sync) begin
              last<=value_sync;
              if(value_sync<minimum) minimum<=value_sync;
              if(value_sync>maximum) maximum<=value_sync;
              count<=count+1'b1;age<=0;duration<=elapsed;
              state<=0;timer<=CLK_HZ/100-1;
            end else if(elapsed>=CLK_HZ/20) begin
              timeouts<=timeouts+1'b1;request<=0;state<=0;timer<=CLK_HZ/100-1;
            end
          end
          default:begin state<=0;request<=0;timer<=CLK_HZ/100-1;end
        endcase
      end
    end
endmodule
