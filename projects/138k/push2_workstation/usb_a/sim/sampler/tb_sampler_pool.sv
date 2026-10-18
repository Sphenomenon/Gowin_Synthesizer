`timescale 1ns/1ps
module tb_sampler_pool;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,restart=0,reserve=0,commit=0,abort_slot=0,free_slot=0,done;
  logic [5:0] slot=0,query_slot=0;logic [7:0] owner=1,error,epoch;
  logic [31:0] bytes=32,frames=16,gain=65536,crc=32'h12345678,base,capacity;
  logic [63:0] referenced=0;descriptor_t desc;
  sampler_pool #(.GRANULE(32),.GRANULES(4)) pool(.clk(clk),.rst_n(rst_n),.restart(restart),.reserve(reserve),
    .slot(slot),.owner(owner),.bytes(bytes),.commit(commit),.abort_slot(abort_slot),.free_slot(free_slot),
    .frames(frames),.gain_q16(gain),.crc32(crc),.referenced(referenced),.done(done),.error(error),
    .query_slot(query_slot),.descriptor(desc),.reserved_base(base),.reserved_capacity(capacity),.epoch(epoch));
  task automatic alloc(input integer s,n,expected);
    @(negedge clk);slot=6'(s);query_slot=slot;bytes=n;reserve=1;
    @(negedge clk);reserve=0;while(!done) @(negedge clk);if(error!=expected) $fatal(1,"allocation %d err=%d",s,error);
  endtask
  task automatic publish;
    @(negedge clk);commit=1;@(negedge clk);commit=0;
    if(error!=OK || !desc.valid || desc.crc32!=crc || desc.gain_q16!=gain) $fatal(1,"commit");
  endtask
  task automatic release_slot(input integer s,expected);
    @(negedge clk);slot=6'(s);free_slot=1;@(negedge clk);free_slot=0;
    if(error!=expected) $fatal(1,"free %d err=%d",s,error);
  endtask
  initial begin
    repeat(3) @(negedge clk);rst_n=1;
    alloc(0,32,OK);publish();alloc(1,33,OK);publish();alloc(2,32,OK);publish();
    alloc(3,1,E_CAPACITY);referenced=1;release_slot(0,E_BUSY);referenced=0;
    owner=2;release_slot(0,E_TAG);owner=1;release_slot(0,OK);alloc(3,1,OK);
    if(base!=32'h09800000) $fatal(1,"cursor wrap must reclaim first granule");
    frames=17;@(negedge clk);commit=1;@(negedge clk);commit=0;if(error!=E_BOUNDS) $fatal(1,"bounds");frames=16;
    @(negedge clk);restart=1;@(negedge clk);restart=0;
    if(epoch!=1 || desc.valid) $fatal(1,"restart cancels reservation");
    query_slot=1;@(negedge clk);if(!desc.valid) $fatal(1,"restart lost committed sample");
    alloc(4,32,OK);publish();alloc(5,32,E_CAPACITY);release_slot(1,OK);
    alloc(5,64,OK);publish();
    $display("METRIC allocator_granules=4 wrap_reallocations=2 epoch=1 guarded_rejections=5");
    $display("PASS tb_sampler_pool");$finish;
  end
endmodule
