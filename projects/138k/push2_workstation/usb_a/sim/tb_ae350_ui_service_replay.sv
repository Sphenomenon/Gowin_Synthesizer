`timescale 1ns/1ps
// Replays the C host bus transcript against the actual frozen APB owner.
module tb_ae350_ui_service_replay;
 reg clk=0,rst=0,valid=0,wr=0,commit=0,attached=0,iv=0,down=0;
 reg [11:0] addr=0;reg [31:0] data=0;reg [15:0] x=0,y=0;
 wire ready,error,pending,visible,next_visible;wire [31:0] response;wire [28:0] front,next_base;
 always #5 clk=!clk;
 gw138k_ui_services dut(.clk(clk),.reset_n(rst),.command_valid(valid),.command_write(wr),
  .command_address(addr),.command_data(data),.command_strobes(4'hf),.command_ready(ready),
  .response_data(response),.response_error(error),.frame_commit(commit),.input_attached(attached),
  .input_valid(iv),.input_down(down),.input_x(x),.input_y(y),.pending(pending),.visible(visible),
  .next_visible(next_visible),.front_base(front),.next_base(next_base));
 reg [4095:0] path,line;string op;integer fd,status,n=0,reads=0,writes=0,commits=0,resets=0;reg [31:0] a,b;
 initial begin
  if(!$value$plusargs("TRACE=%s",path))$fatal(1,"trace missing");fd=$fopen(path,"r");if(!fd)$fatal(1,"trace open");
  repeat(3)@(negedge clk);rst=1;
  while(!$feof(fd))begin
   status=$fgets(line,fd);status=$sscanf(line,"%s %h %h",op,a,b);n=n+1;
   @(negedge clk);
   if(op=="Z")begin rst=0;@(negedge clk);rst=1;attached=0;resets=resets+1;end
   else if(op=="F")begin commit=1;@(negedge clk);commit=0;commits=commits+1;end
   else if(op=="I")begin attached=a[0];down=a[1];x=b[15:0];y=b[31:16];iv=1;@(negedge clk);iv=0;end
   else if(op=="R" || op=="W")begin
    valid=1;wr=op=="W";addr=a[11:0];data=b;#1;
    if(!ready || error)$fatal(1,"actual APB rejected trace line=%0d addr=%h",n,addr);
    if(!wr && response!==b)$fatal(1,"actual APB read mismatch line=%0d addr=%h got=%h expect=%h",n,addr,response,b);
    if(wr)writes=writes+1;else reads=reads+1;
    @(negedge clk);valid=0;
   end else $fatal(1,"unknown trace operation");
  end
  $fclose(fd);if(reads<1000 || writes<10 || commits<5 || resets!=5)$fatal(1,"trace coverage");
  $display("PASS actual_ui_APB_replay reads=%0d writes=%0d commits=%0d resets=%0d",reads,writes,commits,resets);$finish;
 end
 initial begin #100000000;$fatal(1,"replay watchdog");end
endmodule
