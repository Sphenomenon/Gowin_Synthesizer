`timescale 1ns/1ps
// Actual shared/frame writers, registered bridge and existing DDR arbiter.
// Native DDR accepts commands; periodic 120-beat line reads exercise scan priority.
// 2200 pixel clocks / 148.5 MHz = 1481.48 UI clocks per 1080p line.
module tb_display_write_path;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire start,shared_write_done,initialized,shared_busy,sv,sr,fv,fr,bv,br,frame_pending;
    wire load_req,load_ready,load_response,load_busy,load_done,load_valid,load_fault;
    wire [28:0] sa,fa,ba,app_addr,load_addr;
    wire [255:0] sd,fd,bd,app_data;
    wire [31:0] rendered,app_mask;
    wire [255:0] load_meta;wire [31:0] load_aseq,load_askip,load_peaks,load_frame_sequence;
    wire [2:0]load_gain;wire load_analysis_valid;
    wire [2:0] app_cmd;
    wire app_en,app_wren,app_wend,scan_ready,scan_response,fault;
    wire read_enable;wire [1:0]read_kind;wire[15:0]read_addr;
    reg producing=0;reg[20:0] pixel_index=0;
    wire pixel_ready;
    reg exporting=0;
    wire pixel_valid=producing && !exporting;
    wire render_done=pixel_valid && pixel_ready && pixel_index==1036799;
    integer cycles=0,start_cycle=0,writes=0,shared_writes=0,shared_reads=0,pixel_beats=0;
    integer scan_slot=0,starts=0,meta_stall=0;
    wire write_accept=!(bv && ba==29'h200000 && meta_stall<2000);
    reg scan_valid=0,app_response=0;
    reg [255:0] app_read_data=0;
    reg global_committed=0;
    reg [28:0] memory_address[0:399];
    reg [255:0] memory_data[0:399];
    integer memory_count=0;
    function automatic [255:0] memory_lookup(input [28:0] address);
        integer k;
        begin
            memory_lookup=0;
            for(k=0;k<400;k=k+1)if(k<memory_count && memory_address[k]==address)memory_lookup=memory_data[k];
        end
    endfunction
    always @(posedge clk)begin
        cycles<=cycles+1;
        app_response<=app_en && app_cmd==1;
        if(app_en && app_cmd==1)app_read_data<=memory_lookup(app_addr);
        if(bv && ba==29'h200000 && !write_accept)meta_stall<=meta_stall+1;
        if(start)begin
            starts=starts+1;
            if(starts!=1)$fatal(1,"new raster started before the old P5 commit/swap");
            producing<=1;exporting<=1;pixel_index<=0;start_cycle<=cycles;
        end
        if(load_done)exporting<=0;
        if(pixel_valid && pixel_ready)begin
            pixel_index<=pixel_index+1;
            if(render_done)producing<=0;
        end
        if(app_en && app_wren)begin
            writes=writes+1;
            if(app_addr>=29'h200008)begin
                shared_writes=shared_writes+1;
                memory_address[memory_count]=app_addr;memory_data[memory_count]=app_data;memory_count=memory_count+1;
                if(app_addr==29'h200008 && app_data[31:0]==32'h44535032)global_committed=1;
            end else if(app_addr==29'h200000)begin
                if(pixel_beats!=129600)$fatal(1,"P5 commit before final pixels");
            end else begin
                if(!global_committed)$fatal(1,"pixels precede shared publication");
                if(app_addr!==29'h100000+pixel_beats*8 || app_data!=={16{16'hffff}})$fatal(1,"frame payload ordering/data");
                pixel_beats=pixel_beats+1;
            end
        end
        if(app_en && !app_wren && app_addr>=29'h200008)shared_reads=shared_reads+1;
        if(fault)$fatal(1,"arbiter read tagging fault");
        if(load_fault)$fatal(1,"coherent display reload rejected writer packet");
        if(frame_pending)begin
            if(writes!=129969 || shared_writes!=368 || shared_reads!=365 || rendered!=1)$fatal(1,"write/read/commit count %0d %0d %0d",writes,shared_writes,shared_reads);
            if(cycles-start_cycle>=1666667)$fatal(1,"write path exceeds a 60 Hz frame in this native-interface model: %0d cycles",cycles-start_cycle);
            if(!load_valid || load_frame_sequence!=1 || load_aseq!=1 || load_meta!={32'h44495350,224'd0})$fatal(1,"reader did not publish the written frame");
            $display("PASS integrated DDR write/read path: %0d cycles (%0d us); 365 shared writes + 365 coherent reads + framebuffer/P5 writes, scan arbitration/tags intact",cycles-start_cycle,(cycles-start_cycle)/100);
            $finish;
        end
    end
    always @(negedge clk)begin
        scan_slot=(scan_slot+1)%1481;
        scan_valid=rst_n && scan_slot<120;
    end
    display_data_writer shared_writer(.clk,.rst_n,.enabled(rst_n),.start,
        .effect_meta({32'h44495350,224'd0}),.analysis_sequence(32'd1),.analysis_skipped(32'd0),
        .stereo_peaks(32'd0),.analysis_valid(1'b1),.image_gain(3'd0),.busy(shared_busy),.done(shared_write_done),.initialized,
        .req_valid(sv),.req_ready(sr),.req_addr(sa),.req_wdata(sd),.read_enable,.read_kind,.read_addr,.read_data(32'd0));
    display_data_reader reader(.clk,.rst_n,.enabled(rst_n),.start(shared_write_done),
        .busy(load_busy),.done(load_done),.valid(load_valid),.fault(load_fault),
        .req_valid(load_req),.req_ready(load_ready),.req_addr(load_addr),.rsp_valid(load_response),.rsp_data(app_read_data),
        .render_read_enable(1'b0),.render_wave_addr(9'd0),.render_image_addr(16'd0),.render_spectrum_column(9'd0),
        .render_wave_data(),.render_image_hit(),.render_spectrum_left(),.render_spectrum_right(),
        .render_meta(load_meta),.render_analysis_sequence(load_aseq),.render_analysis_skipped(load_askip),
        .render_stereo_peaks(load_peaks),.render_image_gain(load_gain),.render_analysis_valid(load_analysis_valid),
        .render_frame_sequence(load_frame_sequence));
    ddr_frame_writer frame_writer(.clk,.rst_n,.enabled(rst_n),.front_bank(1'b0),.frame_swap(1'b0),
        .renderer_ready(initialized && !fv),.renderer_done(render_done),.renderer_start(start),
        .pixel_valid,.pixel_ready,.pixel_data(64'h00ffffff00ffffff),.display_meta({32'h44495350,224'd0}),
        .req_valid(fv),.req_ready(fr),.req_addr(fa),.req_wdata(fd),.frame_pending,.rendered_frames(rendered));
    display_write_bridge bridge(.clk,.rst_n,.shared_valid(sv),.shared_addr(sa),.shared_data(sd),.shared_ready(sr),
        .frame_valid(fv),.frame_addr(fa),.frame_data(fd),.frame_ready(fr),.req_valid(bv),.req_addr(ba),.req_data(bd),.req_ready(br));
    gw138k_ddr_arbiter arbiter(.clk,.reset_n(rst_n),.bist_done(1'b1),
        .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),.bist_ready(),.bist_response(),
        .scan_valid,.scan_address(29'd0),.scan_ready,.scan_response,
        .display_valid(load_req),.display_address(load_addr),.display_ready(load_ready),.display_response(load_response),
        .writer_valid(bv),.writer_address(ba),.writer_data(bd),.writer_ready(br),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
        .app_cmd,.app_en,.app_wren,.app_wend,.app_address(app_addr),.app_data,.app_mask,
        .app_ready(1'b1),.app_write_ready(write_accept),.app_response,.response_fault(fault));
    initial begin repeat(5)@(negedge clk);rst_n=1;end
    initial begin #30000000;$fatal(1,"integration timeout");end
endmodule
