`timescale 1ns/1ps
`default_nettype none
// Display-only XY bitmap writer. Points come from one immutable block of
// final DAC PCM, after its existing L/-R mapping, auto gain and clamp.
// Published front/back storage remains outside this owner. One extra raw
// bitmap carries exactly the preceding block, never a previously blended
// image. Thus the public one-bit bitmap is current OR previous raw trace.
module workstation_xy_trace (
    input wire clk,reset_n,
    input wire frame_start_i,
    input wire [2:0] gain_i,
    output wire frame_ready_o,
    input wire point_valid_i,point_nonzero_i,
    input wire [7:0] point_x_i,point_y_i,
    output wire point_ready_o,idle_o,
    output wire write_enable_o,
    output wire [15:0] write_address_o,
    output wire write_pixel_o
);
    localparam [1:0] CLEAR_READ=0,CLEAR_WRITE=1,POINT=2,DRAW=3;
    reg [1:0] state;
    reg frame_active,history_valid,keep_history;
    reg [2:0] history_gain;
    reg [15:0] clear_address;
    reg history[0:65535];
    reg history_q;
    reg have_previous,prepare_line;
    reg [7:0] previous_x,previous_y,line_x,line_y,target_x,target_y,line_steps;
    reg [8:0] line_dx,line_dy;
    reg step_right,step_down;
    reg signed [9:0] line_error;
    wire [8:0] input_dx=point_x_i>=previous_x ? {1'b0,point_x_i}-{1'b0,previous_x} : {1'b0,previous_x}-{1'b0,point_x_i};
    wire [8:0] input_dy=point_y_i>=previous_y ? {1'b0,point_y_i}-{1'b0,previous_y} : {1'b0,previous_y}-{1'b0,point_y_i};
    wire signed [10:0] twice_error=$signed({line_error[9],line_error}) <<< 1;
    wire advance_x=twice_error>=-$signed({2'b00,line_dy});
    wire advance_y=twice_error<=$signed({2'b00,line_dx});
    reg signed [9:0] next_error;
    always @* begin
        next_error=line_error;
        if(advance_x)next_error=next_error-$signed({1'b0,line_dy});
        if(advance_y)next_error=next_error+$signed({1'b0,line_dx});
    end
    assign frame_ready_o=frame_active && state==POINT;
    assign point_ready_o=frame_ready_o;
    assign idle_o=frame_ready_o;
    assign write_enable_o=frame_active && (state==CLEAR_WRITE || (state==DRAW && !prepare_line));
    assign write_address_o=state==DRAW ? {line_y,line_x} : clear_address;
    assign write_pixel_o=state==DRAW || (keep_history && history_q);
    // Registered read, one mutually exclusive write port. Clear first copies
    // old raw to the private back bank, then erases that raw cell. Drawing
    // writes the new raw trace. Neither operation touches the published front.
    always @(posedge clk)begin
        if(frame_active && state==CLEAR_READ)history_q<=history[clear_address];
        if(frame_active && state==CLEAR_WRITE)history[clear_address]<=0;
        else if(frame_active && state==DRAW && !prepare_line)history[{line_y,line_x}]<=1;
    end
    always @(posedge clk or negedge reset_n)begin
        if(!reset_n)begin
            state<=POINT;frame_active<=0;history_valid<=0;keep_history<=0;history_gain<=0;clear_address<=0;
            have_previous<=0;prepare_line<=0;previous_x<=0;previous_y<=0;line_x<=0;line_y<=0;target_x<=0;target_y<=0;
            line_dx<=0;line_dy<=0;step_right<=0;step_down<=0;line_error<=0;line_steps<=0;
        end else if(frame_start_i)begin
            state<=CLEAR_READ;frame_active<=1;clear_address<=0;have_previous<=0;prepare_line<=0;
            // A gain change changes the meaning of each coordinate. Retire
            // old coordinates instead of retaining a falsely scaled trail.
            keep_history<=history_valid && history_gain==gain_i;
            history_gain<=gain_i;
        end else if(frame_active)case(state)
            CLEAR_READ:state<=CLEAR_WRITE;
            CLEAR_WRITE:begin
                if(clear_address==16'hffff)begin history_valid<=1;state<=POINT;end
                else begin clear_address<=clear_address+1'b1;state<=CLEAR_READ;end
            end
            POINT:if(point_valid_i)begin
                if(!point_nonzero_i)have_previous<=0;
                else begin
                    line_x<=have_previous ? previous_x:point_x_i;
                    line_y<=have_previous ? previous_y:point_y_i;
                    target_x<=point_x_i;target_y<=point_y_i;
                    line_dx<=have_previous ? input_dx:9'd0;
                    line_dy<=have_previous ? input_dy:9'd0;
                    // Register both absolute deltas before their subtraction.
                    // Display-local work takes one extra cycle per segment;
                    // no PCM schedule or ready signal depends on this writer.
                    prepare_line<=1;
                    step_right<=point_x_i>=previous_x;step_down<=point_y_i>=previous_y;
                    previous_x<=point_x_i;previous_y<=point_y_i;have_previous<=1;line_steps<=0;state<=DRAW;
                end
            end
            DRAW:begin
                // An 8-bit raster segment contains at most 256 pixels. The
                // explicit cap guarantees display work stays bounded even
                // under a future faulty producer. No PCM ready/backpressure.
                if(prepare_line)begin
                    line_error<=$signed({1'b0,line_dx})-$signed({1'b0,line_dy});
                    prepare_line<=0;
                end else if((line_x==target_x && line_y==target_y) || line_steps==8'hff)state<=POINT;
                else begin
                    if(advance_x)line_x<=step_right ? line_x+1'b1:line_x-1'b1;
                    if(advance_y)line_y<=step_down ? line_y+1'b1:line_y-1'b1;
                    line_error<=next_error;line_steps<=line_steps+1'b1;
                end
            end
            default:begin state<=POINT;frame_active<=0;history_valid<=0;end
        endcase
    end
endmodule
`default_nettype wire
