`timescale 1ns/1ps
module tb_workstation_recognition_playback;
    reg clk=0,rn=0;
    always #5 clk=~clk;
    reg [3:0] model=0,track=0,song_track=0,count=0;
    reg mode=0,restart=0,cancel=0,song=0,playlist=0,lost=0,done=0;
    wire [8:0] enabled,reference,disabled;
    workstation_playback_service #(.MODEL_SETTLE_CYCLES(16),.RECOVERY_TIMEOUT_CYCLES(24)) active (
        .clk_i(clk),.rst_ni(rn),.model_status_i(model),.tf_mode_i(mode),.tf_restart_i(restart),
        .cancel_i(cancel),.tf_track_i(track),.song_valid_i(song),.song_track_i(song_track),
        .playlist_ready_i(playlist),.track_count_i(count),.card_lost_i(lost),.analysis_done_i(done),
        .analysis_enable_o(enabled[8]),.analysis_restart_o(enabled[7]),.analysis_hold_o(enabled[6]),
        .reader_restart_o(enabled[5]),.reader_track_o(enabled[4:1]),.score_accept_o(enabled[0]));
    recognition_playback_reference #(.MODEL_SETTLE_CYCLES(16),.RECOVERY_TIMEOUT_CYCLES(24)) original (
        .clk_i(clk),.rst_ni(rn),.model_status_i(model),.tf_mode_i(mode),.tf_restart_i(restart),
        .cancel_i(cancel),.tf_track_i(track),.song_valid_i(song),.song_track_i(song_track),
        .playlist_ready_i(playlist),.track_count_i(count),.card_lost_i(lost),.analysis_done_i(done),
        .analysis_enable_o(reference[8]),.analysis_restart_o(reference[7]),.analysis_hold_o(reference[6]),
        .reader_restart_o(reference[5]),.reader_track_o(reference[4:1]),.score_accept_o(reference[0]));
    workstation_playback_service #(.RECOGNITION_ENABLE(0),.MODEL_SETTLE_CYCLES(16),.RECOVERY_TIMEOUT_CYCLES(24)) inactive (
        .clk_i(clk),.rst_ni(rn),.model_status_i(model),.tf_mode_i(mode),.tf_restart_i(restart),
        .cancel_i(cancel),.tf_track_i(track),.song_valid_i(song),.song_track_i(song_track),
        .playlist_ready_i(playlist),.track_count_i(count),.card_lost_i(lost),.analysis_done_i(done),
        .analysis_enable_o(disabled[8]),.analysis_restart_o(disabled[7]),.analysis_hold_o(disabled[6]),
        .reader_restart_o(disabled[5]),.reader_track_o(disabled[4:1]),.score_accept_o(disabled[0]));
    reg [31:0] random_state=32'h20261030;
    integer checks=0,enabled_cycles=0,restarts=0;
    task check;
        begin
            @(negedge clk);#1;
            if(rn)begin
                if(enabled!==reference)$fatal(1,"default playback changed");
                if(disabled!=={3'b000,restart,track,1'b0})
                    $fatal(1,"disabled playback waited/restarted/accepted analysis");
                checks++;if(enabled[8])enabled_cycles++;if(disabled[5])restarts++;
            end
        end
    endtask
    initial begin
        repeat(3)check();rn=1;
        song=1;song_track=6;check();song=0;repeat(4)check();
        model=14;repeat(40)check();
        cancel=1;check();cancel=0;check();
        for(integer n=0;n<8192;n++)begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            model=random_state[4:0]==0 ? 0:14;mode=random_state[6];restart=random_state[10:7]==0;
            cancel=random_state[14:11]==0;song=random_state[18:15]==0;lost=random_state[22:19]==0;
            playlist=random_state[23];done=random_state[24];track=random_state[7:4];
            count=random_state[15:12];song_track=random_state[11:8];check();
        end
        rn=0;repeat(3)check();rn=1;model=0;restart=0;song=0;lost=0;repeat(8)check();
        if(checks<8200 || enabled_cycles<10 || restarts<100)$fatal(1,"playback coverage missing");
        $display("PASS recognition playback checks=%0d enabled_cycles=%0d raw_restarts=%0d",checks,enabled_cycles,restarts);
        $finish;
    end
endmodule
