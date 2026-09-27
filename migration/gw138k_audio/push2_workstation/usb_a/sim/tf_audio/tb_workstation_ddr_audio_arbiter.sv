`timescale 1ns/1ps
module tb_workstation_ddr_audio_arbiter;
    reg clk=0;always #5 clk=~clk;
    reg reset_n=0;
    reg scan_valid=0,display_valid=0,writer_valid=0,cpu_valid=0,cpu_write=0;
    reg audio_valid=0,audio_write=0;
    reg [28:0] scan_address=0,display_address=0,writer_address=0,cpu_address=0,audio_address=0;
    reg [255:0] writer_data=0,cpu_data=0,audio_data=0;
    reg [31:0] cpu_mask=0;
    wire scan_ready,scan_response,display_ready,display_response,writer_ready;
    wire cpu_ready,cpu_response,audio_ready,audio_response;
    wire [2:0] app_cmd;wire app_en,app_wren,app_wend;
    wire [28:0] app_address;wire [255:0] app_data;wire [31:0] app_mask;
    reg app_response=0;wire fault;

    gw138k_ddr_arbiter #(.TAG_BITS(3)) dut(
        .clk(clk),.reset_n(reset_n),.bist_done(1'b1),
        .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),
        .bist_ready(),.bist_response(),.scan_valid(scan_valid),.scan_address(scan_address),
        .scan_ready(scan_ready),.scan_response(scan_response),
        .display_valid(display_valid),.display_address(display_address),
        .display_ready(display_ready),.display_response(display_response),
        .audio_valid(audio_valid),.audio_write(audio_write),.audio_address(audio_address),
        .audio_data(audio_data),.audio_ready(audio_ready),.audio_response(audio_response),
        .writer_valid(writer_valid),.writer_address(writer_address),.writer_data(writer_data),
        .writer_ready(writer_ready),.cpu_valid(cpu_valid),.cpu_write(cpu_write),
        .cpu_address(cpu_address),.cpu_data(cpu_data),.cpu_mask(cpu_mask),
        .cpu_ready(cpu_ready),.cpu_response(cpu_response),.app_cmd(app_cmd),.app_en(app_en),
        .app_wren(app_wren),.app_wend(app_wend),.app_address(app_address),
        .app_data(app_data),.app_mask(app_mask),.app_ready(1'b1),.app_write_ready(1'b1),
        .app_response(app_response),.response_fault(fault));

    task expect_only;
        input integer owner;
        begin
            #1;
            if(audio_response!==(owner==4) || scan_response!==(owner==1) ||
               display_response!==(owner==0) || cpu_response!==(owner==2))
                $fatal(1,"wrong response routing owner=%0d A/S/D/C=%b%b%b%b",
                       owner,audio_response,scan_response,display_response,cpu_response);
        end
    endtask
    task pulse_response;
        input integer owner;
        begin
            @(negedge clk);app_response=1;expect_only(owner);
            @(negedge clk);app_response=0;
        end
    endtask

    initial begin
        repeat(3)@(posedge clk);reset_n=1;@(negedge clk);
        // A native audio write is accepted with its full BL8 payload.
        audio_valid=1;audio_write=1;audio_address=29'h0060000;audio_data={8{32'h41305544}};
        #1;if(!audio_ready || !app_en || !app_wren || app_address!=audio_address || app_data!=audio_data)
            $fatal(1,"audio write not accepted");
        @(negedge clk);audio_valid=0;audio_write=0;

        // Queue audio, scanout, display and CPU reads in that order.
        audio_valid=1;audio_address=29'h0060008;
        #1;if(!audio_ready || app_address[2:0]!=0)$fatal(1,"audio read/alignment");
        @(negedge clk);audio_valid=0;scan_valid=1;scan_address=29'h0000008;
        #1;if(!scan_ready)$fatal(1,"scan read");
        @(negedge clk);scan_valid=0;display_valid=1;display_address=29'h0200008;
        #1;if(!display_ready)$fatal(1,"display read");
        @(negedge clk);display_valid=0;cpu_valid=1;cpu_address=29'h0400000;
        #1;if(!cpu_ready)$fatal(1,"cpu read");
        @(negedge clk);cpu_valid=0;

        pulse_response(4);
        pulse_response(1);
        pulse_response(0);
        pulse_response(2);

        // Simultaneous requests prove scanout priority, then audio priority.
        @(negedge clk);scan_valid=1;audio_valid=1;scan_address=29'h0000010;audio_address=29'h0060010;
        #1;if(!scan_ready || audio_ready)$fatal(1,"scan/audio priority");
        @(negedge clk);scan_valid=0;
        #1;if(!audio_ready)$fatal(1,"audio priority below scanout");
        @(negedge clk);audio_valid=0;
        if(fault)$fatal(1,"unexpected response fault");
        $display("PASS tb_workstation_ddr_audio_arbiter: tagged audio write/read and scan priority");
        $finish;
    end
endmodule
