// Tang Mega 138K board wrapper for the vendored FAT32/SPI reader.
//
// 31005 routes the Micro-SD socket to the FPGA through the SPI-compatible
// subset of the SDIO net: CMD=MOSI, DAT0=MISO, DAT3=CS and CLK=SCK.  The
// selected file is an 8.3 root-directory name at synthesis time.  The raw
// byte stream is kept separate from format probing so a decoder can be added
// later without changing the storage protocol.

module tf_audio_file_reader #(
    parameter integer FILE_NAME_LEN = 8,
    parameter [52*8-1:0] FILE_NAME = "SONG.WAV",
    // 50 MHz / (2*(100+1)) ~= 247 kHz during SD initialization, within the
    // card's <=400 kHz SPI requirement.  The reader keeps this divider for
    // data reads too; the playlist player below adds a faster data divider.
    parameter integer SPI_CLK_DIV = 100
) (
    input  wire        clk,
    input  wire        rstn,
    input  wire        sd_miso_i,
    output wire        sd_cs_n_o,
    output wire        sd_sck_o,
    output wire        sd_mosi_o,
    output wire [1:0]  card_type_o,
    output wire [3:0]  card_stat_o,
    output wire [1:0]  filesystem_type_o,
    output wire [2:0]  filesystem_stat_o,
    output wire        card_ready_o,
    output wire        file_found_o,
    output wire [31:0] file_size_o,
    output wire        file_data_valid_o,
    output wire [7:0]  file_data_o,
    output wire        file_data_last_o,
    output wire [1:0]  audio_format_o,
    output wire        audio_format_valid_o,
    output wire [31:0] file_byte_count_o
);

    wire        file_found;
    wire [31:0] file_size;
    wire        file_data_valid;
    wire [7:0]  file_data;

    // The single-file reader intentionally uses the conservative init-safe
    // divider for both phases.  tf_sd_audio_pcm_player uses a dual-rate
    // reader when sustained audio throughput is required.
    third_party_sd_spi_file_reader #(
        .FILE_NAME_LEN (FILE_NAME_LEN),
        .FILE_NAME     (FILE_NAME),
        .SPI_CLK_DIV   (SPI_CLK_DIV)
    ) u_reader (
        .rstn            (rstn),
        .clk             (clk),
        .spi_ssn         (sd_cs_n_o),
        .spi_sck         (sd_sck_o),
        .spi_mosi        (sd_mosi_o),
        .spi_miso        (sd_miso_i),
        .card_type       (card_type_o),
        .card_stat       (card_stat_o),
        .filesystem_type (filesystem_type_o),
        .filesystem_stat (filesystem_stat_o),
        .file_found      (file_found),
        .file_size_o     (file_size),
        .outen           (file_data_valid),
        .outbyte         (file_data)
    );

    assign card_ready_o = (card_stat_o == 4'd8) || (card_stat_o == 4'd9);
    assign file_found_o = file_found;
    assign file_size_o = file_size;
    assign file_data_valid_o = file_data_valid;
    assign file_data_o = file_data;
    assign file_data_last_o = file_data_valid && (file_size != 0) &&
                              (file_byte_count_o == file_size - 1'b1);

    reg [31:0] file_byte_count;
    reg [7:0] header0, header1, header2;
    reg [7:0] wav8, wav9, wav10;
    reg [1:0] audio_format;
    reg       audio_format_valid;

    // 0=unknown, 1=MP3, 2=WAV/RIFF, 3=FLAC.  Detection is a signature probe;
    // it does not claim to decode any of these formats.
    always @(posedge clk or negedge rstn) begin
        if (!rstn) begin
            file_byte_count <= 32'd0;
            header0 <= 8'd0;
            header1 <= 8'd0;
            header2 <= 8'd0;
            wav8 <= 8'd0;
            wav9 <= 8'd0;
            wav10 <= 8'd0;
            audio_format <= 2'd0;
            audio_format_valid <= 1'b0;
        end else if (file_data_valid) begin
            if (file_byte_count == 0) header0 <= file_data;
            if (file_byte_count == 1) header1 <= file_data;
            if (file_byte_count == 2) header2 <= file_data;
            if (file_byte_count == 8) wav8 <= file_data;
            if (file_byte_count == 9) wav9 <= file_data;
            if (file_byte_count == 10) wav10 <= file_data;

            if (!audio_format_valid) begin
                if (file_byte_count == 2 && header0 == 8'h49 &&
                    header1 == 8'h44 && file_data == 8'h33) begin
                    audio_format <= 2'd1;
                    audio_format_valid <= 1'b1;
                end else if (file_byte_count == 1 && header0 == 8'hFF &&
                             file_data[7:5] == 3'b111) begin
                    audio_format <= 2'd1;
                    audio_format_valid <= 1'b1;
                end else if (file_byte_count == 3 && header0 == 8'h66 &&
                             header1 == 8'h4C && header2 == 8'h61 &&
                             file_data == 8'h63) begin
                    audio_format <= 2'd3;
                    audio_format_valid <= 1'b1;
                end else if (file_byte_count == 11 && header0 == 8'h52 &&
                             header1 == 8'h49 && header2 == 8'h46 &&
                             wav8 == 8'h57 && wav9 == 8'h41 &&
                             wav10 == 8'h56 && file_data == 8'h45) begin
                    audio_format <= 2'd2;
                    audio_format_valid <= 1'b1;
                end
            end
            file_byte_count <= file_byte_count + 1'b1;
        end
    end

    assign audio_format_o = audio_format;
    assign audio_format_valid_o = audio_format_valid;
    assign file_byte_count_o = file_byte_count;

endmodule
