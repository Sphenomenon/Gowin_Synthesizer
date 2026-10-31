`timescale 1ns/1ps
module tb_workstation_media_policy_score;
    reg clk=0,reset_n=0,valid=0,write=0,start=0,stop=0;
    always #6.510416667 clk=~clk;
    reg [63:0] cue={32'd0,32'ha5};
    wire running,done,failed,cancelled;wire [31:0] leds,frame;
    integer checks=0,done_pulses=0;
    workstation_observation_consumers #(.ENABLE_MEDIA_POLICY(1),.RECORD_ADDRESS_BITS(2)) dut(
        .clk_i(clk),.rst_ni(reset_n),.frame_valid_i(valid),.frame_44k1_i(1'b0),.frame_error_i(1'b0),
        .stream_change_i(1'b0),.sequence_gap_i(1'b0),.observation_loss_i(1'b0),.media_switch_busy_i(1'b0),
        .frame_epoch_i(32'd7),.left_i(32'sd0),.right_i(32'sd0),.record_enable_i(1'b0),.record_ready_i(1'b0),
        .record_valid_o(),.record_packet_o(),.record_failed_o(),.record_failure_code_o(),.record_drop_o(),
        .fft_valid_o(),.fft_bin_o(),.fft_real_o(),.fft_imag_o(),.fft_frame_o(),.fft_44k1_o(),.fft_context_valid_o(),
        .fft_epoch_o(),.fft_discard_count_o(),.score_write_i(write),.score_address_i(8'd0),.score_data_i(cue),
        .score_length_i(9'd1),.score_start_i(start),.score_stop_i(stop),.score_running_o(running),.score_done_o(done),
        .led_mask_o(leds),.score_frame_o(frame),.score_failed_o(failed),.record_seal_i(1'b0),.record_seal_done_o(),
        .record_seal_failed_o(),.record_start_ready_o(),.record_object_id_o(),.record_object_rate_o(),.record_object_epoch_o(),
        .record_object_frames_o(),.record_object_status_o(),.record_object_failure_o(),.record_seal_status_o(),
        .record_seal_count_o(),.score_cancelled_o(cancelled));
    always @(posedge clk)if(reset_n && done)done_pulses=done_pulses+1;
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task upload(input integer when0);begin
        cue={32'(when0),32'ha5};write=1;clocks(1);write=0;clocks(3);
    end endtask
    task cancelled_result;begin
        clocks(2);
        if(running || done || failed || !cancelled || leds!=0)
            $fatal(1,"planned score stop lost explicit cancellation or published success");
        checks=checks+1;
    end endtask
    initial begin
        clocks(3);reset_n=1;clocks(4);valid=1;clocks(1);valid=0;clocks(3);
        upload(0);
        // Stop wins on the exact same edge as a zero-time first cue launch.
        start=1;stop=1;clocks(1);start=0;cancelled_result();stop=0;
        // The final zero-time cue has reached its execution edge. A planned
        // stop still produces cancellation and never a spurious successful done.
        start=1;clocks(1);start=0;
        wait(dut.local_score.score.state==3);@(negedge clk);stop=1;clocks(1);cancelled_result();stop=0;
        // Resident cues survive cancellation and can complete after an explicit
        // restart. Neither the held-note/parameter owner nor cue RAM is reset.
        start=1;clocks(1);start=0;clocks(10);
        if(running || failed || cancelled || leds!=32'ha5 || done_pulses!=1)$fatal(1,"resident score restart failed");
        checks=checks+1;
        // A stop coincident with the registered natural-done pulse cannot
        // hide both outcomes: it is explicitly represented as cancellation.
        start=1;clocks(1);start=0;wait(done);@(negedge clk);stop=1;clocks(1);
        if(!cancelled || done || running)$fatal(1,"registered final done lost terminal state");
        stop=0;checks=checks+1;
        // Nonzero physical time also stops promptly, without awaiting a frame.
        upload(1000);start=1;clocks(1);start=0;clocks(4);stop=1;clocks(1);cancelled_result();
        $display("PASS media_policy_score: checks=%0d natural_done_pulses=%0d",checks,done_pulses);$finish;
    end
    initial begin #100000;$fatal(1,"planned score watchdog");end
endmodule
