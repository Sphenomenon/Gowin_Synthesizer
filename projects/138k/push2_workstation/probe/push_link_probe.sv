module push_link_probe(input wire clk_50m,button1_n,pc_uart_rx_i,output wire debug_uart_tx,
 output wire push_htclk,push_htreq,push_htvld,input wire push_htrdy,push_hrclk,push_hrreq,push_hrvld,
 output wire push_hrack,inout wire[15:0]push_hd);
 wire [223:0] diagnostic;
 reg[31:0] last_midi,note_ons,bends,ccs;
 wire reset_n;reset_release reset(clk_50m,button1_n,reset_n);
 wire enabled,configured,hs;wire[15:0]vid,pid;wire[6:0]address;wire[7:0]de,me,hstate,ee,he;wire[10:0]dm,mm;
 wire[31:0]replies,errors,ie,packets;wire mv;wire[31:0]midi;
 push2_host_gate gate(clk_50m,!reset_n,pc_uart_rx_i,enabled);
 push2_hspi_link link(.clk(clk_50m),.rst(!reset_n),.host_enable(enabled),
 .htclk(push_htclk),.htreq(push_htreq),.htvld(push_htvld),.htrdy(push_htrdy),.hrclk(push_hrclk),.hrreq(push_hrreq),.hrvld(push_hrvld),.hrack(push_hrack),.hd(push_hd),
 .req_valid(1'b0),.req_ready(),.req_address(7'd8),.req_endpoint(4'd0),.req_data1(1'b0),.req_length(10'd0),
 .tx_valid(1'b0),.tx_ready(),.tx_data(8'd0),.tx_last(1'b0),.out_done(),.out_response(),
 .midi_valid(mv),.midi_ready(1'b1),.midi_event(midi),.configured(configured),.high_speed(hs),.vid(vid),.pid(pid),.address(address),.display_ep(de),.midi_ep(me),.display_mps(dm),.midi_mps(mm),
 .replies(replies),.link_errors(errors),.usb_in_errors(ie),.usb_packets(packets),.host_state(hstate),.enum_error(ee),.hspi_errors(he));
 assign diagnostic={ccs,bends,note_ons,last_midi,5'd0,dm,5'd0,mm,pid,vid,de,me,1'b0,address,7'd0,hs};
 always @(posedge clk_50m or negedge reset_n) begin
  if(!reset_n)begin last_midi<=0;note_ons<=0;bends<=0;ccs<=0;end
  else if(mv)begin
   last_midi<=midi;
   if(midi[15:12]==9 && midi[31:24]!=0)note_ons<=note_ons+1'b1;
   if(midi[15:12]==14)bends<=bends+1'b1;
   if(midi[15:12]==11)ccs<=ccs+1'b1;
  end
 end
 reg[31:0]events;
 always @(posedge clk_50m or negedge reset_n)if(!reset_n)events<=0;else if(mv)events<=events+1'b1;
 wire[223:0]words={errors,ie,32'd0,32'd0,events,replies,he,ee,hstate,4'd0,hs,1'b0,configured,enabled};
 // Extra C350 words carry the actual profile and raw packet for probe diagnosis.
 gw138k_push_performance_uart #(.INTERVAL_CYCLES(5000000)) telemetry(.clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(clk_50m),.audio_reset_n(reset_n),.audio_locked(1'b0),.sample_valid(1'b0),
 .memory_flags(8'd0),.audio_status(32'd0),.video_diagnostics(128'd0),.cpu_clk(clk_50m),.cpu_reset_n(reset_n),.cpu_words(diagnostic),
 .performance_words(448'd0),.usb_clk(clk_50m),.usb_reset_n(reset_n),.usb_words(224'd0),.push_words(words),.performance_feedback(),.serial_out(debug_uart_tx));
endmodule
