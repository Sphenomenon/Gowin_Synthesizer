`timescale 1ns/1ps
module tb_workstation_xy_analysis;
 parameter integer FRAMES=7;
 reg clk=0,reset_n=0,sample_valid=0,release_frame=0,read_enable=0;
 reg [31:0] pcm=0;reg [15:0] image_addr=0;reg [8:0] column=0;
 always #5 clk=~clk;
 wire [2:0] ready,display_valid,image_hit;
 wire [15:0] peak_left[0:2],peak_right[0:2];wire [2:0] gain[0:2];
 wire [31:0] seq[0:2],skip[0:2];wire [7:0] spectrum_left[0:2],spectrum_right[0:2];
`define PORTS(N) .clk(clk),.reset_n(reset_n),.source_clk(clk),.source_reset_n(reset_n),.pcm_pair(pcm),.sample_valid(sample_valid),.release_frame(release_frame),.ready(ready[N]),.peak_left(peak_left[N]),.peak_right(peak_right[N]),.image_gain(gain[N]),.sequence_data(seq[N]),.skipped_data(skip[N]),.display_read_enable(read_enable),.spectrum_column(column),.image_addr(image_addr),.spectrum_left(spectrum_left[N]),.spectrum_right(spectrum_right[N]),.image_hit(image_hit[N]),.display_valid(display_valid[N])
 reference_output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1)) reference(`PORTS(0));
 output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1)) unchanged(.vector_xy_i(1'b1),`PORTS(1));
 output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1),.XY_TRACE_ENABLE(1)) connected(.vector_xy_i(1'b1),`PORTS(2));
`undef PORTS
 reg [31:0] samples[0:FRAMES*2048-1];reg expect_off[0:FRAMES*65536-1],expect_on[0:FRAMES*65536-1];
 reg [31:0] expect_peak[0:FRAMES-1];reg [2:0] expect_gain[0:FRAMES-1];
 integer cycles=0,off_checks=0,pixel_checks=0,spectrum_checks=0,frames_done=0,stall_checks=0;
 always @(negedge clk)begin
  cycles=cycles+1;
  if(reset_n)begin
   if({ready[0],display_valid[0],peak_left[0],peak_right[0],gain[0],seq[0],skip[0],spectrum_left[0],spectrum_right[0],image_hit[0]}!=={ready[1],display_valid[1],peak_left[1],peak_right[1],gain[1],seq[1],skip[1],spectrum_left[1],spectrum_right[1],image_hit[1]})$fatal(1,"XY analysis default-off cycle mismatch cycle=%0d",cycles);
   off_checks=off_checks+1;
  end
 end
 task clocks(input integer count);repeat(count)@(negedge clk);endtask
 task reset_all;begin sample_valid=0;release_frame=0;read_enable=0;reset_n=0;clocks(5);reset_n=1;clocks(10);if(display_valid!==0)$fatal(1,"reset front still valid");end endtask
 task feed(input integer frame_index);begin
  for(integer sample_index=0;sample_index<2048;sample_index=sample_index+1)begin
   @(negedge clk);sample_valid=1;pcm=samples[frame_index*2048+sample_index];@(negedge clk);sample_valid=0;
  end
 end endtask
 task publish;begin
  wait(&ready);@(negedge clk);release_frame=1;@(negedge clk);release_frame=0;clocks(2);
  if(display_valid!==3'b111)$fatal(1,"front publication incomplete");
 end endtask
 task metadata(input integer frame_index,input integer expected_sequence);begin
  for(integer instance_index=0;instance_index<3;instance_index=instance_index+1)begin
   if({peak_left[instance_index],peak_right[instance_index]}!==expect_peak[frame_index] || gain[instance_index]!==expect_gain[frame_index] || seq[instance_index]!==32'(expected_sequence) || skip[instance_index]!==0)$fatal(1,"XY analysis metadata f=%0d instance=%0d peak=%h gain=%0d seq=%0d skip=%0d",frame_index,instance_index,{peak_left[instance_index],peak_right[instance_index]},gain[instance_index],seq[instance_index],skip[instance_index]);
  end
 end endtask
 task scan(input integer frame_index);reg old_image[0:2];reg [15:0] old_spectrum[0:2];begin
  read_enable=1;
  for(integer addr=0;addr<65536;addr=addr+1)begin
   image_addr=16'(addr);column=9'(addr%512);clocks(3);
   if(image_hit[0]!==expect_off[frame_index*65536+addr] || image_hit[1]!==expect_off[frame_index*65536+addr] || image_hit[2]!==expect_on[frame_index*65536+addr])$fatal(1,"XY analysis bitmap mismatch f=%0d addr=%0d got=%b expected=%b/%b",frame_index,addr,image_hit,expect_off[frame_index*65536+addr],expect_on[frame_index*65536+addr]);
   pixel_checks=pixel_checks+1;
   if(addr<512)begin
    if({spectrum_left[0],spectrum_right[0]}!=={spectrum_left[2],spectrum_right[2]})$fatal(1,"XY analysis FFT mismatch f=%0d column=%0d",frame_index,addr);spectrum_checks=spectrum_checks+1;
   end
   if(addr%4096==0)begin
    for(integer j=0;j<3;j=j+1)begin old_image[j]=image_hit[j];old_spectrum[j]={spectrum_left[j],spectrum_right[j]};end
    read_enable=0;image_addr=~image_addr;column=~column;clocks(5);
    for(integer j=0;j<3;j=j+1)if(image_hit[j]!==old_image[j] || {spectrum_left[j],spectrum_right[j]}!==old_spectrum[j])$fatal(1,"XY analysis stalled read changed");
    stall_checks=stall_checks+1;read_enable=1;
   end
  end
  read_enable=0;clocks(3);
 end endtask
 integer f;
 initial begin
  $readmemh("samples.mem",samples);$readmemh("off.mem",expect_off);$readmemh("on.mem",expect_on);$readmemh("peaks.mem",expect_peak);$readmemh("gains.mem",expect_gain);
  reset_all();
  for(f=0;f<FRAMES;f=f+1)begin
   if(f==6)reset_all();
   feed(f);wait(&ready);
   if(f>0 && f!=6)scan(f-1); // completed private back must not alter old public front
   publish();metadata(f,f==6 ? 0:f);scan(f);frames_done=frames_done+1;
  end
  // Uninterrupted source overruns an occupied analysis consumer. All capture
  // owners must count exactly the same loss; the slower display never feeds
  // a ready signal back into the audio source.
  reset_all();
  for(integer n=0;n<6144;n=n+1)begin @(negedge clk);pcm=0;sample_valid=1;end
  @(negedge clk);sample_valid=0;publish();if(skip[0]!==0 || skip[2]!==0)$fatal(1,"first snapshot skip identity");
  wait(&ready);publish();
  if(seq[0]!==1 || seq[2]!==1 || skip[0]==0 || skip[0]!==skip[2])$fatal(1,"XY analysis skipped input contract seq=%0d skip=%0d/%0d",seq[2],skip[0],skip[2]);
  $display("PASS xy_analysis frames=%0d off_cycles=%0d pixels=%0d stereo_fft_columns=%0d stalls=%0d skip=%0d reset_gain_history=1 immutable_front=1",frames_done,off_checks,pixel_checks,spectrum_checks,stall_checks,skip[2]);$finish;
 end
 initial begin #150000000;$fatal(1,"XY analysis watchdog frames=%0d state=%0d/%0d/%0d",frames_done,reference.state,unchanged.state,connected.state);end
endmodule
