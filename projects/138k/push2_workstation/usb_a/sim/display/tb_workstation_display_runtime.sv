`timescale 1ns/1ps
module tb_workstation_display_runtime;
    import display_data_layout_pkg::*;
    reg source_clk=0,clk=0,rst_n=0,source_rst_n=0;
    reg source_clock_run=1,memory_clock_run=1;
    always #10 if(source_clock_run)source_clk=!source_clk;
    always #5 if(memory_clock_run)clk=!clk;
    reg trusted=1,rate44=0,frame_error=0,burst=0,pause_frames=0,frame_valid=0;
    reg [31:0] epoch=1,sequence_number=0,pcm=0;
    integer ticks=0;
    function automatic integer left_pcm(input integer n);left_pcm=$rtoi(12000.0*$sin(6.283185307179586*32.0*n/2048.0));endfunction
    function automatic integer right_pcm(input integer n);right_pcm=$rtoi(8000.0*$cos(6.283185307179586*64.0*n/2048.0));endfunction
    function automatic [31:0] mono(input integer n);mono=32'(left_pcm(n)+right_pcm(n))<<15;endfunction
    wire [31:0] reference_data=32'h10000000+sequence_number;
    wire [31:0] voices=32'h20000000+sequence_number,status=32'h30000000+sequence_number;
    wire [2:0] effect_mask=sequence_number[2:0];
    wire [5:0] effect_order=sequence_number[0] ? 6'b00_01_10:6'b10_01_00;
    always @(negedge source_clk)begin
        if(frame_valid)sequence_number=sequence_number+1'b1;
        frame_valid=0;
        if(rst_n && source_rst_n)begin
            ticks=ticks+1;
            if(!pause_frames && (burst || ticks%16==0))begin
                frame_valid=1;pcm={16'(left_pcm(integer'(sequence_number%64))),16'(right_pcm(integer'(sequence_number%64)))};
            end
        end
    end
    reg raster_busy=0,raster_start=0,write_stall=0,reader_stall=0;
    wire allowed,current_image,summary,wbusy,wdone,initialized,wreq,rbusy,rdone,rvalid,rfault,rreq;
    wire [28:0] waddr,raddr;
    wire [255:0] wdata;
    wire [31:0] drops,render_rate,render_epoch,render_sequence,wave_data;
    wire [7:0] left_level,right_level;
    wire image_hit;
    wire [2:0] gain,wdiagnostic;
    wire [3:0] rdiagnostic;
    reg [8:0] wave_address=0,column=0;
    reg [15:0] image_address=0;
    reg render_enable=0,response=0,pending_response=0;
    reg [255:0] response_data=0,pending_data=0;
    workstation_display_runtime dut(
        .source_clk_i(source_clk),.source_reset_ni(source_rst_n),.clk_i(clk),.rst_ni(rst_n),.enabled_i(rst_n),
        .frame_valid_i(frame_valid),.frame_44k1_i(rate44),.frame_error_i(frame_error),.observation_trusted_i(trusted),
        .frame_epoch_i(epoch),.frame_sequence_i(sequence_number),.frame_pcm_i(pcm),.trigger_reference_i(reference_data),
        .active_voices_i(voices),.status_i(status),.effect_mask_i(effect_mask),.effect_order_i(effect_order),
        .observation_drop_o(drops),.memory_status_i(32'hcb),.raster_busy_i(raster_busy),.raster_start_i(raster_start),
        .raster_allowed_o(allowed),.current_image_o(current_image),.summary_publish_o(summary),
        .writer_busy_o(wbusy),.writer_done_o(wdone),.writer_initialized_o(initialized),
        .writer_req_o(wreq),.writer_ready_i(!write_stall),.writer_address_o(waddr),.writer_data_o(wdata),
        .reader_busy_o(rbusy),.reader_done_o(rdone),.reader_valid_o(rvalid),.reader_fault_o(rfault),
        .reader_req_o(rreq),.reader_ready_i(!pending_response && !reader_stall),.reader_address_o(raddr),
        .reader_response_i(response),.reader_data_i(response_data),.render_read_enable_i(render_enable),
        .render_wave_address_i(wave_address),.render_spectrum_column_i(column),.render_image_address_i(image_address),
        .render_wave_data_o(wave_data),.render_image_hit_o(image_hit),.render_spectrum_left_o(left_level),
        .render_spectrum_right_o(right_level),.render_meta_o(),.render_analysis_sequence_o(),.render_analysis_skipped_o(),
        .render_stereo_peaks_o(),.render_image_gain_o(gain),.render_analysis_valid_o(),.render_frame_sequence_o(render_sequence),
        .render_sample_rate_o(render_rate),.render_epoch_o(render_epoch),.writer_diagnostic_o(wdiagnostic),.reader_diagnostic_o(rdiagnostic));
    reg [255:0] memory[0:16383];
    function automatic integer slot(input [28:0] a);
        if(a>=PAYLOAD_BANK1_WORD)slot=8192+((integer'(a)-integer'(PAYLOAD_BANK1_WORD))>>3);
        else if(a>=PAYLOAD_BANK0_WORD)slot=4096+((integer'(a)-integer'(PAYLOAD_BANK0_WORD))>>3);
        else slot=((integer'(a)-integer'(LEGACY_META_WORD))>>3);
    endfunction
    integer publications=0,commits=0,tuple_checks=0,checked_wave=0,checked_xy=0,checked_columns=0;
    integer drop_cycle_checks=0,drop_revocations=0,drop_completion_races=0;
    integer reset_prior_drops=0;
    reg [31:0] previous_binary_drop=0;
    // Retain the former binary implementation only as a cycle-exact oracle.
    // Every loss must revoke public state before the next destination edge.
    always @(posedge clk or negedge dut.memory_reset_n)
        if(!dut.memory_reset_n)previous_binary_drop<=0;else previous_binary_drop<=dut.destination_drop;
    always @(negedge clk)if(rst_n)begin
        if(dut.observation_loss!==(dut.destination_drop!=previous_binary_drop))
            $fatal(1,"Gray drop detection added a publication aperture");
        drop_cycle_checks=drop_cycle_checks+1;
        if(dut.observation_loss)begin
            drop_revocations=drop_revocations+1;
            if(current_image || allowed || summary || dut.source_ready || dut.export_start)
                $fatal(1,"drop failed same-cycle publication/export revocation");
        end
    end
    integer export_phase=-1,loaded_phase=-1;
    reg stalled=0;
    reg [28:0] held_address;
    reg [255:0] held_data;
    always @(posedge clk)begin
        response<=0;
        if(rst_n)begin
            if(stalled && (!wreq || waddr!==held_address || wdata!==held_data))$fatal(1,"runtime withdrew stalled DDR write");
            stalled=wreq && write_stall;held_address=waddr;held_data=wdata;
            if(wreq && !write_stall)begin
                memory[slot(waddr)]=wdata;
                if(waddr==DISPLAY_CONTROL_WORD && wdata!=0)commits=commits+1;
            end
            if(rreq && !pending_response && !reader_stall)begin
                pending_response<=1;pending_data=memory[slot(raddr)];
            end
            if(pending_response)begin response<=1;response_data<=pending_data;pending_response<=0;end
            if(rbusy && raster_busy)$fatal(1,"reader copied/flipped local cache during raster");
            if(summary)begin
                if(!current_image || !allowed || render_epoch!=epoch || render_rate!=(rate44 ? 44100:48000))
                    $fatal(1,"stale context published to raster/summary");
                publications=publications+1;
            end
            if(dut.tuple_valid)begin
                if(dut.tuple_pcm!=={16'(left_pcm(integer'(dut.tuple_sequence%64))),16'(right_pcm(integer'(dut.tuple_sequence%64)))} ||
                   dut.tuple_reference!==32'h10000000+dut.tuple_sequence || dut.tuple_voices!==32'h20000000+dut.tuple_sequence ||
                   dut.tuple_status!==32'h30000000+dut.tuple_sequence || dut.tuple_mask!==dut.tuple_sequence[2:0] ||
                   dut.tuple_order!==(dut.tuple_sequence[0] ? 6'b00_01_10:6'b10_01_00))$fatal(1,"torn 204bit physical/control tuple CDC");
                tuple_checks=tuple_checks+1;
            end
            if(dut.export_start)begin
                export_phase=-1;
                for(integer n=0;n<64;n=n+1)if(dut.producer.aligner.trace_samples[0]===mono(n) &&
                    dut.producer.aligner.trace_samples[1]===mono(n+1))export_phase=n;
                if(export_phase<0)$fatal(1,"runtime wave is not unfiltered physical PCM");
            end
            if(dut.load_start)loaded_phase=export_phase;
        end
    end
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task verify_current(input integer actual_rate,input integer actual_epoch);
        integer phase,px,py,peak_l,peak_r,max_l,max_r;
        reg expected_pixel;
        reg [15:0] expected_columns[0:511];
        begin
            wait(summary);@(negedge clk);raster_busy=1;phase=loaded_phase;
            if(!current_image || render_rate!=32'(actual_rate) || render_epoch!=32'(actual_epoch))$fatal(1,"wrong runtime context");
            peak_l=0;peak_r=0;max_l=0;max_r=0;
            for(integer bin=2;bin<=853;bin=bin+1)begin
                if(integer'(dut.producer.analysis.levels_left[bin])>max_l)begin max_l=integer'(dut.producer.analysis.levels_left[bin]);peak_l=bin;end
                if(integer'(dut.producer.analysis.levels_right[bin])>max_r)begin max_r=integer'(dut.producer.analysis.levels_right[bin]);peak_r=bin;end
            end
            if(peak_l!=32 || peak_r!=64)$fatal(1,"runtime actual FFT peak drift");
            for(integer col=0;col<512;col=col+1)
                expected_columns[col]={dut.producer.analysis.display_right[dut.producer.analysis.read_bank*512+col],dut.producer.analysis.display_left[dut.producer.analysis.read_bank*512+col]};
            render_enable=1;
            for(integer i=0;i<65536;i=i+1)begin
                wave_address=9'(i);image_address=16'(i);column=9'(i);clocks(3);
                if(i<512)begin
                    if(wave_data!==mono((phase+i)%64))$fatal(1,"runtime waveform corruption index=%0d",i);
                    if({right_level,left_level}!==expected_columns[i])$fatal(1,"runtime FFT column corruption");
                    checked_wave=checked_wave+1;checked_columns=checked_columns+1;
                end
                expected_pixel=0;
                for(integer n=0;n<64;n=n+1)begin
                    px=128+(left_pcm(n) >>> (9-integer'(gain)));py=128-(right_pcm(n) >>> (9-integer'(gain)));
                    if(px<0)px=0;if(px>255)px=255;if(py<0)py=0;if(py>255)py=255;
                    if(i==py*256+px)expected_pixel=1;
                end
                if(image_hit!==expected_pixel)$fatal(1,"runtime XY bitmap corruption index=%0d",i);
                checked_xy=checked_xy+1;
            end
            render_enable=0;
            $display("RUNTIME_RATE rate=%0d epoch=%0d left_bin=%0d right_bin=%0d",actual_rate,actual_epoch,peak_l,peak_r);
        end
    endtask
    integer before_publications,before_commits;
    reg [31:0] completion_drop_binary,completion_drop_gray;
    initial begin
        for(integer i=0;i<16384;i=i+1)memory[i]=0;
        clocks(4);rst_n=1;source_rst_n=1;clocks(30);if(allowed || current_image)$fatal(1,"raster admitted without first validated image");
        verify_current(48000,1);
        // A second export can complete in the background, but reader must wait
        // for the currently rendering cache lease to finish.
        wait(dut.pending);clocks(20);if(rbusy || rreq)$fatal(1,"pending reader stole active raster cache");
        @(negedge source_clk);rate44=1;epoch=2;
        wait(!current_image);clocks(20);if(allowed || dut.pending)$fatal(1,"pending old context survived switch");
        @(negedge clk);raster_busy=0;verify_current(44100,2);
        // Loss after every source RAM read, while COMMIT_GLOBAL is stalled:
        // the sealed old DDR packet may drain but cannot publish a new raster.
        @(negedge source_clk);trusted=0;wait(!current_image);clocks(10);raster_busy=0;
        @(negedge source_clk);trusted=1;
        wait(dut.writer.state==dut.writer.COMMIT_GLOBAL);@(negedge clk);write_stall=1;
        before_publications=publications;before_commits=commits;
        @(negedge source_clk);trusted=0;clocks(20);
        if(current_image || allowed || !wreq)$fatal(1,"tail cancellation did not revoke publication");
        write_stall=0;wait(wdone);clocks(20);
        if(publications!=before_publications || commits!=before_commits+1 || dut.pending || rbusy)
            $fatal(1,"sealed stale writer result reached reader/raster");
        @(negedge source_clk);trusted=1;wait(summary);clocks(3);
        // Revoke a context during the real reader's partial local copy. The
        // read may drain coherently, but no stale summary/raster may start.
        wait(dut.reader.state==dut.reader.STORE_PAYLOAD && dut.reader.payload_kind==1);
        @(negedge clk);reader_stall=1;before_publications=publications;
        @(negedge source_clk);trusted=0;clocks(20);reader_stall=0;
        wait(rdone);clocks(5);
        if(publications!=before_publications || current_image || allowed)$fatal(1,"reader pending stale image published");
        @(negedge source_clk);trusted=1;wait(summary);clocks(3);
        // Deliver a synchronized counter change on the exact edge that would
        // publish a completed reader image. This destination-side fixture
        // isolates the publication race; real mailbox overflow follows below.
        wait(!rdone);wait(rdone);@(negedge clk);pause_frames=1;
        if(!dut.loading || !dut.export_current)$fatal(1,"drop/publication race not armed");
        before_publications=publications;
        completion_drop_binary=dut.destination_drop+1'b1;
        completion_drop_gray=completion_drop_binary^(completion_drop_binary>>1);
        force dut.drops.sync_value=completion_drop_gray;
        clocks(2);
        if(publications!=before_publications || dut.publish || current_image || allowed || dut.pending)
            $fatal(1,"drop coincident with reader completion published stale image");
        release dut.drops.sync_value;pause_frames=0;drop_completion_races=drop_completion_races+1;
        wait(summary);clocks(3);
        // Force mailbox overflow without changing the owner epoch. A final
        // drop is observed through its counter even without a later packet.
        before_publications=publications;@(negedge source_clk);burst=1;
        repeat(80)@(negedge source_clk);burst=0;pause_frames=1;
        clocks(20);if(drops==0 || current_image || allowed)$fatal(1,"CDC loss did not flush same-epoch context");
        pause_frames=0;
        wait(summary);clocks(3);
        @(negedge source_clk);frame_error=1;
        wait(dut.tuple_valid && dut.tuple_error);@(negedge source_clk);frame_error=0;
        clocks(10);if(current_image || allowed)$fatal(1,"error PCM kept current image");
        wait(summary);clocks(3);
        // A source-only reset revokes both owners asynchronously. Neither
        // owner may release while its own clock is stopped, and restarting
        // one clock cannot release the other owner's cache or request state.
        pause_frames=1;raster_busy=1;wait(!wbusy && !rbusy);clocks(3);
        @(negedge clk);memory_clock_run=0;
        @(negedge source_clk);source_clock_run=0;
        #2;reset_prior_drops=integer'(drops);source_rst_n=0;#1;
        if(dut.memory_reset_n || dut.source_reset_n || current_image || allowed || summary || wreq || rreq)
            $fatal(1,"source reset did not asynchronously revoke stopped display owners memory=%b source=%b image=%b allowed=%b summary=%b wreq=%b rreq=%b",dut.memory_reset_n,dut.source_reset_n,current_image,allowed,summary,wreq,rreq);
        #2;source_rst_n=1;#80;
        if(dut.memory_reset_n || dut.source_reset_n || initialized || wreq || rreq)
            $fatal(1,"stopped clock released display owner");
        source_clock_run=1;repeat(3)@(negedge source_clk);
        if(!dut.source_reset_n || dut.memory_reset_n || initialized || wreq || rreq)
            $fatal(1,"source release escaped into stopped DDR owner");
        memory_clock_run=1;clocks(2);
        if(dut.memory_reset_n)$fatal(1,"DDR owner released before three local edges");
        clocks(1);if(!dut.memory_reset_n)$fatal(1,"DDR owner did not release after three local edges");
        pause_frames=0;raster_busy=0;wait(summary);clocks(3);
        before_publications=publications;@(negedge source_clk);epoch=0;
        clocks(1000);if(current_image || allowed || publications!=before_publications)$fatal(1,"zero epoch reached raster");
        if(checked_wave!=1024 || checked_xy!=131072 || checked_columns!=1024 || publications<6 || tuple_checks<10000 ||
           drop_cycle_checks<10000 || drop_revocations<1 || drop_completion_races!=1)
            $fatal(1,"runtime composition coverage");
        $display("PASS workstation_display_runtime: publications=%0d commits=%0d tuple_checks=%0d waveform=%0d xy=%0d fft_columns=%0d cdc_drops=%0d tail_cancel=1 reader_cancel=1 idle_cache_lease=1 gray_drop_cycle_checks=%0d drop_revocations=%0d drop_completion_races=%0d reset_local_release=1",publications,commits,tuple_checks,checked_wave,checked_xy,checked_columns,reset_prior_drops+integer'(drops),drop_cycle_checks,drop_revocations,drop_completion_races);
        $finish;
    end
    initial begin #200000000;$fatal(1,"runtime display watchdog publications=%0d writer=%0d reader=%0d",publications,dut.writer.state,dut.reader.state);end
endmodule
