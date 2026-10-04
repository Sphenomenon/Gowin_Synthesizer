`timescale 1ns/1ps
// Seed the scanned playlist to isolate the playback entry bound. The sector
// reader remains real RTL with idle MISO; no physical filesystem is claimed.
module tb_scope_tf_bounds;
 reg clk=0,rst_n=0,start=0;
 reg [3:0] track=15;
 wire playing,eof,outen;
 wire [2:0] state;
 always #5 clk=~clk;
 tf_sd_file_reader dut(.clk(clk),.rstn(rst_n),.spi_miso(1'b1),.spi_ssn(),.spi_sck(),.spi_mosi(),
  .card_type(),.card_stat(),.filesystem_type(),.filesystem_stat(state),.scan_done(),.track_count(),
  .track_index(track),.track_start(start),.playing(playing),.eof(eof),.sector_allow(1'b1),.outen(outen),.outbyte(),
  .name_raddr(8'd0),.name_rdata(),.debug_cmdrsp(),.debug_rwrsp(),.debug_cardstate(),.debug_spidone(),.debug_rvalid_session());
 task seed(input integer count);
  @(negedge clk);dut.filesystem_state=3'd7;dut.inflight=0;dut.track_count=5'(count);dut.start_req=0;
 endtask
 task trigger;
  start=1;@(negedge clk);start=0;@(negedge clk);
 endtask
 initial begin
  repeat(4) @(negedge clk);rst_n=1;
  seed(1);trigger();if(playing || !eof || outen || state!=7 || dut.file_size!=0) $fatal(1,"unpopulated track read");
  track=0;seed(0);trigger();if(playing || !eof || state!=7) $fatal(1,"empty playlist read");
  seed(1);dut.cluster_ram[0]=32'd8;dut.size_ram[0]=32'd1024;dut.first_data_sector_no=100;dut.cluster_shift=0;
  trigger();if(!playing || eof || state!=3'd5 || dut.file_size!=1024 || dut.read_sector_no!=108) $fatal(1,"valid track start changed");
  $display("M tf_playlist_bound_checks 3");$display("PASS scope_tf_bounds");$finish;
 end
 initial begin #100000;$fatal(1,"timeout");end
endmodule
