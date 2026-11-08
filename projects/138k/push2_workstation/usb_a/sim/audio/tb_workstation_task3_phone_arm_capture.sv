`timescale 1ns/1ps
module tb_workstation_task3_phone_arm_capture;
    reg clk=0;always #5 clk=~clk;
    reg reset_n=0,link=1,panic=0,arm=0,cancel=0,ack=0;
    reg [31:0] boot=11,session=22,generation=1;
    wire ready,rejected,accepted,tx,armed;
    wire [31:0] actual_boot,actual_session,actual_generation;
    workstation_task3_phone_command_proxy #(.CAPTURE_ARM(1),.ROUND_TRIP_TIMEOUT_CYCLES(16)) dut(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),
        .arm_valid_i(arm),.arm_ready_o(ready),.arm_boot_i(boot),.arm_session_i(session),.arm_generation_i(generation),
        .arm_accepted_o(accepted),.arm_rejected_o(rejected),.arm_tx_valid_o(tx),.arm_tx_ready_i(1'b1),
        .arm_result_accepted_i(ack),.arm_result_rejected_i(1'b0),
        .boot_o(actual_boot),.session_o(actual_session),.generation_o(actual_generation),
        .cancel_tx_ready_i(1'b1),.cancel_valid_i(cancel),.cancel_session_i(session),.cancel_generation_i(generation),
        .cpu_command_valid_i(1'b0),.cpu_command_target_i(1'b0),.cpu_command_write_i(1'b0),
        .cpu_command_address_i(12'd0),.cpu_command_data_i(32'd0),.cpu_command_strobes_i(4'd0),
        .request_ready_i(1'b1),.response_valid_i(1'b0),.response_boot_i(32'd0),.response_session_i(32'd0),
        .response_generation_i(32'd0),.response_sequence_i(32'd0),.response_data_i(32'd0),.response_error_i(1'b0),.armed_o(armed));
    integer checks=0;
    task automatic restart;
        begin
            reset_n=0;arm=0;link=1;panic=0;cancel=0;ack=0;boot=11;session=22;generation=1;
            repeat(3)@(negedge clk);reset_n=1;@(negedge clk);
        end
    endtask
    task automatic launch;
        begin
            if(!ready)$fatal(1,"ARM boundary not ready");
            arm=1;@(negedge clk);arm=0;
            if(tx || armed || ready)$fatal(1,"capture must precede business ARM");checks++;
        end
    endtask
    task automatic rejected_next;
        begin
            @(negedge clk);
            if(!rejected || tx || armed || actual_boot!=0)$fatal(1,"stale/fenced ARM escaped");checks++;
        end
    endtask
    initial begin
        restart();launch();@(negedge clk);
        if(!tx || actual_boot!=boot || actual_session!=session || actual_generation!=generation)$fatal(1,"captured identity not applied");checks++;
        @(negedge clk);ack=1;@(negedge clk);ack=0;
        if(!armed || !accepted)$fatal(1,"matched remote ARM ACK lost");checks++;
        panic=1;#1;if(tx)$fatal(1,"PANIC must revoke combinationally");
        @(negedge clk);panic=0;repeat(3)@(negedge clk);
        launch();@(negedge clk);if(!rejected || tx || armed)$fatal(1,"retired generation replay");checks++;
        restart();launch();generation=2;rejected_next();
        restart();launch();session=23;rejected_next();
        restart();launch();boot=12;rejected_next();
        restart();launch();link=0;rejected_next();
        restart();launch();panic=1;rejected_next();
        restart();launch();cancel=1;rejected_next();
        restart();generation=0;launch();rejected_next();
        restart();boot=0;launch();rejected_next();
        restart();session=0;launch();rejected_next();
        $display("PASS task3 phone ARM capture checks=%0d",checks);$finish;
    end
    initial begin #20000;$fatal(1,"timeout");end
endmodule
