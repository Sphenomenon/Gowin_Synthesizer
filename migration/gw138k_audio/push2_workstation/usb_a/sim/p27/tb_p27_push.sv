`timescale 1ns/1ps
module tb_p27_push;
    reg clk=0,rst=1,connected=1,valid=0,event_ready=1;
    reg [3:0] kind=11,cable=0,channel=0;reg [6:0] a=0,b=0;
    wire ready,event_valid;wire [17:0] event_data;wire [31:0] mapped,ignored;
    wire [63:0] mapper_held;wire [6:0] note,velocity;
    reg [63:0] light_held=64'd2;reg [31:0] control=32'd7;
    wire light_valid;reg light_ready=1;wire [1:0] light_kind;wire [6:0] light_index;wire [7:0] light_value;
    integer light_score=0,light_record=0,light_master=0,light_score_pad=0,light_held_pad=0;
    integer repeat_before=0;
    always #10 clk=~clk;
    push2_controls controls(.clk,.rst,.connected,.valid,.ready,.kind,.cable,.channel,.a,.b,
        .actual_control(control),.actual_options(32'd0),.actual_panic_epoch(10'd0),
        .event_valid,.event_ready,.event_data,.held(mapper_held),.last_note(note),
        .last_velocity(velocity),.mapped,.ignored);
    push2_lights lights(.clk,.rst,.held(light_held),.control,
        .score_mask(32'd1),.score_running(1'b1),.record_enabled(1'b1),
        .valid(light_valid),.ready(light_ready),.kind(light_kind),.index(light_index),.value(light_value));
    always @(posedge clk)if(!rst && light_valid && light_ready)begin
        if(light_kind==0 && light_index==36 && light_value==126)light_score_pad=1;
        if(light_kind==0 && light_index==37 && light_value==122)light_held_pad=1;
        if(light_kind==3 && light_index==28 && light_value==126)light_master=1;
        if(light_kind==3 && light_index==85 && light_value==126)light_score=1;
        if(light_kind==3 && light_index==86 && light_value==5)light_record=1;
    end
    task word(input [6:0] cc,input [6:0] value);
        @(negedge clk);a=cc;b=value;valid=1;
        do @(posedge clk);while(!ready);
        @(negedge clk);valid=0;repeat(2)@(posedge clk);
    endtask
    task press(input [6:0] cc,input [17:0] expected);
        integer base_count;begin
            base_count=mapped;word(cc,127);
            if(event_data!==expected || mapped!=base_count+1)$fatal(1,"CC%0d map %h count %0d",cc,event_data,mapped);
            word(cc,0);
            if(mapped!=base_count+1 || event_valid)$fatal(1,"CC%0d release generated event",cc);
        end
    endtask
    initial begin
        repeat(3)@(posedge clk);rst=0;repeat(4)@(posedge clk);
        press(85,{4'd6,7'd0,7'd0});press(86,{4'd6,7'd1,7'd0});
        press(62,{4'd2,7'd89,7'd0});press(63,{4'd2,7'd89,7'd1});
        press(28,{4'd2,7'd88,7'd0});press(29,{4'd2,7'd120,7'd0});
        // A second nonzero value before release is still the same physical press.
        word(85,127);repeat_before=mapped;word(85,64);
        if(mapped!=repeat_before || event_valid)$fatal(1,"held Play repeated");word(85,0);
        repeat(500)@(posedge clk);
        if(!light_score || !light_record || !light_master || !light_score_pad || !light_held_pad)
            $fatal(1,"status lights missing score=%0d rec=%0d master=%0d cue=%0d held=%0d",
                light_score,light_record,light_master,light_score_pad,light_held_pad);
        $display("PASS P27 Push: CC85/86 panel, CC62/63 mode, CC28 master, CC29 PANIC; releases/held repeat suppressed; cue/held/status lights");
        $finish;
    end
endmodule
