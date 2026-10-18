`timescale 1ns/1ps
module performance_race_case #(parameter integer CASE_ID=0)(output reg done=0, output reg failed=0);
    reg clk=0;always #10 clk=~clk;
    reg reset=1;
    reg [15:0] key_bitmap=0;
    reg keypad_ready=1,slider_valid=0,slider_touch=1;
    reg [7:0] slider_position=0;
    reg enc1_step=0,enc1_press=0,enc2_step=0,enc2_press=0;
    reg signed [1:0] enc1_direction=1,enc2_direction=1;
    reg config_write=0;reg [7:0] config_opcode=0;reg [31:0] config_value=0;
    reg [1:0] online=0;reg [12:0] timestamp_ms=0;
    wire event_valid;reg event_ready=1;wire [23:0] event_message;
    wire [1:0] event_length,event_targets;wire [12:0] event_timestamp;
    wire [3:0] midi_channel;wire signed [7:0] transpose;
    wire [6:0] velocity,program_number;wire [1:0] slider_mode;
    wire [7:0] brightness,strip_value;wire [2:0] focus;
    wire [15:0] active_keys;wire panic_busy;wire [31:0] emitted_events;
    midi_performance dut(.*);
    reg [23:0] messages[0:511];integer events=0,j,c,start;
    reg found;
    always @(posedge clk) if(!reset && event_valid && event_ready) begin
        messages[events]=event_message;events=events+1;
    end
    task ticks(input integer count);begin repeat(count)@(negedge clk);end endtask
    task channel(input [3:0] value);
        begin @(negedge clk);config_write=1;config_opcode=8'h10;config_value=value;
            @(negedge clk);config_write=0;end
    endtask
    task expect_seen(input [23:0] wanted);
        begin
            found=0;for(j=start;j<events;j=j+1)if(messages[j]===wanted)found=1;
            if(!found) begin
                $display("FAIL race%0d missing %06h since event%0d",CASE_ID,wanted,start);failed=1;
            end
        end
    endtask
    initial begin
        ticks(5);reset=0;ticks(4);start=events;
        if(CASE_ID==0)begin
            // Two consecutive valid snapshots: the second arrives exactly as
            // the first pending controller update is placed in the output slot.
            @(negedge clk);slider_valid=1;slider_position=64;
            @(negedge clk);slider_position=192;
            @(negedge clk);slider_valid=0;ticks(40);
            if(strip_value!==192)$fatal(1,"Race setup did not change slider state");
            expect_seen(24'hb00160);
        end else if(CASE_ID==1)begin
            repeat(4)begin @(negedge clk);enc1_step=1;@(negedge clk);enc1_step=0;end
            @(negedge clk);enc2_step=1;
            @(negedge clk); // keep valid step asserted on the next clock
            @(negedge clk);enc2_step=0;ticks(40);
            if(program_number!==2)$fatal(1,"Race setup did not increment program twice");
            expect_seen(24'hc00200);
        end else begin
            channel(10);ticks(80);start=events;event_ready=0;
            channel(5);wait(event_valid);
            if(event_message!==24'hba0100)$fatal(1,"Expected first cleanup slot for channel10, got%06h",event_message);
            channel(3);event_ready=1;ticks(100);
            // Both outgoing channels must receive all three cleanup messages,
            // even when a lower-numbered dirty channel arrives mid-sequence.
            expect_seen(24'hba0100);expect_seen(24'hba0b7f);expect_seen(24'hea0040);
            expect_seen(24'hb50100);expect_seen(24'hb50b7f);expect_seen(24'he50040);
        end
        done=1;
    end
endmodule
module tb_midi_performance_races;
    wire [2:0] done,failed;
    performance_race_case #(.CASE_ID(0)) strip_case(done[0],failed[0]);
    performance_race_case #(.CASE_ID(1)) program_case(done[1],failed[1]);
    performance_race_case #(.CASE_ID(2)) cleanup_case(done[2],failed[2]);
    initial begin
        wait(done==3'b111);
        if(failed)$fatal(1,"Performance update/cleanup races failed mask=%b",failed);
        $display("PASS performance races: consecutive final strip/program updates survive emission; each cleanup channel receives its complete sequence");$finish;
    end
    initial begin #100_000;$fatal(1,"Performance race timeout done=%b",done);end
endmodule
