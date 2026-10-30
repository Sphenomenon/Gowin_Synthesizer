`timescale 1ns/1ps
module tb_workstation_audio_clock_service #(
    parameter bit RESERVE_ZERO_EPOCH=0,
    parameter [31:0] INITIAL_STREAM_EPOCH=RESERVE_ZERO_EPOCH ? 32'd1 : 32'd0
);
    function automatic [31:0] epoch_at(input integer transitions);
        reg [63:0] ordinal;
        begin
            ordinal={32'd0,INITIAL_STREAM_EPOCH}+64'(transitions);
            if(RESERVE_ZERO_EPOCH)epoch_at=32'((ordinal-1)%64'hffffffff+1);
            else epoch_at=ordinal[31:0];
        end
    endfunction

    reg clk=0,pclk=0,pclk_run=1;
    always #10 clk=~clk;
    real source_phase;
    initial begin
        if(!$value$plusargs("BUS_PHASE=%f",source_phase))source_phase=3.7;
        #(source_phase);
        forever begin #13.7;if(pclk_run)pclk=~pclk;end
    end
    reg board_reset_n=0,bus_reset_n=0;
    reg psel=0,penable=0,pwrite=0;
    reg [11:0] paddr=0;
    reg [31:0] pwdata=0;
    reg [3:0] pstrb=0;
    wire pready,pslverr;
    wire [31:0] prdata;
    wire command_reset_n,command_valid,command_ready,command_write;
    wire [11:0] command_address;
    wire [31:0] command_data,response_data;
    wire [3:0] command_strobes;
    wire response_error;
    reg hold_valid=0;
    gw138k_apb_cdc bridge(.reset_n(bus_reset_n),.pclk,.audio_clk(clk),
        .psel,.penable,.pwrite,.paddr,.pwdata,.pstrb,.pready,.pslverr,.prdata,
        .command_reset_n,.command_valid,.command_ready,.command_write,
        .command_address,.command_data,.command_strobes,.response_data,.response_error);
    reg permit=1,dsp_fault=0,frame_quiet=1;
    reg [1:0] source_qualified=3;
    wire request,request_rate,recover;
    wire core_ready,core_busy,core_fault,core_accepted,core_applied,core_rejected,core_failed;
    wire [2:0] reject_code;
    wire [3:0] fault_code;
    wire actual_rate,actual_valid;
    wire [31:0] actual_epoch;
    reg policy_rejected=0;
    reg suppress_accepted=0,suppress_applied=0,inject_applied=0,corrupt_epoch=0;
    // Exact runtime request permission gate; DSP failure stays external and
    // cannot be cleared by resetting this command owner.
    always @(posedge clk or negedge board_reset_n)
        if(!board_reset_n)policy_rejected<=0;
        else policy_rejected<=request && !permit;
    workstation_sample_rate_switch #(.TIMEOUT_CYCLES(96),
        .RESERVE_ZERO_EPOCH(RESERVE_ZERO_EPOCH),.INITIAL_STREAM_EPOCH(INITIAL_STREAM_EPOCH)) core(
        .clk_i(clk),.rst_ni(board_reset_n),
        .request_i(request && permit && !dsp_fault),.request_44k1_i(request_rate),.recover_i(recover),
        .source_qualified_i(source_qualified),.frame_quiescent_i(frame_quiet),
        .selected_clock_stopped_low_i(1'b1),.selected_clock_qualified_i(1'b1),
        .prefill_ready_i(1'b1),.output_running_i(1'b1),
        .request_ready_o(core_ready),.busy_o(core_busy),.fault_o(core_fault),
        .accepted_o(core_accepted),.applied_o(core_applied),.rejected_o(core_rejected),.failed_o(core_failed),
        .reject_code_o(reject_code),.fault_code_o(fault_code),
        .quiesce_o(),.dac_mute_o(),.stream_flush_o(),.audio_reset_no(),
        .clock_monitor_restart_o(),.clock_select_o(),.active_44k1_o(actual_rate),
        .active_valid_o(actual_valid),.stream_epoch_o(actual_epoch),.staged_44k1_o(),.staged_epoch_o());
    workstation_audio_clock_service #(.ACCEPT_TIMEOUT_CYCLES(16),.RESULT_TIMEOUT_CYCLES(192),
        .RESERVE_ZERO_EPOCH(RESERVE_ZERO_EPOCH)) dut(
        .clk_i(clk),.reset_ni(command_reset_n),
        .command_valid_i(command_valid || hold_valid),.command_write_i(command_write),
        .command_address_i(command_address),.command_data_i(command_data),.command_strobes_i(command_strobes),
        .command_ready_o(command_ready),.response_data_o(response_data),.response_error_o(response_error),
        .switch_permit_i(permit),.core_request_ready_i(core_ready),.core_busy_i(core_busy),
        .core_fault_i(core_fault || dsp_fault),.core_dsp_fault_i(dsp_fault),
        .core_accepted_i(core_accepted && !suppress_accepted),
        .core_applied_i((core_applied && !suppress_applied) || inject_applied),
        .core_rejected_i(core_rejected),.core_policy_rejected_i(policy_rejected),.core_failed_i(core_failed),
        .core_reject_code_i(reject_code),.core_fault_code_i(fault_code),
        .core_active_44k1_i(actual_rate),.core_active_valid_i(actual_valid && !dsp_fault),
        .core_stream_epoch_i(actual_epoch ^ {31'b0,corrupt_epoch}),.core_source_qualified_i(source_qualified),
        .request_o(request),.request_44k1_o(request_rate),.recover_o(recover));
    integer bus_transactions=0,max_bus_cycles=0,request_pulses=0,recover_pulses=0;
    integer hardware_accepts=0,hardware_applies=0,hardware_failures=0;
    integer held_checks=0,busy_rejects=0,late_rejects=0,recover_accepts=0;
    integer cpu_reset_during_hardware=0,ignored_startup=0,timeout_cases=0;
    integer context_mismatch_cases=0,dsp_fault_rejects=0,source_bus_stop_checks=0,snapshot_checks=0;
    reg previous_request=0,previous_recover=0;
    reg [48:0] previous_word=0;
    always @(posedge clk)begin
        if(board_reset_n)begin
            if(request)request_pulses=request_pulses+1;
            if(recover)recover_pulses=recover_pulses+1;
            if(core_accepted)hardware_accepts=hardware_accepts+1;
            if(core_applied)hardware_applies=hardware_applies+1;
            if(core_failed)hardware_failures=hardware_failures+1;
            if(request && previous_request)$fatal(1,"request held for more than one edge");
            if(recover && previous_recover)$fatal(1,"recover held for more than one edge");
        end
        previous_request=request;previous_recover=recover;
        if(command_valid && {command_write,command_strobes,command_address,command_data}!==previous_word)
            $fatal(1,"real APB mailbox did not provide the required local predecode edge");
        previous_word={command_write,command_strobes,command_address,command_data};
    end
    task automatic apb(input bit wr,input [11:0] address,input [31:0] data,input [3:0] strobes,
                       input bit expected_error,output [31:0] returned);
        integer cycles;
        begin
            @(negedge pclk);psel=1;penable=0;pwrite=wr;paddr=address;pwdata=data;pstrb=strobes;
            @(negedge pclk);penable=1;cycles=0;
            begin:wait_bus
                forever begin
                    @(posedge pclk);#0.1;cycles=cycles+1;
                    if(pready)disable wait_bus;
                    if(cycles>30)$fatal(1,"APB waited for audio completion addr=%h",address);
                end
            end
            returned=prdata;
            if(pslverr!==expected_error)$fatal(1,"APB error addr=%h wr=%b got=%b expected=%b value=%h",address,wr,pslverr,expected_error,prdata);
            bus_transactions=bus_transactions+1;
            if(cycles>max_bus_cycles)max_bus_cycles=cycles;
            @(negedge pclk);psel=0;penable=0;pwrite=0;pstrb=0;
        end
    endtask
    task automatic read_eq(input [11:0] address,input [31:0] expected);
        reg [31:0] data;
        begin apb(0,address,0,0,0,data);if(data!==expected)$fatal(1,"read addr=%h got=%h expected=%h",address,data,expected);end
    endtask
    task automatic submit(input [31:0] operation_value,input [31:0] id);
        reg [31:0] data;
        begin apb(1,12'h008,operation_value,4'hf,0,data);if(data!==id)$fatal(1,"command-id got=%d expected=%d",data,id);end
    endtask
    task automatic result_eq(input [31:0] code,input [31:0] id);
        reg [31:0] data;
        integer attempts;
        begin
            attempts=0;
            begin:wait_result
                forever begin
                    apb(0,12'h018,0,0,0,data);
                    if(data==id)disable wait_result;
                    attempts=attempts+1;
                    if(attempts>20)$fatal(1,"result never became terminal id=%d phase=%d",id,dut.phase);
                end
            end
            read_eq(12'h01c,code);
            if(dut.phase!=0)$fatal(1,"terminal command remains pending");
        end
    endtask
    task automatic actual_eq(input bit rate,input [31:0] epoch,input bit valid);
        reg [31:0] data;
        begin
            apb(0,12'h02c,0,0,0,data);
            if(data[1:0]!=={valid,rate})$fatal(1,"actual status got=%h expected rate=%b valid=%b",data,rate,valid);
            read_eq(12'h030,epoch_at(int'(epoch)));
        end
    endtask
    task automatic cpu_reset;
        begin
            @(negedge pclk);bus_reset_n=0;hold_valid=0;
            repeat(6)@(negedge pclk);
            bus_reset_n=1;
            repeat(12)@(posedge clk);
        end
    endtask
    task automatic common_reset;
        begin
            @(negedge pclk);board_reset_n=0;bus_reset_n=0;hold_valid=0;
            permit=1;dsp_fault=0;frame_quiet=1;source_qualified=3;
            suppress_accepted=0;suppress_applied=0;inject_applied=0;corrupt_epoch=0;
            repeat(6)@(negedge pclk);
            board_reset_n=1;bus_reset_n=1;
            wait(core_ready);repeat(12)@(posedge clk);
        end
    endtask
    reg [31:0] returned;
    integer i,requests_before,applies_before,accepts_before;
    initial begin
        common_reset();
        read_eq(12'h000,32'h434c4b01);
        read_eq(12'h004,32'h00010007 | (32'(RESERVE_ZERO_EPOCH)<<3));
        for(i=0;i<24;i=i+1)if(i!=2)apb(0,12'(i*4),0,0,0,returned);
        requests_before=request_pulses;
        apb(1,12'h000,0,15,1,returned);
        apb(1,12'h02c,0,15,1,returned);
        apb(1,12'h009,0,15,1,returned);
        apb(1,12'h108,0,15,1,returned);
        apb(0,12'h060,0,0,1,returned);
        apb(0,12'h008,0,0,1,returned);
        apb(1,12'h008,3,15,1,returned);
        apb(1,12'h008,32'hffffffff,15,1,returned);
        apb(1,12'h008,1,0,1,returned);
        apb(1,12'h008,1,7,1,returned);
        permit=0;apb(1,12'h008,1,15,1,returned);read_eq(12'h04c,8);permit=1;
        apb(1,12'h008,2,15,1,returned);read_eq(12'h04c,12);
        source_qualified=1;apb(1,12'h008,1,15,1,returned);read_eq(12'h04c,13);source_qualified=3;
        if(request_pulses!=requests_before)$fatal(1,"bad APB command produced hardware request");
        @(negedge clk);inject_applied=1;
        @(negedge clk);inject_applied=0;
        read_eq(12'h01c,0);read_eq(12'h03c,0);read_eq(12'h048,1);ignored_startup=1;

        // A held command_valid from the real mailbox produces one submission.
        frame_quiet=0;requests_before=request_pulses;
        fork
            submit(1,1);
            begin
                wait(command_valid);@(negedge clk);hold_valid=1;
                repeat(20)@(negedge clk);
                hold_valid=0;held_checks=held_checks+1;
            end
        join
        read_eq(12'h034,1);
        if(request_pulses!=requests_before+1)$fatal(1,"held valid repeated submission");
        if(!core_busy || dut.phase!=3)$fatal(1,"APB admission waited for hardware transaction");
        apb(1,12'h008,0,15,1,returned);read_eq(12'h04c,5);busy_rejects=busy_rejects+1;
        apb(0,12'h02c,0,0,0,returned);
        if(returned[1:0]!=2'b10)$fatal(1,"snapshot did not capture old committed rate");
        frame_quiet=1;wait(core_ready);read_eq(12'h030,epoch_at(0));snapshot_checks=snapshot_checks+1;
        result_eq(1,1);actual_eq(1,1,1);
        submit(1,2);result_eq(1,2);actual_eq(1,1,1); // same-rate accepted+applied on one edge

        // Admission succeeds, but registered request is rejected at core input.
        fork
            submit(0,3);
            begin wait(request);@(negedge clk);source_qualified=2;end
        join
        result_eq(2,3);read_eq(12'h020,32'h0202); // rejected + reject_code=2
        source_qualified=3;late_rejects=late_rejects+1;
        fork
            submit(0,4);
            begin wait(request);@(negedge clk);permit=0;end
        join
        result_eq(3,4);permit=1;late_rejects=late_rejects+1;

        // Real QUIESCE timeout then real FAULT->STOP_START recover. Recover
        // deliberately has no core accepted pulse; busy transition is evidence.
        frame_quiet=0;submit(0,5);result_eq(4,5);
        if(!core_fault)$fatal(1,"real switch did not enter terminal FAULT");
        frame_quiet=1;accepts_before=hardware_accepts;
        submit(2,6);result_eq(1,6);actual_eq(1,2,1);
        if(hardware_accepts!=accepts_before)$fatal(1,"fixture unexpectedly fabricated recover accepted");
        read_eq(12'h05c,6);read_eq(12'h034,6);read_eq(12'h038,4);
        read_eq(12'h03c,3);read_eq(12'h040,3);read_eq(12'h044,14);recover_accepts=recover_accepts+1;

        // CPU reset cannot clear or recover an external sticky DSP failure.
        dsp_fault=1;requests_before=request_pulses;
        apb(1,12'h008,0,15,1,returned);read_eq(12'h04c,10);
        apb(1,12'h008,2,15,1,returned);read_eq(12'h04c,10);
        cpu_reset();
        apb(1,12'h008,2,15,1,returned);read_eq(12'h04c,10);
        apb(0,12'h02c,0,0,0,returned);
        if(!returned[5] || returned[1])$fatal(1,"CPU reset hid sticky DSP fault");
        if(request_pulses!=requests_before)$fatal(1,"DSP fault admitted a request");
        dsp_fault_rejects=3;

        common_reset();
        // An accepted command whose ACK is lost terminates locally; the actual
        // hardware is not canceled. Late result cannot become APPLIED or attach
        // to a newer command, which is rejected until observer reset.
        suppress_accepted=1;frame_quiet=0;
        submit(1,1);result_eq(5,1);timeout_cases=timeout_cases+1;
        if(!core_busy)$fatal(1,"missing-ACK test did not leave real hardware in flight");
        apb(1,12'h008,0,15,1,returned);read_eq(12'h04c,7);
        frame_quiet=1;wait(core_applied);repeat(4)@(posedge clk);
        read_eq(12'h01c,5);read_eq(12'h03c,0);actual_eq(1,1,1);
        suppress_accepted=0;

        // Reset APB/CPU owner after the real core has accepted a command. No
        // board reset, stream reset, cancellation or replay is connected here.
        cpu_reset();frame_quiet=0;submit(0,1);wait(core_busy);
        applies_before=hardware_applies;cpu_reset();
        if(!core_busy || actual_epoch!=epoch_at(1) || actual_rate!=1)$fatal(1,"CPU reset altered hardware transaction");
        apb(1,12'h008,1,15,1,returned);read_eq(12'h04c,6);
        frame_quiet=1;wait(core_ready);repeat(8)@(posedge clk);
        if(hardware_applies!=applies_before+1)$fatal(1,"hardware did not continue across CPU reset");
        actual_eq(0,2,1);read_eq(12'h010,0);read_eq(12'h018,0);read_eq(12'h01c,0);
        cpu_reset_during_hardware=cpu_reset_during_hardware+1;
        submit(1,1);result_eq(1,1);actual_eq(1,3,1);

        suppress_applied=1;submit(0,2);result_eq(6,2);timeout_cases=timeout_cases+1;
        actual_eq(0,4,1);apb(1,12'h008,1,15,1,returned);read_eq(12'h04c,7);
        suppress_applied=0;
        cpu_reset();
        fork
            submit(1,1);
            begin wait(request);@(negedge clk);corrupt_epoch=1;end
        join
        result_eq(7,1);corrupt_epoch=0;context_mismatch_cases=context_mismatch_cases+1;
        apb(1,12'h008,0,15,1,returned);read_eq(12'h04c,7);

        cpu_reset();frame_quiet=0;submit(0,1);wait(core_busy);
        @(negedge pclk);pclk_run=0;frame_quiet=1;
        wait(core_ready);repeat(12)@(posedge clk);
        if(dut.result_code!=1 || actual_epoch!=epoch_at(6))$fatal(1,"stopped source bus blocked hardware result");
        pclk_run=1;actual_eq(0,6,1);result_eq(1,1);source_bus_stop_checks=source_bus_stop_checks+1;
        $display("PASS audio_clock_service: bus_transactions=%0d max_bus_cycles=%0d request_pulses=%0d recover_pulses=%0d hardware_accepts=%0d hardware_applies=%0d hardware_failures=%0d held_checks=%0d busy_rejects=%0d late_rejects=%0d recover_accepts=%0d ignored_startup=%0d timeout_cases=%0d cpu_reset_during_hardware=%0d context_mismatch_cases=%0d dsp_fault_rejects=%0d source_bus_stop_checks=%0d snapshot_checks=%0d",
            bus_transactions,max_bus_cycles,request_pulses,recover_pulses,hardware_accepts,hardware_applies,hardware_failures,
            held_checks,busy_rejects,late_rejects,recover_accepts,ignored_startup,timeout_cases,cpu_reset_during_hardware,
            context_mismatch_cases,dsp_fault_rejects,source_bus_stop_checks,snapshot_checks);
        $finish;
    end
    initial begin #3000000;$fatal(1,"clock service regression deadline");end
endmodule
