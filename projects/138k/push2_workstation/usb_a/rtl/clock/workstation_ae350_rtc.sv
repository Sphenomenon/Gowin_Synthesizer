`default_nettype none
// 32.768 kHz average from the board's 50 MHz reference. Each half-period is
// 762 or 763 reference cycles; edge phase error stays below one reference tick.
// This independent, always-running RTC must not depend on CPU/APB activity.
module workstation_ae350_rtc(
    input wire clk_50m,reset_n,
    output wire rtc_clk
);
    reg [25:0] phase=0;
    (* syn_keep=1,syn_preserve=1 *) reg rtc_tick=0;
    wire [26:0] advance={1'b0,phase}+27'd65536;
    wire [26:0] wrapped=advance-27'd50000000;
    assign rtc_clk=rtc_tick;
    always @(posedge clk_50m or negedge reset_n)
        if(!reset_n)begin phase<=0;rtc_tick<=0;end
        else if(advance>=27'd50000000)begin phase<=wrapped[25:0];rtc_tick<=!rtc_tick;end
        else phase<=advance[25:0];
endmodule
`default_nettype wire
