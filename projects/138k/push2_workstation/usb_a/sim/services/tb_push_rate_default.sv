`timescale 1ns/1ps
// Whole public USB-owner output miter against caller-supplied frozen bytes.
module tb_push_rate_default;
    reg clk=0,aclk=0,rn=1,arn=1,sel=0,wr=0,consume=1,rate_ready=0;
    reg[7:0]addr=0;reg[31:0]wd=0,random_state=32'h22510a51;
    always #10 clk=~clk;
    always #6.5 aclk=~aclk;
    wire[284:0]got,want;wire pulse,reject_pulse;
    wire[31:0]rd[0:1];wire[223:0]telemetry[0:1];wire[17:0]event_data[0:1];
    wire[3:0]track[0:1];wire[1:0]ready,av,life,cancel,launch,sr,pr;
`define COMMON .clk,.reset_n(rn),.audio_clk(aclk),.audio_reset_n(arn),.feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(448'd0),.display_meta_data(64'd0),.display_meta_valid(1'b0),.service_state_data(34'd0),.service_state_valid(1'b0),.score_valid(1'b0),.analysis_done(1'b0),.score_note(7'd0),.playlist_valid(1'b0),.playlist_word(16'd0),.select(sel),.write(wr),.address(addr),.wdata(wd),.audio_ready(consume)
    push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0)) actual(`COMMON,
        .rdata(rd[0]),.telemetry(telemetry[0]),.audio_event(event_data[0]),.track_index(track[0]),.ready(ready[0]),
        .audio_valid(av[0]),.audio_lifecycle(life[0]),.audio_cancel(cancel[0]),.track_launch(launch[0]),.score_ready(sr[0]),.playlist_ready(pr[0]),
        .rate_control_ready_i(rate_ready),.rate_toggle_o(pulse),.rate_rejected_o(reject_pulse));
    push2_usb_a_control_before #(.CNN_FOLLOW_ENABLE(0)) reference(`COMMON,
        .rdata(rd[1]),.telemetry(telemetry[1]),.audio_event(event_data[1]),.track_index(track[1]),.ready(ready[1]),
        .audio_valid(av[1]),.audio_lifecycle(life[1]),.audio_cancel(cancel[1]),.track_launch(launch[1]),.score_ready(sr[1]),.playlist_ready(pr[1]));
    assign got={rd[0],telemetry[0],ready[0],av[0],event_data[0],life[0],cancel[0],launch[0],track[0],sr[0],pr[0]};
    assign want={rd[1],telemetry[1],ready[1],av[1],event_data[1],life[1],cancel[1],launch[1],track[1],sr[1],pr[1]};
    integer checks=0;
    always @(posedge clk or negedge clk or posedge aclk or negedge aclk)begin
        #0.1;
        if(got!==want || pulse!==0 || reject_pulse!==0)$fatal(1,"default USB output miter mismatch check=%0d",checks);
        checks++;
    end
    initial begin
        #1;rn=0;arn=0;repeat(5)@(negedge clk);rn=1;arn=1;
        for(integer i=0;i<24000;i=i+1)begin
            @(negedge clk);
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            rate_ready=random_state[0];consume=random_state[1];
            if(i%503==0)arn=0;else if(i%503==8)arn=1;
            if(!sel || ready[0])begin
                sel=1;wr=1;
                case(i%13)
                    0:begin addr=0;wd=(i%39==0)?1:3;end
                    1,2,3:begin addr=4;wd={1'b0,(i%2==0?7'd127:7'd0),1'b0,7'd51,16'hb00b};end
                    4:begin addr=4;wd={1'b0,7'd1,1'b0,7'd71,16'hb00b};end
                    5:begin addr=4;wd={1'b0,7'd127,1'b0,7'd27,16'hb00b};end
                    6:begin addr=4;wd={1'b0,7'd0,1'b0,7'd27,16'hb00b};end
                    7:begin addr=8'h54;wd={14'd0,4'd2,7'd7,random_state[6:0]};end
                    8:begin addr=8'h54;wd={14'd0,4'd1,7'd60,7'd100};end
                    9:begin addr=8'h10;wr=0;end
                    10:begin addr=8'h58;wd=random_state;end
                    11:begin addr=0;wd=0;end
                    12:sel=0;
                endcase
            end
        end
        @(negedge clk);sel=0;
        $display("PASS push_rate_default public_output_checks=%0d USB_cycles=24000 default_parameter_unchanged=1",checks);$finish;
    end
endmodule
