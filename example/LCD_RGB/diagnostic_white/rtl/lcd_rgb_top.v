module lcd_rgb_top (
    input wire clk_50mhz,
    input wire restart_n,
    output wire [4:0] lcd_r,
    output wire [5:0] lcd_g,
    output wire [4:0] lcd_b,
    output wire lcd_pclk, lcd_hsync, lcd_vsync, lcd_de, lcd_bl
);
    wire pixel_clk, locked;
    wire async_reset_n=restart_n & locked;
    reg [1:0] reset_release;
    wire [15:0] rgb;
    wire [3:0] pattern;
    lcd_pll clockgen(.clkin(clk_50mhz),.clkout0(pixel_clk),.lock(locked));
    // Async assertion, synchronized deassertion in the pixel clock domain.
    always @(posedge pixel_clk or negedge async_reset_n)
        if(!async_reset_n) reset_release<=0;
        else reset_release<={reset_release[0],1'b1};
    lcd_scan #(.FIXED_PATTERN(6)) scan(.pixel_clk(pixel_clk),.reset_n(reset_release[1]),
        .rgb(rgb),.hsync(lcd_hsync),.vsync(lcd_vsync),.de(lcd_de),
        .bl(lcd_bl),.pattern(pattern));
    // Static white on every RGB output; DE determines the visible region.
    // Keeping blanking data high also avoids merging DE and all RGB outputs.
    assign {lcd_r,lcd_g,lcd_b}=16'hffff;
    assign lcd_pclk=~pixel_clk;
    // Diagnostic counters observe the same scan/PLL used for fixed white.
    reg [31:0] pixel_count=0,frame_count=0,active_count=0;
    reg [31:0] pixel_gray=0,frame_gray=0,active_gray=0;
    reg previous_vs=1,white_seen=0,de_seen=0,hs_seen=0,vs_seen=0;
    function [31:0] gray;
        input [31:0] value;
        begin gray=value^(value>>1); end
    endfunction
    always @(posedge pixel_clk or negedge async_reset_n) begin
        if(!async_reset_n) begin
            pixel_count<=0;frame_count<=0;active_count<=0;
            pixel_gray<=0;frame_gray<=0;active_gray<=0;
            previous_vs<=1;white_seen<=0;de_seen<=0;hs_seen<=0;vs_seen<=0;
        end else begin
            pixel_count<=pixel_count+1'b1;
            pixel_gray<=gray(pixel_count+1'b1);
            previous_vs<=lcd_vsync;
            if(lcd_vsync && !previous_vs) begin
                frame_count<=frame_count+1'b1;
                frame_gray<=gray(frame_count+1'b1);
            end
            if(lcd_de) begin
                active_count<=active_count+1'b1;
                active_gray<=gray(active_count+1'b1);
                de_seen<=1;
                if({lcd_r,lcd_g,lcd_b}==16'hffff) white_seen<=1;
            end
            if(!lcd_hsync) hs_seen<=1;
            if(!lcd_vsync) vs_seen<=1;
        end
    end
    (* ASYNC_REG="TRUE" *) reg [31:0] pg1=0,pg2=0,fg1=0,fg2=0,ag1=0,ag2=0;
    (* ASYNC_REG="TRUE" *) reg [15:0] flags1=0,flags2=0;
    reg [31:0] heartbeat=0;
    (* syn_keep=1, syn_preserve=1 *) reg [191:0] lcd_debug;
    always @(posedge clk_50mhz) begin
        pg1<=pixel_gray; pg2<=pg1; fg1<=frame_gray; fg2<=fg1;
        ag1<=active_gray; ag2<=ag1;
        // bit 0 lock, 1 restart, 2 scan reset released, 3 backlight;
        // bits 4..7 sticky DE, HS, VS and white-data observations.
        flags1<={8'd0,white_seen,vs_seen,hs_seen,de_seen,lcd_bl,
                 reset_release[1],restart_n,locked};
        flags2<=flags1;
        heartbeat<=heartbeat+1'b1;
        // Counter words remain Gray encoded; decode them on the host.
        lcd_debug<={16'd0,flags2,ag2,fg2,pg2,heartbeat,32'h4c434431};
    end
endmodule
