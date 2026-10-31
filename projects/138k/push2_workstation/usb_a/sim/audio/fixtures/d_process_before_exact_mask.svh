// Actual W9b consumed function before the combinational arithmetic rewrite.
// Original module SHA256: 238d1274e1ad5d724632607374f08a8f03a8fe9d4df26c69613f7dbb26de2646
// Original function SHA256 (restore name d_process and original indent):
// 11247717c12f218bd37fe96d399cc6a6e1ae6b7aa6228388bd3c9a6d414742e2
  function automatic signed [31:0] d_process_old_reference(input signed [31:0] x,input [6:0] crush,drive);
    reg signed [63:0] amplified;
    reg signed [31:0] clipped;
    integer shift;
    begin
      amplified=($signed(x)*$signed({1'b0,12'(128+int'(drive)*8)}))>>>7;
      if(amplified>64'sd2147483647)clipped=32'sh7fffffff;
      else if(amplified< -64'sd2147483648)clipped=32'sh80000000;
      else clipped=amplified[31:0];
      shift=crush==0 ? 0 : 16+int'(crush)*12/127;
      d_process_old_reference=($signed(clipped)>>>shift)<<<shift;
    end
  endfunction
