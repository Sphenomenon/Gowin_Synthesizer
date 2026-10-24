module ak4493_amp_top (
    input wire clk_50mhz, clk_12m288, restart_n, plug_det,
    output wire ak_pdn, ak_mclk, ak_bick, ak_lrck, ak_sdata,
    output wire ak_smute, ak_sslow, ak_sd, ak_slow
);
    wire [31:0] clock_gray, frame_gray;
    wire [1:0] phase;
`ifdef CONTINUOUS_TONE_TEST
    ak4493_pin_test #(.CONTINUOUS_TONES(1)) audio (
`elsif CHANNEL_ISOLATION_TEST
    ak4493_pin_test #(.ISOLATE_CHANNELS(1),.PHASE_FRAMES(144000)) audio (
`else
    ak4493_pin_test audio (
`endif
        .audio_clk(clk_12m288),.restart_n(restart_n),
        .pdn(ak_pdn),.mclk(ak_mclk),.bick(ak_bick),.lrck(ak_lrck),
        .sdata(ak_sdata),.smute(ak_smute),.sslow(ak_sslow),.sd(ak_sd),.slow(ak_slow),
        .clock_gray(clock_gray),.frame_gray(frame_gray),.phase(phase));
    reg [10:0] power_por=0;
    wire [13:0] rail_last,rail_min,rail_max;
    wire [31:0] rail_count,rail_timeouts,rail_age,rail_duration;
    wire [7:0] rail_flags;
    vccio5_monitor power (.clk(clk_50mhz),.rst_n(power_por[10]),
        .last(rail_last),.minimum(rail_min),.maximum(rail_max),.count(rail_count),
        .timeouts(rail_timeouts),.age(rail_age),.duration(rail_duration),.flags(rail_flags));
    (* ASYNC_REG="TRUE" *) reg [31:0] cg1=0,cg2=0,fg1=0,fg2=0;
    (* ASYNC_REG="TRUE" *) reg [7:0] pins1=0,pins2=0;
    reg [31:0] heartbeat=0;
    function [31:0] binary;
        input [31:0] gray;
        integer i;
        begin
            binary[31]=gray[31];
            for(i=30;i>=0;i=i-1) binary[i]=binary[i+1]^gray[i];
        end
    endfunction
    (* syn_keep=1, syn_preserve=1 *) reg [351:0] audio_debug;
    always @(posedge clk_50mhz) begin
        if(!power_por[10]) power_por<=power_por+1'b1;
        cg1<=clock_gray; cg2<=cg1; fg1<=frame_gray; fg2<=fg1;
        pins1<={2'b00,phase,plug_det,restart_n,ak_smute,ak_pdn}; pins2<=pins1;
        heartbeat<=heartbeat+1'b1;
        audio_debug<={{rail_age[23:0],rail_flags},rail_timeouts,rail_count,
            {rail_duration[17:0],rail_max},{4'd0,rail_min,rail_last},32'h41444335,
            heartbeat,24'd0,pins2,binary(fg2),binary(cg2),32'h414d5031};
    end
endmodule
