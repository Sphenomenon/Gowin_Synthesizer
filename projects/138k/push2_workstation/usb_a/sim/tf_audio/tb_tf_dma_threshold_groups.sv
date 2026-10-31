`timescale 1ns/1ps
module tb_tf_dma_threshold_groups;
 parameter [31:0] BANK_BYTES=64;
 localparam [31:0] CAPACITY=BANK_BYTES+BANK_BYTES;
 reg [31:0] value=0;
 reg [5:0] pending=0;
 reg eof=0;
 integer i,j,k,e,p,v,checks=0;
 workstation_tf_runtime_dma #(.AUDIO_BANK_BYTES(BANK_BYTES)) dut(
  .clk(1'b0),.rst_n(1'b0),.mem_ready(1'b0),.capture_done_toggle(1'b0),.restart_toggle(1'b0),
  .file_size_bytes(32'b0),.fifo_in_empty(1'b1),.fifo_in_rd_valid(1'b0),.fifo_in_rd_data(8'b0),
  .fifo_out_full(1'b0),.app_rdy(1'b0),.app_wrdy(1'b0),.app_rvalid(1'b0),.app_rdata(256'b0),.runtime_hold_i(1'b0));
 function quad(input [1:0] c);begin case(c)0:quad=0;1:quad=1;2:quad=1'bx;3:quad=1'bz;endcase end endfunction
 function old_capacity(input [31:0] occupancy,input [5:0] amount);
  reg [6:0] low_sum;
  reg [25:0] upper_plus;
  reg upper_less,upper_equal,incremented_less,incremented_equal;
  begin
   low_sum={1'b0,occupancy[5:0]}+{1'b0,amount};
   upper_plus=occupancy[31:6]+26'd1;
   upper_less=occupancy[31:6]<CAPACITY[31:6];
   upper_equal=occupancy[31:6]==CAPACITY[31:6];
   incremented_less=upper_plus<CAPACITY[31:6];
   incremented_equal=upper_plus==CAPACITY[31:6];
   old_capacity=low_sum[6] ? (incremented_less||(incremented_equal&&low_sum[5:0]<=CAPACITY[5:0])) :
                            (upper_less||(upper_equal&&low_sum[5:0]<=CAPACITY[5:0]));
  end
 endfunction
 task check;
  begin #1;
   if(dut.read_has_full_beat !== (value>=32'd32))
    $fatal(1,"threshold full differs value=%h got=%b expected=%b",value,dut.read_has_full_beat,(value>=32'd32));
   if(dut.read_has_partial_beat !== (eof&&(value!=0)))
    $fatal(1,"threshold partial differs value=%h",value);
   if(dut.read_chunk_bytes !== ((eof&&(value<32'd32))?value[5:0]:6'd32))
    $fatal(1,"threshold chunk differs value=%h eof=%b got=%b expected=%b",value,eof,dut.read_chunk_bytes,((eof&&(value<32'd32))?value[5:0]:6'd32));
   if(dut.ring_can_commit !== old_capacity(value,pending))
    $fatal(1,"threshold capacity differs value=%h pending=%b got=%b expected=%b",value,pending,dut.ring_can_commit,old_capacity(value,pending));
   checks=checks+4;
  end
 endtask
 task pending_cases;
  begin
   for(p=0;p<8;p=p+1)begin
    case(p)0:pending=0;1:pending=1;2:pending=31;3:pending=32;4:pending=63;5:pending=6'bx00000;6:pending=6'b00000x;7:pending=6'bzzzzzz;endcase
    for(e=0;e<4;e=e+1)begin eof=quad(2'(e));check();end
   end
  end
 endtask
 initial begin
  force dut.available_bytes=value;force dut.pending_bytes=pending;force dut.eof_finalized=eof;
  for(v=0;v<256;v=v+1)begin value=32'(v);pending_cases();end
  for(i=0;i<32;i=i+1)begin
   value=32'b1<<i;pending_cases();value=~(32'b1<<i);pending_cases();
   for(j=-1;j<32;j=j+1)for(k=2;k<4;k=k+1)begin
    value=0;if(j>=0)value[j]=1;value[i]=quad(2'(k));pending_cases();
   end
  end
  for(v=0;v<4096;v=v+1)begin
   value=CAPACITY;value[6]=quad(v[1:0]);value[12]=quad(v[3:2]);value[19]=quad(v[5:4]);
   value[26]=quad(v[7:6]);value[27]=quad(v[9:8]);value[31]=quad(v[11:10]);pending_cases();
  end
  value='x;pending_cases();value='z;pending_cases();
  $display("PASS threshold capacity four-state: bank=%0d checks=%0d vectors=%0d",BANK_BYTES,checks,checks/4);
  $finish;
 end
endmodule
