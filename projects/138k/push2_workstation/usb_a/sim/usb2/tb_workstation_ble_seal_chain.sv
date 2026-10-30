`timescale 1ns/1ps
module tb_workstation_ble_seal_chain;
    reg clk=0;always #10 clk=~clk;
    reg rst_n=0,pcm_valid=0,source_allowed=1,seal_hold=0,seal_request=0;
    reg [31:0] pcm_pair=0,pcm_sequence=0;
    wire ready,pending,done,failed;
    wire [3:0] failure;
    wire [7:0] state;
    wire [31:0] rid,frames,crc;
    integer done_count=0,failed_count=0;
    workstation_bluetooth #(.CAPACITY_FRAMES(32),.EXTERNAL_SEAL_PROTOCOL(1),.DISABLE_MS(0),.STARTUP_MS(0)) dut(
        .clk_i(clk),.rst_ni(rst_n),.module_uart_tx_i(1'b1),.pcm_valid_i(pcm_valid),
        .source_allowed_i(source_allowed),.pcm_pair_i(pcm_pair),.pcm_sequence_i(pcm_sequence),
        .module_uart_rx_o(),.module_bt_dis_no(),.module_wl_dis_no(),.outputs_active_o(),
        .initialized_o(),.connected_o(),.subscribed_o(),.failed_o(),.status_o(),
        .seal_hold_i(seal_hold),.seal_request_i(seal_request),.seal_ready_o(ready),
        .seal_pending_o(pending),.seal_done_o(done),.seal_failed_o(failed),.seal_failure_code_o(failure),
        .seal_record_state_o(state),.seal_recording_id_o(rid),.seal_frames_o(frames),.seal_crc_o(crc));
    always @(negedge clk)if(rst_n)begin
        if(done)done_count=done_count+1;
        if(failed)failed_count=failed_count+1;
    end
    function [31:0] word_crc(input [31:0] value);
        reg [31:0] c;integer i,j;
        begin c=32'hffffffff;for(i=0;i<4;i=i+1)begin
            c=c^((value>>(8*i))&255);for(j=0;j<8;j=j+1)c=(c>>1)^(c[0]?32'hedb88320:0);
        end word_crc=~c;end
    endfunction
    task sample(input [31:0] value);
        begin @(negedge clk);pcm_pair=value;pcm_sequence=pcm_sequence+1;pcm_valid=1;
            @(negedge clk);pcm_valid=0;end
    endtask
    task seal(input integer target);
        integer n;
        begin
            @(negedge clk);seal_hold=1;seal_request=1;
            @(negedge clk);seal_request=0;n=0;
            while(done_count<target)begin @(negedge clk);n=n+1;if(n>100)$fatal(1,"staged chain seal timeout pending=%b failed=%b code=%0d",pending,failed,failure);end
            repeat(4)@(negedge clk);
        end
    endtask
    initial begin
        repeat(5)@(negedge clk);rst_n=1;repeat(12)@(negedge clk);
        if(dut.initialized_o || !ready)$fatal(1,"uninitialized chain fixture");
        source_allowed=0;seal(1);
        if(state!=0 || rid!=0 || frames!=0 || crc!=0 || failed_count!=0)$fatal(1,"uninitialized EMPTY blocked seal");
        // Link controls alone are forced; recording, its RAM/CRC, wrapper
        // stereo adaptation and all five seal interface layers remain real.
        force dut.u_core.initialized=1'b1;
        force dut.u_core.application.connected=1'b1;
        source_allowed=1;seal_hold=0;sample(32'h00000000);repeat(8)@(negedge clk);
        force dut.u_core.application.command_endpoint.recording.opcode=8'h20;
        force dut.u_core.application.command_endpoint.recording.payload_length=16'd8;
        force dut.u_core.application.command_endpoint.recording.payload={64'd0,32'd32,32'd1};
        force dut.u_core.application.command_endpoint.recording.command_start=1'b1;
        @(negedge clk);release dut.u_core.application.command_endpoint.recording.command_start;
        release dut.u_core.application.command_endpoint.recording.opcode;
        release dut.u_core.application.command_endpoint.recording.payload_length;
        release dut.u_core.application.command_endpoint.recording.payload;
        if(dut.u_core.application.command_endpoint.recording.record_state!=1)$fatal(1,"chain start not accepted");
        sample(32'h1234fedc);seal(2);
        if(state!=4 || rid!=1 || frames!=1 || crc!=word_crc(32'hfedc1234) || failed_count!=0)
            $fatal(1,"staged five-layer seal stereo/CRC identity");
        force dut.u_core.initialized=1'b0;source_allowed=0;repeat(12)@(negedge clk);
        seal(3);
        if(state!=4 || rid!=1 || frames!=1 || crc!=word_crc(32'hfedc1234) || failed_count!=0)
            $fatal(1,"disabled READY object lost identity");
        release dut.u_core.initialized;release dut.u_core.application.connected;
        $display("PASS ble_external_seal_chain: cases=3 done=%0d failed=%0d frames=%0d",done_count,failed_count,frames);$finish;
    end
    initial begin #1000000;$fatal(1,"staged BLE seal watchdog");end
endmodule
