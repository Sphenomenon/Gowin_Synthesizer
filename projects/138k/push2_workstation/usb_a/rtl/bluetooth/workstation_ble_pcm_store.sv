`include "src/memory/ddr_address_map.vh"

// One ordered command stream carries capture writes and download prefetches.
// Capture never waits for DDR: overflow fails the recording via fault_o.
// The 8 KiB download cache preserves the codec's synchronous sample interface.
// Experimental short-store component, unselected by paired profiles. The
// established common FIFO stays unchanged; its physical RAM mapping must be
// remeasured before this alternative backend can be integrated.
module workstation_ble_pcm_store (
    input wire clk_i, rst_ni, memory_clk_i, memory_rst_ni, memory_ready_i,
    input wire write_i,
    input wire [13:0] write_frame_i,
    input wire [31:0] write_pcm_i,
    input wire fetch_i,
    input wire [31:0] fetch_byte_i,
    input wire [12:0] fetch_bytes_i,
    output wire fetched_o, ready_o, fault_o,
    input wire [13:0] read_frame_i,
    output reg [31:0] read_pcm_o,
    output wire req_o, write_o,
    output wire [28:0] address_o,
    output wire [255:0] data_o,
    output wire [31:0] mask_o,
    input wire req_ready_i, response_i,
    input wire [255:0] response_data_i
);
    wire reset_pair=rst_ni && memory_rst_ni;
    (* ASYNC_REG="TRUE" *) reg ready_meta, ready_sync;
    always @(posedge clk_i or negedge reset_pair)
        if(!reset_pair) begin ready_meta<=0;ready_sync<=0;end
        else begin ready_meta<=memory_ready_i;ready_sync<=ready_meta;end
    assign ready_o=ready_sync;
    reg [2:0] phase;
    localparam IDLE=0, REQUEST=1, RESPONSE=2, FILL=3, DONE=4;
    reg [13:0] fetch_frame, last_frame, cache_base;
    reg [10:0] fill_index;
    reg [2:0] lane;
    reg [255:0] beat;
    reg cancelled;
    wire command_valid=write_i || phase==REQUEST;
    wire command_ready, queued_valid, queued_ready;
    wire [46:0] command={write_i,write_i ? write_frame_i : fetch_frame,write_pcm_i};
    wire [46:0] queued;
    wire [255:0] returned;
    wire returned_valid, returned_ready, response_room;
    music_async_fifo #(.WIDTH(47),.ADDRESS_BITS(4)) u_commands (
        .write_clk_i(clk_i),.write_rst_ni(reset_pair),
        .write_valid_i(command_valid && ready_sync),.write_ready_o(command_ready),.write_data_i(command),
        .read_clk_i(memory_clk_i),.read_rst_ni(reset_pair),
        .read_valid_o(queued_valid),.read_ready_i(queued_ready),.read_data_o(queued));
    reg read_pending;
    assign req_o=queued_valid && !read_pending && memory_ready_i && (queued[46] || response_room);
    assign queued_ready=req_o && req_ready_i;
    assign write_o=queued[46];
    assign address_o=`PRJ1_DDR_BLE_PCM_APP_BASE+{15'd0,queued[45:35],3'b000};
    assign data_o={8{queued[31:0]}};
    assign mask_o=~(32'hf << {queued[34:32],2'b00});
    always @(posedge memory_clk_i or negedge reset_pair)
        if(!reset_pair) read_pending<=0;
        else if(response_i) read_pending<=0;
        else if(queued_ready && !write_o) read_pending<=1;
    music_async_fifo #(.WIDTH(256),.ADDRESS_BITS(2)) u_responses (
        .write_clk_i(memory_clk_i),.write_rst_ni(reset_pair),
        .write_valid_i(response_i),.write_ready_o(response_room),.write_data_i(response_data_i),
        .read_clk_i(clk_i),.read_rst_ni(reset_pair),
        .read_valid_o(returned_valid),.read_ready_i(returned_ready),.read_data_o(returned));
    assign returned_ready=phase==RESPONSE;
    assign fault_o=write_i && (!ready_sync || !command_ready);
    assign fetched_o=phase==DONE && !cancelled;
    (* syn_ramstyle="block_ram" *) reg [31:0] cache[0:2047];
    always @(posedge clk_i) begin
        if(phase==FILL) cache[fill_index]<=beat[31:0];
        read_pcm_o<=cache[(read_frame_i-cache_base)&14'h7ff];
    end
    always @(posedge clk_i or negedge reset_pair) begin
        if(!reset_pair) begin
            phase<=IDLE;fetch_frame<=0;last_frame<=0;cache_base<=0;fill_index<=0;lane<=0;beat<=0;cancelled<=0;
        end else begin
        // Drain an abandoned read before accepting another fetch. Disconnect
        // or a new recording cannot turn an old response into a new cache hit.
        if(!fetch_i && phase!=IDLE) cancelled<=1;
        case(phase)
            IDLE: if(fetch_i && ready_sync) begin
                // Include the offset inside the first DDR beat. Max payload
                // 8112 bytes plus 28-byte alignment fits the 8192-byte cache.
                cache_base<={fetch_byte_i[15:5],3'b000};
                fetch_frame<={fetch_byte_i[15:5],3'b000};
                last_frame<=(fetch_byte_i+fetch_bytes_i-1)>>2;
                fill_index<=0;phase<=REQUEST;cancelled<=0;
            end
            REQUEST: if(!write_i && command_ready && ready_sync) phase<=RESPONSE;
            RESPONSE: if(returned_valid) begin beat<=returned;lane<=0;phase<=FILL;end
            FILL: begin
                beat<=beat>>32;fill_index<=fill_index+1'b1;
                if(lane==7) begin
                    if(fetch_frame+14'd7>=last_frame) phase<=cancelled || !fetch_i ? IDLE : DONE;
                    else begin fetch_frame<=fetch_frame+14'd8;phase<=REQUEST;end
                end else lane<=lane+1'b1;
            end
            DONE: if(!fetch_i || write_i) phase<=IDLE;
            default:phase<=IDLE;
        endcase
        end
    end
endmodule
