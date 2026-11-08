`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
module tb_workstation_task3_pcm_blocks;
    parameter bit REGISTER_W_TX_CLASS=0;
`ifdef TASK3_MIXED_MEDIA
    localparam bit W_BLOCK=0;
`else
    localparam bit W_BLOCK=1;
`endif
    reg clk=0;always #5 clk=~clk;
    reg reset_n=0,link=0,panic=0;
    reg m_observer_reset=0;
    reg [31:0] m_boot=11;
    reg [31:0] generation=1;
    integer checks=0,physical_ticks=0,record_count=0,phone_count=0,status_count=0;
    reg status_seen=0,owner_allow=1,object_idle=1,transport_fault=0;
    reg [1:0] cpu_valid=0,cpu_write=0;
    reg [23:0] cpu_address=0;reg [63:0] cpu_data=0;reg [7:0] cpu_strobes=0;
    wire [1:0] cpu_ready,cpu_error;wire [63:0] cpu_response;
    wire mtv,mtr,wtv,wtr;wire [3:0] mtc,wtc;wire [255:0] mtp,wtp;wire [5:0] mtl,wtl;
    reg inject=0;reg [3:0] ic=0;reg [255:0] ip=0;reg [5:0] il=0;
    wire wrx_ready;
    assign mtr=!inject && wrx_ready;
    wire record_valid,record_allowed,record_fault,phone_fault;
    wire source_needed,engine_start,engine_done,engine_idle;
    wire [7:0] engine_state,engine_status;
    wire [31:0] engine_frames;
    reg engine_command=0;
    wire [31:0] record_pcm,record_sequence;
    wire [3:0] record_failure;
    wire cdv,cfv,csv,ccv;reg cdr=1,cfr=1,csr=1,ccr=1;
    wire [199:0] cdesc;wire [191:0] cframe,cseal;wire [127:0] ccancel;
    reg terminal_valid=0;reg [163:0] terminal=0;
    wire terminal_ready;
    workstation_task3_w_bus_endpoint #(.BLOCK_PCM(W_BLOCK),.REGISTER_TX_CLASS(REGISTER_W_TX_CLASS && W_BLOCK),.MEDIA_CAP_TIMEOUT_CYCLES(3000)) w(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),
        .local_boot_i(32'd22),.peer_boot_i(m_boot),.session_i(32'd33),.generation_i(generation),
        .rx_valid_i(inject || mtv),.rx_ready_o(wrx_ready),.rx_channel_i(inject?ic:mtc),.rx_payload_i(inject?ip:mtp),.rx_length_i(inject?il:mtl),
        .tx_valid_o(wtv),.tx_ready_i(wtr),.tx_channel_o(wtc),.tx_payload_o(wtp),.tx_length_o(wtl),
        .cnn_desc_valid_o(cdv),.cnn_desc_ready_i(cdr),.cnn_desc_o(cdesc),
        .cnn_frame_valid_o(cfv),.cnn_frame_ready_i(cfr),.cnn_frame_o(cframe),
        .cnn_seal_valid_o(csv),.cnn_seal_ready_i(csr),.cnn_seal_o(cseal),
        .cnn_cancel_valid_o(ccv),.cnn_cancel_ready_i(ccr),.cnn_cancel_o(ccancel),
        .cnn_score_valid_i(1'b0),.cnn_score_ready_o(),.cnn_score_i(167'd0),
        .cnn_terminal_valid_i(terminal_valid),.cnn_terminal_ready_o(terminal_ready),.cnn_terminal_i(terminal),
        .backend_ready_i(1'b1),.model_status_i(4'd9),.record_object_idle_i(object_idle),
        .record_source_needed_i(source_needed),
        .record_transport_fault_i(transport_fault),.record_pcm_valid_o(record_valid),.record_source_allowed_o(record_allowed),
        .record_pcm_o(record_pcm),.record_sequence_o(record_sequence),.record_fault_o(record_fault),.record_failure_o(record_failure),
        .hci_classic_ready_i(1'b1),.phone_owner_ready_i(1'b1),.hci_epoch_i(32'd44),.hci_generation_i(32'd55),
        .command_valid_i(cpu_valid),.command_write_i(cpu_write),.command_address_i(cpu_address),.command_data_i(cpu_data),.command_strobes_i(cpu_strobes),
        .command_ready_o(cpu_ready),.response_error_o(cpu_error),.response_data_o(cpu_response),
        .phone_fault_o(phone_fault),.malformed_packets_o(),.stale_packets_o());
    defparam w.phone_proxy.ROUND_TRIP_TIMEOUT_CYCLES=500;
    defparam m.record_blocks.PARTIAL_TIMEOUT_CYCLES=40;
    defparam m.analysis_blocks.PARTIAL_TIMEOUT_CYCLES=40;
    assign source_needed=1'b0;
    reg analysis_pcm_valid=0,analysis_pcm_last=0,analysis_cancel=0;
    reg [31:0] analysis_pcm=0;
    wire analysis_failed,analysis_busy,analysis_done;
    wire m_done;
    integer cnn_count=0,seal_count=0,record_expected=0;
    reg [127:0] cnn_identity;
    reg frame_valid=0,record_arm=0,record_cancel=0;
    reg [31:0] frame_epoch=7,frame_sequence=100,frame_pcm=0;
    wire record_armed,mrecord_fault,phone_live,mcommand_valid,mcommand_target,mcommand_write;
    wire [11:0] mcommand_address;wire [31:0] mcommand_data;wire [3:0] mcommand_strobes;
    integer owner_delay=0;
    always @(posedge clk)if(!reset_n || !mcommand_valid)owner_delay<=0;else owner_delay<=owner_delay+1;
    wire mcommand_ready=mcommand_valid && owner_allow && owner_delay>=3;
    wire [31:0] mresponse=32'h1111a000+{31'd0,mcommand_target};
    wire hci_ready;wire [31:0] hci_epoch,hci_generation;wire [3:0] model_status;
    reg analysis_start=0;wire analysis_ready,analysis_pcm_ready;
    workstation_task3_m_bus_endpoint #(.BLOCK_PCM(1'b1),.MEDIA_CAP_TIMEOUT_CYCLES(3000)) m(
        .clk_i(clk),.reset_ni(reset_n && !m_observer_reset),.link_ready_i(link),.panic_i(panic),
        .local_boot_i(m_boot),.peer_boot_i(32'd22),.session_i(32'd33),.generation_i(generation),
        .rx_valid_i(wtv),.rx_ready_o(wtr),.rx_channel_i(wtc),.rx_payload_i(wtp),.rx_length_i(wtl),
        .tx_valid_o(mtv),.tx_ready_i(mtr),.tx_channel_o(mtc),.tx_payload_o(mtp),.tx_length_o(mtl),
        .analysis_start_i(analysis_start),.analysis_ready_o(analysis_ready),.analysis_cancel_i(analysis_cancel),
        .analysis_pcm_valid_i(analysis_pcm_valid),.analysis_pcm_last_i(analysis_pcm_last),.analysis_pcm_ready_o(analysis_pcm_ready),.analysis_pcm_i(analysis_pcm),
        .analysis_failed_o(analysis_failed),.analysis_busy_o(analysis_busy),.analysis_done_o(analysis_done),.push_score_valid_o(),.push_score_ready_i(1'b1),.push_score_note_o(),
        .record_arm_i(record_arm),.record_cancel_i(record_cancel),.frame_valid_i(frame_valid),.frame_44k1_i(1'b0),.frame_error_i(1'b0),
        .frame_epoch_i(frame_epoch),.frame_sequence_i(frame_sequence),.frame_pcm_i(frame_pcm),.record_armed_o(record_armed),.record_fault_o(mrecord_fault),
        .phone_owner_idle_i(1'b1),.phone_owner_live_o(phone_live),.phone_command_valid_o(mcommand_valid),.phone_command_ready_i(mcommand_ready),
        .phone_command_target_o(mcommand_target),.phone_command_write_o(mcommand_write),.phone_command_address_o(mcommand_address),
        .phone_command_data_o(mcommand_data),.phone_command_strobes_o(mcommand_strobes),.phone_response_data_i(mresponse),.phone_response_error_i(1'b0),
        .hci_ready_o(hci_ready),.hci_epoch_o(hci_epoch),.hci_generation_o(hci_generation),.model_status_o(model_status),.malformed_packets_o(),.stale_packets_o());

    task check(input bit ok,input [511:0] message);begin checks=checks+1;if(!ok)$fatal(1,"%s at %0t",message,$time);end endtask
    task ticks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task await_phone;integer n;begin n=0;while(!phone_live && n<300)begin ticks(1);n=n+1;end check(phone_live,"phone owner live");ticks(3);end endtask
    task command(input integer lane);integer n;begin
        @(negedge clk);cpu_valid=2'b01<<lane;cpu_write=2'b01<<lane;cpu_address=24'h234123;cpu_data=64'hcafe0001cafe0000;cpu_strobes=8'hff;
        n=0;while(!cpu_ready[lane] && n<600)begin ticks(1);n=n+1;end
        check(cpu_ready[lane] && !cpu_error[lane],"phone command completes during media stall");
        check(cpu_response[32*lane+:32]==32'h1111a000+lane,"phone original owner response");
        cpu_valid=0;ticks(5);
    end endtask
    task observed(input [31:0] seq,input [31:0] pcm);begin
        @(negedge clk);frame_sequence=seq;frame_pcm=pcm;frame_valid=1;ticks(1);frame_valid=0;ticks(8);
    end endtask
    task arm_record;integer n;begin
        @(negedge clk);record_arm=1;ticks(1);record_arm=0;n=0;ticks(2);
        while(!(record_armed && record_allowed && !m.recording.arm_pending) && !mrecord_fault && n<300)begin ticks(1);n=n+1;end
        check(record_armed && record_allowed,"block recording ARM acknowledged");
    end endtask
    task pcm(input [31:0] value,input bit last);integer n;begin
        @(negedge clk);analysis_pcm_valid=1;analysis_pcm=value;analysis_pcm_last=last;
        n=0;while(!analysis_pcm_ready && n<300)begin ticks(1);n=n+1;end
        check(analysis_pcm_ready,"TF source accepts bounded frame");ticks(1);analysis_pcm_valid=0;analysis_pcm_last=0;
    end endtask
    task start_analysis;integer n;begin
        n=0;while(!analysis_ready && n<300)begin ticks(1);n=n+1;end
        check(analysis_ready,"compatible media negotiation enables analysis");analysis_start=1;ticks(1);analysis_start=0;ticks(5);
    end endtask
    task packet(input [3:0] channel,input [5:0] len,input [255:0] payload);begin
        inject=1;ic=channel;il=len;ip=payload;ticks(1);check(wrx_ready,"shared receive consumes injected media error");inject=0;ip=0;ticks(8);
    end endtask
    always @(posedge clk)if(reset_n)begin
        physical_ticks=physical_ticks+1;
        if(cdv && cdr)begin cnn_identity=cdesc[199:72];check(cdesc[199:136]=={m_boot,32'd33},"CNN receives full descriptor context");end
        if(cfv && cfr)begin
            check(cframe[191:64]==cnn_identity,"expanded CNN frame retains full identity");
            check(cframe[63:32]==cnn_count,"expanded CNN indices contiguous");
            check(cframe[31:0]==32'h60000000+cnn_count,"expanded CNN PCM exact");cnn_count=cnn_count+1;
        end
        if(csv && csr)begin check(cnn_count==61,"seal follows every expanded frame");check(cseal[63:32]==61,"seal frame count unchanged");seal_count=seal_count+1;end
        if(record_valid)begin check(record_pcm==32'h70000000+record_expected,"record PCM unaffected by CNN stall");record_expected=record_expected+1;end
        if(mtv && mtr && (mtc==`TASK3_PAIR_CH_ANALYSIS_BLOCK || mtc==`TASK3_PAIR_CH_RECORD_BLOCK))begin
            check(mtl>=12 && mtl<=32 && mtl[1:0]==0,"block length legal");
        end
    end
    reg run_selection_checks=0;
    wire selection_checks_done;
    generate if(REGISTER_W_TX_CLASS && W_BLOCK)begin:g_selection_checks
        reg done=0;
        reg [2:0] pending_classes=0;
        wire phone_class=pending_classes[2],credit_class=pending_classes[1],result_class=pending_classes[0];
        reg [1:0] turn=0;
        reg live_now=1;
        reg [2:0] expected;
        integer mask,t;
        assign selection_checks_done=done;
        initial begin
            wait(run_selection_checks);
            // Exercise the actual endpoint register at arbitrary scheduling
            // states. No packet is delivered while manipulating its inputs.
            force w.tx_valid_o=0;
            force w.live=live_now;
            force w.normal_turn=turn;
            force w.phone_flow_pending=phone_class;
            force w.credit_pending=credit_class;
            force w.result_pending=result_class;
            for(t=0;t<3;t=t+1)for(mask=0;mask<8;mask=mask+1)begin
                turn=2'(t);pending_classes=3'(mask);live_now=1;
                case(t)
                    0:expected=mask[2]?3'b100:mask[1]?3'b010:mask[0]?3'b001:0;
                    1:expected=mask[1]?3'b010:mask[0]?3'b001:mask[2]?3'b100:0;
                    2:expected=mask[0]?3'b001:mask[2]?3'b100:mask[1]?3'b010:0;
                endcase
                @(posedge clk);#1;
                check(w.g_registered_tx_class.selection===expected,"registered class exact priority for all pending combinations");
                @(negedge clk);live_now=0;#1;
                check(!w.phone_request_ready && !w.a_credit_ready && !w.r_credit_ready &&
                      !w.cnn_terminal_ready_o && !w.take_status,"current live revokes every ordinary consumer before next clock");
                @(posedge clk);#1;
                check(w.g_registered_tx_class.selection===0,"session fence clears registered preference");
                @(negedge clk);
            end
            live_now=1;pending_classes=3'b100;turn=0;
            @(posedge clk);#1;
            force w.phone_request=0;force w.phone_batch_valid=0;force w.phone_window_valid=0;
            #1;check(!w.phone_request_ready && !w.phone_batch_ready && !w.phone_window_ready,
                     "vanished phone class cannot consume stale payload");
            @(negedge clk);pending_classes=3'b010;
            @(posedge clk);#1;
            force w.a_credit_valid=0;force w.r_credit_valid=0;
            #1;check(!w.a_credit_ready && !w.r_credit_ready,"vanished credit class cannot acknowledge absent credit");
            @(negedge clk);pending_classes=3'b001;
            @(posedge clk);#1;
            force w.status_pending=0;force w.cnn_terminal_valid_i=0;force w.cnn_score_valid_i=0;
            #1;check(!w.take_status,"vanished status cannot be committed");
            force w.phone_cancel_tx=1;
            #1;check(w.phone_cancel_tx_ready && !w.cnn_terminal_ready_o,"urgent cancel preempts registered ordinary class");
            release w.phone_cancel_tx;
            force w.record_ack_pending=1;
            #1;check(!w.cnn_terminal_ready_o,"record ACK preempts registered ordinary class");
            $display("PASS registered TX class current-live, withdrawn payload and urgent priority checks");
            done=1;
        end
    end else begin:g_no_selection_checks
        assign selection_checks_done=1;
    end endgenerate
    integer i,n,j,old_ticks;reg [255:0] corrupt;reg [127:0] retired_identity;
    initial begin
        ticks(4);reset_n=1;ticks(3);check(!analysis_ready,"no media before link");link=1;await_phone;
        if(!W_BLOCK)begin
            check(!m.media_cap_ready && !analysis_ready,"legacy peer cannot grant block media permission");
            observed(100,0);record_arm=1;ticks(1);record_arm=0;ticks(20);
            check(!record_armed && !record_allowed,"mixed peer cannot arm recording media");command(0);
            n=0;while(!m.media_cap_fault && n<3200)begin ticks(1);n=n+1;end
            check(m.media_cap_fault && !analysis_ready && !record_armed,"mixed version fails within bounded negotiation watchdog");
            check(phone_live && physical_ticks>3000,"mixed version preserves local scheduling and separate control owner");
            $display("PASS task3 mixed media checks=%0d",checks);$finish;
        end
        check(m.media_cap_ready && w.media_cap_ready,"both full-context block capabilities exchanged");
        cdr=0;cfr=0;start_analysis;
        for(i=0;i<13;i=i+1)pcm(32'h60000000+i,0);
        ticks(10);check(w.a_desc_pending && !w.analysis_blocks.active_o,"no initial credit before real CNN descriptor acceptance");
        command(0);
        observed(100,0);arm_record;
        for(i=0;i<12;i=i+1)observed(101+i,32'h70000000+i);
        ticks(70);check(record_expected==12,"record works while CNN descriptor blocked");
        cdr=1;ticks(20);
        for(i=13;i<61;i=i+1)pcm(32'h60000000+i,i==60);
        ticks(150);check(w.analysis_blocks.accepted_blocks_o==8,"CNN blocked at eight reserved blocks");
        check(w.analysis_blocks.count==8 && !w.a_rx_fault,"finite queue retains exactly reserved blocks");
        old_ticks=physical_ticks;
        for(i=12;i<24;i=i+1)observed(101+i,32'h70000000+i);
        command(1);ticks(70);check(record_expected==24,"credit exhausted analysis cannot block record or phone");
        check(physical_ticks>old_ticks,"local physical schedule continues");
        cfr=1;n=0;while(seal_count==0 && n<500)begin ticks(1);n=n+1;end
        check(seal_count==1 && cnn_count==61,"partial tail flush and deferred seal complete");
        terminal={cnn_identity,32'd0,4'd0};terminal_valid=1;n=0;
        while(!terminal_ready && n<100)begin ticks(1);n=n+1;end
        check(terminal_ready,"real owner terminal can return");ticks(1);terminal_valid=0;ticks(30);
        check(!analysis_busy && !analysis_failed,"successful block stream finishes original M source");
        // A current-token legacy DATA in block mode is an explicit stream fault.
        cfr=0;start_analysis;pcm(32'h60000000,0);ticks(12);
        corrupt=0;corrupt[201:0]={2'd1,8'd0,w.a_context,32'd0,32'd1};
        packet(`TASK3_PAIR_CH_ANALYSIS,`TASK3_PAIR_ANALYSIS_BYTES,corrupt);ticks(30);
        check(analysis_failed && !w.a_active,"legacy DATA rejected and matching M task cancelled");
        check(record_allowed && !record_fault,"analysis protocol error isolates recording");
        // A current record token with impossible length is consumed and ends
        // the EXISTING recording source, not an alternate recording backend.
        corrupt=0;corrupt[31:0]=w.record_active_common[31:0];corrupt[63:32]=125;
        packet(`TASK3_PAIR_CH_RECORD_BLOCK,6'd8,corrupt);ticks(30);
        check(record_fault && !record_allowed && !record_armed,"malformed record block terminates original object source");
        generation=2;ticks(10);await_phone;check(!m.media_cap_fault,"fresh pair context renegotiates");
        // A pending descriptor is an independent local slot. Invalid traffic
        // must revoke it even before the real CNN owner can accept it.
        cdr=0;start_analysis;ticks(3);check(w.a_desc_pending,"slow CNN holds only local descriptor slot");
        corrupt=0;corrupt[201:0]={2'd1,8'd0,w.a_context,32'd0,32'd1};
        packet(`TASK3_PAIR_CH_ANALYSIS,`TASK3_PAIR_ANALYSIS_BYTES,corrupt);ticks(20);
        check(analysis_failed && !w.a_desc_pending && !w.a_active,"legacy DATA revokes pending descriptor immediately");
        start_analysis;ticks(3);corrupt=0;corrupt[31:0]=w.a_context[31:0];corrupt[95:64]=1;
        packet(`TASK3_PAIR_CH_ANALYSIS_BLOCK,6'd12,corrupt);ticks(20);
        check(analysis_failed && !w.a_desc_pending,"premature block without initial credit revokes pending context");
        start_analysis;ticks(3);corrupt=0;corrupt[201:0]={2'd0,w.a_descriptor};
        packet(`TASK3_PAIR_CH_ANALYSIS,`TASK3_PAIR_ANALYSIS_BYTES,corrupt);ticks(20);
        check(analysis_failed && !w.a_desc_pending,"duplicate descriptor cannot replace active pending identity");
        retired_identity=w.a_context;
        start_analysis;ticks(3);terminal={retired_identity,32'd0,4'd1};terminal_valid=1;
        n=0;while(!terminal_ready && n<100)begin ticks(1);n=n+1;end
        check(terminal_ready,"late old terminal is drained");ticks(1);terminal_valid=0;ticks(10);
        check(w.a_active && w.a_desc_pending && !analysis_failed,"old terminal cannot retire new full context");
        // Queue a seal while descriptor is waiting, then offer a late block on
        // the exact edge that an empty queue could otherwise publish the seal.
        corrupt=0;corrupt[201:0]={2'd2,8'd0,w.a_context,32'd0,32'd0};
        packet(`TASK3_PAIR_CH_ANALYSIS,`TASK3_PAIR_ANALYSIS_BYTES,corrupt);
        check(w.a_wire_sealed && w.a_seal_pending,"seal remains a persistent wire fence");
        cdr=1;ticks(1);corrupt=0;corrupt[31:0]=w.a_context[31:0];corrupt[95:64]=1;
        packet(`TASK3_PAIR_CH_ANALYSIS_BLOCK,6'd12,corrupt);ticks(20);
        check(analysis_failed && seal_count==1,"late block suppresses same-edge empty-queue seal publication");
        cdr=0;start_analysis;ticks(3);corrupt=0;corrupt[201:0]={2'd2,8'd0,w.a_context,32'd0,32'd0};
        packet(`TASK3_PAIR_CH_ANALYSIS,`TASK3_PAIR_ANALYSIS_BYTES,corrupt);
        packet(`TASK3_PAIR_CH_ANALYSIS,`TASK3_PAIR_ANALYSIS_BYTES,corrupt);ticks(20);
        check(analysis_failed && !w.a_active,"duplicate seal after fence is explicit task failure");
        // Cancellation at every non-full tail length drops partial PCM and old
        // credit; it never emits the partial block into the next generation.
        for(j=1;j<=5;j=j+1)begin
            start_analysis;
            for(i=0;i<j;i=i+1)pcm(32'h60000000+i,0);
            analysis_cancel=1;ticks(1);analysis_cancel=0;ticks(18);
            check(m.analysis_blocks.empty_o && !m.analysis_blocks.active_o && !w.a_active,"cancel clears every partial tail length");
        end
        // A changed advertised media version revokes immediately rather than
        // preserving permission until the age watchdog expires.
        start_analysis;ticks(3);corrupt=0;
        corrupt[223:0]={m_boot,32'd22,32'd33,generation,`TASK3_PAIR_MEDIA_MAGIC,32'd99,`TASK3_PAIR_MEDIA_FEATURES};
        packet(`TASK3_PAIR_CH_MEDIA_CAPS,`TASK3_PAIR_MEDIA_CAPS_BYTES,corrupt);ticks(15);
        check(w.media_cap_fault && !w.a_active,"incompatible capability revokes pending task immediately");
        generation=3;ticks(10);await_phone;
        analysis_cancel=1;panic=1;ticks(2);check(!record_allowed && !m.analysis_blocks.active_o,"PANIC clears partial and media contexts");
        panic=0;analysis_cancel=0;generation=4;ticks(10);await_phone;
        // Standalone legacy peer has no v1 capability: no grant or ARM is inferred.
        n=0;while(!m.media_cap_fault && n<3200)begin ticks(1);n=n+1;end
        check(m.media_cap_fault && !analysis_ready,"missing recurring capability expires media within bound");
        check(phone_live,"media capability failure does not replace phone control owner");
        run_selection_checks=1;wait(selection_checks_done);
        $display("PASS task3 paired PCM blocks checks=%0d cnn_frames=%0d record_frames=%0d seals=%0d",checks,cnn_count,record_expected,seal_count);$finish;
    end
    initial begin #200000;$fatal(1,"block endpoint watchdog");end
endmodule
