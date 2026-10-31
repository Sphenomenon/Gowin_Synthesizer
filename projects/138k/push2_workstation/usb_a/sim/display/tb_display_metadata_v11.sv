`timescale 1ns/1ps
module tb_display_metadata_v11;
    import display_data_layout_pkg::*;
    reg clk=0,rst_n=0,wstart=0,rstart=0;
    always #5 clk=!clk;
    reg source_valid=1,wave_valid=1,analysis_context=1,analysis_valid=1;
    reg [31:0] rate=48000,epoch=1,cancel_generation=10,wave_epoch=1,analysis_epoch=1;
    reg [31:0] wave_generation_offset=0,analysis_generation_offset=0;
    reg [31:0] tag=1;
    wire wbusy,wdone,initialized,wreq,wread,rejected,aborted,unavailable;
    wire [2:0] wdiagnostic;
    wire [28:0] waddr;
    wire [255:0] wdata;
    wire [1:0] kind;
    wire [15:0] address;
    reg [31:0] source_data=0;
    reg write_stall=0,reader_stall=0,write_always_ready=0;
    integer cycles=0,writes=0,commits=0,rejections=0,aborts=0,reads=0,checks=0,first_reads=0;
    wire wready=!write_stall && (write_always_ready || cycles%7!=0);
    wire [255:0] effect_meta={32'h44495350,23'd0,6'b10_01_00,3'd3,32'h32100000,32'h3,
        32'h11223344,tag+32'd100,32'd9,32'hcb};
    display_data_writer #(.METADATA_MINOR(1)) writer(
        .clk,.rst_n,.enabled(rst_n),.start(wstart),.effect_meta,.analysis_sequence(tag+32'd200),
        .analysis_skipped(32'd11),.stereo_peaks(32'h12345678),.analysis_valid,.image_gain(3'd5),
        .source_context_valid_i(source_valid),.source_sample_rate_i(rate),.source_epoch_i(epoch),.source_generation_i(cancel_generation),
        .waveform_context_valid_i(wave_valid),.waveform_sample_rate_i(rate),.waveform_epoch_i(wave_epoch),.waveform_generation_i(cancel_generation+wave_generation_offset),
        .analysis_context_valid_i(analysis_context),.analysis_sample_rate_i(rate),.analysis_epoch_i(analysis_epoch),.analysis_generation_i(cancel_generation+analysis_generation_offset),
        .context_rejected_o(rejected),.context_aborted_o(aborted),.context_unavailable_o(unavailable),.context_diagnostic_o(wdiagnostic),
        .busy(wbusy),.done(wdone),.initialized,.req_valid(wreq),.req_ready(wready),.req_addr(waddr),.req_wdata(wdata),
        .read_enable(wread),.read_kind(kind),.read_addr(address),.read_data(source_data));
    function automatic [31:0] source_value(input [31:0] identity,input [1:0] k,input [15:0] a);
        if(k==0)source_value=(identity<<20)+{16'd0,a};
        else if(k==1)source_value={31'd0,((32'(a)+identity)%17)==3};
        else source_value={16'd0,8'(32'(a)+identity+1),8'(32'(a)+identity)};
    endfunction
    always @(posedge clk)if(wread)source_data<=source_value(tag,kind,address);
    reg [255:0] memory[0:16383];
    function automatic integer slot(input [28:0] a);
        if(a>=PAYLOAD_BANK1_WORD)slot=8192+((integer'(a)-integer'(PAYLOAD_BANK1_WORD))>>3);
        else if(a>=PAYLOAD_BANK0_WORD)slot=4096+((integer'(a)-integer'(PAYLOAD_BANK0_WORD))>>3);
        else slot=((integer'(a)-integer'(LEGACY_META_WORD))>>3);
    endfunction
    wire rbusy,rdone,rvalid,rfault,rreq,incompatible,context_changed;
    wire [3:0] diagnostic;
    wire [28:0] raddr;
    reg response=0;
    reg [255:0] response_data=0,pending_data=0;
    reg pending=0;
    integer delay_count=0,header_reads=0;
    reg mutate_final=0;
    wire rready=!pending && !reader_stall && cycles%5!=0;
    reg render_enable=0;
    reg [8:0] wave_address=0,column=0;
    reg [15:0] image_address=0;
    wire [31:0] wave_data,aseq,askip,peaks,frame_sequence,render_rate,render_epoch,render_generation;
    wire image_hit,render_analysis_valid;
    wire [7:0] left_level,right_level;
    wire [2:0] gain;
    wire [255:0] meta;
    display_data_reader #(.METADATA_MINOR(1)) reader(
        .clk,.rst_n,.enabled(rst_n),.start(rstart),.busy(rbusy),.done(rdone),.valid(rvalid),.fault(rfault),
        .req_valid(rreq),.req_ready(rready),.req_addr(raddr),.rsp_valid(response),.rsp_data(response_data),
        .render_read_enable(render_enable),.render_wave_addr(wave_address),.render_image_addr(image_address),.render_spectrum_column(column),
        .render_wave_data(wave_data),.render_image_hit(image_hit),.render_spectrum_left(left_level),.render_spectrum_right(right_level),
        .render_meta(meta),.render_analysis_sequence(aseq),.render_analysis_skipped(askip),.render_stereo_peaks(peaks),
        .render_image_gain(gain),.render_analysis_valid,.render_frame_sequence(frame_sequence),
        .render_sample_rate_o(render_rate),.render_epoch_o(render_epoch),.render_generation_o(render_generation),
        .render_context_changed_o(context_changed),.incompatible_o(incompatible),.diagnostic_code_o(diagnostic));
    reg stalled=0;
    reg [28:0] held_addr;
    reg [255:0] held_data;
    always @(posedge clk)begin
        cycles=cycles+1;response<=0;
        if(rst_n)begin
            if(stalled && (!wreq || waddr!==held_addr || wdata!==held_data))$fatal(1,"writer withdrew/changed stalled request");
            stalled=wreq && !wready;held_addr=waddr;held_data=wdata;
            if(wreq && wready)begin
                memory[slot(waddr)]=wdata;writes=writes+1;
                if(waddr==DISPLAY_CONTROL_WORD && wdata!=0)commits=commits+1;
            end
            if(rejected)rejections=rejections+1;
            if(aborted)aborts=aborts+1;
            if(rreq && rready)begin
                if(pending)$fatal(1,"two outstanding reads");
                pending<=1;delay_count<=2;pending_data=memory[slot(raddr)];reads=reads+1;
                if(raddr==BANK0_HEADER_WORD || raddr==BANK1_HEADER_WORD)begin
                    header_reads=header_reads+1;
                    if(mutate_final && header_reads==2)begin
                        pending_data[96]=1;mutate_final=0;
                    end
                end
            end
            if(pending)begin
                if(delay_count==0)begin response<=1;response_data<=pending_data;pending<=0;end
                else delay_count=delay_count-1;
            end
        end
    end
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task write_frame;
        begin @(negedge clk);wstart=1;clocks(1);wstart=0;wait(wdone);clocks(1);end
    endtask
    task abort_final_payload(input bit during_write);
        integer old_commits,old_aborts;
        begin
            old_commits=commits;old_aborts=aborts;write_always_ready=1;
            @(negedge clk);wstart=1;clocks(1);wstart=0;
            wait(writer.kind==2 && writer.index==511 &&
                writer.state==(during_write ? writer.WRITE : writer.CAPTURE));
            // Change only across the final capture/accepted-write edge. Even
            // a one-edge identity loss must cancel the unpublished packet.
            @(negedge clk);source_valid=0;clocks(1);source_valid=1;
            wait(wdone);clocks(2);write_always_ready=0;
            if(commits!=old_commits || aborts!=old_aborts+1 || !unavailable)
                $fatal(1,"final payload context change published during_write=%0d",during_write);
        end
    endtask
    task read_frame(input bit good);
        reg [31:0] expected_wave,expected_image,expected_spectrum;
        begin header_reads=0;render_enable=1;wave_address=511;image_address=65535;column=511;
            @(negedge clk);rstart=1;clocks(1);rstart=0;wait(rdone);clocks(1);
            if(good && (!rvalid || rfault || rbusy))$fatal(1,"good writer packet rejected diag=%0d",diagnostic);
            if(!good && (!rfault || rbusy))$fatal(1,"bad snapshot did not terminate with fault");
            if(good)begin
                expected_wave=source_value(tag,0,16'd511);expected_image=source_value(tag,1,16'd65535);
                expected_spectrum=source_value(tag,2,16'd511);
                if(wave_data!==expected_wave || image_hit!==expected_image[0] ||
                   {right_level,left_level}!==expected_spectrum[15:0])$fatal(1,"first synchronous read published old local bank");
                first_reads=first_reads+1;
            end
            render_enable=0;
        end
    endtask
    task check_cache(input integer identity,input integer actual_rate,input integer actual_epoch);
        reg [31:0] expected_wave,expected_image,expected_spectrum;
        begin
            if(!rvalid || render_rate!=32'(actual_rate) || render_epoch!=32'(actual_epoch) ||
               aseq!=32'(identity+200) || askip!=11 || peaks!=32'h12345678 || gain!=5 || !render_analysis_valid ||
               meta[95:64]!=32'(identity+100) || meta[255:224]!=32'h44495350)
                $fatal(1,"published metadata changed without valid atomic commit");
            render_enable=1;
            for(integer i=0;i<65536;i=i+1)begin
                wave_address=9'(i);image_address=16'(i);column=9'(i);clocks(3);
                expected_wave=source_value(32'(identity),0,{7'd0,9'(i)});
                expected_image=source_value(32'(identity),1,16'(i));
                expected_spectrum=source_value(32'(identity),2,{7'd0,9'(i)});
                if(wave_data!==expected_wave || image_hit!==expected_image[0] ||
                   {right_level,left_level}!==expected_spectrum[15:0])
                    $fatal(1,"last-good cache corruption identity=%0d index=%0d",identity,i);
            end
            render_enable=0;checks=checks+1;
        end
    endtask
    reg [255:0] saved,old_header;
    integer saved_commits;
    reg saved_bank;
    initial begin
        for(integer i=0;i<16384;i=i+1)memory[i]=0;
        clocks(4);rst_n=1;wait(initialized);write_frame();read_frame(1);check_cache(1,48000,1);
        // Reject mixed epoch before any DDR invalidation, and retain global.
        saved_commits=commits;analysis_epoch=9;write_frame();analysis_epoch=1;
        if(commits!=saved_commits || !unavailable || wdiagnostic!=4)$fatal(1,"mixed analysis epoch published");
        wave_epoch=9;write_frame();wave_epoch=1;if(wdiagnostic!=3)$fatal(1,"mixed wave epoch accepted");
        analysis_generation_offset=1;write_frame();analysis_generation_offset=0;
        if(wdiagnostic!=4)$fatal(1,"stale analysis local generation accepted");
        wave_generation_offset=1;write_frame();wave_generation_offset=0;
        if(wdiagnostic!=3)$fatal(1,"stale waveform local generation accepted");
        epoch=0;wave_epoch=0;analysis_epoch=0;write_frame();if(wdiagnostic!=1)$fatal(1,"epoch0 admitted");
        epoch=2;wave_epoch=2;analysis_epoch=2;rate=44100;cancel_generation=11;tag=2;
        write_frame();read_frame(1);check_cache(2,44100,2);
        // Corrupt each context/version position; reader completes with fault
        // and never publishes or overwrites its last-good local image.
        saved_bank=memory[slot(DISPLAY_CONTROL_WORD)][48];
        saved=memory[slot(DISPLAY_CONTROL_WORD)];memory[slot(DISPLAY_CONTROL_WORD)][39:32]=0;
        read_frame(0);if(!incompatible || diagnostic!=1)$fatal(1,"unselected minor accepted");
        memory[slot(DISPLAY_CONTROL_WORD)]=saved;check_cache(2,44100,2);
        for(integer d=0;d<4;d=d+1)begin
            saved=memory[slot((saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)+29'(d*16))];
            memory[slot((saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)+29'(d*16))][39:32]=0;
            read_frame(0);if(!incompatible || diagnostic!=1)$fatal(1,"descriptor unselected version accepted type=%0d",d);
            memory[slot((saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)+29'(d*16))]=saved;
            saved=memory[slot((saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)+29'(d*16+8))];
            memory[slot((saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)+29'(d*16+8))][223:192]=0;
            read_frame(0);if(diagnostic!=4)$fatal(1,"descriptor zero/mixed epoch accepted type=%0d",d);
            memory[slot((saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)+29'(d*16+8))]=saved;
        end
        saved=memory[slot(saved_bank ? DESC_BANK1_WORD+24:DESC_BANK0_WORD+24)];
        memory[slot(saved_bank ? DESC_BANK1_WORD+24:DESC_BANK0_WORD+24)][223:192]=3;
        read_frame(0);if(diagnostic!=4)$fatal(1,"descriptor epoch mismatch accepted");
        memory[slot(saved_bank ? DESC_BANK1_WORD+24:DESC_BANK0_WORD+24)]=saved;
        saved=memory[slot((saved_bank ? PAYLOAD_BANK1_WORD:PAYLOAD_BANK0_WORD)+EFFECT_META_OFFSET_WORD+8)];
        memory[slot((saved_bank ? PAYLOAD_BANK1_WORD:PAYLOAD_BANK0_WORD)+EFFECT_META_OFFSET_WORD+8)][191:160]=48000;
        read_frame(0);if(diagnostic!=5)$fatal(1,"late metadata rate mismatch accepted");
        memory[slot((saved_bank ? PAYLOAD_BANK1_WORD:PAYLOAD_BANK0_WORD)+EFFECT_META_OFFSET_WORD+8)]=saved;
        check_cache(2,44100,2);
        saved=memory[slot((saved_bank ? PAYLOAD_BANK1_WORD:PAYLOAD_BANK0_WORD)+EFFECT_META_OFFSET_WORD)];
        memory[slot((saved_bank ? PAYLOAD_BANK1_WORD:PAYLOAD_BANK0_WORD)+EFFECT_META_OFFSET_WORD)][223:201]=1;
        read_frame(0);if(diagnostic!=5)$fatal(1,"metadata reserved effect bits accepted");
        memory[slot((saved_bank ? PAYLOAD_BANK1_WORD:PAYLOAD_BANK0_WORD)+EFFECT_META_OFFSET_WORD)]=saved;
        check_cache(2,44100,2);
        mutate_final=1;read_frame(0);if(diagnostic!=6)$fatal(1,"torn final seqlock accepted");check_cache(2,44100,2);
        // Change physical identity while a writer beat is stalled: drain it
        // unchanged, abort the partial bank, leave last global and cache intact.
        saved_commits=commits;@(negedge clk);wstart=1;clocks(1);wstart=0;
        wait(writer.state==writer.WRITE);@(negedge clk);write_stall=1;clocks(2);
        epoch=3;wave_epoch=3;analysis_epoch=3;rate=48000;cancel_generation=12;tag=3;
        clocks(10);if(!wreq || wdone)$fatal(1,"abort withdrew held beat");write_stall=0;wait(wdone);clocks(2);
        if(commits!=saved_commits || aborts!=1 || !unavailable)$fatal(1,"partial switched window committed");
        check_cache(2,44100,2);
        // A reader copies bank A, pauses mid-payload, while two new frames reuse
        // A. Its final header check must discard the mixed work, retaining B.
        @(negedge clk);rstart=1;clocks(1);rstart=0;
        wait(reader.state==reader.STORE_PAYLOAD && reader.payload_kind==1);@(negedge clk);reader_stall=1;
        write_frame();tag=4;write_frame();reader_stall=0;wait(rdone);clocks(1);
        if(!rfault || diagnostic!=6)$fatal(1,"slow reader survived overwritten DDR bank");
        check_cache(2,44100,2);read_frame(1);check_cache(4,48000,3);
        // A new minor1 frame cannot contain descriptor rate zero/unsupported.
        saved_bank=memory[slot(DISPLAY_CONTROL_WORD)][48];
        saved=memory[slot(saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)];
        memory[slot(saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)][159:128]=32000;
        read_frame(0);if(diagnostic!=4)$fatal(1,"unsupported rate accepted");
        memory[slot(saved_bank ? DESC_BANK1_WORD:DESC_BANK0_WORD)]=saved;
        read_frame(1);check_cache(4,48000,3);
        // Once every RAM element has been exported, the sealed old snapshot
        // may finish its commit after a context change, with only its old tags.
        tag=5;@(negedge clk);wstart=1;clocks(1);wstart=0;
        wait(writer.state==writer.META);@(negedge clk);write_stall=1;
        rate=44100;epoch=4;wave_epoch=4;analysis_epoch=4;cancel_generation=13;tag=6;
        clocks(10);write_stall=0;wait(wdone);clocks(2);
        if(aborts!=1 || unavailable)$fatal(1,"sealed packet changed context/aborted after capture");
        tag=5;read_frame(1);check_cache(5,48000,3);
        tag=6;write_frame();read_frame(1);check_cache(6,44100,4);
        abort_final_payload(0);check_cache(6,44100,4);
        abort_final_payload(1);check_cache(6,44100,4);
        // Reset invalidates local publication and all DDR headers coherently.
        rst_n=0;clocks(4);rst_n=1;wait(initialized);clocks(2);
        if(rvalid || render_epoch!=0 || memory[slot(DISPLAY_CONTROL_WORD)]!=0)$fatal(1,"reset retained old publication");
        $display("PASS display_metadata_v11: checks=%0d writes=%0d commits=%0d reads=%0d rejected=%0d aborted=%0d first_reads=%0d local_banks=2 final_payload_aborts=2",checks,writes,commits,reads,rejections,aborts,first_reads);
        $finish;
    end
    initial begin #100000000;$fatal(1,"display metadata watchdog");end
endmodule
