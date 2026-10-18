`timescale 1ns/1ps
// Physical pad primitives and the independent 50 MHz snapshot multiplexer.
// Uses Gowin's real LUT2/IOBUF simulation models; CLKOUT stays stopped.
module tb_usb2_lowpower_pads;
    reg clk50=0,clk60=0,dir=0,nxt=0;
    always #10 clk50=~clk50;
    tri [7:0] pads;
    reg external_oe=0;
    reg [7:0] external_data=0;
    assign pads=external_oe ? external_data : 8'hzz;
    wire stp,ready,done;
    usb2_device_top dut(.clk_50mhz(clk50),.clk_ulpi60(clk60),
        .ulpi_data(pads),.ulpi_dir(dir),.ulpi_nxt(nxt),.ulpi_stp(stp),
        .led_ready(ready),.led_done(done));

    reg [15:0] source_vid=16'h0424,source_pid=16'h0004;
    reg [7:0] source_fc=8'h45,source_if=8'h00,source_otg=8'h00;
    reg [3:0] source_errorcode=4'h0;
    reg [15:0] source_masks=16'h1421,source_phase_flags=16'hffff;
    reg [31:0] source_samples=32'h10101010;
    reg [7:0] source_stage=8'h60;
    reg [4:0] source_flags=5'b11100;
    reg [127:0] expected_pages;
    reg [7:0] expected_stage;
    reg [4:0] expected_flags;
    reg previous_heartbeat;
    reg [1:0] previous_page;
    integer n,wait_ticks;

    function [31:0] select_payload;
        input [127:0] all_pages;
        input [1:0] page;
        begin
            case(page)
                0: select_payload=all_pages[127:96];
                1: select_payload=all_pages[95:64];
                2: select_payload=all_pages[63:32];
                3: select_payload=all_pages[31:0];
            endcase
        end
    endfunction
    task check_status;
        input integer index;
        input [127:0] all_pages;
        input [7:0] metadata_stage;
        input [4:0] metadata_flags;
        reg [1:0] p;
        begin
            p=dut.status_50mhz[2:1];
            if(p!==((index/8)%4))
                $fatal(1,"status page order index=%0d page=%0d",index,p);
            if(dut.status_50mhz[63:32]!==select_payload(all_pages,p))
                $fatal(1,"snapshot tore or wrong payload page=%0d expected=%08x actual=%08x",p,select_payload(all_pages,p),dut.status_50mhz[63:32]);
            if(dut.status_50mhz[31:16]!==16'h0000 ||
               dut.status_50mhz[15:8]!==metadata_stage ||
               dut.status_50mhz[7:3]!==metadata_flags)
                $fatal(1,"status metadata/reserved mismatch: %016x",dut.status_50mhz);
            if(dut.status_50mhz[0]===previous_heartbeat)
                $fatal(1,"50MHz heartbeat stopped while CLKOUT absent");
            previous_heartbeat=dut.status_50mhz[0];
        end
    endtask
    task set_source_b;
        begin
            source_vid=16'h1234;source_pid=16'h5678;
            source_fc=8'h41;source_if=8'h08;source_otg=8'h06;
            source_errorcode=4'h5;source_masks=16'h1881;
            source_phase_flags=16'h3210;source_samples=32'h01020408;
            source_stage=8'h2b;source_flags=5'b00111;
            force dut.u_diag.clock_stop_seen=1'b0;
            force dut.u_diag.done=1'b0;
            force dut.u_diag.id_ok=1'b1;
            force dut.u_diag.error=1'b1;
            force dut.u_diag.clock_alive=1'b1;
        end
    endtask

    initial begin
        force dut.powerup=13'h1000;
        force dut.u_diag.drive_ready=0;
        force dut.u_diag.data_o=8'ha5;
        #1;if(pads!==8'hzz) $fatal(1,"unarmed pads drive");
        force dut.u_diag.drive_ready=1;
        #1;if(pads!==8'ha5) $fatal(1,"pad output polarity across eight bits");
        force dut.u_diag.data_o=8'h5a;
        #1;if(pads!==8'h5a) $fatal(1,"pad output low/high bit independence");
        dir=1;
        #1;if(pads!==8'hzz) $fatal(1,"raw DIR did not release before any clock edge");
        external_oe=1;external_data=8'h3c;
        #1;if(dut.data_in!==8'h3c) $fatal(1,"pad input path");
        external_data=8'hc3;
        #1;if(dut.data_in!==8'hc3) $fatal(1,"eight pad inputs not independent");
        force dut.u_diag.drive_ready=0;
        external_data=8'h08;
        #1;if(dut.data_in!==8'h08) $fatal(1,"low-power SE0 input");
        external_data=8'h09;
        #1;if(dut.data_in[1:0]!==2'b01) $fatal(1,"low-power FS direct LineState");
        external_data=8'h0a;
        #1;if(dut.data_in[1:0]!==2'b10) $fatal(1,"low-power LS direct LineState");
        external_data=8'h0b;
        #1;if(dut.data_in[1:0]!==2'b11) $fatal(1,"low-power SE1 direct LineState");
        external_oe=0;dir=0;
        #1;if(pads!==8'hzz) $fatal(1,"unarmed return turnaround drove");
        force dut.u_diag.drive_ready=1;
        #1;if(pads!==8'h5a) $fatal(1,"armed return output");
        // DIR=1,ready=0 and DIR=1,ready=1 both have already been covered.
        // Together with ready=0/1 at DIR=0 this exercises all LUT2 INIT=B
        // entries for each of the eight separately instantiated enable LUTs.
        $display("PASS lowpower physical eight-pad LUT2/IOBUF truth table, immediate raw-DIR release, asynchronous input and guarded return");
        force dut.u_diag.drive_ready=0;
        dir=1;external_oe=1;external_data=8'h08;

        force dut.u_diag.vid=source_vid;
        force dut.u_diag.pid=source_pid;
        force dut.u_diag.fc=source_fc;
        force dut.u_diag.if_ctrl=source_if;
        force dut.u_diag.otg=source_otg;
        force dut.u_diag.errorcode=source_errorcode;
        force dut.u_diag.direct_masks=source_masks;
        force dut.u_diag.phase_flags=source_phase_flags;
        force dut.u_diag.sample_counts=source_samples;
        force dut.u_diag.stage=source_stage;
        force dut.u_diag.clock_stop_seen=1'b1;
        force dut.u_diag.done=1'b1;
        force dut.u_diag.id_ok=1'b1;
        force dut.u_diag.error=1'b0;
        force dut.u_diag.clock_alive=1'b0;

        expected_pages={source_vid,source_pid,source_fc,source_if,source_otg,
            source_errorcode,4'b0,source_masks,source_phase_flags,source_samples};
        expected_stage=source_stage;expected_flags=source_flags;
        // Synchronize to the first page-0 boundary of a committed snapshot.
        // Bounded exclusively by the running 50MHz clock.
        previous_page=0;wait_ticks=0;
        begin: find_boundary
            while(wait_ticks<100) begin
                @(negedge clk50);wait_ticks=wait_ticks+1;
                if(previous_page==3 && dut.status_50mhz[2:1]==0 &&
                    dut.status_50mhz[63:32]==source_vid*32'h10000+source_pid)
                    disable find_boundary;
                previous_page=dut.status_50mhz[2:1];
            end
            $fatal(1,"50MHz status failed to update without CLKOUT");
        end
        previous_heartbeat=~dut.status_50mhz[0];
        for(n=0;n<32;n=n+1) begin
            if(n!=0) @(negedge clk50);
            check_status(n,expected_pages,expected_stage,expected_flags);
            if(n==12) begin
                set_source_b;
                #1;if(ready!==1 || done!==0) $fatal(1,"updated LED flags mismatch");
            end
        end
        // A midway source update must affect the next entire rotation only.
        expected_pages={source_vid,source_pid,source_fc,source_if,source_otg,
            source_errorcode,4'b0,source_masks,source_phase_flags,source_samples};
        expected_stage=source_stage;expected_flags=source_flags;
        for(n=0;n<32;n=n+1) begin
            @(negedge clk50);
            check_status(n,expected_pages,expected_stage,expected_flags);
        end
        if(clk60!==0 || ready!==1 || done!==0)
            $fatal(1,"stopped CLKOUT/LED metadata mismatch");
        $display("PASS lowpower 50MHz four-page payload, metadata, heartbeat and coherent complete snapshots with CLKOUT stopped");
        $finish;
    end
endmodule
