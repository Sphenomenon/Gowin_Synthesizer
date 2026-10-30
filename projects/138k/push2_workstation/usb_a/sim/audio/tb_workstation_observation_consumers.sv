`timescale 1ns/1ps
module tb_workstation_observation_consumers;
    reg clk=0,rst_n=0,valid=0,rate44=0,error=0,changed=0,gap=0,loss=0,switch_busy=0;
    reg [31:0] epoch=1;
    reg signed [31:0] left=0,right=0;
    reg rec_enable=0,rec_ready=0;
    wire rec_valid,rec_failed;
    wire [95:0] packet;
    wire [2:0] rec_code;
    wire [31:0] drops,fft_frame,fft_discards,fft_epoch;
    wire fft_valid,fft_rate,fft_context;
    wire [7:0] fft_bin;
    wire signed [23:0] fft_real,fft_imag;
    reg score_write=0,score_start=0,score_stop=0;
    reg [7:0] score_addr=0;
    reg [63:0] score_data=0;
    reg [8:0] score_length=256;
    wire running,done,score_failed;
    wire [31:0] leds,score_frame;
    integer bin_count=0,score_updates=0,failures=0,checks=0;
    integer switch_score_start_checks=0,switch_score_completion_checks=0;
    reg [31:0] previous_leds=0;
    always #5 clk=!clk;
    workstation_observation_consumers #(.RECORD_ADDRESS_BITS(2)) dut(
        .clk_i(clk),.rst_ni(rst_n),.frame_valid_i(valid),.frame_44k1_i(rate44),.frame_error_i(error),
        .stream_change_i(changed),.sequence_gap_i(gap),.observation_loss_i(loss),.media_switch_busy_i(switch_busy),
        .frame_epoch_i(epoch),.left_i(left),.right_i(right),.record_enable_i(rec_enable),.record_ready_i(rec_ready),
        .record_valid_o(rec_valid),.record_packet_o(packet),.record_failed_o(rec_failed),
        .record_failure_code_o(rec_code),.record_drop_o(drops),.fft_valid_o(fft_valid),.fft_bin_o(fft_bin),
        .fft_real_o(fft_real),.fft_imag_o(fft_imag),.fft_frame_o(fft_frame),.fft_discard_count_o(fft_discards),
        .fft_44k1_o(fft_rate),.fft_context_valid_o(fft_context),.fft_epoch_o(fft_epoch),
        .score_write_i(score_write),.score_address_i(score_addr),.score_data_i(score_data),
        .score_length_i(score_length),.score_start_i(score_start),.score_stop_i(score_stop),
        .score_running_o(running),.score_done_o(done),.led_mask_o(leds),.score_frame_o(score_frame),.score_failed_o(score_failed),
        .record_seal_i(1'b0),.record_seal_done_o(),.record_seal_failed_o(),.record_start_ready_o(),
        .record_object_id_o(),.record_object_rate_o(),.record_object_epoch_o(),.record_object_frames_o(),
        .record_object_status_o(),.record_object_failure_o(),.record_seal_status_o(),.record_seal_count_o(),.score_cancelled_o());
    always @(negedge clk)if(rst_n)begin
        if(fft_valid)begin
            if(!fft_context || fft_epoch!=epoch || fft_rate!=rate44 || fft_real!=0 || fft_imag!=0)
                $fatal(1,"FFT mixed context or failed zero-input transform");
            if(fft_bin!=8'(bin_count%128))$fatal(1,"FFT bin sequence");
            bin_count=bin_count+1;
        end
        if(leds!=0 && leds!=previous_leds)score_updates=score_updates+1;
        previous_leds=leds;
        if(rec_failed && rec_valid)$fatal(1,"failed recorder exposed a success packet");
    end
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task sample(input integer value);
        begin
            @(negedge clk);left=value;right=-value;valid=1;
            @(negedge clk);valid=0;clocks(3);
        end
    endtask
    task rearm;
        begin rec_enable=0;valid=0;error=0;changed=0;gap=0;loss=0;rate44=0;switch_busy=0;
            sample(0);clocks(3);rec_enable=1;clocks(3);
            if(rec_failed)$fatal(1,"recorder did not rearm after disable");end
    endtask
    task failed(input integer expected);
        begin clocks(3);if(!rec_failed || rec_code!=3'(expected) || rec_valid || drops!=32'(failures+1))
            $fatal(1,"wrong recording failure expected=%0d code=%0d drops=%0d",expected,rec_code,drops);
            failures=failures+1;checks=checks+1;end
    endtask
    reg [95:0] held;
    integer base_sequence;
    initial begin
        clocks(3);rst_n=1;clocks(3);changed=1;sample(0);changed=0;
        // Enable coincident with the first accepted frame: no release bubble.
        rec_enable=1;valid=1;left=32'sh12340000;right=-32'sh12340000;
        base_sequence=dut.recorder.sequence_number;
        clocks(1);valid=0;rec_enable=0;clocks(3);
        if(!rec_valid || packet!={32'(base_sequence),32'sh12340000,-32'sh12340000})
            $fatal(1,"stop-first firmware flow lost initial physical frame");
        held=packet;clocks(8);if(packet!==held || !rec_valid)$fatal(1,"stopped queue changed while stalled");
        rec_ready=1;clocks(1);rec_ready=0;clocks(2);if(rec_valid)$fatal(1,"stopped queue did not POP");
        checks=checks+1;
        // Overflow terminates the object, rather than silently resuming it.
        rearm();for(integer i=0;i<5;i=i+1)sample(i*65536);failed(6);
        sample(42);if(!rec_failed || rec_valid)$fatal(1,"overflow silently resumed");
        rearm();gap=1;sample(0);gap=0;failed(2);
        rearm();error=1;sample(0);error=0;failed(3);
        rearm();loss=1;clocks(1);loss=0;failed(4);
        rearm();epoch=2;changed=1;sample(0);changed=0;failed(1);
        rearm();rate44=1;epoch=3;changed=1;sample(0);changed=0;failed(1);
        // Clear failure while remaining at 44.1: a new legacy object is refused.
        rec_enable=0;clocks(3);rec_enable=1;failed(5);
        rearm();switch_busy=1;clocks(1);failed(7);switch_busy=0;
        rec_enable=0;clocks(3);
        // Saturated loss stays asserted in the wrapper. Disable/re-enable and
        // score starts must not manufacture a trustworthy session/window.
        loss=1;clocks(2);rec_enable=1;failed(4);rec_enable=0;
        score_start=1;clocks(1);score_start=0;clocks(2);
        if(running || !score_failed || fft_context || fft_valid)$fatal(1,"persistent loss admitted new consumers");
        loss=0;rec_enable=0;clocks(3);sample(0);
        // A partial FFT window is discarded; only a new complete 256-frame
        // zero window may publish 128 zero bin_count with the new context.
        for(integer i=0;i<100;i=i+1)sample(0);
        epoch=4;changed=1;sample(0);changed=0;clocks(7000);
        if(bin_count!=0)$fatal(1,"partial context window emitted bin_count");
        for(integer i=0;i<256;i=i+1)sample(0);
        clocks(7000);if(bin_count!=128 || fft_epoch!=4)$fatal(1,"complete FFT window missing bin_count=%0d",bin_count);
        // Fill every cue, execute all 256 entries on physical sample time.
        for(integer i=0;i<256;i=i+1)begin
            score_addr=8'(i);score_data={32'(i+2),32'(i+1)};score_write=1;clocks(1);
        end
        score_write=0;score_start=1;clocks(1);score_start=0;clocks(4);
        for(integer i=0;i<260;i=i+1)sample(0);
        clocks(8);if(running || leds!=256 || score_updates!=256 || score_failed)
            $fatal(1,"256-cue playback truncated updates=%0d leds=%0d",score_updates,leds);
        score_start=1;clocks(1);score_start=0;clocks(4);gap=1;sample(0);gap=0;clocks(3);
        if(running || !score_failed || done || leds!=0)$fatal(1,"broken timebase did not fail score");
        checks=checks+1;
        // A switch blocks a same-edge score launch, and also wins over the
        // exact edge that would otherwise publish the final cue and success.
        score_length=1;score_addr=0;score_data={32'd0,32'ha5};score_write=1;clocks(1);score_write=0;clocks(2);
        switch_busy=1;score_start=1;clocks(1);score_start=0;clocks(2);
        if(running || !score_failed || done)$fatal(1,"switch/start boundary admitted score");
        switch_score_start_checks=switch_score_start_checks+1;
        switch_busy=0;score_start=1;clocks(1);score_start=0;
        wait(dut.score.state==3);@(negedge clk);
        if(!running || dut.score.cue[63:32]>score_frame)$fatal(1,"final score cue boundary was not armed");
        switch_busy=1;clocks(1);
        if(running || !score_failed || done || leds!=0)$fatal(1,"switch/final cue boundary published success");
        switch_score_completion_checks=switch_score_completion_checks+1;
        switch_busy=0;score_start=1;clocks(1);score_start=0;clocks(8);
        if(running || score_failed || leds!=32'ha5)$fatal(1,"score did not recover after switch release");
        checks=checks+3;
        $display("PASS observation_consumers: checks=%0d failures=%0d fft_bins=%0d fft_discards=%0d cues=%0d switch_score_start_checks=%0d switch_score_completion_checks=%0d",checks,failures,bin_count,fft_discards,score_updates,switch_score_start_checks,switch_score_completion_checks);
        $finish;
    end
    initial begin #1000000;$fatal(1,"consumer watchdog");end
endmodule
