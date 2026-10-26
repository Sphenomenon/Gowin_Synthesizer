`timescale 1ns/1ps

module tb_workstation_volume;
    reg clk=0,reset_n=0,connected=0,raw_valid=0,accept=1,panel_valid=0;
    reg [6:0] raw_cc=0,raw_value=0,panel_volume=0;
    wire raw_ready,mapped_valid;
    wire [17:0] mapped_event;
    wire [15:0] volume,expression_gain,synth_gain;
    wire [17:0] event_data=panel_valid ? {4'd2,7'd7,panel_volume} : mapped_event;
    wire committed=(panel_valid || mapped_valid) && accept;
    always #6.510417 clk=!clk;
    push2_controls #(.INITIAL_VOLUME(127)) push (
        .clk(clk),.rst(!reset_n),.connected(connected),
        .valid(raw_valid),.ready(raw_ready),.kind(4'd11),.cable(4'd0),.channel(4'd0),
        .a(raw_cc),.b(raw_value),.actual_control({volume,16'd0}),.actual_options(32'd0),
        .actual_panic_epoch(10'd0),.guide_enabled_i(1'b0),.guide_mode_i(1'b0),
        .event_valid(mapped_valid),.event_ready(accept && !panel_valid),.event_data(mapped_event)
    );
    workstation_parameters parameters (
        .clk_i(clk),.rst_ni(reset_n),.commit_i(committed),.lifecycle_i(1'b0),.mode_applied_i(1'b0),
        .kind_i(event_data[17:14]),.address_i(event_data[13:7]),.value_i(event_data[6:0]),
        .mode_i(2'd2),.legacy_active_i(32'd0),.vector_active_i(8'd0),.cue_running_i(1'b0),
        .volume_o(volume),.expression_gain_o(expression_gain),.synth_gain_o(synth_gain)
    );
    task push_delta(input [6:0] controller,input [6:0] delta);
        begin
            @(negedge clk);while(!raw_ready)@(negedge clk);
            raw_cc=controller;raw_value=delta;raw_valid=1;
            @(negedge clk);raw_valid=0;
            repeat(4)@(negedge clk);
        end
    endtask
    task panel_set(input [6:0] value);
        begin
            @(negedge clk);panel_volume=value;panel_valid=1;
            @(negedge clk);panel_valid=0;
            repeat(2)@(negedge clk);
        end
    endtask
    integer value_index;
    initial begin
        repeat(8)@(negedge clk);reset_n=1;connected=1;
        repeat(8)@(negedge clk);
        if(volume!=32768)$fatal(1,"volume reset is not unity");
        push_delta(71,127);
        if(volume!=32256)$fatal(1,"Push CC71 relative decrement did not become CC7");
        push_delta(79,1);
        if(volume!=32768)$fatal(1,"Push CC79 relative increment did not become CC7");
        push_delta(71,1);
        if(volume!=32768)$fatal(1,"Push volume exceeded unity");
        accept=0;push_delta(71,127);
        if(volume!=32768 || !mapped_valid)$fatal(1,"queued knob event changed authoritative volume before commit");
        accept=1;repeat(4)@(negedge clk);
        if(volume!=32256)$fatal(1,"queued knob event was not applied exactly once");
        for(value_index=0;value_index<128;value_index=value_index+1) begin
            panel_set(7'(value_index));
            if(volume!=(value_index==127 ? 32768 : value_index*256))
                $fatal(1,"25K absolute CC7 mapping changed at %0d",value_index);
        end
        panel_set(0);
        repeat(100010)@(negedge clk);
        push_delta(71,127);
        if(volume!=0)$fatal(1,"Push volume underflowed zero");
        push_delta(79,1);
        if(volume!=256)$fatal(1,"Push cache did not align with committed CC7 state");
        if(expression_gain!=32768 || synth_gain!=256)$fatal(1,"master/expression authority changed");
        $display("PASS volume controls: Push CC71/79, 25K CC7 all 128 values, commit/backpressure and bounds");
        $finish;
    end
    initial begin #10000000;$fatal(1,"volume control timeout");end
endmodule
