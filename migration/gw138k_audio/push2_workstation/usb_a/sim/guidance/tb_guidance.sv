`timescale 1ns/1ps
module tb_guidance;
    reg clk=0,rst=1,score_valid=0,valid=0;
    reg [6:0] score_note=0,a=0,b=0;
    reg [3:0] kind=11;
    wire score_ready,ready,event_valid,guide_toggle,mode,target_valid;
    wire [6:0] target_note,last_note,last_velocity;
    wire [17:0] event_data;
    wire [63:0] held,guide_mask;
    wire [15:0] score_count,cursor;
    wire [15:0] wrong_count;
    wire [31:0] mapped,ignored;
    wire led_valid; wire [1:0] led_kind;wire [6:0] led_index;wire [7:0] led_value;
    reg [6:0] pad_color [36:99];
    reg [6:0] button_color [0:127];
    integer i;
    always #10 clk=~clk;
    push2_controls controls(.clk,.rst,.connected(1'b1),.valid,.ready,.kind,
        .cable(4'd0),.channel(4'd0),.a,.b,
        .actual_control(32'd0),.actual_options(32'd0),.actual_panic_epoch(10'd0),
        .guide_enabled_i(1'b1),.guide_mode_i(mode),.guide_toggle_o(guide_toggle),
        .guide_prev_o(),.guide_next_o(),.guide_select_o(),
        .event_valid,.event_ready(1'b1),.event_data,.held,.last_note,.last_velocity,.mapped,.ignored);
    push2_score_guide guide(.clk,.rst,.score_valid,.score_ready,.score_note,
        .toggle(guide_toggle),.selected_i(1'b1),.clear_i(1'b0),.played_valid(event_valid &&
            event_data[17:14]==4'd1 && event_data[6:0]!=7'd0),
        .played_note(event_data[13:7]),.mode,.target_valid,.target_note,
        .score_count,.cursor,.wrong_count,.guide_mask);
    push2_lights lights(.clk,.rst,.held(64'hffffffffffffffff),.control(32'hffffffff),
        .score_mask(32'hffffffff),.score_running(1'b1),.record_enabled(1'b1),
        .guide_mode(mode),.guide_mask,
        .valid(led_valid),.ready(1'b1),.kind(led_kind),.index(led_index),.value(led_value));
    always @(posedge clk) if (!rst && led_valid) begin
        if (led_kind==0) pad_color[led_index]<=led_value[6:0];
        if (led_kind==3 && led_index<125) button_color[led_index]<=led_value[6:0];
    end
    task score(input [6:0] note);
        begin
            @(negedge clk);score_note=note;score_valid=1;
            @(negedge clk);score_valid=0;
        end
    endtask
    task midi(input [3:0] k,input [6:0] note,input [6:0] velocity);
        begin
            @(negedge clk);kind=k;a=note;b=velocity;valid=1;
            do @(posedge clk);while(!ready);
            @(negedge clk);valid=0;
            repeat(3)@(negedge clk);
        end
    endtask
    task assert_exclusive(input [6:0] only_note);
        begin
            repeat(430)@(negedge clk);
            for(integer n=36;n<=99;n=n+1)
                if(pad_color[n] !== (n==only_note ? 7'd126 : 7'd0))
                    $fatal(1,"pad %0d colour %0d, target %0d",n,pad_color[n],only_note);
            for(integer n=0;n<128;n=n+1)
                if(n==102 || n==103 || n==104 || n==105 || n==106 || n==107 ||
                   n==108 || n==109 || (n>=20 && n<=28) || n==85 || n==86 ||
                   n==62 || n==63)
                    if(button_color[n] !== 7'd0)
                        $fatal(1,"button %0d colour %0d",n,button_color[n]);
        end
    endtask
    initial begin
        for(i=36;i<=99;i=i+1)pad_color[i]=7'h7f;
        for(i=0;i<128;i=i+1)button_color[i]=7'h7f;
        repeat(4)@(negedge clk);rst=0;
        score(7'd60);score(7'd62);score(7'd60);
        if(score_count!=3)$fatal(1,"score count %0d",score_count);
        repeat(400)@(negedge clk);
        midi(11,85,127);midi(11,85,0);
        if(!mode || !target_valid || target_note!=60 || guide_mask!=(64'd1<<24))
            $fatal(1,"first target mode=%b note=%0d mask=%h",mode,target_note,guide_mask);
        assert_exclusive(60);
        midi(9,61,100);midi(8,61,0);
        if(cursor!=0 || wrong_count!=1)$fatal(1,"wrong key advanced");
        midi(9,60,0);midi(8,60,0);
        if(cursor!=0)$fatal(1,"zero-velocity note-on advanced");
        midi(9,60,100);
        if(cursor!=1 || target_note!=62)$fatal(1,"first correct did not advance");
        assert_exclusive(62);
        midi(9,62,100);
        if(cursor!=2 || target_note!=60)$fatal(1,"second correct did not advance");
        midi(9,60,100);
        if(cursor!=2)$fatal(1,"held note advanced repeated target");
        midi(8,60,0);midi(9,60,100);
        if(cursor!=3 || target_valid || guide_mask!=0)$fatal(1,"final target not completed");
        assert_exclusive(0);
        midi(11,85,127);midi(11,85,0);
        if(mode)$fatal(1,"guide mode did not exit");
        $display("PASS guidance: CNN list -> exclusive Push LEDs -> wrong/held notes blocked -> fresh correct keys advance");
        $finish;
    end
endmodule
