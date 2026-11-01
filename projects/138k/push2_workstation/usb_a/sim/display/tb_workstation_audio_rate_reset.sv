`timescale 1ns/1ps
module tb_workstation_audio_rate_reset;
    reg control=0,system_reset_n=0,mailbox_reset_n=1,frame_start=0;
    always #10 control=~control;
    wire pixel,serial,pixel_reset_n,source_reset_n,serializer_reset_n,serializer_reset,locked;
    video_clock_1080p #(.SIMULATION(1)) clock_owner(
        .clk_50m(control),.reset_n(system_reset_n),.pixel_clk(pixel),.serial_clk(serial),
        .serializer_reset_n(serializer_reset_n),.serializer_reset(serializer_reset),
        .pixel_reset_n(pixel_reset_n),.video_source_reset_n(source_reset_n),.pll_locked(locked));
    reg [3:0] status=4'b0011;
    wire hit;wire [23:0] rgb;
    workstation_audio_rate_overlay dut(
        .reset_ni(system_reset_n && pixel_reset_n && mailbox_reset_n),.pixel_reset_ni(pixel_reset_n),
        .control_clk_i(control),.pixel_clk_i(pixel),.actual_status_i(status),
        .frame_start_i(frame_start),.x_i(11'd1280),.y_i(11'd1024),.hit_o(hit),.rgb_o(rgb));
    wire [72:0] business={dut.frame_status,dut.status_seen,dut.glyph,dut.column,dut.row,
        dut.area_q,dut.text_q,dut.hit_o,dut.rgb_o};
    integer release_edges=0,release_checks=0,async_assertions=0,common_pulses=0,freeze_checks=0;
    reg [3:0] expected_frame=0;
    reg enforce_frame=0,checking_release=0;
    always @(negedge clock_owner.clocks_ready)begin
        release_edges=0;
        #0.001;
        if(business!==73'd0)$fatal(1,"pixel reset did not assert asynchronously");
        async_assertions++;
    end
    always @(posedge pixel)begin
        if(!clock_owner.clocks_ready)release_edges=0;
        else if(release_edges<5)release_edges++;
        #0.001;
        if(checking_release && pixel_reset_n!==(release_edges>=4))$fatal(1,"existing four-edge pixel release changed edges=%0d pipe=%b reset=%b ready=%b",release_edges,clock_owner.pixel_reset_pipe,pixel_reset_n,clock_owner.clocks_ready);
        if(checking_release && release_edges<=4 && business!==73'd0)$fatal(1,"overlay released before existing pixel owner completed four edges");
        if(checking_release && release_edges<=5)release_checks++;
        if(enforce_frame && dut.frame_status!==expected_frame)$fatal(1,"status changed outside actual frame boundary");
        if(enforce_frame)freeze_checks++;
    end
    task cycles(input integer count);repeat(count)@(negedge pixel);endtask
    task publish(input [3:0] value);begin
        status=value;cycles(100);enforce_frame=0;frame_start=1;cycles(1);frame_start=0;
        expected_frame=value;enforce_frame=1;cycles(8);
        if(dut.frame_status!==value)$fatal(1,"actual status was not frozen at frame start");
    end endtask
    reg [72:0] snapshot;
    initial begin
        #17.333;system_reset_n=1;
        // The ideal PLL model stops its clocks during initial reset. Prime
        // one genuine ready-to-reset edge before checking release; this is
        // an explicit warm reset, without assigning the owner's RTL state.
        wait(clock_owner.clocks_ready);#0.01;system_reset_n=0;
        #41.0;checking_release=1;system_reset_n=1;
        wait(pixel_reset_n);cycles(100);publish(4'b0011);
        // Inject a brief common-mailbox assertion between pixel edges. This
        // models the reset port independently and verifies that no raw control
        // reset is retained on the pixel consumers' CLEAR pins.
        repeat(4)begin
            @(negedge pixel);#0.1;snapshot=business;mailbox_reset_n=0;
            #0.1;if(business!==snapshot)$fatal(1,"raw common reset still reaches pixel business registers");
            #0.1;mailbox_reset_n=1;common_pulses++;
            cycles(100);
        end
        status=4'b1110;cycles(200);publish(4'b1110);
        enforce_frame=0;
        @(negedge pixel);#0.1;system_reset_n=0;
        #0.002;if(business!==73'd0)$fatal(1,"clock-owner assertion did not clear business with pixel clock stopped");
        #43.777;system_reset_n=1;
        wait(pixel_reset_n);cycles(100);publish(4'b0010);
        if(release_checks<10 || async_assertions<1 || common_pulses!=4 || freeze_checks<600)$fatal(1,"pixel reset coverage short");
        $display("PASS audio_rate_reset release_checks=%0d assertions=%0d common_pulses=%0d frozen=%0d existing_owner_edges=4",release_checks,async_assertions,common_pulses,freeze_checks);
        $finish;
    end
    initial begin #20000000;$fatal(1,"reset release watchdog");end
endmodule
