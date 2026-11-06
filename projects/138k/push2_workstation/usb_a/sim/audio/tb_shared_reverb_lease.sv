`timescale 1ns/1ps
module tb_shared_reverb_lease;
    reg c25=0,c50=0,fast=0,memclk=0,rst=0;
    always #20 c25=~c25;
    always #10 c50=~c50;
    always #7 memclk=~memclk;
    wire clk=fast ? c50 : c25;
    reg clear=0,preempt=0,admit=0,local_valid=0,config_valid=0,local_rate=0,remote_rate=1,hold_fence=0;
    wire ready,slot,local_out,local_clip,config_ready,config_applied,history_ready,history_done,quiet,fault,applied_rate;
    reg signed [31:0] il=0,ir=0;
    wire signed [31:0] ol,oright;
    wire [31:0] transaction,denied,restore_failed,rejected,timeouts;
    wire dwr,wrpop,drpush,drready,audiohb,memhb,ddr_req,ddr_write,ddr_response,dmafault,lease,quiesce;
    wire [64:0] wdata,rdata;
    wire [28:0] ddr_address;
    wire [255:0] ddr_wdata,ddr_rdata;
    wire [31:0] ddr_mask;
    reg [191:0] key={32'd1,32'd2,32'd3,32'd4,32'd0,32'd5};
    reg qvalid=0;
    reg [31:0] qs=0;
    reg signed [31:0] ql=0,qr=0;
    wire qready,rvalid,rrate,rerror,rclip;
    wire [191:0] rkey;
    wire [31:0] rs;
    wire signed [31:0] rl,rr;
    workstation_worker_effects_shared #(.TRANSACTION_TIMEOUT_CYCLES(16384),.PEER_TIMEOUT_CYCLES(16384)) dut(
        .clk_i(clk),.rst_ni(rst),.clear_i(clear),.local_preempt_i(preempt),.valid_i(local_valid),
        .synth_i(32'sd0),.pcm_left_i(il),.pcm_right_i(ir),.vector_left_i(32'sd0),.vector_right_i(32'sd0),
        .synth_gain_i(16'd0),.pcm_gain_i(16'd32768),.effect_mask_i(3'd0),.effect_order_i(6'b10_01_00),.delay_send_i(7'd127),
        .ready_o(ready),.sample_slot_ready_o(slot),.valid_o(local_out),.clip_o(local_clip),.left_o(ol),.right_o(oright),
        .mem_clk_i(memclk),.mem_rst_ni(rst),.dwr_valid_o(dwr),.dwr_data_o(wdata),.dwr_pop_i(wrpop),
        .drd_push_i(drpush),.drd_data_i(rdata),.drd_ready_o(drready),
        .config_valid_i(config_valid),.rate_44100_i(local_rate),.history_clear_i(1'b0),
        .config_ready_o(config_ready),.config_applied_o(config_applied),.history_ready_o(history_ready),.history_done_o(history_done),
        .quiescent_o(quiet),.fault_o(fault),.applied_rate_44100_o(applied_rate),.applied_transaction_o(transaction),
        .peer_heartbeat_i(memhb),.delay_dma_fault_i(dmafault),.heartbeat_o(audiohb),
        .admitted_i(admit),.remote_rate_44100_i(remote_rate),.key_i(key),.req_valid_i(qvalid),.req_ready_o(qready),
        .req_key_i(key),.req_rate_44100_i(remote_rate),.req_enabled_i(1'b1),.req_sequence_i(qs),.req_left_i(ql),.req_right_i(qr),
        .rsp_valid_o(rvalid),.rsp_ready_i(1'b1),.rsp_key_o(rkey),.rsp_rate_44100_o(rrate),.rsp_error_o(rerror),.rsp_clip_o(rclip),
        .rsp_sequence_o(rs),.rsp_left_o(rl),.rsp_right_o(rr),.lease_granted_o(lease),.local_quiesce_o(quiesce),
        .lease_denied_count_o(denied),.restore_failure_count_o(restore_failed),.rejected_count_o(rejected),.timeout_count_o(timeouts));
    // The memory clock is independent: its watchdog must outlast the directed
    // two-drain-window hold even at the slowest worker clock.
    workstation_runtime_delay_ddr_dma #(.TRANSACTION_TIMEOUT_CYCLES(65536),.PEER_TIMEOUT_CYCLES(16384)) dma(
        .clk_i(memclk),.rst_ni(rst),.dwr_valid_i(dwr),.dwr_data_i(wdata),.dwr_pop_o(wrpop),
        .drd_push_o(drpush),.drd_data_o(rdata),.drd_ready_i(drready),.ddr_req_o(ddr_req),.ddr_write_o(ddr_write),
        .ddr_address_o(ddr_address),.ddr_data_o(ddr_wdata),.ddr_mask_o(ddr_mask),.ddr_ready_i(1'b1),
        .ddr_response_i(ddr_response),.ddr_read_data_i(ddr_rdata),.debug_status_o(),.flush_done_o(),.fault_o(dmafault),
        .applied_rate_44100_o(),.applied_transaction_o(),.peer_heartbeat_i(audiohb),.heartbeat_o(memhb));
    runtime_effects_memory_model memory_model(.clk(memclk),.rst_n(rst),.req(ddr_req),.write_i(ddr_write),
        .ready_i(1'b1),.hold_fence(hold_fence),.address_i(ddr_address),.data_i(ddr_wdata),
        .is_fence(dma.state==8),.response_o(ddr_response),.data_o(ddr_rdata));

    typedef struct packed {logic signed [31:0] l,r;} pcm_t;
    typedef struct packed {bit clip;logic signed [31:0] l,r;} result_t;
    pcm_t local_expected[$];
    result_t computed[integer];
    integer requested[$],active_sequence;
    integer checks=0,local_frames=0,local_results=0,remote_frames=0,remote_results=0,wet_frames=0,grants=0;
    integer pg=0,fraction=0,step;
    bit last_lease=0,busy=0,external_history=0,external_config=0;
    pcm_t expected_local;
    integer before_fences=0;
    function automatic signed [31:0] scaled(input signed [31:0] pcm,input integer gain);
        reg signed [63:0] product,magnitude;
        begin product=64'(pcm)*64'(gain);magnitude=(product<0 ? -product : product)+64'd16384;
            scaled=32'(product<0 ? -(magnitude>>>15) : magnitude>>>15);end
    endfunction
    task automatic check(input bit ok,input string why);
        checks++;if(!ok)$fatal(1,"shared lease: %s time=%0t",why,$time);
    endtask
    always @(posedge clk)if(rst)begin
        if(clear)begin local_expected.delete();requested.delete();busy=0;external_history=1;end
        if(!lease && last_lease)begin requested.delete();computed.delete();busy=0;end
        if(config_valid && config_ready)begin external_history=1;external_config=1;end
        if(config_applied)begin
            check(external_config,"configuration completion requires accepted local configuration");external_config=0;
        end
        if(history_done)begin
            check(external_history,"internal fence cannot acknowledge external history");external_history=0;
        end
        if(local_valid && ready)begin
            check(!lease && !quiesce,"local sample admitted only under local ownership");
            local_expected.push_back({scaled(il,pg),scaled(ir,pg)});local_frames++;
            step=128;
            if(applied_rate)begin fraction+=47;step=139+(fraction>=147 ? 1 : 0);fraction%=147;end
            pg=pg+step>32768 ? 32768 : pg+step;
        end
        if(local_out && !clear)begin
            check(local_expected.size()!=0 && !lease,"no cross-owner local result");
            expected_local=local_expected.pop_front();
            check(!local_clip && {ol,oright}==expected_local,"local full32 dry mix and gain preservation");local_results++;
        end
        if(lease)check(quiesce && !ready && !slot && !config_ready && !history_ready,"local admission closed during lease");
        if(lease && !last_lease)begin
            check(local_expected.size()==0,"last local sample completes before grant");
            check(memory_model.fence_returns>before_fences,"actual ordered DDR fence returned before grant");grants++;
        end
        last_lease=lease;
        if(qvalid && qready)begin requested.push_back(int'(qs));remote_frames++;end
        if(dut.worker.engine_valid_o && dut.worker.engine_ready_i)begin
            check(lease && !dut.local_effects.rv_valid_o,"exclusive single-engine execution");
            check(requested.size()!=0 && !busy,"remote engine command belongs to one admitted request");
            active_sequence=requested.pop_front();busy=1;
            check(dut.shared_engine.engine.left_i==32'sh08000007+32'(active_sequence*53177),"full32 remote engine input");
            check(dut.shared_engine.engine.right_i==-32'sh0400000b-32'(active_sequence*9127),"full32 remote right engine input");
        end
        if(dut.shared_engine.engine_clear)busy=0;
        if(dut.worker.engine_result_valid_i)begin
            check(!dut.local_effects.rv_valid_i,"remote completion is hidden from local client");
            check(busy && lease,"engine completion requires remote owner");
            computed[active_sequence]={dut.worker.engine_clip_i,dut.worker.engine_left_i,dut.worker.engine_right_i};busy=0;
        end
        if(rvalid)begin
            check(lease && rkey==key && rrate==remote_rate && !rerror,"remote result retains committed context");
            check(computed.exists(int'(rs))!=0,"response has actual engine output");
            check({rclip,rl,rr}==computed[int'(rs)],"remote output preserves engine PCM and clip");
            if(rl!=32'sh08000007+32'(int'(rs)*53177))wet_frames++;
            remote_results++;
        end
        if(ready)check(dut.shared_engine.applied_rate_44100_o==applied_rate,"local readiness requires real rate restoration");
    end
    task automatic wait_local;
        integer n;n=0;
        while(!ready && n<18000)begin @(negedge clk);n++;end
        if(!ready || fault)$display("LOCAL_WAIT state=%0d fault=%b local_fault=%b dma_fault=%b",dut.shared_engine.state,fault,dut.local_fault,dmafault);
        check(ready && !fault,"local path opens within bound");
    endtask
    task automatic configure;
        wait_local();@(negedge clk);config_valid=1;
        do @(posedge clk);while(!config_ready);
        @(negedge clk);config_valid=0;
        wait(config_applied);@(negedge clk);wait_local();
    endtask
    task automatic local_frame(input integer n);
        wait_local();@(negedge clk);local_valid=1;il=32'(1234567+n*99);ir=-32'(7654321+n*77);
        @(negedge clk);local_valid=0;
        wait(local_out);@(posedge clk);@(negedge clk);
    endtask
    task automatic start_claim;
        @(negedge clk);before_fences=memory_model.fence_returns;admit=1;
    endtask
    task automatic wait_lease;
        integer n;n=0;
        while(!lease && n<5000)begin @(negedge clk);n++;end
        check(lease && !fault,"lease granted after real local fence");
    endtask
    task automatic enqueue_remote(input integer seq);
        @(negedge clk);qvalid=1;qs=32'(seq);ql=32'sh08000007+32'(seq*53177);qr=-32'sh0400000b-32'(seq*9127);
        do @(posedge clk);while(!qready);
        @(negedge clk);qvalid=0;
    endtask
    task automatic remote_frame(input integer seq);
        enqueue_remote(seq);
        if(remote_rate)#22550;else #20700;
    endtask
    integer mhz,initial_rate,restore_ack_fault,old_denied,old_grants;
    initial begin
        if(!$value$plusargs("W_MHZ=%d",mhz))mhz=25;
        if(!$value$plusargs("LOCAL44=%d",initial_rate))initial_rate=0;
        if(!$value$plusargs("RESTORE_ACK_FAULT=%d",restore_ack_fault))restore_ack_fault=0;
        fast=mhz==50;local_rate=1'(initial_rate);remote_rate=!local_rate;
        #50;check(!ready && !slot && !config_ready && !history_ready && !lease && !qready && !rvalid,"reset closes client admission");
        #50;rst=1;wait_local();configure();
        for(integer n=0;n<30;n++)local_frame(n);
        // Assert a claim while an accepted local sample is still in flight.
        wait_local();@(negedge clk);local_valid=1;il=1234567;ir=-7654321;
        @(negedge clk);local_valid=0;hold_fence=1;start_claim();
        #10000;check(!lease && quiesce && !ready,"held DDR fence forbids lease");
        check(!history_done,"internal history transaction is not external ACK");
        hold_fence=0;wait_lease();
        for(integer n=0;n<2300;n++)remote_frame(n);
        check(remote_results==2300 && wet_frames>1200,"sustained real reverb after history fills");
        check(!fault && timeouts==0,"different remote rate does not poison suspended local chain");
        // Local configuration held during a lease receives no invented ACK.
        config_valid=1;#2000;check(!config_applied && !config_ready,"local config stays unaccepted while leased");
        enqueue_remote(2300);wait(busy);@(negedge clk);
        preempt=1;admit=0;requested.delete();config_valid=0;wait_local();
        check(dut.shared_engine.applied_rate_44100_o==local_rate,"actual original local rate restored");
        preempt=0;for(integer n=0;n<20;n++)local_frame(n);
        check(local_frames==local_results,"all admitted local frames completed");
        // Drain timeout denies this claim; no DDR ACK is fabricated.
        hold_fence=1;old_denied=int'(denied);old_grants=grants;key[31:0]++;start_claim();
        repeat(8300)@(negedge clk);
        check(denied==32'(old_denied+1) && grants==old_grants && !lease,"stuck DDR fence causes one bounded denial");
        admit=0;hold_fence=0;wait_local();for(integer n=0;n<5;n++)local_frame(n);
        key[31:0]++;start_claim();wait_lease();remote_frame(0);
        // PANIC while remotely owned must restore the physical local rate.
        @(negedge clk);clear=1;admit=0;
        repeat(3)@(negedge clk);clear=0;requested.delete();wait_local();
        repeat(3)@(negedge clk);
        for(integer n=0;n<5;n++)local_frame(n);
        // A source-only fault injection holds the real engine config-ready
        // boundary low. Restoration must fail closed until coordinated reset.
        key[31:0]++;start_claim();wait_lease();remote_frame(0);
        @(negedge clk);
        if(restore_ack_fault!=0)force dut.shared_engine.engine_config_applied=1'b0;
        else force dut.shared_engine.engine_config_ready=1'b0;
        preempt=1;admit=0;requested.delete();repeat(530)@(negedge clk);
        check(fault && restore_failed==1 && !ready && !lease,"failed restoration latches closed fault");
        release dut.shared_engine.engine_config_ready;
        release dut.shared_engine.engine_config_applied;
        clear=1;repeat(3)@(negedge clk);clear=0;repeat(10)@(negedge clk);
        check(fault && !ready,"PANIC cannot clear a restoration fault");
        check(grants>=3 && denied==1 && local_results>=60,"ownership scenarios executed");
        check(remote_frames-remote_results==1,"one in-flight remote request cancelled without stale completion");
        $display("SHARED_REVERB_RESULT {\"passed\":true,\"worker_mhz\":%0d,\"local_rate44\":%0d,\"restore_ack_fault\":%0d,\"checks\":%0d,\"local_frames\":%0d,\"remote_frames\":%0d,\"remote_results\":%0d,\"wet_frames\":%0d,\"grants\":%0d,\"denied\":%0d,\"restore_failures\":%0d}",mhz,initial_rate,restore_ack_fault,checks,local_results,remote_frames,remote_results,wet_frames,grants,denied,restore_failed);
        $finish;
    end
    initial begin #150000000;$fatal(1,"shared lease test timeout");end
endmodule
