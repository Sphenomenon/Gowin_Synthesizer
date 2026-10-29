module workstation_usb1_clock (
    input wire clk_50m,
    output wire clk_48m, locked_o, reset_n_o
);
    reg [9:0] power_count_q=0;
    wire power_ready=&power_count_q;
    always @(posedge clk_50m)
        if (!power_ready) power_count_q<=power_count_q+1'b1;
    gw138k_cpu_pll_cell #(.OUTPUT_DIV0(25),.OUTPUT1_ENABLE("FALSE")) pll (
        .clkin(clk_50m),.init_clk(clk_50m),.reset(!power_ready),.enable0(1'b1),
        .lock(locked_o),.clkout0(clk_48m),.clkout1()
    );
    wire qualified=power_ready&&locked_o;
    (* ASYNC_REG="TRUE",syn_preserve=1 *)reg[2:0]release_q=0;
    always @(posedge clk_48m or negedge qualified)
        if(!qualified)release_q<=0;else release_q<={release_q[1:0],1'b1};
    assign reset_n_o=release_q[2];
endmodule
