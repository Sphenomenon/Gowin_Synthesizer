`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
// Exact selected CQT/CNN/cache/Viterbi sources and real WAV byte decoding.
// Automatic configuration ROM -> DDR -> readback CRC precedes inference.
// No model preload, forced readiness, CNN output, layer state or score.
module tb_cnn_demo_inference #(
    parameter integer FILE_BYTES=384044,
    parameter integer AUDIO_KIND=2,
    parameter integer FRAMES=3,
    parameter integer MAX_CYCLES=200000000
);
    reg clk=0,rstn=0,restart=0;
    always #10 clk=~clk;
    reg [7:0] wav[0:FILE_BYTES-1];
    integer byte_index=0,pcm_count=0,cycles=0,model_reads=0;
    wire in_ready,pcm_valid,pcm_ready,header,unsupported,decode_error;
    wire signed [15:0] pcm_l,pcm_r;
    wire [19:0] rate;
    // The user selects a song after the Push model-ready state. Do not send
    // WAV bytes during boot, when the analysis owner is not ready to accept.
    // Match the historical DDR byte FIFO's separated read pulses. In
    // particular, the legacy MP3 framer uses an internal header-size cycle.
    wire in_valid=rstn && model_status==14 && !cycles[0] && byte_index<FILE_BYTES;
    always @(posedge clk)if(in_valid && in_ready)byte_index<=byte_index+1;
    tf_audio_decoder_ip #(.FORMAT(AUDIO_KIND)) decoder(.clk_i(clk),.rst_ni(rstn),.restart_i(1'b0),
        .byte_valid_i(in_valid),.byte_data_i(byte_index<FILE_BYTES ? wav[byte_index] : 8'd0),
        .byte_ready_o(in_ready),.byte_last_i(byte_index==FILE_BYTES-1),
        .format_ready_o(header),.sample_rate_hz_o(rate),.format_o(),.channels_o(),.bits_per_sample_o(),
        .pcm_valid_o(pcm_valid),.pcm_ready_i(pcm_ready),.pcm_left_o(pcm_l),.pcm_right_o(pcm_r),
        .unsupported_o(unsupported),.error_o(decode_error),.eof_seen_o(),.bytes_seen_o(),
        .frame_count_o(),.resync_count_o(),.stuck_frames_o(),.pcm_fifo_parity_errors_o());
    integer eof_quiet=0;
    // Compressed input may finish while a decoded granule is still in flight.
    always @(posedge clk) begin
        if(byte_index<FILE_BYTES || pcm_valid)eof_quiet<=0;
        else if(eof_quiet<500000)eof_quiet<=eof_quiet+1;
    end
    function automatic [3:0] gmap(input [11:0] g);
        case(g)
            12'h100:gmap=0;12'h101:gmap=1;12'h102:gmap=2;12'h103:gmap=3;
            12'h104:gmap=4;12'h105:gmap=5;12'h106:gmap=6;12'h107:gmap=7;
            12'h108:gmap=8;12'h304:gmap=9;12'h301:gmap=10;12'h302:gmap=11;
            12'h303:gmap=12;default:gmap=15;
        endcase
    endfunction
    reg [15:0] mem[0:13*524288-1];
    wire req,wr;
    wire [31:0] addr;
    wire [15:0] wdata;
    wire [22:0] index={gmap(addr[31:20]),addr[19:1]};
    reg rsp_valid=0;reg [15:0] rdata=0;
    wire mem_ready=rstn && !rsp_valid;
    always @(posedge clk)begin
        rsp_valid<=0;
        if(req && mem_ready)begin
            if(gmap(addr[31:20])==15 || addr[0])$fatal(1,"invalid actual CNN address %h",addr);
            if(wr)mem[index]<=wdata;
            else begin rsp_valid<=1;rdata<=mem[index];if(addr[31:20]==12'h101)model_reads=model_reads+1;end
        end
    end
    wire score_valid,score_ready,done,song_done;
    wire [6:0] score_note,target;
    wire [191:0] hashes;
    wire [8:0] wave;
    wire [15:0] progress;
    wire [3:0] model_status;
    wire [31:0] model_crc;
    basic_pitch_pcm_pipeline #(.WIN_LEN(43844),.FRAME_LIMIT(FRAMES),.OCTAVE_LIMIT(9),
        .USE_EXTERNAL_STATE(1),.USE_EXTERNAL_PLANE(1),.USE_EXTERNAL_WEIGHTS(1),
        .USE_EXTERNAL_FEATURES(1),.USE_ALL_DDR(0),.USE_DDR_SIGNAL(1),
        .USE_DDR_FRONT_COEFF(1),.USE_DDR_CQT_COEFF(1)) dut(
        .clk_i(clk),.rst_ni(rstn),.analysis_restart_i(restart),.model_serial_i(1'b1),
        .model_status_o(model_status),.debug_model_actual_crc_o(model_crc),
        .pcm_valid_i(pcm_valid && !restart),.pcm_end_i(eof_quiet==500000),
        .pcm_ready_o(pcm_ready),.pcm_left_i(pcm_l),.pcm_right_i(pcm_r),
        .score_valid_o(score_valid),.score_ready_i(score_ready),.score_note_o(score_note),
        .debug_layer_hashes_o(hashes),.debug_stream_wave_o(wave),.debug_progress_o(progress),
        .done_o(done),.song_done_o(song_done),
        .mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),.mem_wdata_o(wdata),
        .mem_ready_i(mem_ready),.mem_rsp_valid_i(rsp_valid),.mem_rdata_i(rdata));
    reg toggle=0,played=0,clear=0;reg [6:0] played_note=0;
    wire mode,target_valid;wire [15:0] count,cursor,wrong;wire [63:0] mask;
    push2_score_guide guide(.clk,.rst(!rstn),.score_valid,.score_ready,.score_note,
        .toggle,.selected_i(1'b1),.clear_i(clear),.played_valid(played),.played_note,
        .mode,.target_valid,.target_note(target),.score_count(count),.cursor,
        .wrong_count(wrong),.guide_mask(mask));
    integer writes[0:5];
    always @(posedge clk)if(rstn)begin
        cycles=cycles+1;
        if(pcm_valid && pcm_ready)pcm_count=pcm_count+1;
        if(unsupported || decode_error || (header && rate!=48000))$fatal(1,"unsupported/error audio rate=%0d",rate);
        if(dut.contour_act_valid)writes[0]=writes[0]+1;
        if(dut.reduce_act_valid)writes[1]=writes[1]+1;
        if(dut.notes_act_valid)writes[2]=writes[2]+1;
        if(dut.note_out_act_valid)writes[3]=writes[3]+1;
        if(dut.onset_act_valid)writes[4]=writes[4]+1;
        if(dut.onset_out_act_valid)writes[5]=writes[5]+1;
        if(cycles%10000000==0)begin
            $display("CNN heartbeat cycles=%0d PCM=%0d wave=%0d progress=%0d notes=%0d",cycles,pcm_count,wave,progress,count);$fflush();
        end
        if(cycles>MAX_CYCLES)$fatal(1,"inference timeout wave=%0d progress=%0d",wave,progress);
    end
    integer i,old_cursor;
    initial begin
        $readmemh("cnn_fixture.mem",wav);
        for(i=0;i<13*524288;i=i+1)mem[i]=0;
        for(i=0;i<6;i=i+1)writes[i]=0;
        repeat(8)@(negedge clk);rstn=1;toggle=1;
        @(negedge clk);toggle=0;
        wait(done);repeat(100)@(negedge clk);
        if(model_status!=14 || model_crc!=32'hAF01A61B)$fatal(1,"embedded model boot not verified");
        if(pcm_count<40000 || model_reads<100 || hashes==0)$fatal(1,"missing real model input or inference");
        for(i=0;i<6;i=i+1)if(writes[i]==0)$fatal(1,"missing real CNN layer %0d",i);
        if(count==0 || !target_valid)$fatal(1,"real inference emitted no guide target");
        old_cursor=cursor;played_note=target^7'd1;played=1;
        @(negedge clk);played=0;
        if(cursor!=old_cursor || wrong==0)$fatal(1,"wrong key advanced");
        played_note=target;played=1;
        @(negedge clk);played=0;
        if(cursor!=old_cursor+1)$fatal(1,"correct real CNN target did not advance");
        $display("PASS CNN demo inference: decoded_PCM=%0d model_reads=%0d notes=%0d hashes=%048h correct/wrong-key",pcm_count,model_reads,count,hashes);
        clear=1;restart=1;
        repeat(4)@(negedge clk);clear=0;
        if(model_status!=14 || model_crc!=32'hAF01A61B)$fatal(1,"song restart disturbed verified model");
        if(count!=0 || cursor!=0 || target_valid || mask!=0)$fatal(1,"reselection retained old guidance");
        $display("PASS CNN demo inference cleanup: no stale target after restart");
        $finish;
    end
endmodule
