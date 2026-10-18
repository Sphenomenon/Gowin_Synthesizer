`timescale 1ns/1ps
// Read-only bring-up telemetry. No command input and no audio backpressure.
// A138 + eight 32bit hex words + CRC16/CCITT-FALSE (little-endian payload).
module gw138k_performance_uart #(
    parameter integer INTERVAL_CYCLES=50000000,
    parameter integer BAUD=115200,
    parameter integer CPU_SNAPSHOT_BITS=16
) (
    input wire clk_50m, reset_n, audio_clk, audio_reset_n, audio_locked, sample_valid,
    input wire [7:0] memory_flags,
    input wire [31:0] audio_status,
    input wire [127:0] video_diagnostics,
    input wire cpu_clk,cpu_reset_n,
    input wire [223:0] cpu_words,
    input wire [447:0] performance_words,
    output wire serial_out
);
    // Periodic held snapshot; telemetry never backpressures CPU or audio.
    reg [CPU_SNAPSHOT_BITS-1:0] cpu_divider;
    always @(posedge cpu_clk or negedge cpu_reset_n)
        if(!cpu_reset_n) cpu_divider<=0;else cpu_divider<=cpu_divider+1'b1;
    wire [223:0] cpu_snapshot;
    gw138k_stream_cdc #(.WIDTH(224)) u_cpu_cdc(
        .reset_n(reset_n && cpu_reset_n),.source_clk(cpu_clk),.destination_clk(clk_50m),
        .source_valid(&cpu_divider),.source_data(cpu_words),.drop_count(),
        .destination_valid(),.destination_data(cpu_snapshot));
    reg [CPU_SNAPSHOT_BITS-1:0] performance_divider;
    always @(posedge audio_clk or negedge audio_reset_n)
        if(!audio_reset_n)performance_divider<=0;else performance_divider<=performance_divider+1'b1;
    wire [447:0] performance_snapshot;
    reg [223:0] extension_held;
    gw138k_stream_cdc #(.WIDTH(448)) u_performance_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(&performance_divider),.source_data(performance_words),.drop_count(),
        .destination_valid(),.destination_data(performance_snapshot));
    logic [1:0] record_kind;
    wire cpu_record=record_kind==1;

    logic [31:0] sample_count;
    (* syn_preserve=1, syn_keep=1 *) logic [31:0] sample_gray;
    always_ff @(posedge audio_clk or negedge audio_reset_n) begin
        if(!audio_reset_n) begin sample_count<=0; sample_gray<=0; end
        else begin
            if(sample_valid) sample_count<=sample_count+1'b1;
            sample_gray<=sample_count^(sample_count>>1);
        end
    end
    (* ASYNC_REG="TRUE", syn_preserve=1 *) logic [31:0] sample_meta,sample_sync;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) logic [1:0] flags_meta,flags_sync;
    logic [31:0] decoded_samples;
    integer bit_index;
    always_comb begin
        decoded_samples[31]=sample_sync[31];
        for(bit_index=30;bit_index>=0;bit_index=bit_index-1)
            decoded_samples[bit_index]=decoded_samples[bit_index+1]^sample_sync[bit_index];
    end
    always_ff @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin sample_meta<=0;sample_sync<=0;flags_meta<=0;flags_sync<=0;end
        else begin
            sample_meta<=sample_gray;sample_sync<=sample_meta;
            flags_meta<={audio_reset_n,audio_locked};flags_sync<=flags_meta;
        end
    end
    function automatic [15:0] crc_byte(input [15:0] prior,input [7:0] data);
        reg [15:0] value; integer k;
        begin
            value=prior^{data,8'd0};
            for(k=0;k<8;k=k+1) value=value[15] ? (value<<1)^16'h1021 : value<<1;
            crc_byte=value;
        end
    endfunction
    function automatic [7:0] hex_digit(input [3:0] value);
        hex_digit=value<10 ? 8'd48+{4'd0,value} : 8'd55+{4'd0,value};
    endfunction
    localparam [1:0] IDLE=0,CRC=1,SEND=2;
    logic [1:0] state;
    localparam integer INTERVAL_WIDTH=(INTERVAL_CYCLES<2)?1:$clog2(INTERVAL_CYCLES);
    logic [INTERVAL_WIDTH-1:0] interval_count;
    logic [31:0] sequence_count;
    logic [255:0] payload;
    logic [15:0] crc;
    logic [4:0] crc_index;
    logic [6:0] character;
    logic [3:0] word_character;
    logic [7:0] tx_byte;
    wire tx_ready;
    always_comb begin
        tx_byte=8'h20;
        case(character)
            0:tx_byte=record_kind==3?"E":record_kind==2?"K":cpu_record?"C":"A";1:tx_byte=cpu_record?"3":"1";2:tx_byte=cpu_record?"5":"3";3:tx_byte=cpu_record?"0":"8";4:tx_byte=" ";
            77,78,79,80:tx_byte=hex_digit(crc[15:12]);
            81:tx_byte=13;82:tx_byte=10;
            default: if(character>=5 && character<=76) begin
                if(word_character<8) tx_byte=hex_digit(payload[31:28]);
            end
        endcase
    end
    uart_tx #(.BAUD(BAUD)) u_tx(.clk(clk_50m),.rst_n(reset_n),.data({24'd0,tx_byte}),
        .valid(state==SEND),.ready(tx_ready),.serial_out(serial_out),.byte_done());
    always_ff @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            extension_held<=0;record_kind<=0;state<=IDLE;interval_count<=0;sequence_count<=0;payload<=0;crc<=16'hffff;crc_index<=0;character<=0;word_character<=0;
        end else begin
            interval_count<=interval_count==INTERVAL_CYCLES-1 ? 0 : interval_count+1;
            case(state)
                IDLE: if(interval_count==INTERVAL_CYCLES-1) begin
                    record_kind<=0;
                    payload<={video_diagnostics,audio_status,decoded_samples,
                        16'd0,memory_flags,6'd0,flags_sync,sequence_count};
                    sequence_count<=sequence_count+1;crc<=16'hffff;crc_index<=0;state<=CRC;
                end
                CRC: begin
                    // Rotate bytes through a fixed tap. After 32 cycles the
                    // snapshot is restored; avoid a 256-bit indexed mux.
                    crc<=crc_byte(crc,payload[7:0]);
                    payload<={payload[7:0],payload[255:8]};
                    if(crc_index==31) begin character<=0;word_character<=0;state<=SEND;end
                    else crc_index<=crc_index+1'b1;
                end
                SEND: if(tx_ready) begin
                    if(character>=5 && character<=76) begin
                        if(word_character<8) begin
                            payload<={payload[255:32],payload[27:0],payload[31:28]};
                            word_character<=word_character+1'b1;
                        end else begin
                            payload<={payload[31:0],payload[255:32]};
                            word_character<=0;
                        end
                    end
                    if(character>=77 && character<=80) crc<={crc[11:0],crc[15:12]};
                    if(character==82) begin
                        if(record_kind==3)state<=IDLE;
                        else if(record_kind==2)begin
                            record_kind<=3;payload<={extension_held,sequence_count-32'd1};
                            crc<=16'hffff;crc_index<=0;state<=CRC;
                        end
                        else if(cpu_record)begin
                            record_kind<=2;payload<={performance_snapshot[223:0],sequence_count-32'd1};
                            extension_held<=performance_snapshot[447:224];
                            crc<=16'hffff;crc_index<=0;state<=CRC;
                        end
                        else begin
                            record_kind<=1;payload<={cpu_snapshot,sequence_count-32'd1};
                            crc<=16'hffff;crc_index<=0;state<=CRC;
                        end
                    end else character<=character+1'b1;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
