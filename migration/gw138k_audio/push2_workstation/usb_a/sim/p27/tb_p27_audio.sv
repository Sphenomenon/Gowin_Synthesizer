`timescale 1ns/1ps
module tb_p27_audio;
    reg clk=0,reset_n=0,event_valid=0;reg [17:0] event_data=0;
    wire event_ready;wire [1:0] mode;wire [2:0] effect_mask;wire [5:0] effect_order;
    wire panel_event_valid;wire [6:0] panel_command;integer panels=0;reg [6:0] last_panel=127;
    always #5 clk=~clk;
    always @(posedge clk)if(panel_event_valid)begin panels=panels+1;last_panel=panel_command;end
    gw138k_event_workstation dut(.clk_i(clk),.rst_ni(reset_n),
        .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
        .held_notes_o(),.applied_events_o(),.pc_overflow_o(),.control_options_o(),.panic_epoch_o(),
        .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(event_ready),
        .sample_ce_i(1'b0),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.sample_valid_o(),
        .left_o(),.right_o(),.synth_valid_o(),.synth_o(),.active_mask_o(),.active_voice_count_o(),
        .mode_o(mode),.pitch_q20_o(),.deadline_miss_o(),.midi_overflow_o(),.note_drop_o(),.clip_o(),
        .synth_gain_o(),.pcm_gain_o(),.route_o(),.profile_o(),.effect_mask_o(effect_mask),
        .effect_order_o(effect_order),.panel_event_valid_o(panel_event_valid),.panel_command_o(panel_command));
    task send_event(input [3:0] kind,input [6:0] aa,input [6:0] bb);
        @(negedge clk);event_data={kind,aa,bb};event_valid=1;
        do @(posedge clk);while(!event_ready);
        @(negedge clk);event_valid=0;repeat(3)@(posedge clk);
    endtask
    initial begin
        repeat(3)@(posedge clk);reset_n=1;repeat(6)@(posedge clk);
        send_event(2,80,0);wait(mode==0);
        send_event(2,89,0);wait(mode==2);
        send_event(2,89,1);wait(mode==0);
        send_event(2,89,1);wait(mode==1);
        send_event(2,87,2);send_event(2,87,0);
        if(effect_mask!=3'b101 || effect_order!=6'b11_00_10)$fatal(1,"effect setup %b %b",effect_mask,effect_order);
        send_event(2,88,0);if(effect_mask!=0 || effect_order!=6'b11_00_10)$fatal(1,"master off lost order");
        send_event(2,120,0);if(effect_mask!=0 || effect_order!=6'b11_00_10)$fatal(1,"PANIC changed master/order");
        send_event(2,88,0);if(effect_mask!=3'b101 || effect_order!=6'b11_00_10)$fatal(1,"master restore failed");
        send_event(6,0,0);send_event(6,1,0);
        repeat(2)@(posedge clk);
        if(panels!=2 || last_panel!=1)$fatal(1,"panel dispatch count=%0d command=%0d",panels,last_panel);
        $display("PASS P27 audio: ordered panel dispatch, A/B/C wrap, effect master preserves mask/order across off/PANIC/on");
        $finish;
    end
    initial begin #100000;$fatal(1,"timeout");end
endmodule
