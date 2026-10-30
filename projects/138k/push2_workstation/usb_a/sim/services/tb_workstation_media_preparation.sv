`timescale 1ns/1ps
module tb_workstation_media_preparation;
    reg clk=0,reset_n=0,request=0,hold=0;
    always #10 clk=~clk;
    reg rr=1,rd=0,rf=0,br=1,bd=0,bf=0;
    reg [3:0] rc=0,bc=0;
    wire ready,done,failed,rreq,rhold,breq,bhold;
    wire [3:0] code,ble_code;
    workstation_media_preparation #(.ENABLE_BLE(1)) dut(
        .clk_i(clk),.reset_ni(reset_n),.request_i(request),.hold_i(hold),
        .ready_o(ready),.done_o(done),.failed_o(failed),.failure_code_o(code),
        .runtime_request_o(rreq),.runtime_hold_o(rhold),.runtime_ready_i(rr),
        .runtime_done_i(rd),.runtime_failed_i(rf),.runtime_failure_code_i(rc),
        .ble_request_o(breq),.ble_hold_o(bhold),.ble_ready_i(br),.ble_done_i(bd),
        .ble_failed_i(bf),.ble_failure_code_i(bc),.ble_failure_code_o(ble_code));
    wire legacy_ready,legacy_done,legacy_failed,legacy_req,legacy_hold,legacy_ble_req,legacy_ble_hold;
    wire [3:0] legacy_code,legacy_ble_code;
    workstation_media_preparation legacy(
        .clk_i(clk),.reset_ni(reset_n),.request_i(request),.hold_i(hold),
        .ready_o(legacy_ready),.done_o(legacy_done),.failed_o(legacy_failed),.failure_code_o(legacy_code),
        .runtime_request_o(legacy_req),.runtime_hold_o(legacy_hold),.runtime_ready_i(rr),
        .runtime_done_i(rd),.runtime_failed_i(rf),.runtime_failure_code_i(rc),
        .ble_request_o(legacy_ble_req),.ble_hold_o(legacy_ble_hold),.ble_ready_i(br),.ble_done_i(bd),
        .ble_failed_i(bf),.ble_failure_code_i(bc),.ble_failure_code_o(legacy_ble_code));
    integer requests=0,completions=0,failures=0,checks=0,cases=0;
    reg previous_req=0,previous_done=0,previous_failed=0;
    always @(posedge clk)if(reset_n)begin
        if(rreq!==breq || rhold!==bhold)$fatal(1,"backend request/hold mismatch");
        if(rreq)begin
            if(previous_req || !rhold)$fatal(1,"duplicated or unfenced request");
            requests=requests+1;
        end
        if(done)begin if(previous_done || failed)$fatal(1,"duplicate/conflicting completion");completions=completions+1;end
        if(failed)begin if(previous_failed)$fatal(1,"duplicate failure");failures=failures+1;end
        previous_req=rreq;previous_done=done;previous_failed=failed;
    end
    always @(negedge clk)begin
        if({legacy_ready,legacy_done,legacy_failed,legacy_req,legacy_hold,legacy_code}!=={rr,rd,rf,request,hold,rc} ||
           {legacy_ble_req,legacy_ble_hold,legacy_ble_code}!==6'd0)$fatal(1,"default pass-through changed");
        checks=checks+1;
    end
    task step(input integer n);begin repeat(n)@(negedge clk);#0.001;end endtask
    task launch;
        begin
            if(!ready)$fatal(1,"backend not rearmed");
            request=1;hold=1;step(1);request=0;
            if(!rreq || !breq || !rhold || ready)$fatal(1,"request not launched atomically");
            rr=0;br=0;step(1);
            if(done || failed)$fatal(1,"old completion satisfied new request");
        end
    endtask
    task release_backends;
        begin
            rd=0;rf=0;bd=0;bf=0;step(4);
            if(!rhold || ready || done || failed)$fatal(1,"caller hold was released before clock completion");
            hold=0;step(3);
            if(rhold || ready)$fatal(1,"release/readiness ignored actual backend drain");
            rr=1;step(2);if(ready)$fatal(1,"one backend readiness invented admission");
            br=1;step(3);if(!ready)$fatal(1,"actual backend readiness did not rearm");
            cases=cases+1;
        end
    endtask
    initial begin
        step(3);reset_n=1;step(2);
        launch();rd=1;step(1);
        if(done || failed)$fatal(1,"premature aggregate completion");
        rd=0;step(12);if(done || failed || !rhold)$fatal(1,"slow BLE lost hold");
        bd=1;step(1);if(!done || failed)$fatal(1,"ordered success missing");release_backends();
        launch();bd=1;step(1);bd=0;step(7);
        if(done || failed)$fatal(1,"premature aggregate completion");
        rd=1;step(1);if(!done || failed)$fatal(1,"reverse success missing");release_backends();
        launch();rd=1;bd=1;step(1);if(!done || failed)$fatal(1,"simultaneous success missing");release_backends();
        launch();bc=6;bf=1;step(1);bf=0;step(5);
        if(done || failed)$fatal(1,"failure abandoned still-running runtime");
        rd=1;step(1);if(done || !failed || code!=10 || ble_code!=6)$fatal(1,"BLE failure identity lost");release_backends();
        launch();rc=8;rf=1;step(1);rf=0;step(5);
        if(done || failed)$fatal(1,"failure abandoned still-running BLE");
        bd=1;step(1);if(done || !failed || code!=8)$fatal(1,"runtime failure identity lost");release_backends();
        launch();rc=9;bc=3;rf=1;bf=1;step(1);
        if(done || !failed || code!=9 || ble_code!=3)$fatal(1,"dual failure precedence lost");release_backends();
        // CPU reset drops the caller hold. Neither slow backend has finished.
        launch();hold=0;step(20);
        if(!rhold || ready || done || failed)$fatal(1,"lost caller released pending work");
        rd=1;step(1);rd=0;step(8);if(!rhold || done || failed)$fatal(1,"lost caller bypassed BLE");
        bd=1;step(1);if(!done || failed)$fatal(1,"orphan cleanup did not terminate");bd=0;
        step(3);if(rhold || ready)$fatal(1,"orphan rearmed before backends");rr=1;br=1;step(4);cases=cases+1;
        // A terminal pulse outside a request cannot become a later result.
        rd=1;bd=1;step(1);rd=0;bd=0;step(2);if(done || failed)$fatal(1,"unowned result was accepted");
        // Old results overlap the request delivery edge, before either
        // registered owner could have answered this request.
        rd=1;bd=1;launch();rd=0;bd=0;
        step(4);if(done || failed)$fatal(1,"old completion satisfied new request");
        rd=1;bd=1;step(1);if(!done)$fatal(1,"fresh completion missing");release_backends();
        br=0;request=1;hold=1;step(1);request=0;
        if(!failed || code!=11 || rreq || breq || rhold)$fatal(1,"unready admission silently disappeared");
        hold=0;br=1;step(3);cases=cases+1;
        if(requests!=8 || completions!=5 || failures!=4 || cases!=9 || checks<150)$fatal(1,"coverage incomplete");
        $display("PASS media_preparation: cases=%0d requests=%0d completions=%0d failures=%0d default_checks=%0d",cases,requests,completions,failures,checks);
        $finish;
    end
    initial begin #100000;$fatal(1,"media preparation timeout");end
endmodule
