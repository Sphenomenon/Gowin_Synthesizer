`timescale 1ns/1ps
`include "vectors.vh"
module tb_sampler_import;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,restart=0,start=0,in_valid=0,in_last=0,in_ready;
  logic [1:0] granularity=1;logic rhythm=0,melody=0,arrangement=0,norm=1;
  logic [31:0] expected_frames=37,expected_crc=`WAV_CRC,base=32'h09800000,capacity=1048576;
  logic [7:0] in_byte=0;logic write_valid,write_ready=0,response=0;
  logic [31:0] addr,write_base,write_capacity,frames,gain,crc;logic [255:0] data;
  logic busy,done;logic [7:0] error;logic [7:0] bytes[`WAV_BYTES];
  integer cycles=0,pending=0,delay=0,writes=0;logic [255:0] saved;
  logic [31:0] actual_crc=32'hffffffff;integer pcm_count=0;
  sampler_import dut(.clk(clk),.rst_n(rst_n),.restart(restart),.start(start),.granularity(granularity),
    .contains_rhythm(rhythm),.contains_melody(melody),.contains_arrangement(arrangement),.normalize(norm),
    .expected_frames(expected_frames),.expected_crc(expected_crc),.base_bytes(base),.capacity_bytes(capacity),
    .in_valid(in_valid),.in_byte(in_byte),.in_last(in_last),.in_ready(in_ready),
    .write_valid(write_valid),.write_ready(write_ready),.write_address(addr),.write_base(write_base),
    .write_capacity(write_capacity),.write_data(data),.response_valid(response),.response_error(8'd0),
    .busy(busy),.done(done),.error(error),.frames(frames),.gain_q16(gain),.crc32(crc));
  always @(negedge clk) begin
    cycles=cycles+1;write_ready=cycles%5==0 && !pending;response=0;
    if(pending) begin delay=delay-1;if(delay==0) begin pending=0;response=1;end end
  end
  always @(posedge clk) if(write_valid && write_ready) begin
    if(addr!=base+writes*32 || addr[4:0]!=0) $fatal(1,"packed address progression");
    pending=1;delay=7;writes=writes+1;saved=data;
    for(int i=0;i<16;i++) if(pcm_count<37) begin
      if($signed(data[i*16+:16])!=pcm_count*301-5000) $fatal(1,"PCM decode mismatch");
      actual_crc=crc_byte(crc_byte(actual_crc,data[i*16+:8]),data[i*16+8+:8]);pcm_count=pcm_count+1;
    end else if(data[i*16+:16]!=0) $fatal(1,"partial BL8 zero padding");
  end
  task automatic launch;
    @(negedge clk);start=1;@(negedge clk);start=0;
  endtask
  task automatic feed(input integer size);
    for(int i=0;i<size;i++) begin
      @(negedge clk);while(!in_ready && busy) @(negedge clk);
      if(!busy) break;
      in_valid=1;in_byte=bytes[i];in_last=i==size-1;
      @(negedge clk);in_valid=0;in_last=0;
    end
    while(busy) @(negedge clk);
  endtask
  initial begin
    $readmemh("wav.mem",bytes);repeat(3) @(negedge clk);rst_n=1;
    launch();feed(`WAV_BYTES);
    if(error!=OK || frames!=37 || writes!=3 || crc!=`WAV_CRC || crc!=~actual_crc || gain!=32'h7fff0000/5836)
      $fatal(1,"valid normalized import err=%d frames=%d writes=%d gain=%d crc=%h",error,frames,writes,gain,crc);
    rhythm=1;launch();if(error!=E_POLICY || busy) $fatal(1,"breakbeat declaration accepted");rhythm=0;
    melody=1;launch();if(error!=E_POLICY) $fatal(1,"phrase accepted");melody=0;
    arrangement=1;launch();if(error!=E_POLICY) $fatal(1,"arrangement accepted");arrangement=0;
    granularity=0;launch();if(error!=E_POLICY) $fatal(1,"missing declaration");granularity=1;
    expected_frames=288001;launch();if(error!=E_POLICY) $fatal(1,"duration policy");expected_frames=37;
    capacity=32;launch();if(error!=E_BOUNDS) $fatal(1,"overflow reservation");capacity=1048576;
    writes=0;pcm_count=0;actual_crc=32'hffffffff;expected_crc=0;launch();feed(`WAV_BYTES);
    if(error!=E_CRC) $fatal(1,"CRC accepted");expected_crc=`WAV_CRC;
    writes=0;pcm_count=0;actual_crc=32'hffffffff;launch();feed(`WAV_BYTES-4);
    if(error!=E_TRUNCATED) $fatal(1,"truncation accepted %d",error);
    bytes[24]=8'h44;bytes[25]=8'hac;bytes[26]=0;bytes[27]=0; //44100
    writes=0;pcm_count=0;launch();feed(`WAV_BYTES);
    if(error!=E_FORMAT) $fatal(1,"unsupported rate silently accepted");
    bytes[24]=8'h80;bytes[25]=8'hbb;granularity=1;
    launch();@(negedge clk);restart=1;@(negedge clk);restart=0;
    if(busy || write_valid) $fatal(1,"restart leaked import");
    $display("METRIC imported_frames=37 pcm_bytes=74 packed_beats=3 policy_rejections=5 explicit_format_errors=1 crc_rejections=1 truncation_rejections=1");
    $display("PASS tb_sampler_import");$finish;
  end
  initial begin #200000;$fatal(1,"timeout");end
endmodule
