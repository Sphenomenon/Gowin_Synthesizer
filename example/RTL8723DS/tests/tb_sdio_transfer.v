`timescale 1ns/1ps
module tb_sdio_transfer;
 reg clk=0; always #5 clk=~clk;
 reg resetn=0,start=0;
 reg [5:0] command=53;
 reg [31:0] argument=0;
 tri1 sd_cmd,sd_dat0;
 wire sd_clk,idle,done; wire [3:0] error; wire [31:0] response;
 wire [10:0] tx_address,rx_address; wire [7:0] rx_data;
 wire rx_write;
 reg [7:0] source[0:2047],received[0:2047];
 reg coe=0,cv=1,doe=0,dv=1,sending=0;
 assign sd_cmd=coe ? cv : 1'bz;
 assign sd_dat0=doe ? dv : 1'bz;
 sdio_transfer #(.CLK_HZ(50000000),.SD_HZ(1000000)) dut(
 .clk(clk),.resetn(resetn),.start(start),.command(command),.argument(argument),
 .expect_response(1'b1),.check_crc(1'b1),.wait_busy(1'b0),.sd_clk(sd_clk),
 .sd_cmd(sd_cmd),.sd_dat0(sd_dat0),.idle(idle),.done(done),.error(error),.response(response),
 .tx_address(tx_address),.tx_data(source[tx_address]),.rx_write(rx_write),.rx_address(rx_address),.rx_data(rx_data));
 integer seen=0,bytes_seen=0,scenario=0,length=9,blocks=1;
 reg [47:0] frame=0,reply;
 function [6:0] crc7;
 input [39:0] d; reg [46:0] p; integer k;
 begin p={d,7'b0}; for(k=46;k>=7;k=k-1) if(p[k]) p=p^(47'h89<<(k-7)); crc7=p[6:0]; end
 endfunction
 // Byte polynomial division, independent of the DUT bit-at-a-time function.
 function [15:0] crcbyte;
 input [15:0] c; input [7:0] b; reg [23:0] p; integer k;
 begin p={c^({b,8'b0}),8'b0}; for(k=23;k>=16;k=k-1) if(p[k]) p=p^(24'h11021<<(k-16)); crcbyte=p[15:0]; end
 endfunction
 task command_reply;
 integer k;
 begin
 coe=1;
 for(k=47;k>=0;k=k-1) begin @(negedge sd_clk); #1; cv=reply[k]; end
 @(negedge sd_clk); #1; coe=0;
 end endtask
 task read_payload;
 integer b,j,k,size,base; reg [15:0] crc;
 begin
 repeat(4) @(negedge sd_clk);
 for(b=0;b<blocks;b=b+1) begin
 size=blocks>1 ? 512 : length; base=b*512; crc=0;
 @(negedge sd_clk); #1; doe=1;dv=0;
 for(j=0;j<size;j=j+1) begin
 crc=crcbyte(crc,source[base+j]);
 for(k=7;k>=0;k=k-1) begin @(negedge sd_clk);#1;dv=source[base+j][k];end
 end
 if(length==9 && crc!=16'h31c3) $fatal(1,"invalid CRC model %h",crc);
 if(scenario==1) crc=crc^1;
 for(k=15;k>=0;k=k-1) begin @(negedge sd_clk);#1;dv=crc[k];end
 @(negedge sd_clk);#1;dv=1;
 @(negedge sd_clk);#1;doe=0;
 repeat(3) @(negedge sd_clk);
 end
 end endtask
 task write_payload;
 integer b,j,k,size,base,watch; reg [15:0] crc,gotcrc; reg [7:0] value;
 begin
 for(b=0;b<blocks;b=b+1) begin
 size=blocks>1 ? 512 : length; base=b*512;crc=0;watch=0;
 @(posedge sd_clk);#2;
 while(sd_dat0!==0 && watch<4096) begin @(posedge sd_clk);#2;watch=watch+1;end
 if(watch==4096) $fatal(1,"write start timeout");
 for(j=0;j<size;j=j+1) begin
 value=0;
 for(k=7;k>=0;k=k-1) begin @(posedge sd_clk);#2; value[k]=sd_dat0;end
 if(value!==source[base+j]) $fatal(1,"write payload offset %d: %h != %h",base+j,value,source[base+j]);
 crc=crcbyte(crc,value);
 end
 gotcrc=0;
 for(k=15;k>=0;k=k-1) begin @(posedge sd_clk);#2; gotcrc[k]=sd_dat0;end
 if(gotcrc!==crc) $fatal(1,"write CRC mismatch %h != %h",gotcrc,crc);
 @(posedge sd_clk);#2;if(sd_dat0!==1) $fatal(1,"write end bit");
 repeat(3) @(negedge sd_clk);
 #2;doe=1;dv=0;
 for(k=3;k>=0;k=k-1) begin @(negedge sd_clk);#2;dv=(5'b00101>>k)&1;end
 @(negedge sd_clk);#2;dv=0;
 repeat(5) @(negedge sd_clk);
 #2;dv=1;
 @(negedge sd_clk);#2;doe=0;
 end
 end endtask
 always @(posedge clk) if(rx_write) begin received[rx_address]=rx_data;bytes_seen=bytes_seen+1;end
 always @(posedge sd_clk) begin
 #2;
 if(resetn && !sending && (seen>0 || sd_cmd===0)) begin
 frame={frame[46:0],sd_cmd};seen=seen+1;
 if(seen==48) begin
 seen=0;sending=1;
 if(frame[47:46]!=1 || frame[7:1]!=crc7(frame[47:8]) || !frame[0]) $fatal(1,"command frame %h",frame);
 reply={2'b00,frame[45:40],(scenario==3 ? 32'h100 : 32'd0),7'b0,1'b1};
 reply[7:1]=crc7(reply[47:8]);
 fork
 command_reply();
 begin
 if(command==53 && scenario!=2 && scenario!=3) begin
 // Model DAT beginning before command engine has completed its trailing gap.
 if(argument[31]) begin repeat(52) @(negedge sd_clk);write_payload();end
 else begin repeat(48) @(negedge sd_clk);read_payload();end
 end
 end
 join
 sending=0;
 end
 end
 end
 task run;
 input integer size,writing,which,expected;
 integer i,watch;
 begin
 resetn=0;start=0;doe=0;coe=0;seen=0;bytes_seen=0;sending=0;
 scenario=which;length=size;blocks=size>512 ? size/512 : 1;
 for(i=0;i<2048;i=i+1) begin source[i]=(i*73+19)&255;received[i]=0;end
 if(size==9) for(i=0;i<9;i=i+1) source[i]=8'h31+i;
 command=which==4 ? 52 : 53;
 argument=(writing ? 32'h80000000 : 0)|32'h14000000|(size>512 ? (32'h08000000|blocks) : (size%512));
 repeat(10) @(negedge clk);resetn=1;repeat(10) @(negedge clk);start=1;
 @(negedge clk);start=0;watch=0;
 while(!done && watch<7000000) begin @(negedge clk);watch=watch+1;end
 if(!done || error!=expected) $fatal(1,"size %d write %d scenario %d: done %b error %d",size,writing,which,done,error);
 if(!writing && expected==0 && command==53) begin
 if(bytes_seen!=size) $fatal(1,"read count %d != %d",bytes_seen,size);
 for(i=0;i<size;i=i+1) if(received[i]!==source[i]) $fatal(1,"read mismatch offset %d %h != %h",i,received[i],source[i]);
 end
 $display("PASS CMD%0d length=%0d write=%0d scenario=%0d error=%0d",command,size,writing,which,error);
 wait(!sending); repeat(100) @(negedge clk);
 end endtask
 initial begin
 run(9,0,0,0);run(9,1,0,0);run(512,0,0,0);run(512,1,0,0);
 run(1024,0,0,0);run(1024,1,0,0);run(9,0,1,6);run(9,0,2,4);
 run(9,0,3,9);run(9,0,4,0);
 $display("PASS SDIO transfer: payload, independent CRC, per-block framing, timeout, R5");$finish;
 end
endmodule
