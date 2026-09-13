`default_nettype none
// The vendor PHY does not restart its calibration FSM on every PLL lock loss.
// Arm only after calibration, then force a complete controller/PLL reset.
module ddr_recovery_guard #(
    parameter integer RESET_CYCLES = 256 // 5.12 us at 50 MHz
) (
    input wire clk, reset_n, pll_locked, calibrated,
    output reg controller_reset_n,
    output wire lock_stable
);
    localparam integer COUNT_WIDTH = RESET_CYCLES < 2 ? 1 : $clog2(RESET_CYCLES);
    localparam [COUNT_WIDTH-1:0] LAST_COUNT = RESET_CYCLES-1;
    reg [COUNT_WIDTH-1:0] reset_count;
    reg armed;
    reg calibrated_meta, calibrated_sync;
    reg [1:0] lock_observed;
    reg [1:0] health_observed;
    wire lock_observe_reset_n = reset_n && pll_locked;
    // Cover loss immediately after CALIB rises, before its normal status
    // synchronizer can arm the monitor. A conservative restart is safe.
    wire health_reset_n = reset_n && (pll_locked || !calibrated);
    // A short loss between clk edges clears both stages immediately. Their
    // two-cycle recovery gives the controller FSM time to latch the restart.
    always @(posedge clk or negedge lock_observe_reset_n) begin
        if(!lock_observe_reset_n) lock_observed<=0;
        else lock_observed<={lock_observed[0],1'b1};
    end
    always @(posedge clk or negedge health_reset_n) begin
        if(!health_reset_n) health_observed<=0;
        else health_observed<={health_observed[0],1'b1};
    end
    assign lock_stable=lock_observed[1];
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            controller_reset_n<=0;reset_count<=LAST_COUNT;armed<=0;
            calibrated_meta<=0;calibrated_sync<=0;
        end else begin
            calibrated_meta<=calibrated;calibrated_sync<=calibrated_meta;
            if(!controller_reset_n) begin
                armed<=0;calibrated_meta<=0;calibrated_sync<=0;
                if(reset_count==0) controller_reset_n<=1;
                else reset_count<=reset_count-1'b1;
            end else if((armed && !lock_stable) || !health_observed[1]) begin
                controller_reset_n<=0;reset_count<=LAST_COUNT;armed<=0;
            end else if(calibrated_sync && lock_stable) armed<=1;
        end
    end
endmodule
`default_nettype wire
