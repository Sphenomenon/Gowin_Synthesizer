// One-entry command buffer between the TF DMA and the shared DDR arbiter.
// It isolates the DMA's ring-capacity arithmetic from other clients' ready
// paths. Reads retain the arbiter's normal response ordering.
module tf_audio_ddr_command_buffer (
    input wire clk,rst_n,
    input wire in_valid,in_write,
    input wire [28:0] in_address,
    input wire [255:0] in_data,
    output wire in_ready,
    output wire out_valid,out_write,
    output wire [28:0] out_address,
    output wire [255:0] out_data,
    input wire out_ready
);
    reg full;
    reg write_q;
    reg [28:0] address_q;
    reg [255:0] data_q;
    assign in_ready=!full;
    assign out_valid=full;
    assign out_write=write_q;
    assign out_address=address_q;
    assign out_data=data_q;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            full<=0;write_q<=0;address_q<=0;data_q<=0;
        end else if(full && out_ready) full<=0;
        else if(!full && in_valid) begin
            full<=1;
            write_q<=in_write;
            address_q<=in_address;
            data_q<=in_data;
        end
    end
endmodule
