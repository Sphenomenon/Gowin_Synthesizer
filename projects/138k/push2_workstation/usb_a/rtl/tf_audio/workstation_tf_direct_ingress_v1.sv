// Unselected M03 component: same-clock file events -> held WAV bytes -> PCM.
// No SD controller, DDR port, clock generator or sample-schedule backpressure.
// Session identity is one snapshot; RAM contains only bytes or {last,R,L}.
module workstation_tf_direct_ingress_v1 #(
    parameter integer BYTE_DEPTH=4096,
    parameter integer PCM_DEPTH=4096,
    parameter integer PREFILL_FRAMES=3072,
    parameter integer SECTOR_PIPELINE_MARGIN=2
)(
    input wire clk_i,rst_ni,
    input wire start_i,cancel_i,pause_i,
    input wire [31:0] generation_i,
    input wire [19:0] expected_rate_i,
    input wire data_sector_start_i,
    output wire sector_allow_o,
    input wire file_byte_valid_i,
    input wire [7:0] file_byte_i,
    input wire file_eof_i,file_error_i,
    input wire [3:0] file_error_code_i,
    // Qualified deadline event in THIS clock domain. Not an asynchronous tick.
    input wire sample_request_i,
    output wire pcm_valid_o,
    input wire pcm_ready_i,
    output wire signed [15:0] pcm_left_o,pcm_right_o,
    output wire pcm_last_o,
    output wire [31:0] generation_o,
    output wire [19:0] session_rate_o,
    output wire active_o,
    output reg prefill_ready_o,decoded_eos_o,local_tail_drained_o,empty_o,
    output reg failed_o,
    output reg [3:0] failure_code_o,file_failure_code_o,
    output wire [31:0] byte_level_o,pcm_level_o,
    output reg [31:0] byte_high_water_o,pcm_high_water_o,
    output wire format_ready_o,
    output wire [19:0] file_rate_o,
    output wire [5:0] file_bits_o,
    output wire file_stereo_o
);
    localparam integer BW=$clog2(BYTE_DEPTH),PW=$clog2(PCM_DEPTH);
    localparam [3:0] FILE_FAIL=1,SECTOR_CONTRACT=2,BYTE_OVERFLOW=3,
        WAV_FAIL=4,RATE_FAIL=5,UNDERRUN=6;
    initial begin
        if(BYTE_DEPTH<1024 || (1<<BW)!=BYTE_DEPTH || PCM_DEPTH<4 ||
           (1<<PW)!=PCM_DEPTH || PREFILL_FRAMES<1 || PREFILL_FRAMES>PCM_DEPTH ||
           SECTOR_PIPELINE_MARGIN<2 || BYTE_DEPTH<512+SECTOR_PIPELINE_MARGIN)
            $fatal(1,"invalid direct ingress capacity");
    end
    reg live;
    reg [31:0] generation;
    reg [19:0] session_rate;
    reg file_ended,eof_sent,tail_queued;
    reg [9:0] reserved_bytes;
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [7:0] byte_mem[0:BYTE_DEPTH-1];
    reg [BW-1:0] byte_wr,byte_rd;
    reg [BW:0] byte_count;
    reg byte_held_valid;
    reg [7:0] byte_held;
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [32:0] pcm_mem[0:PCM_DEPTH-1];
    reg [PW-1:0] pcm_wr,pcm_rd;
    reg [PW:0] pcm_count;
    reg pcm_held_valid;
    reg [32:0] pcm_held;
    reg pending_valid;
    reg [31:0] pending_pair;
    wire [31:0] used_frames=32'(pcm_count)+32'(pcm_held_valid);
    wire decoder_ready,decoder_valid,decoder_eos,decoder_error,decoder_unsupported,decoder_format_ready;
    wire signed [15:0] decoder_left,decoder_right;
    wire decoder_pcm_ready=live && !failed_o && (!pending_valid || used_frames<PCM_DEPTH);
    wire decoder_take=byte_held_valid && decoder_ready && live && !failed_o;
    wire decoder_frame=decoder_valid && decoder_pcm_ready;
    wire byte_prefetch=live && (!byte_held_valid || decoder_take) && byte_count!=0;
    wire byte_push=file_byte_valid_i && live && !failed_o;
    wire pcm_take=pcm_valid_o && pcm_ready_i;
    wire pcm_prefetch=live && (!pcm_held_valid || pcm_take) && pcm_count!=0;
    wire flush_tail=decoder_eos && !decoder_valid && pending_valid &&
        !tail_queued && used_frames<PCM_DEPTH;
    wire pcm_push=live && !failed_o && ((decoder_frame && pending_valid) || flush_tail);
    wire decoder_eof=live && file_ended && !eof_sent && byte_count==0 && !byte_held_valid;
    wire [31:0] used_bytes=32'(byte_count)+32'(byte_held_valid);
    assign byte_level_o=used_bytes;
    assign pcm_level_o=used_frames;
    // Reserve the complete unbackpressured sector and two registered events.
    // Metadata sectors do not use this allowance and never produce file bytes.
    assign sector_allow_o=live && !failed_o && !file_ended && reserved_bytes==0 &&
        used_bytes<=BYTE_DEPTH-512-SECTOR_PIPELINE_MARGIN && !cancel_i && !start_i && !file_error_i;
    assign format_ready_o=live && !failed_o && decoder_format_ready;
    assign generation_o=generation;
    assign session_rate_o=session_rate;
    assign active_o=live && !failed_o && prefill_ready_o && !empty_o && !local_tail_drained_o &&
        !cancel_i && !start_i && !file_error_i;
    assign pcm_valid_o=active_o && !pause_i && pcm_held_valid && !cancel_i && !start_i;
    assign {pcm_last_o,pcm_right_o,pcm_left_o}=pcm_held;
    workstation_tf_wav_pcm_decoder_v1 decoder(
        .clk(clk_i),.rst_n(rst_ni),.restart(start_i || cancel_i || !live || failed_o),
        .in_valid(byte_held_valid && live && !failed_o),.in_byte(byte_held),.in_ready(decoder_ready),
        .eof_i(decoder_eof),.eos_o(decoder_eos),.error_o(decoder_error),
        .header_valid(decoder_format_ready),.sample_rate_hz(file_rate_o),.stereo(file_stereo_o),
        .bits_per_sample(file_bits_o),.pcm_valid(decoder_valid),.pcm_ready(decoder_pcm_ready),
        .pcm_left(decoder_left),.pcm_right(decoder_right),.unsupported(decoder_unsupported));
    reg [3:0] failure_now;
    always @* begin
        failure_now=0;
        if(live && !failed_o)begin
            if(file_error_i)failure_now=FILE_FAIL;
            else if(data_sector_start_i && !sector_allow_o)failure_now=SECTOR_CONTRACT;
            else if(file_byte_valid_i && used_bytes>=BYTE_DEPTH && !decoder_take)failure_now=BYTE_OVERFLOW;
            else if(file_byte_valid_i && (reserved_bytes==0 || file_ended))failure_now=SECTOR_CONTRACT;
            else if(session_rate!=20'd48000 && session_rate!=20'd44100)failure_now=RATE_FAIL;
            else if(decoder_error || decoder_unsupported)failure_now=WAV_FAIL;
            else if(format_ready_o && file_rate_o!=session_rate)failure_now=RATE_FAIL;
            else if(sample_request_i && prefill_ready_o && !pause_i &&
                !local_tail_drained_o && !empty_o && !pcm_held_valid)failure_now=UNDERRUN;
        end
    end
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            live<=0;generation<=0;session_rate<=0;file_ended<=0;eof_sent<=0;tail_queued<=0;
            reserved_bytes<=0;byte_wr<=0;byte_rd<=0;byte_count<=0;byte_held_valid<=0;byte_held<=0;
            pcm_wr<=0;pcm_rd<=0;pcm_count<=0;pcm_held_valid<=0;pcm_held<=0;pending_valid<=0;pending_pair<=0;
            prefill_ready_o<=0;decoded_eos_o<=0;local_tail_drained_o<=0;empty_o<=0;
            failed_o<=0;failure_code_o<=0;file_failure_code_o<=0;byte_high_water_o<=0;pcm_high_water_o<=0;
        end else if(cancel_i || start_i)begin
            // Explicit cancel wins a simultaneous start. File-owner stop/drain
            // must finish before a later track_applied starts a new session.
            live<=start_i && !cancel_i && !file_error_i &&
                (expected_rate_i==20'd48000 || expected_rate_i==20'd44100);
            if(start_i && !cancel_i)begin generation<=generation_i;session_rate<=expected_rate_i;end
            file_ended<=start_i && !cancel_i && file_eof_i;
            eof_sent<=0;tail_queued<=0;reserved_bytes<=0;
            byte_wr<=0;byte_rd<=0;byte_count<=0;byte_held_valid<=0;
            pcm_wr<=0;pcm_rd<=0;pcm_count<=0;pcm_held_valid<=0;pending_valid<=0;
            prefill_ready_o<=0;decoded_eos_o<=0;local_tail_drained_o<=0;empty_o<=0;
            if(start_i && !cancel_i)begin
                failed_o<=file_error_i || (expected_rate_i!=20'd48000 && expected_rate_i!=20'd44100);
                failure_code_o<=file_error_i ? FILE_FAIL:
                    ((expected_rate_i!=20'd48000 && expected_rate_i!=20'd44100) ? RATE_FAIL:4'd0);
                file_failure_code_o<=file_error_i ? file_error_code_i:4'd0;
                byte_high_water_o<=0;pcm_high_water_o<=0;
            end
        end else if(live && !failed_o)begin
            if(used_bytes>byte_high_water_o)byte_high_water_o<=used_bytes;
            if(used_frames>pcm_high_water_o)pcm_high_water_o<=used_frames;
            if(data_sector_start_i)reserved_bytes<=10'd512;
            else if(byte_push && reserved_bytes!=0)reserved_bytes<=reserved_bytes-1'b1;
            // The final sector may expose fewer than 512 file bytes. Actual
            // file EOF retires its unused reservation, never fabricates bytes.
            if(file_eof_i)begin file_ended<=1;reserved_bytes<=0;end
            if(decoder_eof)eof_sent<=1;
            if(byte_push)begin byte_mem[byte_wr]<=file_byte_i;byte_wr<=byte_wr+1'b1;end
            if(byte_prefetch)begin byte_held<=byte_mem[byte_rd];byte_rd<=byte_rd+1'b1;byte_held_valid<=1;end
            else if(decoder_take)byte_held_valid<=0;
            case({byte_push,byte_prefetch})
                2'b10:byte_count<=byte_count+1'b1;
                2'b01:byte_count<=byte_count-1'b1;
                default:begin end
            endcase
            // One frame of lookbehind makes final PCM identity independent of
            // where file EOF falls relative to tail metadata and backpressure.
            if(decoder_frame)begin pending_pair<={decoder_right,decoder_left};pending_valid<=1;end
            if(pcm_push)begin
                pcm_mem[pcm_wr]<={flush_tail,pending_pair};pcm_wr<=pcm_wr+1'b1;
                if(flush_tail)begin pending_valid<=0;tail_queued<=1;decoded_eos_o<=1;end
            end
            if(pcm_prefetch)begin pcm_held<=pcm_mem[pcm_rd];pcm_rd<=pcm_rd+1'b1;pcm_held_valid<=1;end
            else if(pcm_take)pcm_held_valid<=0;
            case({pcm_push,pcm_prefetch})
                2'b10:pcm_count<=pcm_count+1'b1;
                2'b01:pcm_count<=pcm_count-1'b1;
                default:begin end
            endcase
            if(used_frames>=PREFILL_FRAMES || (tail_queued && used_frames!=0))prefill_ready_o<=1;
            if(decoder_eos && !decoder_valid && !pending_valid && !tail_queued)begin
                decoded_eos_o<=1;empty_o<=1;local_tail_drained_o<=1;
            end
            if(pcm_take && pcm_last_o)local_tail_drained_o<=1;
            if(failure_now!=0)begin
                failed_o<=1;failure_code_o<=failure_now;file_failure_code_o<=file_error_code_i;
                live<=0;prefill_ready_o<=0;reserved_bytes<=0;byte_count<=0;byte_held_valid<=0;
                pcm_count<=0;pcm_held_valid<=0;pending_valid<=0;
            end
        end
    end
endmodule
