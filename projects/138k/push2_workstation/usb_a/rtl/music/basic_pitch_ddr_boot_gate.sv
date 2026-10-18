`timescale 1ns/1ps
// Stagger initial DDR calibration until the auxiliary clock trees have settled.
// After release, only global reset closes this gate; DDR lock-loss recovery
// remains owned by the unmodified platform guard.
module basic_pitch_ddr_boot_gate #(
    parameter integer HOLD_CYCLES=5_000_000
) (
    input wire clk_i,rst_ni,aux_ready_i,
    output wire memory_rst_no
);
    localparam integer COUNT_BITS=HOLD_CYCLES<2?1:$clog2(HOLD_CYCLES+1);
    (* ASYNC_REG="TRUE" *) reg ready_meta=0,ready_sync=0;
    reg [COUNT_BITS-1:0] count=0;
    reg released=0;
    initial if(HOLD_CYCLES<1 || HOLD_CYCLES>50_000_000)
        $fatal(1,"DDR boot hold cycles must be1..50000000");
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin ready_meta<=0;ready_sync<=0;end
        else begin ready_meta<=aux_ready_i;ready_sync<=ready_meta;end
    end
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin count<=0;released<=0;end
        else if(!released)begin
            if(!ready_sync)count<=0;
            else if(count==HOLD_CYCLES-1)released<=1;
            else count<=count+1'b1;
        end
    end
    assign memory_rst_no=rst_ni && released;
endmodule
