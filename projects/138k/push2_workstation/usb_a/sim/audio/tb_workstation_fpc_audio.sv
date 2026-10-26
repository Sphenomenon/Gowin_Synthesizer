`timescale 1ns/1ps

module tb_workstation_fpc_audio;
    reg clk_50m = 0, audio_clk = 0, dac_reference_clk = 0;
    reg [15:0] master_volume=32768, expected_gain=32768;
    reg check_exact=0;
    reg reset_n = 0, audio_reset_n = 0;
    reg source_running = 1, reference_running = 1, enable = 1, sample_valid = 0;
    reg [31:0] pcm = 0;
    integer source_period = 1600;
    integer source_count = 0, samples_sent = 0;
    wire mclk, bck, lrck, data_bit, pdn_n, smute, sslow, sd, slow;
    wire [31:0] drops;
    wire frame_clock,frame_valid;
    wire [31:0] frame_pcm,frame_sequence;
    reg [31:0] current_tap=0,previous_tap=0,last_sequence=0;
    reg current_mute=1,previous_mute=1;
    always #10 clk_50m = !clk_50m;
    always #6.510417 audio_clk = !audio_clk;
    always #40.690104 dac_reference_clk = reference_running ? !dac_reference_clk : 1'b0;
    workstation_fpc_audio dut (
        .clk_50m_i(clk_50m), .dac_reference_clk_i(dac_reference_clk), .audio_clk_i(audio_clk),
        .rst_ni(reset_n), .audio_rst_ni(audio_reset_n), .master_volume_i(master_volume),
        .sample_valid_i(sample_valid), .enable_i(enable), .pcm_pair_i(pcm),
        .mclk_o(mclk), .bck_o(bck), .lrck_o(lrck), .data_o(data_bit),
        .pdn_no(pdn_n), .smute_o(smute), .sslow_o(sslow), .sd_o(sd), .slow_o(slow),
        .frame_clock_o(frame_clock),.frame_valid_o(frame_valid),.frame_pcm_o(frame_pcm),.frame_sequence_o(frame_sequence),
        .mailbox_drop_count_o(drops)
    );
    always @(posedge frame_clock) begin
        #1;
        if(!pdn_n) begin
            current_tap=0;previous_tap=0;last_sequence=frame_sequence;
            current_mute=1;previous_mute=1;
        end else if(frame_valid) begin
            if(frame_sequence!==last_sequence+1'b1)$fatal(1,"Bluetooth PCM sequence skipped");
            last_sequence=frame_sequence;
            previous_tap=current_tap;current_tap=frame_pcm;
            previous_mute=current_mute;current_mute=smute;
        end
    end
    always @(negedge audio_clk) begin
        sample_valid = 0;
        if (!audio_reset_n || !source_running) source_count = 0;
        else if (source_count >= source_period-1) begin
            source_count = 0;
            pcm = samples_sent[0] ? 32'h1234abcd : 32'hcdef5678;
            samples_sent = samples_sent + 1;
            sample_valid = 1;
        end else source_count = source_count + 1;
    end

    reg previous_ws = 0, aligned = 0;
    reg [31:0] serial_word = 0, left_word = 0;
    integer bits_seen = 0, checked_pairs = 0, nonzero_pairs = 0, master_edges = 0;
    realtime previous_bck = 0, previous_mclk = 0, previous_lrck = 0;
    always @(posedge mclk) begin
        master_edges = master_edges + 1;
        if (pdn_n && previous_mclk && ($realtime-previous_mclk < 81 || $realtime-previous_mclk > 82))
            $fatal(1, "MCLK is not 12.288 MHz");
        previous_mclk = $realtime;
    end
    always @(posedge lrck) begin
        if (pdn_n && previous_lrck && ($realtime-previous_lrck < 20800 || $realtime-previous_lrck > 20860))
            $fatal(1, "LRCK is not 48 kHz");
        previous_lrck = $realtime;
    end
    always @(data_bit)
        if (reset_n && audio_reset_n && bck) $fatal(1, "SDATA changed while BICK high");
    always @(negedge pdn_n) begin
        aligned = 0;
        bits_seen = 0;
        previous_bck = 0;
        previous_mclk = 0;
        previous_lrck = 0;
    end
    function [31:0] scaled_pair(input [31:0] pair_value, input [15:0] gain_value);
        reg signed [32:0] left_value,right_value;
        begin
            left_value=$signed(pair_value[31:16])*$signed({1'b0,gain_value});
            right_value=$signed(pair_value[15:0])*$signed({1'b0,gain_value});
            scaled_pair={left_value[30:15],right_value[30:15]};
        end
    endfunction
    always @(posedge bck) begin
        if (pdn_n && previous_bck && ($realtime-previous_bck < 325 || $realtime-previous_bck > 327))
            $fatal(1, "BICK is not 3.072 MHz");
        previous_bck = $realtime;
        serial_word = {serial_word[30:0], data_bit};
        if (lrck != previous_ws) begin
            if (aligned) begin
                if (bits_seen != 31 || serial_word[15:0] != 0)
                    $fatal(1, "I2S slot length, one-bit delay or PCM16 padding wrong");
                if (!previous_ws) left_word = serial_word;
                else begin
                    checked_pairs = checked_pairs + 1;
                    if(frame_sequence>6 && previous_tap!==(previous_mute ? 32'd0 : {left_word[31:16],serial_word[31:16]}))
                        $fatal(1,"Bluetooth tap differs from actual I2S stereo/mute");
                    if (check_exact &&
                        {left_word[31:16], serial_word[31:16]} != scaled_pair(32'h1234abcd,expected_gain) &&
                        {left_word[31:16], serial_word[31:16]} != scaled_pair(32'hcdef5678,expected_gain) &&
                        {left_word[31:16], serial_word[31:16]} != 0)
                        $fatal(1, "left/right swap or torn PCM frame: pcm=%h gain=%0d expected=%0d", {left_word[31:16],serial_word[31:16]},dut.gain,expected_gain);
                    if (left_word != 0) nonzero_pairs = nonzero_pairs + 1;
                end
            end
            previous_ws = lrck;
            aligned = pdn_n;
            bits_seen = 0;
            serial_word = 0;
        end else bits_seen = bits_seen + 1;
    end

    initial begin
        #1;
        if (pdn_n !== 0 || smute !== 1) $fatal(1, "unsafe power-on controls");
        repeat (8) @(negedge audio_clk);
        reset_n = 1;
        audio_reset_n = 1;
        @(posedge pdn_n);
        if (master_edges < 1024 || !smute) $fatal(1, "PDN released before stable clocks");
        wait (!smute);
        check_exact=1;
        if (checked_pairs < 1020 || nonzero_pairs < 1000) $fatal(1, "startup/PCM stream missing");
        source_period = 1741;
        repeat (48) @(posedge lrck);
        if (smute) $fatal(1, "44.1 kHz input was treated as underrun");
        source_period = 800;
        repeat (48) @(posedge lrck);
        if (smute || drops != 0) $fatal(1, "96 kHz input stalled or dropped mailbox transfers");
        check_exact=0;master_volume=16384;
        repeat (132) @(posedge lrck);
        expected_gain=16384;check_exact=1;
        repeat (16) @(posedge lrck);
        if(dut.gain!=16384 || smute)$fatal(1,"half volume did not settle once at final output");
        if(dut.frame_pcm!=scaled_pair(32'h1234abcd,16384) && dut.frame_pcm!=scaled_pair(32'hcdef5678,16384))
            $fatal(1,"half volume output is silent or was attenuated twice");
        check_exact=0;master_volume=0;
        repeat (4) @(posedge lrck);
        if(!smute || dut.frame_pcm!=0)$fatal(1,"zero volume did not mute all final sources");
        master_volume=32768;
        repeat (132) @(posedge lrck);
        expected_gain=32768;check_exact=1;
        source_period = 9600;
        repeat (48) @(posedge lrck);
        if (smute) $fatal(1, "8 kHz input was treated as underrun");
        source_running = 0;
        repeat (22) @(posedge lrck);
        if (!smute || dut.frame_pcm != 0) $fatal(1, "stopped input replayed stale audio");
        enable = 0;
        source_running = 1;
        source_period = 1600;
        repeat (8) @(posedge lrck);
        if (!smute || dut.frame_pcm != 0) $fatal(1, "disabled output was not silent");
        enable = 1;
        check_exact=0;
        repeat (132) @(posedge lrck);
        check_exact=1;
        if (smute) $fatal(1, "output did not resume");
        check_exact=0;
        reference_running = 0;
        #2000;
        if (pdn_n || !smute) $fatal(1, "reference loss did not mute/reset within 2us");
        repeat (3200) @(posedge audio_clk);
        reference_running = 1;
        @(posedge pdn_n);
        if (!smute) $fatal(1, "reference restart skipped muted startup");
        wait (!smute);
        check_exact=0;
        if ({sslow, sd, slow} !== 0 || drops != 0) $fatal(1, "filter controls/mailbox wrong");
        $display("PASS FPC audio: I2S stereo, 256fs MCLK, final master gain, rate conversion, silence, reference recovery; pairs=%0d", checked_pairs);
        $finish;
    end
    initial begin
        #60000000;
        $fatal(1, "FPC audio timeout");
    end
endmodule
