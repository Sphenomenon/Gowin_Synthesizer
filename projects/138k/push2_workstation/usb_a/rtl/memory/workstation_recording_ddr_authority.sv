`timescale 1ns/1ps
`default_nettype none
// One controller/ledger epoch per common root reset. The existing guard owns
// clock qualification and post-grant loss; survival closes its pre-grant gap.
module workstation_recording_ddr_authority #(
    parameter integer HEARTBEAT_TIMEOUT_CYCLES=500,
    parameter integer HEARTBEAT_BITS=32
)(
    input wire root_reset_ni,control_clk_i,memory_clk_i,
    input wire ledger_reset_ni,backend_ready_i,
    output wire channel_ready_o,started_o,fault_o,epoch_lost_o,
    output wire boot_seen_o,epoch_survived_o
);
    // The real ledger may first leave reset only after this local root
    // release. e855 provides three platform UI and three HDMI UI edges.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] root_release;
    always @(posedge memory_clk_i or negedge root_reset_ni)
        if(!root_reset_ni)root_release<=0;
        else root_release<={root_release[0],1'b1};
    wire root_memory_reset_n=root_release[1];

    // Never reset boot_seen for UI/PLL/calibration/BIST/client recovery.
    reg boot_seen;
    always @(posedge memory_clk_i or negedge root_memory_reset_n)
        if(!root_memory_reset_n)boot_seen<=0;
        else if(ledger_reset_ni)boot_seen<=1;

    // A single ordinary async-clear flop suffices. Both flops rise on the
    // first globally usable memory edge; after that, a ledger reset clears
    // survival even with a stopped clock and boot_seen forbids setting it.
    reg epoch_survived;
    wire survival_reset_n=root_memory_reset_n && ledger_reset_ni;
    always @(posedge memory_clk_i or negedge survival_reset_n)
        if(!survival_reset_n)epoch_survived<=0;
        else if(!boot_seen)epoch_survived<=1;

    wire guard_channel,guard_fault;
    workstation_runtime_memory_guard #(
        .HEARTBEAT_TIMEOUT_CYCLES(HEARTBEAT_TIMEOUT_CYCLES),
        .HEARTBEAT_BITS(HEARTBEAT_BITS)
    ) guard(
        .reset_ni(root_reset_ni),.clk_50m_i(control_clk_i),.memory_clk_i(memory_clk_i),
        .backend_reset_ni(ledger_reset_ni),
        .backend_ready_i(backend_ready_i && epoch_survived),
        .started_o(started_o),.fault_o(guard_fault),.start_ready_o(),.mute_o(),
        .channel_open_o(guard_channel),.clock_alive_o(),.fault_code_o());
    assign boot_seen_o=boot_seen;
    assign epoch_survived_o=epoch_survived;
    assign epoch_lost_o=boot_seen && !epoch_survived;
    assign fault_o=guard_fault || epoch_lost_o;
    // Final raw survival gate is deliberate: closure does not wait for either
    // a reference-clock fault latch or the memory clock to resume.
    assign channel_ready_o=guard_channel && epoch_survived;
endmodule
`default_nettype wire
