`timescale 1ns/1ps
module tb_usb_lifecycle_merge;
    reg clk=0,rn=0,usb_valid=0,pc_valid=0,ready=0;
    reg [17:0] usb_data=0,pc_data=0;
    wire usb_ready,pc_ready,valid;wire [17:0] data;
    always #5 clk=~clk;
    gw138k_usb_lifecycle_merge #(.EXPLICIT_LIFECYCLE(1)) dut(.clk(clk),.reset_n(rn),
        .g1_valid(usb_valid),.g1_lifecycle(usb_data[17:14]==15),.g1_cancel(usb_data[6:0]<3),.g1_data(usb_data),.g1_ready(usb_ready),
        .pc_valid(pc_valid),.pc_data(pc_data),.pc_ready(pc_ready),
        .cpu_valid(1'b0),.cpu_data(18'd0),.cpu_ready(),
        .event_valid(valid),.event_data(data),.event_ready(ready));
    initial begin
        repeat(3)@(negedge clk);rn=1;
        usb_valid=1;usb_data={4'd1,7'd60,7'd100};
        @(negedge clk);usb_valid=0;
        if(!valid || data!=usb_data)$fatal(1,"registered normal input");
        repeat(3)@(negedge clk);
        if(!valid || data!=usb_data)$fatal(1,"stalled normal event changed");
        // Detach bypasses the old buffered note and prevents an unrelated PC
        // store from being acknowledged on the global cancellation boundary.
        usb_valid=1;usb_data={4'd15,7'd0,7'd0};pc_valid=1;pc_data={4'd2,7'd7,7'd30};ready=1;
        #1;if(!valid || data!=usb_data || !usb_ready || pc_ready)$fatal(1,"lifecycle priority");
        @(negedge clk);usb_valid=0;pc_valid=0;ready=0;
        #1;if(valid)$fatal(1,"old merge event survived cancellation");
        // Completion is an end-to-end handshake; the merge cannot acknowledge
        // it into a register while the audio initialization is still busy.
        usb_valid=1;usb_data={4'd15,7'd0,7'd3};
        repeat(5)begin @(negedge clk);if(usb_ready || !valid || data!=usb_data)$fatal(1,"probe buffered early");end
        ready=1;#1;if(!usb_ready)$fatal(1,"probe did not acknowledge");
        @(negedge clk);usb_valid=0;pc_valid=1;
        @(negedge clk);pc_valid=0;
        if(!valid || data!=pc_data)$fatal(1,"PC route did not resume");
        @(negedge clk);if(valid)$fatal(1,"duplicate PC item");
        $display("PASS USB lifecycle merge: stalled old event canceled, immediate priority, CPU backpressure, completion handshake, normal resume");
        $finish;
    end
    initial begin #10000;$fatal(1,"timeout");end
endmodule
