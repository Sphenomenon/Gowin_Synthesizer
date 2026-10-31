`timescale 1ns/1ps
// A FIFO producer may only leave reset on a real producer clock edge.
// Assertion remains asynchronous, including while either clock is stopped.
module workstation_fifo_write_reset (
    input wire clk_i, reset_i,
    output wire reset_o, ready_o
);
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] release_q = 2'b00;
    always @(posedge clk_i or posedge reset_i)
        if(reset_i) release_q <= 2'b00;
        else release_q <= {release_q[0],1'b1};
    assign reset_o = !release_q[1];
    assign ready_o = release_q[1];
endmodule
