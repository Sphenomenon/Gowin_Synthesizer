`timescale 1ns/1ps
// Validated-transport -> existing single recording engine adapter, clk_i only.
// frame_valid_i is a one-cycle delivery attempt, not a held ready/valid offer.
// A transport may issue it only with a credit (frame_ready_o). Ignoring credits
// fails this recording source; it can never stall M's physical sample schedule.
// This module does not implement LCD pins, packet CRC, resampling or a recorder.
module workstation_task3_record_ingress #(
    parameter integer FIFO_ADDRESS_BITS=8,
    parameter integer MIN_FRAME_CYCLES=5,
    parameter integer SOURCE_LEASE_CYCLES=200000
) (
    input wire clk_i,reset_ni,link_ready_i,panic_i,transport_fault_i,object_idle_i,
    input wire cancel_valid_i,
    input wire [31:0] cancel_session_i,cancel_generation_i,
    input wire arm_valid_i,
    output wire arm_ready_o,
    input wire [31:0] arm_session_i,arm_generation_i,arm_physical_epoch_i,arm_first_sequence_i,
    input wire [7:0] arm_format_i,
    output reg arm_accepted_o,arm_rejected_o,
    input wire frame_valid_i,
    output wire frame_ready_o,
    input wire [31:0] frame_session_i,frame_generation_i,frame_physical_epoch_i,
    input wire [31:0] frame_sequence_i,frame_pcm_i,
    input wire frame_44k1_i,frame_error_i,
    output wire pcm_valid_o,source_allowed_o,
    output wire [31:0] pcm_pair_o,
    output reg [31:0] pcm_sequence_o,
    output wire [31:0] physical_sequence_o,
    output reg [31:0] session_o,generation_o,physical_epoch_o,
    output reg armed_o,fault_o,
    // 1 overflow,2 identity/sequence/format,3 link/transport,4 source lease,
    // 5 PANIC,6 matching cancellation. Higher generation and retired object
    // are both mandatory for rearm; stale cancellation cannot kill a new arm.
    output reg [3:0] failure_code_o,
    output wire [FIFO_ADDRESS_BITS:0] queued_frames_o,
    output reg [31:0] accepted_frames_o,delivered_frames_o
);
    localparam integer DEPTH=1<<FIFO_ADDRESS_BITS;
    localparam integer GAP_BITS=$clog2(MIN_FRAME_CYCLES+1);
    localparam integer AGE_BITS=$clog2(SOURCE_LEASE_CYCLES+1);
    initial if(FIFO_ADDRESS_BITS<2 || FIFO_ADDRESS_BITS>8 || MIN_FRAME_CYCLES<5 || SOURCE_LEASE_CYCLES<16)
        $fatal(1,"invalid bounded recording ingress geometry/lease/pacing");
    (* ram_style="block" *) reg [63:0] frames[0:DEPTH-1];
    reg [FIFO_ADDRESS_BITS-1:0] write_pointer,read_pointer;
    reg [FIFO_ADDRESS_BITS:0] count;
    reg [31:0] last_generation,expected_sequence;
    reg [GAP_BITS-1:0] cooldown;
    reg [AGE_BITS-1:0] source_age;
    wire identity_bad=frame_session_i!=session_o || frame_generation_i!=generation_o ||
        frame_physical_epoch_i!=physical_epoch_o || frame_sequence_i!=expected_sequence ||
        frame_44k1_i || frame_error_i;
    wire lease_expired=source_age==AGE_BITS'(SOURCE_LEASE_CYCLES);
    wire frame_bad=frame_valid_i && (identity_bad || count==DEPTH);
    wire cancel_match=cancel_valid_i && cancel_session_i==session_o && cancel_generation_i==generation_o;
    wire external_fence=!link_ready_i || transport_fault_i || panic_i;
    wire immediate_fence=external_fence || cancel_match || frame_bad || lease_expired;
    assign source_allowed_o=reset_ni && armed_o && !fault_o && !immediate_fence;
    assign pcm_valid_o=source_allowed_o && count!=0 && cooldown==0;
    assign pcm_pair_o=frames[read_pointer][31:0];
    assign physical_sequence_o=frames[read_pointer][63:32];
    assign frame_ready_o=source_allowed_o && count<DEPTH;
    assign queued_frames_o=count;
    assign arm_ready_o=reset_ni && !armed_o && object_idle_i && !external_fence && last_generation!=32'hffffffff;
    wire push=frame_valid_i && frame_ready_o;
    wire pop=pcm_valid_o;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            write_pointer<=0;read_pointer<=0;count<=0;last_generation<=0;expected_sequence<=0;cooldown<=0;source_age<=0;
            pcm_sequence_o<=0;session_o<=0;generation_o<=0;physical_epoch_o<=0;
            arm_accepted_o<=0;arm_rejected_o<=0;armed_o<=0;fault_o<=0;failure_code_o<=0;
            accepted_frames_o<=0;delivered_frames_o<=0;
        end else begin
            arm_accepted_o<=0;arm_rejected_o<=0;
            if(arm_valid_i)begin
                if(!arm_ready_o || arm_session_i==0 || arm_generation_i==0 || arm_generation_i<=last_generation ||
                   arm_physical_epoch_i==0 || arm_format_i!=1)arm_rejected_o<=1;
                else begin
                    armed_o<=1;fault_o<=0;failure_code_o<=0;arm_accepted_o<=1;
                    session_o<=arm_session_i;generation_o<=arm_generation_i;physical_epoch_o<=arm_physical_epoch_i;
                    last_generation<=arm_generation_i;expected_sequence<=arm_first_sequence_i;
                    write_pointer<=0;read_pointer<=0;count<=0;cooldown<=0;source_age<=0;
                    accepted_frames_o<=0;delivered_frames_o<=0;
                end
            end
            if(armed_o)begin
                if(immediate_fence)begin
                    armed_o<=0;fault_o<=1;count<=0;cooldown<=0;
                    failure_code_o<=panic_i?4'd5:cancel_match?4'd6:(!link_ready_i || transport_fault_i)?4'd3:
                        lease_expired?4'd4:(count==DEPTH && frame_valid_i)?4'd1:4'd2;
                end else begin
                    if(push)begin
                        frames[write_pointer]<={frame_sequence_i,frame_pcm_i};write_pointer<=write_pointer+1'b1;
                        expected_sequence<=expected_sequence+1'b1;accepted_frames_o<=accepted_frames_o+1'b1;source_age<=0;
                    end else if(source_age<AGE_BITS'(SOURCE_LEASE_CYCLES))source_age<=source_age+1'b1;
                    if(pop)begin
                        read_pointer<=read_pointer+1'b1;cooldown<=GAP_BITS'(MIN_FRAME_CYCLES-1);
                        // This local observer sequence is continuous across arms;
                        // physical sequence/epoch was independently checked on ingress.
                        pcm_sequence_o<=pcm_sequence_o+1'b1;delivered_frames_o<=delivered_frames_o+1'b1;
                    end else if(cooldown!=0)cooldown<=cooldown-1'b1;
                    case({push,pop})
                        2'b10:count<=count+1'b1;
                        2'b01:count<=count-1'b1;
                        default:begin end
                    endcase
                end
            end
        end
    end
endmodule
