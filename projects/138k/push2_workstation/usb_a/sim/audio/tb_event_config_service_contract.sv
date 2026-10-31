`timescale 1ns/1ps
module event_config_service_case #(parameter bit NATIVE=1,D_ONLY=1)(output reg finished=0);
  reg clk=0,mclk=0,rst_n=0,mrst_n=0;
  always #7 clk=~clk;
  always #10 mclk=~mclk;
  reg request=0,rate=0,config_valid=0,config_rate=0,history_clear=0;
  reg event_valid=0,injected_fault=0;
  reg [17:0] event_data=0;
  reg signed [31:0] pcm_l=32'sh12345600,pcm_r=-32'sh12345600;
  wire ready,done,error,busy,sample_ce,event_ready,config_ready,config_applied,history_ready,history_done,quiet,fault,applied_rate;
  wire signed [31:0] left_o,right_o;
  wire [31:0] applied;
  wire dwr_valid,dwr_pop,drd_push,drd_ready,ddr_req,ddr_write,ddr_response,dma_fault,audio_hb,memory_hb;
  wire [64:0] dwr_data,drd_data;
  wire [28:0] ddr_addr;
  wire [255:0] ddr_wdata,ddr_rdata;
  event_config_contract_miter #(.RUNTIME_RATE_ENABLE(NATIVE),.RUNTIME_EFFECTS_ENABLE(NATIVE),
      .SYNTH_ENGINES_ENABLE(!D_ONLY),.D_ONLY_ENABLE(D_ONLY)) dut(
      .clk_i(clk),.rst_ni(rst_n),.render_request_i(request),.render_44k1_i(rate),
      .render_ready_o(ready),.render_done_o(done),.render_error_o(error),.render_left_o(left_o),.render_right_o(right_o),
      .render_busy_o(busy),.sample_ce_o(sample_ce),.rejected_request_count_o(),.unsupported_rate_count_o(),
      .cancelled_response_count_o(),.drained_result_count_o(),
      .config_valid_i(config_valid),.config_rate_44100_i(config_rate),.history_clear_i(history_clear),
      .config_ready_o(config_ready),.config_applied_o(config_applied),.history_ready_o(history_ready),.history_done_o(history_done),
      .quiescent_o(quiet),.fault_o(fault),.applied_rate_44100_o(applied_rate),
      .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
      .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(event_ready),
      .pcm_left_i(pcm_l),.pcm_right_i(pcm_r),.held_notes_o(),.applied_events_o(applied),
      .panic_epoch_o(),.panic_muted_o(),.active_mask_o(),.deadline_miss_o(),.note_drop_o(),.delivery_duplicate_count_o(),
      .delay_mem_clk_i(mclk),.delay_mem_rst_ni(mrst_n),.delay_dwr_valid_o(dwr_valid),.delay_dwr_data_o(dwr_data),
      .delay_dwr_pop_i(dwr_pop),.delay_drd_push_i(drd_push),.delay_drd_data_i(drd_data),.delay_drd_ready_o(drd_ready),
      .delay_peer_heartbeat_i(memory_hb),.delay_dma_fault_i(dma_fault || injected_fault),.delay_heartbeat_o(audio_hb));
  workstation_runtime_delay_ddr_dma dma(
      .clk_i(mclk),.rst_ni(mrst_n),.dwr_valid_i(dwr_valid),.dwr_data_i(dwr_data),.dwr_pop_o(dwr_pop),
      .drd_push_o(drd_push),.drd_data_o(drd_data),.drd_ready_i(drd_ready),.ddr_req_o(ddr_req),
      .ddr_write_o(ddr_write),.ddr_address_o(ddr_addr),.ddr_data_o(ddr_wdata),.ddr_mask_o(),
      .ddr_ready_i(1'b1),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_rdata),.debug_status_o(),
      .flush_done_o(),.fault_o(dma_fault),.applied_rate_44100_o(),.applied_transaction_o(),
      .peer_heartbeat_i(audio_hb),.heartbeat_o(memory_hb));
  runtime_effects_memory_model memory_model(.clk(mclk),.rst_n(mrst_n),.req(ddr_req),.write_i(ddr_write),
      .ready_i(1'b1),.hold_fence(1'b0),.address_i(ddr_addr),.data_i(ddr_wdata),.is_fence(dma.state==8),
      .response_o(ddr_response),.data_o(ddr_rdata));
  integer requests=0,responses=0,configs=0,histories=0,events=0,coincidences=0,fault_checks=0;
  always @(posedge clk)if(rst_n)begin
    if(request && ready)requests=requests+1;
    if(done)responses=responses+1;
    if(config_applied)configs=configs+1;
    if(history_done)histories=histories+1;
    if(dut.actual.workstation.event_valid && dut.actual.workstation.event_ready)events=events+1;
    if(NATIVE && fault)begin
      if(ready || dut.actual.accepted || dut.actual.workstation.core_ce ||
         dut.actual.workstation.engine_rate_commit)$fatal(1,"fault admitted native work");
      fault_checks=fault_checks+1;
    end
    if(dut.actual.workstation.dispatch && dut.actual.workstation.core_ce)
      $fatal(1,"sample/event admission overlapped");
  end
  task automatic reset_case;
    begin
      rst_n=0;mrst_n=0;request=0;event_valid=0;config_valid=0;history_clear=0;injected_fault=0;
      repeat(8)@(negedge clk);rst_n=1;mrst_n=1;repeat(100)@(negedge clk);
    end
  endtask
  task automatic drain;
    integer timeout;
    begin
      timeout=0;while(!quiet && timeout<2000000)begin @(negedge clk);timeout=timeout+1;end
      if(!quiet)$fatal(1,"contract case failed to drain NATIVE=%0d",NATIVE);
    end
  endtask
  task automatic enqueue(input integer kind,address,value);
    integer timeout;
    begin
      @(negedge clk);event_data={4'(kind),7'(address),7'(value)};event_valid=1;timeout=0;
      do begin @(posedge clk);timeout=timeout+1;end while(!event_ready && timeout<10000);
      if(!event_ready)$fatal(1,"contract event ingress stuck");
      @(negedge clk);event_valid=0;
    end
  endtask
  task automatic send(input integer kind,address,value);
    begin enqueue(kind,address,value);repeat(4)@(negedge clk);end
  endtask
  task automatic render(input bit next_rate);
    integer before_response,timeout;
    begin
      before_response=responses;timeout=0;
      while(!ready && timeout<2000000)begin @(negedge clk);timeout=timeout+1;end
      if(!ready)$fatal(1,"contract render not ready");
      @(negedge clk);rate=next_rate;request=1;@(negedge clk);request=0;
      timeout=0;while(responses==before_response && timeout<2000000)begin @(negedge clk);timeout=timeout+1;end
      if(responses!=before_response+1)$fatal(1,"contract render completion missing");
      drain();pcm_l=pcm_l+32'sd7919;pcm_r=-pcm_l;
    end
  endtask
  task automatic configure_queued(input bit next_rate,history_only);
    integer before_history,timeout;
    begin
      drain();enqueue(2,16,63);before_history=histories;
      config_valid=!history_only;config_rate=next_rate;history_clear=history_only;request=1;rate=next_rate;
      #1;
      if(ready || dut.actual.workstation.dispatch || dut.actual.workstation.mode_valid)
        $fatal(1,"queued configuration/history did not reserve event/sample edge");
      coincidences=coincidences+1;
      do @(posedge clk);while(history_only ? !history_ready : !config_ready);
      @(negedge clk);config_valid=0;history_clear=0;request=0;timeout=0;
      while(histories==before_history && timeout<2000000)begin @(negedge clk);timeout=timeout+1;end
      if(histories!=before_history+1 || applied_rate!=next_rate)$fatal(1,"contract configuration did not apply");
      drain();
    end
  endtask
  initial begin
    reset_case();
    if(NATIVE)configure_queued(0,0);
    send(2,16,127);send(2,81,7);send(1,60,100);
    for(integer n=0;n<32;n=n+1)begin
      send(2,80,n%3);send(2,90,(n&1)?127:0);render(NATIVE ? 1'((n/4)&1):1'(n&1));
      if(NATIVE && (n%4)==0)begin configure_queued(applied_rate,1);configure_queued(!applied_rate,0);end
    end
    // Lifecycle and CC PANIC race with a newly accepted real PCM request.
    for(integer k=0;k<2;k=k+1)begin
      drain();enqueue(k==0 ? 15:2,k==0 ? 0:120,0);
      request=1;rate=NATIVE ? applied_rate:0;@(negedge clk);request=0;
      repeat(2000)@(negedge clk);drain();coincidences=coincidences+1;
    end
    if(NATIVE)begin
      // The real effect-domain DMA fault synchronizer supplies the veto.
      // Keep configuration, history, event and render requests on its edge.
      reset_case();configure_queued(0,0);enqueue(2,80,2);
      injected_fault=1;request=1;rate=1;config_valid=1;config_rate=1;history_clear=1;
      repeat(20)@(negedge clk);
      if(!fault || fault_checks==0)$fatal(1,"missing native fault boundary");
      request=0;config_valid=0;history_clear=0;injected_fault=0;
      repeat(10)@(negedge clk);reset_case();configure_queued(0,0);render(1);coincidences=coincidences+1;
    end
    if(events==0 || requests==0 || responses==0 || (NATIVE && (configs<4 || histories<4)))
      $fatal(1,"contract case coverage missing");
    $display("PASS event_config_contract native=%0d d_only=%0d requests=%0d responses=%0d configs=%0d histories=%0d events=%0d coincidences=%0d fault_checks=%0d",
        NATIVE,D_ONLY,requests,responses,configs,histories,events,coincidences,fault_checks);
    finished=1;
  end
endmodule
module tb_event_config_service_contract;
  wire w_done,legacy_done;
  event_config_service_case #(.NATIVE(1),.D_ONLY(1)) worker_case(w_done);
  event_config_service_case #(.NATIVE(0),.D_ONLY(0)) legacy_case(legacy_done);
  initial begin wait(w_done && legacy_done);$display("PASS full W/legacy module contracts");$finish;end
  initial begin #500000000;$fatal(1,"contract case timeout");end
endmodule
