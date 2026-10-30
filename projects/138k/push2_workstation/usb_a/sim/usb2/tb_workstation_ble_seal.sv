`timescale 1ns/1ps
module tb_workstation_ble_seal;
    reg clk=0;always #10 clk=~clk;
    reg resetn=0,enable=1,connected=1,source_ready=1,source_fault=0,pcm_valid=0;
    reg [31:0] pcm_pair=0;
    reg command_start=0,seal_hold=0,seal_request=0;
    reg [7:0] opcode=0;
    reg [31:0] request_id=1;
    reg [15:0] payload_length=0;
    reg [127:0] payload=0;
    reg [6:0] command_addr=0;
    wire command_done,seal_ready,seal_pending,seal_done,seal_failed;
    wire [7:0] command_status,command_data,record_state,seal_state;
    wire [3:0] seal_failure;
    wire [31:0] recording_id,recorded_frames,seal_id,seal_frames,seal_crc;
    localparam BOOT_ID=64'h1234567811223344;
    localparam A=32'hfedc1234,B=32'h98765678,C=32'h43218765;
    integer cases=0,done_count=0,failed_count=0,crc_phases=0,held_checks=0;
    reg done_q=0,failed_q=0;
    ble_recording #(.EXTERNAL_PCM(1),.CAPACITY_FRAMES(32),.EXTERNAL_SEAL_PROTOCOL(1)) dut(
        .clk(clk),.resetn(resetn),.enable(enable),.connected(connected),.transfer_subscribed(1'b1),
        .pcm_valid_i(pcm_valid),.pcm_pair_i(pcm_pair),.source_ready_i(source_ready),.source_fault_i(source_fault),
        .boot_id(BOOT_ID),.att_value_limit(9'd20),.elapsed_ms(32'd100),
        .command_start(command_start),.command_replay(1'b0),.opcode(opcode),.request_id(request_id),
        .nonce(64'habcdef),.payload_length(payload_length),.payload(payload),.replay_recording_id(32'd0),
        .command_done(command_done),.command_status(command_status),.command_length(),
        .command_addr(command_addr),.command_data(command_data),.record_state(record_state),
        .recording_id(recording_id),.recorded_frames(recorded_frames),.capacity_frames(),
        .transfer_valid(),.transfer_compact(),.transfer_bulk(),.transfer_direct(),.transfer_length(),
        .transfer_addr(13'd0),.transfer_data(),.transfer_consume(1'b0),
        .seal_hold_i(seal_hold),.seal_request_i(seal_request),.seal_ready_o(seal_ready),
        .seal_pending_o(seal_pending),.seal_done_o(seal_done),.seal_failed_o(seal_failed),
        .seal_failure_code_o(seal_failure),.seal_record_state_o(seal_state),
        .seal_recording_id_o(seal_id),.seal_frames_o(seal_frames),.seal_crc_o(seal_crc));
    always @(negedge clk)if(resetn)begin
        if(seal_done)begin
            if(done_q || seal_failed || seal_pending || dut.capture_state!=0 ||
               (record_state!=0 && record_state!=4) || seal_id!=recording_id || seal_frames!=recorded_frames ||
               (record_state==4 && seal_crc!=dut.object_crc))$fatal(1,"seal ACK escaped committed identity/CRC proof");
            done_count=done_count+1;
        end
        if(seal_failed)begin
            if(failed_q || seal_done || seal_failure==0)$fatal(1,"seal failure pulse invalid");
            failed_count=failed_count+1;
        end
        done_q=seal_done;failed_q=seal_failed;
    end else begin done_q=0;failed_q=0;end
    function [31:0] word_crc(input [31:0] previous,input [31:0] value);
        reg [31:0] c;integer i,j;
        begin c=previous;for(i=0;i<4;i=i+1)begin
            c=c^((value>>(8*i))&255);for(j=0;j<8;j=j+1)c=(c>>1)^(c[0]?32'hedb88320:0);
        end word_crc=c;end
    endfunction
    task reset_case;
        begin
            @(negedge clk);resetn=0;enable=1;connected=1;source_ready=1;source_fault=0;
            pcm_valid=0;command_start=0;seal_request=0;seal_hold=0;
            repeat(4)@(negedge clk);resetn=1;repeat(4)@(negedge clk);
            if(!seal_ready)$fatal(1,"seal not ready after reset");
        end
    endtask
    task command(input [7:0] op,input [15:0] length,input [127:0] data,input [7:0] expected);
        integer n;
        begin
            @(negedge clk);opcode=op;payload_length=length;payload=data;command_start=1;
            @(negedge clk);command_start=0;n=0;
            while(!command_done)begin @(negedge clk);n=n+1;if(n>40)$fatal(1,"command timeout");end
            if(command_status!=expected)$fatal(1,"held command status op=%h got=%h expected=%h",op,command_status,expected);
            request_id=request_id+1;@(negedge clk);
        end
    endtask
    task start_object;
        begin command(8'h20,8,{64'd0,32'd32,32'd1},1);end
    endtask
    task sample(input [31:0] value);
        begin @(negedge clk);pcm_pair=value;pcm_valid=1;@(negedge clk);pcm_valid=0;repeat(8)@(negedge clk);end
    endtask
    task pulse_seal;
        begin @(negedge clk);seal_hold=1;seal_request=1;@(negedge clk);seal_request=0;end
    endtask
    task await_result(input integer target_done,input integer target_failed);
        integer n;
        begin
            n=0;
            while(done_count<target_done || failed_count<target_failed || seal_pending)begin
                @(negedge clk);n=n+1;if(n>200)$fatal(1,"seal result timeout done=%0d/%0d fail=%0d/%0d state=%0d capture=%0d",done_count,target_done,failed_count,target_failed,record_state,dut.capture_state);
            end
            repeat(3)@(negedge clk);
            if(done_count!=target_done || failed_count!=target_failed)$fatal(1,"seal emitted extra result");
        end
    endtask
    task check_ready(input [31:0] rid,input [31:0] frames,input [31:0] crc);
        begin
            if(record_state!=4 || seal_state!=4 || recording_id!=rid || seal_id!=rid ||
               recorded_frames!=frames || seal_frames!=frames || dut.object_crc!==crc || seal_crc!==crc)
                $fatal(1,"sealed prefix differs id=%0d/%0d frames=%0d/%0d CRC=%h/%h expected=%h",seal_id,rid,seal_frames,frames,seal_crc,dut.object_crc,crc);
        end
    endtask
    task check_task(input [31:0] operation,input [7:0] phase,input [7:0] result);
        begin
            command(4,4,{96'd0,operation},0);command_addr=9;#1;if(command_data!=phase)$fatal(1,"task phase");
            command_addr=10;#1;if(command_data!=result)$fatal(1,"task result");
        end
    endtask
    integer d,f,phase;
    reg [31:0] rid,crc;
    initial begin
        // No BLE initialization/connection or audio source is needed for EMPTY.
        reset_case();enable=0;connected=0;source_ready=0;d=done_count;f=failed_count;
        pulse_seal();await_result(d+1,f);
        if(seal_state!=0 || seal_id!=0 || seal_frames!=0 || seal_crc!=0)$fatal(1,"disabled EMPTY identity");cases=cases+1;
        // Request at every remaining CRC byte boundary, including just after
        // commit. The accepted second word must be entirely in the old object.
        for(phase=0;phase<6;phase=phase+1)begin
            reset_case();start_object();sample(A);rid=recording_id;crc=~word_crc(word_crc(32'hffffffff,A),B);
            @(negedge clk);pcm_pair=B;pcm_valid=1;
            @(negedge clk);pcm_valid=0;
            repeat(phase)@(negedge clk);
            d=done_count;f=failed_count;seal_hold=1;seal_request=1;
            repeat(12)begin @(negedge clk);if(seal_ready)$fatal(1,"held request accepted twice");end
            seal_request=0;await_result(d+1,f);check_ready(rid,2,crc);check_task(1,2,0);
            command(8'h20,8,{64'd0,32'd32,32'd1},8'h82);
            command(8'h21,12,{32'd0,rid,BOOT_ID},8'h82);
            command(8'h23,12,{32'd0,rid,BOOT_ID},8'h82);
            sample(C);check_ready(rid,2,crc);
            repeat(8)begin @(negedge clk);if(seal_id!=rid || seal_frames!=2 || seal_crc!=crc)$fatal(1,"held snapshot mutated");held_checks=held_checks+1;end
            // Frozen READY is independent of BLE enable and 48k availability.
            enable=0;connected=0;source_ready=0;repeat(4)@(negedge clk);
            pulse_seal();await_result(d+2,f);check_ready(rid,2,crc);
            crc_phases=crc_phases+1;cases=cases+1;
        end
        // No first PCM: preserve the zero-length object's ID and CRC, while
        // START task fails rather than pretending a first frame was recorded.
        reset_case();start_object();rid=recording_id;d=done_count;f=failed_count;
        pulse_seal();await_result(d+1,f);check_ready(rid,0,0);check_task(1,3,8'h83);cases=cases+1;
        // A command accepted on the SAME edge as local seal cannot allocate.
        reset_case();d=done_count;f=failed_count;
        fork begin command(8'h20,8,{64'd0,32'd32,32'd1},8'h82);end
             begin pulse_seal();end join
        await_result(d+1,f);if(recording_id!=0 || dut.object_counter!=0)$fatal(1,"in-flight START crossed seal barrier");cases=cases+1;
        // Previously accepted STOP keeps its real task and finishes the old ID.
        reset_case();start_object();sample(A);rid=recording_id;crc=~word_crc(word_crc(32'hffffffff,A),B);d=done_count;f=failed_count;
        @(negedge clk);pcm_pair=B;pcm_valid=1;
        @(negedge clk);pcm_valid=0;opcode=8'h21;payload_length=12;payload={32'd0,rid,BOOT_ID};command_start=1;
        @(negedge clk);command_start=0;
        if(!command_done || command_status!=1)$fatal(1,"old STOP was not accepted");
        seal_hold=1;seal_request=1;@(negedge clk);seal_request=0;
        await_result(d+1,f);check_ready(rid,2,crc);check_task(2,2,0);cases=cases+1;
        // Same-edge CLEAR cannot erase the snapshot; after hold releases,
        // explicit CLEAR is allowed, and 44.1/unavailable source rejects START.
        d=done_count;f=failed_count;
        fork begin command(8'h23,12,{32'd0,rid,BOOT_ID},8'h82);end begin pulse_seal();end join
        await_result(d+1,f);check_ready(rid,2,crc);
        seal_hold=0;command(8'h23,12,{32'd0,rid,BOOT_ID},0);
        source_ready=0;command(8'h20,8,{64'd0,32'd32,32'd1},8'h83);
        pulse_seal();await_result(d+2,f);if(seal_id!=0 || seal_state!=0)$fatal(1,"prior CLEAR mixed old object");cases=cases+1;
        // Real readiness/fault/enable loss before seal ACK remains failure.
        for(phase=0;phase<3;phase=phase+1)begin
            reset_case();start_object();sample(A);rid=recording_id;d=done_count;f=failed_count;
            @(negedge clk);pcm_pair=B;pcm_valid=1;
            @(negedge clk);pcm_valid=0;seal_hold=1;seal_request=1;
            @(negedge clk);seal_request=0;
            if(phase==0)source_ready=0;else if(phase==1)source_fault=1;else enable=0;
            await_result(d,f+1);
            if(record_state!=5 || recording_id!=rid || seal_id!=rid || seal_crc!=0 || seal_failure!=(phase==2?2:4))
                $fatal(1,"source loss masqueraded as normal seal phase=%0d failure=%0d state=%0d",phase,seal_failure,record_state);
            source_ready=1;source_fault=0;enable=1;repeat(10)@(negedge clk);
            if(seal_done || done_count!=d || failed_count!=f+1)$fatal(1,"failed seal later reported success");
            // An already failed object has an explicit idempotent failure.
            pulse_seal();await_result(d,f+2);if(seal_failure!=1 || seal_id!=rid)$fatal(1,"existing ERROR was hidden");cases=cases+1;
        end
        // Source loss at the final ACK boundary is still a failed transaction;
        // a later new request may separately ACK that already frozen object.
        reset_case();start_object();sample(A);rid=recording_id;crc=~word_crc(32'hffffffff,A);d=done_count;f=failed_count;
        pulse_seal();wait(record_state==4);@(negedge clk);source_ready=0;
        await_result(d,f+1);check_ready(rid,1,crc);
        if(seal_failure!=4)$fatal(1,"last source loss escaped seal failure");
        pulse_seal();await_result(d+1,f+1);check_ready(rid,1,crc);cases=cases+1;
        // Watchdog fails once yet still permits eventual real cleanup. Force
        // only the completion boundary, so PCM/CRC are not altered by injection.
        reset_case();start_object();sample(A);rid=recording_id;crc=~word_crc(32'hffffffff,A);d=done_count;f=failed_count;
        force dut.seal_commit=1'b0;pulse_seal();repeat(80)@(negedge clk);
        if(failed_count!=f+1 || done_count!=d || seal_failure!=8 || !seal_pending)$fatal(1,"seal timeout invented completion");
        release dut.seal_commit;await_result(d,f+1);check_ready(rid,1,crc);cases=cases+1;
        if(crc_phases!=6 || held_checks!=48 || cases!=16)$fatal(1,"missing BLE seal coverage cases=%0d",cases);
        $display("PASS ble_external_seal: cases=%0d crc_phases=%0d held_checks=%0d done=%0d failed=%0d",cases,crc_phases,held_checks,done_count,failed_count);$finish;
    end
    initial begin #2000000;$fatal(1,"BLE seal watchdog");end
endmodule
