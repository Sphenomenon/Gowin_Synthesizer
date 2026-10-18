// Two already-decoded event sources. Each source retains its own parser;
// nothing inserts bytes into G1's running-status stream. A held output stage
// preserves data through backpressure; round robin prevents starvation.
module gw138k_event_arbiter (
    input wire clk,reset_n,
    input wire g1_valid,cpu_valid,
    input wire [17:0] g1_data,cpu_data,
    output wire g1_ready,cpu_ready,
    output reg event_valid,
    output reg [17:0] event_data,
    input wire event_ready
);
    reg prefer_cpu;
    wire take_cpu=cpu_valid && (!g1_valid || prefer_cpu);
    wire room=!event_valid || event_ready;
    assign cpu_ready=room && take_cpu;
    assign g1_ready=room && !take_cpu;
    always @(posedge clk or negedge reset_n)
        if(!reset_n) begin prefer_cpu<=0;event_valid<=0;event_data<=0;end
        else if(room) begin
            event_valid<=g1_valid || cpu_valid;
            if(g1_valid || cpu_valid) begin
                event_data<=take_cpu?cpu_data:g1_data;
                prefer_cpu<=!take_cpu;
            end
        end
endmodule
