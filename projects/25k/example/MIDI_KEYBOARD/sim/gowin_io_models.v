`timescale 1ns/1ps
// Functional simulation/elaboration models only. The board build uses the
// actual Gowin primitives; this file must not be added to sources.f/build.tcl.
module LUT2 #(parameter [3:0] INIT=4'h0)(
    input wire I0,input wire I1,output wire F
);
    assign F=INIT[{I1,I0}];
endmodule

// Gowin OEN is active high: 1 releases the pad, 0 drives I. O always observes
// the resolved physical pin, including any external owner or contention.
module IOBUF(input wire I,output wire O,input wire OEN,inout wire IO);
    assign IO=OEN?1'bz:I;
    assign O=IO;
endmodule

// GW5A ODDRC functional model. Keep the pair pipeline identical to the vendor
// prim_sim.v, including its half-cycle output stages. The board simulation
// holds global GSR released; CLEAR asynchronously clears every pipeline stage.
module ODDRC(Q0,Q1,D0,D1,TX,CLK,CLEAR);
    input D0,D1,TX,CLK,CLEAR;
    output Q0,Q1;
    parameter TXCLK_POL=1'b0;
    parameter INIT=1'b0;
    reg d0_reg_0,d0_reg_1,d0_reg_2;
    reg d1_reg_0,d1_reg_1,d1_reg_2;
    reg tx_reg_0,tx_reg_1,tx_reg_p,tx_reg_n;
    initial begin
        d0_reg_0=0;d0_reg_1=0;d0_reg_2=0;
        d1_reg_0=0;d1_reg_1=0;d1_reg_2=0;
        tx_reg_0=0;tx_reg_1=0;tx_reg_p=0;tx_reg_n=0;
    end
    always @(CLEAR) begin
        if(CLEAR) begin
            assign d1_reg_2=1'b0;assign d0_reg_2=1'b0;
            assign d1_reg_1=1'b0;assign d0_reg_1=1'b0;
            assign d1_reg_0=1'b0;assign d0_reg_0=1'b0;
            assign tx_reg_0=1'b0;assign tx_reg_1=1'b0;
            assign tx_reg_p=1'b0;assign tx_reg_n=1'b0;
        end else begin
            deassign d1_reg_2;deassign d0_reg_2;
            deassign d1_reg_1;deassign d0_reg_1;
            deassign d1_reg_0;deassign d0_reg_0;
            deassign tx_reg_0;deassign tx_reg_1;
            deassign tx_reg_p;deassign tx_reg_n;
        end
    end
    always @(posedge CLK) begin
        d0_reg_0<=D0;
        d1_reg_0<=D1;
        d0_reg_1<=d0_reg_0;
        d1_reg_1<=d1_reg_0;
        tx_reg_0<=TX;
        tx_reg_1<=tx_reg_0;
    end
    always @(posedge CLK) begin
        d1_reg_2<=d1_reg_1;
        tx_reg_p<=tx_reg_n;
    end
    always @(negedge CLK) begin
        d0_reg_2<=d0_reg_1;
        tx_reg_n<=tx_reg_1;
    end
    assign Q0=(CLK)?d0_reg_2:d1_reg_2;
    assign Q1=(TXCLK_POL==1'b0)?tx_reg_p:tx_reg_n;
endmodule
