`timescale 1ns/1ps
module tb_sampler_ddr;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;logic rst_n=0,restart=0;
  logic [2:0] valid=0,write=0,ready,response;
  logic [31:0] address[3],base[3],capacity[3];logic [255:0] data[3];
  logic [255:0] response_data,req_data,rsp_data=0;logic [7:0] response_error,fault;
  logic req_valid,req_write,req_ready=0,rsp_valid=0;logic [28:0] req_addr;
  logic [15:0] req_tag,rsp_tag=0,old_tag;logic [31:0] latency,beats,stale;
  sampler_ddr #(.MAX_WAIT(12)) dut(.clk(clk),.rst_n(rst_n),.restart(restart),.valid(valid),.write(write),
    .ready(ready),.response(response),.address(address),.base(base),.capacity(capacity),.data(data),
    .response_data(response_data),.response_error(response_error),.req_valid(req_valid),.req_write(req_write),
    .req_ready(req_ready),.req_addr(req_addr),.req_data(req_data),.req_tag(req_tag),.rsp_valid(rsp_valid),
    .rsp_tag(rsp_tag),.rsp_data(rsp_data),.max_latency(latency),.beats(beats),.stale_responses(stale),.fault(fault));
  task automatic request(input integer client);
    @(negedge clk);valid[client]=1;#1;while(!ready[client]) @(negedge clk);
    @(negedge clk);valid[client]=0;while(!req_valid && response==0) @(negedge clk);
  endtask
  task automatic accept;
    while(!req_valid) @(negedge clk);req_ready=1;
    @(negedge clk);req_ready=0;
    if(req_addr[2:0]!=0) $fatal(1,"native BL8 alignment");
  endtask
  task automatic respond(input logic [15:0] tag);
    @(negedge clk);rsp_tag=tag;rsp_data=256'hbadcafe;rsp_valid=1;@(negedge clk);rsp_valid=0;
  endtask
  initial begin
    for(int i=0;i<3;i++) begin address[i]=32'h09800000+i*32;base[i]=32'h09800000;capacity[i]=96;data[i]=i;end
    repeat(3) @(negedge clk);rst_n=1;
    address[0]=32'h097ffff0;request(0);if(response_error!=E_BOUNDS || req_valid) $fatal(1,"guard before pool");
    address[0]=32'h09800001;request(0);if(response_error!=E_BOUNDS) $fatal(1,"unaligned guard");
    address[0]=32'h09800060;request(0);if(response_error!=E_BOUNDS) $fatal(1,"guard end");
    address[0]=32'h09800000;request(0);accept();old_tag=req_tag;
    respond(old_tag^16'h40);if(response!=0 || stale!=1) $fatal(1,"wrong tag delivered");
    @(negedge clk);restart=1;@(negedge clk);restart=0;
    // An issued read is drained, so even 256 epoch wraps cannot alias a new request.
    repeat(256) begin @(negedge clk);restart=1;@(negedge clk);restart=0;end
    if(ready!=0) $fatal(1,"restart must drain issued tag");
    respond(old_tag);if(response!=0 || stale!=2) $fatal(1,"stale epoch");
    request(1);accept();respond(req_tag);if(response!=2 || response_error!=OK) $fatal(1,"client tag demux");
    write[2]=1;request(2);accept();repeat(16) @(negedge clk);respond(req_tag);
    if(response!=4 || response_error!=E_TIMEOUT || fault!=E_TIMEOUT) $fatal(1,"bounded starvation report");
    // Sustained contention services every client once per round.
    valid=7;for(int round=0;round<9;round++) begin
      while(!req_valid) @(negedge clk);old_tag=req_tag;if(req_tag[15:14]!=round%3) $fatal(1,"round robin starvation");accept();respond(old_tag);
    end
    valid=0;
    $display("METRIC ddr_clients=3 completed_beats=%0d rejected_stale=%0d epoch_wrap_restarts=257 timeout_limit=12",beats,stale);
    $display("PASS tb_sampler_ddr");$finish;
  end
  initial begin #100000;$fatal(1,"timeout");end
endmodule
