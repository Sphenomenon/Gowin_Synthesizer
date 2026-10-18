`timescale 1ns/1ps
// Protocol model only; does not simulate real analog voltages or calibration.
module touch_power_adc(output reg adcrdy,output reg [13:0] adcvalue,
    input wire drstn,adcreqi,input wire [9:0] fscal_value,input wire [11:0] offset_value);
    reg stuck=0;
    integer conversions=0;
    initial begin adcrdy=1;adcvalue=850;end
    always @(negedge drstn) begin adcrdy=1;adcvalue=850;conversions=0;end
    always @(posedge adcreqi) if(drstn && !stuck) begin
      adcrdy=0;
      #2000;
      if(drstn) begin
        conversions=conversions+1;
        adcvalue=(conversions%2)==0 ? 820:870;
        adcrdy=1;
      end
    end
endmodule
