// Asynchronous assertion, synchronous release and deterministic power-up reset.
module reset_release #(
    parameter integer HOLD_CYCLES = 1024
) (
    input wire clk,
    input wire ext_reset_n,
    output wire reset_n
);
    reg [1:0] sync_ff = 2'b00;
    reg [31:0] startup_count = 0;
    reg started = 1'b0;
    always @(posedge clk or negedge ext_reset_n) begin
        if (!ext_reset_n) begin
            sync_ff <= 0;
            startup_count <= 0;
            started <= 0;
        end else begin
            sync_ff <= {sync_ff[0], 1'b1};
            if (!sync_ff[1]) begin
                startup_count <= 0;
                started <= 0;
            end else if (!started) begin
                if (startup_count == HOLD_CYCLES-1)
                    started <= 1;
                else
                    startup_count <= startup_count + 1'b1;
            end
        end
    end
    assign reset_n = started;
endmodule
