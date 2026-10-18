`timescale 1ns/1ps
module tb_sampler_sequencer;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,panic=0,restart=0,tick=0,start=0,stop=0,record_enable=0;
  logic [8:0] bpm=120;logic [5:0] swing=25;
  logic select_valid=0;logic [3:0] select_pattern=0;
  logic edit_valid=0;logic [3:0] edit_pattern=0,edit_step=0;logic [1:0] edit_track=0;
  logic [6:0] edit_note=36,edit_velocity=100;logic [31:0] gate=1;
  logic chain_write=0;logic [3:0] chain_index=0,chain_pattern=0;logic [4:0] chain_length=0;
  logic live_valid=0;logic [17:0] live_event=0;
  logic event_valid,ready=1,running,click;logic [17:0] event_data;
  logic [31:0] ts,time_o,jitter,dispatched;logic [3:0] pattern,step;logic [63:0] grid;logic [7:0] error;
  integer events=0,on_events=0;integer last_note=0;logic [31:0] stamps[256];integer notes_seen[256];
  sampler_sequencer dut(.clk(clk),.rst_n(rst_n),.panic(panic),.restart(restart),.sample_tick(tick),
    .start(start),.stop(stop),.record_enable(record_enable),.bpm(bpm),.swing(swing),
    .select_valid(select_valid),.select_pattern(select_pattern),.edit_valid(edit_valid),
    .edit_pattern(edit_pattern),.edit_step(edit_step),.edit_track(edit_track),.edit_note(edit_note),
    .edit_velocity(edit_velocity),.edit_gate_frames(gate),.chain_write(chain_write),.chain_index(chain_index),
    .chain_pattern(chain_pattern),.chain_length(chain_length),.live_valid(live_valid),.live_event(live_event),
    .event_valid(event_valid),.event_ready(ready),.event_data(event_data),.event_timestamp(ts),.sample_time(time_o),
    .running(running),.click(click),.pattern(pattern),.step(step),.grid(grid),
    .max_jitter_samples(jitter),.dispatched(dispatched),.error(error));
  always @(posedge clk) if(event_valid && ready) begin
    events=events+1;
    if(event_data[17:14]==1) begin stamps[on_events]=ts;notes_seen[on_events]=event_data[13:7];on_events=on_events+1;end
  end
  task automatic frames(input integer n);
    repeat(n) begin @(negedge clk);tick=1;@(negedge clk);tick=0;repeat(10) @(negedge clk);end
  endtask
  task automatic begin_run;
    @(negedge clk);start=1;@(negedge clk);start=0;
  endtask
  task automatic hard_clear;
    @(negedge clk);panic=1;@(negedge clk);panic=0;
    if(running || event_valid || dut.held!=0) $fatal(1,"panic queue/held state");
  endtask
  integer base_count,origin,reference_phase,threshold,reference_step,next_odd;logic [17:0] stalled_data;logic [31:0] stalled_time;
  initial begin
    repeat(3) @(negedge clk);rst_n=1;
    for(int p=0;p<2;p++) for(int s=0;s<16;s++) begin
      @(negedge clk);edit_valid=1;edit_pattern=4'(p);edit_step=4'(s);edit_note=7'(36+p);
    end
    @(negedge clk);edit_valid=0;begin_run();frames(24002);
    if(on_events!=5 || stamps[1]-stamps[0]!=7500 || stamps[2]-stamps[0]!=12000 ||
       stamps[3]-stamps[0]!=19500 || stamps[4]-stamps[0]!=24000 || jitter!=0) $fatal(1,"sample accurate swing");
    hard_clear();swing=0;bpm=137;base_count=on_events;origin=time_o+1;
    begin_run();frames(90001);
    for(int i=0;i<on_events-base_count;i++)
      if(stamps[base_count+i]!=origin+(i*720000+136)/137) $fatal(1,"fractional BPM drift i=%d",i);
    // Tempo change preserves musical phase, checked against an independent sample model.
    hard_clear();base_count=on_events;bpm=120;swing=25;begin_run();frames(1);
    reference_phase=0;reference_step=0;next_odd=1;
    for(int n=0;n<16000;n++) begin
      if(n==4000) bpm=180;
      reference_phase=reference_phase+int'(bpm);threshold=next_odd ? 900000 : 1440000;
      if(reference_phase>=threshold) begin
        reference_step=reference_step+1;
        if(!next_odd) reference_phase=reference_phase-1440000;
        next_odd=!next_odd;
        frames(1);
        if(stamps[base_count+reference_step]!=time_o) $fatal(1,"tempo change phase continuity %d",n);
      end else frames(1);
    end
    // Live quantization chooses the nearest swung step.
    record_enable=1;live_event={4'd1,7'd53,7'd88};
    @(negedge clk);live_valid=1;@(negedge clk);live_valid=0;
    if(!grid[16+step] && !grid[16+(step+1)%16]) $fatal(1,"live recording");
    frames(17);live_event={4'd0,7'd53,7'd0};
    @(negedge clk);live_valid=1;@(negedge clk);live_valid=0;
    if(dut.recorded[1]) $fatal(1,"live gate key-off");
    if(dut.track_ram[1].u_ram.memory[dut.recorded_address[1]][31:0]!=17) $fatal(1,"recorded gate duration");
    record_enable=0;hard_clear();
    // Pending pattern changes only at a bar boundary, then chains 0 -> 1.
    bpm=300;swing=0;chain_length=2;
    @(negedge clk);chain_write=1;chain_index=0;chain_pattern=0;
    @(negedge clk);chain_index=1;chain_pattern=1;
    @(negedge clk);chain_write=0;select_valid=1;select_pattern=0;
    @(negedge clk);select_valid=0;begin_run();frames(38402);
    if(pattern!=1) $fatal(1,"chain did not advance");
    @(negedge clk);select_valid=1;select_pattern=0;@(negedge clk);select_valid=0;
    frames(38400);if(pattern!=0) $fatal(1,"pending bar launch");
    ready=0;frames(2401);if(!event_valid) $fatal(1,"backpressure not retained");
    stalled_data=event_data;stalled_time=ts;frames(101);
    if(event_data!=stalled_data || ts!=stalled_time) $fatal(1,"stalled event changed under new note off");
    hard_clear();ready=1;repeat(20) @(negedge clk);
    if(event_valid || error!=0) $fatal(1,"post panic stale event/error %d",error);
    bpm=0;begin_run();if(running || error!=E_BOUNDS) $fatal(1,"unsupported BPM");
    $display("METRIC swing_odd_offset_samples=1500 fractional_bpm=137 tempo_change_from=120 tempo_change_to=180 max_jitter_samples=%0d dispatched=%0d",jitter,dispatched);
    $display("PASS tb_sampler_sequencer");$finish;
  end
  initial begin #50000000;$fatal(1,"timeout");end
endmodule
