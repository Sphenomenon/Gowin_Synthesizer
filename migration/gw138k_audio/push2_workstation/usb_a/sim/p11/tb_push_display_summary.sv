module tb_push_display_summary;
    reg clk=0,rst=1,frame_ready=0;
    reg [9:0] x=0; reg [7:0] y=0;
    reg [31:0] control=0,options=0; reg [63:0] held=0;
    reg [6:0] note=60,velocity=0;
    reg [63:0] display_meta=0; reg display_meta_valid=0;
    wire frame_start,pixel_valid; wire [15:0] pixel;
    push2_surface_pixels dut(.clk(clk),.rst(rst),.frame_ready(frame_ready),
        .frame_start(frame_start),.x(x),.y(y),.pixel_valid(pixel_valid),.pixel(pixel),
        .control(control),.options(options),.held(held),.note(note),.velocity(velocity),
        .display_meta(display_meta),.display_meta_valid(display_meta_valid));
    always #5 clk=~clk;
    initial begin
        repeat(2)@(posedge clk); rst<=0;
        display_meta<=64'h00000001_02800000; // frame sequence 1, effect mask 101
        display_meta_valid<=1;
        @(posedge clk); #1;
        display_meta_valid<=0;
        if(!dut.display_meta_seen || dut.display_effect_mask!==3'b101)
            $fatal(1,"Push summary was not latched");
        frame_ready<=1;
        @(posedge clk); #1; frame_ready<=0;
        $display("PASS Push display summary endpoint and effect-mask latch");
        $finish;
    end
endmodule
