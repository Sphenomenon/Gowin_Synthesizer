`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
module tb_workstation_task3_phone_window_owner #(parameter bit W_PHONE_WINDOW=1);
`ifdef TASK3_MIXED_MEDIA
    localparam bit W_BLOCK=0;
`else
    localparam bit W_BLOCK=1;
`endif
    reg clk=0;always #10 clk=~clk;
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
    workstation_task3_w_bus_endpoint #(.BLOCK_PCM(W_BLOCK),.PHONE_WINDOW_BLOCK(W_PHONE_WINDOW),.MEDIA_CAP_TIMEOUT_CYCLES(W_PHONE_WINDOW ? 1000000:3000)) w(
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
    reg compute_clk=0;always #6.510417 compute_clk=~compute_clk;
    wire cb_ready,cb_error,cb_reset,oc_valid,oc_write,oc_ready,oc_error;
    wire [11:0] oc_address;wire [31:0] oc_data,oc_response,cb_response;wire [3:0] oc_strobes;
    wire mcommand_ready=mcommand_target ? mcommand_valid:cb_ready;
    wire [31:0] mresponse=mcommand_target ? 32'hc10c0001:cb_response;
    wire merror=mcommand_target ? 1'b0:cb_error;
    gw138k_apb_cdc command_cdc(
        .reset_n(reset_n && !m_observer_reset),.pclk(clk),.audio_clk(compute_clk),
        .psel(mcommand_valid && !mcommand_target),.penable(mcommand_valid && !mcommand_target),
        .pwrite(mcommand_write),.paddr(mcommand_address),.pwdata(mcommand_data),.pstrb(mcommand_strobes),
        .pready(cb_ready),.pslverr(cb_error),.prdata(cb_response),.command_reset_n(cb_reset),
        .command_valid(oc_valid),.command_ready(oc_ready),.command_write(oc_write),
        .command_address(oc_address),.command_data(oc_data),.command_strobes(oc_strobes),
        .response_data(oc_response),.response_error(oc_error));
    reg [2:0] live_sync=0;
    always @(posedge compute_clk or negedge reset_n)
        if(!reset_n)live_sync<=0;else live_sync<={live_sync[1:0],phone_live};
    integer sample_phase=0,rendered=0,nonzero=0,applied_words=0,wire_blocks=0;
    reg take=0;
    reg [1:0] history_completion=0;
    wire history_done=history_completion[1];
    wire selected,owner_failed,owner_idle,history_clear,serial_hold;
    wire signed [31:0] pcm_l,pcm_r;
    always @(posedge compute_clk or negedge reset_n)
        if(!reset_n)history_completion<=0;
        else history_completion<={history_completion[0],history_clear};
    always @(negedge compute_clk)begin
        take=sample_phase==1599;
        sample_phase=take ? 0:sample_phase+1;
        if(take)physical_ticks=physical_ticks+1;
        if(take && selected && !serial_hold)begin
            rendered=rendered+1;
            if(pcm_l==32'sh1f400000 && pcm_r==-32'sh17700000)nonzero=nonzero+1;
        end
    end
    workstation_ae350_pcm_owner owner(
        .clk_i(compute_clk),.reset_ni(reset_n),.cpu_ready_i(cb_reset),
        .command_valid_i(oc_valid),.command_ready_o(oc_ready),.command_write_i(oc_write),
        .command_address_i(oc_address),.command_data_i(oc_data),.command_strobes_i(oc_strobes),
        .response_data_o(oc_response),.response_error_o(oc_error),
        .session_live_i(live_sync[2]),.controller_epoch_i(32'd44),.transport_generation_i(32'd55),
        .context_ready_i(1'b1),.rate_44100_i(1'b0),.physical_epoch_i(32'd7),
        .tf_busy_i(1'b0),.switch_busy_i(1'b0),.sample_take_i(take),
        .legacy_left_i(32'd0),.legacy_right_i(32'd0),.pcm_left_o(pcm_l),.pcm_right_o(pcm_r),
        .history_clear_o(history_clear),.history_ready_i(1'b1),.history_done_i(history_done),
        .serial_hold_o(serial_hold),.cancel_epoch_o(),.selected_o(selected),.failed_o(owner_failed),.hard_fault_o(),.idle_o(owner_idle));
    always @(posedge compute_clk)if(reset_n && oc_valid && oc_ready && oc_write && oc_address[11])begin
        if(oc_error)$fatal(1,"real PCM1 window rejected");
        applied_words=applied_words+1;
    end
    always @(posedge clk)if(wtv && wtr && wtc==`TASK3_PAIR_CH_PHONE_WINDOW)wire_blocks=wire_blocks+1;
    wire hci_ready;wire [31:0] hci_epoch,hci_generation;wire [3:0] model_status;
    reg analysis_start=0;wire analysis_ready,analysis_pcm_ready;
    workstation_task3_m_bus_endpoint #(.BLOCK_PCM(1'b1),.PHONE_WINDOW_BLOCK(1'b1),.MEDIA_CAP_TIMEOUT_CYCLES(W_PHONE_WINDOW ? 1000000:3000)) m(
        .clk_i(clk),.reset_ni(reset_n && !m_observer_reset),.link_ready_i(link),.panic_i(panic),
        .local_boot_i(m_boot),.peer_boot_i(32'd22),.session_i(32'd33),.generation_i(generation),
        .rx_valid_i(wtv),.rx_ready_o(wtr),.rx_channel_i(wtc),.rx_payload_i(wtp),.rx_length_i(wtl),
        .tx_valid_o(mtv),.tx_ready_i(mtr),.tx_channel_o(mtc),.tx_payload_o(mtp),.tx_length_o(mtl),
        .analysis_start_i(analysis_start),.analysis_ready_o(analysis_ready),.analysis_cancel_i(analysis_cancel),
        .analysis_pcm_valid_i(analysis_pcm_valid),.analysis_pcm_last_i(analysis_pcm_last),.analysis_pcm_ready_o(analysis_pcm_ready),.analysis_pcm_i(analysis_pcm),
        .analysis_failed_o(analysis_failed),.analysis_busy_o(analysis_busy),.analysis_done_o(analysis_done),.push_score_valid_o(),.push_score_ready_i(1'b1),.push_score_note_o(),
        .record_arm_i(record_arm),.record_cancel_i(record_cancel),.frame_valid_i(frame_valid),.frame_44k1_i(1'b0),.frame_error_i(1'b0),
        .frame_epoch_i(frame_epoch),.frame_sequence_i(frame_sequence),.frame_pcm_i(frame_pcm),.record_armed_o(record_armed),.record_fault_o(mrecord_fault),
        .phone_owner_idle_i(owner_idle),.phone_owner_live_o(phone_live),.phone_command_valid_o(mcommand_valid),.phone_command_ready_i(mcommand_ready),
        .phone_command_target_o(mcommand_target),.phone_command_write_o(mcommand_write),.phone_command_address_o(mcommand_address),
        .phone_command_data_o(mcommand_data),.phone_command_strobes_o(mcommand_strobes),.phone_response_data_i(mresponse),.phone_response_error_i(merror),
        .hci_ready_o(hci_ready),.hci_epoch_o(hci_epoch),.hci_generation_o(hci_generation),.model_status_o(model_status),.malformed_packets_o(),.stale_packets_o());


    task check(input bit ok,input [511:0] message);begin checks=checks+1;if(!ok)$fatal(1,"%s at %0t",message,$time);end endtask
    task ticks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task bus(input bit target,input bit write,input [11:0] address,input [31:0] data,output reg [31:0] result);
        integer timeout;begin
            @(negedge clk);cpu_valid=target ? 2:1;cpu_write=write ? cpu_valid:0;
            cpu_address=target ? {address,12'd0}:{12'd0,address};cpu_data=target ? {data,32'd0}:{32'd0,data};cpu_strobes=8'hff;
            timeout=0;while(!cpu_ready[target] && timeout<100000)begin ticks(1);timeout=timeout+1;end
            if(!cpu_ready[target] || cpu_error[target])
                $display("BUS_FAIL target=%0d write=%0d address=%h data=%h ready=%b error=%b timeout=%0d owner_failure=%0d queued=%0d expected_sequence=%0d phone_live=%b tx_fault=%b rx_fault=%b applied=%0d blocks=%0d",
                    target,write,address,data,cpu_ready,cpu_error,timeout,owner.failure,owner.queued,
                    owner.expected_sequence,phone_live,w.phone_window_fault,
                    m.phone_window_fault,applied_words,wire_blocks);
            check(cpu_ready[target] && !cpu_error[target],"actual paired PCM1/clock command completes");
            result=cpu_response[target*32+:32];cpu_valid=0;ticks(7);
        end
    endtask
    reg [31:0] value;
    task wr(input [11:0] address,input [31:0] data);begin bus(0,1,address,data,value);end endtask
    task key(input [31:0] stream);begin wr('h020,44);wr('h024,55);wr('h028,stream);wr('h02c,48000);wr('h030,7);end endtask
    task block(input integer slot,input integer block_sequence);integer i;begin
        for(i=0;i<128;i=i+1)wr(12'('h800+slot*512+i*4),32'he8901f40);
        // This read MUST flush the partial block and wait for the actual owner.
        bus(0,0,'h068,0,value);check(value==32'(block_sequence*128),"staged writes cannot increment committed queue frames");
        key(1);wr('h034,32'(slot));wr('h038,128);wr('h03c,32'(block_sequence));wr('h040,2);
        bus(0,0,'h068,0,value);check(value==32'((block_sequence+1)*128),"COMMIT follows every real window completion");
    end endtask
    integer n,prior_words,prior_samples,prior_ticks;reg [31:0] stale;
    initial begin
        ticks(4);reset_n=1;ticks(3);link=1;
        if(!W_PHONE_WINDOW)begin
            ticks(3100);check(!phone_live && !m.media_cap_ready && !w.media_cap_ready,"old phone policy cannot grant new media or phone owner");
            $display("PASS phone window mixed checks=%0d",checks);$finish;
        end
        n=0;while(!phone_live && n<1000)begin ticks(1);n=n+1;end
        check(phone_live && !phone_fault,"negotiated phone owner armed");ticks(10);
        bus(0,0,0,0,value);check(value==32'h50434d31,"same real PCM1 identity");
        bus(0,0,8,0,value);check(!(value&8),"production sustained capability remains false");
        key(1);wr('h040,1);
        block(0,0);block(1,1);block(2,2);block(3,3);
        check(applied_words==512,"every window word applied exactly once through real CDC");
        check(wire_blocks==104,"128-frame slots use26 bounded blocks each");
        wr('h040,3);n=0;while(nonzero<160 && n<300000)begin ticks(1);n=n+1;end
        check(nonzero>=160 && !owner_failed,"prefilled real owner renders stereo PCM without underrun");
        prior_samples=nonzero;
        // Clock remains a remote owner operation and is ordered after data.
        bus(1,0,0,0,value);check(value==32'hc10c0001,"clock request retains original target");
        wr('h040,4);ticks(2500);check(!selected && owner_idle,"STOP drains the original source-switch owner");
        key(2);wr('h040,1);wr('h800,32'h12345678);
        // PANIC clears partial and any in-flight write; a fresh pair must ARM again.
        prior_ticks=physical_ticks;
        panic=1;ticks(8);panic=0;ticks(30);
        check(!phone_live && !selected,"PANIC revokes remote phone owner");
        // Outwait the actual 12,500-cycle partial flush timer, so this checks
        // cancellation rather than observing an unexpired partial buffer.
        prior_words=applied_words;ticks(13000);check(applied_words==prior_words,"PANIC cannot replay cancelled partial words");
        check(physical_ticks>prior_ticks+10,"independent sample schedule runs while cancelled phone queue waits");
        generation=2;ticks(10);n=0;while(!phone_live && n<1000)begin ticks(1);n=n+1;end
        check(phone_live && !phone_fault,"fresh pair generation can arm after PANIC");
        key(3);wr('h040,1);wr('h800,32'h01020304);link=0;ticks(8);link=1;ticks(100);
        check(!phone_live,"link reconnection never rearms old pair context");
        check(nonzero>=prior_samples,"base sample schedule continues across phone faults");
        $display("PASS phone window real owner checks=%0d words=%0d blocks=%0d nonzero=%0d sample_ticks=%0d",checks,applied_words,wire_blocks,nonzero,physical_ticks);$finish;
    end
    initial begin #100000000;$fatal(1,"phone owner integration watchdog");end
endmodule
