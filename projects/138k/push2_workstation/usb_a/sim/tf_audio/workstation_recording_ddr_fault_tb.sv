`timescale 1ns/1ps
`default_nettype none
module tb_workstation_recording_ddr_fault;
    parameter integer CASE=0;
    reg clk=0;always #5 clk=~clk;
    reg rstn=0,scan=0,return_valid=0;
    wire en,sticky_fault,transport_fault,scan_ready,scan_response,record_response;
    wire [255:0] returned;
    workstation_recording_ddr_arbiter_pipeline #(.RECORDING_ENABLE(1)) dut(
        .clk(clk),.reset_n(rstn),.bist_done(1'b1),.bist_valid(1'b0),.bist_write(1'b0),
        .bist_address(29'd0),.bist_data(256'd0),.bist_ready(),.bist_response(),
        .scan_valid(scan),.scan_address(29'h8),.scan_ready(scan_ready),.scan_response(scan_response),
        .display_valid(1'b0),.display_address(29'd0),.display_ready(),.display_response(),
        .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),.audio_ready(),.audio_response(),
        .music_valid(1'b0),.music_write(1'b0),.music_address(29'd0),.music_data(256'd0),.music_mask(32'd0),.music_ready(),.music_response(),
        .delay_valid(1'b0),.delay_write(1'b0),.delay_address(29'd0),.delay_data(256'd0),.delay_ready(),.delay_response(),
        .writer_valid(1'b0),.writer_address(29'd0),.writer_data(256'd0),.writer_ready(),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
        .recording_valid(1'b0),.recording_write(1'b0),.recording_address(29'd0),.recording_data(256'd0),.recording_mask(32'd0),
        .recording_ready(),.recording_response(record_response),
        .app_cmd(),.app_en(en),.app_wren(),.app_wend(),.app_address(),.app_data(),.app_mask(),
        .app_ready(1'b1),.app_write_ready(1'b1),.app_response(return_valid),.app_response_data(256'hdeadbeef),
        .response_data(returned),.response_fault(sticky_fault),.core_accept_o(),.native_accept_o(),.transport_fault_o(transport_fault));
    reg published=0,slot_ready=0,native_accept=0,raw_fault=0;
    wire slot_valid,native_ready,bridge_fault,submitted,protocol_fault;
    workstation_recording_ddr_native_bridge bridge(
        .clk_i(clk),.rst_ni(rstn),.published_valid_i(published),.slot_ready_i(slot_ready),
        .native_accept_i(native_accept),.transport_fault_i(raw_fault),.slot_valid_o(slot_valid),
        .native_ready_o(native_ready),.transport_fault_o(bridge_fault),.submitted_o(submitted),.protocol_fault_o(protocol_fault));
    initial begin
        repeat(4)@(negedge clk);rstn=1;repeat(2)@(negedge clk);
        if(CASE<3)begin
            if(CASE!=0)begin
                scan=1;@(negedge clk);scan=0;
                while(!en)@(negedge clk);
                @(negedge clk);
                // Fault injection deliberately corrupts a real accepted read's
                // owner entry; the normal scoreboard never reads DUT tags.
                if(CASE==1)dut.g_recording.tags[0]=4'd3;
                else dut.g_recording.tags[0]=4'd9;
            end
            return_valid=1;#1;
            if(!transport_fault)$fatal(1,"missing same-edge empty/invalid owner fault");
            @(negedge clk);return_valid=0;
            if(!sticky_fault || scan_response || record_response)
                $fatal(1,"bad owner response routed or fault not sticky");
            repeat(3)@(negedge clk);
            if(!transport_fault)$fatal(1,"transport fault recovered without common reset");
        end else if(CASE==3)begin
            native_accept=1;#1;
            if(native_ready)$fatal(1,"native completion without submitted identity acknowledged");
            if(!bridge_fault)$fatal(1,"bridge protocol fault not visible before edge");
            @(negedge clk);native_accept=0;
            if(!protocol_fault || !bridge_fault)$fatal(1,"missing impossible native completion fault");
        end else if(CASE==4)begin
            published=1;slot_ready=1;#1;
            if(!slot_valid || native_ready)$fatal(1,"slot ACK mistaken for native acceptance");
            @(negedge clk);slot_ready=0;
            if(!submitted || slot_valid || native_ready)$fatal(1,"bridge did not retain submitted command");
            // Slot becomes free after core accepts it, while PHY remains
            // stalled. This must never allow a second enqueue of the same cmd.
            slot_ready=1;repeat(8)begin @(negedge clk);
                if(!submitted || slot_valid || native_ready)$fatal(1,"core/local ACK duplicated submitted command");
            end
            native_accept=1;#1;
            if(!native_ready)$fatal(1,"real native acceptance not acknowledged");
            @(negedge clk);native_accept=0;published=0;
            if(submitted || protocol_fault)$fatal(1,"bridge failed to retire unique native command");
        end else begin
            published=1;slot_ready=1;@(negedge clk);slot_ready=0;published=0;#1;
            if(!bridge_fault)$fatal(1,"bridge protocol fault not visible before edge");
            @(negedge clk);
            if(!protocol_fault || !bridge_fault || !submitted)$fatal(1,"withdrawn submitted command escaped protocol fault");
        end
        rstn=0;published=0;native_accept=0;return_valid=0;
        repeat(3)@(negedge clk);rstn=1;repeat(2)@(negedge clk);
        if(sticky_fault || transport_fault || bridge_fault || submitted)$fatal(1,"common reset did not rearm clean path");
        $display("PASS recording DDR fault/bridge case=%0d",CASE);$finish;
    end
    initial begin #100000;$fatal(1,"fault fixture timeout");end
endmodule
`default_nettype wire
