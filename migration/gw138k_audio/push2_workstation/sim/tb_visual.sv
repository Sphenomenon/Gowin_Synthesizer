`timescale 1ns/1ps
module tb_visual;
 reg clk=0,rst=1;always #10 clk=~clk;
 wire cv,cr;wire[1:0]ck;wire[6:0]ci;wire[7:0]val;wire session;
 wire fs,fr,fd,pv,pr;wire[15:0]px;wire[9:0]x;wire[7:0]y;
 wire req,txv,last,data1;wire[6:0]addr;wire[3:0]ep;wire[9:0]len;wire[7:0]data;
 reg done=0;reg[2:0]response=1;reg busy=0;wire fault;wire[3:0]fc;wire[31:0]frames,commands;
 push2_lights lights(clk,rst||!session,64'h0000000000000101,32'h64000097,cv,cr,ck,ci,val);
 push2_surface_pixels pixels(clk,rst||!session,fr,fs,x,y,pv,px,32'h64000097,32'h020101f0,64'h0000000000000101,7'd60,7'd100);
 push2_driver_core core(.clk(clk),.rst(rst),.usb_configured(!rst),.usb_high_speed(1'b1),.usb_vid(16'h2982),.usb_pid(16'h1967),
 .usb_address(7'd8),.usb_display_out(8'd1),.usb_display_mps(11'd512),.usb_midi_out(8'd2),.usb_midi_mps(11'd512),.session_ready(session),
 .cmd_valid(cv),.cmd_ready(cr),.cmd_kind(ck),.cmd_index(ci),.cmd_value(val),.cmd_cable(4'd0),.frame_start(fs),.frame_ready(fr),.frame_done(fd),
 .pixel_valid(pv),.pixel_ready(pr),.pixel_bgr565(px),.pixel_x(x),.pixel_y(y),.usb_rx_valid(1'b0),.usb_rx_ready(),.usb_rx_event(32'd0),
 .event_valid(),.event_ready(1'b1),.event_kind(),.event_channel(),.event_cable(),.event_data1(),.event_data2(),.event_pitch(),
 .out_req_valid(req),.out_req_ready(!busy),.out_device_address(addr),.out_endpoint(ep),.out_data1(data1),.out_length(len),
 .out_valid(txv),.out_ready(busy),.out_data(data),.out_last(last),.out_done(done),.out_response(response),.busy(),.fault(fault),.fault_code(fc),
 .packets_acked(),.nak_count(),.retry_count(),.frames_acked(frames),.pixels_accepted(),.commands_acked(commands),.commands_rejected(),.events_received(),.packets_ignored());
 integer fpix,fout,fmidi,n=0,pixcount=0,dispbytes=0,npacket=0;reg[9:0]expected_len;reg[3:0]endpoint;
 reg[7:0]buffer[0:511];reg[2:0]toggles=0;reg nak_once=0;
 initial begin fpix=$fopen("pixels.bgr565","wb");fout=$fopen("display.usb","wb");fmidi=$fopen("lights.usb","wb");#100;rst=0;end
 always @(posedge clk)begin
  done<=0;
  if(pv&&pr)begin $fwrite(fpix,"%c%c",px[7:0],px[15:8]);pixcount=pixcount+1;end
  if(req&&!busy)begin
   if(addr!=8||len==0||len>512||data1!=toggles[ep])$fatal(1,"USB request or PID invalid");
   expected_len<=len;endpoint<=ep;n=0;busy<=1;
  end
  if(txv&&busy)begin
   buffer[n]=data;n=n+1;
   if(last)begin
    if(n!=expected_len)$fatal(1,"wrong USB length");
    busy<=0;done<=1;
    if(!nak_once && endpoint==1)begin nak_once<=1;response<=2;end
    else begin
     response<=1;toggles[endpoint]<=~toggles[endpoint];npacket=npacket+1;
     for(integer k=0;k<n;k=k+1)begin
      if(endpoint==1)begin $fwrite(fout,"%c",buffer[k]);dispbytes=dispbytes+1;end
      else $fwrite(fmidi,"%c",buffer[k]);
     end
    end
   end
  end
  if(fault)$fatal(1,"visual fault %d",fc);
  if(fd)begin
   if(pixcount!=153600 || dispbytes!=327696 || commands<84)$fatal(1,"incomplete frame/lights %d %d %d",pixcount,dispbytes,commands);
   $fclose(fpix);$fclose(fout);$fclose(fmidi);
   $display("PASS complete Push screen 327696 bytes, 153600 pixels, MIDI brightness/mode/touch-strip/80 lights, independent PID and NAK retry");$finish;
  end
 end
 initial begin #100000000;$fatal(1,"visual timeout");end
endmodule
