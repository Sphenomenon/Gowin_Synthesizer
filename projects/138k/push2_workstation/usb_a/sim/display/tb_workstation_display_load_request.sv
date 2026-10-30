`timescale 1ns/1ps
// Exercise the owning scheduler against the real writer, real minor1 reader
// and an ordered DDR model. Only the producer's immutable export contract is
// driven directly so races can land on exact acceptance/completion edges.
module tb_workstation_display_load_request;
    import display_data_layout_pkg::*;
    reg clk=0,rst_n=0,enabled=0;
    always #5 clk=!clk;
    reg context_valid=1,source_ready=0;
    reg [31:0] context_rate=48000,context_epoch=1,context_generation=1;
    reg raster_busy=0,raster_start=0,write_stall=0,reader_stall=0,corrupt_global=0;
    wire allowed,current_image,summary,wbusy,wdone,initialized,wreq,rbusy,rdone,rvalid,rfault,rreq;
    wire [28:0] waddr,raddr;
    wire [255:0] wdata;
    reg response=0,response_pending=0;
    reg [255:0] response_data=0,pending_data=0;
    workstation_display_runtime dut(
        .source_clk_i(clk),.source_reset_ni(rst_n),.clk_i(clk),.rst_ni(rst_n),.enabled_i(enabled),
        .frame_valid_i(1'b0),.frame_44k1_i(1'b0),.frame_error_i(1'b0),.observation_trusted_i(1'b1),
        .frame_epoch_i(32'd1),.frame_sequence_i(32'd0),.frame_pcm_i(32'd0),.trigger_reference_i(32'd0),
        .active_voices_i(32'd0),.status_i(32'd0),.effect_mask_i(3'd0),.effect_order_i(6'b10_01_00),
        .observation_drop_o(),.memory_status_i(32'd0),.raster_busy_i(raster_busy),.raster_start_i(raster_start),
        .raster_allowed_o(allowed),.current_image_o(current_image),.summary_publish_o(summary),
        .writer_busy_o(wbusy),.writer_done_o(wdone),.writer_initialized_o(initialized),
        .writer_req_o(wreq),.writer_ready_i(!write_stall),.writer_address_o(waddr),.writer_data_o(wdata),
        .reader_busy_o(rbusy),.reader_done_o(rdone),.reader_valid_o(rvalid),.reader_fault_o(rfault),
        .reader_req_o(rreq),.reader_ready_i(!response_pending && !reader_stall),.reader_address_o(raddr),
        .reader_response_i(response),.reader_data_i(response_data),.render_read_enable_i(1'b0),
        .render_wave_address_i(9'd0),.render_spectrum_column_i(9'd0),.render_image_address_i(16'd0),
        .render_wave_data_o(),.render_image_hit_o(),.render_spectrum_left_o(),.render_spectrum_right_o(),
        .render_meta_o(),.render_analysis_sequence_o(),.render_analysis_skipped_o(),.render_stereo_peaks_o(),
        .render_image_gain_o(),.render_analysis_valid_o(),.render_frame_sequence_o(),
        .render_sample_rate_o(),.render_epoch_o(),.writer_diagnostic_o(),.reader_diagnostic_o());
    reg [255:0] memory[0:16383];
    function automatic integer slot(input [28:0] a);
        if(a>=PAYLOAD_BANK1_WORD)slot=8192+((integer'(a)-integer'(PAYLOAD_BANK1_WORD))>>3);
        else if(a>=PAYLOAD_BANK0_WORD)slot=4096+((integer'(a)-integer'(PAYLOAD_BANK0_WORD))>>3);
        else slot=((integer'(a)-integer'(LEGACY_META_WORD))>>3);
    endfunction
    reg export_started=0;
    integer summaries=0,loads=0,exports=0,read_beats=0,checks=0;
    integer total_loads=0,total_reads=0,total_summaries=0,cases=0;
    always @(posedge clk)begin
        response<=0;export_started<=rst_n && dut.export_start;
        if(!rst_n)begin response_pending<=0;summaries=0;loads=0;exports=0;read_beats=0;end
        else begin
            if(wreq && !write_stall)memory[slot(waddr)]=wdata;
            if(rreq && !response_pending && !reader_stall)begin
                response_pending<=1;
                pending_data=memory[slot(raddr)];
                if(corrupt_global && raddr==DISPLAY_CONTROL_WORD)pending_data[0]=!pending_data[0];
                read_beats=read_beats+1;total_reads=total_reads+1;
            end
            if(response_pending)begin response<=1;response_data<=pending_data;response_pending<=0;end
            if(dut.export_start)exports=exports+1;
            if(dut.load_start)begin
                if(rbusy || dut.loading || raster_busy || raster_start || !enabled)$fatal(1,"load accepted without idle lease");
                loads=loads+1;total_loads=total_loads+1;
            end
            if(summary)begin
                if(!enabled || !current_image || !allowed || !context_valid)$fatal(1,"ineligible summary published");
                summaries=summaries+1;total_summaries=total_summaries+1;
            end
        end
    end
    always @(negedge clk)if(export_started)source_ready=0;
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task check(input reg condition,input string message);begin
        checks=checks+1;if(!condition)$fatal(1,"%s",message);
    end endtask
    task reset_case;begin
        @(negedge clk);rst_n=0;enabled=0;source_ready=0;raster_busy=0;raster_start=0;
        write_stall=0;reader_stall=0;corrupt_global=0;
        context_valid=1;context_rate=48000;context_epoch=1;context_generation=1;
        clocks(3);rst_n=1;enabled=1;clocks(4);cases=cases+1;
    end endtask
    task pending_request;begin
        raster_busy=1;source_ready=1;
        wait(dut.load_request);@(negedge clk);
        check(dut.pending && !rbusy && loads==0,"request did not wait for raster lease");
    end endtask
    task finish_read;begin wait(rdone);clocks(3);check(!rbusy && !dut.loading,"reader completion did not clear flight");end endtask
    task good_image;begin
        source_ready=1;wait(summary);clocks(3);
        check(summaries==1 && current_image && allowed && loads==1,"valid current image did not publish exactly once");
    end endtask
    integer before_summaries;
    initial begin
        // The producer algorithm is covered by the full runtime/atomic-context
        // regression. Here its stable context and source RAM contract feed the
        // unchanged real writer and reader without a second FFT-sized fixture.
        force dut.source_valid=context_valid;
        force dut.source_rate=context_rate;force dut.source_epoch=context_epoch;
        force dut.source_generation=context_generation;force dut.source_ready=source_ready;
        force dut.wave_valid=context_valid;force dut.wave_rate=context_rate;
        force dut.wave_epoch=context_epoch;force dut.wave_generation=context_generation;
        force dut.analysis_context=context_valid;force dut.analysis_rate=context_rate;
        force dut.analysis_epoch=context_epoch;force dut.analysis_generation=context_generation;
        force dut.analysis_valid=1'b1;force dut.analysis_sequence=32'd20;
        force dut.analysis_skipped=32'd0;force dut.peaks=32'h10002000;force dut.gain=3'd0;
        force dut.metadata={32'h44495350,32'd0,32'd0,32'd0,32'd0,32'd10,32'd0,32'd0};
        force dut.read_data=32'h00110011;
        for(integer i=0;i<16384;i=i+1)memory[i]=0;
        reset_case();source_ready=1;
        wait(dut.pending);#1;
        check(!dut.load_start && !rbusy,"qualification bypassed the request register");
        @(posedge clk);#1;check(dut.load_start && !rbusy,"registered request did not become eligible one cycle later");
        @(posedge clk);#1;check(rbusy && dut.loading && !dut.pending && !dut.load_start,"reader acceptance duplicated or lost request");
        finish_read();check(summaries==1 && loads==1,"normal request did not publish once");
        context_valid=0;#1;check(!current_image && !allowed,"context revocation was delayed with the request");

        reset_case();pending_request();clocks(4);
        check(!dut.load_start && !rbusy,"busy raster accepted load request");
        raster_busy=0;raster_start=1;clocks(3);
        check(!dut.load_start && !rbusy,"raster start pulse accepted load request");
        raster_start=0;finish_read();check(loads==1 && summaries==1,"lease release duplicated or lost request");

        // Invalidating while the registered request is blocked cancels it.
        reset_case();pending_request();context_valid=0;context_generation=2;
        clocks(2);raster_busy=0;clocks(3);
        check(!dut.pending && !dut.load_request && !rbusy && loads==0 && summaries==0,"blocked obsolete request survived cancellation");

        // A break arriving precisely at acceptance may launch one old private
        // copy, but its completion must be discarded for every context tag.
        for(integer field=0;field<4;field=field+1)begin
            reset_case();pending_request();
            case(field)
                0:context_rate=44100;
                1:context_epoch=2;
                2:context_generation=2;
                3:begin context_valid=0;context_generation=2;end
            endcase
            raster_busy=0;#1;check(dut.load_start,"acceptance-edge race did not exercise already registered request");
            @(posedge clk);#1;check(rbusy && loads==1,"acceptance-edge obsolete copy missing");
            if(field==3)begin @(negedge clk);context_valid=1;end
            finish_read();check(loads==1 && summaries==0 && !current_image && !allowed,"obsolete context reached publication");
        end

        reset_case();pending_request();enabled=0;raster_busy=0;#1;
        check(!dut.load_start && !summary && !allowed,"disabled registered request accepted");
        clocks(2);enabled=1;clocks(3);
        check(!dut.pending && !dut.loading && !dut.load_request && !dut.export_live && loads==0 && summaries==0,"request revived after re-enable");

        reset_case();reader_stall=1;pending_request();raster_busy=0;
        wait(rbusy);@(negedge clk);enabled=0;clocks(2);
        check(!dut.loading && !dut.export_live && !current_image,"disable did not cancel reader flight");
        enabled=1;reader_stall=0;finish_read();
        check(summaries==0 && !current_image && !allowed && loads==1,"disabled old reader result published after re-enable");

        // Disable at a stalled real writer commit; re-enable and drain the
        // unchanged sealed DDR transaction without resurrecting its request.
        reset_case();source_ready=1;
        wait(dut.writer.state==dut.writer.COMMIT_GLOBAL);@(negedge clk);write_stall=1;
        enabled=0;clocks(2);enabled=1;write_stall=0;
        wait(wdone);clocks(5);
        check(loads==0 && summaries==0 && !dut.pending && !dut.export_live,"disabled writer tail revived a load");

        reset_case();good_image();before_summaries=summaries;
        corrupt_global=1;source_ready=1;wait(rdone);clocks(3);
        check(rfault && rvalid && current_image && allowed && summaries==before_summaries && loads==2,
            "failed same-context reload replaced or revoked previous image");

        // A completion without an accepted loading token cannot emit another
        // publication, even if the previous real reader cache remains valid.
        corrupt_global=0;force dut.reader_fault_o=1'b0;force dut.reader_done_o=1'b1;
        clocks(1);release dut.reader_done_o;release dut.reader_fault_o;clocks(2);
        check(summaries==before_summaries,"completion without accepted request published");

        reset_case();source_ready=1;wait(summary);@(negedge clk);enabled=0;#1;
        check(!summary && !allowed,"summary was not revoked immediately by disable");
        clocks(2);enabled=1;clocks(2);
        check(!current_image && !allowed,"disabled image eligibility survived re-enable");
        check(cases==12 && total_loads>=10 && total_reads>1000,"load race coverage incomplete");
        $display("PASS display_load_request: cases=%0d checks=%0d loads=%0d reads=%0d summaries=%0d registered_latency=1 context_races=4 stale_drain=1 disable_cancel=3 raster_gates=2 fault_retains_image=1 unsolicited_done_rejected=1",cases,checks,total_loads,total_reads,total_summaries);
        $finish;
    end
    initial begin #200000000;$fatal(1,"load request watchdog case=%0d writer=%0d reader=%0d pending=%0b live=%0b ready=%0b",cases,dut.writer.state,dut.reader.state,dut.pending,dut.export_live,source_ready);end
endmodule
