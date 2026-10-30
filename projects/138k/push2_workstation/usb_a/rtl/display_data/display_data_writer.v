`default_nettype none
// Snapshot the same immutable front banks used by this raster. Reuse their
// read ports before pixels issue. DDR stalls retain those banks; audio never waits.
module display_data_writer #(
    parameter integer METADATA_MINOR=0,
    parameter integer CONTEXT_ENABLE=(METADATA_MINOR==1 ? 1 : 0)
) (
    input wire clk,rst_n,enabled,start,
    input wire [255:0] effect_meta,
    input wire [31:0] analysis_sequence,analysis_skipped,stereo_peaks,
    input wire analysis_valid,
    input wire [2:0] image_gain,
    // Optional atomic result identity, already in clk domain. Legacy minor0
    // callers leave CONTEXT_ENABLE=0 and retain their fixed-48k contract.
    input wire source_context_valid_i,
    input wire [31:0] source_sample_rate_i,source_epoch_i,source_generation_i,
    input wire waveform_context_valid_i,
    input wire [31:0] waveform_sample_rate_i,waveform_epoch_i,waveform_generation_i,
    input wire analysis_context_valid_i,
    input wire [31:0] analysis_sample_rate_i,analysis_epoch_i,analysis_generation_i,
    output reg context_rejected_o,context_aborted_o,context_unavailable_o,
    output reg [2:0] context_diagnostic_o,
    output wire busy,
    output reg done,initialized,
    output wire req_valid,
    input wire req_ready,
    output reg [28:0] req_addr,
    output reg [255:0] req_wdata,
    output wire read_enable,
    output wire [1:0] read_kind,
    output wire [15:0] read_addr,
    input wire [31:0] read_data
);
    import display_data_layout_pkg::*;
    localparam [7:0] SELECTED_MINOR=8'(METADATA_MINOR);
    localparam CONTEXT_ENABLED=(CONTEXT_ENABLE!=0);
    initial begin
        if(METADATA_MINOR<0 || METADATA_MINOR>1 || (METADATA_MINOR==1 && !CONTEXT_ENABLED))
            $fatal(1,"display writer minor/context selection unsupported");
    end
    localparam [3:0] INIT_CONTROL=0,INIT_BANK0=1,INIT_BANK1=2,IDLE=3,SNAPSHOT=4,
        INVALIDATE=5,READ=6,WAIT_RAM=7,CAPTURE=8,WRITE=9,META=10,DESC=11,
        COMMIT_BANK=12,COMMIT_GLOBAL=13,FINISH=14;
    reg [3:0] state;
    reg bank,published_bank;
    reg [31:0] frame_sequence;
    reg [255:0] meta_q,pack_data;
    reg [31:0] analysis_sequence_q,analysis_skipped_q,peaks_q;
    reg [31:0] sample_rate_q,epoch_q,context_generation_q;
    reg abort_pending;
    reg valid_q;
    reg [2:0] gain_q;
    reg [1:0] kind,descriptor;
    reg high_beat;
    reg [15:0] index;
    reg [28:0] payload_address;
    wire [28:0] payload_base=bank ? PAYLOAD_BANK1_WORD : PAYLOAD_BANK0_WORD;
    wire [28:0] desc_base=bank ? DESC_BANK1_WORD : DESC_BANK0_WORD;
    wire [28:0] bank_header=bank ? BANK1_HEADER_WORD : BANK0_HEADER_WORD;
    wire [31:0] wave_sequence=meta_q[95:64],wave_skipped=meta_q[63:32];
    wire [31:0] valid_flags=valid_q ? 32'hf : 32'h9;
    wire [31:0] generation=frame_sequence<<1;
    wire supported_source=(source_sample_rate_i==32'd48000 ||
        (METADATA_MINOR==1 && source_sample_rate_i==32'd44100));
    wire wave_matches=waveform_context_valid_i && waveform_sample_rate_i==source_sample_rate_i &&
        waveform_epoch_i==source_epoch_i && waveform_generation_i==source_generation_i;
    wire analysis_matches=analysis_context_valid_i && analysis_sample_rate_i==source_sample_rate_i &&
        analysis_epoch_i==source_epoch_i && analysis_generation_i==source_generation_i;
    wire snapshot_context_ok=!CONTEXT_ENABLED || (source_context_valid_i && source_epoch_i!=0 &&
        supported_source && wave_matches && (!analysis_valid || analysis_matches));
    wire changed_context=CONTEXT_ENABLED && (!source_context_valid_i || source_sample_rate_i!=sample_rate_q ||
        source_epoch_i!=epoch_q || source_generation_i!=context_generation_q);
    // Once all RAM elements have been read, the captured packet is immutable.
    // A context change before that point cancels publication. An advertised
    // stalled DDR beat is drained without changing/withdrawing its payload.
    wire exporting_source=state>=INVALIDATE && state<=WRITE;
    wire abort_now=exporting_source && (abort_pending || changed_context);
    control_record_t control_data;
    block_descriptor_t desc_data;
    always @* begin
        control_data='0;
        control_data.magic=DISPLAY_MAGIC;
        control_data.version_bank_count={8'd4,7'd0,bank,VERSION_MAJOR,SELECTED_MINOR};
        control_data.frame_sequence=frame_sequence;
        control_data.commit_sequence=state==INVALIDATE ? generation|32'd1 : generation;
        control_data.descriptor_base_word={3'd0,desc_base};
        control_data.flags=valid_flags;
        control_data.waveform_skipped=wave_skipped;
        control_data.analysis_skipped=analysis_skipped_q;
        desc_data='0;
        desc_data.magic=BLOCK_MAGIC;
        desc_data.version_type_format={16'd0,VERSION_MAJOR,SELECTED_MINOR};
        desc_data.version_type_format[31:24]={6'd0,descriptor}+8'd1;
        desc_data.version_type_format[23:16]={6'd0,descriptor}+8'd1;
        desc_data.frame_sequence=frame_sequence;
        desc_data.source_sequence=descriptor==0 ? wave_sequence : descriptor==3 ? frame_sequence : analysis_sequence_q;
        desc_data.sample_rate_hz=descriptor==3 ? 32'd0 : sample_rate_q;
        desc_data.reserved=METADATA_MINOR==1 ? epoch_q : 32'd0;
        desc_data.flags=descriptor==0 || descriptor==3 || valid_q ? 32'd1 : 32'd0;
        desc_data.skipped_samples=descriptor==0 ? wave_skipped : descriptor==3 ? 32'd0 : analysis_skipped_q;
        desc_data.bank_header_word={3'd0,bank_header};
        case(descriptor)
            0:begin
                desc_data.valid_length=512; desc_data.payload_words=512;
                desc_data.payload_base_word={3'd0,payload_base}+{3'd0,WAVEFORM_OFFSET_WORD};
                desc_data.window_trigger=32'h0d010200; // 8192 timeout, six-pole trigger, 512 unwindowed samples
            end
            1:begin
                desc_data.valid_length=valid_q ? 65536 : 0; desc_data.payload_words=2048;
                desc_data.payload_base_word={3'd0,payload_base}+{3'd0,LISSAJOUS_OFFSET_WORD};
                desc_data.window_trigger=32'h00000800; // 2048 unwindowed L/R samples
                desc_data.display_gain={29'd0,gain_q};desc_data.aux0=32'h01000100; // 256 x 256
            end
            2:begin
                desc_data.valid_length=valid_q ? 512 : 0; desc_data.payload_words=256;
                desc_data.payload_base_word={3'd0,payload_base}+{3'd0,SPECTRUM_OFFSET_WORD};
                desc_data.window_trigger=32'h00020800; // periodic Hann, 2048 samples
                desc_data.aux0=32'h03550002; // input bin range 2..853 inclusive
                desc_data.aux1=224; // legacy display log-height ceiling
            end
            3:begin
                desc_data.valid_length=16;desc_data.payload_words=16;
                desc_data.payload_base_word={3'd0,payload_base}+{3'd0,EFFECT_META_OFFSET_WORD};
            end
        endcase
    end
    assign busy=state!=IDLE;
    assign read_enable=state==READ || state==WAIT_RAM;
    assign read_kind=kind;
    assign read_addr=index;
    wire last_lane=kind==0 ? &index[2:0] : kind==1 ? &index[7:0] : &index[3:0];
    wire last_element=kind==1 ? &index : index==511;
    wire write_state=state<=INIT_BANK1 || state==INVALIDATE || state==WRITE ||
        state==META || state==DESC || state==COMMIT_BANK || state==COMMIT_GLOBAL;
    assign req_valid=enabled && write_state;
    always @* begin
        req_addr=0;req_wdata=0;
        case(state)
            INIT_CONTROL:req_addr=DISPLAY_CONTROL_WORD;
            INIT_BANK0:req_addr=BANK0_HEADER_WORD;
            INIT_BANK1:req_addr=BANK1_HEADER_WORD;
            INVALIDATE,COMMIT_BANK:begin req_addr=bank_header;req_wdata=control_data;end
            WRITE:begin req_addr=payload_address;req_wdata=pack_data;end
            META:begin
                req_addr=payload_base+EFFECT_META_OFFSET_WORD+(high_beat ? 29'd8 : 29'd0);
                req_wdata=high_beat ? {32'd0,METADATA_MINOR==1 ? epoch_q : 32'd0,sample_rate_q,
                    valid_flags,{29'd0,gain_q},peaks_q,analysis_skipped_q,analysis_sequence_q} : meta_q;
            end
            DESC:begin
                req_addr=desc_base+{23'd0,descriptor,high_beat,3'd0};
                req_wdata=high_beat ? desc_data[511:256] : desc_data[255:0];
            end
            COMMIT_GLOBAL:begin req_addr=DISPLAY_CONTROL_WORD;req_wdata=control_data;end
            default:begin end
        endcase
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=INIT_CONTROL;bank<=0;published_bank<=0;frame_sequence<=0;initialized<=0;done<=0;
            meta_q<=0;analysis_sequence_q<=0;analysis_skipped_q<=0;peaks_q<=0;valid_q<=0;gain_q<=0;
            sample_rate_q<=SAMPLE_RATE_HZ;epoch_q<=0;context_generation_q<=0;abort_pending<=0;
            context_rejected_o<=0;context_aborted_o<=0;context_unavailable_o<=0;context_diagnostic_o<=0;
            kind<=0;index<=0;descriptor<=0;high_beat<=0;payload_address<=0;pack_data<=0;
        end else begin
            done<=0;
            context_rejected_o<=0;context_aborted_o<=0;
            if(abort_now)begin
                abort_pending<=1;context_unavailable_o<=1;context_diagnostic_o<=5;
                if(!req_valid || req_ready)begin
                    state<=FINISH;context_aborted_o<=1;abort_pending<=0;
                end
            end else
            case(state)
                INIT_CONTROL:if(req_valid && req_ready)state<=INIT_BANK0;
                INIT_BANK0:if(req_valid && req_ready)state<=INIT_BANK1;
                INIT_BANK1:if(req_valid && req_ready)begin state<=IDLE;initialized<=1;end
                IDLE:if(start)begin
                    bank<=CONTEXT_ENABLED ? ~published_bank : ~bank;
                    frame_sequence<=frame_sequence+1'b1;state<=SNAPSHOT;abort_pending<=0;
                end
                // Renderer latches effect state and swaps the analysis bank on start.
                SNAPSHOT:begin
                    meta_q<=effect_meta;analysis_sequence_q<=analysis_sequence;analysis_skipped_q<=analysis_skipped;
                    valid_q<=analysis_valid;gain_q<=image_gain;peaks_q<=stereo_peaks;
                    sample_rate_q<=CONTEXT_ENABLED ? source_sample_rate_i : SAMPLE_RATE_HZ;
                    epoch_q<=CONTEXT_ENABLED ? source_epoch_i : 32'd0;
                    context_generation_q<=CONTEXT_ENABLED ? source_generation_i : 32'd0;
                    kind<=0;index<=0;payload_address<=payload_base;
                    if(snapshot_context_ok)state<=INVALIDATE;
                    else begin
                        state<=FINISH;context_rejected_o<=1;context_unavailable_o<=1;
                        context_diagnostic_o<=!source_context_valid_i || source_epoch_i==0 ? 1 :
                            !supported_source ? 2 : !wave_matches ? 3 : 4;
                    end
                end
                INVALIDATE:if(req_valid && req_ready)state<=READ;
                READ:state<=WAIT_RAM;
                WAIT_RAM:state<=CAPTURE;
                CAPTURE:begin
                    case(kind)
                        0:pack_data<={read_data,pack_data[255:32]};
                        1:pack_data<={valid_q && read_data[0],pack_data[255:1]};
                        2:pack_data<={valid_q ? read_data[15:0] : 16'd0,pack_data[255:16]};
                        default:begin end
                    endcase
                    if(last_lane)state<=WRITE;
                    else begin index<=index+1'b1;state<=READ;end
                end
                WRITE:if(req_valid && req_ready)begin
                    payload_address<=payload_address+29'd8;
                    if(last_element)begin
                        index<=0;
                        if(kind==2)begin high_beat<=0;state<=META;end
                        else begin kind<=kind+1'b1;state<=READ;end
                    end else begin index<=index+1'b1;state<=READ;end
                end
                META:if(req_valid && req_ready)begin
                    high_beat<=~high_beat;
                    if(high_beat)begin descriptor<=0;state<=DESC;end
                end
                DESC:if(req_valid && req_ready)begin
                    high_beat<=~high_beat;
                    if(high_beat)begin
                        if(descriptor==3)state<=COMMIT_BANK;
                        else descriptor<=descriptor+1'b1;
                    end
                end
                COMMIT_BANK:if(req_valid && req_ready)state<=COMMIT_GLOBAL;
                COMMIT_GLOBAL:if(req_valid && req_ready)begin
                    state<=FINISH;published_bank<=bank;context_unavailable_o<=0;context_diagnostic_o<=0;
                end
                FINISH:begin done<=1;state<=IDLE;end
                default:state<=INIT_CONTROL;
            endcase
        end
    end
endmodule

// Register the selected request before arbitration. This breaks the path from
// display enables/address selection through DDR ready and back to the writers.
// The shared FSM gets a registered ACK to keep its next-state decode off the
// DDR-ready path. Framebuffer beats keep the immediate ACK for 60 Hz throughput.
module display_write_bridge(
    input wire clk,rst_n,
    input wire shared_valid,
    input wire [28:0] shared_addr,
    input wire [255:0] shared_data,
    output wire shared_ready,
    input wire frame_valid,
    input wire [28:0] frame_addr,
    input wire [255:0] frame_data,
    output wire frame_ready,
    output wire req_valid,
    output reg [28:0] req_addr,
    output reg [255:0] req_data,
    input wire req_ready
);
    reg pending,owner_shared,shared_ack;
    assign req_valid=pending;
    assign shared_ready=shared_ack;
    assign frame_ready=pending && req_ready && !owner_shared;
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin pending<=0;owner_shared<=0;shared_ack<=0;req_addr<=0;req_data<=0;end
        else begin
            shared_ack<=0;
            if(pending)begin
                if(req_ready)begin pending<=0;shared_ack<=owner_shared;end
            end else if(!shared_ack && (shared_valid || frame_valid))begin
                owner_shared<=shared_valid;
                req_addr<=shared_valid ? shared_addr : frame_addr;
                req_data<=shared_valid ? shared_data : frame_data;
                pending<=1;
            end
        end
    end
endmodule
`default_nettype wire
