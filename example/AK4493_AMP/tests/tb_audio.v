`timescale 1ns/1ps
module tb_audio;
    reg clk=0, restart_n=0;
    always #40.690104 clk=~clk;
    wire pdn,mclk,bick,lrck,data,mute,sslow,sd,slow;
    wire [31:0] cg,fg;
    wire [1:0] phase;
`ifdef CHANNEL_ISOLATION_TEST
    localparam ISOLATE_CHANNELS=1;
`else
    localparam ISOLATE_CHANNELS=0;
`endif
`ifdef CONTINUOUS_TONE_TEST
    localparam CONTINUOUS_TONES=1;
`else
    localparam CONTINUOUS_TONES=0;
`endif
    ak4493_pin_test #(.RESET_CYCLES(32),.WARMUP_FRAMES(16),.PHASE_FRAMES(192),
                      .ISOLATE_CHANNELS(ISOLATE_CHANNELS),.CONTINUOUS_TONES(CONTINUOUS_TONES)) dut (
        .audio_clk(clk),.restart_n(restart_n),.pdn(pdn),.mclk(mclk),.bick(bick),
        .lrck(lrck),.sdata(data),.smute(mute),.sslow(sslow),.sd(sd),.slow(slow),
        .clock_gray(cg),.frame_gray(fg),.phase(phase));
    integer position=-1,received=0,bits=0,frame_index=0;
    reg previous_lr=1;
    reg [31:0] sample=0;
    reg channel=0;
    realtime previous_mclk=0,previous_bick=0,previous_frame=0;
    always @(posedge mclk) begin
        if (!pdn) $fatal(1,"MCLK while PDN low");
        if (previous_mclk!=0 && $realtime-previous_mclk<81.37) $fatal(1,"MCLK pulse truncated");
        previous_mclk=$realtime;
    end
    always @(posedge bick) begin
        if (!pdn) $fatal(1,"BICK while PDN low");
        if (previous_bick!=0 && ($realtime-previous_bick<325.50 || $realtime-previous_bick>325.55)) $fatal(1,"BICK period");
        previous_bick=$realtime;
        // The old channel's LSB is captured at the LRCK transition itself.
        if (position>=0) begin
            sample={sample[30:0],data};
            bits=bits+1;
            if(bits==32) begin
                $display("PCM %0d %0d %08h %0d",frame_index,channel,sample,mute);
                if(channel) frame_index=frame_index+1;
                received=received+1;
                position=-1;
            end
        end
        if(lrck!=previous_lr) begin
            if(!lrck) begin
                if(previous_frame!=0 && ($realtime-previous_frame<20833.0 || $realtime-previous_frame>20834.0)) $fatal(1,"LRCK period");
                previous_frame=$realtime;
            end
            channel=lrck; position=0; bits=0; sample=0;
        end
        previous_lr=lrck;
        if(received>=2000) begin
            restart_n=0;
            repeat(8) @(negedge clk);
            #1;
            if(pdn || mclk || bick || !mute || data) $fatal(1,"Restart did not stop/mute DAC");
            if(dut.frames!=0) $fatal(1,"Restart did not clear frame count");
            restart_n=1;
            wait(pdn);
            #5000;
            if(!pdn || !dut.clocks_on || !mute) $fatal(1,"Restart startup sequence");
            $display("PASS audio physical clocks, I2S framing and restart"); $finish;
        end
    end
    initial begin
        #1000;
        if(pdn || mclk || bick || !mute) $fatal(1,"Unsafe initial/reset pins");
        restart_n=1;
        #25000000; $fatal(1,"Audio simulation timeout");
    end
endmodule
