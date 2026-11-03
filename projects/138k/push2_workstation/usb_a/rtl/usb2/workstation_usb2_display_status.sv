`default_nettype none
// Observation only. The input owner and host retain all USB authority.
module workstation_usb2_display_status #(
    parameter integer STALE_CYCLES=4800000
) (
    input wire cpu_clk,ulpi_clk,reset_n,
    input wire [2:0] device_state,
    input wire [3:0] cpu_fault,
    input wire failed,traffic_enable,transaction_ready,high_speed,
    output wire [7:0] status
);
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] ulpi_release;
    always @(posedge ulpi_clk or negedge reset_n)
        if(!reset_n)ulpi_release<=0;
        else ulpi_release<={ulpi_release[0],1'b1};
    // Host status levels originate in reference, CPU and ULPI domains.
    // Synchronize them before publishing one coherent ULPI-side snapshot.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] link_meta,link_sync;
    always @(posedge ulpi_clk or negedge ulpi_release[1])
        if(!ulpi_release[1])begin link_meta<=0;link_sync<=0;end
        else begin
            link_meta<={failed,traffic_enable,transaction_ready,high_speed};
            link_sync<=link_meta;
        end
    wire valid;
    wire [3:0] link;
    gw138k_stream_cdc #(.WIDTH(4)) link_cdc(
        .reset_n(reset_n),.source_clk(ulpi_clk),.destination_clk(cpu_clk),
        .source_valid(1'b1),.source_data(link_sync),
        .destination_valid(valid),.destination_data(link),.drop_count());
    localparam integer AGE_BITS=$clog2(STALE_CYCLES+1);
    reg [AGE_BITS-1:0] age;
    reg seen,fresh;
    always @(posedge cpu_clk or negedge reset_n)
        if(!reset_n)begin age<=0;seen<=0;fresh<=0;end
        else if(valid)begin age<=0;seen<=1;fresh<=1;end
        else if(age<STALE_CYCLES-1)age<=age+1'b1;
        else fresh<=0;
    // A stopped ULPI clock cannot keep advertising the previous device.
    // Startup has no link; a previously live snapshot expiring is an error.
    assign status={|cpu_fault,(seen && !fresh) || (fresh && link[3]),
                   fresh && link[2],fresh && link[1],fresh && link[0],device_state};
endmodule
`default_nettype wire
