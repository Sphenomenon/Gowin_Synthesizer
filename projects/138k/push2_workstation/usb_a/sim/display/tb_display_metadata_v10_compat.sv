`timescale 1ns/1ps
module tb_display_metadata_v10_compat;
    import display_data_layout_pkg::*;
    reg clk=0,rst_n=0,start=0,av=0;
    always #5 clk=!clk;
    integer cycles=0,beats=0,comparisons=0;
    reg [255:0] meta=256'h44495350_00000103_12345678_76543210_00000000_00000064_00000009_000000cb;
    wire busy,done,initialized,req,read_enable,ref_busy,ref_done,ref_initialized,ref_req,ref_read_enable;
    wire [28:0] addr,ref_addr;
    wire [255:0] data,ref_data;
    wire [1:0] kind,ref_kind;
    wire [15:0] index,ref_index;
    reg [31:0] read_data=0;
    reg [255:0] memory[0:16383];
    function automatic integer slot(input [28:0] a);
        if(a>=PAYLOAD_BANK1_WORD)slot=8192+((integer'(a)-integer'(PAYLOAD_BANK1_WORD))>>3);
        else if(a>=PAYLOAD_BANK0_WORD)slot=4096+((integer'(a)-integer'(PAYLOAD_BANK0_WORD))>>3);
        else slot=((integer'(a)-integer'(LEGACY_META_WORD))>>3);
    endfunction
    wire ready=cycles%11>2 && !(cycles>10000 && cycles<20000);
    display_data_writer writer(
        .clk,.rst_n,.enabled(rst_n),.start,.effect_meta(meta),.analysis_sequence(32'd200),
        .analysis_skipped(32'd11),.stereo_peaks(32'h12345678),.analysis_valid(av),.image_gain(3'd5),
        .source_context_valid_i(1'b0),.source_sample_rate_i(32'd0),.source_epoch_i(32'd0),.source_generation_i(32'd0),
        .waveform_context_valid_i(1'b0),.waveform_sample_rate_i(32'd0),.waveform_epoch_i(32'd0),.waveform_generation_i(32'd0),
        .analysis_context_valid_i(1'b0),.analysis_sample_rate_i(32'd0),.analysis_epoch_i(32'd0),.analysis_generation_i(32'd0),
        .context_rejected_o(),.context_aborted_o(),.context_unavailable_o(),.context_diagnostic_o(),
        .busy,.done,.initialized,.req_valid(req),.req_ready(ready),.req_addr(addr),.req_wdata(data),
        .read_enable,.read_kind(kind),.read_addr(index),.read_data);
    reference_display_data_writer reference_writer(
        .clk,.rst_n,.enabled(rst_n),.start,.effect_meta(meta),.analysis_sequence(32'd200),
        .analysis_skipped(32'd11),.stereo_peaks(32'h12345678),.analysis_valid(av),.image_gain(3'd5),
        .busy(ref_busy),.done(ref_done),.initialized(ref_initialized),.req_valid(ref_req),.req_ready(ready),
        .req_addr(ref_addr),.req_wdata(ref_data),.read_enable(ref_read_enable),.read_kind(ref_kind),.read_addr(ref_index),.read_data);
    // A minor0 caller that provides real context must explicitly reject 44.1.
    reg aware_start=0;
    wire aware_done,aware_rejected;
    wire [2:0] aware_diagnostic;
    integer aware_requests=0;
    wire aware_req;
    display_data_writer #(.CONTEXT_ENABLE(1)) context_aware_v0(
        .clk,.rst_n,.enabled(rst_n),.start(aware_start),.effect_meta(meta),.analysis_sequence(32'd200),
        .analysis_skipped(32'd11),.stereo_peaks(32'h12345678),.analysis_valid(1'b1),.image_gain(3'd5),
        .source_context_valid_i(1'b1),.source_sample_rate_i(32'd44100),.source_epoch_i(32'd2),.source_generation_i(32'd1),
        .waveform_context_valid_i(1'b1),.waveform_sample_rate_i(32'd44100),.waveform_epoch_i(32'd2),.waveform_generation_i(32'd1),
        .analysis_context_valid_i(1'b1),.analysis_sample_rate_i(32'd44100),.analysis_epoch_i(32'd2),.analysis_generation_i(32'd1),
        .context_rejected_o(aware_rejected),.context_aborted_o(),.context_unavailable_o(),.context_diagnostic_o(aware_diagnostic),
        .busy(),.done(aware_done),.initialized(),.req_valid(aware_req),.req_ready(1'b1),.req_addr(),.req_wdata(),
        .read_enable(),.read_kind(),.read_addr(),.read_data(32'd0));
    reg rstart=0,response=0,pending=0,render_enable=0;
    reg [255:0] response_data=0,pending_data=0;
    wire rdone,rvalid,rfault,rreq,incompatible;
    wire [28:0] raddr;
    wire [31:0] render_rate,render_epoch,wave_data,frame_sequence;
    wire [255:0] render_meta;
    wire image_hit;
    wire [7:0] left_level,right_level;
    display_data_reader reader(
        .clk,.rst_n,.enabled(rst_n),.start(rstart),.busy(),.done(rdone),.valid(rvalid),.fault(rfault),
        .req_valid(rreq),.req_ready(!pending),.req_addr(raddr),.rsp_valid(response),.rsp_data(response_data),
        .render_read_enable(render_enable),.render_wave_addr(9'd511),.render_image_addr(16'd65535),.render_spectrum_column(9'd511),
        .render_wave_data(wave_data),.render_image_hit(image_hit),.render_spectrum_left(left_level),.render_spectrum_right(right_level),
        .render_meta,.render_analysis_sequence(),.render_analysis_skipped(),.render_stereo_peaks(),.render_image_gain(),
        .render_analysis_valid(),.render_frame_sequence(frame_sequence),.render_sample_rate_o(render_rate),.render_epoch_o(render_epoch),
        .render_generation_o(),.render_context_changed_o(),.incompatible_o(incompatible),.diagnostic_code_o());
    always @(posedge clk)begin
        cycles=cycles+1;response<=0;
        if(rst_n)begin
            if({busy,done,initialized,req,addr,data,read_enable,kind,index}!==
               {ref_busy,ref_done,ref_initialized,ref_req,ref_addr,ref_data,ref_read_enable,ref_kind,ref_index})
                $fatal(1,"default minor0 changed cycle/bytes at cycle %0d",cycles);
            comparisons=comparisons+1;
            if(read_enable)read_data<=kind==0 ? 32'h10000000+{16'd0,index} : kind==1 ? {31'd0,index[0]} : {16'd0,index};
            if(req && ready)begin beats=beats+1;memory[slot(addr)]=data;end
            if(aware_req)aware_requests=aware_requests+1;
            if(rreq && !pending)begin pending<=1;pending_data=memory[slot(raddr)];end
            if(pending)begin response<=1;response_data<=pending_data;pending<=0;end
        end
    end
    task tick(input integer n);begin repeat(n)@(negedge clk);end endtask
    initial begin
        for(integer i=0;i<16384;i=i+1)memory[i]=0;
        tick(4);rst_n=1;wait(initialized);tick(2);
        for(integer frame=0;frame<3;frame=frame+1)begin
            av=frame!=0;start=1;tick(1);start=0;tick(100);meta[194:192]=3'(frame+4);
            wait(done);tick(2);
        end
        aware_start=1;tick(1);aware_start=0;wait(aware_done);tick(1);
        if(aware_diagnostic!=2 || aware_requests!=3 || beats!=1098)$fatal(1,"minor0 context refusal/default beat count");
        rstart=1;tick(1);rstart=0;wait(rdone);render_enable=1;tick(4);
        if(!rvalid || rfault || render_rate!=48000 || render_epoch!=0 || frame_sequence!=3 ||
           wave_data!=32'h100001ff || !image_hit || {right_level,left_level}!=16'h01ff)
            $fatal(1,"default reader rejected exact minor0 writer");
        // An unselected minor1 header must never enter the legacy cache copy.
        memory[slot(DISPLAY_CONTROL_WORD)][39:32]=1;
        rstart=1;tick(1);rstart=0;wait(incompatible && rfault);tick(100);
        if(!rvalid || rdone || reader.state==reader.IDLE || render_rate!=48000 || render_epoch!=0 || frame_sequence!=3 ||
           wave_data!=32'h100001ff || !image_hit || {right_level,left_level}!=16'h01ff || render_meta[255:224]!=32'h44495350)
            $fatal(1,"default reader consumed unselected minor1/changed last local image");
        $display("PASS display_metadata_v10_compat: compared_cycles=%0d default_beats=%0d context44_rejected=1 reader_unselected_minor1_rejected=1",comparisons,beats);
        $finish;
    end
    initial begin #20000000;$fatal(1,"minor0 compatibility watchdog");end
endmodule
