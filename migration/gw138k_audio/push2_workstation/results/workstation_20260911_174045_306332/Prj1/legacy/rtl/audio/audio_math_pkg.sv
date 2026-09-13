package audio_math_pkg;
  function automatic logic signed [63:0] rshift(
      input logic signed [63:0] x, input integer n);
    logic increment;
    begin
      // Equivalent to abs/add/shift/restore, without two 64-bit negations.
      // Arithmetic shift rounds toward -inf; negative ties remain there.
      increment = x[n-1] && (!x[63] ||
          (($unsigned(x) & ((64'd1 << (n-1))-1)) != 0));
      rshift = (x >>> n) + $signed({63'd0,increment});
    end
  endfunction
  function automatic logic signed [31:0] sat31(input logic signed [63:0] x);
    if (x > 64'sd2147483647) sat31 = 32'sh7fffffff;
    else if (x < -64'sd2147483648) sat31 = 32'sh80000000;
    else sat31 = x[31:0];
  endfunction
  function automatic logic [15:0] slew15(input logic [15:0] now_value,
      input logic [15:0] target_value);
    logic [15:0] upper,lower;
    // Compute bounds from the current (registered) gain in parallel with the
    // target multiplier. This avoids subtracting the late-arriving target.
    upper=now_value>16'd65407 ? 16'hffff : now_value+16'd128;
    lower=now_value<16'd128 ? 16'd0 : now_value-16'd128;
    if(target_value>upper) slew15=upper;
    else if(target_value<lower) slew15=lower;
    else slew15=target_value;
  endfunction
endpackage
