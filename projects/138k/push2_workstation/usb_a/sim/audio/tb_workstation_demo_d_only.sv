`timescale 1ns/1ps
module tb_workstation_demo_d_only;
  reg clk=0,mclk=0,rst_n=0,mrst_n=0,run_memory=1;
  always #7 clk=~clk;
  always #10 if(run_memory)mclk=~mclk;
  reg request=0,rate=0,event_valid=0,config_valid=0,config_rate=0,history_clear=0,hold_fence=0;
  reg [17:0] event_data=0;
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
      .pcm_left_i(pcm_l),.pcm_right_i(pcm_r),.held_notes_o(held),.applied_events_o(applied),
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
  integer frames=0,events=0,waited=0;
  task clocks(input integer n);repeat(n)@(negedge clk);endtask
  task event_send(input [17:0] data);begin
    event_data=data;event_valid=1;waited=0;
    // Consume exactly one valid/ready edge, including non-idempotent CC87/88.
    do begin @(posedge clk);waited=waited+1;if(waited>3000)$fatal(1,"event timeout");end while(!event_ready);
    @(negedge clk);event_valid=0;clocks(12);events=events+1;
  end endtask
  task cc(input [6:0] address,value);event_send({4'd2,address,value});endtask
  task frame(input signed [31:0] l,r);begin
    while(!ready)begin clocks(1);if(fault)$fatal(1,"render fault waiting ready");end
    pcm_l=l;pcm_r=r;request=1;clocks(1);request=0;waited=0;
    while(!done)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"render timeout");end
    if(error || fault || active!=0 || mode!=3)$fatal(1,"D-only state/error/voices");
    frames=frames+1;clocks(2);
  end endtask
  task change_rate(input reg next_rate);begin
    while(!config_ready)clocks(1);config_rate=next_rate;config_valid=1;clocks(1);config_valid=0;waited=0;
    while(!config_applied)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"config timeout");end
    if(applied_rate!=next_rate || fault)$fatal(1,"config ACK before all-rate agreement");rate=next_rate;clocks(2);
  end endtask
  initial begin
    clocks(4);rst_n=1;mrst_n=1;clocks(10);
    if(mode!=3 || dut.workstation.pcm_gain_o!=32768)$fatal(1,"D-only startup not actual PCM unity/modeD");
    for(integer i=0;i<300;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"dry real PCM not bit-exact");
    cc(21,16);frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh2468acf0 || right_o!=-32'sh2468acf0 || options[13:7]!=16)$fatal(1,"committed drive disagrees with output");
    cc(20,127);frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh20000000 || right_o!=32'shd0000000 || options[6:0]!=127)$fatal(1,"committed crush disagrees with output");
    cc(20,0);cc(21,0);cc(22,127);
    for(integer i=0;i<100;i=i+1)frame(32'sh10000000,32'sh08000000);
    if(mask!=1 || options[20:14]!=127 || dut.workstation.runtime_effects.effects.delay_stage.gain!=8192)
      $fatal(1,"CC22 did not control unique runtime Delay wet");
    cc(22,64);for(integer i=0;i<40;i=i+1)frame(0,0);
    if(dut.workstation.runtime_effects.effects.delay_stage.gain!=4096)$fatal(1,"CC22 depth was only boolean");
    cc(22,0);for(integer i=0;i<50;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"D momentary release lost dry PCM");
    change_rate(1);for(integer i=0;i<300;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"44.1 dry PCM");
    cc(81,7);for(integer i=0;i<1200;i=i+1)frame(32'sh10000000,32'sh08000000);
    if(mask!=7 || fault)$fatal(1,"full effect chain not retained");
    if(effect_state!=32'h124)$fatal(1,"default effect feedback disagrees with committed owner");
    cc(87,2);if(effect_state!=32'h17e)$fatal(1,"reverb first feedback");
    cc(87,0);if(effect_state!=32'h1b2)$fatal(1,"delay second feedback");
    cc(87,1);if(effect_state!=32'h1d2)$fatal(1,"chorus third feedback got=%h",effect_state);
    cc(88,127);if(effect_state!=32'h0d2 || mask!=0)$fatal(1,"effect master feedback");
    cc(81,7);
    cc(20,100);cc(21,100);cc(22,100);
    event_send({4'd15,7'd1,7'd1});
    waited=0;while(dut.workstation.attach_initializing)begin clocks(1);waited=waited+1;if(waited>3000)$fatal(1,"D attach waited for nonexistent C engine");end
    if(options[20:0]!=0 || muted || mode!=3)$fatal(1,"D attach left stale controls/mute");
    for(integer i=0;i<300;i=i+1)frame(32'sh12345678,-32'sh12345678);
    if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)$fatal(1,"D did not resume after25K attach withoutNoteOn");
    if(deadline!=0 || unsupported!=0 || duplicates!=0 || note_drops!=0)$fatal(1,"D health counters");
    $display("PASS demo_d_only frames=%0d events=%0d rate44=%0d full_effects=1 no_instrument_engines=1",frames,events,rate);$finish;
  end
  initial begin #100000000;$fatal(1,"test watchdog");end
endmodule
