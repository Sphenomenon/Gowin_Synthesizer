"""Checked reuse of the original protocol test's real fragmentation/CRC helpers."""
from pathlib import Path


def build(source: Path) -> str:
    text=source.read_text()
    anchor='    initial begin\n        repeat(3) @(negedge clk); resetn=1;'
    if text.count(anchor)!=1:raise ValueError('BLE protocol fixture initial anchor drift')
    text=text.split(anchor)[0]
    original='    ble_protocol_command #(.CLK_HZ(480000)) dut(.clk(clk),.resetn(resetn),.enable(enable),'
    if text.count(original)!=1:raise ValueError('BLE protocol fixture endpoint anchor drift')
    text=text.replace(original,'''    reg ext_hold=0,ext_request=0,pcm_valid=0,source_ready=1;
    reg [31:0] pcm=0;
    wire ext_ready,ext_pending,ext_done,ext_failed;
    wire [3:0] ext_failure;
    wire [7:0] ext_state;
    wire [31:0] ext_id,ext_frames,ext_crc;
    integer seal_done_count=0,seal_failed_count=0,cases=0;
    always @(negedge clk)if(resetn)begin
        if(ext_done)seal_done_count=seal_done_count+1;
        if(ext_failed)seal_failed_count=seal_failed_count+1;
    end
    ble_protocol_command #(.CLK_HZ(480000),.CAPACITY_FRAMES(32),.EXTERNAL_PCM(1),.EXTERNAL_SEAL_PROTOCOL(1)) dut(.clk(clk),.resetn(resetn),.enable(enable),
        .pcm_valid_i(pcm_valid),.pcm_pair_i(pcm),.source_ready_i(source_ready),.source_fault_i(1'b0),
        .seal_hold_i(ext_hold),.seal_request_i(ext_request),.seal_ready_o(ext_ready),
        .seal_pending_o(ext_pending),.seal_done_o(ext_done),.seal_failed_o(ext_failed),.seal_failure_code_o(ext_failure),
        .seal_record_state_o(ext_state),.seal_recording_id_o(ext_id),.seal_frames_o(ext_frames),.seal_crc_o(ext_crc),''')
    return text+r'''
    task await_seal(input integer target);
        integer q;
        begin q=0;while(seal_done_count<target || ext_pending)begin
            @(negedge clk);q=q+1;if(q>200)$fatal(1,"protocol seal ACK timeout");
        end repeat(3)@(negedge clk);
            if(seal_done_count!=target || seal_failed_count!=0)$fatal(1,"protocol seal wrong result");
        end
    endtask
    task dispatch_under_seal;
        begin
            fork
                begin send_request();end
                begin wait(dut.state==10);@(negedge clk);ext_hold=1;ext_request=1;
                    @(negedge clk);ext_request=0;end
            join
        end
    endtask
    task pcm_word(input [31:0] value);
        begin @(negedge clk);pcm=value;pcm_valid=1;@(negedge clk);pcm_valid=0;repeat(8)@(negedge clk);end
    endtask
    initial begin
        repeat(3)@(negedge clk);resetn=1;
        make_request(1,1,nonce,4);send_request();verify_response(0,40);release_response();
        // A complete, CRC-checked START already in dispatch cannot allocate a
        // new object after the local owner raises its barrier.
        make_request(8'h20,2,nonce,8);request[16]=1;put32(20,32);seal_request();
        dispatch_under_seal();verify_response(8'h82,28);release_response();await_seal(1);
        if(dut.recording.object_counter!=0 || ext_id!=0 || ext_state!=0)$fatal(1,"assembled START crossed seal barrier");cases=cases+1;
        ext_hold=0;make_request(8'h20,3,nonce,8);request[16]=1;put32(20,32);seal_request();
        send_request();verify_response(1,28);read32(20,rid);release_response();pcm_word(32'hfedc1234);
        object_crc=32'hffffffff;
        object_crc=step(object_crc,8'h34);object_crc=step(object_crc,8'h12);object_crc=step(object_crc,8'hdc);object_crc=~step(object_crc,8'hfe);
        // Already assembled CLEAR is rejected; replay of its exact ID remains
        // the same BUSY response and cannot erase the frozen object.
        make_request(8'h23,4,nonce,12);put_object();seal_request();dispatch_under_seal();
        verify_response(8'h82,28);save_response();release_response();await_seal(2);
        send_request();verify_response(8'h82,28);compare_saved();release_response();
        if(ext_state!=4 || ext_id!=rid || ext_frames!=1 || ext_crc!=object_crc || dut.recording.recording_id!=rid)
            $fatal(1,"assembled CLEAR changed sealed object");cases=cases+1;
        make_request(8'h20,5,nonce,8);request[16]=1;seal_request();send_request();verify_response(8'h82,28);release_response();cases=cases+1;
        // Existing INFO and READ formats expose the same immutable prefix.
        make_request(8'h22,6,nonce,4);send_request();verify_response(0,68);
        out_addr=28;#1;if(out!=4)$fatal(1,"INFO not READY");read32(32,crc);if(crc!=48000)$fatal(1,"BLE rate contract changed");
        read32(36,crc);if(crc!=1)$fatal(1,"INFO frames");read32(48,crc);if(crc!=object_crc)$fatal(1,"INFO CRC");release_response();
        make_request(8'h30,7,nonce,16);put_object();seal_request();send_request();verify_response(0,40);read32(16,tid);release_response();
        make_request(8'h31,8,nonce,12);put32(16,tid);put32(20,0);put32(24,4);seal_request();send_request();verify_response(0,32);transfer_check(4,0);release_response();
        if({transfer_saved[47],transfer_saved[46],transfer_saved[45],transfer_saved[44]}!=32'hfedc1234)$fatal(1,"sealed download PCM bytes");cases=cases+1;
        make_request(8'h34,9,nonce,4);put32(16,tid);seal_request();send_request();verify_response(0,24);release_response();
        ext_hold=0;make_request(8'h23,10,nonce,12);put_object();seal_request();send_request();verify_response(0,24);release_response();
        source_ready=0;make_request(8'h20,11,nonce,8);request[16]=1;seal_request();send_request();verify_response(8'h83,28);release_response();
        if(dut.recording.recording_id!=0)$fatal(1,"unsupported source allocated object");source_ready=1;cases=cases+1;
        make_request(8'h20,12,nonce,8);request[16]=1;put32(20,32);seal_request();send_request();verify_response(1,28);read32(20,rid);release_response();pcm_word(32'h98765678);
        make_request(8'h21,13,nonce,12);put_object();seal_request();
        fork
            begin send_request();end
            begin wait(dut.recording.stop_pending);@(negedge clk);ext_hold=1;ext_request=1;
                @(negedge clk);ext_request=0;end
        join
        verify_response(1,28);read32(16,operation);release_response();await_seal(3);
        make_request(4,14,nonce,4);put32(16,operation);seal_request();send_request();verify_response(0,40);
        out_addr=25;#1;if(out!=2)$fatal(1,"accepted remote STOP task not completed");release_response();
        if(ext_id!=rid || ext_state!=4 || ext_frames!=1)$fatal(1,"remote STOP mixed seal identity");cases=cases+1;
        if(cases!=6)$fatal(1,"missing protocol seal coverage");
        $display("PASS ble_external_seal_protocol: cases=%0d seals=%0d failed=%0d download_bytes=4",cases,seal_done_count,seal_failed_count);$finish;
    end
    initial begin #5000000;$fatal(1,"BLE protocol seal watchdog state=%0d",dut.state);end
endmodule
'''
