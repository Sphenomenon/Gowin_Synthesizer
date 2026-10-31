`timescale 1ns/1ps
// Tests the actual prepared F806 bridge; audio processing remains independent.
module tb_ae350_pcm_apb_reset;
    reg pclk=0,audio_clk=0,p_run=1,a_run=1,resetn=1;
    always #10 if(p_run)pclk=~pclk;
    always #6.510417 if(a_run)audio_clk=~audio_clk;
    reg psel=0,penable=0,pwrite=0,command_ready=0;
    reg [11:0] paddr=0;
    reg [31:0] pwdata=0;
    reg [3:0] pstrb=0;
    wire pready,pslverr,command_reset_n,command_valid,command_write,response_error;
    wire [11:0] command_address;
    wire [31:0] prdata,command_data,response_data;
    wire [3:0] command_strobes;
    assign response_data=command_data ^ {20'hcda35,command_address};
    assign response_error=command_address[2];
    gw138k_apb_cdc dut(
        .reset_n(resetn),.pclk(pclk),.audio_clk(audio_clk),.psel(psel),.penable(penable),
        .pwrite(pwrite),.paddr(paddr),.pwdata(pwdata),.pstrb(pstrb),
        .pready(pready),.pslverr(pslverr),.prdata(prdata),.command_reset_n(command_reset_n),
        .command_valid(command_valid),.command_ready(command_ready),.command_write(command_write),
        .command_address(command_address),.command_data(command_data),.command_strobes(command_strobes),
        .response_data(response_data),.response_error(response_error));
    integer accepted=0,checks=0;
    reg expect_accept=0;
    reg [48:0] expected_request=0;
    task check(input condition,input [767:0] label);
        begin checks=checks+1;if(!condition)$fatal(1,"FAIL APB CDC %0s",label);end
    endtask
    always @(posedge audio_clk)if(command_valid && command_ready)begin
        check(expect_accept,"unexpected or duplicate command acceptance");
        check({command_write,command_strobes,command_address,command_data}===expected_request,
            "held request mapping or stability");
        expect_accept=0;accepted=accepted+1;
    end
    task cycles(input integer count);repeat(count)@(negedge pclk);endtask
    task idle;
        begin @(negedge pclk);psel=0;penable=0;pwrite=0;cycles(2);end
    endtask
    task launch(input [11:0] address,input [31:0] value,input bit will_accept);
        begin
            @(negedge pclk);psel=1;penable=0;pwrite=1;paddr=address;pwdata=value;pstrb=4'hb;
            expected_request={1'b1,4'hb,address,value};expect_accept=will_accept;
            @(negedge pclk);penable=1;
        end
    endtask
    task complete(input [11:0] address,input [31:0] value);
        integer timeout;
        begin
            timeout=0;while(!pready && timeout<60)begin cycles(1);timeout=timeout+1;end
            check(pready,"bounded response after backpressure release");
            check(prdata===(value^{20'hcda35,address}) && pslverr===address[2],"exact held response data and error");
            idle();
        end
    endtask
    task assert_reset;
        begin
            #0.77;resetn=0;
            #0.004;check(!pready && !command_valid && !command_reset_n,"asynchronous common reset revokes both sides");
            expect_accept=0;psel=0;penable=0;
        end
    endtask
    task restart;
        begin
            cycles(4);resetn=1;cycles(6);
            repeat(6)begin cycles(1);check(!pready && !command_valid,"no stale response or command after reset");end
        end
    endtask
    initial begin
        integer before_count;
        #1;assert_reset();restart();command_ready=1;
        launch('h124,32'h13579bdf,1);complete('h124,32'h13579bdf);
        // Destination service stalls independently of the APB clock.
        command_ready=0;launch('h238,32'hfedcba98,1);cycles(10);
        check(command_valid && !pready && accepted==1,"service stall keeps pending request without response");
        command_ready=1;complete('h238,32'hfedcba98);
        // Cancel a request before any compute edge can observe its token.
        @(negedge audio_clk);a_run=0;before_count=accepted;
        launch('h04c,32'h01234567,0);cycles(7);check(!pready && accepted==before_count,"stopped compute domain cannot accept");
        assert_reset();a_run=1;restart();
        launch('h318,32'h11223344,1);complete('h318,32'h11223344);
        // Reset after real command acceptance, before APB ACK can settle.
        launch('h080,32'ha55a3cc3,1);wait(accepted==4);#0.1;
        check(!pready,"accepted response remains behind ACK synchronizer");
        assert_reset();restart();
        launch('h184,32'hdecafbad,1);complete('h184,32'hdecafbad);
        // A stopped producer clock cannot defer asynchronous cancellation.
        command_ready=0;launch('h268,32'h88776655,0);wait(command_valid);
        @(negedge pclk);p_run=0;assert_reset();#32;p_run=1;restart();
        command_ready=1;launch('h3bc,32'h5599cc33,1);complete('h3bc,32'h5599cc33);
        check(accepted==6 && !expect_accept,"exact command count across all cancellation phases");
        $display("PASS APB CDC reset checks=%0d accepted=%0d pre_capture=1 post_accept=1 stopped_producer=1 stopped_compute=1",checks,accepted);
        $finish;
    end
    initial begin #200000;$fatal(1,"FAIL APB CDC watchdog");end
endmodule
