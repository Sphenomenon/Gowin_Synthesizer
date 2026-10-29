module workstation_usb1_diagnostics #(
    parameter [31:0] BUILD_ID = 32'hC11028F1
)(
    input wire clk_usb, reset_n, session_valid_i,
    input wire service_valid_i, service_write_i,
    input wire [7:0] service_address_i,
    input wire [31:0] service_write_data_i,
    input wire [3:0] service_mask_i,
    output wire service_ready_o, service_error_o,
    output reg [31:0] service_read_data_o,
    output reg [2:0] device_flags_o,
    output reg [31:0] identity_o, protocol_status_o, midi_count_o,
    output wire midi_valid_o,
    input wire midi_ready_i,
    output wire [31:0] midi_data_o
);
    wire midi_write = service_write_i && (service_address_i == 8'h54 || service_address_i == 8'h04);
    assign midi_valid_o = reset_n && session_valid_i && service_valid_i && midi_write && device_flags_o[0];
    assign midi_data_o = service_write_data_i;
    assign service_ready_o = !midi_valid_o || midi_ready_i;
    assign service_error_o = service_write_i && service_mask_i != 4'hf;
    always @* begin
        service_read_data_o = 0;
        case (service_address_i)
            8'h00: service_read_data_o = {29'd0, device_flags_o};
            8'h70: service_read_data_o = identity_o;
            8'h74: service_read_data_o = protocol_status_o;
            8'h78: service_read_data_o = midi_count_o;
            8'h7c: service_read_data_o = BUILD_ID;
            default: service_read_data_o = 0;
        endcase
    end
    always @(posedge clk_usb or negedge reset_n)
        if (!reset_n) begin
            device_flags_o <= 0;
            identity_o <= 0;
            protocol_status_o <= 0;
            midi_count_o <= 0;
        end else if (!session_valid_i) begin
            device_flags_o <= 0;
            identity_o <= 0;
            protocol_status_o <= 0;
        end else if (service_valid_i && service_ready_o && !service_error_o && service_write_i) begin
            case (service_address_i)
                8'h00: begin
                    device_flags_o <= service_write_data_i[2:0];
                    if (!service_write_data_i[0]) begin identity_o <= 0; protocol_status_o <= 0; end
                end
                8'h70: if (device_flags_o[0]) identity_o <= service_write_data_i;
                8'h74: if (device_flags_o[0]) protocol_status_o <= service_write_data_i;
                8'h54, 8'h04: if (device_flags_o[0] && midi_count_o != 32'hffffffff)
                    midi_count_o <= midi_count_o + 1'b1;
                default: begin end
            endcase
        end
endmodule
