`timescale 1ns/1ps
`default_nettype none
// Six parameters: transpose/octave, channel, velocity, strip mode, program,
// lamp brightness. Notes retain their press-time channel and pitch.
module midi_performance (
    input wire clk, reset,
    input wire [15:0] key_bitmap,
    input wire keypad_ready,
    input wire slider_valid, slider_touch,
    input wire [7:0] slider_position,
    input wire enc1_step, enc1_press, enc2_step, enc2_press,
    input wire signed [1:0] enc1_direction, enc2_direction,
    input wire config_write,
    input wire [7:0] config_opcode,
    input wire [31:0] config_value,
    input wire [1:0] online,
    input wire [12:0] timestamp_ms,
    output reg event_valid,
    input wire event_ready,
    output reg [23:0] event_message,
    output reg [1:0] event_length,
    output reg [12:0] event_timestamp,
    output wire [1:0] event_targets,
    output reg [3:0] midi_channel,
    output reg signed [7:0] transpose,
    output reg [6:0] velocity,
    output reg [1:0] slider_mode,
    output reg [6:0] program_number,
    output reg [7:0] brightness,
    output reg [2:0] focus,
    output reg [15:0] active_keys,
    output reg [7:0] strip_value,
    output wire panic_busy,
    output reg [31:0] emitted_events
);
    reg [6:0] held_note [0:15];
    reg [3:0] held_channel [0:15];
    reg [1:0] targets, previous_online, recovering;
    reg [15:0] blocked_keys;
    reg [5:0] panic_index, recovery_index;
    reg panic_pending, replay;
    reg recovery_link;
    reg [4:0] replay_index;
    reg program_dirty, strip_dirty;
    reg [15:0] cleanup_channels;
    reg [1:0] cleanup_phase;
    reg [3:0] cleanup_owner;
    reg [3:0] cleanup_selected;
    // Commit metadata belongs to the output slot, not the changing UI state.
    localparam [2:0] K_OTHER=0,K_ON=1,K_OFF=2,K_PANIC=3,K_RECOVER=4,K_REPLAY=5,K_CLEAN=6;
    reg [2:0] slot_kind;
    reg [3:0] slot_key;
    reg [6:0] slot_note;
    reg [3:0] slot_channel;
    reg [15:0] desired;
    reg found;
    reg [3:0] selected;
    integer i;
    integer mapped;
    assign event_targets = targets & online;
    assign panic_busy = panic_pending || (recovering != 0) || replay;
    always @* begin
        desired = keypad_ready ? (key_bitmap & ~blocked_keys) : 16'd0;
        found = 0; selected = 0;
        // Release priority prevents CC traffic or new keys starving Note Off.
        for (i=15;i>=0;i=i-1)
            if (active_keys[i] && !desired[i]) begin found=1; selected=i; end
        if (!found)
            for (i=15;i>=0;i=i-1)
                if (desired[i] && !active_keys[i]) begin found=1; selected=i; end
        mapped = 48 + $signed({1'b0,selected}) + $signed(transpose);
        cleanup_selected=cleanup_owner;
        if(cleanup_phase==0)
            for(i=15;i>=0;i=i-1) if(cleanup_channels[i]) cleanup_selected=i;
    end
    task emit;
        input [23:0] message;
        input [1:0] length;
        input [1:0] mask;
        input [2:0] kind;
        begin
            event_valid <= 1;
            event_message <= message;
            event_length <= length;
            event_timestamp <= timestamp_ms;
            targets <= mask;
            slot_kind <= kind;
        end
    endtask
    // CC120 + CC123 + centered pitch on all 16 channels, including channels
    // that were selected before a held note or configuration change.
    function [23:0] panic_message;
        input [5:0] index;
        begin
            if (index<16) panic_message={{4'hb,index[3:0]},8'd120,8'd0};
            else if (index<32) panic_message={{4'hb,index[3:0]},8'd123,8'd0};
            else panic_message={{4'he,index[3:0]},8'd0,8'd64};
        end
    endfunction
    always @(posedge clk) begin
        if (reset) begin
            midi_channel<=0; transpose<=0; velocity<=100; slider_mode<=0;
            program_number<=0; brightness<=96; focus<=0; active_keys<=0;
            blocked_keys<=0; strip_value<=0; previous_online<=0; recovering<=0;
            panic_pending<=0; panic_index<=0; recovery_index<=0;
            replay<=0; replay_index<=0; recovery_link<=0;
            event_valid<=0; event_message<=0; event_length<=0; event_timestamp<=0;
            targets<=0; slot_kind<=K_OTHER; slot_key<=0; slot_note<=0; slot_channel<=0;
            program_dirty<=0; strip_dirty<=0; cleanup_channels<=0; cleanup_phase<=0;cleanup_owner<=0;
            emitted_events<=0;
        end else begin
            previous_online <= online;
            recovering <= (recovering | (online & ~previous_online)) & online;
            targets <= targets & online;
            blocked_keys <= blocked_keys & key_bitmap;
            if (slider_valid) begin
                if (slider_touch) begin
                    if (strip_value != slider_position) strip_dirty <= 1;
                    strip_value <= slider_position;
                end else if (slider_mode == 2 && strip_value != 128) begin
                    strip_value <= 128; strip_dirty <= 1;
                end
            end
            if (enc1_step) begin
                if (enc1_direction > 0) focus <= focus==5 ? 0 : focus+1'b1;
                else focus <= focus==0 ? 5 : focus-1'b1;
            end
            if (enc1_press) begin
                slider_mode <= slider_mode==2 ? 0 : slider_mode+1'b1;
                cleanup_channels[midi_channel] <= 1;
                strip_dirty <= 1;
            end
            if (enc2_step) begin
                case (focus)
                    0: begin
                        if (enc2_direction>0 && transpose<48) transpose<=transpose>36 ? 48 : transpose+8'sd12;
                        else if (enc2_direction<0 && transpose> -48) transpose<=transpose< -36 ? -48 : transpose-8'sd12;
                    end
                    1: begin
                        if(enc2_direction>0)midi_channel<=midi_channel+4'd1;
                        else if(enc2_direction<0)midi_channel<=midi_channel-4'd1;
                        cleanup_channels[midi_channel]<=1; strip_dirty<=1; program_dirty<=1;
                    end
                    2: if (enc2_direction>0 && velocity<127) velocity<=velocity+1'b1;
                       else if (enc2_direction<0 && velocity>1) velocity<=velocity-1'b1;
                    3: begin
                        if (enc2_direction>0) slider_mode<=slider_mode==2 ? 0 : slider_mode+1'b1;
                        else slider_mode<=slider_mode==0 ? 2 : slider_mode-1'b1;
                        cleanup_channels[midi_channel]<=1; strip_dirty<=1;
                    end
                    4: begin
                        if (enc2_direction>0 && program_number<127) program_number<=program_number+1'b1;
                        else if (enc2_direction<0 && program_number>0) program_number<=program_number-1'b1;
                        program_dirty<=1;
                    end
                    5: if (enc2_direction>0) brightness<=brightness>247 ? 255 : brightness+8'd8;
                       else brightness<=brightness<8 ? 0 : brightness-8'd8;
                endcase
            end
            // Explicit host writes win over a simultaneous local adjustment.
            if (config_write) begin
                if (config_opcode==8'h10) begin
                    midi_channel<=config_value[3:0]; cleanup_channels[midi_channel]<=1;
                    strip_dirty<=1; program_dirty<=1;
                end
                if (config_opcode==8'h11) transpose<=config_value[7:0];
            end
            if (enc2_press) begin
                panic_pending<=1; panic_index<=0;
                blocked_keys<=key_bitmap; // must lift before a panic-held key retriggers
            end
            if (event_valid && event_ready) begin
                event_valid<=0;
                emitted_events<=emitted_events+1'b1;
                case (slot_kind)
                    K_ON: begin
                        active_keys[slot_key]<=1;
                        held_note[slot_key]<=slot_note; held_channel[slot_key]<=slot_channel;
                    end
                    K_OFF: active_keys[slot_key]<=0;
                    K_PANIC: begin
                        if (panic_index==47) begin
                            panic_pending<=0; panic_index<=0; active_keys<=0;
                        end else panic_index<=panic_index+1'b1;
                    end
                    K_RECOVER: if (event_targets==0) begin
                        recovery_index<=0;
                    end else if (recovery_index==47) begin
                        recovery_index<=0; replay<=1; replay_index<=0;
                    end else recovery_index<=recovery_index+1'b1;
                    K_REPLAY: replay_index<=replay_index+1'b1;
                    K_CLEAN: if (cleanup_phase==2) begin
                        cleanup_channels[slot_channel]<=0; cleanup_phase<=0;
                    end else cleanup_phase<=cleanup_phase+1'b1;
                endcase
            end
            // A bubble after each committed event simplifies ownership of the
            // note table and guarantees stable payload throughout a stall.
            if (!event_valid) begin
                if (panic_pending) begin
                    emit(panic_message(panic_index),3,online,K_PANIC);
                end else if (replay) begin
                    if (!online[recovery_link] || replay_index==16) begin
                        replay<=0; replay_index<=0;
                        recovering[recovery_link]<=0;
                    end else if (active_keys[replay_index[3:0]] && desired[replay_index[3:0]]) begin
                        emit({{4'h9,held_channel[replay_index[3:0]]},
                              1'b0,held_note[replay_index[3:0]],1'b0,velocity},3,
                              recovery_link ? 2'b10 : 2'b01,K_REPLAY);
                    end else replay_index<=replay_index+1'b1;
                end else if (recovering != 0) begin
                    recovery_link<=!recovering[0];
                    emit(panic_message(recovery_index),3,recovering[0] ? 2'b01 : 2'b10,K_RECOVER);
                end else if (found) begin
                    slot_key<=selected;
                    if (active_keys[selected])
                        emit({{4'h8,held_channel[selected]},1'b0,held_note[selected],8'd0},3,online,K_OFF);
                    else if (mapped>=0 && mapped<=127) begin
                        slot_note<=mapped; slot_channel<=midi_channel;
                        emit({{4'h9,midi_channel},1'b0,mapped[6:0],1'b0,velocity},3,online,K_ON);
                    end
                end else if (cleanup_channels != 0) begin
                    slot_channel<=cleanup_selected;cleanup_owner<=cleanup_selected;
                    if (cleanup_phase==0) emit({4'hb,cleanup_selected,8'd1,8'd0},3,online,K_CLEAN);
                    else if (cleanup_phase==1) emit({4'hb,cleanup_selected,8'd11,8'd127},3,online,K_CLEAN);
                    else emit({4'he,cleanup_selected,8'd0,8'd64},3,online,K_CLEAN);
                end else if (program_dirty) begin
                    emit({4'hc,midi_channel,1'b0,program_number,8'd0},2,online,K_OTHER);
                    program_dirty<=0;
                end else if (strip_dirty) begin
                    if (slider_mode==2)
                        emit({4'he,midi_channel,1'b0,strip_value[0],6'd0,1'b0,strip_value[7:1]},3,online,K_OTHER);
                    else emit({4'hb,midi_channel,8'd1+(slider_mode==1 ? 8'd10 : 8'd0),1'b0,strip_value[7:1]},3,online,K_OTHER);
                    strip_dirty<=0;
                end
            end
            // An ended recovery session cannot lend its partial counter to a
            // different link. Restart from channel zero on the next link.
            if (!online[recovery_link] && (replay || recovery_index!=0)) begin
                recovery_index<=0; replay<=0;
            end
            if (enc2_press) begin
                panic_pending<=1; panic_index<=0; blocked_keys<=key_bitmap;
            end
            // New samples/configurations win over clearing a dirty flag for
            // the older value emitted on this same edge.
            if(slider_valid && ((slider_touch && strip_value!=slider_position) ||
                (!slider_touch && slider_mode==2 && strip_value!=128)))strip_dirty<=1;
            if(enc1_press || (enc2_step && (focus==1 || focus==3)) ||
                (config_write && config_opcode==8'h10))begin
                strip_dirty<=1;cleanup_channels[midi_channel]<=1;
            end
            if((enc2_step && (focus==1 || focus==4)) ||
                (config_write && config_opcode==8'h10))program_dirty<=1;
        end
    end
endmodule
`default_nettype wire
