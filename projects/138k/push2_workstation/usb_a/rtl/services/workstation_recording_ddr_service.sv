`timescale 1ns/1ps
`default_nettype none
// CPU-owned object commands, on the continuously running DDR UI clock.
// Observer reset releases a download reference; it never resets capture/object.
module workstation_recording_ddr_service #(
    parameter integer CAPACITY_FRAMES=16384,FIFO_ADDRESS_BITS=9,
    parameter integer DDR_BUDGET_CYCLES=10000,SOURCE_GAP_CYCLES=400000
)(
    input wire clk_i,reset_ni,command_reset_ni,backend_ready_i,
    input wire command_valid_i,command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output reg command_ready_o,response_error_o,
    output reg [31:0] response_data_o,
    input wire pcm_valid_i,pcm_44k1_i,pcm_error_i,pcm_loss_i,
    input wire [31:0] pcm_epoch_i,pcm_sequence_i,pcm_pair_i,pcm_drop_count_i,
    input wire seal_hold_i,seal_request_i,
    output wire seal_ready_o,
    output reg seal_done_o,seal_failed_o,
    output reg [3:0] seal_failure_code_o,
    output wire ddr_valid_o,ddr_write_o,
    output wire [28:0] ddr_address_o,
    output wire [255:0] ddr_data_o,
    output wire [31:0] ddr_mask_o,
    input wire ddr_ready_i,ddr_response_i,
    input wire [255:0] ddr_read_data_i,
    input wire transport_fault_i,
    output wire [3:0] object_state_o,object_failure_o,
    output wire [31:0] object_frames_o,committed_frames_o,
    output wire capture_o
);
    localparam [11:0] ID=12'h000,CAPS=12'h004,COMMAND=12'h008,STATUS=12'h00c,
        STAGE_ID_LOW=12'h010,STAGE_ID_HIGH=12'h014,LIMIT=12'h018,
        OBJECT_LOW=12'h01c,OBJECT_HIGH=12'h020,RATE=12'h024,EPOCH=12'h028,
        FRAMES=12'h02c,COMMITTED=12'h030,FIFO_PEAK=12'h034,COMMAND_WAIT=12'h038,
        READ_WAIT=12'h03c,OFFSET=12'h040,LENGTH=12'h044,DATA_STATUS=12'h048,
        DATA0=12'h04c,DATA7=12'h068,LAST_SEQUENCE=12'h06c,DROPS=12'h070;
    localparam [3:0] CREATE=1,SEAL=2,CANCEL=3,CLEAR=4,ACQUIRE=5,RELEASE=6,
        DOWNLOAD=7,POP_HEAD=8,RELEASE_HEAD=9;
    reg [63:0] staged_id;
    reg [31:0] staged_limit,staged_offset,staged_length,create_wait,last_sequence;
    reg snapshot_valid;
    reg [255:0] snapshot_data;
    reg [5:0] snapshot_bytes;
    reg snapshot_last,seal_pending,download_done_sticky,download_error_sticky;
    wire [63:0] object_id;
    wire object_rate,create_ready,clear_ready,reference_ready,reference_held;
    wire reference_error;
    wire download_ready,download_valid,download_last,download_done,download_error,quiescent;
    wire [255:0] download_data;
    wire [5:0] download_bytes;
    wire [31:0] object_epoch,max_command_wait,max_read_wait;
    wire [FIFO_ADDRESS_BITS:0] fifo_peak;
    wire bus=command_valid_i && command_reset_ni;
    wire operation=command_write_i && command_address_i==COMMAND;
    wire [3:0] opcode=command_data_i[3:0];
    wire source_good=backend_ready_i && !transport_fault_i && !pcm_loss_i && !pcm_error_i && pcm_epoch_i!=0;
    wire create_eligible=create_ready && !seal_hold_i && !seal_pending && !seal_request_i && staged_id!=0 &&
        staged_limit!=0 && staged_limit<=CAPACITY_FRAMES;
    wire snapshot_available=snapshot_valid && object_state_o==3 && reference_held && !transport_fault_i && command_reset_ni;
    wire create_timeout=create_wait>=SOURCE_GAP_CYCLES-1;
    // Decode accepted operations independently. Feeding the aggregate bus
    // error back through backend readiness creates a combinational loop across
    // mutually exclusive opcodes before synthesis can simplify the decoder.
    wire bus_operation=bus && operation && command_strobes_i==4'hf && command_data_i>=1 && command_data_i<=9;
    wire create=bus_operation && opcode==CREATE && create_eligible && pcm_valid_i && source_good && !create_timeout;
    wire cpu_seal=bus_operation && opcode==SEAL && (object_state_o==1 || object_state_o==2 || object_state_o==3);
    wire cancel=bus_operation && opcode==CANCEL && !seal_hold_i && !seal_pending && object_state_o!=0;
    wire clear=bus_operation && opcode==CLEAR && clear_ready && !seal_hold_i && !seal_pending;
    wire acquire=bus_operation && opcode==ACQUIRE && reference_ready && staged_id==object_id;
    wire release_reference=(bus_operation && opcode==RELEASE && reference_held) || !command_reset_ni;
    wire start_download=bus_operation && opcode==DOWNLOAD && download_ready && staged_length!=0 &&
        {1'b0,staged_offset}+{1'b0,staged_length}<={1'b0,(object_frames_o<<2)} && !snapshot_valid;
    wire pop_head=bus_operation && opcode==POP_HEAD && download_valid && !snapshot_valid;
    wire release_head=bus_operation && opcode==RELEASE_HEAD && snapshot_valid;
    assign seal_ready_o=reset_ni && !seal_pending;
    // Never cancel a live object to satisfy a rate change. The backend drains
    // accepted writes and reaches immutable READY before successful seal ACK.
    wire backend_seal=cpu_seal || (seal_request_i && seal_ready_o);
    workstation_pcm_ddr_backend #(.CAPACITY_FRAMES(CAPACITY_FRAMES),
        .FIFO_ADDRESS_BITS(FIFO_ADDRESS_BITS),.DDR_BUDGET_CYCLES(DDR_BUDGET_CYCLES),
        .SOURCE_GAP_CYCLES(SOURCE_GAP_CYCLES),.TRANSPORT_FAULT_ENABLE(1)) backend(
        .clk_i(clk_i),.rst_ni(reset_ni),.create_i(create),.create_ready_o(create_ready),
        .object_id_i(staged_id),.rate_44k1_i(pcm_44k1_i),.epoch_i(pcm_epoch_i),
        .first_sequence_i(pcm_sequence_i+1'b1),.limit_frames_i(staged_limit),
        .seal_i(backend_seal),.cancel_i(cancel),.soft_reset_i(1'b0),.clear_i(clear),.clear_ready_o(clear_ready),
        .pcm_valid_i(pcm_valid_i),.source_ready_i(backend_ready_i && !pcm_loss_i),
        .source_error_i(pcm_valid_i && pcm_error_i),.pcm_pair_i(pcm_pair_i),.pcm_sequence_i(pcm_sequence_i),
        .pcm_epoch_i(pcm_epoch_i),.pcm_44k1_i(pcm_44k1_i),.capture_o(capture_o),
        .state_o(object_state_o),.failure_code_o(object_failure_o),.object_id_o(object_id),
        .rate_44k1_o(object_rate),.epoch_o(object_epoch),.frames_o(object_frames_o),
        .committed_frames_o(committed_frames_o),.quiescent_o(quiescent),.fifo_peak_o(fifo_peak),
        .max_command_wait_o(max_command_wait),.max_read_wait_o(max_read_wait),.discarded_responses_o(),
        .reference_acquire_i(acquire),.reference_release_i(release_reference),.reference_object_id_i(staged_id),
        .reference_ready_o(reference_ready),.reference_held_o(reference_held),
        .reference_granted_o(),.reference_error_o(reference_error),.reference_released_o(),
        .download_i(start_download),.download_ready_o(download_ready),
        .download_offset_i(staged_offset),.download_length_i(staged_length),
        .download_valid_o(download_valid),.download_ready_i(pop_head),.download_data_o(download_data),
        .download_bytes_o(download_bytes),.download_last_o(download_last),
        .download_done_o(download_done),.download_error_o(download_error),
        .ddr_valid_o(ddr_valid_o),.ddr_write_o(ddr_write_o),.ddr_address_o(ddr_address_o),
        .ddr_data_o(ddr_data_o),.ddr_mask_o(ddr_mask_o),.ddr_ready_i(ddr_ready_i),
        .ddr_response_i(ddr_response_i),.ddr_read_data_i(ddr_read_data_i),.transport_fault_i(transport_fault_i));

    always @* begin
        command_ready_o=1;response_error_o=0;response_data_o=0;
        if(command_write_i)begin
            if(command_strobes_i!=4'hf)response_error_o=1;
            else case(command_address_i)
                STAGE_ID_LOW,STAGE_ID_HIGH,LIMIT,OFFSET,LENGTH:begin end
                COMMAND:begin
                    if(command_data_i>9 || command_data_i==0)response_error_o=1;
                    else case(opcode)
                        CREATE:begin
                            response_error_o=!create_eligible || (pcm_valid_i && !source_good) || create_timeout;
                            command_ready_o=!create_eligible || pcm_valid_i || create_timeout;
                        end
                        SEAL:response_error_o=object_state_o!=1 && object_state_o!=2 && object_state_o!=3;
                        CANCEL:response_error_o=seal_hold_i || seal_pending || object_state_o==0;
                        CLEAR:response_error_o=!clear_ready || seal_hold_i || seal_pending;
                        ACQUIRE:response_error_o=!reference_ready || staged_id!=object_id;
                        RELEASE:response_error_o=!reference_held;
                        DOWNLOAD:response_error_o=!download_ready || staged_length==0 ||
                            {1'b0,staged_offset}+{1'b0,staged_length}>{1'b0,(object_frames_o<<2)} || snapshot_valid;
                        POP_HEAD:response_error_o=!download_valid || snapshot_valid;
                        RELEASE_HEAD:response_error_o=!snapshot_valid;
                        default:response_error_o=1;
                    endcase
                end
                default:response_error_o=1;
            endcase
        end else begin
            case(command_address_i)
                ID:response_data_o=32'h52434401;
                CAPS:response_data_o=32'h00010007; // v1; dual-rate, 64-KiB, owner8; no BLE ABI claim.
                STATUS:response_data_o={20'd0,quiescent,snapshot_available,reference_held,seal_pending,
                    object_failure_o,object_state_o};
                STAGE_ID_LOW:response_data_o=staged_id[31:0];
                STAGE_ID_HIGH:response_data_o=staged_id[63:32];
                LIMIT:response_data_o=staged_limit;
                OBJECT_LOW:response_data_o=object_id[31:0];
                OBJECT_HIGH:response_data_o=object_id[63:32];
                RATE:response_data_o=object_rate ? 32'd44100:32'd48000;
                EPOCH:response_data_o=object_epoch;
                FRAMES:response_data_o=object_frames_o;
                COMMITTED:response_data_o=committed_frames_o;
                FIFO_PEAK:response_data_o={{(31-FIFO_ADDRESS_BITS){1'b0}},fifo_peak};
                COMMAND_WAIT:response_data_o=max_command_wait;
                READ_WAIT:response_data_o=max_read_wait;
                OFFSET:response_data_o=staged_offset;
                LENGTH:response_data_o=staged_length;
                DATA_STATUS:response_data_o={20'd0,reference_error,download_error_sticky,download_done_sticky,
                    download_valid,snapshot_available,snapshot_last,snapshot_bytes};
                LAST_SEQUENCE:response_data_o=last_sequence;
                DROPS:response_data_o=pcm_drop_count_i;
                default:begin
                    if(command_address_i>=DATA0 && command_address_i<=DATA7 && command_address_i[1:0]==0)begin
                        response_error_o=!snapshot_available;
                        if(snapshot_available)response_data_o=snapshot_data[(command_address_i-DATA0)*8+:32];
                    end else response_error_o=1;
                end
            endcase
        end
    end
    // Only bus staging/snapshot bookkeeping uses the CPU observer reset.
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            staged_id<=0;staged_limit<=0;staged_offset<=0;staged_length<=0;create_wait<=0;
            snapshot_valid<=0;snapshot_data<=0;snapshot_bytes<=0;snapshot_last<=0;
            last_sequence<=0;seal_pending<=0;download_done_sticky<=0;download_error_sticky<=0;seal_done_o<=0;seal_failed_o<=0;seal_failure_code_o<=0;
        end else begin
            seal_done_o<=0;seal_failed_o<=0;
            if(pcm_valid_i)last_sequence<=pcm_sequence_i;
            if(download_done)download_done_sticky<=1;
            if(download_error)download_error_sticky<=1;
            if(start_download || release_reference)begin download_done_sticky<=0;download_error_sticky<=0;end
            if(bus && operation && opcode==CREATE && !command_ready_o)create_wait<=create_wait+1'b1;
            else create_wait<=0;
            if(!command_reset_ni)begin
                staged_id<=0;staged_limit<=0;staged_offset<=0;staged_length<=0;
                snapshot_valid<=0;
            end else begin
                if(bus && command_write_i && command_ready_o && !response_error_o)case(command_address_i)
                    STAGE_ID_LOW:staged_id[31:0]<=command_data_i;
                    STAGE_ID_HIGH:staged_id[63:32]<=command_data_i;
                    LIMIT:staged_limit<=command_data_i;
                    OFFSET:staged_offset<=command_data_i;
                    LENGTH:staged_length<=command_data_i;
                    default:begin end
                endcase
                if(pop_head)begin
                    snapshot_valid<=1;snapshot_data<=download_data;
                    snapshot_bytes<=download_bytes;snapshot_last<=download_last;
                end
                if(release_head || release_reference || cancel || clear || object_state_o>=4 || transport_fault_i)
                    snapshot_valid<=0;
            end
            if(seal_request_i && seal_ready_o)begin
                seal_pending<=1;seal_failure_code_o<=0;
            end
            if(seal_pending)begin
                if(object_state_o>=4 || transport_fault_i)begin
                    seal_pending<=0;seal_failed_o<=1;
                    seal_failure_code_o<=transport_fault_i ? 4'd9:object_failure_o;
                end else if((object_state_o==0 || object_state_o==3) && quiescent)begin
                    seal_pending<=0;seal_done_o<=1;
                end
            end
        end
    end
endmodule
`default_nettype wire
