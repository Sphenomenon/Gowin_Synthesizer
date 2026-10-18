`timescale 1ns/1ps
// Target the streamed Number Of Completed Packets reduction after replacing
// the large packet register array with a 32-byte prefix and sync H5 reads.
module tb_ble_gatt_completion;
 reg clk=0,resetn=0;
 always #5 clk=~clk;
 reg rx_valid=0;
 reg [3:0]rx_type=0;
 reg [8:0]rx_length=0;
 wire [8:0]rx_addr;
 reg [7:0]rx_data=0;
 reg [7:0]mailbox[0:279];
 wire rx_consume,tx_start;
 wire [3:0]tx_type;
 wire [8:0]tx_length;
 reg tx_done=0;
 wire [7:0]tx_data;
 reg value_valid=0;
 wire value_ready;
 reg [39:0]value_data=40'h403c908080;
 wire connected,subscribed,failed;
 midi_ble_gatt #(.CLK_HZ(1000000)) dut(
  .clk(clk),.resetn(resetn),.enable(1'b1),.local_address(48'h665544332211),
  .rx_valid(rx_valid),.rx_type(rx_type),.rx_length(rx_length),
  .rx_payload_addr(rx_addr),.rx_payload_data(rx_data),.rx_consume(rx_consume),
  .tx_start(tx_start),.tx_type(tx_type),.tx_length(tx_length),
  .tx_ready(1'b1),.tx_done(tx_done),.tx_error(1'b0),
  .tx_payload_addr(9'd8),.tx_payload_data(tx_data),
  .value_tx_valid(value_valid),.value_tx_ready(value_ready),
  .value_tx_data(value_data),.value_tx_length(3'd5),
  .value_rx_valid(),.value_rx_ready(1'b1),.value_rx_data(),.value_rx_length(),
  .connected(connected),.subscribed(subscribed),.failed(failed));
 // Match the actual block-RAM H5 delivered mailbox: one clock read latency.
 always @(posedge clk)rx_data<=rx_addr<280?mailbox[rx_addr]:8'd0;
 integer transmitted=0;
 always @(posedge clk)begin
  tx_done<=tx_start;
  if(resetn && tx_start)begin
   if(tx_type!==2 || tx_length!==16 || tx_data!==8'h1b)
    $fatal(1,"Unexpected GATT transmit while testing ACL credit");
   transmitted=transmitted+1;
  end
  if(resetn && failed)$fatal(1,"GATT failed during completion test");
 end
 localparam [15:0] HANDLE=16'h0345;
 integer i;
 task send_mailbox;
  input [3:0]typ;input integer length;
  begin
   @(negedge clk);rx_type=typ;rx_length=length;rx_valid=1;
   wait(rx_consume);@(negedge clk);rx_valid=0;
   repeat(8)@(negedge clk);
  end
 endtask
 task queue_notification;
  begin
   @(negedge clk);value_data=value_data+40'h0100000000;value_valid=1;
   while(!value_ready)@(negedge clk);
   @(negedge clk);value_valid=0;
  end
 endtask
 task expect_quiet;
  input integer count;
  begin repeat(100)@(negedge clk);
   if(transmitted!=count)$fatal(1,"Invalid completion released credit: got %0d, expected %0d",transmitted,count);
  end
 endtask
 task expect_transmits;
  input integer count;
  integer guard;
  begin
   guard=0;
   while(transmitted<count && guard<100)begin @(negedge clk);guard=guard+1;end
   if(transmitted!=count)$fatal(1,"Valid completion did not release credit: got %0d expected %0d",transmitted,count);
   repeat(8)@(negedge clk);
  end
 endtask
 task completion_event;
  input integer entries,matching_index;
  input [15:0]count;
  input integer malformed;
  integer n,at;
  reg [15:0]entry_handle,entry_count;
  begin
   for(n=0;n<280;n=n+1)mailbox[n]=0;
   mailbox[0]=8'h13;mailbox[1]=1+4*entries;mailbox[2]=entries;
   for(n=0;n<entries;n=n+1)begin
    at=3+4*n;entry_handle=n==matching_index?HANDLE:16'h0200+n;
    entry_count=n==matching_index?count:16'h0003;
    mailbox[at]=entry_handle[7:0];mailbox[at+1]=entry_handle[15:8];
    mailbox[at+2]=entry_count[7:0];mailbox[at+3]=entry_count[15:8];
   end
   if(malformed==1)mailbox[1]=mailbox[1]-1; // bad HCI parameter-length envelope
   if(malformed==2)mailbox[2]=entries-1; // valid envelope, inconsistent Num_Handles
   send_mailbox(4,3+4*entries);
  end
 endtask
 initial begin
  for(i=0;i<280;i=i+1)mailbox[i]=0;
  repeat(4)@(negedge clk);resetn=1;
  // Real connection event, then a CCCD Write Command without an ATT reply.
  mailbox[0]=8'h3e;mailbox[1]=19;mailbox[2]=1;
  mailbox[4]=HANDLE[7:0];mailbox[5]=HANDLE[15:8];send_mailbox(4,21);
  if(!connected)$fatal(1,"Connection event was not parsed with synchronous read");
  mailbox[0]=HANDLE[7:0];mailbox[1]=HANDLE[15:8];mailbox[2]=9;mailbox[3]=0;
  mailbox[4]=5;mailbox[5]=0;mailbox[6]=4;mailbox[7]=0;
  mailbox[8]=8'h52;mailbox[9]=8;mailbox[10]=0;mailbox[11]=1;mailbox[12]=0;
  send_mailbox(2,13);if(!subscribed)$fatal(1,"CCCD Write Command failed");
  queue_notification();expect_transmits(1);queue_notification();expect_quiet(1);
  // All these long events exceed the retained packet prefix and must leave
  // the pending notification blocked, even with positive unrelated counts.
  completion_event(10,-1,1,0);expect_quiet(1);
  completion_event(10,9,0,0);expect_quiet(1);
  completion_event(10,9,1,1);expect_quiet(1);
  completion_event(10,9,1,2);expect_quiet(1);
  // Only final entry matches; a high-byte-only count must still be nonzero.
  completion_event(10,9,16'h0100,0);expect_transmits(2);
  queue_notification();expect_quiet(2);
  // The maximum parameter-length-safe 63-handle event has 255 total bytes,
  // with the matching handle and count at offsets 251..254, far past byte32.
  completion_event(63,62,1,0);expect_transmits(3);
  queue_notification();expect_quiet(3);
  // A match at the first entry must survive all subsequent unrelated entries.
  completion_event(63,0,1,0);expect_transmits(4);
  queue_notification();completion_event(0,-1,0,0);expect_quiet(4);
  // Also ensure stale positive reduction never leaks from the previous event.
  completion_event(10,9,0,0);expect_quiet(4);
  completion_event(1,0,1,0);expect_transmits(5);
  $display("PASS: BLE GATT sync mailbox, 43/255-byte streamed completions, final/first handle, high-byte count, unrelated/zero/malformed isolation and credit-controlled notifications");
  $finish;
 end
 initial begin #1000000;$fatal(1,"GATT completion watchdog");end
endmodule
