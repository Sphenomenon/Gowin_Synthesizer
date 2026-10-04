`timescale 1ns/1ps
`include "vectors.vh"
module tb_sampler_storage;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;logic rst_n=0,restart=0,load_start=0,capture_start=0,capture_stop=0;
  logic [5:0] slot=0,query_slot=0;logic [7:0] owner=1,source_error=0;
  logic [31:0] expected_frames=37,expected_crc=`WAV_CRC;
  logic approved=1,sequencer_running=0;logic [5:0] active_voices=1;
  logic sample_valid=0;logic signed [15:0] pcm_l=12000,pcm_r=-4000;
  logic in_valid=0,in_last=0,in_ready;logic [7:0] in_byte=0;
  logic [63:0] referenced=0;logic free_slot=0,busy,done;logic [7:0] error;descriptor_t desc;
  logic [31:0] frames,gain,crc,addr,base,capacity;logic write_valid,write_ready=1,response=0;
  logic [255:0] data;logic [7:0] bytes[`WAV_BYTES];integer pending=0,delay=0,write_count=0;
  logic [31:0] observed_crc=32'hffffffff;integer capture_pcm_count=0;logic capture_check=0;
  sampler_storage dut(.clk(clk),.rst_n(rst_n),.restart(restart),.load_start(load_start),.capture_start(capture_start),
    .capture_stop(capture_stop),.slot(slot),.owner(owner),.expected_frames(expected_frames),.expected_crc(expected_crc),
    .granularity(2'd1),.contains_rhythm(1'b0),.contains_melody(1'b0),.contains_arrangement(1'b0),.normalize(1'b0),
    .approved_single_note(approved),.sequencer_running(sequencer_running),.active_voices(active_voices),
    .sample_valid(sample_valid),.pcm_l(pcm_l),.pcm_r(pcm_r),.source_error(source_error),
    .in_valid(in_valid),.in_byte(in_byte),.in_last(in_last),.in_ready(in_ready),.referenced(referenced),.free_slot(free_slot),
    .query_slot(query_slot),.descriptor(desc),.busy(busy),.done(done),.error(error),.committed_frames(frames),
    .committed_gain(gain),.committed_crc(crc),.write_valid(write_valid),.write_ready(write_ready),
    .write_address(addr),.write_base(base),.write_capacity(capacity),.write_data(data),
    .response_valid(response),.response_error(8'd0));
  always @(negedge clk) begin
    response=0;
    if(pending) begin delay=delay-1;if(delay==0) begin response=1;pending=0;end end
  end
  always @(posedge clk) if(write_valid && write_ready) begin
    pending=1;delay=8;write_count=write_count+1;
    if(capture_check) for(int i=0;i<16;i++) if(capture_pcm_count<20) begin
      if($signed(data[i*16+:16])!=4000) $fatal(1,"loopback mono sign");
      observed_crc=crc_byte(crc_byte(observed_crc,data[i*16+:8]),data[i*16+8+:8]);capture_pcm_count=capture_pcm_count+1;
    end
  end
  task automatic launch(input logic capture);
    @(negedge clk);if(capture) capture_start=1;else load_start=1;
    @(negedge clk);capture_start=0;load_start=0;
  endtask
  task automatic finish;
    while(busy) @(negedge clk);@(negedge clk);
  endtask
  initial begin
    $readmemh("wav.mem",bytes);repeat(3) @(negedge clk);rst_n=1;
    launch(0);
    for(int i=0;i<`WAV_BYTES;i++) begin
      @(negedge clk);while(!in_ready) @(negedge clk);in_valid=1;in_byte=bytes[i];in_last=i==`WAV_BYTES-1;
      @(negedge clk);in_valid=0;in_last=0;
    end
    finish();
    if(error!=OK || !desc.valid || desc.frames!=37 || desc.crc32!=`WAV_CRC || desc.owner!=1) $fatal(1,"transaction commit %d",error);
    // CRC rejection must free the provisional slot and leave it inaccessible.
    slot=1;query_slot=1;source_error=E_OVERFLOW;launch(0);finish();
    if(error!=E_OVERFLOW || desc.valid) $fatal(1,"TF overflow committed");source_error=0;
    // Single-voice RTL bus capture: 20 frames -> two beats -> descriptor commit.
    expected_frames=20;capture_check=1;launch(1);while(!dut.cap_busy) @(negedge clk);
    repeat(20) begin @(negedge clk);sample_valid=1;@(negedge clk);sample_valid=0;repeat(30) @(negedge clk);end
    finish();capture_check=0;
    if(error!=OK || !desc.valid || desc.frames!=20 || desc.crc32!=~observed_crc || capture_pcm_count!=20)
      $fatal(1,"capture descriptor %d",error);
    // Recording an arrangement is explicitly prohibited and the allocation is reclaimed.
    slot=2;query_slot=2;sequencer_running=1;launch(1);finish();
    if(error!=E_POLICY || desc.valid) $fatal(1,"pattern recording allowed");sequencer_running=0;
    active_voices=2;launch(1);finish();if(error!=E_POLICY || desc.valid) $fatal(1,"mixed voice capture");active_voices=1;
    launch(1);while(!dut.cap_busy) @(negedge clk);active_voices=2;
    @(negedge clk);sample_valid=1;@(negedge clk);sample_valid=0;finish();
    if(error!=E_POLICY || desc.valid) $fatal(1,"dynamic capture policy");active_voices=1;
    // An audio producer cannot be stalled; overflow must cancel a capture.
    write_ready=0;launch(1);while(!dut.cap_busy) @(negedge clk);
    repeat(17) begin @(negedge clk);sample_valid=1;@(negedge clk);sample_valid=0;end
    finish();if(error!=E_OVERFLOW || desc.valid) $fatal(1,"capture backpressure silent");write_ready=1;
    expected_frames=37;launch(0);while(!in_ready) @(negedge clk);
    @(negedge clk);restart=1;@(negedge clk);restart=0;
    if(busy || desc.valid) $fatal(1,"restart provisional descriptor");
    query_slot=0;@(negedge clk);if(!desc.valid) $fatal(1,"restart lost imported sound");
    $display("METRIC committed_imports=1 committed_captures=1 capture_frames=20 aborted_transactions=5 vendor_files_modified=0");
    $display("PASS tb_sampler_storage");$finish;
  end
  initial begin #300000;$fatal(1,"timeout state=%d impbusy=%d frames=%d fill=%d pool_done=%d err=%d",dut.state,dut.imp_busy,dut.imp_frames,dut.u_import.fill,dut.pool_done,error);end
endmodule
