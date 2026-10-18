`timescale 1ns/1ps

// One-at-a-time 16-bit scratch access over the native 256-bit DDR BL8 port.
// Writes use the controller byte mask, so DP history never needs a read/modify/
// write cache.  Reads return the selected halfword after the native response.
module basic_pitch_ddr16_port (
    input  logic         clk_i,
    input  logic         rst_ni,
    input  logic         req_valid_i,
    input  logic         req_write_i,
    input  logic [31:0]  req_byte_addr_i,
    input  logic [15:0]  req_wdata_i,
    output logic         req_ready_o,
    output logic         rsp_valid_o,
    output logic [15:0]  rsp_rdata_o,
    output logic         ddr_req_o,
    output logic         ddr_write_o,
    output logic [28:0]  ddr_address_o,
    output logic [255:0] ddr_data_o,
    output logic [31:0]  ddr_mask_o,
    input  logic         ddr_ready_i,
    input  logic         ddr_response_i,
    input  logic [255:0] ddr_read_data_i
);
    logic read_pending;
    logic [3:0] read_lane;
    wire [3:0] request_lane = req_byte_addr_i[4:1];

    always_comb begin
        ddr_req_o = req_valid_i && !read_pending;
        ddr_write_o = req_write_i;
        // app_addr counts 32-bit DQ words.  Clear [2:0] for one aligned BL8.
        ddr_address_o = {req_byte_addr_i[30:5], 3'b000};
        ddr_data_o = 256'd0;
        ddr_data_o[request_lane*16 +: 16] = req_wdata_i;
        ddr_mask_o = 32'hffff_ffff;
        ddr_mask_o[request_lane*2 +: 2] = 2'b00;
        req_ready_o = ddr_req_o && ddr_ready_i;
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            read_pending <= 1'b0;
            read_lane <= 4'd0;
            rsp_valid_o <= 1'b0;
            rsp_rdata_o <= 16'd0;
        end else begin
            rsp_valid_o <= 1'b0;
            if (req_ready_o && !req_write_i) begin
                read_pending <= 1'b1;
                read_lane <= request_lane;
            end
            if (ddr_response_i && read_pending) begin
                rsp_rdata_o <= ddr_read_data_i[read_lane*16 +: 16];
                rsp_valid_o <= 1'b1;
                read_pending <= 1'b0;
            end
        end
    end
endmodule
