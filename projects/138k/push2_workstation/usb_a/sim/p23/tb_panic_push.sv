`timescale 1ns/1ps
module tb_panic_push;
    reg clk=0,rst=1,connected=1,valid=0,event_ready=1,frame_ready=0;
    reg [3:0] kind=0,cable=0,channel=0;
    reg [6:0] a=0,b=0;
    reg [9:0] panic_epoch=0;
    wire ready,event_valid;wire [17:0] event_data;wire [63:0] held;
    wire [6:0] note,velocity;wire [31:0] mapped,ignored;
    reg [9:0] x=0;reg [7:0] y=0;wire [15:0] pixel;
    always #10 clk=~clk;
    push2_controls controls(.clk,.rst,.connected,.valid,.ready,.kind,.cable,.channel,.a,.b,
        .actual_control(32'd0),.actual_options(32'd0),.actual_panic_epoch(panic_epoch),
        .event_valid,.event_ready,.event_data,.held,.last_note(note),.last_velocity(velocity),.mapped,.ignored);
    push2_surface_pixels pixels(.clk,.rst,.frame_ready,.frame_start(),.x,.y,.pixel_valid(),.pixel,
        .control(32'd0),.options(32'd0),.held,.note,.velocity,.display_meta(64'd0),.display_meta_valid(1'b0));
    task midi(input [3:0] k,input [6:0] aa,input [6:0] bb);
        @(negedge clk);kind=k;a=aa;b=bb;valid=1;
        do @(posedge clk);while(!ready);
        @(negedge clk);valid=0;repeat(2)@(posedge clk);
    endtask
    task capture;
        @(negedge clk);frame_ready=1;@(posedge clk);@(negedge clk);frame_ready=0;repeat(2)@(posedge clk);
    endtask
    initial begin
        repeat(3)@(posedge clk);rst=0;repeat(4)@(posedge clk);
        midi(9,60,2);
        if(!held[24] || note!=60 || velocity!=30 || event_data!={4'd1,7'd60,7'd30})
            $fatal(1,"Push note setup failed");
        capture();if(pixels.pads[24]!==1 || pixels.n!=60 || pixels.v!=30)$fatal(1,"screen setup snapshot");
        panic_epoch=1;repeat(3)@(posedge clk);
        if(held || note || velocity || event_valid)$fatal(1,"epoch did not clear Push latches");
        capture();if(pixels.pads || pixels.n || pixels.v)$fatal(1,"Push screen snapshot remained stale");
        // Pressure and release from the old physical press cannot resurrect a voice.
        midi(10,60,100);midi(8,60,0);
        if(held || event_valid)$fatal(1,"old held pad survived PANIC");
        midi(9,60,100);if(!held[24])$fatal(1,"new pad press blocked after release");
        midi(11,27,127);
        if(event_data!={4'd2,7'd120,7'd0} || held || note || velocity)
            $fatal(1,"Push PANIC button did not emit hard clear");
        panic_epoch=2;repeat(2)@(posedge clk);
        // A pending pre-PANIC event must be discarded when feedback arrives.
        event_ready=0;midi(9,64,100);if(!event_valid)$fatal(1,"pending setup missing");
        panic_epoch=3;repeat(3)@(posedge clk);
        if(event_valid || held || note || velocity)$fatal(1,"pending event crossed PANIC epoch");
        event_ready=0;connected=0;repeat(4)@(posedge clk);
        if(!event_valid || event_data!={4'd2,7'd120,7'd0})$fatal(1,"disconnect did not hard PANIC");
        $display("PASS PANIC Push: local held/note/velocity/pending event and screen snapshot clear; button/disconnect use CC120");
        $finish;
    end
endmodule
