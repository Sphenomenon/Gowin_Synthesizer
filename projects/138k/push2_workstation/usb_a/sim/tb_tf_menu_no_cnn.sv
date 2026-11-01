`timescale 1ns/1ps
// Real USB MMIO/mapper/filename renderer -> held command CDC -> TF owner.
// This does not model the SD card, reader PCM, LCD wire or physical DAC.
module tb_tf_menu_no_cnn;
    reg clk=0,aclk=0,fclk=0,rn=0,sel=0,wr=0;
    always #(1000.0/96)clk=~clk;
    always #(1000.0/153.6)aclk=~aclk;
    always #10 fclk=~fclk;
    reg [7:0] addr=0;reg [31:0] wd=0;
    wire [31:0] rd;wire ready,av;wire [17:0] ae;
    reg pv=0;reg [15:0] pw=0;
    wire pr,sr,launch;wire [3:0] track;
    push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.TF_MENU_ENABLE(1)) dut(
        .clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
        .feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(448'd0),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(34'd0),.service_state_valid(1'b0),
        .score_valid(1'b1),.score_ready(sr),.score_note(7'd69),.analysis_done(1'b1),
        .playlist_valid(pv),.playlist_ready(pr),.playlist_word(pw),
        .track_launch(launch),.track_index(track),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(1'b1),.audio_event(ae),.telemetry());
    // Unselected no-CNN defaults, retired TF controls and W demo stay inert.
    tf_menu_disabled_probe #(.DEFAULT_MENU(1)) default_no_cnn(.*);
    tf_menu_disabled_probe #(.MEDIA(0)) no_media(.*);
    tf_menu_disabled_probe #(.WORKER(1)) worker(.*);

    wire song_valid;wire [3:0] song_track;wire [31:0] cdc_drops;
    gw138k_stream_cdc #(.WIDTH(4)) u_song_command_cdc(
        .reset_n(rn),.source_clk(clk),.destination_clk(fclk),
        .source_valid(launch),.source_data(track),.drop_count(cdc_drops),
        .destination_valid(song_valid),.destination_data(song_track));
    reg control_valid=0;reg [31:0] control=0;
    reg card_lost=0,playlist_available=1;
    wire tf_mode,tf_run,tf_restart,cancel_analysis,tf_error,explicit_restart,file_cancel;
    wire [3:0] tf_track;
    scope_tf_transport tf_owner(.clk_i(fclk),.rst_ni(rn),
        .control_valid_i(control_valid),.control_i(control),
        .song_valid_i(song_valid),.song_track_i(song_track),
        .playlist_ready_i(playlist_available),.card_lost_i(card_lost),.track_count_i(5'd3),
        .mode_o(tf_mode),.run_o(tf_run),.track_o(tf_track),.restart_o(tf_restart),
        .cancel_analysis_o(cancel_analysis),.error_o(tf_error),
        .explicit_restart_o(explicit_restart),.file_cancel_o(file_cancel));
    wire analysis_enable,analysis_restart,analysis_hold,reader_restart,score_accept;
    wire [3:0] reader_track;
    workstation_playback_service #(.RECOGNITION_ENABLE(0)) playback(
        .clk_i(fclk),.rst_ni(rn),.model_status_i(4'd14),
        .tf_mode_i(tf_mode),.tf_restart_i(tf_restart),.cancel_i(cancel_analysis),.tf_track_i(tf_track),
        .song_valid_i(song_valid),.song_track_i(song_track),
        .playlist_ready_i(playlist_available),.track_count_i(4'd3),
        .card_lost_i(card_lost),.analysis_done_i(1'b1),
        .analysis_enable_o(analysis_enable),.analysis_restart_o(analysis_restart),
        .analysis_hold_o(analysis_hold),.reader_restart_o(reader_restart),
        .reader_track_o(reader_track),.score_accept_o(score_accept));
    integer launches=0,commands=0,restarts=0,file_cancels=0,audio_events=0;
    always @(posedge clk)if(rn)begin
        if(launch)launches++;
        if(!sr || dut.guide_target_valid || dut.guide_score_count || dut.guide_cursor ||
           dut.guide_wrong_count || dut.guide_mask || dut.analysis_done_sync || dut.score_flushing)
            $fatal(1,"TF menu enabled absent CNN state");
    end
    always @(posedge fclk)if(rn)begin
        if(song_valid)commands++;
        if(reader_restart)restarts++;
        if(file_cancel)file_cancels++;
        if(analysis_enable || analysis_restart || analysis_hold || score_accept)
            $fatal(1,"no-CNN TF command manufactured analysis");
    end
    always @(posedge aclk)if(rn && av && ae[17:14]!=4'd15)begin
        if(ae!={4'd1,7'd60,7'd100} && ae!={4'd0,7'd60,7'd0})
            $fatal(1,"song control leaked into base audio events: %h",ae);
        audio_events++;
    end
    task put(input [7:0] address,input [31:0] data);
        begin
            @(negedge clk);sel=1;wr=1;addr=address;wd=data;
            do @(posedge clk);while(!ready);
            @(negedge clk);sel=0;
        end
    endtask
    task get(input [7:0] address,output [31:0] value);
        begin
            @(negedge clk);sel=1;wr=0;addr=address;
            do @(posedge clk);while(!ready);
            value=rd;@(negedge clk);sel=0;
        end
    endtask
    task push_cc(input [6:0] a,b);
        begin put(4,{1'b0,b,1'b0,a,4'd11,4'd0,4'd0,4'd11});end
    endtask
    task button(input [6:0] a);
        begin push_cc(a,127);push_cc(a,0);repeat(6)@(negedge clk);end
    endtask
    task generic_cc(input [6:0] a,b);begin put('h54,{14'd0,4'd2,a,b});end endtask
    task playlist(input [15:0] word);
        begin @(negedge clk);pv=1;pw=word;@(negedge clk);pv=0;end
    endtask
    task filename(input [7:0] base,input [95:0] name);
        begin for(integer i=0;i<12;i++)playlist({8'(base+i),name[95-i*8-:8]});end
    endtask
    task tf_control(input [15:0] epoch,input mode,run,input [3:0] index);
        begin
            @(negedge fclk);control={epoch,2'd0,run,mode,index,8'd0};control_valid=1;
            @(negedge fclk);control_valid=0;repeat(3)@(negedge fclk);
        end
    endtask
    task pixel(input integer x,y,input [15:0] expected);
        reg [31:0] value;
        begin
            put('h28,(y<<10)|x);get('h2c,value);
            if(value!={16'd0,expected})$fatal(1,"rendered pixel %0d,%0d = %h expected %h",x,y,value,expected);
        end
    endtask
    reg [31:0] value,before_gw25k;integer before_restarts;
    initial begin
        #250;rn=1;repeat(20)@(negedge clk);
        filename(0,"FIRST   .WAV");filename(12,"SECOND  .WAV");filename(24,"THIRD   .WAV");
        playlist(16'hff03);put(0,1);tf_control(1,1,1,0);
        if(!tf_run || restarts!=1)$fatal(1,"TF authority did not enter playback");
        button(85);get('h60,value);
        if(!value[8] || value[21:17]!=3 || value[9] || value[10] || value[7:0])
            $fatal(1,"no-CNN real playlist menu unavailable: %h",value);
        // First list row is FIRST.WAV: F's top row is visible through MMIO.
        pixel(32,28,16'hffff);pixel(40,28,16'hffff);
        button(45);button(48);repeat(20)@(negedge fclk);
        get('h60,value);
        if(!value[9] || value[25:22]!=1 || launches!=1 || commands!=1 ||
           reader_track!=1 || restarts!=2 || tf_error || cdc_drops)
            $fatal(1,"Push selection lost before TF reader: %h launches=%0d cmd=%0d restart=%0d track=%0d",value,launches,commands,restarts,reader_track);
        // Selected filename SECOND.WAV, not a fabricated fixed title. S top row 01111.
        pixel(96,32,16'h0841);pixel(98,32,16'hffff);
        if(dut.pixels.song_screen.header!="TF SONG         " ||
           dut.pixels.song_screen.state_text!="TRACK SELECTED  ")$fatal(1,"TF page claims CNN analysis");
        pixel(96,82,16'h0841);pixel(80,104,16'h0841);
        // Button release is required; return to list, clamp, then select track2.
        button(48);button(45);button(45);button(48);repeat(20)@(negedge fclk);
        if(reader_track!=2 || launches!=2 || restarts!=3)$fatal(1,"second TF selection/clamp failed");
        // GW25K's reserved commands cannot mutate a surviving Push TF menu.
        put(0,0);repeat(20)@(negedge clk);put(0,7);get('h60,before_gw25k);
        generic_cc(110,0);generic_cc(111,0);generic_cc(112,127);generic_cc(112,0);
        put('h54,{14'd0,4'd1,7'd60,7'd100});put('h54,{14'd0,4'd0,7'd60,7'd0});
        repeat(20)@(negedge clk);get('h60,value);
        if(value!=before_gw25k || launches!=2 || audio_events!=2)$fatal(1,"GW25K altered menu or base audio");
        // Ordinary generic host retains explicit menu CCs independently of CNN.
        put(0,0);repeat(20)@(negedge clk);put(0,3);
        generic_cc(112,127);generic_cc(112,0);generic_cc(111,0);generic_cc(112,127);generic_cc(112,127);
        repeat(20)@(negedge fclk);
        if(launches!=3 || commands!=3 || restarts!=4 || reader_track!=1)$fatal(1,"generic menu select is not one-shot");
        // Mode exit/cancel is owned by committed TF control. A menu selection
        // cannot re-enable TF, hold an audio sample, or start absent analysis.
        tf_control(2,0,0,1);before_restarts=restarts;
        generic_cc(112,0);generic_cc(112,127);generic_cc(112,0);
        generic_cc(111,127);generic_cc(112,127);repeat(20)@(negedge fclk);
        if(tf_mode || tf_run || restarts!=before_restarts || file_cancels!=1 || launches!=4)
            $fatal(1,"menu bypassed TF mode/cancel authority");
        tf_control(3,1,1,2);before_restarts=restarts;
        @(negedge fclk);playlist_available=0;card_lost=1;
        @(negedge fclk);card_lost=0;repeat(4)@(negedge fclk);
        if(tf_run)$fatal(1,"card loss left playback running");
        @(negedge fclk);playlist_available=1;repeat(4)@(negedge fclk);
        if(!tf_run || restarts!=before_restarts+1 || reader_track!=2)$fatal(1,"card recovery lost selected TF track");
        get('h68,value);if(value)$fatal(1,"TF-only menu exposed a score queue");
        $display("PASS TF-only menu: real filename pixels, Push and generic one-shot selection, 48MHz->50MHz command CDC, reader restart/track, TF cancel/card recovery, no CNN queue/target, no-media/default/worker inert, GW25K isolated, base audio live");
        $finish;
    end
    initial begin #5000000;$fatal(1,"TF menu regression timeout");end
endmodule

module tf_menu_disabled_probe #(parameter DEFAULT_MENU=0,MEDIA=1,WORKER=0)(
    input wire clk,aclk,rn,sel,wr,pv,input wire [7:0] addr,
    input wire [31:0] wd,input wire [15:0] pw
);
    wire launch;wire [3:0] track;
    generate if(DEFAULT_MENU)begin: legacy
        push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0)) owner(
            .clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
            .feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(448'd0),
            .display_meta_data(64'd0),.display_meta_valid(1'b0),.service_state_data(34'd0),.service_state_valid(1'b0),
            .score_valid(1'b1),.score_note(7'd60),.analysis_done(1'b1),.playlist_valid(pv),.playlist_word(pw),
            .track_launch(launch),.track_index(track),.select(sel),.write(wr),.address(addr),.wdata(wd),.audio_ready(1'b1));
        always @(posedge clk)if(rn && owner.guide_mode)$fatal(1,"default no-CNN menu changed");
    end else begin: explicitly_disabled
        push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.TF_MENU_ENABLE(1),.MEDIA_CONTROLS_ENABLE(MEDIA),.WORKER_DEMO(WORKER)) owner(
            .clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
            .feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(448'd0),
            .display_meta_data(64'd0),.display_meta_valid(1'b0),.service_state_data(34'd0),.service_state_valid(1'b0),
            .score_valid(1'b1),.score_note(7'd60),.analysis_done(1'b1),.playlist_valid(pv),.playlist_word(pw),
            .track_launch(launch),.track_index(track),.select(sel),.write(wr),.address(addr),.wdata(wd),.audio_ready(1'b1));
        always @(posedge clk)if(rn && owner.guide_mode)$fatal(1,"retired media/worker menu re-enabled");
    end endgenerate
    always @(posedge clk)if(rn && (launch || track))$fatal(1,"disabled TF menu launched a song");
endmodule
