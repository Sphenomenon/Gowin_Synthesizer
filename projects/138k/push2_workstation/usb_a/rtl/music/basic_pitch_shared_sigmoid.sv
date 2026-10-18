`timescale 1ns/1ps

// One physical sigmoid table shared by the three mutually-exclusive heads.
module basic_pitch_shared_sigmoid (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        req_i,
    input  logic [11:0] addr_i,
    output logic        ready_o,
    output logic        rsp_valid_o,
    output logic [15:0] rdata_o
);
    (* ram_style = "block", syn_ramstyle = "block_ram" *)
    logic [15:0] lut [0:4095];
    initial $readmemh("rtl/music/weights/sigmoid_lut.mem", lut);
    assign ready_o = 1'b1;
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            rsp_valid_o <= 1'b0;
            rdata_o <= 16'd0;
        end else begin
            rsp_valid_o <= req_i;
            if (req_i) rdata_o <= lut[addr_i];
        end
    end
endmodule
