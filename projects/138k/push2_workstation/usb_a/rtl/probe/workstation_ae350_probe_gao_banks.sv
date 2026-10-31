`default_nettype none
// Same-domain serializer of the already published atomic UART snapshot.
// Only a new UART sequence may replace the frozen bank, at a sweep boundary.
module workstation_ae350_probe_gao_banks #(
    parameter [31:0] USER_CODE=0
)(
    input wire clk_50m,reset_n,
    input wire [2079:0] full_snapshot_50mhz,
    input wire snapshot_published_50mhz,
    input wire [31:0] digital_io_50mhz,health_50mhz,
    output wire [703:0] sample_50mhz
);
    reg [2079:0] frozen_snapshot=0;
    reg [31:0] frozen_io=0,frozen_health=0;
    reg frozen_valid=0;
    reg [1:0] page=0,dwell=0;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            frozen_snapshot<=0;frozen_io<=0;frozen_health<=0;frozen_valid<=0;
            page<=0;dwell<=0;
        end else if(dwell==3) begin
            dwell<=0;page<=page+1'b1;
            if(page==3 && snapshot_published_50mhz &&
               (!frozen_valid || full_snapshot_50mhz[2079:2048]!=frozen_snapshot[2079:2048])) begin
                frozen_snapshot<=full_snapshot_50mhz;
                frozen_io<=digital_io_50mhz;frozen_health<=health_50mhz;frozen_valid<=1;
            end
        end else dwell<=dwell+1'b1;
    end
    // Word19: page count, total words, page words, reserved, valid, page.
    wire [31:0] metadata={8'd4,8'd64,8'd16,5'd0,frozen_valid,page};
    assign sample_50mhz={frozen_health,frozen_io,metadata,32'ha1386402,USER_CODE,
        frozen_snapshot[2079:2048],frozen_snapshot[page*512+:512]};
endmodule
`default_nettype wire
