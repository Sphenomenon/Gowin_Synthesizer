`timescale 1ns/1ps
module tb_workstation_performance_release;
    reg reset50=1, audio_reset_n=1, source_clk=0, destination_clk=0;
    wire reset_n=reset50 && audio_reset_n;
    reg source_valid=0;
    reg [447:0] source_data=0;
    wire destination_valid;
    wire [447:0] destination_data;
    wire [31:0] drops;
    integer cases=0, async_checks=0, release_checks=0, payloads=0;
    integer cause,source_high,destination_high,order;
    gw138k_stream_cdc #(.WIDTH(448)) dut(
        .reset_n(reset_n),.source_clk(source_clk),.destination_clk(destination_clk),
        .source_valid(source_valid),.source_data(source_data),.drop_count(drops),
        .destination_valid(destination_valid),.destination_data(destination_data));

    task source_edge;begin
        source_clk=0;#6.510417;source_clk=1;#6.510417;source_clk=0;
    end endtask
    task destination_edge;begin
        destination_clk=0;#10;destination_clk=1;#10;destination_clk=0;
    end endtask
    function automatic [447:0] word(input integer generation);
        integer i;begin
            for(i=0;i<14;i=i+1)word[32*i+:32]=32'hdac13800^(generation*32'h10203)^(i*32'h1010101);
        end
    endfunction
    task quiet_reset;begin
        if(dut.source_release!==0 || dut.destination_release!==0 || dut.held_data!==0 ||
           destination_data!==0 || destination_valid!==0 || dut.request_toggle!==0 ||
           dut.acknowledge_toggle!==0 || drops!==0)$fatal(1,"asynchronous quiet reset failed");
        async_checks=async_checks+1;
    end endtask
    task source_release;integer i;reg [2:0] expected;begin
        expected=0;
        for(i=0;i<3;i=i+1)begin
            source_edge();expected={expected[1:0],1'b1};
            if(dut.source_release!==expected)$fatal(1,"source release edge count changed");
            release_checks=release_checks+1;
        end
    end endtask
    task destination_release;integer i;reg [2:0] expected;begin
        expected=0;
        for(i=0;i<3;i=i+1)begin
            destination_edge();expected={expected[1:0],1'b1};
            if(dut.destination_release!==expected)$fatal(1,"destination release edge count changed");
            release_checks=release_checks+1;
        end
    end endtask
    task send_fresh(input integer generation);integer i;begin
        source_data=word(generation);source_valid=1;source_edge();source_valid=0;
        // Destination is stopped: a second observation must drop rather
        // than replace the first genuine telemetry snapshot.
        source_data=word(generation+1000);source_valid=1;source_edge();source_valid=0;
        if(drops!==1 || dut.held_data!==word(generation))$fatal(1,"stopped-consumer snapshot hold/drop failed");
        for(i=0;i<4;i=i+1)destination_edge();
        if(!destination_valid || destination_data!==word(generation))$fatal(1,"fresh snapshot missing or stale");
        payloads=payloads+1;destination_edge();
        if(destination_valid)$fatal(1,"destination valid repeated without a new request");
        repeat(3)source_edge();
    end endtask
    initial begin
        #1;reset50=0;#0.001;quiet_reset();reset50=1;
        source_release();destination_release();send_fresh(1);
        for(cause=0;cause<2;cause=cause+1)
        for(source_high=0;source_high<2;source_high=source_high+1)
        for(destination_high=0;destination_high<2;destination_high=destination_high+1)
        for(order=0;order<2;order=order+1)begin
            source_valid=0;source_clk=source_high;destination_clk=destination_high;#1;
            if(cause==0)reset50=0;else audio_reset_n=0;
            #0.001;quiet_reset();#100;quiet_reset();
            if(cause==0)reset50=1;else audio_reset_n=1;
            #100;quiet_reset();
            if(order==0)begin
                source_release();
                if(dut.destination_release!==0)$fatal(1,"destination released without its clock");
                destination_release();
            end else begin
                destination_release();
                if(dut.source_release!==0)$fatal(1,"source released without its clock");
                source_release();
            end
            if(dut.held_data!==0 || destination_data!==0 || destination_valid!==0)
                $fatal(1,"old snapshot survived reset or appeared on release");
            cases=cases+1;send_fresh(cases+1);
        end
        if(cases!=16 || payloads!=17 || async_checks!=49 || release_checks!=102)
            $fatal(1,"performance release coverage missing");
        $display("PASS performance_release cases=%0d async_checks=%0d release_checks=%0d payloads=%0d width=448",
                 cases,async_checks,release_checks,payloads);$finish;
    end
    initial begin #100000;$fatal(1,"performance release timeout");end
endmodule
