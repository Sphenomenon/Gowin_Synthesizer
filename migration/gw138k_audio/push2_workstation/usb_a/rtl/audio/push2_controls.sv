// Push-specific mapping into the existing workstation {kind,a,b} events.
// Rendering and LED readiness never enter this path.
module push2_controls(
    input wire clk,rst,connected,
    input wire valid,output wire ready,input wire [3:0] kind,cable,channel,
    input wire [6:0] a,b,
    input wire [31:0] actual_control,actual_options,
    output reg event_valid,input wire event_ready,output reg [17:0] event_data,
    output reg [63:0] held,output reg [6:0] last_note,last_velocity,
    output reg [31:0] mapped,ignored
);
    reg was_connected,panic_pending;
    reg [127:0] buttons;
    reg [2:0] effects;
    reg [6:0] volume,vibrato,glide;
    reg [16:0] quiet;
    wire room=!event_valid || event_ready;
    wire [2:0] effect_bit=3'd1 << (a-7'd20);
    assign ready=room && !panic_pending;
    function [6:0] adjust(input [6:0] old_value,delta);
        reg signed [8:0] sum;
        begin
            sum=$signed({2'b00,old_value})+$signed({{2{delta[6]}},delta});
            adjust=sum<0?7'd0:sum>127?7'd127:sum[6:0];
        end
    endfunction
    function [6:0] program_for(input [6:0] button);
        case(button)
            105:program_for=73;106:program_for=40;107:program_for=56;
            108:program_for=12;default:program_for=0;
        endcase
    endfunction
    function [6:0] pad_force(input [6:0] raw);
        begin
            // Preserve a true zero, lift every non-zero pad value by 28, and
            // saturate cleanly: the requested raw 002 is reported as 030.
            pad_force=raw==0 ? 7'd0 : raw>=7'd99 ? 7'd127 : raw+7'd28;
        end
    endfunction
    always @(posedge clk or posedge rst) begin
        if(rst) begin
            event_valid<=0;event_data<=0;held<=0;buttons<=0;
            was_connected<=0;panic_pending<=0;last_note<=60;last_velocity<=0;
            mapped<=0;ignored<=0;effects<=0;volume<=100;vibrato<=0;glide<=0;quiet<=0;
        end else begin
            was_connected<=connected;
            if(was_connected && !connected) begin panic_pending<=1;held<=0;buttons<=0;end
            if(event_valid && event_ready) event_valid<=0;
            if(quiet!=17'd100000) quiet<=quiet+1'b1;
            else begin
                effects<=actual_control[2:0];
                volume<=actual_control[31]?127:actual_control[30:24];
                vibrato<=actual_options[10:4];glide<=actual_options[17:11];
            end
            if(panic_pending && room) begin
                event_valid<=1;event_data<={4'd2,7'd123,7'd0};panic_pending<=0;mapped<=mapped+1'b1;
            end else if(valid && ready) begin
                if(cable!=0 || channel!=0) ignored<=ignored+1'b1;
                else if(kind==10 && a>=36 && a<=99 && held[a-36]) begin
                    // Push poly-aftertouch (USB-MIDI CIN A) updates the
                    // already-held pad without allocating another voice.
                    event_valid<=1;event_data<={4'd5,a,pad_force(b)};mapped<=mapped+1'b1;
                    last_note<=a;last_velocity<=pad_force(b);
                end else if(kind==13 && last_note>=36 && last_note<=99 &&
                            held[last_note-36]) begin
                    // Some Push firmware/host combinations report pad
                    // pressure as channel pressure (USB-MIDI CIN D), where
                    // the note is implicit. Apply it to the most recently
                    // held pad and leave the held mask unchanged.
                    event_valid<=1;event_data<={4'd5,last_note,pad_force(a)};mapped<=mapped+1'b1;
                    last_velocity<=pad_force(a);
                end else if((kind==8 || kind==9) && a>=36 && a<=99) begin
                    if((kind==9 && !held[a-36]) || (kind==8 && held[a-36])) begin
                        event_valid<=1;event_data<={kind==9?4'd1:4'd0,a,kind==9?pad_force(b):b};mapped<=mapped+1'b1;
                        held[a-36]<=kind==9;
                        if(kind==9) begin last_note<=a;last_velocity<=pad_force(b);end
                    end
                end else if(kind==14 || (kind==8 && a==12)) begin
                    event_valid<=1;mapped<=mapped+1'b1;
                    event_data<=kind==14?{4'd4,a,b}:{4'd4,7'd0,7'd64};
                end else if(kind==11) begin
                    if(a==71 || a==79 || a==72 || a==73) begin
                        quiet<=0;event_valid<=1;mapped<=mapped+1'b1;
                        if(a==71 || a==79) begin
                            volume<=adjust(volume,b);event_data<={4'd2,7'd7,adjust(volume,b)};
                        end else if(a==72) begin
                            vibrato<=adjust(vibrato,b);event_data<={4'd2,7'd1,adjust(vibrato,b)};
                        end else begin
                            glide<=adjust(glide,b);event_data<={4'd2,7'd5,adjust(glide,b)};
                        end
                    end else begin
                        buttons[a]<=b!=0;
                        if(b!=0 && !buttons[a]) begin
                            if(a>=102 && a<=104) begin event_valid<=1;event_data<={4'd2,7'd80,a-7'd102};mapped<=mapped+1'b1;end
                            else if(a>=105 && a<=109) begin event_valid<=1;event_data<={4'd3,program_for(a),7'd0};mapped<=mapped+1'b1;end
                            else if(a>=20 && a<=22) begin
                                // Effect keys append to the shared chain. The
                                // audio core owns ordering and resets on press 4.
                                quiet<=0; event_valid<=1; event_data<={4'd2,7'd87,a-7'd20}; mapped<=mapped+1'b1;
                            end else if(a>=23 && a<=26) begin event_valid<=1;event_data<={4'd2,7'd82,a-7'd23};mapped<=mapped+1'b1;end
                            else if(a==27 || a==29) begin event_valid<=1;event_data<={4'd2,7'd123,7'd0};held<=0;mapped<=mapped+1'b1;end
                            else ignored<=ignored+1'b1;
                        end
                    end
                end else ignored<=ignored+1'b1;
            end
        end
    end
endmodule
