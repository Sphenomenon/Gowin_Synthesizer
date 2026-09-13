`timescale 1ns/1ps
module tb_sine_rom;
    reg [9:0] phase_index=0;
    wire signed [31:0] sample_data;
    synth_sine_rom dut(.*);
    integer i, expected, difference;
    reg signed [31:0] values [0:1023];
    real ideal, fractional_error, largest_error;
    localparam real PI = 3.14159265358979323846;
    initial begin
        largest_error=0.0;
        for(i=0;i<1024;i=i+1) begin
            phase_index=i; #1;
            ideal=2147483647.0*$sin(2.0*PI*i/1024.0);
            expected=ideal < 0.0 ? $rtoi(ideal-0.5) : $rtoi(ideal+0.5);
            difference=$signed(sample_data)-expected;
            if(difference < -1 || difference > 1)
                $fatal(1,"sine LUT mismatch index=%0d actual=%0d expected=%0d",i,$signed(sample_data),expected);
            values[i]=sample_data;
            // Worst phase truncation lies near the far end of each phase bin.
            fractional_error=sample_data/2147483647.0-$sin(2.0*PI*(i+0.999999)/1024.0);
            if(fractional_error < 0.0) fractional_error=-fractional_error;
            if(fractional_error > largest_error) largest_error=fractional_error;
        end
        if(values[0] !== 32'sd0 || values[256] !== 32'sh7fffffff ||
           values[512] !== 32'sd0 || values[768] !== -32'sh7fffffff)
            $fatal(1,"sine quadrant endpoint mismatch");
        for(i=0;i<512;i=i+1)
            if(values[i] !== -values[i+512]) $fatal(1,"sine half-cycle asymmetry at %0d",i);
        for(i=1;i<256;i=i+1) begin
            if(values[i] !== values[512-i]) $fatal(1,"sine reflection mismatch at %0d",i);
            if(values[i] <= values[i-1]) $fatal(1,"first quadrant must be strictly increasing");
        end
        if(largest_error > 0.006136)
            $fatal(1,"phase truncation error exceeds 2*pi/1024: %f",largest_error);
        $display("PASS tb_sine_rom: all 1024 coefficients, symmetry, endpoints, maximum phase-bin error %f",largest_error);
        $finish;
    end
endmodule
