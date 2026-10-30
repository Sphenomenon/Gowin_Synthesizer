`timescale 1ns/1ps
// Real minor1 writer -> functional DDR -> reader -> five complete rasters.
// Golden renderers are the byte-sealed pre-fix source with a module-only rename.
module shared_analysis_raster_case #(
    parameter integer LOCAL_ANALYSIS=0, RENDER_ANALYSIS=0, EXPLICIT_RENDER=0, REFERENCE=0
)(
    input wire clk,rst_n,start,sample_valid,pixel_ready,
    input wire [31:0] sample_data,wave_data,
    input wire image_hit,analysis_valid,
    input wire [7:0] spectrum_left,spectrum_right,
    input wire [255:0] metadata,
    input wire [31:0] peaks,analysis_sequence,analysis_skipped,
    input wire [2:0] gain,
    output wire frame_ready,busy,pixel_valid,frame_done,read_enable,
    output wire [63:0] pixel_data,
    output wire [8:0] wave_address,spectrum_column,
    output wire [15:0] image_address
);
`define RASTER_PORTS \
    .clk(clk),.rst_n(rst_n),.start(start),.frame_ready(frame_ready),.busy(busy),.frame_done(frame_done), \
    .pixel_valid(pixel_valid),.pixel_ready(pixel_ready),.pixel_data(pixel_data),.display_meta(),.shared_export_meta(), \
    .source_clk(clk),.source_reset_n(rst_n),.sample_data(sample_data),.sample_valid(sample_valid),.output_pcm(32'd0), \
    .trigger_reference(32'd0),.active_voices(32'd0),.status_data(32'd0),.effect_mask(3'd0),.effect_order(6'b10_01_00), \
    .memory_status(32'd0),.underruns(32'd0),.frame_count(32'd0),.shared_done(1'b0), \
    .shared_read_enable(1'b0),.shared_read_kind(2'd0),.shared_read_addr(16'd0),.shared_read_data(),.shared_start(), \
    .shared_analysis_sequence(),.shared_analysis_skipped(),.shared_analysis_valid(),.shared_image_gain(),.shared_stereo_peaks(), \
    .shared_render_read_enable(read_enable),.shared_render_wave_addr(wave_address),.shared_render_image_addr(image_address), \
    .shared_render_spectrum_column(spectrum_column),.shared_render_wave_data(wave_data),.shared_render_image_hit(image_hit), \
    .shared_render_spectrum_left(spectrum_left),.shared_render_spectrum_right(spectrum_right),.shared_render_meta(metadata), \
    .shared_render_analysis_sequence(analysis_sequence),.shared_render_analysis_skipped(analysis_skipped), \
    .shared_render_stereo_peaks(peaks),.shared_render_image_gain(gain),.shared_render_analysis_valid(analysis_valid)
    generate if(REFERENCE!=0)begin : golden
        reference_feedback_renderer #(.ENABLE_ANALYSIS(LOCAL_ANALYSIS),.SHARED_RENDER(1),.SHARED_EXPORT(0)) renderer(`RASTER_PORTS);
    end else if(EXPLICIT_RENDER!=0)begin : explicit_render
        feedback_renderer #(.ENABLE_ANALYSIS(LOCAL_ANALYSIS),.RENDER_ANALYSIS(RENDER_ANALYSIS),.SHARED_RENDER(1),.SHARED_EXPORT(0)) renderer(`RASTER_PORTS);
    end else begin : inherited_render
        feedback_renderer #(.ENABLE_ANALYSIS(LOCAL_ANALYSIS),.SHARED_RENDER(1),.SHARED_EXPORT(0)) renderer(`RASTER_PORTS);
    end endgenerate
`undef RASTER_PORTS
endmodule

module tb_workstation_shared_analysis_pixels;
    import display_data_layout_pkg::*;
    reg clk=0,rst_n=0,wstart=0,rstart=0,raster_start=0;
    always #5 clk=!clk;
    integer cycles=0,samples=0;
    reg sample_valid=0;
    reg signed [31:0] sample_data=0;
    always @(negedge clk)begin
        cycles=cycles+1;sample_valid=rst_n && cycles%8==0;
        if(sample_valid)begin sample_data=32'(samples%64-32)<<<24;samples=samples+1;end
    end
    wire wbusy,wdone,initialized,wreq,rbusy,rdone,rvalid,rfault,rreq;
    wire [28:0] waddr,raddr;
    wire [255:0] wdata;
    wire source_read;
    wire [1:0] source_kind;
    wire [15:0] source_address;
    wire wready=cycles%7!=0;
    reg [31:0] source_data;
    function automatic [15:0] fixture_spectrum(input [8:0] column);
        case(column)
            100:fixture_spectrum={8'd112,8'd224};
            200:fixture_spectrum={8'd200,8'd32};
            default:fixture_spectrum=0;
        endcase
    endfunction
    always @*case(source_kind)
        0:source_data=0;
        1:source_data={31'd0,source_address==16'h2828};
        default:source_data={16'd0,fixture_spectrum(source_address[8:0])};
    endcase
    display_data_writer #(.METADATA_MINOR(1)) writer(
        .clk(clk),.rst_n(rst_n),.enabled(rst_n),.start(wstart),
        .effect_meta({32'h44495350,32'h00000024,32'h08000000,32'd0,32'd0,32'd23,32'd0,32'd0}),
        .analysis_sequence(32'd51),.analysis_skipped(32'd0),.stereo_peaks(32'h40002000),.analysis_valid(1'b1),.image_gain(3'd2),
        .source_context_valid_i(1'b1),.source_sample_rate_i(32'd48000),.source_epoch_i(32'd7),.source_generation_i(32'd9),
        .waveform_context_valid_i(1'b1),.waveform_sample_rate_i(32'd48000),.waveform_epoch_i(32'd7),.waveform_generation_i(32'd9),
        .analysis_context_valid_i(1'b1),.analysis_sample_rate_i(32'd48000),.analysis_epoch_i(32'd7),.analysis_generation_i(32'd9),
        .context_rejected_o(),.context_aborted_o(),.context_unavailable_o(),.context_diagnostic_o(),
        .busy(wbusy),.done(wdone),.initialized(initialized),.req_valid(wreq),.req_ready(wready),.req_addr(waddr),.req_wdata(wdata),
        .read_enable(source_read),.read_kind(source_kind),.read_addr(source_address),.read_data(source_data));
    reg response=0,pending=0;
    reg [255:0] response_data=0,pending_data=0;
    wire rready=!pending && cycles%5!=0;
    reg [255:0] memory[0:16383];
    function automatic integer slot(input [28:0] address);
        if(address>=PAYLOAD_BANK1_WORD)slot=8192+((integer'(address)-integer'(PAYLOAD_BANK1_WORD))>>3);
        else if(address>=PAYLOAD_BANK0_WORD)slot=4096+((integer'(address)-integer'(PAYLOAD_BANK0_WORD))>>3);
        else slot=(integer'(address)-integer'(LEGACY_META_WORD))>>3;
    endfunction
    integer writes=0,reads=0;
    always @(posedge clk)begin
        response<=0;
        if(rst_n)begin
            if(wreq && wready)begin memory[slot(waddr)]=wdata;writes=writes+1;end
            if(rreq && rready)begin pending<=1;pending_data<=memory[slot(raddr)];reads=reads+1;end
            if(pending)begin response<=1;response_data<=pending_data;pending<=0;end
        end
    end
    wire [31:0] wave_data,peaks,analysis_sequence,analysis_skipped,render_rate,render_epoch;
    wire image_hit,analysis_valid;
    wire [7:0] spectrum_left,spectrum_right;
    wire [2:0] gain;
    wire [255:0] metadata;
    wire [4:0] frame_ready,busy,pixel_valid,frame_done,read_enable;
    wire [63:0] pixels[0:4];
    wire [8:0] wave_address[0:4],spectrum_column[0:4];
    wire [15:0] image_address[0:4];
    reg probe=1,probe_enable=0;
    reg [8:0] probe_column=0;
    reg [15:0] probe_image=0;
    wire shared_read=probe ? probe_enable:read_enable[0];
    display_data_reader #(.METADATA_MINOR(1)) reader(
        .clk(clk),.rst_n(rst_n),.enabled(rst_n),.start(rstart),.busy(rbusy),.done(rdone),.valid(rvalid),.fault(rfault),
        .req_valid(rreq),.req_ready(rready),.req_addr(raddr),.rsp_valid(response),.rsp_data(response_data),
        .render_read_enable(shared_read),.render_wave_addr(wave_address[0]),
        .render_image_addr(probe ? probe_image:image_address[0]),.render_spectrum_column(probe ? probe_column:spectrum_column[0]),
        .render_wave_data(wave_data),.render_image_hit(image_hit),.render_spectrum_left(spectrum_left),.render_spectrum_right(spectrum_right),
        .render_meta(metadata),.render_analysis_sequence(analysis_sequence),.render_analysis_skipped(analysis_skipped),
        .render_stereo_peaks(peaks),.render_image_gain(gain),.render_analysis_valid(analysis_valid),.render_frame_sequence(),
        .render_sample_rate_o(render_rate),.render_epoch_o(render_epoch),.render_generation_o(),.render_context_changed_o(),
        .incompatible_o(),.diagnostic_code_o());
    wire pixel_ready=cycles%11!=0 && cycles%17!=0;
    generate for(genvar index=0;index<5;index=index+1)begin : rasters
        // 0 fixed native; 1 inherited disabled; 2 old disabled;
        // 3 old enabled; 4 inherited enabled. All use the same real local cache.
        shared_analysis_raster_case #(.LOCAL_ANALYSIS(index>=3 ? 1:0),.RENDER_ANALYSIS(1),
            .EXPLICIT_RENDER(index==0 ? 1:0),.REFERENCE(index==2 || index==3 ? 1:0)) raster(
            .clk(clk),.rst_n(rst_n),.start(raster_start),.sample_valid(sample_valid),.pixel_ready(pixel_ready),
            .sample_data(sample_data),.wave_data(wave_data),.image_hit(image_hit),.analysis_valid(analysis_valid),
            .spectrum_left(spectrum_left),.spectrum_right(spectrum_right),.metadata(metadata),.peaks(peaks),
            .analysis_sequence(analysis_sequence),.analysis_skipped(analysis_skipped),.gain(gain),
            .frame_ready(frame_ready[index]),.busy(busy[index]),.pixel_valid(pixel_valid[index]),.frame_done(frame_done[index]),
            .read_enable(read_enable[index]),.pixel_data(pixels[index]),.wave_address(wave_address[index]),
            .spectrum_column(spectrum_column[index]),.image_address(image_address[index]));
    end endgenerate
    task automatic clocks(input integer count);repeat(count)@(negedge clk);endtask
    integer checked_columns=0,checked_xy=0,beats=0,known_pixels=0,negative_differences=0,stalls=0;
    integer px,py;
    reg [31:0] expected;
    reg known;
    reg [63:0] stalled_pixels[0:4];
    reg was_stalled=0;
    function automatic [31:0] pixel_expect(input integer x,y);
        if((x==264 && y==650) || (x==1328 && y==304) || (x==1408 && y==790))pixel_expect=32'h003cdbab;
        else if((x==264 && y==700) || (x==464 && y==780))pixel_expect=32'h00a8d5bd;
        else if((x==464 && y==650) || (x==1312 && y==822))pixel_expect=32'h00f1c05a;
        else if((x==1332 && y==304))pixel_expect=32'h000b1420;
        else pixel_expect=32'h00263a4f;
    endfunction
    function automatic bit pixel_known(input integer x,y);
        pixel_known=(x==264 && (y==650 || y==700)) || (x==464 && (y==650 || y==780)) ||
            ((x==1328 || x==1332) && y==304) || (x==1408 && y==790) || (x==1312 && y==822) ||
            (x==1536 && y==790) || (x==1408 && y==822);
    endfunction
    always @(posedge clk)if(rst_n && !probe)begin
        if(pixel_valid!={5{pixel_valid[0]}} || read_enable!={5{read_enable[0]}})$fatal(1,"raster mode scheduling differs");
        for(integer mode=1;mode<5;mode=mode+1)
            if(read_enable[0] && (wave_address[mode]!==wave_address[0] || spectrum_column[mode]!==spectrum_column[0] || image_address[mode]!==image_address[0]))
                $fatal(1,"mode cache address differs");
        if(was_stalled)for(integer mode=0;mode<5;mode=mode+1)
            if(!pixel_valid[mode] || pixels[mode]!==stalled_pixels[mode])$fatal(1,"stalled pixel changed");
        was_stalled=pixel_valid[0] && !pixel_ready;
        if(was_stalled)begin stalls=stalls+1;for(integer mode=0;mode<5;mode=mode+1)stalled_pixels[mode]=pixels[mode];end
        if(pixel_valid[0] && pixel_ready)begin
            if(pixels[0]!==pixels[3] || pixels[4]!==pixels[3])$fatal(1,"analysis page or enabled default compatibility differs at beat %0d",beats);
            if(pixels[1]!==pixels[2])$fatal(1,"disabled default compatibility differs at beat %0d",beats);
            px=(beats%960)*2;py=beats/960;
            for(integer lane=0;lane<2;lane=lane+1)begin
                known=pixel_known(px+lane,py);expected=pixel_expect(px+lane,py);
                if(known)begin
                    if(pixels[0][lane*32+:32]!==expected)$fatal(1,"known pixel (%0d,%0d) got %h want %h",px+lane,py,pixels[0][lane*32+:32],expected);
                    known_pixels=known_pixels+1;
                    if(pixels[1][lane*32+:32]!==expected)negative_differences=negative_differences+1;
                end
            end
            beats=beats+1;
        end
    end
    initial begin
        clocks(5);rst_n=1;wait(initialized);clocks(2);wstart=1;clocks(1);wstart=0;wait(wdone);clocks(2);
        rstart=1;clocks(1);rstart=0;wait(rdone);clocks(3);
        if(!rvalid || rfault || !analysis_valid || peaks!==32'h40002000 || analysis_sequence!==51 || gain!==2 || render_rate!==48000 || render_epoch!==7)
            $fatal(1,"minor1 reader did not publish fixture metadata");
        probe_enable=1;
        for(integer column=0;column<512;column=column+1)begin
            probe_column=9'(column);clocks(3);
            if({spectrum_right,spectrum_left}!==fixture_spectrum(9'(column)))$fatal(1,"spectrum cache mismatch %0d",column);
            checked_columns=checked_columns+1;
        end
        for(integer address=0;address<65536;address=address+1)begin
            probe_image=16'(address);clocks(3);
            if(image_hit!==(address==32'h2828))$fatal(1,"XY cache mismatch %0d",address);
            checked_xy=checked_xy+1;
        end
        probe_enable=0;wait(&frame_ready);clocks(2);probe=0;raster_start=1;clocks(1);raster_start=0;
        wait(&frame_done);clocks(2);
        if(beats!=1036800 || known_pixels!=10 || negative_differences<7 || stalls<10000 || checked_columns!=512 || checked_xy!=65536)
            $fatal(1,"pixel coverage beats=%0d known=%0d negative=%0d stalls=%0d",beats,known_pixels,negative_differences,stalls);
        $display("PASS workstation_shared_analysis_pixels: beats=%0d pixels=%0d known=%0d negative=%0d stalls=%0d spectrum=%0d xy=%0d writes=%0d reads=%0d default0=1 default1=1 native_no_local_fft=1",beats,beats*2,known_pixels,negative_differences,stalls,checked_columns,checked_xy,writes,reads);
        $finish;
    end
    initial begin #50000000;$fatal(1,"shared analysis pixels watchdog beats=%0d writer=%0d reader=%0d",beats,writer.state,reader.state);end
endmodule
