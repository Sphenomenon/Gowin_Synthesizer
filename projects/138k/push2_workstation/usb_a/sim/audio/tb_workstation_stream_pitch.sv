`timescale 1ns/1ps
module tb;
`ifdef WORKSTATION_SDP_VENDOR_SIM
GSR GSR(.GSRI(1'b1));
`endif
reg clk=0;always #5 clk=~clk;
reg rst=0,clear=0,valid=0,enable=0;reg [21:0] ratio=1048576;
reg signed [31:0] l=0,r=0;wire ready,quiet,outvalid,fault;wire signed[31:0] ol,orr;
workstation_stream_pitch dut(.clk_i(clk),.rst_ni(rst),.clear_i(clear),.valid_i(valid),.enable_i(enable),.ratio_q20_i(ratio),.left_i(l),.right_i(r),.ready_o(ready),.quiescent_o(quiet),.valid_o(outvalid),.fault_o(fault),.left_o(ol),.right_o(orr));
integer fi,fo,n,code,ri,en,li,rr,clear_after,gap,waited,tick=0,index=0,got,overrun;
initial begin
 fi=$fopen("input.txt","r");fo=$fopen("output.txt","w");
 repeat(3)@(negedge clk);rst=1;
 while(!$feof(fi))begin
  n=$fscanf(fi,"%d %d %d %d %d %d %d %d\n",code,ri,en,li,rr,clear_after,gap,overrun);
  if(n!=8)begin
   if($feof(fi))begin $fclose(fi);$fclose(fo);$display("PASS stream pitch requests=%0d",index);$finish;end
   else $fatal(1,"bad fixture row");
  end
  if(code==0)begin
   clear=1;@(negedge clk);clear=0;#1;
   if(outvalid||!ready||fault)$fatal(1,"clear failed");
   $fwrite(fo,"C\n");
  end else begin
   if(!ready)$fatal(1,"not ready between frames");
   valid=1;ratio=ri;enable=en;l=li;r=rr;@(negedge clk);valid=0;waited=0;got=0;
   while(waited<45)begin
    if(clear_after>0 && waited==clear_after)clear=1;
    else clear=0;
    if(overrun && waited==2)valid=1;else valid=0;
    if(outvalid)begin
     if(got)$fatal(1,"duplicate output");got=1;
     $fwrite(fo,"R %0d %0d %0d %0d %0d\n",index,ol,orr,waited,fault);
    end
    @(negedge clk);waited=waited+1;
   end
   clear=0;valid=0;
   if(clear_after>0)begin if(got)$fatal(1,"cancel published a result");$fwrite(fo,"X %0d\n",index);end
   else if(!got)$fatal(1,"missed sample");
   if(!ready)$fatal(1,"stuck pipeline");
   if(fault!=overrun)$fatal(1,"unexpected fault state");
   repeat(gap)@(negedge clk);
   index=index+1;
  end
 end
 $fclose(fi);$fclose(fo);$display("PASS stream pitch requests=%0d",index);$finish;
end
endmodule
