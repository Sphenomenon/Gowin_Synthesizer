// Diagnostic surface: real USB/HSPI/display/control logic; no audio/HDMI.
module push_surface_probe(input wire clk_50m,button1_n,pc_uart_rx_i,output wire debug_uart_tx,
 output wire push_htclk,push_htreq,push_htvld,input wire push_htrdy,push_hrclk,push_hrreq,push_hrvld,
 output wire push_hrack,inout wire[15:0]push_hd);
 wire reset_n;reset_release reset(clk_50m,button1_n,reset_n);
 wire av;wire[17:0]ae;wire[223:0]words;
 // Fixed diagnostic status only. Acceptance of audio controls uses full build.
 wire[447:0]feedback={224'd0,160'd0,32'h64000000,32'd0};
 push2_surface u_push(.clk(clk_50m),.rst(!reset_n),.audio_clk(clk_50m),.audio_reset_n(reset_n),.pc_rx(pc_uart_rx_i),.performance_words(feedback),
 .htclk(push_htclk),.htreq(push_htreq),.htvld(push_htvld),.htrdy(push_htrdy),.hrclk(push_hrclk),.hrreq(push_hrreq),.hrvld(push_hrvld),.hrack(push_hrack),.hd(push_hd),
 .audio_valid(av),.audio_ready(1'b1),.audio_event(ae),.telemetry(words));
 reg[31:0]events,last_event;
 always @(posedge clk_50m or negedge reset_n)if(!reset_n)begin events<=0;last_event<=0;end else if(av)begin events<=events+1'b1;last_event<={14'd0,ae};end
 wire[223:0]diagnostic={32'd0,32'd0,32'd0,32'd0,last_event,events,32'h44494147};
 gw138k_push_performance_uart #(.INTERVAL_CYCLES(5000000)) telemetry(.clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(clk_50m),.audio_reset_n(reset_n),.audio_locked(1'b0),.sample_valid(1'b0),
 .memory_flags(8'd0),.audio_status(32'd0),.video_diagnostics(128'd0),.cpu_clk(clk_50m),.cpu_reset_n(reset_n),.cpu_words(diagnostic),
 .performance_words(feedback),.usb_clk(clk_50m),.usb_reset_n(reset_n),.usb_words(224'd0),.push_words(words),.performance_feedback(),.serial_out(debug_uart_tx));
endmodule
