`timescale 1ns/1ps
module tb_midi_performance;
    reg clk=0; always #10 clk=~clk;
    reg reset=1;
    reg [15:0] key_bitmap=0;
    reg keypad_ready=1, slider_valid=0, slider_touch=0;
    reg [7:0] slider_position=0;
    reg enc1_step=0,enc1_press=0,enc2_step=0,enc2_press=0;
    reg signed [1:0] enc1_direction=1,enc2_direction=1;
    reg config_write=0;
    reg [7:0] config_opcode=0;
    reg [31:0] config_value=0;
    reg [1:0] online=0;
    reg [12:0] timestamp_ms=0;
    wire event_valid;
    reg event_ready=1;
    wire [23:0] event_message;
    wire [1:0] event_length,event_targets;
    wire [12:0] event_timestamp;
    wire [3:0] midi_channel;
    wire signed [7:0] transpose;
    wire [6:0] velocity,program_number;
    wire [1:0] slider_mode;
    wire [7:0] brightness,strip_value;
    wire [2:0] focus;
    wire [15:0] active_keys;
    wire panic_busy;
    wire [31:0] emitted_events;
    midi_performance dut(.*);
    reg [23:0] log_message[0:8191];
    reg [1:0] log_targets[0:8191];
    reg [1:0] log_length[0:8191];
    integer events=0, ons=0, offs=0;
    reg voices[0:1][0:15][0:127];
    integer link,ch,note,c,n,i,mark,old_ons,old_offs;
    reg was_stalled=0;
    reg [23:0] stalled_message;
    reg [1:0] stalled_length;
    reg [12:0] stalled_timestamp;
    always @(posedge clk) begin
        timestamp_ms <= timestamp_ms+1'b1;
        if (reset) was_stalled=0;
        else begin
            if (was_stalled && (!event_valid || event_message!==stalled_message ||
                event_length!==stalled_length || event_timestamp!==stalled_timestamp))
                $fatal(1,"Performance output changed while backpressured");
            was_stalled=event_valid && !event_ready;
            stalled_message=event_message; stalled_length=event_length; stalled_timestamp=event_timestamp;
            if (event_valid && event_ready) begin
                if (event_length!==2 && event_length!==3) $fatal(1,"Illegal MIDI length");
                if (event_message[23]!==1 || event_message[15]!==0 ||
                    (event_length==3 && event_message[7]!==0)) $fatal(1,"Invalid MIDI data byte");
                log_message[events]=event_message; log_targets[events]=event_targets;
                log_length[events]=event_length; events=events+1;
                ch=event_message[19:16]; note=event_message[14:8];
                if (event_message[23:20]==9) ons=ons+1;
                if (event_message[23:20]==8) offs=offs+1;
                for(link=0;link<2;link=link+1) if(event_targets[link]) begin
                    case(event_message[23:20])
                        9: begin
                            if(voices[link][ch][note]) $fatal(1,"Duplicate Note On link%0d ch%0d note%0d",link,ch,note);
                            voices[link][ch][note]=1;
                        end
                        8: voices[link][ch][note]=0;
                        11: if(note==120 || note==123)
                            for(n=0;n<128;n=n+1) voices[link][ch][n]=0;
                    endcase
                end
            end
        end
    end
    task tick(input integer cycles); begin repeat(cycles) @(negedge clk); end endtask
    task write_config(input [7:0] opcode,input [31:0] value);
        begin @(negedge clk);config_write=1;config_opcode=opcode;config_value=value;
            @(negedge clk);config_write=0;end
    endtask
    task turn_focus(input integer direction);
        begin @(negedge clk);enc1_direction=direction;enc1_step=1;
            @(negedge clk);enc1_step=0;end
    endtask
    task turn_value(input integer direction);
        begin @(negedge clk);enc2_direction=direction;enc2_step=1;
            @(negedge clk);enc2_step=0;end
    endtask
    task press_mode;
        begin @(negedge clk);enc1_press=1;@(negedge clk);enc1_press=0;end
    endtask
    task press_panic;
        begin @(negedge clk);enc2_press=1;@(negedge clk);enc2_press=0;end
    endtask
    task set_slider(input [7:0] position,input touched);
        begin @(negedge clk);slider_position=position;slider_touch=touched;slider_valid=1;
            @(negedge clk);slider_valid=0;end
    endtask
    task drain;
        integer quiet,limit;
        begin : draining
            quiet=0;
            for(limit=0;limit<3000;limit=limit+1) begin
                @(negedge clk);
                if(!event_valid && !panic_busy) quiet=quiet+1; else quiet=0;
                if(quiet==12) disable draining;
            end
            $fatal(1,"Performance never drained: active=%h valid=%b panic=%b",active_keys,event_valid,panic_busy);
        end
    endtask
    task expect_message(input integer first,input [23:0] expected,input [1:0] targets);
        integer j;reg found;
        begin
            found=0;
            for(j=first;j<events;j=j+1) if(log_message[j]===expected && log_targets[j]===targets) found=1;
            if(!found) $fatal(1,"Missing MIDI message %06h targets%b since event%0d (now%0d)",expected,targets,first,events);
        end
    endtask
    task check_silent;
        integer a,b,d;
        begin for(a=0;a<2;a=a+1) for(b=0;b<16;b=b+1) for(d=0;d<128;d=d+1)
            if(voices[a][b][d]) $fatal(1,"Stuck voice link%0d channel%0d note%0d",a,b,d);end
    endtask
    task goto_focus(input [2:0] target);
        begin while(focus!=target) turn_focus(1); end
    endtask
    initial begin
        for(i=0;i<2;i=i+1) for(c=0;c<16;c=c+1) for(n=0;n<128;n=n+1) voices[i][c][n]=0;
        tick(5);reset=0;online=1;drain();
        if(transpose!==0 || midi_channel!==0 || velocity!==100 || focus!==0) $fatal(1,"Wrong performance defaults");
        mark=events;old_ons=ons;old_offs=offs;
        key_bitmap=16'hffff;drain();
        if(active_keys!==16'hffff || ons-old_ons!=16) $fatal(1,"Sixteen simultaneous keys lost");
        for(i=0;i<16;i=i+1) expect_message(mark,{8'h90,8'd48+i[7:0],8'd100},1);
        write_config(8'h11,12);write_config(8'h10,3);drain();
        key_bitmap=0;drain();
        if(active_keys!==0 || offs-old_offs!=16) $fatal(1,"Sixteen Note Offs lost");
        for(i=0;i<16;i=i+1) expect_message(mark,{8'h80,8'd48+i[7:0],8'd0},1);
        check_silent();
        // Stall a Note On, change both keys and mappings before consuming it.
        mark=events;event_ready=0;key_bitmap=1;wait(event_valid);tick(2);
        if(event_message!==24'h933c64) $fatal(1,"Wrong captured Note On");
        key_bitmap=2;write_config(8'h11,32'hfffffff4);write_config(8'h10,5);tick(8);
        event_ready=1;drain();
        expect_message(mark,24'h933c64,1);expect_message(mark,24'h833c00,1);expect_message(mark,24'h952564,1);
        key_bitmap=0;drain();check_silent();
        // Encoder 1 browses all six focus items in both directions.
        turn_focus(-1);if(focus!==5)$fatal(1,"Encoder 1 reverse wrap failed");
        turn_focus(1);if(focus!==0)$fatal(1,"Encoder 1 forward wrap failed");
        goto_focus(1);turn_value(-1);
        if(midi_channel!==4) $fatal(1,"Encoder 2 channel decrement produced %0d expected4",midi_channel);
        turn_value(1);if(midi_channel!==5)$fatal(1,"Encoder 2 channel increment failed");
        @(negedge clk);enc2_step=1;enc2_direction=-1;config_write=1;config_opcode=8'h10;config_value=9;
        @(negedge clk);enc2_step=0;config_write=0;
        if(midi_channel!==9)$fatal(1,"Host channel write must beat encoder");
        goto_focus(0);repeat(12)turn_value(1);if(transpose!==48)$fatal(1,"Positive transpose clamp failed");
        repeat(12)turn_value(-1);if(transpose!==-48)$fatal(1,"Negative transpose signed arithmetic failed");
        @(negedge clk);enc2_step=1;enc2_direction=1;config_write=1;config_opcode=8'h11;config_value=7;
        @(negedge clk);enc2_step=0;config_write=0;
        if(transpose!==7)$fatal(1,"Host transpose write must beat encoder");
        goto_focus(2);repeat(40)turn_value(1);if(velocity!==127)$fatal(1,"Velocity max failed");
        repeat(150)turn_value(-1);if(velocity!==1)$fatal(1,"Velocity min failed");
        goto_focus(3);turn_value(-1);if(slider_mode!==2)$fatal(1,"Slider reverse wrap failed");
        turn_value(1);if(slider_mode!==0)$fatal(1,"Slider forward wrap failed");
        goto_focus(4);repeat(140)turn_value(1);if(program_number!==127)$fatal(1,"Program max failed");
        repeat(140)turn_value(-1);if(program_number!==0)$fatal(1,"Program min failed");
        goto_focus(5);repeat(40)turn_value(1);if(brightness!==255)$fatal(1,"Brightness max failed");
        repeat(40)turn_value(-1);if(brightness!==0)$fatal(1,"Brightness min failed");
        drain();
        // MOD/EXPR hold their last value; BEND alone springs to center.
        mark=events;set_slider(0,1);set_slider(128,1);drain();expect_message(mark,24'hb90140,1);
        mark=events;set_slider(255,1);drain();expect_message(mark,24'hb9017f,1);
        mark=events;set_slider(255,0);drain();if(events!=mark)$fatal(1,"MOD release should hold value");
        press_mode();drain();if(slider_mode!==1)$fatal(1,"Encoder 1 switch must select EXPR");
        mark=events;set_slider(64,1);drain();expect_message(mark,24'hb90b20,1);
        press_mode();drain();if(slider_mode!==2)$fatal(1,"Encoder 1 switch must select BEND");
        mark=events;set_slider(0,1);drain();expect_message(mark,24'he90000,1);
        mark=events;set_slider(255,1);drain();expect_message(mark,24'he9407f,1);
        mark=events;set_slider(255,0);drain();expect_message(mark,24'he90040,1);
        if(strip_value!==128)$fatal(1,"Pitch strip release must center");
        // PANIC suppresses keys physically held at panic until they lift.
        key_bitmap=3;drain();old_ons=ons;mark=events;
        event_ready=0;press_panic();tick(6);event_ready=1;drain();
        if(active_keys!==0 || ons!=old_ons)$fatal(1,"Panic retriggered held keys");
        for(i=0;i<16;i=i+1) begin
            expect_message(mark,{4'hb,i[3:0],8'd120,8'd0},1);
            expect_message(mark,{4'hb,i[3:0],8'd123,8'd0},1);
            expect_message(mark,{4'he,i[3:0],8'd0,8'd64},1);
        end
        check_silent();tick(30);if(ons!=old_ons)$fatal(1,"Panic-held key suppression lost");
        key_bitmap=0;tick(3);key_bitmap=1;drain();if(ons!=old_ons+1)$fatal(1,"Lift/repress did not rearm");
        // Drop a link with a stalled event; reconnect cleanup must precede
        // replay of current held notes, without reviving a released old key.
        event_ready=0;key_bitmap=3;wait(event_valid);tick(2);online=0;tick(3);
        key_bitmap=4;event_ready=1;drain();
        if(active_keys!==4)$fatal(1,"Offline logical key tracking failed");
        mark=events;old_ons=ons;online=3;drain();
        if(ons-old_ons!=2)$fatal(1,"Reconnect should replay one current held key to each link");
        for(i=mark;i<events;i=i+1) begin
            if(log_message[i][23:20]==9 && log_message[i]!==24'h993901)
                $fatal(1,"Reconnect replayed stale/wrong note %06h",log_message[i]);
        end
        for(c=0;c<16;c=c+1) begin
            expect_message(mark,{4'hb,c[3:0],8'd120,8'd0},1);
            expect_message(mark,{4'hb,c[3:0],8'd123,8'd0},1);
            expect_message(mark,{4'he,c[3:0],8'd0,8'd64},1);
            expect_message(mark,{4'hb,c[3:0],8'd120,8'd0},2);
            expect_message(mark,{4'hb,c[3:0],8'd123,8'd0},2);
            expect_message(mark,{4'he,c[3:0],8'd0,8'd64},2);
        end
        key_bitmap=0;drain();check_silent();
        if(emitted_events!==events)$fatal(1,"Emitted event counter disagrees with handshakes");
        $display("PASS performance: 16 notes/offs; captured held mapping; backpressure; both encoders/all focuses; signed limits; host priority; MOD/EXPR/BEND; panic rearm; offline cleanup+replay without stale notes");
        $finish;
    end
    initial begin #2_000_000;$fatal(1,"Performance timeout events=%0d focus=%0d active=%h",events,focus,active_keys);end
endmodule
