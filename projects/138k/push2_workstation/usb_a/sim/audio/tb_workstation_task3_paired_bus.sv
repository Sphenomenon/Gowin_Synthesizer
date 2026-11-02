`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
module tb_workstation_task3_paired_bus;
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
    workstation_task3_w_bus_endpoint w(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),
        .local_boot_i(32'd22),.peer_boot_i(m_boot),.session_i(32'd33),.generation_i(generation),
        .rx_valid_i(inject || mtv),.rx_ready_o(wrx_ready),.rx_channel_i(inject?ic:mtc),.rx_payload_i(inject?ip:mtp),.rx_length_i(inject?il:mtl),
        .tx_valid_o(wtv),.tx_ready_i(wtr),.tx_channel_o(wtc),.tx_payload_o(wtp),.tx_length_o(wtl),
        .cnn_desc_valid_o(cdv),.cnn_desc_ready_i(cdr),.cnn_desc_o(cdesc),
        .cnn_frame_valid_o(cfv),.cnn_frame_ready_i(cfr),.cnn_frame_o(cframe),
        .cnn_seal_valid_o(csv),.cnn_seal_ready_i(csr),.cnn_seal_o(cseal),
        .cnn_cancel_valid_o(ccv),.cnn_cancel_ready_i(ccr),.cnn_cancel_o(ccancel),
        .cnn_score_valid_i(1'b0),.cnn_score_ready_o(),.cnn_score_i(167'd0),
        .cnn_terminal_valid_i(1'b0),.cnn_terminal_ready_o(),.cnn_terminal_i(164'd0),
        .backend_ready_i(1'b1),.model_status_i(4'd9),.record_object_idle_i(object_idle),
        .record_source_needed_i(source_needed),
        .record_transport_fault_i(transport_fault),.record_pcm_valid_o(record_valid),.record_source_allowed_o(record_allowed),
        .record_pcm_o(record_pcm),.record_sequence_o(record_sequence),.record_fault_o(record_fault),.record_failure_o(record_failure),
        .hci_classic_ready_i(1'b1),.phone_owner_ready_i(1'b1),.hci_epoch_i(32'd44),.hci_generation_i(32'd55),
        .command_valid_i(cpu_valid),.command_write_i(cpu_write),.command_address_i(cpu_address),.command_data_i(cpu_data),.command_strobes_i(cpu_strobes),
        .command_ready_o(cpu_ready),.response_error_o(cpu_error),.response_data_o(cpu_response),
        .phone_fault_o(phone_fault),.malformed_packets_o(),.stale_packets_o());
    defparam w.phone_proxy.ROUND_TRIP_TIMEOUT_CYCLES=80;
    workstation_task3_record_source_gate #(.WAIT_CYCLES(200)) source_gate(
        .clk_i(clk),.reset_ni(reset_n),.command_start_i(engine_command),.command_opcode_i(8'h20),
        .object_idle_i(engine_state==0),.source_ready_i(record_allowed && record_valid),.source_fault_i(record_fault),
        .engine_done_i(engine_done),.record_state_i(engine_state),.engine_start_o(engine_start),.source_needed_o(source_needed),.timed_out_o());
    // Same maintained physical engine, with a small simulation-only local RAM.
    // Production W still selects the single 60s raw-DDR store.
    workstation_ble_record_data_engine #(.CAPACITY_FRAMES(32),.EXTERNAL_PCM(1)) engine(
        .clk(clk),.resetn(reset_n),.enable(1'b1),.connected(1'b1),.transfer_subscribed(1'b1),
        .pcm_valid_i(record_valid),.source_ready_i(record_allowed),.source_fault_i(record_fault),.pcm_pair_i(record_pcm),
        .boot_id(64'd123),.att_value_limit(9'd247),.elapsed_ms(32'd100),
        .command_start(engine_start),.command_flags_i(5'd0),.command_object_id_i(32'd1),.command_transfer_id_i(32'd0),
        .opcode(8'h20),.request_id(32'd1),.nonce(64'd10),.payload_length(16'd8),.payload({64'd0,32'd4,32'd1}),
        .command_done(engine_done),.command_status(engine_status),.command_length(),.command_addr(7'd0),.command_data(),
        .record_state(engine_state),.recording_id(),.recorded_frames(engine_frames),.capacity_frames(),
        .transfer_valid(),.transfer_compact(),.transfer_bulk(),.transfer_direct(),.transfer_length(),
        .transfer_addr(13'd0),.transfer_data(),.transfer_consume(1'b0),
        .seal_hold_i(1'b0),.seal_request_i(1'b0),.seal_ready_o(),.seal_pending_o(),.seal_done_o(),.seal_failed_o(),
        .seal_failure_code_o(),.seal_record_state_o(),.seal_recording_id_o(),.seal_frames_o(),.seal_crc_o(),.idle_o(engine_idle));
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
    workstation_task3_m_bus_endpoint m(
        .clk_i(clk),.reset_ni(reset_n && !m_observer_reset),.link_ready_i(link),.panic_i(panic),
        .local_boot_i(m_boot),.peer_boot_i(32'd22),.session_i(32'd33),.generation_i(generation),
        .rx_valid_i(wtv),.rx_ready_o(wtr),.rx_channel_i(wtc),.rx_payload_i(wtp),.rx_length_i(wtl),
        .tx_valid_o(mtv),.tx_ready_i(mtr),.tx_channel_o(mtc),.tx_payload_o(mtp),.tx_length_o(mtl),
        .analysis_start_i(analysis_start),.analysis_ready_o(analysis_ready),.analysis_cancel_i(1'b0),
        .analysis_pcm_valid_i(1'b0),.analysis_pcm_last_i(1'b0),.analysis_pcm_ready_o(analysis_pcm_ready),.analysis_pcm_i(32'd0),
        .analysis_failed_o(),.analysis_busy_o(),.analysis_done_o(),.push_score_valid_o(),.push_score_ready_i(1'b1),.push_score_note_o(),
        .record_arm_i(record_arm),.record_cancel_i(record_cancel),.frame_valid_i(frame_valid),.frame_44k1_i(1'b0),.frame_error_i(1'b0),
        .frame_epoch_i(frame_epoch),.frame_sequence_i(frame_sequence),.frame_pcm_i(frame_pcm),.record_armed_o(record_armed),.record_fault_o(mrecord_fault),
        .phone_owner_idle_i(1'b1),.phone_owner_live_o(phone_live),.phone_command_valid_o(mcommand_valid),.phone_command_ready_i(mcommand_ready),
        .phone_command_target_o(mcommand_target),.phone_command_write_o(mcommand_write),.phone_command_address_o(mcommand_address),
        .phone_command_data_o(mcommand_data),.phone_command_strobes_o(mcommand_strobes),.phone_response_data_i(mresponse),.phone_response_error_i(1'b0),
        .hci_ready_o(hci_ready),.hci_epoch_o(hci_epoch),.hci_generation_o(hci_generation),.model_status_o(model_status),.malformed_packets_o(),.stale_packets_o());
    task check(input bit ok,input [255:0] message);begin checks=checks+1;if(!ok)$fatal(1,"%s at %0t",message,$time);end endtask
    task ticks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task await_phone;integer n;begin n=0;while(!phone_live && n<100)begin ticks(1);n=n+1;end check(phone_live,"phone owner live after status");ticks(5);end endtask
    task command(input integer lane);integer n;begin
        @(negedge clk);cpu_valid=2'b01<<lane;cpu_write=2'b01<<lane;cpu_address=24'h234123;cpu_data=64'hcafe0001cafe0000;cpu_strobes=8'hff;
        n=0;while(!cpu_ready[lane] && n<150)begin ticks(1);n=n+1;end
        check(cpu_ready[lane],"remote caller completes");check(!cpu_error[lane],"remote caller success");
        check(cpu_response[32*lane+:32]==32'h1111a000+lane,"matched response payload");
        cpu_valid=0;ticks(5);
    end endtask
    task observed(input [31:0] seq,input [31:0] pcm);begin
        @(negedge clk);frame_sequence=seq;frame_pcm=pcm;frame_valid=1;ticks(1);frame_valid=0;ticks(8);
    end endtask
    task arm_record;integer n;begin
        @(negedge clk);record_arm=1;ticks(1);record_arm=0;n=0;ticks(2);
        while(!(record_armed && record_allowed && !m.recording.arm_pending) && !mrecord_fault && n<100)begin ticks(1);n=n+1;end
    end endtask
    always @(posedge clk)if(reset_n)begin
        physical_ticks=physical_ticks+1;
        if(wtv && wtr)begin
            if(wtc==`TASK3_PAIR_CH_STATUS)begin status_seen=1;status_count=status_count+1;end
            if(wtc==`TASK3_PAIR_CH_PHONE && wtp[179:178]==`TASK3_PAIR_KIND_ARM)check(status_seen,"status precedes phone ARM");
        end
        if(mcommand_valid && mcommand_ready)begin
            check(mcommand_write,"remote write preserved");check(mcommand_strobes==15,"remote strobes preserved");
            check(mcommand_address==(mcommand_target?12'h234:12'h123),"remote address preserved");
            check(mcommand_data==(mcommand_target?32'hcafe0001:32'hcafe0000),"remote data preserved");phone_count=phone_count+1;
        end
        if(record_valid)begin
            check(record_pcm==32'h70000000+record_count,"record PCM ordering");
            check(record_sequence==record_count,"single real object observer sequence");record_count=record_count+1;
        end
    end
    integer i,before_ticks;
    initial begin
        ticks(4);reset_n=1;ticks(4);check(!phone_live && !record_allowed,"disabled business endpoint closed");link=1;await_phone;
        check(hci_ready && hci_epoch==44 && hci_generation==55 && model_status==9,"actual W status reaches M");
        command(0);command(1);check(phone_count==2,"both original APB targets used");
        observed(100,0);arm_record;check(record_armed && record_allowed,"explicit record arm ACK");
        for(i=0;i<16;i=i+1)observed(101+i,32'h70000000+i);
        ticks(30);check(record_count==16,"all final tap frames delivered");
        record_cancel=1;ticks(1);record_cancel=0;ticks(20);check(!record_allowed,"matching cancellation fences source");
        generation=2;object_idle=0;status_seen=0;ticks(5);await_phone;
        observed(200,0);arm_record;ticks(30);check(mrecord_fault && !record_allowed,"busy real record object rejects arm");
        generation=3;object_idle=1;status_seen=0;ticks(5);await_phone;
        observed(300,0);arm_record;check(record_armed,"fresh generation rearms retired source");
        before_ticks=physical_ticks;link=0;ticks(10);check(!record_allowed && !phone_live,"disconnect immediately fences branches");
        check(physical_ticks-before_ticks==10,"physical sample observer never waits");
        link=1;generation=4;status_seen=0;ticks(5);await_phone;
        owner_allow=0;cpu_valid=1;cpu_write=1;cpu_address=0;cpu_data=0;cpu_strobes=15;
        i=0;while(!cpu_ready[0] && i<200)begin ticks(1);i=i+1;end
        check(cpu_ready[0] && cpu_error[0] && phone_fault,"uncertain remote timeout fails caller");cpu_valid=0;ticks(20);check(!phone_live,"timeout sends matching remote cancellation");
        generation=5;owner_allow=1;status_seen=0;ticks(5);await_phone;
        inject=1;ic=`TASK3_PAIR_CH_RECORD;il=`TASK3_PAIR_RECORD_BYTES;ip=256'd1<<255;ticks(1);inject=0;ticks(3);
        check(w.malformed_packets_o==1,"malformed high padding drained and counted");
        panic=1;ticks(1);check(!phone_live && !record_allowed,"PANIC revokes remote branches");
        engine_command=1;ticks(1);engine_command=0;ticks(210);
        check(source_gate.timed_out_o && engine_status==8'h83 && engine_state==0 && !source_needed,
              "bounded tap acquisition returns real engine failure when link unavailable");
        panic=0;m_observer_reset=1;ticks(2);m_boot=111;generation=6;m_observer_reset=0;status_seen=0;ticks(5);await_phone;
        check(!record_armed,"expired recording demand never arms after reconnect");
        observed(500,0);engine_command=1;ticks(1);engine_command=0;
        i=0;while(!record_allowed && i<100)begin ticks(1);i=i+1;end
        check(record_allowed && record_armed,"actual REC_START demand automatically arms M tap");
        check(m.record_generation==1 && w.record_active_local>1,"independent M reboot maps fresh wire key to W monotonic generation");
        // The first observed frame qualifies the real source. The gate then
        // releases REC_START; the engine starts capturing from the next frame.
        observed(501,32'h70000010);ticks(10);
        check(engine_state==1 && engine_status==0,"same physical engine accepts acquired source");
        for(i=0;i<4;i=i+1)observed(502+i,32'h70000011+i);
        ticks(30);check(engine_state==4 && engine_frames==4,"same engine seals real streamed recording");
        check(!source_needed && !record_allowed && !record_armed,"terminal object cancels M tap automatically");
        $display("PASS task3 paired typed bus checks=%0d record_frames=%0d phone_commands=%0d status=%0d engine_frames=%0d",checks,record_count,phone_count,status_count,engine_frames);$finish;
    end
    initial begin #200000;$fatal(1,"paired fixture watchdog");end
endmodule
