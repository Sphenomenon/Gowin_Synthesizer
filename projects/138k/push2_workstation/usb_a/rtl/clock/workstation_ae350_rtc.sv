`default_nettype none
// 32.768 kHz average from the board's 50 MHz reference. Each half-period is
// 762 or 763 reference cycles; edge phase error stays below one reference tick.
// This independent, always-running RTC must not depend on CPU/APB activity.
module workstation_ae350_rtc(
    input wire clk_50m,reset_n,
    output wire rtc_clk
);
    reg [25:0] phase;
    (* syn_keep=1,syn_preserve=1 *) reg rtc_tick;
    initial begin phase=0;rtc_tick=0;end
    // phase < 50,000,000, so the sum also fits in 26 bits.
    wire [25:0] advance=phase+26'd65536;
    assign rtc_clk=rtc_tick;
    always @(posedge clk_50m or negedge reset_n)
        if(!reset_n)begin phase<=0;rtc_tick<=0;end
        else if(advance>=26'd50000000)begin phase<=advance-26'd50000000;rtc_tick<=!rtc_tick;end
        else phase<=advance;
endmodule
`default_nettype wire
