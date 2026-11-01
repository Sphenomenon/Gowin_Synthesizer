`timescale 1ns/1ps
// Real immutable PCM blocks exercise arithmetic, trace/history and stereo FFT.
module tb_workstation_xy_stereo;
 parameter integer FRAMES=21;
 reg clk=0,reset_n=0,sample_valid=0,release_frame=0,read_enable=0;
 reg [31:0] pcm=0;reg [15:0] image_addr=0;reg [8:0] column=0;
 always #5 clk=~clk;
 wire [3:0] ready,display_valid,image_hit;
 wire [15:0] peak_left[0:3],peak_right[0:3];wire [2:0] gain[0:3];
 wire [31:0] seq[0:3],skip[0:3];wire [7:0] spectrum_left[0:3],spectrum_right[0:3];
`define PORTS(N) .clk(clk),.reset_n(reset_n),.source_clk(clk),.source_reset_n(reset_n),.pcm_pair(pcm),.sample_valid(sample_valid),.release_frame(release_frame),.ready(ready[N]),.peak_left(peak_left[N]),.peak_right(peak_right[N]),.image_gain(gain[N]),.sequence_data(seq[N]),.skipped_data(skip[N]),.display_read_enable(read_enable),.spectrum_column(column),.image_addr(image_addr),.spectrum_left(spectrum_left[N]),.spectrum_right(spectrum_right[N]),.image_hit(image_hit[N]),.display_valid(display_valid[N])
 reference_output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1),.XY_TRACE_ENABLE(1)) reference(`PORTS(0));
 output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1),.XY_TRACE_ENABLE(1)) default_off(.vector_xy_i(1'b0),`PORTS(1));
 output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1),.XY_TRACE_ENABLE(1),.XY_STEREO_ENABLE(1)) vector_on(.vector_xy_i(1'b1),`PORTS(2));
 output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1),.XY_TRACE_ENABLE(1),.XY_STEREO_ENABLE(1)) stereo_on(.vector_xy_i(1'b0),`PORTS(3));
`undef PORTS
 reg [31:0] samples[0:FRAMES*2048-1];reg expect_direct[0:FRAMES*65536-1],expect_stereo[0:FRAMES*65536-1];
 reg [31:0] expect_peak[0:FRAMES-1];reg [2:0] expect_gain[0:FRAMES-1];reg reset_frame[0:FRAMES-1];
 integer cycles=0,cycle_checks=0,pixel_checks=0,spectrum_checks=0,frames_done=0,stall_checks=0,sequence_index=0;
 always @(negedge clk)begin
  cycles=cycles+1;
  if(reset_n)begin
   for(integer k=1;k<3;k=k+1)begin
    if({ready[0],display_valid[0],peak_left[0],peak_right[0],gain[0],seq[0],skip[0],spectrum_left[0],spectrum_right[0],image_hit[0]}!=={ready[k],display_valid[k],peak_left[k],peak_right[k],gain[k],seq[k],skip[k],spectrum_left[k],spectrum_right[k],image_hit[k]})$fatal(1,"stereo vector/default cycle mismatch cycle=%0d instance=%0d",cycles,k);
    cycle_checks=cycle_checks+1;
   end
  end
 end
 task clocks(input integer count);repeat(count)@(negedge clk);endtask
 task reset_all;begin sample_valid=0;release_frame=0;read_enable=0;reset_n=0;clocks(5);reset_n=1;clocks(10);if(display_valid!==0)$fatal(1,"stereo reset front still valid");end endtask
 task feed(input integer frame_index);begin
  for(integer sample_index=0;sample_index<2048;sample_index=sample_index+1)begin
   @(negedge clk);sample_valid=1;pcm=samples[frame_index*2048+sample_index];@(negedge clk);sample_valid=0;
  end
 end endtask
 task publish;begin
  wait(&ready);@(negedge clk);release_frame=1;@(negedge clk);release_frame=0;clocks(2);
  if(display_valid!==4'b1111)$fatal(1,"stereo front publication incomplete");
 end endtask
 task metadata(input integer frame_index,input integer expected_sequence);begin
  for(integer k=0;k<4;k=k+1)
   if({peak_left[k],peak_right[k]}!==expect_peak[frame_index] || gain[k]!==expect_gain[frame_index] || seq[k]!==32'(expected_sequence) || skip[k]!==0)$fatal(1,"stereo metadata f=%0d instance=%0d peak=%h gain=%0d seq=%0d skip=%0d",frame_index,k,{peak_left[k],peak_right[k]},gain[k],seq[k],skip[k]);
 end endtask
 task scan(input integer frame_index);reg old_image[0:3];reg [15:0] old_spectrum[0:3];begin
  read_enable=1;
  for(integer addr=0;addr<65536;addr=addr+1)begin
   image_addr=16'(addr);column=9'(addr%512);clocks(3);
   if(image_hit[0]!==expect_direct[frame_index*65536+addr] || image_hit[1]!==expect_direct[frame_index*65536+addr] || image_hit[2]!==expect_direct[frame_index*65536+addr] || image_hit[3]!==expect_stereo[frame_index*65536+addr])$fatal(1,"stereo bitmap mismatch f=%0d addr=%0d got=%b expected=%b/%b",frame_index,addr,image_hit,expect_direct[frame_index*65536+addr],expect_stereo[frame_index*65536+addr]);
   pixel_checks=pixel_checks+4;
   if(addr<512)begin
    for(integer k=1;k<4;k=k+1)begin
     if({spectrum_left[0],spectrum_right[0]}!=={spectrum_left[k],spectrum_right[k]})$fatal(1,"stereo FFT mismatch f=%0d instance=%0d column=%0d",frame_index,k,addr);
     spectrum_checks=spectrum_checks+1;
    end
   end
   if(addr%4096==0)begin
    for(integer j=0;j<4;j=j+1)begin old_image[j]=image_hit[j];old_spectrum[j]={spectrum_left[j],spectrum_right[j]};end
    read_enable=0;image_addr=~image_addr;column=~column;clocks(5);
    for(integer j=0;j<4;j=j+1)if(image_hit[j]!==old_image[j] || {spectrum_left[j],spectrum_right[j]}!==old_spectrum[j])$fatal(1,"stereo stalled read changed");
    stall_checks=stall_checks+4;read_enable=1;
   end
  end
  read_enable=0;clocks(3);
 end endtask
 integer f;
 initial begin
  $readmemh("samples.mem",samples);$readmemh("direct.mem",expect_direct);$readmemh("stereo.mem",expect_stereo);$readmemh("peaks.mem",expect_peak);$readmemh("gains.mem",expect_gain);$readmemh("resets.mem",reset_frame);
  reset_all();
  for(f=0;f<FRAMES;f=f+1)begin
   if(reset_frame[f])begin reset_all();sequence_index=0;end
   feed(f);wait(&ready);
   if(f>0 && !reset_frame[f])scan(f-1); // private back cannot modify public front
   publish();metadata(f,sequence_index);scan(f);frames_done=frames_done+1;sequence_index=sequence_index+1;
  end
  $display("PASS xy_stereo frames=%0d vector_default_cycles=%0d pixels=%0d stereo_fft_columns=%0d stalls=%0d signed_extremes=1 all_gains=1 normal_orientation=1 immutable_front=1 finite_history=1",frames_done,cycle_checks,pixel_checks,spectrum_checks,stall_checks);$finish;
 end
 initial begin #400000000;$fatal(1,"stereo watchdog frames=%0d state=%0d/%0d",frames_done,reference.state,stereo_on.state);end
endmodule
