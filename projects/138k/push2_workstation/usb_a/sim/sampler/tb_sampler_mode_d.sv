`timescale 1ns/1ps
module tb_sampler_mode_d;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;logic rst_n=0,restart=0,panic=0,enable=1,tick=0;
  logic event_valid=0,event_ready;logic [17:0] event_data=0;
  logic pad_write=0;logic [5:0] pad_index=0,descriptor_slot;pad_t pad;descriptor_t desc;
  logic [63:0] referenced;logic seq_start=0,seq_stop=0;
  logic edit_valid=0;logic [3:0] edit_step=0;
  logic running;logic [3:0] pattern,step;logic [63:0] grid;logic [1:0] group_select;
  logic storage_ready,storage_response;logic [255:0] storage_response_data;logic [7:0] storage_error;
  logic req_valid,req_write,req_ready=1;logic [28:0] req_addr;logic [255:0] req_data,rsp_data=0;
  logic [15:0] req_tag,rsp_tag=0;logic rsp_valid=0,pcm_valid;
  logic signed [15:0] l,r;logic [6:0] delay_send;logic [15:0] mask;logic [5:0] count;
  logic [31:0] misses,latency,beats,jitter;logic [7:0] voice_error,ddr_error,seq_error;
  integer pending=0,delay=0,frame=0,sequence_onsets=0,last_voice_count=0,max_render=0;
  sampler_mode_d dut(.clk(clk),.rst_n(rst_n),.restart(restart),.panic(panic),.enable(enable),.sample_tick(tick),
    .event_valid(event_valid),.event_ready(event_ready),.event_data(event_data),
    .pad_write(pad_write),.pad_index(pad_index),.pad_config(pad),.descriptor_slot(descriptor_slot),.descriptor(desc),
    .referenced(referenced),.seq_start(seq_start),.seq_stop(seq_stop),.record_enable(1'b0),.metronome_enable(1'b0),
    .bpm(9'd300),.swing(6'd25),.select_valid(1'b0),.select_pattern(4'd0),
    .edit_valid(edit_valid),.edit_pattern(4'd0),.edit_step(edit_step),.edit_track(2'd0),
    .edit_note(7'd36),.edit_velocity(7'd100),.edit_gate_frames(32'd100),
    .chain_write(1'b0),.chain_index(4'd0),.chain_pattern(4'd0),.chain_length(5'd0),
    .seq_running(running),.pattern(pattern),.step(step),.grid(grid),.group_select(group_select),
    .storage_valid(1'b0),.storage_write(1'b0),.storage_address(32'd0),.storage_base(32'd0),.storage_capacity(32'd0),
    .storage_data(256'd0),.storage_ready(storage_ready),.storage_response(storage_response),
    .storage_response_data(storage_response_data),.storage_error(storage_error),
    .req_valid(req_valid),.req_write(req_write),.req_ready(req_ready),.req_addr(req_addr),.req_data(req_data),.req_tag(req_tag),
    .rsp_valid(rsp_valid),.rsp_tag(rsp_tag),.rsp_data(rsp_data),.pcm_valid(pcm_valid),.pcm_l(l),.pcm_r(r),
    .delay_send(delay_send),.active_mask(mask),.active_count(count),.deadline_misses(misses),.max_latency(latency),
    .ddr_beats(beats),.seq_jitter_samples(jitter),.voice_error(voice_error),.ddr_error(ddr_error),.seq_error(seq_error));
  always @(negedge clk) begin
    rsp_valid=0;
    if(pending) begin delay=delay-1;if(delay==0) begin pending=0;rsp_valid=1;end end
  end
  always @(posedge clk) if(req_valid && req_ready) begin
    if(pending) $fatal(1,"multiple outstanding");pending=1;delay=10;rsp_tag=req_tag;
    for(int i=0;i<16;i++) rsp_data[i*16+:16]=16'sd10000;
  end
  task automatic send(input integer k,n,v);
    @(negedge clk);event_data={4'(k),7'(n),7'(v)};event_valid=1;
    #1;while(!event_ready) @(negedge clk);@(negedge clk);event_valid=0;
  endtask
  task automatic sample;
    integer clocks;
    @(negedge clk);tick=1;@(negedge clk);tick=0;clocks=0;
    while(!pcm_valid) begin @(negedge clk);clocks=clocks+1;if(clocks>1500) $fatal(1,"mode frame deadline");end
    frame=frame+1;if(clocks>max_render) max_render=clocks;
    if(running && count!=0 && last_voice_count==0) begin
      sequence_onsets=sequence_onsets+1;
      if(dut.sample_time!=dut.u_seq.off_time[0]-100) $fatal(1,"event-to-voice timestamp jitter");
    end
    last_voice_count=count;
    repeat(1600-clocks-1) @(negedge clk);
  endtask
  initial begin
    pad='0;desc='0;
    pad.slot=0;pad.root_note=36;pad.play_mode=LOOPED;pad.trim_end=64;pad.loop_end=64;
    pad.sustain=65535;pad.decay_inc=65535;pad.release_inc=65535;pad.volume=65535;pad.pan=64;
    desc.valid=1;desc.base_bytes=32'h09800000;desc.capacity_bytes=1048576;desc.frames=64;desc.gain_q16=65536;
    repeat(3) @(negedge clk);rst_n=1;
    @(negedge clk);pad_write=1;@(negedge clk);pad_write=0;
    send(1,36,127);sample();if(l<=0 || r<=0 || count!=1) $fatal(1,"mode voice output");
    send(5,36,64);sample();if(l>3000 || l<2000) $fatal(1,"continuous pressure");
    send(0,36,0);repeat(2) sample();if(count!=0) $fatal(1,"gate release");
    for(int s=0;s<4;s++) begin @(negedge clk);edit_valid=1;edit_step=4'(s);end
    @(negedge clk);edit_valid=0;seq_start=1;@(negedge clk);seq_start=0;
    repeat(5001) sample();
    if(sequence_onsets!=3 || jitter!=0 || misses!=0 || voice_error!=0 || ddr_error!=0 || seq_error!=0)
      $fatal(1,"integrated sequencer onsets=%d jitter=%d",sequence_onsets,jitter);
    send(2,110,127);sample();send(2,110,0);sample();
    send(2,120,0);if(count!=0 || running || dut.u_seq.event_valid) $fatal(1,"CC120 integrated panic");
    enable=0;#1;if(event_ready) $fatal(1,"inactive mode consumed event");
    $display("METRIC integrated_frames=%0d same_sample_onsets=%0d integrated_jitter_samples=0 max_render_cycles=%0d",frame,sequence_onsets,max_render);
    $display("PASS tb_sampler_mode_d");$finish;
  end
  initial begin #100000000;$fatal(1,"timeout");end
endmodule
