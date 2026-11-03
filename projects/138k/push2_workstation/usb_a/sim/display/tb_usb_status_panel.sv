`timescale 1ns/1ps
module tb_usb_status_panel;
    reg source_clk=0,clk=0,source_run=1;
    always #7 if(source_run) source_clk=~source_clk;
    always #5 clk=~clk;
    reg source_reset_n=0,reset_n=0,frame_start=0,pixel_valid=0,pixel_ready=0;
    reg [7:0] source_status=0;
`ifdef WORKSTATION_NATIVE_USB_STATUS
    reg ulpi_clk=0;
    always #9 ulpi_clk=~ulpi_clk;
    wire [7:0] observed_status;
    workstation_usb2_display_status #(.STALE_CYCLES(200)) actual_status(
        .cpu_clk(source_clk),.ulpi_clk(ulpi_clk),.reset_n(source_reset_n),
        .device_state(source_status[2:0]),.cpu_fault({3'b0,source_status[7]}),
        .failed(source_status[6]),.traffic_enable(source_status[5]),
        .transaction_ready(source_status[4]),.high_speed(source_status[3]),.status(observed_status));
`else
    wire [7:0] observed_status=source_status;
`endif
    reg [31:0] active_voices=0;
    wire [63:0] decorated;
    workstation_usb_status_panel #(.STALE_CYCLES(200)) dut(
        .source_clk(source_clk),.source_reset_n(source_reset_n),.source_status(observed_status),
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
        $display("PASS USB status: device switching, frame freeze, stalls, raster, stale/reset");
        $finish;
    end
    initial begin #30000000;$fatal(1,"timeout");end
endmodule

// Compare every accepted pixel against the legacy combinational decoration.
// Independent input bubbles/output stalls exercise all elastic-stage edges.
module tb_usb_status_pipeline;
    reg clk=0,source_clk=0,ulpi_clk=0;
    always #5 clk=~clk;
    always #7 source_clk=~source_clk;
    always #9 ulpi_clk=~ulpi_clk;
    reg reset_n=0,source_reset_n=0,frame_start=0;
    reg pixel_valid=0,pixel_ready=0,renderer_done=0;
    reg [63:0] pixel_data=0;
    wire input_ready,output_valid,output_done;
    wire [63:0] result,reference;
    wire [7:0] source_status;
    workstation_usb2_display_status #(.STALE_CYCLES(200)) observer(
        .cpu_clk(source_clk),.ulpi_clk(ulpi_clk),.reset_n(source_reset_n),
        .device_state(3'b111),.cpu_fault(4'd0),.failed(1'b0),
        .traffic_enable(1'b1),.transaction_ready(1'b1),.high_speed(1'b0),
        .status(source_status));
    workstation_usb_status_panel #(.STALE_CYCLES(200),.PIPELINED(1)) dut(
        .source_clk(source_clk),.source_reset_n(source_reset_n),.source_status(source_status),
        .clk(clk),.reset_n(reset_n),.frame_start(frame_start),
        .pixel_valid(pixel_valid),.pixel_ready(pixel_ready),.active_voices(32'haaaa5555),
        .pixel_data(pixel_data),.decorated_data(result),.input_ready(input_ready),
        .output_valid(output_valid),.renderer_done(renderer_done),.output_done(output_done));
    workstation_usb_status_panel #(.STALE_CYCLES(200)) model(
        .source_clk(source_clk),.source_reset_n(source_reset_n),.source_status(source_status),
        .clk(clk),.reset_n(reset_n),.frame_start(frame_start),
        .pixel_valid(pixel_valid),.pixel_ready(input_ready),.active_voices(32'haaaa5555),
        .pixel_data(pixel_data),.decorated_data(reference));
    localparam integer PAIRS=1920*1080/2;
    integer sent=0,received=0,queued=0,write_index=0,read_index=0;
    integer cycle=0,stalls=0;
    reg [63:0] expected[0:15];
    reg stalled=0;
    reg [63:0] held;
    reg [31:0] random_state=32'h1234abcd;
    reg running=0,done_sent=0;
    always @(posedge clk)if(reset_n && running && !frame_start)begin
        if(stalled && (!output_valid || result!==held))$fatal(1,"output changed during stall");
        stalled=output_valid && !pixel_ready;held=result;
        if(stalled)stalls=stalls+1;
        if(output_valid && pixel_ready)begin
            if(queued==0 || result!==expected[read_index])
                $fatal(1,"pipeline ordering/pixel mismatch at pair %0d",received);
            read_index=(read_index+1)%16;queued=queued-1;received=received+1;
        end
        if(pixel_valid && input_ready)begin
            expected[write_index]=reference;write_index=(write_index+1)%16;
            queued=queued+1;sent=sent+1;
            if(queued>4)$fatal(1,"pipeline exceeded four accepted pixels");
        end
        if(output_done)begin
            if(sent!=PAIRS || received!=PAIRS || queued!=0 || stalls<100)
                $fatal(1,"frame committed before final output handshake");
            // Reset flush cannot leak an old valid or completion pulse.
            running=0;reset_n=0;
        end
    end
    always @(negedge clk)if(running)begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        cycle=cycle+1;
        pixel_ready=random_state[2] || random_state[8];
        renderer_done=0;
        if(sent==PAIRS)begin
            pixel_valid=0;
            if(!done_sent)begin renderer_done=1;done_sent=1;end
        end else if(!pixel_valid || input_ready)begin
            pixel_valid=random_state[0] || random_state[5];
            pixel_data=64'h0012345600654321 ^ sent;
        end
    end
    initial begin
        repeat(3)@(negedge clk);reset_n=1;source_reset_n=1;
        repeat(200)@(negedge clk);frame_start=1;
        @(negedge clk);frame_start=0;running=1;
        wait(!reset_n);repeat(3)@(negedge clk);
        if(output_valid || output_done)$fatal(1,"reset did not flush output");
        $display("PASS pipelined USB status: %0d ordered pairs, %0d stalls, writer done after drain",received,stalls);
        $finish;
    end
    initial begin #100000000;$fatal(1,"pipeline timeout");end
endmodule
