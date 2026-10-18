`timescale 1ns/1ps
module tb_shared_display;
    import display_data_layout_pkg::*;
    reg clk=0,source_clk=0,reset_n=0;
    always #5 clk=~clk;
    always #10 source_clk=~source_clk;
    reg sample_valid=0;
    reg [31:0] pcm=0,sample_data=0;
    reg [31:0] ticks=0;
    always @(posedge source_clk)begin
        ticks<=ticks+1;
        sample_valid<=ticks[4:0]==0;
        if(ticks[4:0]==0)begin
            pcm<={16'(ticks>>5),16'(-(ticks>>6))};
            sample_data<=32'($signed(16'(ticks>>5))+$signed(16'(-(ticks>>6))))<<15;
        end
    end
    reg start=0,ref_start=0;
    wire ready,render_busy,render_done,pv;reg pr=1;
    wire [63:0] pixels;
    wire [255:0] meta,export_meta;
    wire ds,dw,dd,db,initialized,re,req; wire [1:0] kind;wire [15:0] addr;
    wire [31:0] rd,aseq,askip,peaks;wire av;wire[2:0] gain;
    wire [28:0] wa;wire [255:0] wd;
    wire load_req,load_ready,load_done,load_valid,load_fault,load_busy;
    wire [28:0]load_addr;reg load_response=0;reg [255:0]load_response_data=0;
    wire cache_read,cache_image_hit,cache_analysis_valid;wire [8:0]cache_wave_addr,cache_spectrum_column;
    wire [15:0]cache_image_addr;wire [31:0]cache_wave_data,cache_aseq,cache_askip,cache_peaks,cache_frame_sequence;
    wire [7:0]cache_spectrum_left,cache_spectrum_right;wire [2:0]cache_gain;wire [255:0]cache_meta;
    wire source_req,source_ready,frame_write_ready;
    wire [28:0] source_addr;
    wire [255:0] source_data;
    reg [4:0] frame_write_index=16;
    integer frame_write_accepted=0;
    always @(posedge clk)begin
        if(!reset_n)frame_write_index<=16;
        else if(dd)frame_write_index<=0;
        else if(frame_write_ready)frame_write_index<=frame_write_index+1;
    end
    reg wrdy=1;
    reg [31:0] frame_count=0;
    reg [2:0] mask=3;reg [5:0] order=6'b10_00_01;
    feedback_renderer #(.ENABLE_ANALYSIS(1),.SHARED_EXPORT(1),.SHARED_RENDER(1),.SHARED_WAVE_ZERO_BITS(15)) render(
        .clk,.rst_n(reset_n),.start,.frame_ready(ready),.busy(render_busy),.frame_done(render_done),
        .pixel_valid(pv),.pixel_ready(pr),.pixel_data(pixels),.display_meta(meta),.shared_export_meta(export_meta),.source_clk,.source_reset_n(reset_n),
        .sample_data,.sample_valid,.output_pcm(pcm),.trigger_reference(32'd0),.active_voices(32'h17),.status_data(32'd0),
        .effect_mask(mask),.effect_order(order),.memory_status(32'hcb),.underruns(32'd0),.frame_count,
        .shared_start(ds),.shared_done(dd),.shared_read_enable(re),.shared_read_kind(kind),.shared_read_addr(addr),.shared_read_data(rd),
        .shared_analysis_sequence(aseq),.shared_analysis_skipped(askip),.shared_analysis_valid(av),.shared_image_gain(gain),.shared_stereo_peaks(peaks),
        .shared_render_read_enable(cache_read),.shared_render_wave_addr(cache_wave_addr),.shared_render_image_addr(cache_image_addr),.shared_render_spectrum_column(cache_spectrum_column),
        .shared_render_wave_data(cache_wave_data),.shared_render_image_hit(cache_image_hit),.shared_render_spectrum_left(cache_spectrum_left),.shared_render_spectrum_right(cache_spectrum_right),
        .shared_render_meta(cache_meta),.shared_render_analysis_sequence(cache_aseq),.shared_render_analysis_skipped(cache_askip),
        .shared_render_stereo_peaks(cache_peaks),.shared_render_image_gain(cache_gain),.shared_render_analysis_valid(cache_analysis_valid));
    display_data_writer writer(.clk,.rst_n(reset_n),.enabled(reset_n),.start(ds),.effect_meta(export_meta),
        .analysis_sequence(aseq),.analysis_skipped(askip),.stereo_peaks(peaks),.analysis_valid(av),.image_gain(gain),
        .busy(db),.done(dw),.initialized,.req_valid(source_req),.req_ready(source_ready),.req_addr(source_addr),.req_wdata(source_data),
        .read_enable(re),.read_kind(kind),.read_addr(addr),.read_data(rd));
    display_data_reader reader(.clk,.rst_n(reset_n),.enabled(reset_n),.start(dw),.busy(load_busy),.done(dd),.valid(load_valid),.fault(load_fault),
        .req_valid(load_req),.req_ready(load_ready),.req_addr(load_addr),.rsp_valid(load_response),.rsp_data(load_response_data),
        .render_read_enable(cache_read),.render_wave_addr(cache_wave_addr),.render_image_addr(cache_image_addr),.render_spectrum_column(cache_spectrum_column),
        .render_wave_data(cache_wave_data),.render_image_hit(cache_image_hit),.render_spectrum_left(cache_spectrum_left),.render_spectrum_right(cache_spectrum_right),
        .render_meta(cache_meta),.render_analysis_sequence(cache_aseq),.render_analysis_skipped(cache_askip),.render_stereo_peaks(cache_peaks),
        .render_image_gain(cache_gain),.render_analysis_valid(cache_analysis_valid),.render_frame_sequence(cache_frame_sequence));
    display_write_bridge bridge(.clk,.rst_n(reset_n),
        .shared_valid(source_req),.shared_addr(source_addr),.shared_data(source_data),.shared_ready(source_ready),
        .frame_valid(frame_write_index<16),.frame_addr({21'd0,frame_write_index,3'd0}),
        .frame_data({8{27'd0,frame_write_index}}),.frame_ready(frame_write_ready),
        .req_valid(req),.req_addr(wa),.req_data(wd),.req_ready(wrdy));
    wire ref_ready,ref_pv,ref_done;wire[63:0]ref_pixels;
    p10_feedback_renderer #(.ENABLE_ANALYSIS(1)) reference(
        .clk,.rst_n(reset_n),.start(ref_start),.frame_ready(ref_ready),.busy(),.frame_done(ref_done),
        .pixel_valid(ref_pv),.pixel_ready(1'b1),.pixel_data(ref_pixels),.display_meta(),.source_clk,.source_reset_n(reset_n),
        .sample_data,.sample_valid,.output_pcm(pcm),.trigger_reference(32'd0),.active_voices(32'h17),.status_data(32'd0),
        .effect_mask(mask),.effect_order(order),.memory_status(32'hcb),.underruns(32'd0),.frame_count(32'd0));
    reg [63:0] reference_frame[0:1036799];
    integer reference_count=0,pixel_count=0,frame_pixels=0;
    integer frames=0,writes=0,payloads=0,descriptors=0,commits=0;
    integer cycles=0,hold_cycles=0,i,j,offset,slot;
    reg [28:0] ddr_address[0:1699];reg [255:0]ddr_data[0:1699],pending_read_data;integer ddr_count=0,read_delay=0,k;
    reg read_pending=0;
    function automatic [255:0] ddr_lookup(input [28:0] lookup_address);
        integer n;
        begin
            ddr_lookup=0;
            for(n=0;n<1700;n=n+1)if(n<ddr_count && ddr_address[n]==lookup_address)ddr_lookup=ddr_data[n];
        end
    endfunction
    assign load_ready=reset_n && !read_pending && cycles%7!=0;
    reg [31:0] wave[0:511];reg image_bits[0:65535];reg[15:0] columns[0:511];
    reg [255:0] expected_meta;
    reg [31:0] expected_aseq,expected_askip,expected_peaks;reg expected_valid;
    reg [2:0] expected_gain;
    reg [28:0] current_base,current_desc,current_header;
    reg [255:0] bank_headers[0:1],bank_payload[0:1][0:353],old_header;
    reg [28:0] stalled_addr;reg [255:0]stalled_data;reg stalled=0;
    reg invalidated=0,bank_committed=0;
    reg [255:0] global_control=0;
    reg [31:0] prior_seq=0;
    // Deterministic ordinary backpressure plus one 25 ms DDR stall.
    always @(negedge clk) begin
        cycles=cycles+1;
        if(hold_cycles>0)begin wrdy=0;hold_cycles=hold_cycles-1;end
        else wrdy=(cycles%11)>2;
        pr=(cycles%13)>1;
    end
    always @(posedge clk)if(reset_n)begin
        load_response<=0;
        if(load_req && load_ready)begin read_pending<=1;read_delay<=2;pending_read_data=ddr_lookup(load_addr);end
        if(read_pending)begin
            if(read_delay==0)begin load_response<=1;load_response_data<=pending_read_data;read_pending<=0;end
            else read_delay<=read_delay-1;
        end
        if(load_fault)$fatal(1,"HDMI reader rejected writer packet");
        if(ref_pv)begin reference_frame[reference_count]=ref_pixels;reference_count=reference_count+1;end
        if(pv && pr)begin
            if(frames==1)begin
                if(pixel_count>=reference_count || pixels!==reference_frame[pixel_count])
                    $fatal(1,"P10 pixel mismatch at %0d got=%h expected=%h",pixel_count,pixels,reference_frame[pixel_count]);
                pixel_count=pixel_count+1;
            end
            frame_pixels=frame_pixels+1;
        end
        if(render_done)begin
            if(frame_pixels!=1036800)$fatal(1,"raster length %0d",frame_pixels);
            frame_pixels=0;
        end
        if(stalled && (!req || wa!==stalled_addr || wd!==stalled_data))$fatal(1,"unstable stalled request");
        stalled=req && !wrdy;stalled_addr=wa;stalled_data=wd;
        if(writer.state==writer.SNAPSHOT)begin
            frames=frames+1;writes=0;payloads=0;descriptors=0;invalidated=0;bank_committed=0;
            current_base=writer.bank ? PAYLOAD_BANK1_WORD : PAYLOAD_BANK0_WORD;
            current_desc=writer.bank ? DESC_BANK1_WORD : DESC_BANK0_WORD;
            current_header=writer.bank ? BANK1_HEADER_WORD : BANK0_HEADER_WORD;
            expected_meta=export_meta;expected_aseq=aseq;expected_askip=askip;expected_valid=av;
            expected_peaks=peaks;expected_gain=gain;
            for(i=0;i<512;i=i+1)begin
                wave[i]=render.u_align.trace_samples[i];
                columns[i]=av ? {render.g_analysis.u_analysis.display_right[render.g_analysis.u_analysis.read_bank*512+i],render.g_analysis.u_analysis.display_left[render.g_analysis.u_analysis.read_bank*512+i]} : 0;
            end
            for(i=0;i<65536;i=i+1)image_bits[i]=av && render.g_analysis.u_analysis.image_pixels[render.g_analysis.u_analysis.read_bank*65536+i];
        end
        if(req && wrdy)begin
            if(wa>=DISPLAY_CONTROL_WORD)begin ddr_address[ddr_count]=wa;ddr_data[ddr_count]=wd;ddr_count=ddr_count+1;end
            if(wa<128)begin
                if(wa!==29'((frame_write_accepted%16)*8) || wd!=={8{32'(frame_write_accepted%16)}})$fatal(1,"frame writer bridge ordering/data");
                frame_write_accepted=frame_write_accepted+1;
            end else if(!initialized)begin
                if(wd!==0)$fatal(1,"reset must invalidate publication");
                if(wa==DISPLAY_CONTROL_WORD)global_control=wd;
                if(wa==BANK0_HEADER_WORD)bank_headers[0]=wd;
                if(wa==BANK1_HEADER_WORD)bank_headers[1]=wd;
            end else begin
                writes=writes+1;
                if(wa==current_header)begin
                    if(wd[96])begin
                        if(writes!=1)$fatal(1,"invalidation must precede payload");
                        invalidated=1;
                    end else begin
                        if(payloads!=354 || descriptors!=8)$fatal(1,"early bank commit");
                        bank_committed=1;
                    end
                    bank_headers[writer.bank]=wd;
                end else if(wa>=current_base && wa<current_base+29'hb10)begin
                    if(!invalidated || !bank_headers[writer.bank][96])$fatal(1,"overwrite bank without odd header");
                    offset=wa-current_base;payloads=payloads+1;
                    bank_payload[writer.bank][offset/8]=wd;
                    if(offset<512)begin
                        for(j=0;j<8;j=j+1)if(wd[j*32+:32]!==wave[offset+j])$fatal(1,"wave index %0d",offset+j);
                    end else if(offset<2560)begin
                        for(j=0;j<256;j=j+1)if(wd[j]!==image_bits[(offset-512)*32+j])$fatal(1,"bitmap index %0d",(offset-512)*32+j);
                    end else if(offset<2816)begin
                        for(j=0;j<16;j=j+1)if(wd[j*16+:16]!==columns[(offset-2560)*2+j])$fatal(1,"spectrum column %0d",(offset-2560)*2+j);
                    end else if(offset==2816)begin
                        if(wd!==expected_meta)$fatal(1,"metadata changed during export");
                    end else if(wd!=={64'd0,32'd48000,expected_valid?32'hf:32'h9,29'd0,expected_gain,expected_peaks,expected_askip,expected_aseq})$fatal(1,"analysis metadata");
                end else if(wa>=current_desc && wa<current_desc+64)begin
                    descriptors=descriptors+1;slot=(wa-current_desc)/16;
                    if(!wa[3])begin
                        if(wd[31:0]!==BLOCK_MAGIC || wd[47:32]!==16'h0100 || wd[55:48]!==slot+1 || wd[63:56]!==slot+1)$fatal(1,"descriptor version/type");
                        if(wd[95:64]!==frames || wd[159:128]!==(slot==3 ? 0 : 48000))$fatal(1,"descriptor seq/rate");
                        if(wd[127:96]!==(slot==0?expected_meta[95:64]:slot==3?frames:expected_aseq))$fatal(1,"descriptor source sequence");
                        if(wd[255:224]!==((slot==0 || slot==3 || expected_valid)?1:0))$fatal(1,"descriptor valid");
                        if(wd[223:192]!==(slot==0?512:slot==3?16:!expected_valid?0:slot==1?65536:512))$fatal(1,"descriptor length");
                        if(wd[191:160]!==(slot==0?32'h0d010200:slot==1?32'h800:slot==2?32'h20800:0))$fatal(1,"window/trigger");
                    end else begin
                        if(wd[31:0]!==current_base+(slot==0?0:slot==1?512:slot==2?2560:2816))$fatal(1,"payload pointer");
                        if(wd[63:32]!==(slot==0?512:slot==1?2048:slot==2?256:16))$fatal(1,"payload words");
                        if(wd[95:64]!==(slot==0?expected_meta[63:32]:slot==3?0:expected_askip))$fatal(1,"descriptor skipped samples");
                        if(wd[127:96]!==(slot==1?{29'd0,expected_gain}:0))$fatal(1,"descriptor gain");
                        if(wd[159:128]!==(slot==1?32'h01000100:slot==2?32'h03550002:0))$fatal(1,"descriptor aux0");
                        if(wd[191:160]!==(slot==2?224:0) || wd[223:192]!==0)$fatal(1,"descriptor aux1/reserved");
                        if(wd[255:224]!=={3'd0,current_header})$fatal(1,"header pointer");
                    end
                end else if(wa==DISPLAY_CONTROL_WORD)begin
                    if(!bank_committed || writes!=365 || wd!==bank_headers[writer.bank])$fatal(1,"commit ordering/count %0d",writes);
                    if(wd[31:0]!==DISPLAY_MAGIC || wd[47:32]!==16'h0100 || wd[95:64]!==prior_seq+1 || wd[127:96]!==frames*2)$fatal(1,"control packet");
                    if(wd[159:128]!=={3'd0,current_desc})$fatal(1,"descriptor pointer");
                    if(wd[63:48]!=={8'd4,7'd0,writer.bank} || wd[191:160]!==(expected_valid?32'hf:32'h9) || wd[223:192]!==expected_meta[63:32] || wd[255:224]!==expected_askip)$fatal(1,"control bank/flags/skipped");
                    global_control=wd;prior_seq=wd[95:64];commits=commits+1;
                end else $fatal(1,"unexpected DDR address %h",wa);
            end
        end
    end
    initial begin
        repeat(5)@(negedge clk);reset_n=1;
        wait(ready && ref_ready && initialized && render.g_analysis.u_analysis.ready && reference.g_analysis.u_analysis.ready);
        @(negedge clk);start=1;ref_start=1;
        @(negedge clk);start=0;ref_start=0;
        wait(render_done);@(negedge clk);
        if(pixel_count!=1036800)$fatal(1,"pixel compare count");
        // A slow consumer starts copying bank 1. On its reuse it must discard
        // the copy after observing an odd/changed generation, never display it.
        old_header=bank_headers[1];
        wait(ready);@(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(writer.state==writer.WRITE);@(negedge clk);hold_cycles=2500000;
        // Change live controls during DDR stall; published effect state is frozen.
        mask=7;order=6'b00_01_10;
        wait(render_done);@(negedge clk);
        wait(ready);@(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(writer.state==writer.READ);@(negedge clk);
        if(bank_headers[1]===old_header || !bank_headers[1][96])$fatal(1,"slow reader missed bank reuse");
        wait(render_done);@(negedge clk);
        if(commits!=3 || frame_write_accepted!=48)$fatal(1,"commit/bridge count");
        $display("PASS shared DDR HDMI source: 3 frames, every payload/descriptor, backpressure/25ms stall, coherent DDR reload, 1036800 P10 pixel pairs identical");
        // Startup may render a waveform before the first FFT: mark analysis invalid.
        reset_n=0;frames=0;prior_seq=0;commits=0;repeat(5)@(negedge clk);reset_n=1;
        wait(ready && initialized);@(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(dd);@(negedge clk);
        if(expected_valid)$fatal(1,"startup fixture expected no FFT front");
        if(writer.valid_flags!==32'h9)$fatal(1,"startup analysis valid flag");
        $display("PASS startup invalid analysis: zero bitmap/columns, lengths zero; waveform and metadata valid");
        $finish;
    end
    initial begin #300000000;$fatal(1,"simulation timeout");end
endmodule
