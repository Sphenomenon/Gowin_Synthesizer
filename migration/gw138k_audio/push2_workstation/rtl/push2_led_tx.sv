// Push 2 visual controls -> USB-MIDI 1.0 event packets (Bulk OUT endpoint 2).
// kind: 0=pad colour, 1=LED brightness, 2=display brightness, 3=button CC.
// kind 3 indices 127/126 select Live mode / touch-strip configuration SysEx.
// A packet remains immutable until the scheduler reports a USB ACK.
module push2_led_tx (
    input wire clk, input wire rst,
    input wire cmd_valid, output wire cmd_ready,
    input wire [1:0] cmd_kind, input wire [6:0] cmd_index,
    input wire [7:0] cmd_value, input wire [3:0] cmd_cable,
    output reg packet_valid, output reg [9:0] packet_length,
    input wire [8:0] packet_index, output wire [7:0] packet_data,
    input wire packet_acked,
    output reg [31:0] commands_acked, output reg [31:0] commands_rejected
);
    reg [127:0] bytes_q;
    assign cmd_ready = !packet_valid;
    assign packet_data = packet_index<16 ? bytes_q[packet_index[3:0]*8 +: 8] : 8'd0;
    wire legal = cmd_cable<=1 &&
                 ((cmd_kind==0 && cmd_index>=36 && cmd_index<=99 && !cmd_value[7]) ||
                  (cmd_kind==1 && !cmd_value[7]) || cmd_kind==2 || (cmd_kind==3 && !cmd_value[7]));
    always @(posedge clk) begin
        if (rst) begin
            packet_valid<=0; packet_length<=0; bytes_q<=0;
            commands_acked<=0; commands_rejected<=0;
        end else begin
            if (packet_valid && packet_acked) begin
                packet_valid<=0; commands_acked<=commands_acked+1'b1;
            end
            if (cmd_valid && cmd_ready) begin
                if (!legal) commands_rejected<=commands_rejected+1'b1;
                else begin
                    packet_valid<=1;
                    bytes_q<=0;
                    if (cmd_kind==0 || (cmd_kind==3 && cmd_index<126)) begin
                        packet_length<=4;
                        bytes_q[7:0]<={cmd_cable,cmd_kind==3?4'hb:4'h9};
                        bytes_q[15:8]<=cmd_kind==3?8'hb0:8'h90;
                        bytes_q[23:16]<={1'b0,cmd_index};
                        bytes_q[31:24]<=cmd_value;
                    end else begin
                        // F0 00 21 1D 01 01 is the documented Push 2 prefix.
                        bytes_q[7:0]<={cmd_cable,4'h4}; bytes_q[15:8]<=8'hf0;
                        bytes_q[23:16]<=8'h00; bytes_q[31:24]<=8'h21;
                        bytes_q[39:32]<={cmd_cable,4'h4}; bytes_q[47:40]<=8'h1d;
                        bytes_q[55:48]<=8'h01; bytes_q[63:56]<=8'h01;
                        if (cmd_kind==1 || cmd_kind==3) begin
                            packet_length<=12;
                            bytes_q[71:64]<={cmd_cable,4'h7}; bytes_q[79:72]<=cmd_kind==3?(cmd_index==127?8'h0a:8'h17):8'h06;
                            bytes_q[87:80]<=cmd_value; bytes_q[95:88]<=8'hf7;
                        end else begin
                            packet_length<=16;
                            bytes_q[71:64]<={cmd_cable,4'h4}; bytes_q[79:72]<=8'h08;
                            bytes_q[87:80]<={1'b0,cmd_value[6:0]};
                            bytes_q[95:88]<={7'd0,cmd_value[7]};
                            bytes_q[103:96]<={cmd_cable,4'h5}; bytes_q[111:104]<=8'hf7;
                        end
                    end
                end
            end
        end
    end
endmodule
