// Existing USB/CPU round-robin merge with an unbuffered USB lifecycle lane.
// Lifecycle cancellation clears the old registered item before normal traffic
// resumes. This preserves immediate PANIC even when the audio core is busy.
module gw138k_usb_lifecycle_merge #(parameter EXPLICIT_LIFECYCLE=0) (
    input wire clk,reset_n,g1_valid,pc_valid,cpu_valid,
    input wire [17:0] g1_data,pc_data,cpu_data,
    input wire g1_lifecycle,g1_cancel,
    output wire g1_ready,pc_ready,cpu_ready,
    output wire event_valid,output wire [17:0] event_data,input wire event_ready
);
    // Explicit flags come from local lifecycle state, never the MIDI RAM DO.
    // Retain the legacy port contract for standalone callers only.
    wire lifecycle=g1_valid && (EXPLICIT_LIFECYCLE ? g1_lifecycle : g1_data[17:14]==4'd15);
    wire cancel=lifecycle && (EXPLICIT_LIFECYCLE ? g1_cancel : g1_data[6:0]<3);
    wire normal_valid,normal_g1_ready,normal_pc_ready,normal_cpu_ready;
    wire [17:0] normal_data;
    assign event_valid=lifecycle || normal_valid;
    assign event_data=lifecycle ? g1_data : normal_data;
    assign g1_ready=lifecycle ? event_ready : normal_g1_ready;
    assign pc_ready=!lifecycle && normal_pc_ready;
    assign cpu_ready=!lifecycle && normal_cpu_ready;
    gw138k_three_event_arbiter queue(
        .clk(clk),.reset_n(reset_n),
        .g1_valid(g1_valid && !lifecycle),.g1_data(g1_data),.g1_ready(normal_g1_ready),
        .pc_valid(pc_valid && !lifecycle),.pc_data(pc_data),.pc_ready(normal_pc_ready),
        .cpu_valid(cpu_valid && !lifecycle),.cpu_data(cpu_data),.cpu_ready(normal_cpu_ready),
        .event_valid(normal_valid),.event_data(normal_data),
        .event_ready(cancel || (!lifecycle && event_ready)));
endmodule
