// Optional CPU-free example. Connect pixel_valid/data directly to the core.
// A 10 Hz gradient with a note/velocity overlay proves arbitrary pixel control.
// Replace this module with a DDR3 reader, waveform renderer or UI engine.
module push2_demo_pixels #(
    parameter integer FRAME_PERIOD_CYCLES=6000000
) (
    input wire clk, input wire rst,
    input wire frame_ready, output wire frame_start,
    input wire [9:0] pixel_x, input wire [7:0] pixel_y,
    output wire pixel_valid, output wire [15:0] pixel_bgr565,
    input wire event_valid, output wire event_ready,
    input wire [3:0] event_kind,
    input wire [6:0] event_data1, input wire [6:0] event_data2
);
    localparam integer TIMER_BITS=(FRAME_PERIOD_CYCLES<2)?1:$clog2(FRAME_PERIOD_CYCLES+1);
    reg [TIMER_BITS-1:0] timer;
    reg [6:0] note, velocity, frame_velocity;
    reg [4:0] frame_note;
    assign frame_start=!rst && timer==0 && frame_ready;
    assign pixel_valid=!rst;
    assign event_ready=!rst;
    wire overlay=pixel_y<16 && pixel_x<{frame_velocity,3'b000};
    assign pixel_bgr565=overlay ? {frame_note[4:0],6'd63,5'd31} :
                                 {(pixel_x[4:0]^pixel_y[4:0]),pixel_y[5:0],pixel_x[4:0]};
    always @(posedge clk) begin
        if (rst) begin timer<=0; note<=0; velocity<=0; frame_note<=0; frame_velocity<=0; end
        else begin
            if (frame_start) begin
                timer<=TIMER_BITS'(FRAME_PERIOD_CYCLES-1);
                // Hold the overlay constant throughout one frame.
                frame_note<=note[4:0]; frame_velocity<=velocity;
            end else if (timer!=0) timer<=timer-1'b1;
            if (event_valid && event_ready) begin
                if (event_kind==9) begin note<=event_data1; velocity<=event_data2; end
                if (event_kind==8 && note==event_data1) velocity<=0;
            end
        end
    end
endmodule
