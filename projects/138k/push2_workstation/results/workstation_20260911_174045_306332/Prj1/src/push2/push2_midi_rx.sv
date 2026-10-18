// USB-MIDI 1.0 event input: first wire byte in bits [7:0].
// The USB Host must remove duplicate DATA packets and check CRC before this port.
// Voice events are preserved; Note On velocity zero is normalized to Note Off.
// SysEx/realtime are counted as ignored, available upstream as the raw event word.
module push2_midi_rx (
    input wire clk, input wire rst,
    input wire usb_valid, output wire usb_ready, input wire [31:0] usb_event,
    output reg event_valid, input wire event_ready,
    output reg [3:0] event_kind, output reg [3:0] event_channel,
    output reg [3:0] event_cable,
    output reg [6:0] event_data1, output reg [6:0] event_data2,
    output wire [13:0] event_pitch,
    output reg [31:0] events_received, output reg [31:0] packets_ignored
);
    wire [3:0] cin=usb_event[3:0];
    wire [7:0] status=usb_event[15:8];
    wire two_bytes=cin==4'hc || cin==4'hd;
    wire voice=cin>=8 && cin<=14 && cin==status[7:4] &&
               usb_event[7:4]<=1 && !usb_event[23] && (two_bytes || !usb_event[31]);
    assign usb_ready=!event_valid || event_ready;
    assign event_pitch={event_data2,event_data1};
    always @(posedge clk) begin
        if (rst) begin
            event_valid<=0; event_kind<=0; event_channel<=0; event_cable<=0;
            event_data1<=0; event_data2<=0; events_received<=0; packets_ignored<=0;
        end else begin
            if (event_valid && event_ready) event_valid<=0;
            if (usb_valid && usb_ready) begin
                if (voice) begin
                    event_valid<=1;
                    event_kind<=(cin==9 && usb_event[30:24]==0) ? 4'h8 : cin;
                    event_channel<=status[3:0]; event_cable<=usb_event[7:4];
                    event_data1<=usb_event[22:16];
                    event_data2<=two_bytes ? 7'd0 : usb_event[30:24];
                    events_received<=events_received+1'b1;
                end else packets_ignored<=packets_ignored+1'b1;
            end
        end
    end
endmodule
