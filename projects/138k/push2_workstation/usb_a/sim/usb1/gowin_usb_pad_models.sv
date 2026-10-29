module LUT2 #(parameter [3:0] INIT=4'h0)(input wire I0,I1,output wire F);
    assign F=INIT[{I1,I0}];
endmodule

module IOBUF(input wire I,output wire O,input wire OEN,inout wire IO);
    assign IO=OEN ? 1'bz : I;
    assign O=IO;
endmodule
