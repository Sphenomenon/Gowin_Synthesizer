`timescale 1ns/1ps
// Real BLE owner + real async store/native bridge. The DDR model separates
// slot submission, native acceptance and read return; RAM mode is the wire oracle.
module tb_workstation_ble_raw_ddr;
    parameter integer MEM_HALF=7;
    localparam integer BUDGET=50000;
    localparam [28:0] BASE=29'h0040000;
    localparam [63:0] BOOT=64'h1234567811223344;
    reg clk=0,memory_clk=0,memory_run=1,resetn=0,enable=1,connected=1;
    always #10 clk=~clk;
    always #(MEM_HALF)if(memory_run)memory_clk=~memory_clk;else memory_clk=0;
    reg source_ready=1,source_fault=0,pcm_valid=0,command_start=0,command_replay=0,consume=0;
    reg seal_hold=0,seal_request=0;
    reg [31:0] pcm_pair=0,request_id=1,replay_id=0;
    reg [7:0] opcode=0;
    reg [15:0] payload_length=0;
    reg [127:0] payload=0;
    reg [6:0] command_addr=0;
    reg [12:0] transfer_addr=0;
    wire command_done,reference_done,transfer_valid,reference_valid,seal_ready,seal_pending,seal_done,seal_failed;
    wire [7:0] status,reference_status,command_data,reference_data,record_state,reference_state,transfer_data,reference_transfer;
    wire [31:0] recording_id,recorded_frames,reference_id,reference_frames;
    wire [12:0] transfer_length,reference_length;
    wire start,start_ready,start_done,clear,clear_ready,clear_done,capture,capture_ready,close_req,close_ready,drained,fault,object_fault,channel_fault;
    wire [3:0] failure;
    wire [31:0] capture_index,capture_pcm,accepted,committed,sample_address,sample_word,fetch_offset;
    wire [13:0] fetch_length;
    wire fetch,fetch_ready,fetch_done,fetch_fault,cache_valid;
    wire slot_valid,slot_ready,native_accept,ddr_write,native_fault;
    wire [28:0] address;
    wire [255:0] write_data;
    wire [31:0] mask;
    reg read_response=0;reg [255:0] read_data=0;
    ble_recording #(.EXTERNAL_PCM(1),.EXTERNAL_SEAL_PROTOCOL(1),.CAPACITY_FRAMES(2048),
        .EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(BUDGET)) dut(
        .clk(clk),.resetn(resetn),.enable(enable),.connected(connected),.transfer_subscribed(1'b1),
        .pcm_valid_i(pcm_valid),.pcm_pair_i(pcm_pair),.source_ready_i(source_ready),.source_fault_i(source_fault),
        .boot_id(BOOT),.att_value_limit(9'd247),.elapsed_ms(32'd100),
        .command_start(command_start),.command_replay(command_replay),.opcode(opcode),.request_id(request_id),
        .nonce(64'habcdef),.payload_length(payload_length),.payload(payload),.replay_recording_id(replay_id),
        .command_done(command_done),.command_status(status),.command_length(),.command_addr(command_addr),.command_data(command_data),
        .record_state(record_state),.recording_id(recording_id),.recorded_frames(recorded_frames),.capacity_frames(),
        .transfer_valid(transfer_valid),.transfer_compact(),.transfer_bulk(),.transfer_direct(),.transfer_length(transfer_length),
        .transfer_addr(transfer_addr),.transfer_data(transfer_data),.transfer_consume(consume),
        .seal_hold_i(seal_hold),.seal_request_i(seal_request),.seal_ready_o(seal_ready),.seal_pending_o(seal_pending),
        .seal_done_o(seal_done),.seal_failed_o(seal_failed),.seal_failure_code_o(),.seal_record_state_o(),
        .seal_recording_id_o(),.seal_frames_o(),.seal_crc_o(),
        .raw_start_valid_o(start),.raw_start_ready_i(start_ready),.raw_start_done_i(start_done),
        .raw_clear_valid_o(clear),.raw_clear_ready_i(clear_ready),.raw_clear_done_i(clear_done),
        .raw_capture_valid_o(capture),.raw_capture_index_o(capture_index),.raw_capture_pcm_o(capture_pcm),.raw_capture_ready_i(capture_ready),
        .raw_close_valid_o(close_req),.raw_close_ready_i(close_ready),.raw_drained_i(drained),.raw_fault_i(fault),
        .raw_object_fault_i(object_fault),.raw_channel_fault_i(channel_fault),.raw_failure_code_i(failure),
        .raw_accepted_frames_i(accepted),.raw_committed_frames_i(committed),
        .raw_fetch_valid_o(fetch),.raw_fetch_ready_i(fetch_ready),.raw_fetch_offset_o(fetch_offset),.raw_fetch_length_o(fetch_length),
        .raw_fetch_done_i(fetch_done),.raw_fetch_fault_i(fetch_fault),.raw_cache_valid_i(cache_valid),
        .raw_sample_addr_o(sample_address),.raw_sample_word_i(sample_word));
    ble_recording #(.EXTERNAL_PCM(1),.EXTERNAL_SEAL_PROTOCOL(1),.CAPACITY_FRAMES(2048)) reference(
        .clk(clk),.resetn(resetn),.enable(enable),.connected(connected),.transfer_subscribed(1'b1),
        .pcm_valid_i(pcm_valid),.pcm_pair_i(pcm_pair),.source_ready_i(source_ready),.source_fault_i(source_fault),
        .boot_id(BOOT),.att_value_limit(9'd247),.elapsed_ms(32'd100),
        .command_start(command_start),.command_replay(command_replay),.opcode(opcode),.request_id(request_id),
        .nonce(64'habcdef),.payload_length(payload_length),.payload(payload),.replay_recording_id(replay_id),
        .command_done(reference_done),.command_status(reference_status),.command_length(),.command_addr(command_addr),.command_data(reference_data),
        .record_state(reference_state),.recording_id(reference_id),.recorded_frames(reference_frames),.capacity_frames(),
        .transfer_valid(reference_valid),.transfer_compact(),.transfer_bulk(),.transfer_direct(),.transfer_length(reference_length),
        .transfer_addr(transfer_addr),.transfer_data(reference_transfer),.transfer_consume(consume),
        .seal_hold_i(seal_hold),.seal_request_i(seal_request),.seal_ready_o(),.seal_pending_o(),.seal_done_o(),.seal_failed_o(),
        .seal_failure_code_o(),.seal_record_state_o(),.seal_recording_id_o(),.seal_frames_o(),.seal_crc_o());
    workstation_ble_raw_ddr_store #(.BASE_APP(BASE),.CAPACITY_FRAMES(2048),.FIFO_ADDRESS_BITS(3)) store(
        .clk_i(clk),.memory_clk_i(memory_clk),.rst_ni(resetn),
        .start_valid_i(start),.start_ready_o(start_ready),.start_done_o(start_done),
        .clear_valid_i(clear),.clear_ready_o(clear_ready),.clear_done_o(clear_done),
        .capture_valid_i(capture),.capture_index_i(capture_index),.capture_pcm_i(capture_pcm),.capture_ready_o(capture_ready),
        .close_valid_i(close_req),.close_ready_o(close_ready),.drained_o(drained),.fault_o(fault),
        .object_fault_o(object_fault),.channel_fault_o(channel_fault),.failure_code_o(failure),
        .accepted_frames_o(accepted),.committed_frames_o(committed),
        .fetch_valid_i(fetch),.fetch_ready_o(fetch_ready),.fetch_offset_i(fetch_offset),.fetch_length_i(fetch_length),
        .fetch_done_o(fetch_done),.fetch_fault_o(fetch_fault),.cache_valid_o(cache_valid),.sample_addr_i(sample_address),.sample_word_o(sample_word),
        .slot_valid_o(slot_valid),.slot_ready_i(slot_ready),.native_accept_i(native_accept),.ddr_write_o(ddr_write),
        .ddr_address_o(address),.ddr_data_o(write_data),.ddr_mask_o(mask),.read_response_i(read_response),.read_data_i(read_data),
        .transport_fault_i(1'b0),.native_protocol_fault_o(native_fault));
    reg slot_enable=1,native_enable=1,response_enable=1,same_edge_response=0;
    reg model_slot=0,model_read=0,model_write=0;
    reg [28:0] model_address=0,model_read_address=0;
    reg [255:0] model_data=0;reg [31:0] model_mask=0;
    integer model_delay=0,read_delay=0;
    reg native_pulse=0;
    assign slot_ready=slot_enable && !model_slot && !model_read;
    assign native_accept=native_pulse;
    reg [255:0] memory[0:255];
    integer checks=0,cases=0,wire_bytes=0,writes=0,reads=0,fetches=0,clear_fires=0,seal_successes=0,seal_failures=0;
    integer b,n,k,guard,before_fetch,before_reads,before_seal,before_fail;
    reg [31:0] expected_crc,tid,block_crc,saved_id,saved_frames;
    reg reference_seen=0;reg [7:0] reference_result=0;
    reg [7:0] previous_state=0;
    task check(input bit condition,input [511:0] message);
        begin checks=checks+1;if(!condition)$fatal(1,"%0s t=%0t state=%0d raw=%0d c=%0d code=%0d",message,$time,record_state,accepted,committed,failure);end
    endtask
    function [31:0] pattern(input integer at);
        reg [15:0] left_sample;begin left_sample=16'h1234+at*13;pattern={~left_sample,left_sample};end
    endfunction
    function [31:0] crc_byte(input [31:0] previous,input [7:0] value);
        integer i;reg [31:0] c;begin c=previous^value;for(i=0;i<8;i=i+1)c=(c>>1)^(c[0]?32'hedb88320:0);crc_byte=c;end
    endfunction
    always @(negedge memory_clk)begin
        native_pulse=resetn && model_slot && model_delay==0 && native_enable;
        read_response=resetn && response_enable && ((model_read && read_delay==0) || (same_edge_response && native_pulse && !model_write));
        if(model_read)read_data=memory[(model_read_address-BASE)>>3];
        else if(same_edge_response && native_pulse && !model_write)read_data=memory[(model_address-BASE)>>3];
        else read_data=0;
    end
    always @(posedge memory_clk or negedge resetn)begin
        if(!resetn)begin model_slot<=0;model_read<=0;model_delay<=0;read_delay<=0;writes<=0;reads<=0;end
        else begin
            if(slot_valid && slot_ready)begin
                check(address>=BASE && address<BASE+2048 && address[2:0]==0,"native address range");
                model_slot<=1;model_address<=address;model_write<=ddr_write;model_data<=write_data;model_mask<=mask;model_delay<=2;
            end
            if(model_slot && !native_accept)begin
                check({ddr_write,address,write_data,mask}==={model_write,model_address,model_data,model_mask},"published fields held until true native accept");
                if(model_delay>0)model_delay<=model_delay-1;
            end
            if(native_pulse)begin
                model_slot<=0;
                if(model_write)begin
                    for(b=0;b<32;b=b+1)if(!model_mask[b])memory[(model_address-BASE)>>3][b*8+:8]<=model_data[b*8+:8];
                    writes<=writes+1;
                end else begin model_read<=1;model_read_address<=model_address;read_delay<=3;reads<=reads+1;end
            end
            if(model_read && read_delay>0)read_delay<=read_delay-1;
            if(read_response)model_read<=0;
        end
    end
    always @(posedge clk)if(resetn)begin
        if(reference_done)begin reference_seen=1;reference_result=reference_status;end
        if(fetch && fetch_ready)fetches=fetches+1;
        if(clear && clear_ready)clear_fires=clear_fires+1;
        if(seal_done)seal_successes=seal_successes+1;
        if(seal_failed)seal_failures=seal_failures+1;
        check(!(record_state==4 && previous_state!=4 && (!drained || accepted!=recorded_frames || committed!=recorded_frames || fault)),"READY requires actual native drain and exact prefix");
        check(!(dut.raw_cache_owned && (!cache_valid || fault)),"endpoint cache ownership requires valid store cache");
        previous_state=record_state;
    end
    task reset_all;
        begin
            @(negedge clk);resetn=0;enable=1;connected=1;source_ready=1;source_fault=0;pcm_valid=0;command_start=0;
            command_replay=0;replay_id=0;consume=0;seal_hold=0;seal_request=0;request_id=1;
            memory_run=1;native_enable=1;slot_enable=1;response_enable=1;same_edge_response=0;previous_state=0;
            repeat(5)@(negedge clk);resetn=1;repeat(20)@(negedge clk);
            check(start_ready && drained && !fault,"empty common reset");
        end
    endtask
    task launch(input [7:0] op,input [15:0] length,input [127:0] value);
        begin @(negedge clk);opcode=op;payload_length=length;payload=value;command_start=1;reference_seen=0;
            @(negedge clk);command_start=0;end
    endtask
    task await_command(input [7:0] expected,input bit oracle);
        begin guard=0;while(!command_done && guard<1500000)begin @(negedge clk);guard=guard+1;end
            check(command_done && status==expected,"command terminal/status");
            if(oracle)begin
                if(!((reference_seen && reference_result==expected) || (reference_done && reference_status==expected)))$display("ORACLE op=%h expected=%h seen=%b result=%h done=%b status=%h",opcode,expected,reference_seen,reference_result,reference_done,reference_status);
                check((reference_seen && reference_result==expected) || (reference_done && reference_status==expected),"legacy command status matches");end
            request_id=request_id+1;@(negedge clk);end
    endtask
    task command(input [7:0] op,input [15:0] length,input [127:0] value,input [7:0] expected);
        begin launch(op,length,value);await_command(expected,1);end
    endtask
    task result32(input integer at,output reg [31:0] value);
        integer i;begin value=0;for(i=0;i<4;i=i+1)begin command_addr=at+i;#1;value=value|({24'd0,command_data}<<(i*8));end end
    endtask
    task sample(input integer at);
        begin @(negedge clk);pcm_pair=pattern(at);pcm_valid=1;@(negedge clk);pcm_valid=0;repeat(12)@(negedge clk);end
    endtask
    task await_ready;
        begin guard=0;while(record_state!=4 && record_state!=5 && guard<100000)begin @(negedge clk);guard=guard+1;end
            check(record_state==4 && drained && !fault,"eventual real READY");end
    endtask
    task seal;
        begin @(negedge clk);check(seal_ready,"seal admission");seal_hold=1;seal_request=1;@(negedge clk);seal_request=0;end
    endtask
    task release_transfer;
        begin @(negedge clk);consume=1;@(negedge clk);consume=0;end
    endtask
    task compare_transfer(input integer raw_bytes,input bit compare_oracle);
        integer i;reg [31:0] wire_crc,wire_expected,word_value;
        begin
            check(transfer_valid,"transfer published");
            if(compare_oracle)check(reference_valid && transfer_length==reference_length,"wire length same as original recorder");
            wire_crc=32'hffffffff;block_crc=32'hffffffff;
            for(i=0;i<transfer_length;i=i+1)begin
                @(negedge clk);transfer_addr=i;repeat(2)@(negedge clk);
                if(compare_oracle)check(transfer_data===reference_transfer,"wire bytes differ from legacy RAM/codec");
                if(i<transfer_length-4)wire_crc=crc_byte(wire_crc,transfer_data);
                else wire_expected[(i-transfer_length+4)*8+:8]=transfer_data;
                if(i>=40 && i<44)block_crc[(i-40)*8+:8]=transfer_data;
                if(raw_bytes && i>=44 && i<44+raw_bytes)begin
                    word_value=pattern((dut.data_offset+i-44)/4);
                    check(transfer_data===((word_value>>(8*((dut.data_offset+i-44)%4)))&255),"stereo/raw byte order");
                end
                wire_bytes=wire_bytes+1;
            end
            check(wire_expected==~wire_crc,"wire frame CRC");
        end
    endtask
    initial begin
        // Before the raw transport's memory reset releases, START must not
        // allocate even the business object's ID/task slot.
        repeat(5)@(negedge clk);memory_run=0;repeat(5)@(negedge clk);resetn=1;repeat(8)@(negedge clk);
        launch(8'h20,8,{64'd0,32'd32,32'd1});await_command(8'h82,0);
        check(recording_id==0 && dut.object_counter==0 && dut.operation_counter==0,"unavailable START allocates no object/task");cases=cases+1;
        // Maximum descriptor and codec retain every wire byte of original RAM.
        reset_all();launch(8'h20,8,{64'd0,32'd2048,32'd1});
        check(recording_id==0 && dut.object_counter==0,"START identity waits actual raw fire");await_command(1,1);
        expected_crc=32'hffffffff;
        for(n=0;n<2048;n=n+1)begin
            if(n==2045)native_enable=0;
            sample(n);for(k=0;k<4;k=k+1)expected_crc=crc_byte(expected_crc,pattern(n)>>(8*k));
        end
        check(record_state==3 && reference_state==4 && accepted==2048 && committed<2048,"capacity waits true native drain");
        repeat(80)@(negedge clk);check(record_state!=4,"slot acceptance cannot publish READY");native_enable=1;await_ready();
        check(recorded_frames==2048 && dut.object_crc==~expected_crc,"complete prefix object CRC");
        command(8'h3c,16,{32'd0,recording_id,BOOT},0);result32(0,tid);before_reads=reads;
        command(8'h31,12,{32'd0,32'd8112,32'd0,tid},0);
        check(reads-before_reads==254 && fetch_length==8112,"max8112 descriptor fetches padded native beats");
        compare_transfer(8112,1);release_transfer();command(8'h32,12,{32'd0,block_crc,32'd8112,tid},0);
        command(8'h31,12,{32'd0,32'd80,32'd8112,tid},0);compare_transfer(80,1);release_transfer();
        command(8'h32,12,{32'd0,block_crc,32'd8192,tid},0);
        command(8'h33,8,{64'd0,~expected_crc,tid},0);
        command(8'h3c,16,{32'd28,recording_id,BOOT},0);result32(0,tid);before_reads=reads;
        command(8'h31,12,{32'd0,32'd8112,32'd28,tid},0);
        check(reads-before_reads==255,"max8112 descriptor with padded first/last beat");
        compare_transfer(8112,1);release_transfer();command(8'h34,4,{96'd0,tid},0);cases=cases+1;
        // Rice and second-order modes use the same bytes/cache latency as RAM.
        command(8'h3d,16,{32'd0,recording_id,BOOT},0);result32(0,tid);
        command(8'h3e,12,{32'd0,32'd256,32'd0,tid},0);check(dut.data_codec==10,"Rice selected");compare_transfer(0,1);release_transfer();
        command(8'h34,4,{96'd0,tid},0);
        command(8'h40,16,{32'd0,recording_id,BOOT},0);result32(0,tid);
        command(8'h41,12,{32'd0,32'd256,32'd0,tid},0);check(dut.data_codec==11,"second order selected");compare_transfer(0,1);release_transfer();
        command(8'h34,4,{96'd0,tid},0);cases=cases+1;
        // Disconnect during old native read: READY survives, cache completion
        // is abandoned, and reconnect/new descriptor waits for its own fire.
        command(8'h3c,16,{32'd0,recording_id,BOOT},0);result32(0,tid);response_enable=0;
        launch(8'h31,12,{32'd0,32'd256,32'd0,tid});wait(model_read);@(negedge clk);connected=0;
        repeat(5)@(negedge clk);check(record_state==4 && !dut.raw_cache_owned && !transfer_valid,"disconnect preserves READY and abandons cache");
        connected=1;command(8'h3c,16,{32'd256,recording_id,BOOT},0);result32(0,tid);before_fetch=fetches;
        launch(8'h31,12,{32'd0,32'd256,32'd256,tid});repeat(20)@(negedge clk);
        check(fetches==before_fetch && !command_done && !dut.raw_cache_owned,"new descriptor waits old fetch native drain");
        response_enable=1;await_command(0,1);check(fetches==before_fetch+1,"new descriptor owns a distinct fetch fire");compare_transfer(256,1);
        release_transfer();command(8'h34,4,{96'd0,tid},0);cases=cases+1;
        // Replay requests must reference the surviving object and fetch anew.
        command(8'h3c,16,{32'd0,recording_id,BOOT},0);result32(0,tid);command_replay=1;replay_id=recording_id;
        command(8'h31,12,{32'd0,32'd256,32'd0,tid},0);compare_transfer(256,1);release_transfer();
        replay_id=recording_id+1;launch(8'h31,12,{32'd0,32'd256,32'd0,tid});await_command(8'h88,0);
        command_replay=0;launch(8'h34,4,{96'd0,tid});await_command(0,0);cases=cases+1;
        // Existing remote STOP tasks remain pending across every final CRC
        // phase and complete only after the real final write acceptance.
        for(n=0;n<6;n=n+1)begin
            reset_all();command(8'h20,8,{64'd0,32'd32,32'd1},1);sample(0);native_enable=0;
            @(negedge clk);pcm_pair=pattern(1);pcm_valid=1;@(negedge clk);pcm_valid=0;
            repeat(n)@(negedge clk);command(8'h21,12,{32'd0,recording_id,BOOT},1);
            repeat(30)@(negedge clk);check(record_state==3 && !dut.task_finished[dut.stop_task],"STOP task waits native final drain");
            native_enable=1;await_ready();check(recorded_frames==2 && dut.object_crc==reference.object_crc &&
                dut.task_finished[dut.stop_task] && !dut.task_failed[dut.stop_task],"STOP real terminal and CRC prefix");cases=cases+1;
        end
        // Every nonfull last native beat, STOP/seal, holds its exact CRC prefix.
        for(n=1;n<8;n=n+1)begin
            reset_all();command(8'h20,8,{64'd0,32'd32,32'd1},1);
            for(k=0;k<n;k=k+1)sample(k);
            native_enable=0;before_seal=seal_successes;seal();repeat(80)@(negedge clk);
            check(record_state==3 && seal_pending && seal_successes==before_seal,"seal waits last partial native write");
            native_enable=1;await_ready();guard=0;while(seal_pending && guard<1000)begin @(negedge clk);guard=guard+1;end
            repeat(2)@(negedge clk);check(seal_successes==before_seal+1 && recorded_frames==n && dut.object_crc==reference.object_crc,"partial seal CRC/native count");
            seal_hold=0;command(8'h23,12,{32'd0,recording_id,BOOT},0);check(record_state==0 && start_ready,"clear old object only after native clear");cases=cases+1;
        end
        // Source loss wins even on the exact final storage-drain edge. An
        // earlier source check must not be overwritten by the finalizer's NBA.
        for(n=0;n<3;n=n+1)begin
            reset_all();command(8'h20,8,{64'd0,32'd32,32'd1},1);sample(0);native_enable=0;
            before_fail=seal_failures;before_seal=seal_successes;seal();repeat(20)@(negedge clk);native_enable=1;
            wait(drained);@(negedge clk);
            if(n==0)source_ready=0;else if(n==1)source_fault=1;else enable=0;
            repeat(8)@(negedge clk);
            check(record_state==5 && seal_failures==before_fail+1 && seal_successes==before_seal,
                "same-edge source loss outranks native-drain READY");cases=cases+1;
        end
        // Endpoint timeout with memory clock stopped is a failed object; the
        // transport can later drain solely for cleanup, never promote READY.
        reset_all();command(8'h20,8,{64'd0,32'd32,32'd1},1);sample(0);memory_run=0;before_fail=seal_failures;before_seal=seal_successes;seal();
        repeat(BUDGET+80)@(negedge clk);
        check(record_state==5 && seal_pending && seal_failures==before_fail+1 && seal_successes==before_seal,"seal timeout is FAILED with cleanup fence");
        memory_run=1;guard=0;while((seal_pending || dut.raw_closing) && guard<10000)begin @(negedge clk);guard=guard+1;end
        check(drained && record_state==5 && seal_successes==before_seal,"late native drain cannot resurrect READY");
        seal_hold=0;launch(8'h23,12,{32'd0,recording_id,BOOT});await_command(0,1);cases=cases+1;
        // Credit loss never stalls the sample producer: error and close fence.
        reset_all();command(8'h20,8,{64'd0,32'd64,32'd1},1);memory_run=0;
        for(n=0;n<12;n=n+1)sample(n);
        check(record_state==5 && object_fault,"FIFO overflow fails rather than audio backpressure");memory_run=1;
        guard=0;while(!drained && guard<10000)begin @(negedge clk);guard=guard+1;end
        check(drained && record_state==5,"overflow auto-close true drain");cases=cases+1;
        // CLEAR accepted before link loss still waits the actual memory reply.
        reset_all();command(8'h20,8,{64'd0,32'd1,32'd1},1);sample(0);await_ready();saved_id=recording_id;
        memory_run=0;launch(8'h23,12,{32'd0,recording_id,BOOT});wait(dut.raw_clear_sent);@(negedge clk);connected=0;enable=0;
        repeat(80)@(negedge clk);check(recording_id==saved_id && record_state==4 && !command_done,"CLEAR identity waits actual storage completion despite link loss");
        memory_run=1;guard=0;while(record_state!=0 && guard<10000)begin @(negedge clk);guard=guard+1;end
        check(record_state==0 && recording_id==0 && start_ready && !dut.raw_clear_sent,"accepted CLEAR survives disconnected observer");cases=cases+1;
        $display("PASS BLE_RAW_OWNER cases=%0d checks=%0d wire_bytes=%0d fetches=%0d",cases,checks,wire_bytes,fetches);$finish;
    end
    initial begin #200000000;$fatal(1,"BLE raw owner watchdog");end
endmodule
