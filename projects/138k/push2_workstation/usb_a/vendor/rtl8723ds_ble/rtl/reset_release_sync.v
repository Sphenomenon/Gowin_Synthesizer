module reset_release_sync (
    input wire clk,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) input wire arstn,
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *) output wire resetn
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] stages;
    always @(posedge clk or negedge arstn) begin
        if (!arstn) stages <= 2'b00;
        else stages <= {stages[0], 1'b1};
    end
    assign resetn = stages[1];
endmodule
