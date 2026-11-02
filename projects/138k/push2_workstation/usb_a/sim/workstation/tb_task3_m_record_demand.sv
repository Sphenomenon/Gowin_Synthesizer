`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
module tb_task3_m_record_demand;
 reg clk=0,reset=0,link=1,panic=0;always #10 clk=!clk;
 reg rxvalid=0;reg [3:0] rxchannel=0;reg [255:0] rxpayload=0;reg [5:0] rxlength=0;
 wire rxready,txvalid;wire [3:0] txchannel;wire [255:0] txpayload;wire [5:0] txlength;
 reg fv=0,frate=0;reg [31:0] fseq=0;
 wire armed,fault;wire [31:0] stale;
 localparam [31:0] MBOOT=32'h13579bdf,WBOOT=32'h2468ace0,SESSION=32'habcd5555,CONFIGGEN=77;
 localparam [95:0] COMMON={MBOOT,SESSION,CONFIGGEN};
 integer txcount=0,checks=0;
 reg [3:0] channels[0:31];reg [255:0] payloads[0:31];
 workstation_task3_m_bus_endpoint #(.RECORD_DEMAND_TIMEOUT_CYCLES(30)) dut(
  .clk_i(clk),.reset_ni(reset),.link_ready_i(link),.panic_i(panic),
  .local_boot_i(MBOOT),.peer_boot_i(WBOOT),.session_i(SESSION),.generation_i(CONFIGGEN),
  .rx_valid_i(rxvalid),.rx_ready_o(rxready),.rx_channel_i(rxchannel),.rx_payload_i(rxpayload),.rx_length_i(rxlength),
  .tx_valid_o(txvalid),.tx_ready_i(1'b1),.tx_channel_o(txchannel),.tx_payload_o(txpayload),.tx_length_o(txlength),
  .analysis_start_i(1'b0),.analysis_cancel_i(1'b0),.analysis_pcm_valid_i(1'b0),.analysis_pcm_last_i(1'b0),.analysis_pcm_i(32'd0),
  .push_score_ready_i(1'b1),.record_arm_i(1'b0),.record_cancel_i(1'b0),
  .frame_valid_i(fv),.frame_44k1_i(frate),.frame_error_i(1'b0),.frame_epoch_i(32'd7),.frame_sequence_i(fseq),.frame_pcm_i(32'h43211234),
  .record_armed_o(armed),.record_fault_o(fault),.phone_owner_idle_i(1'b1),.phone_command_ready_i(1'b1),
  .phone_response_data_i(32'd0),.phone_response_error_i(1'b0),.stale_packets_o(stale));
 always @(posedge clk)if(reset && txvalid)begin
  if(txcount==32)$fatal(1,"unexpected TX loop");
  channels[txcount]=txchannel;payloads[txcount]=txpayload;txcount=txcount+1;
 end
 task automatic tick(input integer n);repeat(n)@(negedge clk);endtask
 task automatic send(input [3:0] ch,input [5:0] len,input [255:0] payload);
  begin @(negedge clk);rxchannel=ch;rxlength=len;rxpayload=payload;rxvalid=1;
   @(negedge clk);while(!rxready)@(negedge clk);rxvalid=0;end
 endtask
 task automatic demand(input [1:0] kind);
  send(`TASK3_PAIR_CH_RECORD_DEMAND,`TASK3_PAIR_RECORD_DEMAND_BYTES,{158'd0,kind,COMMON});
 endtask
 task automatic frame(input [31:0] sample_sequence);
  begin @(negedge clk);fseq=sample_sequence;fv=1;tick(1);fv=0;end
 endtask
 task automatic expect_tx(input integer index,input [1:0] kind,input [31:0] generation);
  integer age;begin age=0;while(txcount<=index && age<100)begin tick(1);age=age+1;end
   if(age==100 || channels[index]!=`TASK3_PAIR_CH_RECORD || payloads[index][195:194]!=kind ||
      payloads[index][193:130]!={MBOOT,SESSION} || payloads[index][129:98]!=generation)$fatal(1,"wrong record TX index%0d kind%0d generation%0d",index,kind,generation);
   checks=checks+1;
  end
 endtask
 initial begin
  tick(3);reset=1;tick(5);
  demand(0);tick(4);if(armed || txcount)$fatal(1,"demand fabricated physical context");checks=checks+1;
  frame(40);expect_tx(0,0,1);
  if(payloads[0][63:0]!={32'd7,32'd41})$fatal(1,"ARM not based on final physical sample");checks=checks+1;
  send(`TASK3_PAIR_CH_RECORD_ACK,`TASK3_PAIR_RECORD_ACK_BYTES,{158'd0,MBOOT,SESSION,32'd1,2'b10});
  frame(41);expect_tx(1,1,1);if(payloads[1][63:32]!=41)$fatal(1,"physical sequence missing");checks=checks+1;
  demand(2);expect_tx(2,2,1);tick(3);if(armed || !fault)$fatal(1,"cancel failed");checks=checks+1;
  frame(50);demand(0);expect_tx(3,0,2);checks=checks+1;
  // Renewed W demand must cancel a stale M tap before the fresh ARM.
  demand(0);expect_tx(4,2,2);expect_tx(5,0,3);
  demand(2);expect_tx(6,2,3);tick(3);
  // Invalid physical format waits locally with finite lifetime and consumes RX.
  frate=1;frame(60);demand(0);tick(40);frate=0;frame(61);tick(10);
  if(txcount!=7 || dut.record_demand_pending)$fatal(1,"expired demand armed late");checks=checks+1;
  send(`TASK3_PAIR_CH_RECORD_DEMAND,`TASK3_PAIR_RECORD_DEMAND_BYTES,{158'd0,2'd0,MBOOT,32'hdeadbeef,CONFIGGEN});tick(4);
  if(stale!=1 || txcount!=7)$fatal(1,"stale demand accepted");checks=checks+1;
  // Cancelling a held demand prevents a later physical sample from arming it.
  frate=1;frame(70);demand(0);demand(2);frate=0;frame(71);tick(10);
  if(txcount!=7 || dut.record_demand_pending)$fatal(1,"cancelled demand armed late");checks=checks+1;
  demand(0);expect_tx(7,0,4);link=0;tick(3);if(armed || !fault)$fatal(1,"link loss did not fence recording");checks=checks+1;
  $display("PASS task3_m_record_demand checks=%0d scenarios=8 real_exporter=1 actual_DAC=0 actual_LCD=0",checks);$finish;
 end
 initial begin #100000;$fatal(1,"timeout");end
endmodule
