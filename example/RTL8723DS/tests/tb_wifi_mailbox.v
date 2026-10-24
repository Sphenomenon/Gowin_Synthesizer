`timescale 1ns/1ps
// Behavioral TAP model for the GW_JTAG documented capture|shift interface.
module GW_JTAG(input tms_pad_i,tck_pad_i,tdi_pad_i,tdo_er1_i,tdo_er2_i,
 output tdo_pad_o,tck_o,tdi_o,test_logic_reset_o,run_test_idle_er1_o,
 run_test_idle_er2_o,shift_dr_capture_dr_o,pause_dr_o,update_dr_o,enable_er1_o,enable_er2_o);
 reg [3:0] state=0;reg [7:0] ir=0,shiftir=0;
 assign tck_o=tck_pad_i;assign tdi_o=tdi_pad_i;
 assign test_logic_reset_o=state==0;
 assign enable_er1_o=ir==8'h42;assign enable_er2_o=0;
 assign run_test_idle_er1_o=state==1 && enable_er1_o;
 assign run_test_idle_er2_o=0;
 assign shift_dr_capture_dr_o=state==3 || state==4;
 assign pause_dr_o=state==6;assign update_dr_o=state==8;
 assign tdo_pad_o=state==11 ? shiftir[0] : tdo_er1_i;
 always @(posedge tck_pad_i) begin
 if(state==10) shiftir<=8'h01;
 if(state==11) shiftir<={tdi_pad_i,shiftir[7:1]};
 if(state==15) ir<=shiftir;
 case(state)
 0:state<=tms_pad_i?0:1;1:state<=tms_pad_i?2:1;2:state<=tms_pad_i?9:3;
 3:state<=tms_pad_i?5:4;4:state<=tms_pad_i?5:4;5:state<=tms_pad_i?8:6;
 6:state<=tms_pad_i?7:6;7:state<=tms_pad_i?8:4;8:state<=tms_pad_i?2:1;
 9:state<=tms_pad_i?0:10;10:state<=tms_pad_i?12:11;11:state<=tms_pad_i?12:11;
 12:state<=tms_pad_i?15:13;13:state<=tms_pad_i?14:13;14:state<=tms_pad_i?15:11;
 15:state<=tms_pad_i?2:1;endcase
 end
endmodule
module tb_wifi_mailbox;
 reg clk=0;always #7 clk=~clk;
 reg tck=0,tms=1,tdi=0;wire tdo,request;wire [95:0] request_data;
 reg reply=0;reg [95:0] reply_data=0;integer requests=0;
 wifi_jtag_mailbox dut(.clk(clk),.tck_pad_i(tck),.tms_pad_i(tms),.tdi_pad_i(tdi),
 .tdo_pad_o(tdo),.request(request),.request_data(request_data),.reply(reply),.reply_data(reply_data));
 always @(posedge clk) begin
 reply<=0;
 if(request) begin
 requests<=requests+1;
 reply_data<={32'b0,request_data[63:32]^request_data[95:64],request_data[31:0]};reply<=1;
 end
 end
 task tick;
 input m,d;
 begin tck=0;tms=m;tdi=d;#31;tck=1;#37;tck=0;#19;end
 endtask
 task scan;
 input [127:0] data;input integer bits;
 output [127:0] got;
 integer i;
 begin
 tick(1,0);tick(0,0);tick(0,0);got=0;
 for(i=0;i<bits;i=i+1) begin
 // Read TDO prior to rising edge, as FTDI MPSSE does.
 tms=i==bits-1;tdi=data[i];#11;got[i]=tdo;tick(tms,tdi);
 end
 tick(1,0);tick(0,0);
 end endtask
 reg [127:0] got;integer i;
 initial begin
 for(i=0;i<6;i=i+1)tick(1,0);tick(0,0);
 tick(1,0);tick(1,0);tick(0,0);tick(0,0);
 for(i=0;i<8;i=i+1) tick(i==7,(8'h42>>i)&1);
 tick(1,0);tick(0,0);
 scan({32'hdeadbeef,32'h76543210,32'h0001237f,32'h47544a57},128,got);
 scan(0,128,got);scan(0,128,got);
 if(got!=={32'b0,32'ha8f98cff,32'h0001237f,32'h31505357} || requests!=1)
 $fatal(1,"reply %h requests %d",got,requests);
 scan({32'h12345678,32'habcdef01,32'h0001247f,32'h47544a57},127,got);
 scan(0,128,got);
 if(requests!=1) $fatal(1,"short packet accepted");
 scan({32'h12345678,32'habcdef01,32'h0001257f,32'h47544a57},128,got);
 scan(0,128,got);scan(0,128,got);
 if(got!=={32'b0,32'hb9f9b979,32'h0001257f,32'h31505357} || requests!=2)
 $fatal(1,"second reply %h requests %d",got,requests);
 $display("PASS mailbox TAP capture/shift/update, async clock handshakes, tags, no duplicates, short rejection");$finish;
 end
endmodule
