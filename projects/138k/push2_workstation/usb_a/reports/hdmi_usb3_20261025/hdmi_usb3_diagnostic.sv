module hdmi_usb3_diagnostic #(
    parameter integer REPORT_CYCLES=50000000
)(
    input wire clk_50m, hdmi_hpd,
    output wire debug_uart_tx,
    inout wire hdmi_cec,
    output wire tmds_clk_p, tmds_clk_n,
    output wire [2:0] tmds_data_p, tmds_data_n,
    output wire flash_clk, flash_cs_n, flash_mosi, flash_wp_n, flash_hold_n
);
    wire power_reset_n, reset_n, restart_done;
    reset_release u_reset(.clk(clk_50m),.ext_reset_n(1'b1),.reset_n(power_reset_n));
    hdmi_usb3_boot_reset u_boot_reset(
        .clk(clk_50m),.power_reset_n(power_reset_n),.reset_n(reset_n),.restart_done(restart_done)
    );
    wire pixel_clk, serial_clk, pixel_reset_n, serializer_reset_n, serializer_reset;
    wire video_source_reset_n, locked;
    video_clock_1080p u_clock(
        .clk_50m(clk_50m),.reset_n(reset_n),.pixel_clk(pixel_clk),.serial_clk(serial_clk),
        .pixel_reset_n(pixel_reset_n),.serializer_reset_n(serializer_reset_n),
        .serializer_reset(serializer_reset),.video_source_reset_n(video_source_reset_n),.pll_locked(locked)
    );
    wire [11:0] pixel_x;
    wire [10:0] pixel_y;
    wire data_enable, hsync, vsync;
    video_timing_1080p u_timing(
        .pixel_clk(pixel_clk),.reset_n(pixel_reset_n),.pixel_x(pixel_x),.pixel_y(pixel_y),
        .data_enable(data_enable),.hsync(hsync),.vsync(vsync),
        .frame_start(),.line_start(),.vblank_start()
    );
    wire [23:0] pixel_data;
    hdmi_usb3_colorbars u_pattern(.pixel_x(pixel_x),.data_enable(data_enable),.pixel_data(pixel_data));
    dvi_tx_top u_dvi(
        .pixel_clock(pixel_clk),.ddr_bit_clock(serial_clk),.reset(!pixel_reset_n),
        .serializer_reset(serializer_reset),.den(data_enable),.hsync(hsync),.vsync(vsync),
        .pixel_data(pixel_data),.tmds_clk({tmds_clk_p,tmds_clk_n}),
        .tmds_d0({tmds_data_p[0],tmds_data_n[0]}),.tmds_d1({tmds_data_p[1],tmds_data_n[1]}),
        .tmds_d2({tmds_data_p[2],tmds_data_n[2]})
    );
    assign hdmi_cec=1'bz;
    assign flash_clk=1'b0;
    assign flash_cs_n=1'b1;
    assign flash_mosi=1'b0;
    assign flash_wp_n=1'b1;
    assign flash_hold_n=1'b1;
    reg [7:0] pixel_counter;
    always @(posedge pixel_clk or negedge pixel_reset_n)
        if(!pixel_reset_n) pixel_counter<=0;
        else pixel_counter<=pixel_counter+1'b1;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [4:0] status_meta_q, status_sync_q;
    reg pixel_previous, pixel_seen;
    reg [25:0] report_timer;
    reg [15:0] report_flags;
    reg [3:0] character_index;
    reg report_active;
    wire tx_ready;
    wire [7:0] tx_byte;
    hdmi_usb3_status_character u_character(.character_index(character_index),.flags(report_flags),.data(tx_byte));
    uart_tx u_uart(.clk(clk_50m),.rst_n(reset_n),.data({24'd0,tx_byte}),
        .valid(report_active),.ready(tx_ready),.serial_out(debug_uart_tx),.byte_done());
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            status_meta_q<=0;
            status_sync_q<=0;
            pixel_previous<=0;
            pixel_seen<=0;
            report_timer<=0;
            report_flags<=0;
            character_index<=0;
            report_active<=0;
        end else begin
            status_meta_q<={pixel_counter[7],hdmi_hpd,serializer_reset_n,pixel_reset_n,locked};
            status_sync_q<=status_meta_q;
            pixel_previous<=status_sync_q[4];
            if(status_sync_q[4]!=pixel_previous) pixel_seen<=1;
            if(report_timer==REPORT_CYCLES-1) begin
                report_timer<=0;
                if(!report_active) begin
                    report_flags<={10'd0,restart_done,pixel_seen,status_sync_q[3:0]};
                    character_index<=0;
                    report_active<=1;
                    pixel_seen<=0;
                end
            end else report_timer<=report_timer+1'b1;
            if(report_active && tx_ready) begin
                if(character_index==10) report_active<=0;
                else character_index<=character_index+1'b1;
            end
        end
    end
endmodule

module hdmi_usb3_boot_reset #(
    parameter integer RESTART_AFTER_CYCLES=25000000,
    parameter integer RESTART_HOLD_CYCLES=1000000
)(
    input wire clk, power_reset_n,
    output reg reset_n=1'b0,
    output reg restart_done=1'b0
);
    localparam integer RESTART_END_CYCLES=RESTART_AFTER_CYCLES+RESTART_HOLD_CYCLES;
    localparam integer COUNTER_WIDTH=$clog2(RESTART_END_CYCLES+1);
    reg [COUNTER_WIDTH-1:0] restart_counter=0;
    always @(posedge clk or negedge power_reset_n) begin
        if(!power_reset_n) begin
            restart_counter<=0;
            reset_n<=0;
            restart_done<=0;
        end else begin
            if(restart_counter<RESTART_END_CYCLES)
                restart_counter<=restart_counter+1'b1;
            reset_n<=restart_counter<RESTART_AFTER_CYCLES || restart_counter>=RESTART_END_CYCLES;
            restart_done<=restart_counter>=RESTART_END_CYCLES;
        end
    end
endmodule

module hdmi_usb3_colorbars(
    input wire [11:0] pixel_x,
    input wire data_enable,
    output wire [23:0] pixel_data
);
    wire red=pixel_x<240 || (pixel_x>=720 && pixel_x<960) || (pixel_x>=1200 && pixel_x<1680);
    wire green=pixel_x<960;
    wire blue=pixel_x<480 || (pixel_x>=960 && pixel_x<1440);
    assign pixel_data=data_enable ? {{8{red}},{8{green}},{8{blue}}} : 24'd0;
endmodule

module hdmi_usb3_status_character(
    input wire [3:0] character_index,
    input wire [15:0] flags,
    output reg [7:0] data
);
    wire [3:0] nibble=character_index==5 ? flags[15:12] :
        character_index==6 ? flags[11:8] : character_index==7 ? flags[7:4] : flags[3:0];
    always @* begin
        case(character_index)
            0:data="H";
            1:data="3";
            2:data="D";
            3:data="1";
            4:data=" ";
            9:data=8'h0d;
            10:data=8'h0a;
            default:data=nibble<10 ? 8'd48+{4'd0,nibble} : 8'd55+{4'd0,nibble};
        endcase
    end
endmodule
