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
    lcd_scan scan(.pixel_clk(pixel_clk),.reset_n(reset_release[1]),
        .rgb(rgb),.hsync(lcd_hsync),.vsync(lcd_vsync),.de(lcd_de),
        .bl(lcd_bl),.pattern(pattern));
    assign {lcd_r,lcd_g,lcd_b}=rgb;
    assign lcd_pclk=~pixel_clk;
endmodule
