`timescale 1ns/1ps
module tb_p27_services;
    reg clk=0,reset_n=0,command_valid=0,command_write=0,panel_event_valid=0;
    reg [11:0] command_address=0;reg [31:0] command_data=0;reg [3:0] command_strobes=15;
    reg [6:0] panel_command=0;reg sample_ce=1;
    wire command_ready,response_error,cpu_event_valid,panel_event_ready;
    wire [31:0] response_data;wire [17:0] cpu_event;
    wire record_enable,record_ready,score_write,score_start,score_stop;
    wire [7:0] score_address;wire [63:0] score_data;wire [8:0] score_length;
    wire score_running,score_done;wire [31:0] led_mask,score_frame;
    always #5 clk=~clk;
    gw138k_controlled_services services(.clk,.reset_n,.command_valid,.command_write,
        .command_address,.command_data,.command_strobes,.command_ready,.response_data,.response_error,
        .cpu_event_valid,.cpu_event,.cpu_event_ready(1'b1),.panel_event_valid,.panel_command,.panel_event_ready,
        .control_state(32'd0),.control_pitch(32'd0),.control_options(32'd0),.applied_events(32'd0),.pc_health(32'd0),
        .held_notes(128'd0),.sample_valid(sample_ce),.active_mask(32'd0),.deadline_miss(32'd0),
        .midi_overflow(32'd0),.note_drop(32'd0),.underrun_count(32'd0),.midi_cdc_drop(32'd0),
        .observation_drop(32'd0),.record_drop(32'd0),.record_enable,.snap_status(),.snap_left(),
        .snap_right(),.snap_sequence(),.record_valid(1'b0),.record_packet(96'd0),.record_ready,
        .score_write,.score_start,.score_stop,.score_address,.score_data,.score_length,
        .score_running,.score_done,.led_mask,.score_frame);
    score_led_player player(.clk_i(clk),.rst_ni(reset_n),.sample_ce_i(sample_ce),
        .write_i(score_write),.write_address_i(score_address),.write_data_i(score_data),
        .start_i(score_start),.stop_i(score_stop),.length_i(score_length),
        .running_o(score_running),.done_o(score_done),.leds_o(led_mask),.frame_o(score_frame));
    task write_reg(input [11:0] address,input [31:0] data);
        @(negedge clk);command_address=address;command_data=data;command_write=1;command_valid=1;
        @(posedge clk);if(response_error)$fatal(1,"write %h rejected",address);
        @(negedge clk);command_valid=0;command_write=0;repeat(2)@(posedge clk);
    endtask
    task panel(input [6:0] command);
        @(negedge clk);panel_command=command;panel_event_valid=1;@(posedge clk);
        if(!panel_event_ready)$fatal(1,"panel backpressure");
        @(negedge clk);panel_event_valid=0;repeat(2)@(posedge clk);
    endtask
    initial begin
        repeat(3)@(posedge clk);reset_n=1;repeat(3)@(posedge clk);
        write_reg(12'h120,1);
        write_reg(12'h100,0);write_reg(12'h104,3);write_reg(12'h108,32'h00000005);write_reg(12'h10c,1);
        write_reg(12'h100,1);write_reg(12'h104,30);write_reg(12'h108,0);write_reg(12'h10c,1);
        write_reg(12'h110,2);
        panel(0);wait(score_running);wait(led_mask==32'h5);
        if(cpu_event_valid)$fatal(1,"score panel created note/control event");
        panel(0);repeat(3)@(posedge clk);
        if(score_running || led_mask)$fatal(1,"score stop did not clear LEDs");
        panel(1);if(!record_enable)$fatal(1,"record did not start");
        panel(1);if(record_enable)$fatal(1,"record did not stop");
        panel(0);wait(score_running);wait(score_done);repeat(2)@(posedge clk);
        if(score_running || led_mask || score_frame<30)$fatal(1,"score completion mismatch");
        $display("PASS P27 services: existing cue RAM/time/mask start-stop, final zero mask, bounded recorder enable toggle, no note event");
        $finish;
    end
    initial begin #100000;$fatal(1,"timeout");end
endmodule
