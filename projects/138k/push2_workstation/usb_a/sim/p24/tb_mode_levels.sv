`timescale 1ns/1ps

module tb_mode_levels;
  localparam integer SKIP_FRAMES = 1000;
  localparam integer CAPTURE_FRAMES = 8192;
  logic clk = 0;
  always #6.510416 clk = ~clk;
  logic rst_n = 0;
  logic cpu_valid = 0;
  wire cpu_ready;
  logic [17:0] cpu_event = 0;
  logic sample_ce = 0;
  integer sample_div = 0;
  wire sample_valid;
  wire signed [31:0] left, right;
  wire [5:0] active_count;
  wire [1:0] mode;
  wire [2:0] profile;
  wire clip;

  gw138k_event_workstation dut(
      .clk_i(clk),.rst_ni(rst_n),.midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),
      .pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),.held_notes_o(),.applied_events_o(),
      .pc_overflow_o(),.control_options_o(),.panic_epoch_o(),
      .cpu_event_valid_i(cpu_valid),.cpu_event_i(cpu_event),.cpu_event_ready_o(cpu_ready),
      .sample_ce_i(sample_ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
      .sample_valid_o(sample_valid),.left_o(left),.right_o(right),
      .synth_valid_o(),.synth_o(),.active_mask_o(),.active_voice_count_o(active_count),
      .mode_o(mode),.pitch_q20_o(),.deadline_miss_o(),.midi_overflow_o(),
      .note_drop_o(),.clip_o(clip),.synth_gain_o(),.pcm_gain_o(),.route_o(),
      .profile_o(profile),.effect_mask_o(),.effect_order_o());

  always @(negedge clk) begin
    if(!rst_n) begin sample_div <= 0; sample_ce <= 0; end
    else if(sample_div == 1599) begin sample_div <= 0; sample_ce <= 1; end
    else begin sample_div <= sample_div + 1; sample_ce <= 0; end
  end

  task automatic send_event(input [3:0] kind,input [6:0] a,input [6:0] b);
    begin
      @(negedge clk);while(!cpu_ready)@(negedge clk);
      cpu_event={kind,a,b};cpu_valid=1;
      @(negedge clk);cpu_valid=0;
    end
  endtask

  integer requested_mode,requested_profile,program_number;
  integer voices,unison,capture_target,skip_target,voice;
  integer fd,age,captured,clip_count;
  string output_path;
  initial begin
    if(!$value$plusargs("MODE=%d",requested_mode))$fatal(1,"missing MODE");
    if(!$value$plusargs("PROFILE=%d",requested_profile))$fatal(1,"missing PROFILE");
    if(!$value$plusargs("OUT=%s",output_path))$fatal(1,"missing OUT");
    voices=1;unison=0;capture_target=CAPTURE_FRAMES;skip_target=SKIP_FRAMES;
    void'($value$plusargs("VOICES=%d",voices));
    void'($value$plusargs("UNISON=%d",unison));
    void'($value$plusargs("CAPTURE=%d",capture_target));
    void'($value$plusargs("SKIP=%d",skip_target));
    if(voices<1 || voices>32)$fatal(1,"invalid VOICES");
    case(requested_profile)
      0:program_number=20; 1:program_number=40; 2:program_number=56;
      3:program_number=8; default:program_number=0;
    endcase
    fd=$fopen(output_path,"w");if(!fd)$fatal(1,"cannot open output");
    repeat(10)@(negedge clk);rst_n=1;
    send_event(4'd3,program_number[6:0],7'd0);
    send_event(4'd2,7'd80,requested_mode[6:0]);
    while(mode!==requested_mode[1:0] || profile!==requested_profile[2:0])@(negedge clk);
    for(voice=0;voice<voices;voice=voice+1)
      send_event(4'd1,(unison || voices==1)?7'd60:7'd36+voice[6:0],7'd127);
    while(active_count!=voices[5:0])@(negedge clk);
    age=0;captured=0;clip_count=0;
    while(captured<capture_target)begin
      @(posedge clk);
      if(sample_valid)begin
        if(left!==right)$fatal(1,"effects-off stereo mismatch");
        if(clip)clip_count=clip_count+1;
        if(age>=skip_target)begin
          $fwrite(fd,"%0d\n",$signed(left));captured=captured+1;
        end
        age=age+1;
      end
    end
    $fclose(fd);
    $display("PASS LEVEL mode=%0d profile=%0d voices=%0d unison=%0d age=%0d captured=%0d clips=%0d",
        requested_mode,requested_profile,voices,unison,age,captured,clip_count);
    $finish;
  end

  initial begin
    #400000000;
    $fatal(1,"mode level capture timeout");
  end
endmodule
