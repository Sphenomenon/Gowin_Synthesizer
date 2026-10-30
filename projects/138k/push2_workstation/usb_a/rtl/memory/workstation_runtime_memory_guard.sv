`timescale 1ns/1ps

// One startup grant followed by fail-closed isolation. Only the common system
// reset may forget a grant or fault; backend/PLL recovery never rearms traffic.
module workstation_runtime_memory_guard #(
    parameter integer HEARTBEAT_TIMEOUT_CYCLES=500,
    parameter integer HEARTBEAT_BITS=32
) (
    input wire reset_ni,
    input wire clk_50m_i,
    input wire memory_clk_i,
    input wire backend_reset_ni,
    input wire backend_ready_i,
    output reg started_o,
    output reg fault_o,
    output wire start_ready_o,
    output wire mute_o,
    output wire channel_open_o,
    output wire clock_alive_o,
    output reg [1:0] fault_code_o
);
    localparam integer AGE_BITS=$clog2(HEARTBEAT_TIMEOUT_CYCLES+1);
    localparam [1:0] FAULT_BACKEND=2'd1, FAULT_CLOCK=2'd2;

    initial begin
        if (HEARTBEAT_TIMEOUT_CYCLES<8 || HEARTBEAT_BITS<4 || HEARTBEAT_BITS>32)
            $fatal(1,"invalid runtime memory guard parameters");
    end

    // Common reset assertion works even when either local clock is stopped.
    // Each local release waits for three edges of that particular clock.
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] control_reset_pre;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg control_reset_n;
    always @(posedge clk_50m_i or negedge reset_ni)
        if (!reset_ni) begin control_reset_pre<=0; control_reset_n<=0; end
        else begin control_reset_pre<={control_reset_pre[0],1'b1}; control_reset_n<=control_reset_pre[1]; end
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [1:0] memory_reset_pre;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg memory_reset_n;
    always @(posedge memory_clk_i or negedge reset_ni)
        if (!reset_ni) begin memory_reset_pre<=0; memory_reset_n<=0; end
        else begin memory_reset_pre<={memory_reset_pre[0],1'b1}; memory_reset_n<=memory_reset_pre[1]; end

    wire raw_available=backend_reset_ni && backend_ready_i;
    wire availability_reset_n=control_reset_n && raw_available;
    // Stretch any availability loss, including a pulse between both clocks.
    // Release takes three reference edges, so a granted loss is sampled by the
    // fault latch before it could release the memory-domain channel again.
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] availability_release;
    always @(posedge clk_50m_i or negedge availability_reset_n)
        if (!availability_reset_n) availability_release<=0;
        else availability_release<={availability_release[1:0],1'b1};
    wire available=availability_release[2];

    reg [HEARTBEAT_BITS-1:0] memory_binary;
    (* syn_preserve=1 *) reg [HEARTBEAT_BITS-1:0] memory_gray;
    wire [HEARTBEAT_BITS-1:0] memory_next=memory_binary+1'b1;
    always @(posedge memory_clk_i or negedge memory_reset_n)
        if (!memory_reset_n) begin memory_binary<=0; memory_gray<=0; end
        else begin memory_binary<=memory_next; memory_gray<=(memory_next>>1)^memory_next; end
    // Route memory_gray -> gray_meta with max-delay/skew bounded by one actual
    // memory clock period. Broad asynchronous false paths alone are inadequate.
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [HEARTBEAT_BITS-1:0] gray_meta,gray_sync;
    always @(posedge clk_50m_i or negedge control_reset_n)
        if (!control_reset_n) begin gray_meta<=0; gray_sync<=0; end
        else begin gray_meta<=memory_gray; gray_sync<=gray_meta; end
    reg [HEARTBEAT_BITS-1:0] previous_gray;
    reg heartbeat_seen;
    reg [AGE_BITS-1:0] heartbeat_age;
    wire heartbeat_changed=gray_sync!=previous_gray;
    assign clock_alive_o=heartbeat_seen &&
        (heartbeat_changed || heartbeat_age<AGE_BITS'(HEARTBEAT_TIMEOUT_CYCLES));
    always @(posedge clk_50m_i or negedge control_reset_n)
        if (!control_reset_n) begin
            previous_gray<=0; heartbeat_seen<=0;
            heartbeat_age<=AGE_BITS'(HEARTBEAT_TIMEOUT_CYCLES);
        end else begin
            previous_gray<=gray_sync;
            if (heartbeat_changed) begin heartbeat_seen<=1; heartbeat_age<=0; end
            else if (heartbeat_age<AGE_BITS'(HEARTBEAT_TIMEOUT_CYCLES))
                heartbeat_age<=heartbeat_age+1'b1;
        end

    reg armed;
    // Arm the fault latch before opening the memory gate, including the short
    // interval before the reference domain acknowledges that gate as started.
    always @(posedge clk_50m_i or negedge control_reset_n)
        if (!control_reset_n) begin armed<=0; fault_o<=0; fault_code_o<=0; end
        else begin
            if (!armed && available && clock_alive_o && !fault_o) armed<=1;
            if (armed && !fault_o) begin
                if (!available) begin fault_o<=1; fault_code_o<=FAULT_BACKEND; end
                else if (!clock_alive_o) begin fault_o<=1; fault_code_o<=FAULT_CLOCK; end
            end
        end

    wire channel_reset_n=memory_reset_n && raw_available && available && !fault_o;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] grant_release;
    always @(posedge memory_clk_i or negedge channel_reset_n)
        if (!channel_reset_n) grant_release<=0;
        else grant_release<={grant_release[1:0],armed};
    assign channel_open_o=grant_release[2];

    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg open_meta,open_ack;
    always @(posedge clk_50m_i or negedge control_reset_n)
        if (!control_reset_n) begin open_meta<=0; open_ack<=0; end
        else begin open_meta<=channel_open_o; open_ack<=open_meta; end
    always @(posedge clk_50m_i or negedge control_reset_n)
        if (!control_reset_n) started_o<=0;
        else if (open_ack && available && clock_alive_o && !fault_o) started_o<=1;

    assign start_ready_o=started_o && !fault_o && available && open_ack;
    assign mute_o=!start_ready_o;
endmodule
