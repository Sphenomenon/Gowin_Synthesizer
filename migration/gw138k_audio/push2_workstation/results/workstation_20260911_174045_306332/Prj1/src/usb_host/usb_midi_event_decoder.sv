`default_nettype none
// USB-MIDI 1.0 event packet -> existing {kind, a, b} workstation event.
// Complete 4-byte packets only. Cable/channel filtering precedes conversion;
// SysEx, pressure and real-time events are counted but never misread as notes.
// The raw 4-byte stream remains available at the host boundary for diagnostics.
module usb_midi_event_decoder #(
    parameter [3:0] CABLE = 0, CHANNEL = 0
) (
    input wire clk, reset_n, session_lost,
    input wire in_valid, in_first, in_last,
    input wire [7:0] in_data,
    output wire in_ready,
    output reg event_valid,
    output reg [17:0] event_data,
    input wire event_ready,
    output reg [31:0] accepted, filtered, unsupported, malformed
);
    reg [1:0] position;
    reg [7:0] header, status, data1;
    reg panic_pending;
    wire room = !event_valid || event_ready;
    assign in_ready = room && !panic_pending && !session_lost;
    wire [3:0] cin = header[3:0];
    wire channel_message = cin>=8 && cin<=14;
    wire selected = header[7:4]==CABLE && status[3:0]==CHANNEL;
    wire bad_channel = status[7:4]!=cin || data1[7] ||
                       ((cin!=12 && cin!=13) && in_data[7]);
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            position<=0;header<=0;status<=0;data1<=0;
            event_valid<=0;event_data<=0;panic_pending<=0;
            accepted<=0;filtered<=0;unsupported<=0;malformed<=0;
        end else begin
            if(event_valid && event_ready) event_valid<=0;
            // Serialize panic AFTER a pending accepted event. FIFO order is
            // preserved across USB re-enumeration; the audio engine keeps running.
            if(session_lost) begin panic_pending<=1;position<=0;end
            if(panic_pending && room) begin
                event_valid<=1;event_data<={4'd2,7'd123,7'd0};panic_pending<=0;
            end else if(in_valid && in_ready) begin
                if(in_first) begin
                    header<=in_data;position<=1;
                    if(position!=0 || in_last) malformed<=malformed+1'b1;
                end else if(position==1 && !in_last) begin
                    status<=in_data;position<=2;
                end else if(position==2 && !in_last) begin
                    data1<=in_data;position<=3;
                end else if(position==3 && in_last) begin
                    position<=0;
                    if(cin<2 || (channel_message && bad_channel)) malformed<=malformed+1'b1;
                    else if(header[7:4]!=CABLE || (channel_message && !selected)) filtered<=filtered+1'b1;
                    else if(cin==8 || cin==9 || cin==11 || cin==12 || cin==14) begin
                        event_valid<=1;accepted<=accepted+1'b1;
                        case(cin)
                            8:event_data<={4'd0,data1[6:0],in_data[6:0]};
                            9:event_data<={in_data[6:0]==0 ? 4'd0 : 4'd1,data1[6:0],in_data[6:0]};
                            11:event_data<={4'd2,data1[6:0],in_data[6:0]};
                            12:event_data<={4'd3,data1[6:0],7'd0};
                            14:event_data<={4'd4,data1[6:0],in_data[6:0]};
                        endcase
                    end else unsupported<=unsupported+1'b1;
                end else begin position<=0;malformed<=malformed+1'b1;end
            end
        end
    end
endmodule
`default_nettype wire
