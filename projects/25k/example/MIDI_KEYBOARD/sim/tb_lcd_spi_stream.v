`timescale 1ns/1ps
// Decode only physical SPI pins. Run this bench both with gowin_io_models.v
// and -DGOWIN_PRIMITIVE_LIBRARY plus the unmodified GW5A prim_sim.v library.
module tb_lcd_spi_stream;
    reg clk=0,reset=1;
    always #10 clk=~clk;
    reg valid=0;
    reg [7:0] data=0;
    reg data_dc=0,last=0;
    wire ready,idle,sck,mosi,dc,ncs;
    lcd_spi_stream dut(.clk(clk),.reset(reset),.valid(valid),.data(data),
        .data_dc(data_dc),.last(last),.ready(ready),.idle(idle),
        .lcd_sck(sck),.lcd_mosi(mosi),.lcd_dc(dc),.lcd_ncs(ncs));
`ifdef GOWIN_PRIMITIVE_LIBRARY
    GSR GSR(.GSRI(1'b1));
`endif

    reg [7:0] expected_data[0:4095];
    reg expected_dc[0:4095],expected_last[0:4095];
    integer queue_head=0,queue_tail=0,accepted=0,decoded=0;
    integer bit_count=0,transactions=0,completed=0,reset_aborts=0;
    integer clocks=0,previous_accept=0,continuous_accepts=0;
    integer continuous_samples=0,paused_samples=0;
    reg [7:0] received=0;
    reg byte_dc=0,expect_release=0,continuous=0,recovering=0;
    time last_rise=0,last_fall=0,last_mosi_change=0,last_dc_change=0;
    time cs_asserted=0;
    time min_mosi_setup=1000000,min_mosi_hold=1000000;
    time min_dc_setup=1000000,min_dc_hold=1000000;
    time min_cs_setup=1000000,min_cs_hold=1000000;

    always @(posedge clk) begin
        clocks=clocks+1;
        if(!reset && valid && ready) begin
            expected_data[queue_tail]=data;
            expected_dc[queue_tail]=data_dc;
            expected_last[queue_tail]=last;
            queue_tail=queue_tail+1;
            accepted=accepted+1;
            if(continuous) begin
                if(continuous_accepts!=0 && clocks-previous_accept!=8)
                    $fatal(1,"Continuous token interval %0d, expected 8 clocks",clocks-previous_accept);
                previous_accept=clocks;
                continuous_accepts=continuous_accepts+1;
            end
        end
        #1;
        if(!reset && idle && !ncs)
            $fatal(1,"idle preceded physical CS release");
    end
    always @(posedge reset) begin
        if(!ncs)reset_aborts=reset_aborts+1;
        queue_head=queue_tail;
        bit_count=0;
        expect_release=0;
        last_rise=0;
        last_fall=0;
    end
    always @(mosi) begin
        if(!reset && !ncs) begin
            if(sck)$fatal(1,"MOSI changed while SCK high");
            if(last_rise!=0) begin
                if($time-last_rise<10)$fatal(1,"MOSI hold below 10 ns");
                if($time-last_rise<min_mosi_hold)min_mosi_hold=$time-last_rise;
            end
        end
        last_mosi_change=$time;
    end
    always @(dc) begin
        if(!reset && !ncs) begin
            if(sck || bit_count!=0)$fatal(1,"DC changed inside a byte");
            if(last_rise!=0) begin
                if($time-last_rise<5)$fatal(1,"DC hold below 5 ns");
                if($time-last_rise<min_dc_hold)min_dc_hold=$time-last_rise;
            end
        end
        last_dc_change=$time;
    end
    always @(negedge ncs) if(!reset && !recovering) begin
        if(sck || bit_count!=0)$fatal(1,"CS asserted with active SCK/partial byte");
        cs_asserted=$time;
        last_rise=0;
        last_fall=0;
        expect_release=0;
        transactions=transactions+1;
    end
    always @(posedge ncs) if(!reset && !recovering && transactions!=0) begin
        if(sck || bit_count!=0 || !expect_release)
            $fatal(1,"CS released before a complete last token");
        if(last_rise==0 || $time-last_rise<15)$fatal(1,"CS hold below 15 ns");
        if($time-last_rise<min_cs_hold)min_cs_hold=$time-last_rise;
        completed=completed+1;
    end
    always @(negedge sck) if(!reset && last_rise!=0) begin
        if(ncs)$fatal(1,"SCK fell with CS inactive");
        if($time-last_rise!=10)$fatal(1,"SCK high width != 10 ns");
        last_fall=$time;
    end
    always @(posedge sck) if(!reset) begin
        if(recovering)$fatal(1,"Stale SCK edge during reset recovery");
        if(ncs)$fatal(1,"SCK rose with CS inactive");
        if(expect_release)$fatal(1,"Extra SCK after last token");
        if(last_rise==0) begin
            if($time-cs_asserted<15)$fatal(1,"CS setup below 15 ns");
            if($time-cs_asserted<min_cs_setup)min_cs_setup=$time-cs_asserted;
        end else begin
            if($time-last_fall<10)$fatal(1,"SCK low width below 10 ns");
            if(continuous) begin
                if($time-last_rise!=20)$fatal(1,"Gap in continuous 50 MHz SPI");
                continuous_samples=continuous_samples+1;
            end
            if($time-last_rise>20)paused_samples=paused_samples+1;
        end
        if($time-last_mosi_change<10)$fatal(1,"MOSI setup below 10 ns");
        if($time-last_mosi_change<min_mosi_setup)min_mosi_setup=$time-last_mosi_change;
        if($time-last_dc_change<5)$fatal(1,"DC setup below 5 ns");
        if($time-last_dc_change<min_dc_setup)min_dc_setup=$time-last_dc_change;
        last_rise=$time;
        if(bit_count==0)byte_dc=dc;
        else if(dc!==byte_dc)$fatal(1,"DC differs within byte");
        received={received[6:0],mosi};
        bit_count=bit_count+1;
        if(bit_count==8) begin
            if(queue_head>=queue_tail)$fatal(1,"Unaccepted byte on SPI");
            if(received!==expected_data[queue_head] || byte_dc!==expected_dc[queue_head])
                $fatal(1,"Token %0d: got %02x DC=%b expected %02x DC=%b",queue_head,
                    received,byte_dc,expected_data[queue_head],expected_dc[queue_head]);
            expect_release=expected_last[queue_head];
            queue_head=queue_head+1;
            decoded=decoded+1;
            bit_count=0;
        end
    end

    task send_token;
        input [7:0] value;
        input token_dc,token_last;
        begin
            @(negedge clk);
            valid=1;data=value;data_dc=token_dc;last=token_last;
            @(posedge clk);
            while(!ready)@(posedge clk);
            @(negedge clk);valid=0;
        end
    endtask
    task wait_idle;
        begin
            @(negedge clk);
            while(!idle)@(negedge clk);
            if(queue_head!=queue_tail)$fatal(1,"idle with queued tokens");
        end
    endtask
    task reset_stream;
        input short_pulse;
        begin
            #3;recovering=1;reset=1;valid=0;
            #1;
            if(sck || ready || idle)$fatal(1,"Reset did not immediately stop SCK/handshakes");
            if(short_pulse)begin
                #2;reset=0;
            end else begin
                repeat(3)@(negedge clk);
                if(!ncs)$fatal(1,"CS did not release within three reset clocks");
                @(negedge clk);reset=0;
            end
            repeat(2)@(negedge clk);
            if(ready || idle)$fatal(1,"Reset recovery ignored CS pipeline drain");
            @(negedge clk);
            if(!ncs || sck)$fatal(1,"CS pipeline did not drain after reset");
            repeat(3)@(negedge clk);
            if(!idle || !ncs || sck)$fatal(1,"Stale transaction after reset flush");
            recovering=0;
        end
    endtask

    integer i,j;
    initial begin
        #1;
        repeat(4)@(negedge clk);
        reset=0;
        repeat(3)@(negedge clk);
        // Continuous traffic varies every DC byte and exercises every byte
        // value, with sustained throughput and physical rising-edge spacing.
        continuous=1;
        @(negedge clk);valid=1;
        for(i=0;i<1024;i=i+1)begin
            data=(i*73+8'h55)&255;data_dc=i[0];last=i==1023;
            @(posedge clk);
            while(!ready)@(posedge clk);
            @(negedge clk);
        end
        valid=0;
        wait_idle;
        continuous=0;
        if(continuous_accepts!=1024 || continuous_samples!=8191)
            $fatal(1,"Continuous throughput coverage incomplete");
        // Keep CS selected across an arbitrarily long producer pause.
        send_token(8'h2a,0,0);
        repeat(30)@(negedge clk);
        if(ncs || sck || idle || !ready)$fatal(1,"Pause did not retain CS with low SCK");
        send_token(8'h00,1,0);
        repeat(21)@(negedge clk);
        send_token(8'hff,0,1);
        wait_idle;
        // Back-to-back independent transactions with alternating DC.
        for(i=0;i<16;i=i+1)begin
            send_token(i*17,i[0],1);
            wait_idle;
        end
        // Reset at every pipeline/bit position, including queued unobserved
        // bits and a partly decoded byte. Follow every abort with a clean byte.
        for(i=0;i<12;i=i+1)begin
            send_token(8'h96,i[0],0);
            for(j=0;j<i;j=j+1)@(negedge clk);
            reset_stream(i[0]);
            send_token(8'h69,!i[0],1);
            wait_idle;
        end
        // Flush immediately after acceptance, before ODDRC can assert CS.
        send_token(8'h55,0,1);
        reset_stream(1'b1);
        send_token(8'ha5,1,1);
        wait_idle;
        if(completed!=31 || transactions<completed || paused_samples<2 || reset_aborts==0)
            $fatal(1,"Scenario coverage incomplete completed=%0d transactions=%0d pauses=%0d aborts=%0d",
                completed,transactions,paused_samples,reset_aborts);
        $display("PASS lcd_spi_stream: accepted=%0d decoded=%0d transactions=%0d completed=%0d aborted=%0d",
            accepted,decoded,transactions,completed,reset_aborts);
        $display("PASS 50 MHz continuous stream: %0d tokens / 8 clocks, %0d consecutive 20 ns sample intervals",
            continuous_accepts,continuous_samples);
        $display("PASS minimum pin timing ns: MOSI setup/hold=%0d/%0d DC setup/hold=%0d/%0d CS setup/hold=%0d/%0d",
            min_mosi_setup,min_mosi_hold,min_dc_setup,min_dc_hold,min_cs_setup,min_cs_hold);
        $finish;
    end
    initial begin
        #1000000;$fatal(1,"Timeout");
    end
endmodule
