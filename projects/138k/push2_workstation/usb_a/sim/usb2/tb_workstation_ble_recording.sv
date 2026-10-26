`timescale 1ns/1ps
module tb_workstation_ble_recording;
    reg clk=0;
    always #10 clk=~clk;
    reg resetn=0,connected=1,source_ready=1,source_fault=0,pcm_valid=0;
    reg [31:0] pcm_pair=0;
    reg command_start=0,transfer_consume=0;
    reg [7:0] opcode=0;
    reg [31:0] request_id=1,elapsed_ms=100;
    reg [15:0] payload_length=0;
    reg [127:0] payload=0;
    reg [6:0] command_addr=0;
    reg [12:0] transfer_addr=0;
    wire command_done,transfer_valid;
    wire [7:0] command_status,command_data,record_state,transfer_data;
    wire [6:0] command_length;
    wire [31:0] recording_id,recorded_frames,capacity_frames;
    wire [12:0] transfer_length;
    localparam BOOT_ID=64'h1234567811223344;
    reg [31:0] expected_crc=32'hffffffff,object_crc,block_crc,transfer_id,start_operation;
    reg [7:0] returned[0:303];
    integer sample_index,offset,byte_index,guard,task_round,task_slot;
    reg [31:0] sample_word;
    ble_recording #(.CLK_HZ(50000000),.EXTERNAL_PCM(1),.CAPACITY_FRAMES(2048)) dut (
        .clk(clk),.resetn(resetn),.enable(1'b1),.connected(connected),.transfer_subscribed(1'b1),
        .pcm_valid_i(pcm_valid),.pcm_pair_i(pcm_pair),.source_ready_i(source_ready),.source_fault_i(source_fault),
        .boot_id(BOOT_ID),.att_value_limit(9'd20),.elapsed_ms(elapsed_ms),
        .command_start(command_start),.command_replay(1'b0),.opcode(opcode),.request_id(request_id),
        .nonce(64'habcdef),.payload_length(payload_length),.payload(payload),.replay_recording_id(32'd0),
        .command_done(command_done),.command_status(command_status),.command_length(command_length),
        .command_addr(command_addr),.command_data(command_data),.record_state(record_state),
        .recording_id(recording_id),.recorded_frames(recorded_frames),.capacity_frames(capacity_frames),
        .transfer_valid(transfer_valid),.transfer_compact(),.transfer_bulk(),.transfer_direct(),
        .transfer_length(transfer_length),.transfer_addr(transfer_addr),.transfer_data(transfer_data),
        .transfer_consume(transfer_consume)
    );
    function [31:0] crc_byte(input [31:0] previous,input [7:0] value);
        reg [31:0] working;
        integer bit_index;
        begin
            working=previous^value;
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)
                working=(working>>1)^(working[0] ? 32'hedb88320 : 0);
            crc_byte=working;
        end
    endfunction
    function [31:0] pattern(input integer frame_index);
        reg [15:0] left_sample;
        begin left_sample=frame_index*13+16'h1234;pattern={~left_sample,left_sample};end
    endfunction
    task command(input [7:0] next_opcode,input [15:0] length,input [127:0] data,input [7:0] expected_status);
        begin
            @(negedge clk);opcode=next_opcode;payload_length=length;payload=data;command_start=1;
            @(negedge clk);command_start=0;guard=0;
            while(!command_done && guard<50000) begin @(negedge clk);guard=guard+1;end
            if(!command_done || command_status!==expected_status)
                $fatal(1,"BLE opcode %h result %h expected %h",next_opcode,command_status,expected_status);
            request_id=request_id+1;@(negedge clk);
        end
    endtask
    task read_result32(input integer at,output reg [31:0] value);
        integer position;
        begin
            value=0;
            for(position=0;position<4;position=position+1) begin
                command_addr=at+position;#1;value=value|({24'd0,command_data}<<(position*8));
            end
        end
    endtask
    task send_sample(input [31:0] value);
        begin
            @(negedge clk);pcm_pair=value;pcm_valid=1;
            @(negedge clk);pcm_valid=0;repeat(12)@(negedge clk);
        end
    endtask
    task clear_recording;
        begin command(8'h23,12,{32'd0,recording_id,BOOT_ID},0);end
    endtask
    task check_start_task(input [7:0] phase,input [7:0] result);
        begin
            command(8'h04,4,{96'd0,start_operation},0);
            command_addr=9;#1;
            if(command_data!==phase)$fatal(1,"Live start task phase %h expected %h",command_data,phase);
            command_addr=10;#1;
            if(command_data!==result)$fatal(1,"Live start task result %h expected %h",command_data,result);
        end
    endtask
    initial begin
        repeat(5)@(negedge clk);resetn=1;repeat(5)@(negedge clk);
        command(8'h20,8,128'd0,8'h81);
        source_ready=0;command(8'h20,8,128'd1,8'h83);source_ready=1;
        command(8'h20,8,{64'd0,32'd2049,32'd1},8'h89);
        command(8'h20,8,{64'd0,32'd2048,32'd1},1);
        for(sample_index=0;sample_index<2048;sample_index=sample_index+1) begin
            connected=sample_index<10 || sample_index>30;
            sample_word=pattern(sample_index);
            send_sample(sample_word);
            for(byte_index=0;byte_index<4;byte_index=byte_index+1)
                expected_crc=crc_byte(expected_crc,sample_word>>(byte_index*8));
        end
        connected=1;
        if(record_state!=4 || recorded_frames!=2048 || capacity_frames!=2048)
            $fatal(1,"Live PCM capacity seal or disconnect continuation");
        command(8'h22,4,128'd0,0);read_result32(32,object_crc);
        if(object_crc!==~expected_crc)$fatal(1,"Live object CRC %h expected %h",object_crc,~expected_crc);
        command(8'h30,16,{32'd0,recording_id,BOOT_ID},0);read_result32(0,transfer_id);
        for(offset=0;offset<8192;offset=offset+256) begin
            command(8'h31,12,{32'd0,32'd256,offset[31:0],transfer_id},0);
            if(!transfer_valid || transfer_length!=304)$fatal(1,"Live transfer frame missing");
            block_crc=32'hffffffff;
            for(byte_index=0;byte_index<304;byte_index=byte_index+1) begin
                @(negedge clk);transfer_addr=byte_index;repeat(2)@(negedge clk);
                returned[byte_index]=transfer_data;
                if(byte_index>=44 && byte_index<300) begin
                    sample_word=pattern((offset+byte_index-44)/4);
                    if(transfer_data!==((sample_word>>(8*((offset+byte_index-44)%4)))&255))
                        $fatal(1,"Live downloaded PCM mismatch at %0d",offset+byte_index-44);
                    block_crc=crc_byte(block_crc,transfer_data);
                end
            end
            if({returned[43],returned[42],returned[41],returned[40]}!==~block_crc)
                $fatal(1,"Live block CRC mismatch");
            @(negedge clk);transfer_consume=1;@(negedge clk);transfer_consume=0;
            command(8'h32,12,{32'd0,~block_crc,offset+32'd256,transfer_id},0);
        end
        command(8'h33,8,{64'd0,object_crc,transfer_id},0);clear_recording();
        command(8'h20,8,{64'd0,32'd64,32'd1},1);read_result32(0,start_operation);
        send_sample(32'h76543210);
        source_ready=0;repeat(3)@(negedge clk);source_ready=1;
        if(record_state!=5 || dut.stop_reason!=6)$fatal(1,"Source change did not stop recording");
        check_start_task(2,0);
        command(8'h30,16,{32'd0,recording_id,BOOT_ID},8'h83);clear_recording();
        command(8'h20,8,{64'd0,32'd64,32'd1},1);read_result32(0,start_operation);source_fault=1;
        repeat(3)@(negedge clk);source_fault=0;
        if(record_state!=5 || dut.stop_reason!=3)$fatal(1,"PCM loss did not stop recording");
        check_start_task(3,8'h83);
        clear_recording();
        command(8'h20,8,{64'd0,32'd64,32'd1},1);send_sample(32'h12345678);
        command(8'h21,12,{32'd0,recording_id,BOOT_ID},1);repeat(10)@(negedge clk);
        if(record_state!=4 || recorded_frames!=1 || dut.stop_reason!=1)$fatal(1,"Live user stop prefix");
        clear_recording();
        command(8'h20,8,{64'd0,32'd64,32'd1},1);
        command(8'h21,12,{32'd0,recording_id,BOOT_ID},8'h83);
        send_sample(32'h9abc5678);
        command(8'h21,12,{32'd0,recording_id,BOOT_ID},1);repeat(10)@(negedge clk);
        if(record_state!=4 || recorded_frames!=1)$fatal(1,"Rejected early stop changed recording");
        command(8'h30,16,{32'd0,recording_id,BOOT_ID},0);read_result32(0,transfer_id);
        command(8'h31,12,{32'd0,32'd4,32'd0,transfer_id},0);
        for(byte_index=0;byte_index<4;byte_index=byte_index+1) begin
            @(negedge clk);transfer_addr=44+byte_index;repeat(2)@(negedge clk);
            if(transfer_data!==((32'h9abc5678>>(8*byte_index))&255))
                $fatal(1,"Rejected early stop changed RAM byte %0d",byte_index);
        end
        resetn=0;repeat(5)@(negedge clk);elapsed_ms=32'hfffffff0;resetn=1;
        repeat(5)@(negedge clk);
        for(task_round=0;task_round<2;task_round=task_round+1) begin
            for(task_slot=0;task_slot<8;task_slot=task_slot+1) begin
                command(8'h20,8,{64'd0,32'd1,32'd1},1);
                if(task_slot==0) read_result32(0,start_operation);
                send_sample(pattern(task_slot));
                if(record_state!=4)$fatal(1,"Single-frame task did not complete");
                clear_recording();
            end
            command(8'h20,8,{64'd0,32'd1,32'd1},8'h82);
            check_start_task(2,0);
            if(task_round==0) begin
                elapsed_ms=32'hfffffff0+32'd59999;repeat(5)@(negedge clk);
                command(8'h20,8,{64'd0,32'd1,32'd1},8'h82);
                check_start_task(2,0);
                elapsed_ms=32'hfffffff0+32'd60000;repeat(5)@(negedge clk);
            end
        end
        command(8'h04,4,128'd1,8'h88);
        $display("PASS BLE task retention: eight slots, 60-second expiry, timer wrap and reuse retention");
        $display("PASS live BLE PCM: stereo bytes, full RAM, CRC, download ACK, disconnect, capacity, source loss and stop");
        $finish;
    end
    initial begin #20000000;$fatal(1,"Live BLE recorder watchdog");end
endmodule
