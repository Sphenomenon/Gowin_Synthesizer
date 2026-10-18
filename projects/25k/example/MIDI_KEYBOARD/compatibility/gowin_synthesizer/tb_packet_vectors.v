`timescale 1ns/1ps
`default_nettype none
// Actual keyboard/performance and USB-MIDI codec interoperability vectors.
// Only the stimulus and independent expectations live in this compatibility
// directory; the DUTs are the production sources used by the keyboard build.
module tb_packet_vectors;
    reg clk=0;
    always #10 clk=~clk;
    reg reset=1;
    reg [15:0] keys=0;
    reg slider_valid=0, slider_touch=0;
    reg [7:0] slider_position=0;
    reg enc1_step=0, enc1_press=0, enc2_step=0, enc2_press=0;
    reg signed [1:0] enc1_direction=1, enc2_direction=1;
    reg config_write=0;
    reg [7:0] config_opcode=0;
    reg [31:0] config_value=0;
    reg [1:0] online=0;
    wire event_valid, event_ready;
    wire [23:0] event_message;
    wire [1:0] event_length, event_targets;
    wire [12:0] event_timestamp;
    wire [3:0] midi_channel;
    wire signed [7:0] transpose;
    wire [6:0] velocity, program_number;
    wire [1:0] slider_mode;
    wire [7:0] brightness, strip_value;
    wire [2:0] focus;
    wire [15:0] active_keys;
    wire panic_busy;
    wire [31:0] emitted_events;
    midi_performance performance (
        .clk(clk), .reset(reset), .key_bitmap(keys), .keypad_ready(1'b1),
        .slider_valid(slider_valid), .slider_touch(slider_touch),
        .slider_position(slider_position), .enc1_step(enc1_step),
        .enc1_press(enc1_press), .enc2_step(enc2_step), .enc2_press(enc2_press),
        .enc1_direction(enc1_direction), .enc2_direction(enc2_direction),
        .config_write(config_write), .config_opcode(config_opcode),
        .config_value(config_value), .online(online), .timestamp_ms(13'd100),
        .event_valid(event_valid), .event_ready(event_ready),
        .event_message(event_message), .event_length(event_length),
        .event_timestamp(event_timestamp), .event_targets(event_targets),
        .midi_channel(midi_channel), .transpose(transpose), .velocity(velocity),
        .slider_mode(slider_mode), .program_number(program_number),
        .brightness(brightness), .focus(focus), .active_keys(active_keys),
        .strip_value(strip_value), .panic_busy(panic_busy),
        .emitted_events(emitted_events)
    );
    reg direct_mode=0, direct_valid=0;
    reg [23:0] direct_message=0;
    reg [1:0] direct_length=0;
    wire tx_valid=direct_mode ? direct_valid : event_valid;
    wire [23:0] tx_message=direct_mode ? direct_message : event_message;
    wire [1:0] tx_length=direct_mode ? direct_length : event_length;
    wire tx_ready;
    assign event_ready=!direct_mode && tx_ready;
    wire packet_valid;
    reg packet_ready=0;
    wire [31:0] packet_data;
    wire [15:0] tx_errors, rx_errors;
    usb_midi_codec codec (
        .clk(clk), .reset(reset), .tx_valid(tx_valid), .tx_ready(tx_ready),
        .tx_message(tx_message), .tx_length(tx_length),
        .packet_tx_valid(packet_valid), .packet_tx_ready(packet_ready),
        .packet_tx_data(packet_data), .packet_rx_valid(1'b0),
        .packet_rx_ready(), .packet_rx_data(32'd0), .rx_valid(),
        .rx_ready(1'b1), .rx_message(), .rx_length(),
        .tx_errors(tx_errors), .rx_errors(rx_errors)
    );

    reg [23:0] messages[0:4095];
    reg [1:0] lengths[0:4095];
    reg [255:0] labels[0:4095];
    reg [255:0] phase="startup";
    integer written=0, read_count=0, cycle=0;
    integer outfile;
    reg [8191:0] output_path;
    reg [31:0] expected_word;
    reg [3:0] expected_cin;
    reg was_stalled=0;
    reg [31:0] stalled_word;
    always @(negedge clk) begin
        // Exercise ready/valid stability without depending on random seeds.
        cycle=cycle+1;
        packet_ready=(cycle%7 != 0) && (cycle%11 != 0);
    end
    always @(posedge clk) begin
        if (!reset) begin
            if (was_stalled && (!packet_valid || packet_data!==stalled_word))
                $fatal(1,"USB packet changed while stalled");
            was_stalled=packet_valid && !packet_ready;
            stalled_word=packet_data;
            if (tx_valid && tx_ready) begin
                if (written==4096) $fatal(1,"vector queue overflow");
                messages[written]=tx_message;
                lengths[written]=tx_length;
                labels[written]=phase;
                written=written+1;
            end
            if (packet_valid && packet_ready) begin
                if (read_count>=written) $fatal(1,"output without input");
                case (messages[read_count][23:16])
                    8'hf1,8'hf3: expected_cin=2;
                    8'hf2: expected_cin=3;
                    8'hf6: expected_cin=5;
                    8'hf8,8'hfa,8'hfb,8'hfc,8'hfe,8'hff: expected_cin=15;
                    default: expected_cin=messages[read_count][23:20];
                endcase
                expected_word={
                    lengths[read_count]==3 ? messages[read_count][7:0] : 8'd0,
                    lengths[read_count]>=2 ? messages[read_count][15:8] : 8'd0,
                    messages[read_count][23:16],4'd0,expected_cin};
                if (packet_data!==expected_word)
                    $fatal(1,"codec mismatch at %0d: %08x expected %08x",
                        read_count,packet_data,expected_word);
                // packethex is the four bytes in USB transfer order.
                $fdisplay(outfile,"%0s,%0d,%0d,%0d,%0d,%02x%02x%02x%02x,%0d",
                    labels[read_count], packet_data[15:8],packet_data[23:16],
                    packet_data[31:24], lengths[read_count],packet_data[7:0],
                    packet_data[15:8],packet_data[23:16],packet_data[31:24],
                    messages[read_count][7:0]);
                read_count=read_count+1;
            end
        end
    end

    task settle;
        input integer cycles;
        begin repeat(cycles) @(negedge clk); end
    endtask
    task check_message;
        input integer index;
        input integer status, a, b, length;
        reg [23:0] wanted;
        begin
            wanted={status[7:0],a[7:0],b[7:0]};
            if (written<=index || messages[index]!==wanted || lengths[index]!==length[1:0])
                $fatal(1,"performance mismatch %0s #%0d got %06x/%0d expected %06x/%0d",
                    phase,index,messages[index],lengths[index],wanted,length);
        end
    endtask
    task check_count;
        input integer expected;
        begin
            if (written!=expected || read_count!=written)
                $fatal(1,"count %0s: input=%0d output=%0d expected=%0d",
                    phase,written,read_count,expected);
        end
    endtask
    task set_channel;
        input integer channel;
        begin
            @(negedge clk); config_write=1; config_opcode=8'h10; config_value=channel;
            @(negedge clk); config_write=0;
            settle(40);
        end
    endtask
    task slide;
        input integer position, touched;
        begin
            @(negedge clk); slider_valid=1; slider_touch=touched;
            slider_position=position;
            @(negedge clk); slider_valid=0;
            settle(8);
        end
    endtask
    task change_strip_mode;
        begin
            @(negedge clk); enc1_press=1;
            @(negedge clk); enc1_press=0;
            settle(40);
        end
    endtask
    task direct_send;
        input integer status,a,b,length;
        begin
            @(negedge clk);
            direct_valid=1; direct_message={status[7:0],a[7:0],b[7:0]};
            direct_length=length;
            @(posedge clk); while (!tx_ready) @(posedge clk);
            @(negedge clk); direct_valid=0;
            settle(4);
        end
    endtask

    integer ch,k,p,n,start_index,before_index,old_channel,family,av,bv;
    initial begin
        if (!$value$plusargs("output=%s",output_path))
            output_path="usb_midi_vectors_raw.csv";
        outfile=$fopen(output_path,"w");
        if (!outfile) $fatal(1,"cannot open output");
        $fdisplay(outfile,"source,status,a,b,length,packethex,requested_b");
        settle(5); reset=0;
        settle(2); online=1;
        settle(500);
        check_count(48);
        for(k=0;k<48;k=k+1)
            if(k<16) check_message(k,8'hb0+k,120,0,3);
            else if(k<32) check_message(k,8'hb0+k-16,123,0,3);
            else check_message(k,8'he0+k-32,0,64,3);

        // Every keyboard key and MIDI channel; channel writes also exercise
        // real cleanup, Program Change and strip state replay behavior.
        old_channel=0;
        for(ch=0;ch<16;ch=ch+1) begin
            phase="channel_configuration"; start_index=written;
            set_channel(ch);
            check_count(start_index+5);
            check_message(start_index,8'hb0+old_channel,1,0,3);
            check_message(start_index+1,8'hb0+old_channel,11,127,3);
            check_message(start_index+2,8'he0+old_channel,0,64,3);
            check_message(start_index+3,8'hc0+ch,0,0,2);
            check_message(start_index+4,8'hb0+ch,1,0,3);
            old_channel=ch;
            phase="keys_A_P_on"; start_index=written;
            @(negedge clk); keys=16'hffff;
            settle(100); check_count(start_index+16);
            for(k=0;k<16;k=k+1) check_message(start_index+k,8'h90+ch,48+k,100,3);
            phase="keys_A_P_off"; start_index=written;
            @(negedge clk); keys=0;
            settle(100); check_count(start_index+16);
            for(k=0;k<16;k=k+1) check_message(start_index+k,8'h80+ch,48+k,0,3);
        end
        phase="channel_configuration"; start_index=written;
        set_channel(0); check_count(start_index+5);

        phase="slider_CC1"; start_index=written;
        for(p=1;p<256;p=p+1) begin
            slide(p,1); check_message(start_index+p-1,8'hb0,1,p/2,3);
        end
        check_count(start_index+255);
        phase="slider_mode_cleanup"; start_index=written;
        change_strip_mode; check_count(start_index+4);
        check_message(start_index,8'hb0,1,0,3);
        check_message(start_index+1,8'hb0,11,127,3);
        check_message(start_index+2,8'he0,0,64,3);
        check_message(start_index+3,8'hb0,11,127,3);

        phase="slider_CC11"; start_index=written;
        for(p=254;p>=0;p=p-1) begin
            slide(p,1); check_message(start_index+254-p,8'hb0,11,p/2,3);
        end
        check_count(start_index+255);
        phase="slider_mode_cleanup"; start_index=written;
        change_strip_mode; check_count(start_index+4);
        check_message(start_index+3,8'he0,0,0,3);
        phase="slider_pitchbend"; start_index=written;
        for(p=1;p<256;p=p+1) begin
            slide(p,1); check_message(start_index+p-1,8'he0,(p%2)*64,p/2,3);
        end
        check_count(start_index+255);
        phase="slider_pitch_release"; start_index=written;
        slide(255,0); check_count(start_index+1);
        check_message(start_index,8'he0,0,64,3);

        // Navigate E1 to Program and adjust E2 across the whole UI range.
        for(k=0;k<4;k=k+1) begin
            @(negedge clk); enc1_step=1;
            @(negedge clk); enc1_step=0;
            settle(4);
        end
        if(focus!=4) $fatal(1,"encoder focus not Program");
        phase="encoder_program"; start_index=written;
        for(p=1;p<128;p=p+1) begin
            @(negedge clk); enc2_step=1;
            @(negedge clk); enc2_step=0;
            settle(8); check_message(start_index+p-1,8'hc0,p,0,2);
        end
        check_count(start_index+127);
        phase="panic"; start_index=written;
        @(negedge clk); enc2_press=1;
        @(negedge clk); enc2_press=0;
        settle(300); check_count(start_index+48);
        for(k=0;k<48;k=k+1)
            if(k<16) check_message(start_index+k,8'hb0+k,120,0,3);
            else if(k<32) check_message(start_index+k,8'hb0+k-16,123,0,3);
            else check_message(start_index+k,8'he0+k-32,0,64,3);

        // Encoder is the codec here: all seven channel voice families, all
        // sixteen channels and data extrema. A nonzero unused source byte for
        // Cn/Dn proves the real codec zero pads their on-wire fourth byte.
        direct_mode=1;
        phase="codec_channel_voice"; start_index=written;
        for(ch=0;ch<16;ch=ch+1)
            for(family=8;family<=14;family=family+1)
                for(av=0;av<=127;av=av+127)
                    for(bv=0;bv<=127;bv=bv+127)
                        direct_send(family*16+ch,av,
                            (family==12 || family==13) ? 85 : bv,
                            (family==12 || family==13) ? 2 : 3);
        check_count(start_index+448);
        phase="codec_system"; start_index=written;
        direct_send(8'hf1,127,85,2);
        direct_send(8'hf2,127,127,3);
        direct_send(8'hf3,127,85,2);
        direct_send(8'hf6,85,85,1);
        direct_send(8'hf8,85,85,1);
        direct_send(8'hfa,85,85,1);
        direct_send(8'hfb,85,85,1);
        direct_send(8'hfc,85,85,1);
        direct_send(8'hfe,85,85,1);
        direct_send(8'hff,85,85,1);
        settle(20); check_count(start_index+10);
        if(tx_errors || rx_errors) $fatal(1,"unexpected codec errors");
        $fclose(outfile);
        $display("PASS actual performance + USB MIDI codec: %0d wire packets",read_count);
        $finish;
    end
    initial begin #2000000; $fatal(1,"watchdog timeout"); end
endmodule
`default_nettype wire
