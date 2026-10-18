// Explicit PC SysEx: F0 7D 50 55 53 48 01 F7 enables; ...00 F7 disables.
// Existing MIDI parser ignores SysEx. No automatic Host while P1 is on a PC.
module push2_host_gate(input wire clk,rst,serial_in,output reg enabled);
    wire valid,error;wire [7:0] data;
    uart_rx #(.CLOCK_HZ(50000000),.BAUD(115200)) rx(
        .clk_i(clk),.rst_ni(!rst),.rx_i(serial_in),
        .data_o(data),.valid_o(valid),.framing_error_o(error));
    reg [3:0] pos;reg value;
    function [7:0] expected(input [3:0] p);
        case(p) 0:expected=8'hf0;1:expected=8'h7d;2:expected="P";3:expected="U";
            4:expected="S";5:expected="H";default:expected=8'hf7;endcase
    endfunction
    always @(posedge clk or posedge rst) begin
        if(rst)begin enabled<=0;pos<=0;value<=0;end
        else if(error)pos<=0;
        else if(valid)begin
            if(pos==6 && data[7:0]<=1)begin value<=data[0];pos<=7;end
            else if(pos!=6 && data[7:0]==expected(pos))begin
                if(pos==7)begin enabled<=value;pos<=0;end else pos<=pos+1'b1;
            end else pos<=data[7:0]==8'hf0 ? 1:0;
        end
    end
endmodule
