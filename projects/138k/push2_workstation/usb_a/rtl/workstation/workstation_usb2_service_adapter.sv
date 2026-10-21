module workstation_usb2_service_adapter (
    input wire clk_cpu, reset_n, session_valid_i, owner_connected_i,
    input wire service_valid_i, service_write_i,
    input wire [7:0] service_address_i,
    input wire [31:0] service_write_data_i,
    input wire [3:0] service_mask_i,
    output wire service_ready_o, service_error_o,
    output wire [31:0] service_read_data_o,
    output wire owner_select_o, owner_write_o,
    output wire [7:0] owner_address_o,
    output wire [31:0] owner_write_data_o,
    input wire owner_ready_i,
    input wire [31:0] owner_read_data_i,
    output reg [31:0] canceled_requests_o
);
    localparam [1:0] IDLE = 0, REQUEST = 1, RELEASE = 2;
    reg [1:0] state_q;
    reg write_q, illegal_q;
    reg [7:0] address_q;
    reg [31:0] data_q;
    wire detach = !session_valid_i && owner_connected_i;
    wire needs_session = write_q && (address_q == 8'h04 || address_q == 8'h54 ||
                                    (address_q == 8'h00 && data_q[0]));
    wire stale_request = needs_session && (!session_valid_i ||
                          ((address_q == 8'h04 || address_q == 8'h54) && !owner_connected_i));
    wire request = reset_n && state_q == REQUEST && service_valid_i;
    wire rejected = illegal_q || stale_request;

    function automatic valid_read(input [7:0] address);
        case (address)
            8'h00, 8'h10, 8'h14, 8'h18, 8'h1c, 8'h20, 8'h24, 8'h2c,
            8'h30, 8'h34, 8'h38, 8'h3c, 8'h40, 8'h4c, 8'h58, 8'h5c,
            8'h60, 8'h64, 8'h68, 8'h6c: valid_read = 1;
            default: valid_read = 0;
        endcase
    endfunction

    function automatic valid_write(input [7:0] address);
        case (address)
            8'h00, 8'h04, 8'h08, 8'h28, 8'h30, 8'h34, 8'h44, 8'h48,
            8'h54, 8'h58: valid_write = 1;
            default: valid_write = 0;
        endcase
    endfunction

    assign owner_select_o = reset_n && (detach || (request && !rejected));
    assign owner_write_o = detach || write_q;
    assign owner_address_o = detach ? 8'h00 : address_q;
    assign owner_write_data_o = detach ? 32'd0 : data_q;
    assign service_ready_o = request && !detach && (rejected || owner_ready_i);
    assign service_error_o = service_ready_o && illegal_q;
    assign service_read_data_o = rejected ? 32'd0 : owner_read_data_i;

    always @(posedge clk_cpu or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= IDLE; write_q <= 0; address_q <= 0; data_q <= 0; illegal_q <= 0;
            canceled_requests_o <= 0;
        end else begin
            if (state_q == REQUEST && ((!service_valid_i) ||
                (service_ready_o && stale_request && !illegal_q)) && canceled_requests_o != 32'hffffffff)
                canceled_requests_o <= canceled_requests_o + 1'b1;
            case (state_q)
                IDLE: if (service_valid_i) begin
                    write_q <= service_write_i;
                    address_q <= service_address_i;
                    data_q <= service_write_data_i;
                    illegal_q <= service_address_i[1:0] != 0 ||
                                 (service_write_i ? service_mask_i != 15 || !valid_write(service_address_i) :
                                                    !valid_read(service_address_i));
                    state_q <= REQUEST;
                end
                REQUEST: begin
                    if (!service_valid_i) state_q <= IDLE;
                    else if (service_ready_o) state_q <= RELEASE;
                end
                RELEASE: if (!service_valid_i) state_q <= IDLE;
                default: state_q <= IDLE;
            endcase
        end
    end
endmodule
