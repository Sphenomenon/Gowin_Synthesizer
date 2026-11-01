`timescale 1ns/1ps
module tb_workstation_worker_touch_runtime;
`include "sim/audio/fixtures/d_process_before_exact_mask.svh"
  reg clk=0,mclk=0,rst_n=0,mrst_n=0,run_memory=1;
  always #7 clk=~clk;
  always #10 if(run_memory)mclk=~mclk;
  reg request=0,rate=0,config_valid=0,config_rate=0,history_clear=0,hold_fence=0;
  reg cpu_clk=0,allow_events=0;
  always #5 cpu_clk=~cpu_clk;
  wire usb_valid,event_valid=usb_valid && allow_events;
  wire [17:0] event_data;
  wire [15:0] master_volume;

  reg signed [31:0] pcm_l=0,pcm_r=0;
  wire ready,done,error,busy,sample_ce,event_ready,config_ready,config_applied,history_ready,history_done,quiet,fault,applied_rate;
  wire signed [31:0] left_o,right_o;
  wire [127:0] held;
  wire [31:0] active,applied,deadline,note_drops,unsupported,duplicates;
  wire [9:0] epoch;
  wire muted;
  wire [1:0] mode;wire [31:0] options,effect_state;wire [2:0] mask;
  wire dwr_valid,dwr_pop,drd_push,drd_ready,ddr_req,ddr_write,ddr_response,dma_fault,audio_hb,memory_hb;
  wire [64:0] dwr_data,drd_data;
  wire [28:0] ddr_addr;
  wire [255:0] ddr_wdata,ddr_rdata;
  workstation_audio_render_service #(.RUNTIME_RATE_ENABLE(1),.RUNTIME_EFFECTS_ENABLE(1),.SYNTH_ENGINES_ENABLE(0),.D_ONLY_ENABLE(1)) dut(
      .clk_i(clk),.rst_ni(rst_n),.render_request_i(request),.render_44k1_i(rate),
      .render_ready_o(ready),.render_done_o(done),.render_error_o(error),.render_left_o(left_o),.render_right_o(right_o),
      .render_busy_o(busy),.sample_ce_o(sample_ce),.rejected_request_count_o(),.unsupported_rate_count_o(unsupported),
      .cancelled_response_count_o(),.drained_result_count_o(),
      .config_valid_i(config_valid),.config_rate_44100_i(config_rate),.history_clear_i(history_clear),
      .config_ready_o(config_ready),.config_applied_o(config_applied),.history_ready_o(history_ready),.history_done_o(history_done),
      .quiescent_o(quiet),.fault_o(fault),.applied_rate_44100_o(applied_rate),
      .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
      .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(event_ready),
      .pcm_left_i(pcm_l),.pcm_right_i(pcm_r),.held_notes_o(held),.applied_events_o(applied),.master_volume_o(master_volume),
      .panic_epoch_o(epoch),.panic_muted_o(muted),.active_mask_o(active),.mode_o(mode),.control_options_o(options),.effect_mask_o(mask),.effect_state_o(effect_state),
      .deadline_miss_o(deadline),.note_drop_o(note_drops),.delivery_duplicate_count_o(duplicates),
      .delay_mem_clk_i(mclk),.delay_mem_rst_ni(mrst_n),.delay_dwr_valid_o(dwr_valid),.delay_dwr_data_o(dwr_data),
      .delay_dwr_pop_i(dwr_pop),.delay_drd_push_i(drd_push),.delay_drd_data_i(drd_data),.delay_drd_ready_o(drd_ready),
      .delay_peer_heartbeat_i(memory_hb),.delay_dma_fault_i(dma_fault),.delay_heartbeat_o(audio_hb));
  workstation_runtime_delay_ddr_dma dma(
      .clk_i(mclk),.rst_ni(mrst_n),.dwr_valid_i(dwr_valid),.dwr_data_i(dwr_data),.dwr_pop_o(dwr_pop),
      .drd_push_o(drd_push),.drd_data_o(drd_data),.drd_ready_i(drd_ready),.ddr_req_o(ddr_req),
      .ddr_write_o(ddr_write),.ddr_address_o(ddr_addr),.ddr_data_o(ddr_wdata),.ddr_mask_o(),
      .ddr_ready_i(1'b1),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_rdata),.debug_status_o(),
      .flush_done_o(),.fault_o(dma_fault),.applied_rate_44100_o(),.applied_transaction_o(),
      .peer_heartbeat_i(audio_hb),.heartbeat_o(memory_hb));
  runtime_effects_memory_model memory_model(.clk(mclk),.rst_n(mrst_n),.req(ddr_req),.write_i(ddr_write),
      .ready_i(1'b1),.hold_fence,.address_i(ddr_addr),.data_i(ddr_wdata),.is_fence(dma.state==8),
      .response_o(ddr_response),.data_o(ddr_rdata));

  reg sv=0,sw=0;reg [7:0] sa=0;reg [31:0] sd=0;
  wire sr,se,os,ow,orr;wire [7:0] oa;wire [31:0] od,rd,srdata;
  wire ul,uc;wire [223:0] telemetry;
  reg [447:0] feedback;
  always @* begin
    feedback=0;
    feedback[63:32]={master_volume,6'd0,3'd0,2'd0,mode,mask};
    feedback[255:224]=options;feedback[287:278]=epoch;
  end
  workstation_usb2_service_adapter #(.WORKER_DEMO(1)) services(
    .clk_cpu(cpu_clk),.reset_n(rst_n),.session_valid_i(1'b1),.owner_connected_i(telemetry[1]),
    .service_valid_i(sv),.service_write_i(sw),.service_address_i(sa),.service_write_data_i(sd),
    .service_mask_i(4'hf),.service_ready_o(sr),.service_error_o(se),.service_read_data_o(srdata),
    .owner_select_o(os),.owner_write_o(ow),.owner_address_o(oa),.owner_write_data_o(od),
    .owner_ready_i(orr),.owner_read_data_i(rd),.canceled_requests_o());
  push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.WORKER_DEMO(1),.STOP_CLOCK_QUEUE_FENCE(1)) usb_owner(
    .clk(cpu_clk),.reset_n(rst_n),.audio_clk(clk),.audio_reset_n(rst_n),
    .feedback_clk(clk),.feedback_reset_n(rst_n),.performance_words(feedback),
    .display_meta_data(64'd0),.display_meta_valid(1'b0),.service_state_data(34'd0),.service_state_valid(1'b0),
    .score_valid(1'b0),.analysis_done(1'b0),.score_ready(),.score_note(7'd0),
    .playlist_valid(1'b0),.playlist_ready(),.playlist_word(16'd0),.track_launch(),.track_index(),
    .select(os),.write(ow),.address(oa),.wdata(od),.ready(orr),.rdata(rd),
    .audio_valid(usb_valid),.audio_ready(event_ready && allow_events),.audio_event(event_data),
    .audio_lifecycle(ul),.audio_cancel(uc),.telemetry(telemetry));
  integer audio_events=0,lifecycles=0;
  always @(posedge clk)if(rst_n && event_valid && event_ready)begin
    audio_events=audio_events+1;if(event_data[17:14]==15)lifecycles=lifecycles+1;
  end
  task access_bus(input bit wr,input [7:0] address,input [31:0] value,output [31:0] result);
    integer ticks;
    begin
      @(negedge cpu_clk);sv=1;sw=wr;sa=address;sd=value;ticks=0;
      do begin @(posedge cpu_clk);ticks=ticks+1;if(ticks>10000)$fatal(1,"touch MMIO timeout");end while(!sr);
      if(se)$fatal(1,"touch MMIO rejected %h",address);result=srdata;
      @(negedge cpu_clk);sv=0;repeat(2)@(negedge cpu_clk);
    end
  endtask
  integer frames=0,events=0,waited=0;
  integer old_function_snapshots=0,delayed_parameter_frames=0;
  reg signed [31:0] expected_capture_l,expected_capture_r;
  always @(posedge clk)if(rst_n && dut.workstation.core_ce)begin
    expected_capture_l=d_process_old_reference(dut.workstation.pcm_left_i,dut.workstation.d_crush,dut.workstation.d_drive);
    expected_capture_r=d_process_old_reference(dut.workstation.pcm_right_i,dut.workstation.d_crush,dut.workstation.d_drive);
    old_function_snapshots=old_function_snapshots+1;
  end
  always @(posedge clk)if(rst_n && dut.workstation.pcm_pitch_valid && dut.workstation.frame_inflight)begin
    expected_capture_l=d_process_old_reference(dut.workstation.pcm_pitch_left,dut.workstation.pcm_crush,dut.workstation.pcm_drive);
    expected_capture_r=d_process_old_reference(dut.workstation.pcm_pitch_right,dut.workstation.pcm_crush,dut.workstation.pcm_drive);
    #1;
    if(dut.workstation.held_pcm_l!==expected_capture_l || dut.workstation.held_pcm_r!==expected_capture_r)
      $fatal(1,"D core_ce depth snapshot changed across streaming Pitch");
  end
  task clocks(input integer n);repeat(n)@(negedge clk);endtask
  task frame(input signed [31:0] l,r);begin
    while(!ready)begin clocks(1);if(fault)$fatal(1,"render fault waiting ready");end
    @(negedge clk);pcm_l=l;pcm_r=r;request=1;clocks(1);request=0;waited=0;
    while(!done)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"render timeout");end
    if(error || fault || active!=0 || mode!=3)$fatal(1,"D-only state/error/voices");
    frames=frames+1;clocks(2);
  end endtask
  task change_rate(input reg next_rate);begin
    // C trace MMIO completes on an unrelated CPU edge. Start on an audio
    // falling edge and hold until an actual valid/ready rising edge; a pulse
    // ending at the next falling edge can otherwise contain no rising edge.
    @(negedge clk);config_rate=next_rate;config_valid=1;waited=0;
    do begin @(posedge clk);waited=waited+1;if(waited>3000)$fatal(1,"config acceptance timeout");end while(!config_ready);
    @(negedge clk);config_valid=0;waited=0;
    while(!config_applied)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"config timeout configready=%b corebusy=%b quiet=%b stagequiet=%b pitchjoined=%b pitchvalid=%b fxquiet=%b fxhistorydone=%b engine_rate=%b fxrate=%b pending_rate=%b configapplied=%b historydone=%b fault=%b",config_ready,dut.workstation.runtime_config_busy,quiet,dut.workstation.pcm_pitch_quiet,dut.workstation.pcm_pitch_joined,dut.workstation.pcm_pitch_valid,dut.workstation.fx_quiet,dut.workstation.fx_history_done,dut.workstation.engine_rate,dut.workstation.fx_rate,dut.workstation.runtime_configuration.pending_rate,dut.workstation.fx_config_applied,history_done,fault);end
    if(applied_rate!=next_rate || fault)$fatal(1,"config ACK before all-rate agreement");rate=next_rate;clocks(2);
  end endtask

  integer fd,n,op,address,value,crush,drive,send,selected;
  integer checkpoints=0,wet_checkpoints=0,dry_checkpoints=0,rate44_checkpoints=0;
  integer settled_lifecycles=-1,startup_frames=0;
  reg [31:0] read_value;string trace_path;
  reg signed [31:0] expected_l,expected_r;
  task checkpoint(input integer c,d,s,fx,bend);
    integer spins;
    reg [2:0] effective;
    begin
      allow_events=1;repeat(120)@(negedge cpu_clk);spins=0;
      effective=3'(fx) | (s!=0?3'b001:3'b000);
      while(options[20:0]!=={7'(s),7'(d),7'(c)} || options[28:21]!==8'(bend) || mask!==effective ||
            dut.workstation.attach_initializing || usb_valid)begin
        clocks(1);spins=spins+1;
        if(spins>10000)$fatal(1,"touch commit mismatch expected %0d/%0d/%0d/%0d got %h/%d",c,d,s,fx,options,mask);
      end
      if(muted || mode!=3 || active!=0 || effect_state!=32'h124)
        $fatal(1,"touch lifecycle/PANIC did not restore D/complete canonical effect state");
      expected_l=d_process_old_reference(32'sh12345678,7'(c),7'(d));
      expected_r=d_process_old_reference(-32'sh12345678,7'(c),7'(d));
      // Use the existing D-only regression's finite post-lifecycle priming
      // interval before requiring exact nonzero PCM; no unbounded wait.
      if(settled_lifecycles!=lifecycles)begin
        for(integer i=0;i<300;i=i+1)frame(32'sh12345678,-32'sh12345678);
        startup_frames=startup_frames+300;settled_lifecycles=lifecycles;
      end
      for(integer i=0;i<72;i=i+1)begin
        frame(32'sh12345678,-32'sh12345678);
        if(i>=64 && bend==128 && effective==0 && (left_o!==expected_l || right_o!==expected_r))
          $fatal(1,"C touch release did not restore actual dry/D-processed PCM checkpoint=%d frame=%d rate=%d c=%d d=%d got=%h/%h expected=%h/%h",checkpoints,i,rate,c,d,left_o,right_o,expected_l,expected_r);
      end
      if(effective!=0)wet_checkpoints=wet_checkpoints+1;else dry_checkpoints=dry_checkpoints+1;
      if(rate)rate44_checkpoints=rate44_checkpoints+1;
      // Feedback traverses the production coherent mailbox; requests never
      // feed this path. Read the same MMIO used by the real PL renderer.
      clocks(9000);
      access_bus(0,8'h14,0,read_value);
      if(read_value!==options)$fatal(1,"touch committed options feedback mismatch");
      access_bus(0,8'h10,0,read_value);
      if(read_value[2:0]!==effective || read_value[4:3]!==2'd3)
        $fatal(1,"touch committed effect/mode feedback mismatch");
      checkpoints=checkpoints+1;allow_events=0;
    end
  endtask
  initial begin
    if(!$value$plusargs("TRACE=%s",trace_path))$fatal(1,"missing production C trace");
    fd=$fopen(trace_path,"r");if(!fd)$fatal(1,"missing C trace file");
    clocks(4);rst_n=1;mrst_n=1;clocks(20);
    while(!$feof(fd))begin
      n=$fscanf(fd,"%h %h %h %h %h %h %h\n",op,address,value,crush,drive,send,selected);
      if(n==7)begin
        if(op==0)access_bus(1,8'(address),32'(value),read_value);
        else if(op==1)checkpoint(crush,drive,send,selected,value);
        else if(op==2)begin allow_events=1;change_rate(1'(value));allow_events=0;end
        else $fatal(1,"bad C trace operation");
      end else if(n!=-1)$fatal(1,"malformed C trace row %d",n);
    end
    $fclose(fd);allow_events=1;
    if(checkpoints<90 || wet_checkpoints<20 || dry_checkpoints<20 || rate44_checkpoints<4 || lifecycles<5)
      $fatal(1,"touch coverage short checkpoints=%d wet=%d dry=%d rate44=%d lifecycle=%d",checkpoints,wet_checkpoints,dry_checkpoints,rate44_checkpoints,lifecycles);
    if(deadline || unsupported || duplicates || note_drops || fault || old_function_snapshots!=frames)
      $fatal(1,"touch real D effects health/final PCM mismatch");
    $display("PASS worker_touch_runtime checkpoints=%0d wet=%0d dry=%0d rate44=%0d frames=%0d USB_events=%0d lifecycle=%0d real_FIFO_CDC=1 real_D_effects=1 committed_feedback=1",checkpoints,wet_checkpoints,dry_checkpoints,rate44_checkpoints,frames,audio_events,lifecycles);
    $finish;
  end
  initial begin #200000000;$fatal(1,"worker touch runtime watchdog");end
endmodule
