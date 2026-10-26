`timescale 1ns/1ps

module gw138k_cpu_pll_cell #(
    parameter INPUT_MHZ="50", MULTIPLY_INTEGER=24, MULTIPLY_EIGHTHS=0,
    parameter OUTPUT_DIV0=24, OUTPUT_DIV1=12, OUTPUT1_ENABLE="TRUE"
) (
    input wire clkin,init_clk,reset,enable0,
    output wire lock,clkout0,clkout1
);
    reg model_clk=0, lose_lock=0;
    always #15.873016 model_clk=!model_clk;
    assign clkout0=model_clk;
    assign clkout1=0;
    assign lock=!reset && !lose_lock;
    initial if(MULTIPLY_INTEGER!=15 || MULTIPLY_EIGHTHS!=6 || OUTPUT_DIV0!=25)
        $fatal(1,"LCD clock differs from reviewed 31.5 MHz example");
endmodule

module tb_workstation_lcd;
    reg clk_50m=0,audio_clk=0,reset_n=0,feedback_valid=0;
    reg [255:0] feedback=0;
    wire [15:0] rgb;
    wire pclk,hsync,vsync,de,backlight;
    wire [31:0] drops;
    always #10 clk_50m=!clk_50m;
    always #6.510417 audio_clk=!audio_clk;
    workstation_lcd dut (
        .clk_50m_i(clk_50m),.audio_clk_i(audio_clk),.rst_ni(reset_n),.audio_rst_ni(reset_n),
        .feedback_valid_i(feedback_valid),.feedback_i(feedback),
        .score_mask_i(32'd0),.score_running_i(1'b0),.record_enabled_i(1'b0),
        .red_o(rgb[15:11]),.green_o(rgb[10:5]),.blue_o(rgb[4:0]),.pclk_o(pclk),
        .hsync_o(hsync),.vsync_o(vsync),.de_o(de),.backlight_o(backlight),.snapshot_drop_count_o(drops)
    );
    integer source_divider=0;
    always @(negedge audio_clk) begin
        feedback_valid=0;
        if(!reset_n) source_divider=0;
        else if(source_divider==1599) begin source_divider=0;feedback_valid=1;end
        else source_divider=source_divider+1;
    end
    integer horizontal=0,vertical=0,frames=0,active_pixels=0,checked_pixels=0;
    reg [1:0] expected_de=0,expected_hsync=0,expected_vsync=0;
    reg [9:0] source_x=1023,expected_x=1023;
    reg [7:0] source_y=0,expected_y=0;
    wire active=horizontal>=136 && horizontal<936 && vertical>=35 && vertical<515;
    wire [15:0] reference_pixel;
    push2_surface_pixels #(.SHOW_LAST_NOTE(0)) reference_surface (
        .clk(dut.pixel_clk),.rst(!dut.pixel_reset_n),.frame_ready(horizontal==0 && vertical==0),.frame_start(),
        .x(expected_x),.y(expected_y),.pixel_valid(),.pixel(reference_pixel),
        .control(dut.feedback[63:32]),.options(dut.feedback[255:224]),.held(dut.feedback[195:132]),
        .note(7'd0),.velocity(7'd0),.display_meta(64'd0),.display_meta_valid(1'b0),
        .score_mask(32'd0),.score_running(1'b0),.record_enabled(1'b0),
        .guide_mode(1'b0),.guide_chosen(1'b0),.guide_browse(4'd0),.guide_track(4'd0),
        .guide_track_count(5'd0),.guide_score_count(16'd0),.guide_cursor(16'd0),
        .guide_analysis_done(1'b0),.name_write_valid(1'b0),.name_write_addr(8'd0),.name_write_data(8'd0)
    );
    reg [31:0] frozen_control=0;
    reg snapshot_seen=0,changed_midframe=0;
    always @(posedge dut.pixel_clk) begin
        if(!dut.pixel_reset_n) begin
            horizontal=0;vertical=0;frames=0;active_pixels=0;
            expected_de=0;expected_hsync=0;expected_vsync=0;
            source_x=1023;source_y=0;expected_x=1023;expected_y=0;snapshot_seen=0;
        end else begin
            expected_x=source_x;expected_y=source_y;
            source_x=active ? (horizontal-136)*6/5 : 0;
            source_y=active ? (vertical-35)/3 : 0;
            expected_de={expected_de[0],active};
            expected_hsync={expected_hsync[0],horizontal>=48};
            expected_vsync={expected_vsync[0],vertical>=3};
            if(horizontal==0 && vertical==0) begin
                if(frames && active_pixels!=800*480)$fatal(1,"LCD frame lost active pixels: %0d",active_pixels);
                active_pixels=0;
                if(frames) begin frozen_control=dut.feedback[63:32];snapshot_seen=1;end
            end
            if(horizontal==975) begin
                horizontal=0;
                if(vertical==527) begin vertical=0;frames=frames+1;end
                else vertical=vertical+1;
            end else horizontal=horizontal+1;
            #1;
            if(dut.pixel_reset_n) begin
            if({de,hsync,vsync}!={expected_de[1],expected_hsync[1],expected_vsync[1]})
                $fatal(1,"LCD RGB/control pipeline or raster timing changed");
            if(!de && rgb!=0)$fatal(1,"LCD blanking is not black");
            if(snapshot_seen && dut.u_surface.cs!==frozen_control)$fatal(1,"LCD parameters tore inside a frame");
            if(de) begin
                active_pixels=active_pixels+1;checked_pixels=checked_pixels+1;
                if(rgb!==reference_pixel)$fatal(1,"LCD differs from shared performance renderer at %0d,%0d: actual=%h expected=%h source=%0d,%0d local=%h,%h",expected_x,expected_y,rgb,reference_pixel,dut.surface_x,dut.surface_y,reference_surface.local_x,reference_surface.tile);
            end
            end
        end
    end
    initial begin
        repeat(10) @(negedge clk_50m);
        reset_n=1;feedback[63:32]=32'h7f000010;
        wait(frames==1 && vertical==100);
        @(negedge audio_clk);feedback[63:32]=32'h40000129;changed_midframe=1;
        wait(frames==3 && vertical==100);
        if(!backlight || drops || !changed_midframe || checked_pixels<800*480*3)
            $fatal(1,"LCD backlight, CDC or frame progress failed");
        dut.u_pll.lose_lock=1;
        #1;
        if(backlight || de || rgb)$fatal(1,"LCD lock loss did not reset outputs");
        repeat(10) @(negedge clk_50m);
        dut.u_pll.lose_lock=0;
        wait(dut.pixel_reset_n);
        repeat(10) @(negedge clk_50m);
        if(backlight)$fatal(1,"LCD relock skipped delayed backlight");
        $display("PASS LCD workstation: 800x480, shared renderer, atomic snapshots, backlight and lock recovery");
        $finish;
    end
    initial begin #100000000;$fatal(1,"LCD integration timeout");end
endmodule
