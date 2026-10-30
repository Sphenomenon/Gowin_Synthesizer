`timescale 1ns/1ps
module tb_display_analysis_context;
    import display_data_layout_pkg::*;
    reg clk=0,rst_n=0,start=0,rate44=0,trusted=1,loss=0;
    reg [31:0] epoch=1,sequence_number=0;
    always #5 clk=!clk;
    reg frame_valid=0,frame_error=0;
    reg [31:0] pcm=0;
    integer ticks=0;
    function automatic integer left_pcm(input integer n);left_pcm=$rtoi(12000.0*$sin(6.283185307179586*32.0*n/2048.0));endfunction
    function automatic integer right_pcm(input integer n);right_pcm=$rtoi(8000.0*$cos(6.283185307179586*64.0*n/2048.0));endfunction
    function automatic [31:0] mono(input integer n);mono=32'(left_pcm(n)+right_pcm(n))<<15;endfunction
    always @(negedge clk)begin
        frame_valid=0;
        if(rst_n)begin
            ticks=ticks+1;
            if(ticks%16==0)begin
                frame_valid=1;pcm={16'(left_pcm(integer'(sequence_number%64))),16'(right_pcm(integer'(sequence_number%64)))};
                sequence_number=sequence_number+1'b1;
            end
        end
    end
    wire start_ready,source_valid,wave_valid,analysis_context,av;
    wire [31:0] source_rate,source_epoch,source_generation,wave_rate,wave_epoch,wave_generation;
    wire [31:0] analysis_rate,analysis_epoch,analysis_generation,aseq,askip,peaks,discarded,source_data;
    wire [2:0] gain;
    wire [255:0] meta;
    wire wdone,wbusy,initialized,wreq,wread;
    wire [1:0] kind;
    wire [15:0] address;
    wire [28:0] waddr;
    wire [255:0] wdata;
    wire rejected,aborted;
    display_data_analysis_source source(
        .clk,.rst_ni(rst_n),.frame_valid_i(frame_valid),.frame_error_i(frame_error),.frame_44k1_i(rate44),
        .frame_epoch_i(epoch),.frame_sequence_i(sequence_number),.frame_pcm_i(pcm),
        .observation_trusted_i(trusted),.observation_loss_i(loss),.trigger_reference_i(32'd0),
        .active_voices_i(32'd3),.status_i(32'd0),.memory_status_i(32'hcb),.effect_mask_i(3'd3),.effect_order_i(6'b10_01_00),
        .start_i(start),.export_done_i(wdone),.start_ready_o(start_ready),.source_context_valid_o(source_valid),
        .source_sample_rate_o(source_rate),.source_epoch_o(source_epoch),.source_generation_o(source_generation),
        .waveform_context_valid_o(wave_valid),.analysis_context_valid_o(analysis_context),
        .waveform_sample_rate_o(wave_rate),.waveform_epoch_o(wave_epoch),.waveform_generation_o(wave_generation),
        .analysis_sample_rate_o(analysis_rate),.analysis_epoch_o(analysis_epoch),.analysis_generation_o(analysis_generation),
        .effect_meta_o(meta),.analysis_sequence_o(aseq),.analysis_skipped_o(askip),.stereo_peaks_o(peaks),.analysis_valid_o(av),
        .image_gain_o(gain),.discarded_contexts_o(discarded),.read_enable_i(wread),.read_kind_i(kind),.read_addr_i(address),.read_data_o(source_data));
    display_data_writer #(.METADATA_MINOR(1)) writer(
        .clk,.rst_n,.enabled(rst_n),.start,.effect_meta(meta),.analysis_sequence(aseq),.analysis_skipped(askip),.stereo_peaks(peaks),.analysis_valid(av),.image_gain(gain),
        .source_context_valid_i(source_valid),.source_sample_rate_i(source_rate),.source_epoch_i(source_epoch),.source_generation_i(source_generation),
        .waveform_context_valid_i(wave_valid),.waveform_sample_rate_i(wave_rate),.waveform_epoch_i(wave_epoch),.waveform_generation_i(wave_generation),
        .analysis_context_valid_i(analysis_context),.analysis_sample_rate_i(analysis_rate),.analysis_epoch_i(analysis_epoch),.analysis_generation_i(analysis_generation),
        .context_rejected_o(rejected),.context_aborted_o(aborted),.context_unavailable_o(),.context_diagnostic_o(),
        .busy(wbusy),.done(wdone),.initialized,.req_valid(wreq),.req_ready(1'b1),.req_addr(waddr),.req_wdata(wdata),
        .read_enable(wread),.read_kind(kind),.read_addr(address),.read_data(source_data));
    reg [255:0] memory[0:16383];
    function automatic integer slot(input [28:0] a);
        if(a>=PAYLOAD_BANK1_WORD)slot=8192+((integer'(a)-integer'(PAYLOAD_BANK1_WORD))>>3);
        else if(a>=PAYLOAD_BANK0_WORD)slot=4096+((integer'(a)-integer'(PAYLOAD_BANK0_WORD))>>3);
        else slot=((integer'(a)-integer'(LEGACY_META_WORD))>>3);
    endfunction
    reg rstart=0,response=0,pending=0;
    reg [255:0] response_data=0,pending_data=0;
    wire rbusy,rdone,rvalid,rfault,rreq;
    wire [28:0] raddr;
    integer commits=0,checked_wave=0,checked_image=0,checked_columns=0,published=0,early_rejects=0,abort_count=0;
    always @(posedge clk)begin
        response<=0;
        if(rst_n)begin
            if(wreq)begin memory[slot(waddr)]=wdata;if(waddr==DISPLAY_CONTROL_WORD && wdata!=0)commits=commits+1;end
            if(rejected)early_rejects=early_rejects+1;
            if(aborted)abort_count=abort_count+1;
            if(rreq && !pending)begin pending<=1;pending_data=memory[slot(raddr)];end
            if(pending)begin response<=1;response_data<=pending_data;pending<=0;end
        end
    end
    reg render_enable=0;
    reg [8:0] wave_address=0,column=0;
    reg [15:0] image_address=0;
    wire [31:0] wave_data,render_rate,render_epoch,render_generation;
    wire [7:0] left_level,right_level;
    wire image_hit;
    display_data_reader #(.METADATA_MINOR(1)) reader(
        .clk,.rst_n,.enabled(rst_n),.start(rstart),.busy(rbusy),.done(rdone),.valid(rvalid),.fault(rfault),
        .req_valid(rreq),.req_ready(!pending),.req_addr(raddr),.rsp_valid(response),.rsp_data(response_data),
        .render_read_enable(render_enable),.render_wave_addr(wave_address),.render_image_addr(image_address),.render_spectrum_column(column),
        .render_wave_data(wave_data),.render_image_hit(image_hit),.render_spectrum_left(left_level),.render_spectrum_right(right_level),
        .render_meta(),.render_analysis_sequence(),.render_analysis_skipped(),.render_stereo_peaks(),.render_image_gain(),
        .render_analysis_valid(),.render_frame_sequence(),.render_sample_rate_o(render_rate),.render_epoch_o(render_epoch),
        .render_generation_o(render_generation),.render_context_changed_o(),.incompatible_o(),.diagnostic_code_o());
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task export_and_verify(input integer actual_rate,input integer actual_epoch);
        integer peak_l,peak_r,max_l,max_r,phase,px,py;
        reg expected_pixel;
        begin
            wait(start_ready && !wbusy);
            // Freeze the independent wave phase while the producer front is
            // locked. It may acquire its next wave after export_done.
            phase=-1;
            for(integer n=0;n<64;n=n+1)if(source.aligner.trace_samples[0]===mono(n) &&
                source.aligner.trace_samples[1]===mono(n+1))phase=n;
            if(phase<0)$fatal(1,"waveform is not unfiltered physical PCM");
            @(negedge clk);start=1;clocks(1);start=0;
            wait(wdone);clocks(1);
            peak_l=0;peak_r=0;max_l=0;max_r=0;
            for(integer bin=2;bin<=853;bin=bin+1)begin
                if(integer'(source.analysis.levels_left[bin])>max_l)begin max_l=integer'(source.analysis.levels_left[bin]);peak_l=bin;end
                if(integer'(source.analysis.levels_right[bin])>max_r)begin max_r=integer'(source.analysis.levels_right[bin]);peak_r=bin;end
            end
            if(peak_l!=32 || peak_r!=64)$fatal(1,"actual stereo FFT bin drift left=%0d right=%0d",peak_l,peak_r);
            rstart=1;clocks(1);rstart=0;wait(rdone);clocks(1);
            if(!rvalid || rfault || render_rate!=32'(actual_rate) || render_epoch!=32'(actual_epoch))$fatal(1,"actual result relabeled");
            render_enable=1;
            for(integer i=0;i<65536;i=i+1)begin
                wave_address=9'(i);image_address=16'(i);column=9'(i);clocks(3);
                if(i<512)begin
                    if(wave_data!==mono((phase+i)%64))$fatal(1,"physical waveform mismatch index=%0d",i);
                    checked_wave=checked_wave+1;
                    if({right_level,left_level}!=={source.analysis.display_right[source.analysis.read_bank*512+i],source.analysis.display_left[source.analysis.read_bank*512+i]})
                        $fatal(1,"FFT log-column transport changed index=%0d",i);
                    checked_columns=checked_columns+1;
                end
                expected_pixel=0;
                for(integer n=0;n<64;n=n+1)begin
                    px=128+(left_pcm(n) >>> (9-integer'(gain)));py=128-(right_pcm(n) >>> (9-integer'(gain)));
                    if(px<0)px=0;if(px>255)px=255;if(py<0)py=0;if(py>255)py=255;
                    if(i==py*256+px)expected_pixel=1;
                end
                if(image_hit!==expected_pixel)$fatal(1,"physical XY bitmap mismatch at %0d",i);
                checked_image=checked_image+1;
            end
            render_enable=0;published=published+1;
            $display("RATE_CHECK rate=%0d epoch=%0d left_bin=%0d right_bin=%0d left_hz_q16=%0d right_hz_q16=%0d generation=%0d",actual_rate,actual_epoch,peak_l,peak_r,(64'(peak_l)*64'(render_rate)*65536)/2048,(64'(peak_r)*64'(render_rate)*65536)/2048,render_generation);
        end
    endtask
    initial begin
        for(integer i=0;i<16384;i=i+1)memory[i]=0;
        clocks(4);rst_n=1;wait(initialized);export_and_verify(48000,1);
        // Cancel a fully captured old PCM block during real FFT processing.
        wait(start_ready && !wbusy);@(negedge clk);start=1;clocks(1);start=0;
        wait(source.analysis.state==source.analysis.FFT_MULT);@(negedge clk);rate44=1;epoch=2;sequence_number=0;
        wait(wdone);clocks(40);if(start_ready || av || wave_valid || abort_count!=1)$fatal(1,"old result survived physical epoch change");
        start=1;clocks(1);start=0;wait(wdone);clocks(2);
        if(commits!=1 || early_rejects!=1)$fatal(1,"incomplete new analysis published");
        export_and_verify(44100,2);
        // A sequence loss with unchanged stream epoch discards both workspaces;
        // a separate local cancellation generation prevents old-window reuse.
        @(negedge clk);loss=1;clocks(1);loss=0;clocks(3);
        if(start_ready || av || wave_valid)$fatal(1,"loss did not invalidate analysis window");
        export_and_verify(44100,2);
        trusted=0;clocks(20);if(start_ready || source_valid || av)$fatal(1,"untrusted source admitted image");
        if(published!=3 || commits!=3 || discarded<3)$fatal(1,"analysis context coverage");
        $display("PASS display_analysis_context: published=%0d physical_wave_samples=%0d xy_pixels=%0d fft_columns=%0d discarded=%0d early_rejected=%0d",published,checked_wave,checked_image,checked_columns,discarded,early_rejects);
        $finish;
    end
    initial begin #100000000;$fatal(1,"analysis context watchdog");end
endmodule
