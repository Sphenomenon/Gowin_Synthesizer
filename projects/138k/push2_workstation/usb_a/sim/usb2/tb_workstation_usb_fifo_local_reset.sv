`timescale 1ns/1ps
// The real generated FIFO, including its unreset read output buffer.
module tb_workstation_usb_fifo_local_reset;
    reg usb_clk=0,audio_clk=0,usb_run=1,audio_run=1,reset=1;
    always #10.416667 if(usb_run)usb_clk=!usb_clk;
    always #6.510417 if(audio_run)audio_clk=!audio_clk;
    reg [17:0] data=0;
    reg write_enable=0,read_enable=1;
    wire write_ready,read_ready;
    wire [17:0] read_data;
    integer transfers=0,assertions=0,releases=0,stopped_usb_checks=0,stopped_audio_checks=0;
    gw138k_usb_event_fifo dut(.usb_clk(usb_clk),.audio_clk(audio_clk),.usb_rst(reset),
        .w_data(data),.w_en(write_enable),.w_rdy(write_ready),
        .r_en(read_enable),.r_data(read_data),.r_rdy(read_ready));
    task async_assert;
        begin
            reset=1;#0.001;
            if(dut.fifo.unbuffered.write_domain_reset.release_q!==0 ||
               !dut.fifo.unbuffered.write_reset || write_ready ||
               dut.fifo.unbuffered.produce_w_bin!==0 || dut.fifo.unbuffered.produce_w_gry!==0)
                $fatal(1,"write state did not assert asynchronously with a stopped clock");
            assertions=assertions+1;
        end
    endtask
    task exact_usb_release;
        begin
            @(negedge usb_clk);reset=0;
            #0.001;if(write_ready || !dut.fifo.unbuffered.write_reset)$fatal(1,"release without USB edge");
            @(posedge usb_clk);#0.001;
            if(write_ready || !dut.fifo.unbuffered.write_reset)$fatal(1,"release before two real USB edges");
            @(posedge usb_clk);#0.001;
            if(!write_ready || dut.fifo.unbuffered.write_reset)$fatal(1,"missing second USB-edge release");
            releases=releases+1;
        end
    endtask
    task drain;
        begin
            read_enable=1;repeat(16)@(negedge audio_clk);
            if(read_ready || dut.fifo.unbuffered.consume_r_bin!==0 ||
               dut.fifo.unbuffered.produce_r_gry!==0)
                $fatal(1,"real read reset/output drain failed");
        end
    endtask
    task transfer(input [17:0] value);
        integer budget;
        begin
            @(negedge usb_clk);data=value;write_enable=1;
            do @(posedge usb_clk);while(!write_ready);
            @(negedge usb_clk);write_enable=0;
            budget=0;
            do begin @(negedge audio_clk);budget=budget+1;
                if(budget>40)$fatal(1,"fresh item lost after local release");
            end while(!read_ready);
            if(read_data!==value)$fatal(1,"stale item escaped reset/drain");
            transfers=transfers+1;
            repeat(6)@(negedge audio_clk);
        end
    endtask
    initial begin
        #1;async_assert();exact_usb_release();drain();transfer(18'h12345);
        // Stop USB across audio-owned deassertion. Audio reset and buffer
        // drain must complete while the producer remains locally in reset.
        @(negedge usb_clk);usb_run=0;async_assert();
        repeat(6)@(negedge audio_clk);
        reset=0;repeat(16)@(negedge audio_clk);
        if(write_ready || !dut.fifo.unbuffered.write_reset ||
           dut.fifo.unbuffered.r_rst || read_ready)
            $fatal(1,"stopped USB released producer or delayed original audio reset");
        stopped_usb_checks=stopped_usb_checks+1;
        reset=1;usb_run=1;exact_usb_release();drain();transfer(18'h2abcd);
        // A stopped audio clock cannot delay producer assertion, and USB
        // release must not manufacture an audio reset acknowledgement.
        @(negedge audio_clk);audio_run=0;async_assert();
        repeat(10)@(negedge usb_clk);
        if(!dut.fifo.unbuffered.r_rst || write_ready)$fatal(1,"stopped audio acknowledged its reset release");
        stopped_audio_checks=stopped_audio_checks+1;
        audio_run=1;repeat(6)@(negedge audio_clk);exact_usb_release();drain();transfer(18'h0fedc);
        // Repeated reset boundaries with both clocks absent coalesce to one
        // empty generation; no elapsed wall time can release either domain.
        @(negedge usb_clk);usb_run=0;
        @(negedge audio_clk);audio_run=0;
        repeat(3)begin async_assert();#7;reset=0;#7;
            if(write_ready || !dut.fifo.unbuffered.write_reset)$fatal(1,"both-stopped release");
        end
        reset=1;usb_run=1;audio_run=1;repeat(6)@(negedge audio_clk);
        exact_usb_release();drain();transfer(18'h3cafe);
        $display("PASS usb_fifo_local_reset: transfers=%0d asynchronous_assertions=%0d two_edge_releases=%0d stopped_usb=%0d stopped_audio=%0d both_stopped_boundaries=3",transfers,assertions,releases,stopped_usb_checks,stopped_audio_checks);
        $finish;
    end
    initial begin #1000000;$fatal(1,"local-reset watchdog");end
endmodule
