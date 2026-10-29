`timescale 1ns/1ps
// Independent dual-clock component verification. The DDR model queues accepted
// commands before execution: a write handshake is deliberately NOT completion.
module tb_workstation_runtime_delay;
  reg aclk=0,mclk=0,run_audio=1,run_memory=1;
  always #7 if(run_audio)aclk=~aclk;
  always #10 if(run_memory)mclk=~mclk;
  reg arst_n=0,mrst_n=0,valid_i=0,enabled_i=1,clear_i=0;
  reg signed [31:0] left_i=0,right_i=0;
  reg config_valid=0,rate_44=0,history_clear=0;
  wire ready,valid_o,active,clip,config_ready,config_applied;
  wire history_ready,history_done,quiescent,fault,applied_rate;
  wire [31:0] applied_id;
  wire signed [31:0] left_o,right_o;
  wire dwr_valid,dwr_pop,drd_ready,raw_push,raw_ready;
  wire [64:0] dwr_data,raw_data;
  wire [7:0] audio_status,dma_status;
  wire audio_heartbeat,memory_heartbeat,mem_fault,flush_done,mem_rate;
  wire [31:0] mem_id;
  reg inject_valid=0,corrupt_marker=0,allow_return=1;
  reg [64:0] inject_data=0;
  wire fifo_push=inject_valid || (raw_push && allow_return);
  wire [64:0] fifo_data=inject_valid ? inject_data : raw_data;
  assign raw_ready=drd_ready && allow_return && !inject_valid;
  wire [64:0] memory_input=corrupt_marker && dwr_data[64] ?
      dwr_data ^ (65'd1<<33) : dwr_data;
  wire ddr_req,ddr_write;
  wire [28:0] ddr_addr;
  wire [255:0] ddr_wdata;
  wire [31:0] ddr_mask;
  reg ddr_response=0;
  reg [255:0] ddr_rdata=0;
  reg hold_accept=0,hold_exec=0,hold_fence=0;
  integer mcycle=0;
  reg ready_phase=0;
  always @(negedge mclk)ready_phase=(mcycle%3!=0);
  wire ddr_ready=!hold_accept && ready_phase;

  workstation_runtime_delay_effect_ddr #(
      .TRANSACTION_TIMEOUT_CYCLES(2048),.PEER_TIMEOUT_CYCLES(512)) u_audio(
      .clk_i(aclk),.rst_ni(arst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
      .left_i(left_i),.right_i(right_i),.ready_o(ready),.valid_o(valid_o),
      .active_o(active),.left_o(left_o),.right_o(right_o),.clip_o(clip),
      .mem_clk_i(mclk),.mem_rst_ni(mrst_n),.dwr_valid_o(dwr_valid),.dwr_data_o(dwr_data),
      .dwr_pop_i(dwr_pop),.drd_push_i(fifo_push),.drd_data_i(fifo_data),.drd_ready_o(drd_ready),
      .debug_status_o(audio_status),.config_valid_i(config_valid),.rate_44100_i(rate_44),
      .history_clear_i(history_clear),.config_ready_o(config_ready),.config_applied_o(config_applied),
      .history_ready_o(history_ready),.history_done_o(history_done),.quiescent_o(quiescent),
      .fault_o(fault),.applied_rate_44100_o(applied_rate),.applied_transaction_o(applied_id),
      .peer_heartbeat_i(memory_heartbeat),.heartbeat_o(audio_heartbeat));
  workstation_runtime_delay_ddr_dma #(
      .TRANSACTION_TIMEOUT_CYCLES(2048),.PEER_TIMEOUT_CYCLES(512)) u_dma(
      .clk_i(mclk),.rst_ni(mrst_n),.dwr_valid_i(dwr_valid),.dwr_data_i(memory_input),
      .dwr_pop_o(dwr_pop),.drd_push_o(raw_push),.drd_data_o(raw_data),.drd_ready_i(raw_ready),
      .ddr_req_o(ddr_req),.ddr_write_o(ddr_write),.ddr_address_o(ddr_addr),
      .ddr_data_o(ddr_wdata),.ddr_mask_o(ddr_mask),.ddr_ready_i(ddr_ready),
      .ddr_response_i(ddr_response),.ddr_read_data_i(ddr_rdata),.debug_status_o(dma_status),
      .flush_done_o(flush_done),.fault_o(mem_fault),.applied_rate_44100_o(mem_rate),
      .applied_transaction_o(mem_id),.peer_heartbeat_i(audio_heartbeat),.heartbeat_o(memory_heartbeat));

  wire ref_ready,ref_valid,ref_active,ref_clip;
  wire signed [31:0] ref_l,ref_r;
  serial_delay_effect #(.DELAY_BITS(14),.ECHO_SAMPLES(9600)) u_ref(
      .clk_i(aclk),.rst_ni(arst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
      .left_i(left_i),.right_i(right_i),.ready_o(ref_ready),.valid_o(ref_valid),
      .active_o(ref_active),.left_o(ref_l),.right_o(ref_r),.clip_o(ref_clip));

  // Queue order models the existing stable owner6 client + ordered native
  // command interface. Completion is an execution event, not acceptance.
  localparam [28:0] BASE=29'h0c000000;
  reg [255:0] memory[0:4095],queue_data[0:63];
  reg [28:0] queue_addr[0:63];
  reg queue_write[0:63],queue_fence[0:63];
  integer qhead=0,qtail=0,qcount=0,execute_wait=0;
  integer accepted_writes=0,executed_writes=0,accepted_reads=0,returned_reads=0;
  integer fence_accepts=0,fence_returns=0,accepted_before_fence=0,post_write_peak=0;
  always @(posedge mclk) begin : memory_model
    if(!mrst_n)begin
      qhead=0;qtail=0;qcount=0;execute_wait=0;mcycle=0;
      accepted_writes=0;executed_writes=0;accepted_reads=0;returned_reads=0;
      fence_accepts=0;fence_returns=0;accepted_before_fence=0;post_write_peak=0;
      ddr_response<=0;ddr_rdata<=0;
    end else begin
      mcycle=mcycle+1;ddr_response<=0;
      if(ddr_req && ddr_ready)begin
        if(ddr_addr<BASE || ddr_addr>=BASE+29'd32768 || ddr_addr[2:0]!=0 || ddr_mask!=0)
          $fatal(1,"out-of-allocation or unaligned DDR command");
        if(qcount==64)$fatal(1,"behavioral command queue overflow");
        queue_addr[qtail]=ddr_addr;queue_data[qtail]=ddr_wdata;
        queue_write[qtail]=ddr_write;queue_fence[qtail]=(u_dma.state==8);
        if(ddr_write)accepted_writes=accepted_writes+1;
        else accepted_reads=accepted_reads+1;
        if(u_dma.state==8)begin
          fence_accepts=fence_accepts+1;accepted_before_fence=accepted_writes;
          if(ddr_addr!=u_dma.last_write_address)$fatal(1,"fence changed last-write address");
        end
        qtail=(qtail+1)%64;qcount=qcount+1;
      end
      if(accepted_writes-executed_writes>post_write_peak)
        post_write_peak=accepted_writes-executed_writes;
      if(qcount!=0 && !hold_exec && !(queue_fence[qhead] && hold_fence))begin
        if(execute_wait==3)begin
          execute_wait=0;
          if(queue_write[qhead])begin
            memory[12'((queue_addr[qhead]-BASE)>>3)]=queue_data[qhead];
            executed_writes=executed_writes+1;
          end else begin
            ddr_response<=1;ddr_rdata<=memory[12'((queue_addr[qhead]-BASE)>>3)];
            returned_reads=returned_reads+1;
            if(queue_fence[qhead])begin
              fence_returns=fence_returns+1;
              if(executed_writes!=accepted_before_fence)$fatal(1,"fence passed unexecuted old writes");
            end
          end
          qhead=(qhead+1)%64;qcount=qcount-1;
        end else execute_wait=execute_wait+1;
      end
      if(flush_done && fence_returns!=fence_accepts)$fatal(1,"DMA ACK before fence response");
    end
  end

  reg compare48=0,model44=0;
  integer outputs=0,compared=0,clips=0,acks=0,dma_acks=0;
  integer model_frame=0,model_gain=0,model_fraction=0;
  reg signed [31:0] model_l[0:8819],model_r[0:8819],expect_l,expect_r;
  reg expect_clip,expect_pending=0;
  longint signed wet_l,wet_r,fb_l,fb_r,mix_l,mix_r;
  integer delta,idx;
  function automatic longint signed rounded(input longint signed value,input integer shift);
    longint signed magnitude;
    begin
      magnitude=value<0 ? -value : value;
      magnitude=(magnitude+(64'sd1<<(shift-1)))>>>shift;
      rounded=value<0 ? -magnitude : magnitude;
    end
  endfunction
  function automatic logic signed [31:0] saturated(input longint signed value);
    if(value>2147483647)saturated=32'sh7fffffff;
    else if(value< -64'sd2147483648)saturated=32'sh80000000;
    else saturated=32'(value);
  endfunction
  always @(posedge aclk) if(arst_n && model44 && valid_i && ready)begin
    if(expect_pending)$fatal(1,"reference lost an output");
    model_fraction=model_fraction+47;delta=139;
    if(model_fraction>=147)begin model_fraction=model_fraction-147;delta=140;end
    if(enabled_i)model_gain=model_gain+delta>8192 ? 8192 : model_gain+delta;
    else model_gain=model_gain<delta ? 0 : model_gain-delta;
    idx=model_frame%8820;
    wet_l=model_frame>=8820 ? 64'(model_l[idx]) : 0;
    wet_r=model_frame>=8820 ? 64'(model_r[idx]) : 0;
    fb_l=64'(left_i)+rounded(wet_l,1);fb_r=64'(right_i)+rounded(wet_r,1);
    mix_l=64'(left_i)+rounded(wet_l*64'(model_gain),15);
    mix_r=64'(right_i)+rounded(wet_r*64'(model_gain),15);
    model_l[idx]=saturated(fb_l);model_r[idx]=saturated(fb_r);
    expect_l=saturated(mix_l);expect_r=saturated(mix_r);
    expect_clip=mix_l>2147483647 || mix_l< -64'sd2147483648 ||
        mix_r>2147483647 || mix_r< -64'sd2147483648;
    model_frame=model_frame+1;expect_pending=1;
  end
  always @(negedge aclk) if(arst_n)begin
    if(config_applied || history_done)begin
      if(applied_id!=mem_id || applied_rate!=mem_rate || fence_returns!=fence_accepts)
        $fatal(1,"audio ACK lacks matching memory commit and ordered fence");
      acks=acks+1;
    end
    if(compare48)begin
      if({ready,valid_o,active}!={ref_ready,ref_valid,ref_active})
        $fatal(1,"48k handshake mismatch at frame %0d",outputs);
      if(valid_o)begin
        if({left_o,right_o,clip}!={ref_l,ref_r,ref_clip})
          $fatal(1,"48k PCM/clip mismatch frame %0d got %h,%h expected %h,%h",outputs,left_o,right_o,ref_l,ref_r);
        compared=compared+1;
      end
    end
    if(valid_o)begin
      outputs=outputs+1;if(clip)clips=clips+1;
      if(model44)begin
        if(!expect_pending || {left_o,right_o,clip}!={expect_l,expect_r,expect_clip})
          $fatal(1,"44.1 reference mismatch frame %0d got %h,%h expected %h,%h",model_frame-1,left_o,right_o,expect_l,expect_r);
        if(u_audio.gain!=16'(model_gain) || u_audio.gain_remainder!=8'(model_fraction))
          $fatal(1,"44.1 rational slew mismatch");
        expect_pending=0;compared=compared+1;
      end
    end
  end
  always @(negedge mclk)if(mrst_n && flush_done)dma_acks=dma_acks+1;

  reg [31:0] random_state=32'h72ab194f;
  task automatic random_step;
    random_state=(random_state>>1)^(random_state[0]?32'h80200003:0);
  endtask
  task automatic frame(input logic signed [31:0] l,r,input logic enable);
    begin
      @(negedge aclk);
      if(!ready)$fatal(1,"frame not accepted");
      left_i=l;right_i=r;enabled_i=enable;valid_i=1;
      @(negedge aclk);valid_i=0;
      repeat(23)@(negedge aclk);
    end
  endtask
  task automatic random_frame;
    reg signed [31:0] l,r;reg en;
    begin random_step();l=32'(random_state);random_step();r=32'(random_state);en=random_state[7];frame(l,r,en);end
  endtask
  task automatic begin_config(input logic rate);
    begin
      @(negedge aclk);if(!config_ready)$fatal(1,"config not ready");
      rate_44=rate;config_valid=1;
      @(negedge aclk);config_valid=0;
      if(ready || quiescent)$fatal(1,"accepts audio during configuration barrier");
    end
  endtask
  task automatic await_ack(input integer old_acks);
    integer timeout;
    begin
      timeout=0;
      while(acks==old_acks && timeout<1900)begin @(negedge aclk);timeout=timeout+1;end
      if(acks!=old_acks+1 || !ready || !quiescent || fault || mem_fault)
        $fatal(1,"configuration ACK timeout/fault audio=%b memory=%b state=%0d",fault,mem_fault,u_dma.state);
      repeat(4)@(negedge aclk);
    end
  endtask
  task automatic no_ack_audio(input integer cycles);
    integer before_acks;
    begin
      before_acks=acks;
      repeat(cycles)begin @(negedge aclk);if(ready || valid_o || acks!=before_acks)$fatal(1,"early ACK/output while history unisolated");end
    end
  endtask

  integer scenario=0,i,before_acks,saved_gain,saved_fraction,saved_writes;
  initial begin
    if(!$value$plusargs("SCENARIO=%d",scenario))scenario=0;
    for(i=0;i<4096;i=i+1)memory[i]=0;
    repeat(10)@(negedge aclk);arst_n=1;mrst_n=1;
    repeat(15)@(negedge aclk);
    case(scenario)
      0:begin
        compare48=1;
        for(i=0;i<30000;i=i+1)begin
          random_frame();
          if(i==11999)begin
            compare48=0;before_acks=acks;clear_i=1;
            @(negedge aclk);clear_i=0;await_ack(before_acks);compare48=1;
          end
        end
        if(fault || mem_fault || clips==0 || compared!=30000)$fatal(1,"48k coverage/fault audio=%b dma=%b under=%b over=%b compared=%0d clips=%0d",fault,mem_fault,u_audio.underflow_sticky,u_audio.overflow_sticky,compared,clips);
        $display("PASS runtime delay 48k per-cycle frames=%0d clips=%0d ring_wraps>=1 clear_acks=%0d",compared,clips,acks);
      end
      1:begin
        before_acks=acks;begin_config(1);await_ack(before_acks);model44=1;
        // Actual first wet impulse must occur at frame8820:200ms at44.1k.
        frame(32'sh10000000,-32'sh10000000,1);
        for(i=1;i<19000;i=i+1)begin
          if(i<8900)frame(0,0,1);else random_frame();
          if(i==8820 && (left_o!=32'sh04000000 || right_o!=-32'sh04000000))
            $fatal(1,"echo is not exactly8820 frames");
        end
        if(fault || mem_fault || compared!=19000)$fatal(1,"44.1 coverage/fault");
        $display("PASS runtime delay 44.1 independent fixed-point frames=%0d echo=8820 slew=139+47/147",compared);
      end
      2:begin
        // Keep an old read pending while accepting later posted writes.
        for(i=0;i<9152;i=i+1)begin
          if(i==9140)hold_exec=1;
          frame(32'sh11223344,-32'sh1234567,1);
        end
        if(u_dma.state!=3 || qcount==0)$fatal(1,"no held old read");
        saved_gain=32'(u_audio.gain);saved_fraction=32'(u_audio.gain_remainder);
        before_acks=acks;hold_fence=1;begin_config(1);no_ack_audio(80);
        if(u_dma.state!=5 || fence_accepts!=0)$fatal(1,"old response was not drained before fence");
        hold_exec=0;wait(fence_accepts==1);no_ack_audio(80);
        if(fence_returns!=0 || executed_writes!=accepted_writes)$fatal(1,"posted writes were not isolated before fence");
        hold_fence=0;await_ack(before_acks);
        if(u_audio.gain!=16'(saved_gain) || u_audio.gain_remainder!=8'(saved_fraction) || u_audio.frames!=0)
          $fatal(1,"config changed wet gain or failed logical history clear");
        // History-only request preserves44.1 rate and wet gain as well.
        for(i=0;i<20;i=i+1)frame(1,-1,0);
        saved_gain=32'(u_audio.gain);saved_fraction=32'(u_audio.gain_remainder);
        before_acks=acks;@(negedge aclk);history_clear=1;
        @(negedge aclk);history_clear=0;await_ack(before_acks);
        if(u_audio.gain!=16'(saved_gain) || u_audio.gain_remainder!=8'(saved_fraction) || !applied_rate)
          $fatal(1,"history clear changed parameters/rate/slew state");
        if(applied_id!=2 || mem_id!=2)$fatal(1,"transaction identity not advanced");
        // The next sample must be dry; old DDR words remain but logical history masks them.
        frame(32'sh12345,-32'sh23456,1);
        if(left_o!=32'sh12345 || right_o!=-32'sh23456)$fatal(1,"stale audio escaped after ACK");
        saved_gain=32'(u_audio.gain);saved_fraction=32'(u_audio.gain_remainder);
        before_acks=acks;begin_config(0);await_ack(before_acks);
        if(applied_rate || mem_rate || u_audio.gain!=16'(saved_gain) ||
           u_audio.gain_remainder!=8'(saved_fraction))$fatal(1,"return48k lost preserved state");
        $display("PASS runtime delay drain+ordered fence config/history preserved gain ids=%0d,%0d posted_peak=%0d",applied_id,mem_id,post_write_peak);
      end
      3:begin
        hold_fence=1;begin_config(1);no_ack_audio(3200);
        if(!fault || !mem_fault || acks!=0 || dma_acks!=0 || applied_rate || mem_rate)
          $fatal(1,"missing fence did not fail closed");
        hold_fence=0;repeat(100)@(negedge aclk);
        if(acks!=0 || dma_acks!=0 || ready)$fatal(1,"late fence response falsely recovered timed-out transaction");
        $display("PASS runtime delay missing/late fence timeout faults no ACK");
      end
      4:begin
        hold_fence=1;begin_config(1);wait(fence_accepts==1);
        @(negedge mclk);run_memory=0;no_ack_audio(700);
        if(!u_audio.peer_fault || acks!=0 || applied_rate)$fatal(1,"stopped memory clock undetected");
        $display("PASS runtime delay memory-clock stop detected by surviving audio domain");
      end
      5:begin
        hold_fence=1;begin_config(1);wait(fence_accepts==1);
        @(negedge aclk);run_audio=0;repeat(700)@(negedge mclk);
        if(!u_dma.peer_fault || dma_acks!=0 || mem_rate)$fatal(1,"stopped audio clock undetected");
        $display("PASS runtime delay audio-clock stop detected by surviving memory domain");
      end
      6:begin
        hold_fence=1;begin_config(1);wait(fence_accepts==1);
        @(negedge mclk);inject_data={1'b1,31'd0,32'hffffffff,1'b1};inject_valid=1;
        @(negedge mclk);inject_valid=0;no_ack_audio(20);
        if(!u_audio.transaction_fault)$fatal(1,"wrong/stale marker accepted");
        hold_fence=0;repeat(100)@(negedge aclk);
        if(acks!=0 || ready || applied_rate)$fatal(1,"matching late ACK healed wrong-marker fault");
        $display("PASS runtime delay wrong/stale marker rejected sticky fault");
      end
      7:begin
        corrupt_marker=1;begin_config(1);no_ack_audio(3200);
        if(!u_dma.protocol_fault || acks!=0 || dma_acks!=0 || mem_rate)$fatal(1,"reserved marker bits accepted");
        $display("PASS runtime delay reserved marker payload rejected no ACK");
      end
      8:begin
        for(i=0;i<10000;i=i+1)frame(32'sh10000,-32'sh20000,1);
        hold_accept=1;saved_writes=outputs;
        for(i=0;i<1100;i=i+1)frame(32'sh10000,-32'sh20000,1);
        if(!u_audio.underflow_sticky || !u_audio.overflow_sticky || outputs-saved_writes!=1100 ||
           left_o!=32'sh10000 || right_o!=-32'sh20000)
          $fatal(1,"DDR stall stream faults not observable or render hung");
        $display("PASS runtime delay sustained DDR stall underflow+overflow observable outputs=%0d no render hang",outputs-saved_writes);
      end
      9:begin
        // Old response arrived but its burst is backpressured. Marker must
        // preempt the remaining burst before the ACK is allowed through.
        for(i=0;i<9150;i=i+1)frame(32'sh7654321,-32'sh7654321,1);
        hold_exec=1;
        for(i=0;i<2;i=i+1)frame(32'sh7654321,-32'sh7654321,1);
        if(u_dma.state!=3)$fatal(1,"did not hold read response");
        allow_return=0;hold_exec=0;
        wait(u_dma.state==4);repeat(4)@(negedge mclk);
        before_acks=acks;begin_config(1);no_ack_audio(80);
        if(u_dma.state!=6 || fence_returns!=1 || dma_acks!=0)
          $fatal(1,"marker failed to preempt old read burst or ignored FIFO backpressure");
        allow_return=1;await_ack(before_acks);
        if(u_audio.frames!=0 || applied_id!=1)$fatal(1,"read burst polluted restarted epoch");
        $display("PASS runtime delay preempts old read burst and honors ACK FIFO backpressure");
      end
      10:begin
        // A pending read can leave old PCM before the marker in the write
        // FIFO. ACK must wait for that read, old PCM drain and fence as well.
        for(i=0;i<9180;i=i+1)begin
          if(i==9140)hold_exec=1;
          frame(32'sh12340000,-32'sh12340000,1);
        end
        if(u_dma.state!=3 || !dwr_valid || dwr_data[64])$fatal(1,"no old PCM backlog before marker");
        before_acks=acks;hold_fence=1;begin_config(1);no_ack_audio(80);
        if(fence_accepts!=0 || u_dma.state!=3)$fatal(1,"marker passed pending FIFO PCM/read");
        hold_exec=0;wait(fence_accepts==1);no_ack_audio(80);
        hold_fence=0;await_ack(before_acks);
        if(u_audio.frames!=0 || u_dma.wptr!=0 || u_dma.rptr!=0)
          $fatal(1,"old PCM backlog survived logical clear");
        $display("PASS runtime delay old PCM FIFO backlog drains before ordered fence ACK");
      end
      11:begin
        // Exercise clear in every FSM state, including the already-valid
        // output boundary. Holding clear coalesces to one transaction.
        for(i=0;i<5;i=i+1)begin
          repeat(20)frame(32'sh10000000,-32'sh10000000,1);
          @(negedge aclk);left_i=32'sh7fffffff;right_i=32'sh80000000;valid_i=1;
          @(negedge aclk);valid_i=0;
          repeat(i)@(negedge aclk);
          before_acks=acks;clear_i=1;
          repeat(10)@(negedge aclk);
          if(u_audio.gain!=0 || u_audio.frames!=0 || u_audio.state!=0 || ready || valid_o || acks!=before_acks)
            $fatal(1,"legacy clear did not abort/reset or ACK escaped held clear");
          clear_i=0;await_ack(before_acks);
          if(applied_id!=32'(i+1))$fatal(1,"held clear created duplicate transaction");
          frame(32'sh12345678,-32'sh12345678,1);
          if(left_o!=32'sh12345678 || right_o!=-32'sh12345678)
            $fatal(1,"legacy clear leaked cancelled output/history");
        end
        $display("PASS runtime delay legacy clear aborts five FSM states and coalesces held clear");
      end
      12:begin
        // A held config is backpressured while PCM is being accepted, then
        // takes priority over an accompanying history-only request at idle.
        before_acks=acks;
        @(negedge aclk);left_i=32'sh12345;right_i=-32'sh12345;
        config_valid=1;history_clear=1;rate_44=1;valid_i=1;
        #1;if(config_ready || history_ready)$fatal(1,"config raced accepted frame");
        @(negedge aclk);valid_i=0;
        wait(u_audio.transaction_busy);
        @(negedge aclk);config_valid=0;history_clear=0;
        await_ack(before_acks);
        if(outputs!=1 || applied_id!=1 || !applied_rate)$fatal(1,"config/history priority or PCM acceptance changed");
        $display("PASS runtime delay held config backpressure and config/history priority");
      end
      default:$fatal(1,"unknown scenario");
    endcase
    $finish;
  end
  initial begin #300000000;$fatal(1,"component watchdog timeout");end
endmodule
