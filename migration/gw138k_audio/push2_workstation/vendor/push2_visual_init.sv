// Optional visual startup: brightness followed by all 64 pad colours.
// cmd_* is a ready/valid source for push2_driver_core; reset with the USB session.
module push2_visual_init (
    input wire clk, input wire rst,
    output wire cmd_valid, input wire cmd_ready,
    output wire [1:0] cmd_kind, output wire [6:0] cmd_index,
    output reg [7:0] cmd_value, output wire [3:0] cmd_cable,
    output wire done
);
    reg [6:0] step;
    wire [6:0] pad=step-7'd2;
    assign done=step==7'd66;
    assign cmd_valid=!done && !rst;
    assign cmd_kind=step==0 ? 2'd1 : step==1 ? 2'd2 : 2'd0;
    assign cmd_index=pad+7'd36;
    assign cmd_cable=0;
    always @* begin
        case (pad[2:0])
            0:cmd_value=127; 1:cmd_value=3; 2:cmd_value=8; 3:cmd_value=126;
            4:cmd_value=15; 5:cmd_value=125; 6:cmd_value=22; default:cmd_value=25;
        endcase
        if (step==0) cmd_value=64;
        if (step==1) cmd_value=160;
    end
    always @(posedge clk) begin
        if (rst) step<=0;
        else if (cmd_valid && cmd_ready) step<=step+1'b1;
    end
endmodule
