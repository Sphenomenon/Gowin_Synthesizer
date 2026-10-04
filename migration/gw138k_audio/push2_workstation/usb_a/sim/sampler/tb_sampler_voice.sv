`timescale 1ns/1ps
module tb_sampler_voice;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,restart=0,panic=0,tick=0,ev=0;logic [17:0] event_data=0;
  pad_t pad;descriptor_t desc;logic ready,rv,rr,rsp,pcm_valid;
  logic [31:0] ra,rb,rc;logic [255:0] rd;logic [7:0] re;
  logic signed [15:0] l,r;logic [15:0] mask;logic [63:0] referenced;
  logic [5:0] count;logic [31:0] misses,reads,cycles;logic [7:0] err;
  logic [1:0] cv,cw,cr,cresponse;logic [31:0] addresses[2],bases[2],capacities[2];logic [255:0] datas[2];
  logic req_valid,req_write,req_ready=0,rsp_valid=0;logic [28:0] req_addr;logic [255:0] req_data,rsp_data=0;
  logic [15:0] req_tag,rsp_tag=0;logic [31:0] max_latency,beats,stale;logic [7:0] fault;
  integer cycle=0,pending=0,delay=0,wait_clocks=0;
  logic [28:0] saved_addr;logic [15:0] saved_tag;
  integer max_frame_beats=0,baseline=0,concurrent_cycles=0;
  integer voice_read_age=0,voice_grant_age=0,max_voice_read_latency=0,max_voice_grant_wait=0;logic voice_pending=0;
  sampler_voice dut(.clk(clk),.rst_n(rst_n),.restart(restart),.panic(panic),.sample_tick(tick),
    .event_valid(ev),.event_data(event_data),.event_pad(pad),.event_descriptor(desc),.event_ready(ready),
    .read_valid(rv),.read_ready(rr),.read_address(ra),.read_base(rb),.read_capacity(rc),
    .response_valid(rsp),.response_data(rd),.response_error(re),.pcm_valid(pcm_valid),.pcm_l(l),.pcm_r(r),
    .active_mask(mask),.referenced(referenced),.active_count(count),.deadline_misses(misses),.read_beats(reads),
    .frame_cycles_max(cycles),.error(err));
  assign cv={1'b1,rv};assign cw=0;assign rr=cr[0];assign rsp=cresponse[0];
  assign addresses[0]=ra;assign bases[0]=rb;assign capacities[0]=rc;assign datas[0]=0;
  assign addresses[1]=32'h09801000;assign bases[1]=32'h09800000;assign capacities[1]=1048576;assign datas[1]=0;
  sampler_ddr #(.CLIENTS(2),.MAX_WAIT(18)) bus(.clk(clk),.rst_n(rst_n),.restart(restart),.valid(cv),.write(cw),
    .address(addresses),.base(bases),.capacity(capacities),.data(datas),.ready(cr),.response(cresponse),
    .response_data(rd),.response_error(re),.req_valid(req_valid),.req_write(req_write),.req_ready(req_ready),
    .req_addr(req_addr),.req_data(req_data),.req_tag(req_tag),.rsp_valid(rsp_valid),.rsp_tag(rsp_tag),.rsp_data(rsp_data),
    .max_latency(max_latency),.beats(beats),.stale_responses(stale),.fault(fault));
  function automatic integer wave_at(input integer index);
    integer i;i=index%64;return i<32 ? i*800-12000 : (64-i)*800-12000;
  endfunction
  always @(negedge clk) begin
    cycle=cycle+1;rsp_valid=0;req_ready=(cycle%7==0) && !pending;
    if(pending) begin
      delay=delay-1;
      if(delay==0) begin
        pending=0;rsp_valid=1;rsp_tag=saved_tag;
        for(int i=0;i<16;i++) rsp_data[i*16+:16]=16'(wave_at(((saved_addr*4-32'h09800000)/2)+i));
      end
    end
  end
  always @(posedge clk) if(req_valid && req_ready) begin
    pending=1;delay=9+cycle%5;saved_addr=req_addr;saved_tag=req_tag;
  end
  always @(posedge clk) begin
    if(rv && !voice_pending) begin voice_pending=1;voice_read_age=0;voice_grant_age=0;end
    if(voice_pending) begin
      voice_read_age=voice_read_age+1;
      if(rv && !rr) voice_grant_age=voice_grant_age+1;
      if(rv && rr && voice_grant_age>max_voice_grant_wait) max_voice_grant_wait=voice_grant_age;
      if(rsp) begin
        if(voice_read_age>max_voice_read_latency) max_voice_read_latency=voice_read_age;
        voice_pending=0;
      end
    end
  end
  task automatic send(input integer kind,note,vel);
    @(negedge clk);while(!ready) @(negedge clk);
    event_data={4'(kind),7'(note),7'(vel)};ev=1;
    @(negedge clk);ev=0;
  endtask
  task automatic frame;
    integer before_reads,clocks;
    @(negedge clk);before_reads=reads;tick=1;
    @(negedge clk);tick=0;clocks=0;
    while(!pcm_valid) begin @(negedge clk);clocks=clocks+1;if(clocks>1590) $fatal(1,"deadline exceeded %d",clocks);end
    if(reads-before_reads>max_frame_beats) max_frame_beats=reads-before_reads;
    repeat(1600-clocks-1) @(negedge clk);
  endtask
  task automatic clear;
    @(negedge clk);panic=1;@(negedge clk);panic=0;
  endtask
  real ideal;integer expected;logic [47:0] model_phase;integer frac,aa,bb;
  initial begin
    pad='0;desc='0;
    pad.slot=0;pad.root_note=64;pad.play_mode=LOOPED;pad.trim_end=64;pad.loop_end=64;
    pad.attack_inc=0;pad.decay_inc=65535;pad.sustain=65535;pad.release_inc=16384;pad.volume=65535;pad.pan=0;
    desc.valid=1;desc.owner=1;desc.base_bytes=32'h09800000;desc.capacity_bytes=1048576;desc.frames=64;desc.gain_q16=65536;
    repeat(5) @(negedge clk);rst_n=1;
    // Independent ideal frequency ratios verify MIDI 0..127 and extreme root ranges.
    for(int root=0;root<=127;root+=127) for(int note=0;note<128;note++) begin
      ideal=65536.0*(2.0**((note-root)/12.0));
      if($itor(pitch_ratio(7'(note),7'(root)))<ideal*0.99998-1.0 || $itor(pitch_ratio(7'(note),7'(root)))>ideal*1.00002+1.0)
        $fatal(1,"pitch %d %d",note,root);
    end
    for(int note=0;note<128;note++) begin
      clear();send(1,note,127);repeat(4) frame();
      if(count!=1 || err!=OK || fault!=OK) $fatal(1,"full keyboard failed %d err=%d",note,err);
    end
    // Exact octave: waveform positions 0,2,4...; interpolation seam at sample63->0.
    clear();send(1,76,127);
    for(int n=0;n<40;n++) begin frame();expected=wave_at(n*2);
      if(l<expected-4 || l>expected+4 || r!=0) $fatal(1,"octave output %d got %d exp %d",n,l,expected);
    end
    // Fractional semitone interpolation compared to a separate integer oracle.
    clear();send(1,65,127);model_phase=0;
    for(int n=0;n<180;n++) begin
      aa=wave_at(model_phase[47:16]);bb=wave_at((model_phase[47:16]+1)%64);frac=model_phase[15:0];
      expected=aa+(((bb-aa)*frac)>>>16);frame();
      if(l<expected-4 || l>expected+4) $fatal(1,"linear interpolation n=%d got=%d exp=%d",n,l,expected);
      model_phase=(model_phase+69433)%(64*65536);
    end
    // One-shot ignores key-up, runs to the trim boundary and retires.
    clear();pad.play_mode=ONE_SHOT;send(1,64,127);send(0,64,0);
    repeat(63) frame();if(count!=1) $fatal(1,"one shot key-up killed sample");
    repeat(2) frame();if(count!=0) $fatal(1,"one shot trim end");pad.play_mode=LOOPED;
    clear();pad.reverse=1;send(1,64,127);
    for(int n=0;n<70;n++) begin frame();expected=wave_at((63-n+128)%64);
      if(l<expected-4 || l>expected+4) $fatal(1,"reverse seamless output n=%d got=%d exp=%d",n,l,expected);
    end
    clear();pad.reverse=0;pad.attack_inc=8192;pad.decay_inc=8192;pad.sustain=32768;
    send(1,64,100);frame();if(l!=0) $fatal(1,"attack starts at zero");repeat(20) frame();
    send(0,64,0);repeat(6) frame();if(count!=0) $fatal(1,"release tail stuck");
    clear();pad.attack_inc=0;pad.sustain=65535;pad.pan=64;
    // Force maximum misses: each voice moves 2KiB/frame and loops over a 1MiB sound.
    pad.trim_start=15;pad.loop_start=15;pad.trim_end=524288;pad.loop_end=524288;desc.frames=524288;pad.root_note=0;
    for(int i=0;i<16;i++) send(1,120,10);
    if(count!=16 || referenced!=1) $fatal(1,"16 voice allocation");
    send(1,121,127);if(err!=E_CAPACITY) $fatal(1,"17th voice must fail explicitly");
    repeat(24) frame();
    clear();pad.trim_end=32;pad.loop_end=32;
    for(int i=0;i<16;i++) send(1,120,10);
    repeat(40) frame();concurrent_cycles=cycles;
    if(misses!=0 || cycles>=1600 || max_frame_beats!=32) $fatal(1,"polyphony deadline");
    clear();frame();if(l!=0 || r!=0 || count!=0) $fatal(1,"panic audio");
    pad.trim_end=1;pad.loop_end=1;pad.trim_start=1;send(1,64,127);
    if(err!=E_BOUNDS || count!=0) $fatal(1,"invalid trim accepted");
    $display("METRIC voices=16 full_range_notes=128 extreme_pairs=256 max_frame_beats=%0d max_frame_cycles=%0d max_ddr_latency=%0d deadline_misses=%0d peak_bytes_per_second=%0d max_voice_read_latency=%0d max_voice_grant_wait=%0d",max_frame_beats,concurrent_cycles,max_latency,misses,max_frame_beats*32*48000,max_voice_read_latency,max_voice_grant_wait);
    $display("PASS tb_sampler_voice");$finish;
  end
  initial begin #100000000;$fatal(1,"timeout");end
endmodule
