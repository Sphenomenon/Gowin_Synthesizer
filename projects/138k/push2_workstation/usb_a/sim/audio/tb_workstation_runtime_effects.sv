`timescale 1ns/1ps
module runtime_effects_memory_model(
    input logic clk,rst_n,req,write_i,ready_i,hold_fence,
    input logic [28:0] address_i,
    input logic [255:0] data_i,
    input logic is_fence,
    output logic response_o,
    output logic [255:0] data_o
);
  localparam [28:0] BASE=29'h0c000000;
  logic [255:0] memory[0:4095],queue_data[0:63];
  logic [28:0] queue_address[0:63];
  logic queue_write[0:63],queue_fence[0:63];
  integer head=0,tail=0,count=0,ticks=0,accepted_writes=0,executed_writes=0;
  integer fence_accepts=0,fence_returns=0,writes_before_fence=0;
  always @(posedge clk)begin
    if(!rst_n)begin
      head=0;tail=0;count=0;ticks=0;accepted_writes=0;executed_writes=0;
      fence_accepts=0;fence_returns=0;writes_before_fence=0;response_o<=0;data_o<=0;
    end else begin
      response_o<=0;
      if(req && ready_i)begin
        if(count==64 || address_i<BASE || address_i>=BASE+29'd32768 || address_i[2:0]!=0)
          $fatal(1,"DDR queue capacity/allocation violation");
        queue_address[tail]=address_i;queue_data[tail]=data_i;
        queue_write[tail]=write_i;queue_fence[tail]=is_fence;
        tail=(tail+1)%64;count=count+1;
        if(write_i)accepted_writes=accepted_writes+1;
        if(is_fence)begin fence_accepts=fence_accepts+1;writes_before_fence=accepted_writes;end
      end
      if(count!=0 && !(queue_fence[head] && hold_fence))begin
        if(ticks==3)begin
          ticks=0;
          if(queue_write[head])begin
            memory[12'((queue_address[head]-BASE)>>3)]=queue_data[head];executed_writes=executed_writes+1;
          end else begin
            data_o<=memory[12'((queue_address[head]-BASE)>>3)];response_o<=1;
            if(queue_fence[head])begin
              fence_returns=fence_returns+1;
              if(executed_writes!=writes_before_fence)$fatal(1,"fence overtook posted writes");
            end
          end
          head=(head+1)%64;count=count-1;
        end else ticks=ticks+1;
      end
    end
  end
endmodule

module tb_workstation_runtime_effects;
  reg aclk=0,mclk=0,run_audio=1,run_memory=1;
  always #7 if(run_audio)aclk=~aclk;
  always #10 if(run_memory)mclk=~mclk;
  reg arst_n=0,mrst_n=0,clear_i=0,valid_i=0;
  reg signed [31:0] synth_i=0,pcm_l=0,pcm_r=0,vector_l=0,vector_r=0;
  reg [15:0] synth_gain=16'h4000,pcm_gain=16'h6000;
  reg [2:0] mask=0;
  reg [5:0] order=6'b10_01_00;
  reg config_valid=0,history_clear=0,rate44=0,hold_fence=0;
  wire ready,valid_o,clip,config_ready,config_applied,history_ready,history_done,quiet,fault,rate;
  wire signed [31:0] left_o,right_o;
  wire [31:0] transaction;
  wire dwr_valid,dwr_pop,drd_push,drd_ready,ddr_req,ddr_write,ddr_response,dma_fault;
  wire [64:0] dwr_data,drd_data;
  wire [28:0] ddr_addr;
  wire [255:0] ddr_wdata,ddr_rdata;
  wire [31:0] ddr_mask;
  wire audio_hb,memory_hb,dma_done;
  workstation_runtime_stereo_effects #(.VECTOR_ENABLE(1),.TRANSACTION_TIMEOUT_CYCLES(2048),.PEER_TIMEOUT_CYCLES(512)) u_dut(
      .clk_i(aclk),.rst_ni(arst_n),.clear_i(clear_i),.valid_i(valid_i),.synth_i,
      .pcm_left_i(pcm_l),.pcm_right_i(pcm_r),.vector_left_i(vector_l),.vector_right_i(vector_r),
      .synth_gain_i(synth_gain),.pcm_gain_i(pcm_gain),.effect_mask_i(mask),.effect_order_i(order),
      .ready_o(ready),.valid_o(valid_o),.left_o(left_o),.right_o(right_o),.clip_o(clip),
      .mem_clk_i(mclk),.mem_rst_ni(mrst_n),.dwr_valid_o(dwr_valid),.dwr_data_o(dwr_data),
      .dwr_pop_i(dwr_pop),.drd_push_i(drd_push),.drd_data_i(drd_data),.drd_ready_o(drd_ready),
      .config_valid_i(config_valid),.rate_44100_i(rate44),.history_clear_i(history_clear),
      .config_ready_o(config_ready),.config_applied_o(config_applied),.history_ready_o(history_ready),
      .history_done_o(history_done),.quiescent_o(quiet),.fault_o(fault),.applied_rate_44100_o(rate),
      .applied_transaction_o(transaction),.peer_heartbeat_i(memory_hb),.delay_dma_fault_i(dma_fault),.heartbeat_o(audio_hb));
  workstation_runtime_delay_ddr_dma #(.TRANSACTION_TIMEOUT_CYCLES(2048),.PEER_TIMEOUT_CYCLES(512)) u_dma(
      .clk_i(mclk),.rst_ni(mrst_n),.dwr_valid_i(dwr_valid),.dwr_data_i(dwr_data),.dwr_pop_o(dwr_pop),
      .drd_push_o(drd_push),.drd_data_o(drd_data),.drd_ready_i(drd_ready),.ddr_req_o(ddr_req),
      .ddr_write_o(ddr_write),.ddr_address_o(ddr_addr),.ddr_data_o(ddr_wdata),.ddr_mask_o(ddr_mask),
      .ddr_ready_i(1'b1),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_rdata),.debug_status_o(),
      .flush_done_o(dma_done),.fault_o(dma_fault),.applied_rate_44100_o(),.applied_transaction_o(),
      .peer_heartbeat_i(audio_hb),.heartbeat_o(memory_hb));
  runtime_effects_memory_model u_memory(.clk(mclk),.rst_n(mrst_n),.req(ddr_req),.write_i(ddr_write),
      .ready_i(1'b1),.hold_fence,.address_i(ddr_addr),.data_i(ddr_wdata),.is_fence(u_dma.state==8),
      .response_o(ddr_response),.data_o(ddr_rdata));

  wire ref_ready,ref_valid,ref_clip;
  wire signed [31:0] ref_l,ref_r;
  wire rwvalid,rwpop,rrpush,rrready,rreq,rwrite,rresponse;
  wire [64:0] rwdata,rrdata;
  wire [28:0] raddr;
  wire [255:0] rw256,rr256;
  prepared_stereo_effects #(.VECTOR_ENABLE(1)) u_ref(
      .clk_i(aclk),.rst_ni(arst_n),.clear_i(clear_i),.valid_i(valid_i),.synth_i,
      .pcm_left_i(pcm_l),.pcm_right_i(pcm_r),.vector_left_i(vector_l),.vector_right_i(vector_r),
      .synth_gain_i(synth_gain),.pcm_gain_i(pcm_gain),.effect_mask_i(mask),.effect_order_i(order),
      .ready_o(ref_ready),.valid_o(ref_valid),.left_o(ref_l),.right_o(ref_r),.clip_o(ref_clip),
      .mem_clk_i(mclk),.mem_rst_ni(mrst_n),.dwr_valid_o(rwvalid),.dwr_data_o(rwdata),.dwr_pop_i(rwpop),
      .drd_push_i(rrpush),.drd_data_i(rrdata),.drd_ready_o(rrready));
  delay_ddr_dma u_ref_dma(.clk_i(mclk),.rst_ni(mrst_n),.dwr_valid_i(rwvalid),.dwr_data_i(rwdata),.dwr_pop_o(rwpop),
      .drd_push_o(rrpush),.drd_data_o(rrdata),.drd_ready_i(rrready),.ddr_req_o(rreq),.ddr_write_o(rwrite),
      .ddr_address_o(raddr),.ddr_data_o(rw256),.ddr_mask_o(),.ddr_ready_i(1'b1),.ddr_response_i(rresponse),
      .ddr_read_data_i(rr256),.debug_status_o());
  runtime_effects_memory_model u_ref_memory(.clk(mclk),.rst_n(mrst_n),.req(rreq),.write_i(rwrite),
      .ready_i(1'b1),.hold_fence(1'b0),.address_i(raddr),.data_i(rw256),.is_fence(1'b0),
      .response_o(rresponse),.data_o(rr256));

  reg compare48=0,barrier_expected=0;
  integer outputs=0,compared=0,clips=0,acks=0,config_acks=0,max_latency=0;
  integer stage_calls[0:2],maintenance_calls[0:2],applied_calls[0:2];
  always @(posedge aclk)if(arst_n && u_dut.state==4 && u_dut.selected_ready && !clear_i)begin
    stage_calls[u_dut.work_id]=stage_calls[u_dut.work_id]+1;
    if(u_dut.work_apply)applied_calls[u_dut.work_id]=applied_calls[u_dut.work_id]+1;
    else maintenance_calls[u_dut.work_id]=maintenance_calls[u_dut.work_id]+1;
  end
  always @(negedge aclk)if(arst_n)begin
    if(history_done)acks=acks+1;if(config_applied)config_acks=config_acks+1;
    if(compare48)begin
      if({ready,valid_o}!={ref_ready,ref_valid})$fatal(1,"48k chain control cycle mismatch");
      if(valid_o)begin
        if({left_o,right_o,clip}!={ref_l,ref_r,ref_clip})$fatal(1,"48k exact prepared chain PCM/clip mismatch");
        compared=compared+1;
      end
    end
    if(valid_o)begin outputs=outputs+1;if(clip)clips=clips+1;end
    if(quiet && (u_dut.stage_rate!={3{rate}} || u_dut.barrier_busy))$fatal(1,"quiescent exposed partial rate apply");
    if(barrier_expected && (ready || valid_o || left_o!=0 || right_o!=0))$fatal(1,"partial transaction leaked output/ready");
    if(config_applied && (u_dut.stage_rate!={3{rate}} || fault || !quiet))$fatal(1,"false config completion");
  end
  task automatic configure(input logic next_rate,input logic history_only);
    integer before_acks,timeout;
    begin
      @(negedge aclk);if(!config_ready || !history_ready)$fatal(1,"config not ready");
      before_acks=acks;rate44=next_rate;config_valid=!history_only;history_clear=history_only;
      @(negedge aclk);config_valid=0;history_clear=0;
      timeout=0;
      while(acks==before_acks && timeout<1900)begin @(negedge aclk);timeout=timeout+1;end
      if(acks!=before_acks+1 || fault || !ready || !quiet)$fatal(1,"chain config ACK/fault");
      repeat(3)@(negedge aclk);
    end
  endtask
  task automatic render(input logic check_pcm,input logic signed [31:0] expected_l,expected_r,input logic expected_clip);
    integer latency,calls_before[0:2];
    begin
      @(negedge aclk);if(!ready)$fatal(1,"frame refused");
      for(integer lane=0;lane<3;lane=lane+1)calls_before[lane]=stage_calls[lane];
      valid_i=1;@(negedge aclk);valid_i=0;latency=1;
      while(!valid_o && latency<250)begin @(negedge aclk);latency=latency+1;end
      if(!valid_o)$fatal(1,"full chain render hang");
      if(latency>max_latency)max_latency=latency;
      if(check_pcm && {left_o,right_o,clip}!={expected_l,expected_r,expected_clip})
        $fatal(1,"full chain independent model mismatch output%0d mask%0d order%h got%h,%h,%b expected%h,%h,%b",outputs,mask,order,left_o,right_o,clip,expected_l,expected_r,expected_clip);
      for(integer lane=0;lane<3;lane=lane+1)
        if(stage_calls[lane]!=calls_before[lane]+1)$fatal(1,"effect missing/duplicated frame or maintenance");
      repeat(4)@(negedge aclk);
      if(!quiet)$fatal(1,"chain tail did not drain");
    end
  endtask
  task automatic no_completion(input integer cycles);
    integer before_config;
    begin
      before_config=config_acks;barrier_expected=1;
      repeat(cycles)begin @(negedge aclk);if(config_acks!=before_config)$fatal(1,"early config ACK");end
      barrier_expected=0;
    end
  endtask
  integer scenario=0,i,fd,records,fields,operation,en_clip,timeout;
  integer target_state,target_work,clear_acks;
  integer gain_s,gain_p,mask_value,order_value;
  reg signed [31:0] expected_l,expected_r;
  string vector_file;
  initial begin
    if(!$value$plusargs("SCENARIO=%d",scenario))scenario=0;
    for(i=0;i<3;i=i+1)begin stage_calls[i]=0;maintenance_calls[i]=0;applied_calls[i]=0;end
    repeat(10)@(negedge aclk);arst_n=1;mrst_n=1;repeat(15)@(negedge aclk);
    if(scenario<3)begin
      if(!$value$plusargs("VECTOR_FILE=%s",vector_file))$fatal(1,"missing vectors");
      fd=$fopen(vector_file,"r");fields=$fscanf(fd,"%d\n",records);if(fields!=1)$fatal(1,"bad vectors count");
      compare48=scenario==0;
      for(i=0;i<records;i=i+1)begin
        fields=$fscanf(fd,"%d %h %h %h %h %h %h %h %h %h %h %h %d\n",operation,synth_i,pcm_l,pcm_r,vector_l,vector_r,gain_s,gain_p,mask_value,order_value,expected_l,expected_r,en_clip);
        if(fields!=13)$fatal(1,"bad vector row%0d",i);
        synth_gain=16'(gain_s);pcm_gain=16'(gain_p);mask=3'(mask_value);order=6'(order_value);
        case(operation)
          0:render(1,expected_l,expected_r,1'(en_clip));
          1:configure(1,0);
          2:configure(0,0);
          3:configure(0,1);
          4:begin
            compare48=0;@(negedge aclk);clear_i=1;@(negedge aclk);clear_i=0;
            wait(history_done);repeat(5)@(negedge aclk);if(scenario==0)compare48=1;
          end
          default:$fatal(1,"bad operation");
        endcase
      end
      $fclose(fd);
      if(fault || outputs==0)$fatal(1,"full-chain vector fault");
      for(i=0;i<3;i=i+1)
        if(maintenance_calls[i]==0 || applied_calls[i]==0)$fatal(1,"missing maintenance/apply coverage");
      $display("PASS runtime full effects scenario=%0d frames=%0d reference48=%0d clips=%0d max_latency=%0d maintenance=%0d,%0d,%0d",scenario,outputs,compared,clips,max_latency,maintenance_calls[0],maintenance_calls[1],maintenance_calls[2]);
    end else begin
      mask=7;synth_i=32'sh12345678;pcm_l=32'sh1234567;pcm_r=-32'sh1234567;
      repeat(80)render(0,0,0,0);
      if(scenario==8)begin
        for(i=0;i<9;i=i+1)begin
          repeat(20)render(0,0,0,0);
          target_state=i<7 ? i : 5;target_work=i<7 ? 0 : i-6;
          if(target_state!=0)begin
            @(negedge aclk);valid_i=1;@(negedge aclk);valid_i=0;
            while(!(u_dut.state==4'(target_state) &&
                (target_state!=5 || u_dut.work_id==2'(target_work))))@(negedge aclk);
          end
          clear_acks=acks;clear_i=1;repeat(2)@(negedge aclk);clear_i=0;
          no_completion(2);timeout=0;
          while(acks==clear_acks && timeout<1800)begin @(negedge aclk);timeout=timeout+1;end
          if(acks!=clear_acks+1 || config_acks!=0 || fault || !quiet || !ready ||
             u_dut.sg!=u_ref.sg || u_dut.pg!=u_ref.pg)
            $fatal(1,"legacy clear pipeline cancellation/gain update failed");
          synth_i=0;pcm_l=0;pcm_r=0;vector_l=0;vector_r=0;render(1,0,0,0);
        end
        $display("PASS runtime effects legacy clear cancels9 chain/stage boundaries preserves prepared gain edge");$finish;
      end
      hold_fence=(scenario!=4);
      @(negedge aclk);if(!config_ready)$fatal(1,"manual config not ready");
      config_valid=1;rate44=1;@(negedge aclk);config_valid=0;
      case(scenario)
        3:begin
          wait(u_memory.fence_accepts==1);no_completion(30);
          @(negedge aclk);clear_i=1;repeat(3)@(negedge aclk);clear_i=0;
          // Pulse additional rejected config/history requests while pending.
          config_valid=1;history_clear=1;rate44=0;no_completion(30);
          if(config_ready || history_ready)$fatal(1,"accepted second pending transaction");
          config_valid=0;history_clear=0;hold_fence=0;
        end
        4:begin
          // PANIC after Delay's first ACK must force another fenced clear;
          // the accepted rate transaction still completes at the new rate.
          wait(u_dut.delay_stage.history_done_o);
          @(negedge aclk);clear_i=1;hold_fence=1;
          repeat(3)@(negedge aclk);clear_i=0;
          wait(u_memory.fence_accepts==2);no_completion(40);hold_fence=0;
        end
        5:begin
          no_completion(3200);
          if(!fault || config_acks!=0 || ready || rate)$fatal(1,"missing fence did not fail closed");
          hold_fence=0;repeat(100)@(negedge aclk);
          if(config_acks!=0 || ready)$fatal(1,"late response healed sticky chain failure");
          $display("PASS runtime effects missing/late fence remains sticky failed");$finish;
        end
        6:begin
          wait(u_memory.fence_accepts==1);@(negedge mclk);run_memory=0;no_completion(700);
          if(!fault || config_acks!=0 || rate)$fatal(1,"memory stop not failed closed");
          $display("PASS runtime effects memory-clock stop controlled zero no done");$finish;
        end
        7:begin
          wait(u_memory.fence_accepts==1);@(negedge aclk);run_audio=0;repeat(700)@(negedge mclk);
          if(!dma_fault || dma_done || u_memory.fence_returns!=0)$fatal(1,"audio stop not detected by DMA");
          run_audio=1;repeat(10)@(negedge aclk);
          if(!fault || ready || config_acks!=0)$fatal(1,"resumed audio ignored memory sticky failure");
          $display("PASS runtime effects audio-clock stop sticky failure after resume");$finish;
        end
        default:$fatal(1,"bad scenario");
      endcase
      timeout=0;
      while(config_acks==0 && timeout<1800)begin @(negedge aclk);timeout=timeout+1;end
      if(config_acks!=1 || fault || !rate || !ready || !quiet ||
         u_dut.delay_stage.gain!=0 || u_dut.chorus_stage.gain!=0 || u_dut.reverb_stage.gain!=0)
        $fatal(1,"PANIC retracted/partially applied accepted config");
      synth_i=0;pcm_l=0;pcm_r=0;vector_l=0;vector_r=0;render(1,0,0,0);
      $display("PASS runtime effects PANIC collision scenario=%0d completes matching new rate fences=%0d",scenario,u_memory.fence_returns);
    end
    $finish;
  end
  initial begin #1000000000;$fatal(1,"effects chain test watchdog");end
endmodule
