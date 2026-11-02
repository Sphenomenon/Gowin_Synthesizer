`timescale 1ns/1ps
module tb_usb_status_panel;
    reg source_clk=0,clk=0,source_run=1;
    always #7 if(source_run) source_clk=~source_clk;
    always #5 clk=~clk;
    reg source_reset_n=0,reset_n=0,frame_start=0,pixel_valid=0,pixel_ready=0;
    reg [7:0] source_status=0;
    reg [31:0] active_voices=0;
    wire [63:0] decorated;
    workstation_usb_status_panel #(.STALE_CYCLES(200)) dut(
        .source_clk(source_clk),.source_reset_n(source_reset_n),.source_status(source_status),
        .clk(clk),.reset_n(reset_n),.frame_start(frame_start),.pixel_valid(pixel_valid),
        .pixel_ready(pixel_ready),.active_voices(active_voices),
        .pixel_data(64'h0012345600654321),.decorated_data(decorated));
    task settle(input [7:0] state);
        begin source_status=state;repeat(100) @(negedge clk);end
    endtask
    task frame;
        begin frame_start=1;@(negedge clk);frame_start=0;#1;end
    endtask
    task label_check(input [255:0] status_text,input [255:0] device_text);
        begin
            if(dut.status_line!==status_text || dut.device_line!==device_text)
                $fatal(1,"bad labels: %s / %s",dut.status_line,dut.device_line);
        end
    endtask
    integer row,col,file_id;
    reg [63:0] held_pixel;
    initial begin
        repeat(3) @(negedge clk);reset_n=1;source_reset_n=1;
        settle(0);frame();
        label_check("DISCONNECTED                    ","DEVICE  NONE                    ");
        settle(8'h30);frame();
        label_check("ENUMERATING                     ","DEVICE  NONE                    ");
        settle(8'h39);frame();
        label_check("CONNECTED                       ","DEVICE  PUSH 2                  ");
        settle(8'h37);
        // A classification change cannot tear an in-progress rendered frame.
        label_check("CONNECTED                       ","DEVICE  PUSH 2                  ");
        active_voices=32'haaaa5555;
        frame();label_check("CONNECTED                       ","DEVICE  25K KEYBOARD            ");
        active_voices=32'hffffffff;
        if(dut.frame_voices!==16) $fatal(1,"voice snapshot count/freeze");
        if(dut.speed_line!=="LINK    FULL SPEED              ") $fatal(1,"wrong FS label");
        file_id=$fopen("usb_status_panel.ppm","w");
        $fwrite(file_id,"P3\n640 192\n255\n");
        pixel_valid=1;pixel_ready=1;
        for(row=0;row<1080;row=row+1) begin
            for(col=0;col<1920;col=col+2) begin
                #1;
                if(dut.x!==col || dut.y!==row) $fatal(1,"raster drift");
                if(!(col>=1216 && col<1856 && row>=848 && row<1040)) begin
                    if(decorated!==64'h0012345600654321) $fatal(1,"modified outside panel");
                end else begin
                    $fwrite(file_id,"%0d %0d %0d %0d %0d %0d\n",decorated[23:16],decorated[15:8],
                        decorated[7:0],decorated[55:48],decorated[47:40],decorated[39:32]);
                end
                if(row==1004 && col==1250 && decorated!==64'h0038bdf80038bdf8)
                    $fatal(1,"occupied progress area");
                if(row==1004 && col==1504 && decorated!==64'h0033415500334155)
                    $fatal(1,"half full progress boundary");
                if(col==1248 && row==864) begin
                    // Top-left U pixel from the existing 5x7 font, scaled 2x.
                    if(decorated!==64'h00e2e8f000e2e8f0) $fatal(1,"font misaligned");
                    held_pixel=decorated;pixel_ready=0;
                    repeat(9) begin @(negedge clk);#1;
                        if(decorated!==held_pixel || dut.x!==1248) $fatal(1,"stall changed pixels");
                    end
                    pixel_ready=1;
                end
                @(negedge clk);
            end
        end
        $fclose(file_id);pixel_valid=0;pixel_ready=0;
        frame();if(dut.frame_voices!==32) $fatal(1,"all 32 voices");
        active_voices=32'h80000000;frame();if(dut.frame_voices!==1) $fatal(1,"highest voice");
        active_voices=32'h7fffffff;frame();if(dut.frame_voices!==31) $fatal(1,"31 voices");
        active_voices=0;frame();if(dut.frame_voices!==0) $fatal(1,"empty voices");
        settle(8'h3b);frame();
        label_check("CONNECTED                       ","DEVICE  USB MIDI                ");
        settle(8'hb9);frame();label_check("USB ERROR                       ","DEVICE  NONE                    ");
        settle(8'h08);frame();label_check("DISCONNECTED                    ","DEVICE  NONE                    ");
        settle(8'h39);frame();source_run=0;
        repeat(250) @(negedge clk);frame();
        label_check("NO STATUS                       ","DEVICE  NONE                    ");
        source_run=1;settle(8'h37);frame();
        source_reset_n=0;repeat(2) @(negedge clk);frame();
        label_check("NO STATUS                       ","DEVICE  NONE                    ");
        // Release the source reset between destination edges. Freshness must
        // remain cleared throughout the destination release synchronizer.
        #2;source_reset_n=1;
        repeat(2) begin
            @(negedge clk);#1;
            if(dut.fresh!==0 || dut.age!==0 || dut.status_release_q[2]!==0)
                $fatal(1,"source reset bypassed local release");
        end
        settle(8'h37);frame();
        label_check("CONNECTED                       ","DEVICE  25K KEYBOARD            ");
        $display("PASS USB status: device switching, frame freeze, stalls, raster, stale/reset");
        $finish;
    end
    initial begin #30000000;$fatal(1,"timeout");end
endmodule

// Exercise the actual upstream ULPI mailbox with CPU/display clocks running.
// The old projection kept republishing a healthy held snapshot forever.
module tb_usb_link_status;
    reg ulpi_clk=0,cpu_clk=0,ulpi_run=1,reset_n=0;
    always #7 if(ulpi_run) ulpi_clk=~ulpi_clk;
    always #5 cpu_clk=~cpu_clk;
    wire link_valid;
    wire [4:0] link_status;
    wire [7:0] display_status;
    reg [2:0] device_state=7;
    reg [4:0] source_status=5'b11001;
    gw138k_stream_cdc #(.WIDTH(5)) upstream (
        .reset_n(reset_n),.source_clk(ulpi_clk),.destination_clk(cpu_clk),
        .source_valid(1'b1),.source_data(source_status),
        .destination_valid(link_valid),.destination_data(link_status),.drop_count()
    );
    workstation_usb_status_projection #(.STALE_CYCLES(32)) dut (
        .clk(cpu_clk),.reset_n(reset_n),.cpu_fault(1'b0),.device_state(device_state),
        .link_status(link_status),.link_valid(link_valid),.display_status(display_status)
    );
    initial begin
        repeat(3) @(negedge cpu_clk);reset_n=1;
        repeat(100) @(negedge cpu_clk);
        if(display_status!==8'h37) $fatal(1,"initial link status");
        ulpi_run=0;
        repeat(100) @(negedge cpu_clk);
        if(display_status[6]!==1 || dut.link_fresh!==0)
            $fatal(1,"stopped ULPI republished healthy status");
        // Owner detach does not revive or hide the stale-link fault.
        device_state=0;repeat(3) @(negedge cpu_clk);
        if(display_status[6]!==1) $fatal(1,"detach hid stale upstream");
        ulpi_run=1;device_state=3;source_status=5'b11101;
        repeat(100) @(negedge cpu_clk);
        if(display_status!==8'h3b) $fatal(1,"fresh ULPI reconnect did not recover");
        reset_n=0;repeat(3) @(negedge cpu_clk);
        if(display_status[6]!==1 || dut.link_fresh!==0)
            $fatal(1,"reset retained fresh status");
        $display("PASS upstream USB status: stopped ULPI expires with CPU running, reconnect/reset");
        $finish;
    end
    initial begin #20000;$fatal(1,"timeout upstream");end
endmodule
