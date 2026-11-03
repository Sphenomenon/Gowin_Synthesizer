// Fair two-client composition behind one existing DDR owner. A read owns its
// response until completion; writes are accepted in order without extra RAM.
module workstation_ddr_pair (
    input wire clk_i, rst_ni,
    input wire a_req_i, a_write_i, b_req_i, b_write_i,
    input wire [28:0] a_address_i, b_address_i,
    input wire [255:0] a_data_i, b_data_i,
    input wire [31:0] a_mask_i, b_mask_i,
    output wire a_ready_o, b_ready_o, a_response_o, b_response_o,
    output wire req_o, write_o,
    output wire [28:0] address_o,
    output wire [255:0] data_o,
    output wire [31:0] mask_o,
    input wire ready_i, response_i
);
    reg waiting, owner, prefer_b, locked, locked_b;
    wire select_b=locked ? locked_b : b_req_i && (!a_req_i || prefer_b);
    assign req_o=!waiting && (a_req_i || b_req_i);
    assign write_o=select_b ? b_write_i : a_write_i;
    assign address_o=select_b ? b_address_i : a_address_i;
    assign data_o=select_b ? b_data_i : a_data_i;
    assign mask_o=select_b ? b_mask_i : a_mask_i;
    wire accepted=req_o && ready_i;
    assign a_ready_o=accepted && !select_b;
    assign b_ready_o=accepted && select_b;
    assign a_response_o=response_i && waiting && !owner;
    assign b_response_o=response_i && waiting && owner;
    always @(posedge clk_i or negedge rst_ni)
        if(!rst_ni) begin waiting<=0;owner<=0;prefer_b<=0;locked<=0;locked_b<=0;end
        else if(waiting) begin if(response_i) waiting<=0;end
        else if(accepted) begin
            locked<=0;
            prefer_b<=!select_b;
            if(!write_o) begin waiting<=1;owner<=select_b;end
        end else if(req_o) begin
            locked<=1;locked_b<=select_b;
        end
endmodule
