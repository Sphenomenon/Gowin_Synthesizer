`timescale 1ns/1ps
`default_nettype none
module tb_workstation_pcm_ddr_backend #(
    parameter integer CASE=0,RATE_44K1=0,COMPETITION=0,FIFO_BITS=4,DDR_BUDGET=128,FAULT_ENABLE=1,FAULT_START_PHASE=0
);
    reg clk=0;always #5 clk=~clk; // real 100-MHz DDR UI time base
    reg rstn=0,create=0,seal=0,cancel=0,soft_reset=0,clear=0;
    wire create_ready,clear_ready,captured,quiet;
    reg [63:0] object_id=1;
    reg rate=RATE_44K1;
    reg [31:0] epoch=17,first_sequence=32'hfffffff0,limit=16384;
    reg pcm_valid=0,source_ready=1,source_error=0,pcm_rate=RATE_44K1;
    reg [31:0] pcm=0,sequence_number=0,pcm_epoch=17;
    wire [3:0] state,failure;
    wire [63:0] stored_id;
    wire stored_rate;
    wire [31:0] stored_epoch,frames,committed,max_cmd_wait,max_read_wait,discarded;
    wire [FIFO_BITS:0] fifo_peak;
    reg ref_acquire=0,ref_release=0;
    reg [63:0] ref_id=1;
    wire ref_ready,ref_held,ref_granted,ref_error,ref_released;
    reg download=0,download_ready=0;
    reg [31:0] offset=0,length=0;
    wire download_req_ready,download_valid,download_last,download_done,download_error;
    wire [255:0] download_data;
    wire [5:0] download_bytes;
    wire request,write_request,request_ready,response;
    wire [28:0] address;
    wire [255:0] write_data,response_data;
    wire [31:0] mask;
    ddr_address_map_guard allocation_guard();
    reg force_transport_fault=0,inject_bus_response=0,inject_bridge_completion=0,traffic_enable=1,test_cpu_blocker=0;
    wire transport_fault;
    workstation_pcm_ddr_backend #(.FIFO_ADDRESS_BITS(FIFO_BITS),.DDR_BUDGET_CYCLES(DDR_BUDGET),.SOURCE_GAP_CYCLES(4096),
        .TRANSPORT_FAULT_ENABLE(FAULT_ENABLE)) dut(
        .clk_i(clk),.rst_ni(rstn),.create_i(create),.create_ready_o(create_ready),
        .object_id_i(object_id),.rate_44k1_i(rate),.epoch_i(epoch),.first_sequence_i(first_sequence),.limit_frames_i(limit),
        .seal_i(seal),.cancel_i(cancel),.soft_reset_i(soft_reset),.clear_i(clear),.clear_ready_o(clear_ready),
        .pcm_valid_i(pcm_valid),.source_ready_i(source_ready),.source_error_i(source_error),
        .pcm_pair_i(pcm),.pcm_sequence_i(sequence_number),.pcm_epoch_i(pcm_epoch),.pcm_44k1_i(pcm_rate),
        .capture_o(captured),.state_o(state),.failure_code_o(failure),.object_id_o(stored_id),
        .rate_44k1_o(stored_rate),.epoch_o(stored_epoch),.frames_o(frames),.committed_frames_o(committed),
        .quiescent_o(quiet),.fifo_peak_o(fifo_peak),.max_command_wait_o(max_cmd_wait),.max_read_wait_o(max_read_wait),
        .discarded_responses_o(discarded),.reference_acquire_i(ref_acquire),.reference_release_i(ref_release),
        .reference_object_id_i(ref_id),.reference_ready_o(ref_ready),.reference_held_o(ref_held),
        .reference_granted_o(ref_granted),.reference_error_o(ref_error),.reference_released_o(ref_released),
        .download_i(download),.download_ready_o(download_req_ready),.download_offset_i(offset),.download_length_i(length),
        .download_valid_o(download_valid),.download_ready_i(download_ready),.download_data_o(download_data),
        .download_bytes_o(download_bytes),.download_last_o(download_last),.download_done_o(download_done),.download_error_o(download_error),
        .ddr_valid_o(request),.ddr_write_o(write_request),.ddr_address_o(address),.ddr_data_o(write_data),.ddr_mask_o(mask),
        .ddr_ready_i(request_ready),.ddr_response_i(response),.ddr_read_data_i(response_data),.transport_fault_i(transport_fault));

    reg force_stall=0,hold_response=0,inject_response=0;
    integer cycles=0;
    always @(posedge clk)cycles=cycles+1;
    wire native_ready=!force_stall && (cycles%11!=0) && (cycles%17!=0);
    wire native_en,native_write;
    wire [28:0] native_address;
    wire [255:0] native_data;
    wire [31:0] native_mask;
    reg memory_response=0;
    reg [255:0] memory_response_data=0;
    wire native_record=native_address>=29'h0c140000 && native_address<29'h0c144000;
    wire native_record_accept=native_en && native_record;
    integer scan_ops=0,audio_ops=0,display_ops=0,delay_ops=0,cpu_ops=0,writer_ops=0,music_ops=0;
    integer record_slot_count=0,record_core_count=0,record_native_count=0;
    integer slot_before=0,core_before=0,native_before=0,discard_before=0;
    generate if(COMPETITION)begin:g_real_arbiter
        // Genuine optional owner8 path; music/NN traffic remains on owner5.
        // Neither local enqueue nor core-buffer entry acknowledges the backend.
        wire submitted,bridge_fault,record_native_ready,record_transport_fault;
        wire local_ready,record_slot_valid,record_response,bus_transport_fault;
        wire [8:0] slot_accept,core_accept,native_accept;
        wire [255:0] returned;
        wire [2:0] app_cmd;
        wire scan_ready,audio_ready,display_ready,delay_ready,cpu_ready,writer_ready;
        wire app_en,app_wren,app_wend,fault;
        workstation_recording_ddr_native_bridge u_bridge(
            .clk_i(clk),.rst_ni(rstn),.published_valid_i(request),.slot_ready_i(local_ready),
            .native_accept_i(native_accept[8] || inject_bridge_completion),.transport_fault_i(bus_transport_fault),
            .slot_valid_o(record_slot_valid),.native_ready_o(record_native_ready),
            .transport_fault_o(record_transport_fault),.submitted_o(submitted),.protocol_fault_o(bridge_fault));
        assign request_ready=record_native_ready;
        assign transport_fault=record_transport_fault || force_transport_fault;
        assign response=record_response || inject_response;
        assign response_data=returned;
        assign native_en=app_en;
        assign native_write=app_wren;
        workstation_recording_ddr_client_queues #(.TAG_BITS(5),.RECORDING_ENABLE(1)) arbiter(
            .clk(clk),.reset_n(rstn),.bist_done(1'b1),.bist_valid(1'b0),.bist_write(1'b0),
            .bist_address(29'd0),.bist_data(256'd0),.bist_ready(),.bist_response(),
            .scan_valid(traffic_enable && cycles%16<2),.scan_address(29'h10),.scan_ready(scan_ready),.scan_response(),
            .display_valid(traffic_enable && cycles%37==0),.display_address(29'h200008),.display_ready(display_ready),.display_response(),
            .audio_valid(traffic_enable && cycles%19==0),.audio_write(1'b1),.audio_address(29'h600008),.audio_data(256'h1234),
            .audio_ready(audio_ready),.audio_response(),
            .music_valid(traffic_enable && cycles%41==0),.music_write(cycles%82==0),.music_address(29'h08000008),
            .music_data(256'hdeadbeef),.music_mask(32'h55aa00ff),.music_ready(),.music_response(),
            .recording_valid(record_slot_valid),.recording_write(write_request),.recording_address(address),
            .recording_data(write_data),.recording_mask(mask),.recording_ready(local_ready),.recording_response(record_response),
            .delay_valid(traffic_enable && cycles%29==0),.delay_write(1'b1),.delay_address(29'hc000008),.delay_data(256'h5678),
            .delay_ready(delay_ready),.delay_response(),
            .writer_valid(traffic_enable && cycles%23==0),.writer_address(29'h20),.writer_data(256'habcd),.writer_ready(writer_ready),
            .cpu_valid(test_cpu_blocker || (traffic_enable && cycles%31==0)),.cpu_write(1'b0),.cpu_address(29'h400008),.cpu_data(256'd0),.cpu_mask(32'd0),
            .cpu_ready(cpu_ready),.cpu_response(),.app_cmd(app_cmd),.app_en(app_en),.app_wren(app_wren),.app_wend(app_wend),
            .app_address(native_address),.app_data(native_data),.app_mask(native_mask),
            .app_ready(native_ready),.app_write_ready(native_ready),.app_response(memory_response || inject_bus_response),
            .app_response_data(memory_response_data),.response_data(returned),.response_fault(fault),
            .slot_accept_o(slot_accept),.core_accept_o(core_accept),.native_accept_o(native_accept),.transport_fault_o(bus_transport_fault));
        always @(posedge clk)if(rstn)begin
            if(slot_accept[8])record_slot_count=record_slot_count+1;
            if(core_accept[8])record_core_count=record_core_count+1;
            if(native_accept[8])record_native_count=record_native_count+1;
            if(fault && CASE!=7)$fatal(1,"actual arbiter response fault");
            if(native_en)case(native_address)
                29'h10:scan_ops=scan_ops+1;
                29'h600008:audio_ops=audio_ops+1;
                29'h200008:display_ops=display_ops+1;
                29'hc000008:delay_ops=delay_ops+1;
                29'h400008:cpu_ops=cpu_ops+1;
                29'h20:writer_ops=writer_ops+1;
                29'h08000008:music_ops=music_ops+1;
                default:begin end
            endcase
        end
    end else begin:g_direct
        assign transport_fault=force_transport_fault;
        assign request_ready=request && native_ready;
        assign native_en=request && request_ready;
        assign native_write=write_request;
        assign native_address=address;
        assign native_data=write_data;
        assign native_mask=mask;
        assign response=memory_response || inject_response;
        assign response_data=memory_response_data;
    end endgenerate
    reg [7:0] memory[0:65567];
    reg [255:0] pending_data[0:127];
    integer pending_due[0:127];
    integer qin=0,qout=0,writes=0,reads=0,record_writes=0,record_reads=0,byte_base;
    reg [255:0] read_word;
    always @(posedge clk)begin
        memory_response<=0;
        if(!rstn)begin qin=0;qout=0;end
        else begin
            if(!hold_response && qin!=qout && pending_due[qout%128]<=cycles)begin
                memory_response<=1;memory_response_data<=pending_data[qout%128];qout=qout+1;
            end
            if(native_en)begin
                if(native_address[2:0]!=0)$fatal(1,"unaligned native BL8");
                if(native_write)begin
                    writes=writes+1;
                    if(native_record)begin
                        record_writes=record_writes+1;
                        byte_base=(native_address-29'h0c140000)*4;
                        for(integer b=0;b<32;b=b+1)if(!native_mask[b]) memory[byte_base+b]=native_data[b*8+:8];
                    end
                end else begin
                    reads=reads+1;read_word={8{32'hcafe1234}};
                    if(native_record)begin
                        record_reads=record_reads+1;
                        byte_base=(native_address-29'h0c140000)*4;
                        for(integer b=0;b<32;b=b+1)read_word[b*8+:8]=memory[byte_base+b];
                    end
                    if(qin-qout>=128)$fatal(1,"memory response fixture overflow");
                    pending_data[qin%128]=read_word;pending_due[qin%128]=cycles+9;qin=qin+1;
                end
            end
        end
    end
    function automatic [31:0] pattern(input integer frame_index,input integer seed);
        reg [15:0] left_value,right_value;
        begin left_value=16'(frame_index*73+seed+16'h1234);right_value=16'(frame_index*109^seed^16'had98);
            pattern={right_value,left_value};end
    endfunction
    function automatic [7:0] expected_byte(input integer absolute_offset,input integer seed);
        reg [31:0] pair_value;
        begin pair_value=pattern(absolute_offset/4,seed);expected_byte=pair_value>>(8*(absolute_offset%4));end
    endfunction
    integer active_seed=0,active_epoch=0,active_rate=0,checked_bytes=0,objects_checked=0,failures_checked=0,aborts_checked=0;
    integer priority_checked=0,reads_before_collision=0,collision_deadline=0;
    reg held_command=0;
    reg [317:0] held_payload;
    reg held_download=0;
    reg [262:0] held_download_payload;
    always @(posedge clk)begin
        if(rstn && held_command && (!request || {write_request,address,write_data,mask}!==held_payload[317:0]))
            $fatal(1,"published native command changed/withdrawn before acceptance");
        held_command=rstn && request && !request_ready;
        held_payload={write_request,address,write_data,mask};
        if(rstn && held_download && state==3 && !cancel && !soft_reset && !ref_release &&
           (!download_valid || {download_last,download_bytes,download_data}!==held_download_payload))
            $fatal(1,"download prefetch changed under consumer backpressure");
        held_download=rstn && download_valid && !download_ready;
        held_download_payload={download_last,download_bytes,download_data};
        if(rstn && stored_id!=0 && state!=0 &&
           (stored_id!==64'(active_seed) || stored_epoch!==32'(active_epoch) || stored_rate!==1'(active_rate)))
            $fatal(1,"owner descriptor mutated");
    end
    task automatic wait_cycles(input integer count);repeat(count)@(negedge clk);endtask
    task automatic hard_reset;
        begin
            @(negedge clk);rstn=0;create=0;pcm_valid=0;seal=0;cancel=0;soft_reset=0;clear=0;
            ref_acquire=0;ref_release=0;download=0;download_ready=0;force_stall=0;hold_response=0;inject_response=0;
            force_transport_fault=0;inject_bus_response=0;inject_bridge_completion=0;traffic_enable=1;test_cpu_blocker=0;
            source_ready=1;source_error=0;
            wait_cycles(5);rstn=1;wait_cycles(3);
            if(state!=0 || stored_id!=0 || request || download_valid)$fatal(1,"hard reset ownership");
        end
    endtask
    task automatic new_object(input integer seed,input integer frame_limit);
        begin
            #1; // allow admission to settle after a same-edge clear deassertion
            if(!create_ready)$fatal(1,"object reuse before clear/drain");
            for(integer b=0;b<65568;b=b+1)memory[b]=8'ha5;
            active_seed=seed;active_epoch=seed+100;active_rate=RATE_44K1;
            object_id=64'(seed);epoch=32'(active_epoch);rate=1'(active_rate);first_sequence=32'hfffffff0;
            limit=32'(frame_limit);pcm_rate=rate;pcm_epoch=epoch;
            @(negedge clk);create=1;@(negedge clk);create=0;
            object_id=64'hfeed;epoch=32'hbad;rate=~rate;
        end
    endtask
    task automatic frame(input integer number,input integer spacing);
        begin
            wait_cycles(spacing-1);pcm=pattern(number,active_seed);sequence_number=32'hfffffff0+32'(number);pcm_valid=1;
            @(negedge clk);pcm_valid=0;
        end
    endtask
    task automatic wait_state(input integer value);
        integer until_cycle;
        begin until_cycle=cycles+12000;
            while(state!=value && cycles<until_cycle)@(negedge clk);
            if(state!=value)$fatal(1,"state deadline got=%0d expected=%0d failure=%0d",state,value,failure);
        end
    endtask
    task automatic seal_and_check(input integer expected_frames,input integer stall_tail);
        begin
            if(stall_tail)force_stall=1;
            @(negedge clk);seal=1;pcm_valid=1;pcm=pattern(expected_frames,active_seed);
            sequence_number=32'hfffffff0+32'(expected_frames);
            @(negedge clk);seal=0;pcm_valid=0;
            if(stall_tail)begin wait_cycles(12);
                if(state!=2 || committed>=expected_frames)$fatal(1,"seal published before real final write acceptance");
                force_stall=0;
            end
            wait_state(3);
            if(frames!=expected_frames || committed!=expected_frames || !quiet)$fatal(1,"sealed prefix differs");
            for(integer b=0;b<expected_frames*4;b=b+1)
                if(memory[b]!==expected_byte(b,active_seed))$fatal(1,"DDR PCM mismatch byte=%0d",b);
            for(integer b=expected_frames*4;b<((expected_frames*4+31)/32)*32;b=b+1)
                if(memory[b]!==8'ha5)$fatal(1,"tail mask overwrote byte=%0d",b);
            objects_checked=objects_checked+1;
        end
    endtask
    task automatic acquire;
        begin
            if(!ref_ready)$fatal(1,"reference unavailable");
            ref_id=64'(active_seed);ref_acquire=1;@(negedge clk);ref_acquire=0;
            if(!ref_held || !ref_granted)$fatal(1,"reference not granted");
        end
    endtask
    task automatic begin_download(input integer start_byte,input integer byte_count);
        begin
            if(!download_req_ready)$fatal(1,"download admission unavailable");
            offset=32'(start_byte);length=32'(byte_count);download=1;
            @(negedge clk);download=0;
        end
    endtask
    task automatic check_download(input integer start_byte,input integer byte_count);
        integer consumed,until_cycle;
        begin
            consumed=0;until_cycle=cycles+150000;download_ready=0;
            begin_download(start_byte,byte_count);
            while(consumed<byte_count && cycles<until_cycle)begin
                @(negedge clk);download_ready=(cycles%7<4);
                #1;
                if(download_valid && download_ready)begin
                    if(download_bytes<1 || download_bytes>32 || consumed+download_bytes>byte_count)
                        $fatal(1,"download length/range");
                    for(integer b=0;b<download_bytes;b=b+1)
                        if(download_data[b*8+:8]!==expected_byte(start_byte+consumed+b,active_seed))
                            $fatal(1,"download PCM mismatch byte=%0d",start_byte+consumed+b);
                    consumed=consumed+download_bytes;checked_bytes=checked_bytes+download_bytes;
                    if(download_last!==(consumed==byte_count))$fatal(1,"download last marker");
                end
            end
            @(negedge clk);download_ready=0;
            if(consumed!=byte_count || !download_done)$fatal(1,"download completion deadline bytes=%0d",consumed);
        end
    endtask
    task automatic release_reference;
        integer until_cycle;
        begin
            ref_release=1;@(negedge clk);ref_release=0;
            until_cycle=cycles+1000;
            while(ref_held && cycles<until_cycle)@(negedge clk);
            if(ref_held)$fatal(1,"reference drain/release deadline");
            wait_cycles(2);
        end
    endtask
    task automatic clear_object;
        begin
            #1; // cancellation/reset may have just deasserted at this negedge
            if(!clear_ready)$fatal(1,"clear rejected after quiescence");
            clear=1;@(negedge clk);clear=0;
            if(state!=0 || stored_id!=0 || download_valid)$fatal(1,"clear identity/data fencing");
        end
    endtask
    task automatic expect_error(input integer code);
        begin wait_state(4);
            if(failure!=code || download_valid || captured)$fatal(1,"wrong failure code=%0d expected=%0d",failure,code);
            failures_checked=failures_checked+1;
        end
    endtask
    task automatic wait_quiet;
        integer until_cycle;
        begin until_cycle=cycles+1000;while(!quiet && cycles<until_cycle)@(negedge clk);
            if(!quiet)$fatal(1,"native drain deadline");wait_cycles(3);end
    endtask
    initial begin
        hard_reset();
        if(CASE==0)begin
            new_object(17,16384);
            // Real source cadence at both declared sample rates; carry the
            // fractional period rather than relabelling an accelerated source.
            for(integer n=0;n<519;n=n+1) frame(n,
                (RATE_44K1 ? ((n+1)*1000000/441-n*1000000/441) : ((n+1)*100000/48-n*100000/48)));
            seal_and_check(519,1);
            pcm_valid=1;source_error=1;wait_cycles(8);pcm_valid=0;source_error=0;
            if(state!=3 || frames!=519 || committed!=519 || captured)$fatal(1,"READY changed by live PCM");
            ref_id=64'hbad;ref_acquire=1;@(negedge clk);ref_acquire=0;
            if(!ref_error || ref_held)$fatal(1,"wrong object reference accepted");
            acquire();clear=1;wait_cycles(2);clear=0;
            if(clear_ready || state!=3)$fatal(1,"clear bypassed download reference");
            begin_download(2075,3);
            if(!download_error)$fatal(1,"out-of-range download accepted");
            check_download(3,2071);release_reference();clear_object();
            for(integer tail=1;tail<8;tail=tail+1)begin
                new_object(30+tail,16384);
                for(integer n=0;n<8+tail;n=n+1)frame(n,4);
                seal_and_check(8+tail,1);acquire();check_download(0,(8+tail)*4);release_reference();clear_object();
            end
        end else if(CASE==1)begin
            new_object(91,16384);
            for(integer n=0;n<16384;n=n+1)frame(n,4);
            wait_state(3);seal_and_check(16384,0);
            acquire();check_download(0,65536);release_reference();clear_object();
        end else if(CASE==2)begin
            new_object(101,16384);force_stall=1;
            for(integer n=0;n<(1<<FIFO_BITS)+32 && state==1;n=n+1)frame(n,2);
            expect_error(1);if(clear_ready || !request)$fatal(1,"overflow lost pending write");
            force_stall=0;wait_quiet();clear_object();
            new_object(102,16384);frame(0,4);frame(1,4);sequence_number=0;pcm_valid=1;wait_cycles(1);pcm_valid=0;
            expect_error(2);clear_object();
            for(integer context_case=0;context_case<2;context_case=context_case+1)begin
                new_object(103+context_case,16384);
                if(context_case)pcm_rate=~pcm_rate;else pcm_epoch=pcm_epoch+1;
                frame(0,4);expect_error(3);clear_object();
            end
            new_object(105,16384);source_error=1;wait_cycles(1);source_error=0;expect_error(4);clear_object();
            new_object(106,16384);source_ready=0;wait_cycles(1);source_ready=1;expect_error(4);clear_object();
            new_object(107,16384);wait_cycles(4098);expect_error(4);clear_object();
            new_object(108,16384);force_stall=1;
            for(integer n=0;n<8;n=n+1)frame(n,4);
            expect_error(5);if(clear_ready || !request)$fatal(1,"timeout released published write");
            force_stall=0;wait_quiet();clear_object();
            new_object(109,16384);for(integer n=0;n<17;n=n+1)frame(n,4);
            seal_and_check(17,0);acquire();hold_response=1;begin_download(0,68);
            expect_error(6);if(clear_ready || !ref_held || quiet)$fatal(1,"read timeout forgot outstanding/reference");
            hold_response=0;wait_quiet();wait_cycles(5);
            if(ref_held || discarded!=1)$fatal(1,"late timed-out read not discarded/drained");
            clear_object();
            new_object(110,0);expect_error(8);clear_object();
        end else if(CASE==3)begin
            for(integer reset_case=0;reset_case<2;reset_case=reset_case+1)begin
                new_object(121+reset_case,16384);force_stall=1;
                for(integer n=0;n<9;n=n+1)frame(n,4);
                if(reset_case)soft_reset=1;else cancel=1;
                wait_cycles(1);soft_reset=0;cancel=0;
                if(state!=(reset_case ? 6 : 5) || clear_ready || !request)$fatal(1,"cancel/reset write fence");
                force_stall=0;wait_quiet();clear_object();aborts_checked=aborts_checked+1;
            end
            for(integer reset_case=0;reset_case<2;reset_case=reset_case+1)begin
                new_object(123+reset_case,16384);for(integer n=0;n<17;n=n+1)frame(n,4);
                seal_and_check(17,0);acquire();hold_response=1;begin_download(0,68);
                wait_cycles(8);
                if(reset_case)soft_reset=1;else cancel=1;
                wait_cycles(1);soft_reset=0;cancel=0;
                if(clear_ready || !ref_held || state!=(reset_case ? 6 : 5))$fatal(1,"cancel/reset read fence");
                hold_response=0;wait_quiet();wait_cycles(5);
                if(ref_held || discarded!=reset_case+1 || download_valid)$fatal(1,"old read escaped generation fence");
                clear_object();aborts_checked=aborts_checked+1;
            end
            new_object(125,16384);for(integer n=0;n<17;n=n+1)frame(n,4);
            seal_and_check(17,0);acquire();hold_response=1;begin_download(0,68);wait_cycles(8);
            ref_release=1;wait_cycles(1);ref_release=0;wait_cycles(3);
            if(clear_ready || !ref_held || state!=3)$fatal(1,"release forgot accepted read");
            hold_response=0;wait_quiet();wait_cycles(5);
            if(ref_held || discarded!=3 || state!=3)$fatal(1,"release corrupted immutable object");
            acquire();check_download(1,66);release_reference();clear_object();
            new_object(126,16384);for(integer n=0;n<17;n=n+1)frame(n,4);
            seal_and_check(17,0);acquire();hold_response=1;begin_download(0,68);wait_cycles(8);
            hard_reset(); // paired DDR/tag reset, never a source-only reset
            inject_response=1;wait_cycles(1);inject_response=0;expect_error(7);clear_object();
            new_object(127,16384);for(integer n=0;n<19;n=n+1)frame(n,4);
            seal_and_check(19,0);acquire();check_download(0,76);release_reference();clear_object();
        end else if(CASE==4)begin
            // Inspect valid&&ready BEFORE each active edge, then verify the
            // resulting object/reference and actual native traffic afterwards.
            active_seed=141;active_epoch=241;active_rate=RATE_44K1;
            object_id=141;epoch=241;rate=RATE_44K1;limit=16384;
            pcm_rate=rate;pcm_epoch=epoch;first_sequence=32'hfffffff0;
            for(integer b=0;b<65568;b=b+1)memory[b]=8'ha5;
            create=1;clear=1;
            #1;
            if(create_ready || !clear_ready)$fatal(1,"clear admitted simultaneous create");
            @(negedge clk);
            if(state!=0 || stored_id!=0)$fatal(1,"clear/create priority changed empty object");
            priority_checked=priority_checked+1;
            // A held create is admitted only on a later edge after clear ends.
            clear=0;#1;
            if(!create_ready)$fatal(1,"held create did not reopen after clear");
            @(negedge clk);create=0;
            if(state!=1 || stored_id!=141 || frames!=0)$fatal(1,"accepted held create was lost");
            object_id=64'hfeed;epoch=32'hbad;rate=~rate;
            priority_checked=priority_checked+1;
            for(integer n=0;n<9;n=n+1)frame(n,4);
            seal_and_check(9,0);

            // A release without an old reference must block valid and invalid
            // acquisitions alike; neither grant/error nor a new hold is legal.
            reads_before_collision=record_reads;
            for(integer wrong_id=0;wrong_id<2;wrong_id=wrong_id+1)begin
                ref_id=wrong_id ? 64'hbad : 64'(active_seed);
                ref_acquire=1;ref_release=1;download=1;offset=0;length=36;
                #1;
                if(ref_ready)$fatal(1,"release admitted new reference");
                if(download_req_ready)$fatal(1,"release admitted new download");
                @(negedge clk);ref_acquire=0;ref_release=0;download=0;
                if(ref_held || ref_granted || ref_error || ref_released)
                    $fatal(1,"release/acquire collision created reference outcome");
                wait_cycles(3);
                if(!clear_ready || state!=3 || record_reads!=reads_before_collision)
                    $fatal(1,"release/acquire collision wedged immutable object");
                priority_checked=priority_checked+1;
            end
            // Acquire does not retroactively make a same-edge download ready.
            ref_id=64'(active_seed);ref_acquire=1;download=1;offset=0;length=36;
            #1;
            if(!ref_ready || download_req_ready)$fatal(1,"acquire/download admission boundary");
            @(negedge clk);ref_acquire=0;download=0;
            if(!ref_granted || !ref_held || record_reads!=reads_before_collision)
                $fatal(1,"acquire/download same edge created native read");
            priority_checked=priority_checked+1;
            check_download(0,36);

            // Release wins exactly when the last prefetched output would be
            // accepted; it also blocks a new download/acquire and an early clear.
            begin_download(1,3);collision_deadline=cycles+1000;
            while(!download_valid && cycles<collision_deadline)@(negedge clk);
            if(!download_valid || !download_last)$fatal(1,"collision output precondition");
            ref_release=1;ref_acquire=1;clear=1;download=1;download_ready=1;
            #1;
            if(ref_ready || clear_ready || download_req_ready || download_valid)
                $fatal(1,"release failed to close same-edge admission/output");
            @(negedge clk);ref_release=0;ref_acquire=0;clear=0;download=0;download_ready=0;
            if(download_done || ref_granted || state!=3)$fatal(1,"release delivered cancelled final fragment");
            wait_quiet();wait_cycles(5);
            if(ref_held || !clear_ready || state!=3 || stored_id!=64'(active_seed))
                $fatal(1,"release/clear lost object or held reference");
            priority_checked=priority_checked+1;

            // With no reference, clear must also inhibit acquire while create
            // cannot reuse the region until a later EMPTY edge.
            clear=1;ref_acquire=1;create=1;#1;
            if(!clear_ready || ref_ready || create_ready)$fatal(1,"clear/acquire admission boundary");
            @(negedge clk);clear=0;ref_acquire=0;create=0;
            if(state!=0 || stored_id!=0 || ref_held || ref_granted || ref_error)
                $fatal(1,"clear/acquire silently retained new ownership");
            priority_checked=priority_checked+1;

            // seal only applies to a pre-existing CAPTURE state. Creation and
            // PCM are not retroactively included on its admission edge.
            seal=1;pcm_valid=1;new_object(142,16384);seal=0;pcm_valid=0;
            if(state!=1 || frames!=0)$fatal(1,"create/seal/PCM boundary");
            frame(0,4);seal=1;cancel=1;clear=1;pcm_valid=1;
            #1;
            if(clear_ready || create_ready || captured)$fatal(1,"cancel admitted capture/clear");
            @(negedge clk);seal=0;cancel=0;clear=0;pcm_valid=0;
            if(state!=5 || frames!=1)$fatal(1,"cancel lost priority over seal/PCM");
            wait_quiet();clear_object();aborts_checked=aborts_checked+1;
            priority_checked=priority_checked+2;

            // EMPTY cancellation/reset cannot accept and then erase create;
            // simultaneous soft_reset takes the documented terminal priority.
            create=1;clear=1;cancel=1;soft_reset=1;#1;
            if(create_ready || clear_ready || ref_ready || download_req_ready)
                $fatal(1,"reset admitted new owner command");
            @(negedge clk);create=0;clear=0;cancel=0;soft_reset=0;
            if(state!=6 || stored_id!=0)$fatal(1,"soft reset priority over cancel/create");
            clear_object();aborts_checked=aborts_checked+1;priority_checked=priority_checked+1;

            // An unexpected response is a fault even in otherwise quiescent
            // READY. No download may be admitted on that same active edge.
            new_object(143,16384);for(integer n=0;n<9;n=n+1)frame(n,4);
            seal_and_check(9,0);acquire();reads_before_collision=record_reads;
            inject_response=1;download=1;offset=0;length=36;clear=1;ref_acquire=1;
            #1;
            if(download_req_ready)$fatal(1,"fault admitted simultaneous download");
            if(create_ready || clear_ready || ref_ready || download_valid)
                $fatal(1,"fault admitted other owner command/output");
            @(negedge clk);inject_response=0;download=0;clear=0;ref_acquire=0;
            expect_error(7);wait_quiet();wait_cycles(5);
            if(record_reads!=reads_before_collision || ref_held || ref_granted || download_done)
                $fatal(1,"fault/download created native read or held reference");
            clear_object();priority_checked=priority_checked+1;

            // Cancellation/reset from READY closes every command admission
            // with a held reference, then frees it only through normal drain.
            for(integer abort_kind=0;abort_kind<3;abort_kind=abort_kind+1)begin
                new_object(144+abort_kind,16384);for(integer n=0;n<3;n=n+1)frame(n,4);
                seal_and_check(3,0);acquire();reads_before_collision=record_reads;
                download=1;offset=0;length=12;create=1;clear=1;ref_acquire=1;
                cancel=abort_kind!=1;soft_reset=abort_kind!=0;#1;
                if(create_ready || clear_ready || ref_ready || download_req_ready || download_valid)
                    $fatal(1,"cancel/reset admitted same-edge command");
                @(negedge clk);download=0;create=0;clear=0;ref_acquire=0;cancel=0;soft_reset=0;
                if(state!=(abort_kind==0 ? 5 : 6))$fatal(1,"cancel/reset terminal priority");
                wait_quiet();wait_cycles(5);
                if(record_reads!=reads_before_collision || ref_held || ref_granted || download_done)
                    $fatal(1,"cancel/reset download escaped invalidation");
                clear_object();aborts_checked=aborts_checked+1;priority_checked=priority_checked+1;
            end
        end else if(CASE==5)begin
            if(!FAULT_ENABLE)$fatal(1,"transport fault fixture requires opt-in");
            for(integer phase=FAULT_START_PHASE;phase<4;phase=phase+1)begin
                new_object(160+phase,16384);
                if(phase==0)force_stall=1;
                for(integer n=0;n<(phase==0 ? 9 : 17);n=n+1)frame(n,4);
                if(phase!=0)seal_and_check(17,0);
                if(phase>=2)begin
                    acquire();
                    if(phase==2)begin
                        hold_response=1;reads_before_collision=record_reads;
                        begin_download(0,68);collision_deadline=cycles+1000;
                        while(record_reads==reads_before_collision && cycles<collision_deadline)@(negedge clk);
                        if(record_reads==reads_before_collision || quiet)$fatal(1,"transport accepted-read precondition");
                    end else begin
                        begin_download(1,3);collision_deadline=cycles+1000;
                        while(!download_valid && cycles<collision_deadline)@(negedge clk);
                        if(!download_valid || !download_last)$fatal(1,"transport final-output precondition");
                    end
                end
                force_transport_fault=1;create=1;clear=1;ref_acquire=1;download=1;download_ready=1;#1;
                if(create_ready || clear_ready || ref_ready || download_req_ready || download_valid || captured)
                    $fatal(1,"transport fault left admission/output open");
                @(negedge clk);create=0;clear=0;ref_acquire=0;download=0;download_ready=0;
                expect_error(9);
                if(download_done || clear_ready)$fatal(1,"transport fault falsely completed/rearmed");
                if(phase==0 && !request)$fatal(1,"transport fault withdrew published write");
                if(phase==2 && (!ref_held || quiet))$fatal(1,"transport fault forgot accepted read");
                force_stall=0;hold_response=0;wait_quiet();wait_cycles(5);
                clear=1;soft_reset=1;wait_cycles(2);clear=0;soft_reset=0;#1;
                if(state!=4 || failure!=9 || create_ready || clear_ready || ref_held || download_valid)
                    $fatal(1,"soft reset/clear recovered sticky transport fault");
                hard_reset(); // paired controller, tag ledger, bridge and backend reset
                if(!create_ready)$fatal(1,"common reset did not recover transport channel");
            end
        end else if(CASE==6)begin
            if(FAULT_ENABLE)$fatal(1,"legacy transport fixture requires default disabled");
            force_transport_fault=1;new_object(171,16384);
            for(integer n=0;n<17;n=n+1)frame(n,4);
            seal_and_check(17,0);acquire();check_download(0,68);release_reference();clear_object();
        end else if(CASE==7)begin
            if(!COMPETITION || !FAULT_ENABLE)$fatal(1,"actual native fault fixture configuration");
            new_object(176,16384);for(integer n=0;n<17;n=n+1)frame(n,4);
            seal_and_check(17,0);acquire();traffic_enable=0;wait_cycles(100);
            if(qin!=qout || memory_response || native_en)$fatal(1,"actual native fault drain precondition");
            inject_bus_response=1;download=1;offset=0;length=68;clear=1;#1;
            if(!transport_fault)$fatal(1,"actual empty-ledger fault missing before edge");
            if(download_req_ready || download_valid || clear_ready)$fatal(1,"actual bus fault admitted download");
            @(negedge clk);inject_bus_response=0;download=0;clear=0;expect_error(9);wait_quiet();wait_cycles(5);
            soft_reset=1;clear=1;wait_cycles(2);soft_reset=0;clear=0;#1;
            if(!transport_fault || clear_ready || create_ready || state!=4 || failure!=9)
                $fatal(1,"actual bus sticky fault recovered without paired reset");
            hard_reset();if(!create_ready || transport_fault)$fatal(1,"actual native common reset recovery");
        end else if(CASE==8)begin
            if(!COMPETITION)$fatal(1,"stage-cancel fixture requires actual owner8 queues");
            for(integer phase=0;phase<4;phase=phase+1)begin
                new_object(180+phase,16384);traffic_enable=0;wait_cycles(100);
                if(phase>=2)begin
                    for(integer n=0;n<17;n=n+1)frame(n,4);
                    seal_and_check(17,0);acquire();hold_response=1;
                end
                force_stall=1;
                if(phase%2==0)begin
                    test_cpu_blocker=1;wait_cycles(8);test_cpu_blocker=0;
                end
                slot_before=record_slot_count;core_before=record_core_count;native_before=record_native_count;
                discard_before=discarded;
                if(phase<2)begin for(integer n=0;n<9;n=n+1)frame(n,4);end
                else begin_download(0,68);
                collision_deadline=cycles+1000;
                if(phase%2==0)begin
                    while(record_slot_count==slot_before && cycles<collision_deadline)@(negedge clk);
                    if(record_slot_count!=slot_before+1 || record_core_count!=core_before || record_native_count!=native_before)
                        $fatal(1,"cancel local-slot stage not established");
                end else begin
                    while(record_core_count==core_before && cycles<collision_deadline)@(negedge clk);
                    if(record_slot_count!=slot_before+1 || record_core_count!=core_before+1 || record_native_count!=native_before)
                        $fatal(1,"cancel core-buffer stage not established");
                end
                if(!request || request_ready)$fatal(1,"early ACK retired command before cancel");
                cancel=1;@(negedge clk);cancel=0;
                if(state!=5 || !request || clear_ready)$fatal(1,"cancel withdrew queued/core published command");
                force_stall=0;collision_deadline=cycles+1000;
                while(record_native_count==native_before && cycles<collision_deadline)@(negedge clk);
                if(record_native_count!=native_before+1)$fatal(1,"cancel native command lost/duplicated");
                if(phase>=2)begin
                    if(quiet || !ref_held || clear_ready)$fatal(1,"cancel forgot read accepted after cancellation");
                    hold_response=0;
                end
                wait_quiet();wait_cycles(64);
                if(record_slot_count!=slot_before+1 || record_core_count!=core_before+1 || record_native_count!=native_before+1)
                    $fatal(1,"cancel stage replayed published command");
                if(phase>=2 && (discarded!=discard_before+1 || ref_held))$fatal(1,"cancel post-native read not drained/discarded");
                clear_object();aborts_checked=aborts_checked+1;
            end
        end else if(CASE==9)begin
            if(!COMPETITION || !FAULT_ENABLE)$fatal(1,"bridge fault integration fixture configuration");
            for(integer phase=0;phase<3;phase=phase+1)begin
                new_object(190+phase,16384);for(integer n=0;n<17;n=n+1)frame(n,4);
                seal_and_check(17,0);traffic_enable=0;wait_cycles(100);
                if(phase!=0)acquire();
                if(phase==2)begin
                    begin_download(1,3);collision_deadline=cycles+1000;
                    while(!download_valid && cycles<collision_deadline)@(negedge clk);
                    if(!download_valid || !download_last)$fatal(1,"bridge fault final-output precondition");
                end
                inject_bridge_completion=1;ref_id=64'(active_seed);ref_acquire=1;
                download=1;offset=0;length=68;download_ready=1;clear=1;#1;
                if(!transport_fault || ref_ready || download_req_ready || download_valid || clear_ready)
                    $fatal(1,"bridge protocol fault admitted same-edge owner request/output");
                @(negedge clk);inject_bridge_completion=0;ref_acquire=0;download=0;download_ready=0;clear=0;
                expect_error(9);wait_quiet();wait_cycles(5);
                if(ref_granted || ref_held || download_done || clear_ready || !transport_fault)
                    $fatal(1,"bridge fault failed sticky fencing/drain");
                hard_reset();if(!create_ready || transport_fault)$fatal(1,"bridge fault paired reset recovery");
            end
        end
        if(COMPETITION && CASE!=8 && (scan_ops==0 || audio_ops==0 || display_ops==0 || delay_ops==0 || cpu_ops==0 || writer_ops==0 || music_ops==0))
            $fatal(1,"competition did not exercise every existing port");
        $display("PASS workstation_pcm_ddr_backend: case=%0d rate=%0d competition=%0d objects=%0d failures=%0d aborts=%0d priorities=%0d bytes=%0d writes=%0d reads=%0d command_wait=%0d read_wait=%0d cycles=%0d scan=%0d audio=%0d display=%0d delay=%0d cpu=%0d writer=%0d music=%0d slots=%0d cores=%0d natives=%0d",
            CASE,RATE_44K1?44100:48000,COMPETITION,objects_checked,failures_checked,aborts_checked,priority_checked,
            checked_bytes,record_writes,record_reads,max_cmd_wait,max_read_wait,cycles,scan_ops,audio_ops,display_ops,delay_ops,cpu_ops,writer_ops,music_ops,
            record_slot_count,record_core_count,record_native_count);
        $finish;
    end
    initial begin #1000000000;$fatal(1,"backend fixture global timeout");end
endmodule
`default_nettype wire
