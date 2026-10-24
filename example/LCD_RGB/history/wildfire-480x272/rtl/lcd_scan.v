// RGB565 test generator. Launch on pixel_clk rising, sample on LCD_PCLK rising
// (the opposite edge). No framebuffer, CPU, DDR, audio or touch dependencies.
module lcd_scan #(
    parameter H_ACTIVE=480, H_SYNC=41, H_BACK=2, H_FRONT=2,
    parameter V_ACTIVE=272, V_SYNC=10, V_BACK=2, V_FRONT=2,
    parameter HS_ACTIVE=1, VS_ACTIVE=1, BL_ACTIVE=1,
    parameter FRAMES_PER_PATTERN=360, BACKLIGHT_FRAMES=3,
    parameter FIXED_PATTERN=-1
) (
    input wire pixel_clk, input wire reset_n,
    output reg [15:0] rgb,
    output reg hsync, vsync, de,
    output wire bl,
    output reg [3:0] pattern
);
    localparam HT=H_SYNC+H_BACK+H_ACTIVE+H_FRONT;
    localparam VT=V_SYNC+V_BACK+V_ACTIVE+V_FRONT;
    localparam HX=H_SYNC+H_BACK, VY=V_SYNC+V_BACK;
    reg [15:0] h, v;
    reg [31:0] pattern_frames;
    reg [15:0] startup_frames;
    integer x, y, section, level;
    reg [7:0] red, green, blue;
    reg [15:0] next_rgb;
    wire active=(h>=HX && h<HX+H_ACTIVE && v>=VY && v<VY+V_ACTIVE);
    assign bl = reset_n && startup_frames>=BACKLIGHT_FRAMES ? BL_ACTIVE : !BL_ACTIVE;

    always @* begin
        x=h-HX; y=v-VY;
        section=0; level=0;
        red=0; green=0; blue=0; next_rgb=0;
        if (active) begin
            case (pattern)
                0: begin
                    section=x*8/H_ACTIVE;
                    case(section)
                        0: next_rgb=16'hffff;
                        1: next_rgb=16'hffe0;
                        2: next_rgb=16'h07ff;
                        3: next_rgb=16'h07e0;
                        4: next_rgb=16'hf81f;
                        5: next_rgb=16'hf800;
                        6: next_rgb=16'h001f;
                        default: next_rgb=0;
                    endcase
                end
                1: begin
                    level=x*255/(H_ACTIVE-1);
                    section=y*3/V_ACTIVE;
                    if(section==0) red=level[7:0];
                    else if(section==1) green=level[7:0];
                    else blue=level[7:0];
                    next_rgb={red[7:3],green[7:2],blue[7:3]};
                end
                2,3,4,5: begin
                    case(pattern)
                        2: level=x*255/(H_ACTIVE-1);
                        3: level=(x*16/H_ACTIVE)*17;
                        4: level=(x*8/H_ACTIVE)*8; // 0,8,...56 survive RGB565
                        5: level=199+(x*8/H_ACTIVE)*8; // 199,207,...255
                        default: level=0;
                    endcase
                    red=level[7:0]; green=level[7:0]; blue=level[7:0];
                    next_rgb={red[7:3],green[7:2],blue[7:3]};
                end
                6: next_rgb=16'hffff;
                7: next_rgb=16'h0000;
                8: next_rgb=16'h8410; // quantized RGB(128,128,128)
                9: next_rgb=(x[4]^y[4]) ? 16'hffff : 16'h0000;
                10: next_rgb=16'h0001 << (x*16/H_ACTIVE);
                11: begin
                    if(x==0 || x==H_ACTIVE-1 || y==0 || y==V_ACTIVE-1)
                        next_rgb=16'hffff;
                    else if(x==H_ACTIVE/2 || y==V_ACTIVE/2)
                        next_rgb=16'h07e0;
                    else next_rgb=16'h0000;
                end
                default: next_rgb=0;
            endcase
        end
    end

    always @(posedge pixel_clk or negedge reset_n) begin
        if(!reset_n) begin
            h<=0; v<=0; rgb<=0; de<=0;
            hsync<=!HS_ACTIVE; vsync<=!VS_ACTIVE;
            pattern<=FIXED_PATTERN<0 ? 0 : FIXED_PATTERN;
            pattern_frames<=0; startup_frames<=0;
        end else begin
            rgb<=next_rgb;
            de<=active;
            hsync<=h<H_SYNC ? HS_ACTIVE : !HS_ACTIVE;
            vsync<=v<V_SYNC ? VS_ACTIVE : !VS_ACTIVE;
            if(h==HT-1) begin
                h<=0;
                if(v==VT-1) begin
                    v<=0;
                    if(startup_frames<BACKLIGHT_FRAMES) startup_frames<=startup_frames+1'b1;
                    if(FIXED_PATTERN<0) begin
                        if(pattern_frames==FRAMES_PER_PATTERN-1) begin
                            pattern_frames<=0;
                            pattern<=pattern==11 ? 4'd0 : pattern+4'd1;
                        end else pattern_frames<=pattern_frames+1'b1;
                    end
                end else v<=v+1'b1;
            end else h<=h+1'b1;
        end
    end
endmodule
