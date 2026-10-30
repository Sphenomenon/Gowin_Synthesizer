`timescale 1ns/1ps
// Standalone runner: both paths share inputs and ordered DDR responses. Reference
// reconstructed from the immutable baseline; only its module name is changed.
module tb_tf_path_default_reference;
    reg source_clk=0,memory_clk=0,rst_n=0,restart=0,hold_noise=0;
    reg [3:0] track=0;
    always #10 source_clk=~source_clk;
    always #5 memory_clk=~memory_clk;
    wire pcm_valid[0:1],format_ready[0:1],unsupported[0:1],card_lost[0:1],pcm_end[0:1];
    wire req[0:1],wren[0:1],wend[0:1],playlist[0:1],ddr_error[0:1],playing[0:1];
    wire [31:0] pcm[0:1],file_size[0:1];
    wire [19:0] rate[0:1];
    wire [28:0] address[0:1];
    wire [255:0] write_data[0:1];
    wire [2:0] command[0:1];
    wire [4:0] track_count[0:1];
    wire [10:0] debug[0:1];
    integer source_cycle=0,memory_cycle=0,frames=0,compares=0;
    wire pcm_ready=source_cycle%13==0;
    wire ready=memory_cycle%7!=0;
    reg response=0,pending=0;
    reg [255:0] response_data=0,pending_data;
    reg [255:0] memory[0:127];
    integer delay_count=0;
`define PATH_PORTS \
    .clk_50m(source_clk),.reset_n(rst_n),.restart(restart),.track_index(track),.capture_enable_i(1'b1), \
    .memory_clk(memory_clk),.memory_reset_n(rst_n),.memory_ready(1'b1),.sample_tick(1'b0), \
    .sd_miso(1'b1),.sd_cs_n(),.sd_sck(),.sd_mosi(),.card_type(),.card_stat(), \
    .filesystem_type(),.filesystem_stat(),.scan_done(),.card_lost(card_lost[g]), \
    .hotplug_debug(debug[g]),.card_ready(),.playing(playing[g]),.eof(),.track_count(track_count[g]), \
    .playlist_ready(playlist[g]),.playlist_name_addr(8'd0),.playlist_name_data(), \
    .format_ready(format_ready[g]),.unsupported(unsupported[g]),.audio_ddr_error(ddr_error[g]), \
    .audio_bank0_valid(),.audio_bank1_valid(),.audio_file_size(file_size[g]),.sample_rate_hz(rate[g]), \
    .stereo(),.bits_per_sample(),.pcm_valid(pcm_valid[g]),.pcm_end(pcm_end[g]),.pcm_ready(pcm_ready), \
    .pcm_left(pcm[g][31:16]),.pcm_right(pcm[g][15:0]),.frame_count(),.resync_count(), \
    .skipped_frames(),.stuck_frames(),.pcm_fifo_parity_errors(),.debug_cmdrsp(),.debug_rwrsp(), \
    .debug_cardstate(),.debug_spidone(),.debug_rvalid_session(),.app_cmd(command[g]),.app_en(req[g]), \
    .app_addr(address[g]),.app_wdata(write_data[g]),.app_rdy(ready),.app_wren(wren[g]), \
    .app_wend(wend[g]),.app_wrdy(ready),.app_rvalid(response),.app_rdata(response_data)
    for(genvar g=0;g<2;g=g+1)begin: paths
        if(g==0)begin: native_default
            tf_audio_ddr_path #(.AUDIO_KIND(2),.FILE_EXT("WAV")) path(
                `PATH_PORTS,.native_memory_hold_i(hold_noise));
        end else begin: frozen_reference
            tf_audio_ddr_path_legacy_reference #(.AUDIO_KIND(2),.FILE_EXT("WAV")) path(`PATH_PORTS);
        end
    end
`undef PATH_PORTS
    always @(posedge source_clk)begin
        source_cycle<=source_cycle+1;
        if(rst_n && pcm_valid[0] && pcm_ready)begin
            if(pcm[0]!=={16'(1000+track*100+frames%64),16'(-2000-track*100-frames%64)} ||
               rate[0]!==(track==1 ? 20'd44100:20'd48000))$fatal(1,"default reference golden mismatch");
            frames=frames+1;
        end
    end
    always @(posedge memory_clk)begin
        memory_cycle<=memory_cycle+1;hold_noise<=memory_cycle%3==0;response<=0;
        if(!rst_n)pending<=0;
        else begin
            if(req[0] && ready)begin
                if(address[0]<29'h0600000 || address[0]>=29'h0600400 || address[0][2:0]!=0)$fatal(1,"default DDR bounds");
                if(wren[0])memory[(address[0]-29'h0600000)>>3]<=write_data[0];
                else begin
                    if(pending)$fatal(1,"default multiple read");
                    pending_data<=memory[(address[0]-29'h0600000)>>3];pending<=1;delay_count<=3;
                end
            end
            if(pending)begin
                if(delay_count==0)begin response<=1;response_data<=pending_data;pending<=0;end
                else delay_count<=delay_count-1;
            end
        end
    end
    task compare_outputs;
        begin
            if(rst_n)begin
                if({pcm_valid[0],pcm[0],rate[0],format_ready[0],unsupported[0],card_lost[0],pcm_end[0],
                    req[0],wren[0],wend[0],command[0],address[0],write_data[0],playlist[0],ddr_error[0],
                    playing[0],file_size[0],track_count[0],debug[0]} !==
                   {pcm_valid[1],pcm[1],rate[1],format_ready[1],unsupported[1],card_lost[1],pcm_end[1],
                    req[1],wren[1],wend[1],command[1],address[1],write_data[1],playlist[1],ddr_error[1],
                    playing[1],file_size[1],track_count[1],debug[1]})$fatal(1,"default path drift at %0t",$time);
                compares=compares+1;
            end
        end
    endtask
    always @(negedge memory_clk)compare_outputs();
    always @(negedge source_clk)compare_outputs();
    initial begin
        repeat(8)@(negedge source_clk);rst_n=1;
        wait(frames==64);repeat(20)@(negedge source_clk);
        rst_n=0;track=1;repeat(8)@(negedge source_clk);rst_n=1;
        wait(frames==128);repeat(20)@(negedge source_clk);
        restart=1;@(negedge source_clk);restart=0;repeat(1000)@(negedge source_clk);
        $display("PASS tf_path_default_reference: frames=%0d cycle_compares=%0d",frames,compares);$finish;
    end
    initial begin #1000000;$fatal(1,"default reference timeout frames=%0d",frames);end
endmodule
