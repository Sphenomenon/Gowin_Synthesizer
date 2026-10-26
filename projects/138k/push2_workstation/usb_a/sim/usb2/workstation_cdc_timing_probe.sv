module custom_cdc_timing_probe (
    input wire clk_cpu,
    input wire clk_ulpi,
    input wire reset_n,
    output wire observed
);
    custom_cdc_probe_crossing crossing (
        .clk_cpu(clk_cpu), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .observed(observed)
    );
endmodule

module custom_cdc_probe_crossing (
    input wire clk_cpu,
    input wire clk_ulpi,
    input wire reset_n,
    output wire observed
);
    (* async_reg = "true" *) reg [1:0] cpu_release_q, ulpi_release_q;
    (* async_reg = "true" *) reg [1:0] request_sync_q, result_sync_q;
    reg request_toggle_q, result_toggle_q;
    reg [3:0] descriptor_cpu_q, descriptor_ulpi_q;

    assign observed = ^descriptor_ulpi_q;

    always @(posedge clk_cpu or negedge reset_n)
        if (!reset_n) cpu_release_q <= 0;
        else cpu_release_q <= {cpu_release_q[0], 1'b1};
    always @(posedge clk_ulpi or negedge reset_n)
        if (!reset_n) ulpi_release_q <= 0;
        else ulpi_release_q <= {ulpi_release_q[0], 1'b1};

    always @(posedge clk_cpu or negedge cpu_release_q[1]) begin
        if (!cpu_release_q[1]) begin
            result_sync_q <= 0;
            descriptor_cpu_q <= 0;
            request_toggle_q <= 0;
        end else begin
            result_sync_q <= {result_sync_q[0], result_toggle_q};
            if (result_sync_q[1] == request_toggle_q) begin
                descriptor_cpu_q <= descriptor_cpu_q + 1'b1;
                request_toggle_q <= !request_toggle_q;
            end
        end
    end

    always @(posedge clk_ulpi or negedge ulpi_release_q[1]) begin
        if (!ulpi_release_q[1]) begin
            request_sync_q <= 0;
            descriptor_ulpi_q <= 0;
            result_toggle_q <= 0;
        end else begin
            request_sync_q <= {request_sync_q[0], request_toggle_q};
            if (request_sync_q[1] != result_toggle_q) begin
                descriptor_ulpi_q <= descriptor_cpu_q;
                result_toggle_q <= request_sync_q[1];
            end
        end
    end
endmodule
