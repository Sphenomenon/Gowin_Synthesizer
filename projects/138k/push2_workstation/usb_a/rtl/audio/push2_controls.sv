// Push-specific mapping into the existing workstation {kind,a,b} events.
// Rendering and LED readiness never enter this path.
module push2_controls #(parameter integer INITIAL_VOLUME=100)(
    input wire clk,rst,connected,
    input wire valid,output wire ready,input wire [3:0] kind,cable,channel,
    input wire [6:0] a,b,
    input wire [31:0] actual_control,actual_options,
    input wire [9:0] actual_panic_epoch,
    input wire guide_enabled_i,
    input wire guide_mode_i,
    output reg guide_toggle_o,
    output reg guide_prev_o,guide_next_o,guide_select_o,
    output reg event_valid,input wire event_ready,output reg [17:0] event_data,
    output reg [63:0] held,output reg [6:0] last_note,last_velocity,
    output reg [31:0] mapped,ignored
);
    reg was_connected,panic_pending;
    reg [9:0] panic_epoch;
    reg [127:0] buttons;
    reg [2:0] effects;
    reg [6:0] volume,vibrato,glide;
    reg [6:0] scope_scale,scope_rotation,scope_morph,scope_destination,scope_speed;
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
            guide_toggle_o<=0;guide_prev_o<=0;guide_next_o<=0;guide_select_o<=0;
            was_connected<=0;panic_pending<=0;panic_epoch<=0;last_note<=0;last_velocity<=0;
            mapped<=0;ignored<=0;effects<=0;volume<=7'(INITIAL_VOLUME);vibrato<=0;glide<=0;quiet<=0;
            scope_scale<=127;scope_rotation<=0;scope_morph<=0;scope_destination<=0;scope_speed<=64;
        end else begin
            guide_toggle_o<=0;
            guide_prev_o<=0;guide_next_o<=0;guide_select_o<=0;
            was_connected<=connected;
            if(event_valid && event_ready) event_valid<=0;
            if(quiet!=17'd100000) quiet<=quiet+1'b1;
            else begin
                effects<=actual_control[2:0];
                volume<=actual_control[31]?127:actual_control[30:24];
                vibrato<=actual_options[10:4];glide<=actual_options[17:11];
            end
            if(actual_panic_epoch!=panic_epoch) begin
                // Drop a not-yet-forwarded local event from before PANIC and
                // align every Push-local latch with the accepted audio state.
                panic_epoch<=actual_panic_epoch;event_valid<=0;panic_pending<=0;
                held<=0;buttons<=0;last_note<=0;last_velocity<=0;
            end else if(was_connected && !connected) begin
                panic_pending<=1;held<=0;buttons<=0;last_note<=0;last_velocity<=0;
            end else if(panic_pending && room) begin
                event_valid<=1;event_data<={4'd2,7'd120,7'd0};panic_pending<=0;mapped<=mapped+1'b1;
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
                    end else if(a>=74 && a<=78) begin
                        event_valid<=1;mapped<=mapped+1'b1;
                        case(a)
                          74:begin scope_scale<=adjust(scope_scale,b);event_data<={4'd2,7'd93,adjust(scope_scale,b)};end
                          75:begin scope_rotation<=scope_rotation+b;event_data<={4'd2,7'd94,7'(scope_rotation+b)};end
                          76:begin scope_morph<=adjust(scope_morph,b);event_data<={4'd2,7'd92,adjust(scope_morph,b)};end
                          77:begin scope_destination<=(scope_destination+b)&7;event_data<={4'd2,7'd91,7'((scope_destination+b)&7)};end
                          78:begin scope_speed<=adjust(scope_speed,b)==0 ? 7'd1 : adjust(scope_speed,b);event_data<={4'd2,7'd103,adjust(scope_speed,b)==0 ? 7'd1 : adjust(scope_speed,b)};end
                        endcase
                    end else begin
                        buttons[a]<=b!=0;
                        if(b!=0 && !buttons[a]) begin
                            if(a==85 && guide_enabled_i) begin guide_toggle_o<=1;mapped<=mapped+1'b1;end
                            else if(guide_mode_i && a==44) begin guide_prev_o<=1;mapped<=mapped+1'b1;end
                            else if(guide_mode_i && a==45) begin guide_next_o<=1;mapped<=mapped+1'b1;end
                            else if(guide_mode_i && a==48) begin guide_select_o<=1;mapped<=mapped+1'b1;end
                            else if(a>=102 && a<=104) begin event_valid<=1;event_data<={4'd2,7'd80,a-7'd102};mapped<=mapped+1'b1;end
                            else if(a>=105 && a<=109) begin event_valid<=1;event_data<={4'd3,program_for(a),7'd0};mapped<=mapped+1'b1;end
                            else if(a>=20 && a<=22) begin
                                // Effect keys append to the shared chain. The
                                // audio core owns ordering and resets on press 4.
                                quiet<=0; event_valid<=1; event_data<={4'd2,7'd87,a-7'd20}; mapped<=mapped+1'b1;
                            end else if(a>=23 && a<=26) begin event_valid<=1;event_data<={4'd2,7'd82,a-7'd23};mapped<=mapped+1'b1;end
                            else if(a==51) begin
                                event_valid<=1;event_data<={4'd2,7'd104,7'd64};mapped<=mapped+1'b1;
                            end else if(a==87 || a==88) begin
                                event_valid<=1;event_data<={4'd2,7'd105,a==87 ? 7'd64 : 7'd127};mapped<=mapped+1'b1;
                            end else if(a==44 || a==45) begin
                                event_valid<=1;event_data<={4'd2,7'd108,a==44 ? 7'd0 : 7'd127};mapped<=mapped+1'b1;
                            end else if(a==48) begin
                                event_valid<=1;
                                event_data<={4'd2,7'd90,7'd64};mapped<=mapped+1'b1;
                            end else if(a==60) begin
                                event_valid<=1;
                                event_data<={4'd2,7'd95,7'd64};mapped<=mapped+1'b1;
                            end else if(a==31) begin
                                event_valid<=1;event_data<={4'd2,7'd96,7'd127};mapped<=mapped+1'b1;
                            end else if(a==28) begin
                                // Master gates the selected chain in the audio
                                // owner; selection and serial order stay intact.
                                event_valid<=1;event_data<={4'd2,7'd88,7'd0};mapped<=mapped+1'b1;
                            end else if(a==62 || a==63) begin
                                // Page arrows cycle the only active workstation
                                // view state: the existing A/B/C synthesis mode.
                                event_valid<=1;event_data<={4'd2,7'd89,6'd0,a==63};mapped<=mapped+1'b1;
                            end else if(a==85 || a==86) begin
                                // Non-note panel commands keep the same FIFO and
                                // arbitration path as every other Push event.
                                event_valid<=1;event_data<={4'd6,a-7'd85,7'd0};mapped<=mapped+1'b1;
                            end else if(a==27 || a==29) begin
                                event_valid<=1;event_data<={4'd2,7'd120,7'd0};
                                held<=0;last_note<=0;last_velocity<=0;mapped<=mapped+1'b1;
                            end
                            else ignored<=ignored+1'b1;
                        end
                    end
                end else ignored<=ignored+1'b1;
            end
        end
    end
endmodule
