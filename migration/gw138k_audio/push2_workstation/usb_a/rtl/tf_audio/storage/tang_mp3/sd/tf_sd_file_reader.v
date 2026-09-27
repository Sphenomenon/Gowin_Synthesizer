//--------------------------------------------------------------------------------------------------------
// Module  : sd_file_reader
// Type    : synthesizable
// Standard: Verilog 2001 (IEEE1364-2001)
// License : GPL-3.0 (see repo root)
//
// Multi-track playlist reader for FAT16/FAT32 SD cards over SPI, filtering
// the root directory by file EXTENSION (parameter EXT).
//
// Forked from tang_fm_transmitter's sd_wav_player, which hardcoded "*.WAV".
// The only functional change is that the extension is now a parameter, so the
// same core serves M2 (EXT="WAV") and M3 onward (EXT="MP3"). Everything below
// is unchanged and was verified there against FAT16 and FAT32 images.
//
// Derivative of WangXuan95's sd_spi_file_reader (FPGA-SDcard-Reader-SPI,
// GPL-3.0): the card-init/sector/FAT-chain FSM skeleton is retained; the
// rest is reworked for a small Gowin GW1N-9 with the yosys flow:
//   - boot-sector fields captured in fixed-offset registers instead of a
//     sector_content[0:511] array (the array's async read ports cost ~9.7k
//     LUT4s — more than the chip has)
//   - clean 8.3-only root-directory parser. The original's LFN assembly
//     needed 52-byte arrays with dynamic write indices (very expensive
//     here); every long-named file also carries a short 8.3 entry, so
//     nothing is missed — names just display in 8.3 form
//   - FAT32 fix: the original captured only the low cluster word (dir
//     bytes 0x1A/0x1B); bytes 0x14/0x15 are now captured too, so files
//     beyond cluster 65535 work
//   - instead of matching ONE compile-time filename, collects every *.EXT
//     root entry (up to MAX_TRACKS) into playlist RAMs: 12-char display
//     name, first cluster, byte size
//   - track_index/track_start control with clean sector-boundary switching,
//     eof pulse at end of track, and a sector_allow input that throttles
//     data-sector reads to the consumer's FIFO space
//--------------------------------------------------------------------------------------------------------

module tf_sd_file_reader #(
    parameter [23:0] EXT       = "WAV", // 8.3 extension to collect, upper case
    parameter SPI_CLK_DIV      = 100, // SPI divider during card init (270 kHz at 54 MHz)
    parameter SPI_CLK_DIV_FAST = 12,  // SPI divider during sector reads (2.25 MHz at 54 MHz)
                                      // Halved from 6 (4.5 MHz) to cut coupling into the
                                      // onboard PT8211: SPI activity was measurably the
                                      // source of an audible 2-3 Hz tick (see bringup log).
                                      // 2.25 MHz still moves ~281 KB/s, against 64 KB/s for
                                      // 32 kHz mono WAV and only 40 KB/s for 320 kbps MP3.
    parameter MAX_TRACKS       = 16
) (
    input  wire        rstn,
    input  wire        clk,
    // SD card SPI interface
    output wire        spi_ssn,
    output wire        spi_sck,
    output wire        spi_mosi,
    input  wire        spi_miso,
    // status
    output wire [1:0]  card_type,
    output wire [3:0]  card_stat,
    output wire [1:0]  filesystem_type,
    output wire [2:0]  filesystem_stat,   // = FSM state, see localparams
    output wire        scan_done,         // playlist valid, ready to play
    output reg  [4:0]  track_count,
    // track control
    input  wire [3:0]  track_index,
    input  wire        track_start,       // pulse: (re)start playing track_index
    output reg         playing,
    output reg         eof,               // 1-cycle pulse at end of track
    // flow control: high = consumer has room for a full 512-byte sector
    input  wire        sector_allow,
    // file content stream
    output reg         outen,
    output reg  [7:0]  outbyte,
    // playlist name RAM read port: addr = track*12 + char, 12 chars per
    // track in "NNNNNNNN.EEE" layout (space-padded 8.3)
    input  wire [7:0]  name_raddr,
    output wire [7:0]  name_rdata,
    output wire [7:0]  debug_cmdrsp,
    output wire [7:0]  debug_rwrsp,
    output wire [3:0]  debug_cardstate,
    output wire        debug_spidone,
    output wire        debug_rvalid_session
);

localparam [2:0] RESET         = 3'd0,
                 SEARCH_MBR    = 3'd1,
                 SEARCH_DBR    = 3'd2,
                 LS_ROOT_FAT16 = 3'd3,
                 LS_ROOT_FAT32 = 3'd4,
                 READ_A_FILE   = 3'd5,
                 DONE          = 3'd6,   // filesystem error, parked
                 READY         = 3'd7;   // playlist ready / between tracks

localparam [1:0] UNASSIGNED = 2'd0,
                 UNKNOWN    = 2'd1,
                 FAT16      = 2'd2,
                 FAT32      = 2'd3;

reg [2:0] filesystem_state = RESET;
reg [1:0] filesystem = UNASSIGNED;

assign filesystem_type = filesystem;
assign filesystem_stat = filesystem_state;
assign scan_done       = (filesystem_state == READY) || (filesystem_state == READ_A_FILE);

//----------------------------------------------------------------------------------------------------------------------
// sector reader (vendor, dual-rate SPI mod)
//----------------------------------------------------------------------------------------------------------------------
reg         read_start     = 1'b0;
reg  [31:0] read_sector_no = 0;
wire        read_done;
wire        rvalid;
wire [ 8:0] raddr;
wire [ 7:0] rdata;

tf_sd_spi_sector_reader #(
    .SPI_CLK_DIV      ( SPI_CLK_DIV      ),
    .SPI_CLK_DIV_FAST ( SPI_CLK_DIV_FAST )
) u_sector_reader (
    .rstn      ( rstn           ),
    .clk       ( clk            ),
    .spi_ssn   ( spi_ssn        ),
    .spi_sck   ( spi_sck        ),
    .spi_mosi  ( spi_mosi       ),
    .spi_miso  ( spi_miso       ),
    .card_type ( card_type      ),
    .card_stat ( card_stat      ),
    .start     ( read_start     ),
    .sector_no ( read_sector_no ),
    .done      ( read_done      ),
    .rvalid    ( rvalid         ),
    .raddr     ( raddr          ),
    .rdata     ( rdata          ),
    .debug_cmdrsp         ( debug_cmdrsp ),
    .debug_rwrsp          ( debug_rwrsp ),
    .debug_cardstate      ( debug_cardstate ),
    .debug_spidone        ( debug_spidone ),
    .debug_rvalid_session ( debug_rvalid_session )
);

//----------------------------------------------------------------------------------------------------------------------
// boot-sector (MBR/DBR) field capture — fixed offsets, sync-only block
//----------------------------------------------------------------------------------------------------------------------
reg        sig_55, sig_aa, byte0_jmp, fat32_sig;
reg [31:0] dbr_sector_no;
reg [15:0] bytes_per_sector;
reg [ 7:0] sector_per_cluster;
reg [15:0] resv_sectors;
reg [ 7:0] number_of_fat;
reg [15:0] rootdir_itemcount;   // FAT16 only
reg [15:0] spf16;
reg [31:0] spf32;
reg [31:0] root_cluster_r;      // FAT32 only

always @(posedge clk) begin
    if (rvalid && (filesystem_state == SEARCH_MBR || filesystem_state == SEARCH_DBR)) begin
        case (raddr)
            9'h000: byte0_jmp               <= (rdata == 8'hEB || rdata == 8'hE9);
            9'h00B: bytes_per_sector[ 7:0]  <= rdata;
            9'h00C: bytes_per_sector[15:8]  <= rdata;
            9'h00D: sector_per_cluster      <= rdata;
            9'h00E: resv_sectors[ 7:0]      <= rdata;
            9'h00F: resv_sectors[15:8]      <= rdata;
            9'h010: number_of_fat           <= rdata;
            9'h011: rootdir_itemcount[ 7:0] <= rdata;
            9'h012: rootdir_itemcount[15:8] <= rdata;
            9'h016: spf16[ 7:0]             <= rdata;
            9'h017: spf16[15:8]             <= rdata;
            9'h024: spf32[ 7:0]             <= rdata;
            9'h025: spf32[15:8]             <= rdata;
            9'h026: spf32[23:16]            <= rdata;
            9'h027: spf32[31:24]            <= rdata;
            9'h02C: root_cluster_r[ 7:0]    <= rdata;
            9'h02D: root_cluster_r[15:8]    <= rdata;
            9'h02E: root_cluster_r[23:16]   <= rdata;
            9'h02F: root_cluster_r[31:24]   <= rdata;
            9'h056: fat32_sig               <= (rdata == 8'h32);
            9'h1C6: dbr_sector_no[ 7:0]     <= rdata;
            9'h1C7: dbr_sector_no[15:8]     <= rdata;
            9'h1C8: dbr_sector_no[23:16]    <= rdata;
            9'h1C9: dbr_sector_no[31:24]    <= rdata;
            9'h1FE: sig_55                  <= (rdata == 8'h55);
            9'h1FF: sig_aa                  <= (rdata == 8'hAA);
            default: ;
        endcase
    end
end

wire is_boot_sector = sig_55 & sig_aa;
wire is_dbr         = byte0_jmp;

reg [1:0]  filesystem_parsed;
reg [31:0] sectors_per_fat_w;
reg [31:0] root_cluster_w;
always @(*) begin
    sectors_per_fat_w = {16'h0, spf16};
    root_cluster_w    = 0;
    if (spf16 != 16'h0) begin
        filesystem_parsed = FAT16;
    end else if (fat32_sig) begin
        filesystem_parsed = FAT32;
        sectors_per_fat_w = spf32;
        root_cluster_w    = root_cluster_r;
    end else begin
        filesystem_parsed = UNKNOWN;
    end
end

//----------------------------------------------------------------------------------------------------------------------
// root-directory entry parser — plain 8.3, fixed offsets, sync-only block
//----------------------------------------------------------------------------------------------------------------------
reg        search_fat = 1'b0;
wire       parsing_root = (filesystem_state == LS_ROOT_FAT16 || filesystem_state == LS_ROOT_FAT32) && ~search_fat;

reg [7:0]  ename0, ename1, ename2, ename3, ename4, ename5, ename6, ename7;  // name
reg [7:0]  eext0, eext1, eext2;                                              // extension
reg        entry_valid, entry_isfile;
reg        dir_end;
reg [31:0] ecluster;
reg [31:0] esize;
reg        eready;    // 1-cycle pulse: a plain-file entry finished parsing

always @(posedge clk or negedge rstn) begin
    if (!rstn) begin
        entry_valid <= 1'b0;
        entry_isfile<= 1'b0;
        dir_end     <= 1'b0;
        eready      <= 1'b0;
        ecluster    <= 0;
        esize       <= 0;
    end else begin
        eready <= 1'b0;
        if (rvalid && parsing_root) begin
            case (raddr[4:0])
                5'h00: begin
                    // !dir_end: entries after the 0x00 end marker are free
                    // space and may contain junk — never treat them as files
                    entry_valid <= !dir_end && (rdata != 8'hE5 && rdata != 8'h00 && rdata != 8'h2E);
                    if (rdata == 8'h00) dir_end <= 1'b1;   // end-of-directory marker
                end
                5'h0B: entry_isfile     <= (rdata == 8'h20);  // plain archive file
                                                              // (skips LFN 0x0F, dirs, volume)
                5'h14: ecluster[23:16]  <= rdata;             // FAT32 high word
                5'h15: ecluster[31:24]  <= rdata;
                5'h1A: ecluster[ 7:0]   <= rdata;
                5'h1B: ecluster[15:8]   <= rdata;
                5'h1C: esize[ 7:0]      <= rdata;
                5'h1D: esize[15:8]      <= rdata;
                5'h1E: esize[23:16]     <= rdata;
                5'h1F: begin
                    esize[31:24] <= rdata;
                    eready       <= entry_valid & entry_isfile;
                end
                default: ;
            endcase
        end
    end
end

// name bytes: fixed offsets, no reset needed (validity gated by eready)
always @(posedge clk) begin
    if (rvalid && parsing_root) begin
        case (raddr[4:0])
            5'h00: ename0 <= (rdata == 8'h05) ? 8'hE5 : rdata;  // 0x05 = KANJI escape for 0xE5
            5'h01: ename1 <= rdata;
            5'h02: ename2 <= rdata;
            5'h03: ename3 <= rdata;
            5'h04: ename4 <= rdata;
            5'h05: ename5 <= rdata;
            5'h06: ename6 <= rdata;
            5'h07: ename7 <= rdata;
            5'h08: eext0  <= rdata;
            5'h09: eext1  <= rdata;
            5'h0A: eext2  <= rdata;
            default: ;
        endcase
    end
end

// FAT16 cluster numbers are only 16 bits — mask the high word there
wire [31:0] ecluster_fs = (filesystem == FAT16) ? {16'h0, ecluster[15:0]} : ecluster;

//----------------------------------------------------------------------------------------------------------------------
// playlist collection: *.EXT entries -> name/cluster/size RAMs
//----------------------------------------------------------------------------------------------------------------------
// Directory entries store the 8.3 extension already upper-cased, and EXT is
// documented as upper case, so a plain compare is enough.
wire entry_is_match = (eext0 == EXT[23:16]) &&
                      (eext1 == EXT[15: 8]) &&
                      (eext2 == EXT[ 7: 0]);

reg [7:0]  name_ram [0:191];             // MAX_TRACKS(16) * 12 chars
reg [31:0] cluster_ram [0:15];
// BSRAM, not distributed RAM. yosys built this 16 x 32 array from RAM16SDP4
// cells, which have far tighter placement rules than ordinary LUTs -- nextpnr
// could not site them once the decoder filled the device, even at 56% LUT
// occupancy. Registers were tried first and cost ~1200 LUTs for the 16:1 mux,
// pushing density back up until the ALU chains stopped placing again. The read
// is already synchronous, so a block RAM costs one BSRAM and no logic.
(* ram_style = "block" *)
reg [31:0] size_ram [0:15];

// REGISTERED read, not asynchronous. An async read forces distributed RAM
// (20 x RAM16SDP4 here), and those have tight siting rules -- with the m7 UI
// reading this every cycle, placement could not legalise them. A registered
// read infers one BSRAM instead. Consumers must present the address one cycle
// earlier; ui_ctrl does.
reg [7:0] name_rdata_r;
always @(posedge clk) name_rdata_r <= name_ram[name_raddr];
assign name_rdata = name_rdata_r;

// 12-cycle name copy: "NNNNNNNN.EEE"
reg        ncopy_active = 1'b0;
reg [3:0]  ncopy_i;
reg [3:0]  ncopy_track;
reg [7:0]  ncopy_buf [0:11];             // parallel-latched on eready

// addr = track*12 + char  (12t = 8t + 4t)
wire [7:0] ncopy_addr = {1'b0, ncopy_track, 3'b0} + {2'b0, ncopy_track, 2'b0} + {4'b0, ncopy_i};

wire       collect = eready && entry_is_match && (track_count < MAX_TRACKS[4:0]) && !ncopy_active;

always @(posedge clk) begin
    if (collect) begin
        ncopy_buf[0]  <= ename0;
        ncopy_buf[1]  <= ename1;
        ncopy_buf[2]  <= ename2;
        ncopy_buf[3]  <= ename3;
        ncopy_buf[4]  <= ename4;
        ncopy_buf[5]  <= ename5;
        ncopy_buf[6]  <= ename6;
        ncopy_buf[7]  <= ename7;
        ncopy_buf[8]  <= ".";
        ncopy_buf[9]  <= eext0;
        ncopy_buf[10] <= eext1;
        ncopy_buf[11] <= eext2;
        cluster_ram[track_count[3:0]] <= ecluster_fs;
        size_ram[track_count[3:0]]    <= esize;
    end
    if (ncopy_active)
        name_ram[ncopy_addr] <= ncopy_buf[ncopy_i];
end

always @(posedge clk or negedge rstn) begin
    if (!rstn) begin
        track_count  <= 0;
        ncopy_active <= 1'b0;
        ncopy_i      <= 0;
        ncopy_track  <= 0;
    end else begin
        if (collect) begin
            ncopy_track  <= track_count[3:0];
            ncopy_i      <= 0;
            ncopy_active <= 1'b1;
            track_count  <= track_count + 1'b1;
        end else if (ncopy_active) begin
            if (ncopy_i == 4'd11) ncopy_active <= 1'b0;
            else                  ncopy_i      <= ncopy_i + 1'b1;
        end
    end
end

//----------------------------------------------------------------------------------------------------------------------
// track request latching
//----------------------------------------------------------------------------------------------------------------------
reg       start_req = 1'b0;
reg [3:0] req_idx   = 0;

//----------------------------------------------------------------------------------------------------------------------
// main FSM (skeleton from vendor sd_spi_file_reader)
//----------------------------------------------------------------------------------------------------------------------
reg [31:0] rootdir_sector = 0;        // FAT16 only
reg [15:0] rootdir_sectorcount = 0;   // FAT16 only
reg [31:0] curr_cluster = 0;
reg [ 7:0] cluster_sector_offset = 8'h0;
reg [31:0] file_size = 0;
reg [ 7:0] cluster_size = 0;
reg [ 2:0] cluster_shift = 3'd0;      // log2(cluster_size) — cluster sizes are
                                      // powers of two, so sector arithmetic
                                      // uses shifts, not 8x32 multipliers
reg [31:0] first_fat_sector_no = 0;
reg [31:0] first_data_sector_no = 0;

function [2:0] log2cs(input [7:0] v);
    casez (v)
        8'b1???????: log2cs = 3'd7;
        8'b01??????: log2cs = 3'd6;
        8'b001?????: log2cs = 3'd5;
        8'b0001????: log2cs = 3'd4;
        8'b00001???: log2cs = 3'd3;
        8'b000001??: log2cs = 3'd2;
        8'b0000001?: log2cs = 3'd1;
        default:     log2cs = 3'd0;
    endcase
endfunction
reg        inflight = 1'b0;
reg        load_track;                // pulse: clear fptr

wire [ 6:0] curr_cluster_fat_offset;        // FAT32: 128 entries/sector
wire [24:0] curr_cluster_fat_no;
assign {curr_cluster_fat_no, curr_cluster_fat_offset} = curr_cluster;

wire [ 7:0] curr_cluster_fat_offset_fat16;  // FAT16: 256 entries/sector
wire [23:0] curr_cluster_fat_no_fat16;
assign {curr_cluster_fat_no_fat16, curr_cluster_fat_offset_fat16} = curr_cluster;

reg  [31:0] target_cluster = 0;
reg  [15:0] target_cluster_fat16 = 16'h0;

reg [31:0] fptr = 0;

always @(posedge clk or negedge rstn) begin
    if (!rstn) begin
        read_start <= 1'b0;
        read_sector_no <= 0;
        filesystem_state <= RESET;
        filesystem <= UNASSIGNED;
        search_fat <= 1'b0;
        cluster_size = 8'h0;
        first_fat_sector_no   = 0;
        first_data_sector_no  = 0;
        curr_cluster          = 0;
        cluster_sector_offset = 8'h0;
        rootdir_sector        = 0;
        rootdir_sectorcount   = 16'h0;
        file_size  <= 0;
        inflight   <= 1'b0;
        playing    <= 1'b0;
        eof        <= 1'b0;
        load_track <= 1'b0;
        start_req  <= 1'b0;
        req_idx    <= 0;
    end else begin
        read_start <= 1'b0;
        eof        <= 1'b0;
        load_track <= 1'b0;

        if (track_start) begin
            start_req <= 1'b1;
            req_idx   <= track_index;
        end

        if (read_done) begin
            inflight <= 1'b0;
            case (filesystem_state)
            SEARCH_MBR :    if (is_boot_sector) begin
                                filesystem_state <= SEARCH_DBR;
                                if (~is_dbr) read_sector_no <= dbr_sector_no;
                            end else begin
                                read_sector_no <= read_sector_no + 1;
                            end
            SEARCH_DBR :    if (is_boot_sector && is_dbr) begin
                                if (bytes_per_sector != 16'd512) begin
                                    filesystem_state <= DONE;
                                end else begin
                                    filesystem <= filesystem_parsed;
                                    if (filesystem_parsed == FAT16) begin
                                        cluster_size        = sector_per_cluster;
                                        cluster_shift       = log2cs(sector_per_cluster);
                                        first_fat_sector_no = read_sector_no + resv_sectors;
                                        rootdir_sectorcount = rootdir_itemcount / (16'd512 / 16'd32);
                                        rootdir_sector      = first_fat_sector_no +
                                            ((number_of_fat == 8'd2) ? {sectors_per_fat_w[30:0], 1'b0} : sectors_per_fat_w);
                                        first_data_sector_no= rootdir_sector + rootdir_sectorcount - {cluster_size[6:0], 1'b0};
                                        cluster_sector_offset = 8'h0;
                                        read_sector_no      <= rootdir_sector;
                                        filesystem_state    <= LS_ROOT_FAT16;
                                    end else if (filesystem_parsed == FAT32) begin
                                        cluster_size        = sector_per_cluster;
                                        cluster_shift       = log2cs(sector_per_cluster);
                                        first_fat_sector_no = read_sector_no + resv_sectors;
                                        first_data_sector_no= first_fat_sector_no +
                                            ((number_of_fat == 8'd2) ? {sectors_per_fat_w[30:0], 1'b0} : sectors_per_fat_w)
                                            - {cluster_size[6:0], 1'b0};
                                        curr_cluster        = root_cluster_w;
                                        cluster_sector_offset = 8'h0;
                                        read_sector_no      <= first_data_sector_no + (curr_cluster << cluster_shift);
                                        filesystem_state    <= LS_ROOT_FAT32;
                                    end else begin
                                        filesystem_state <= DONE;
                                    end
                                end
                            end
            LS_ROOT_FAT16 : if (dir_end) begin
                                filesystem_state <= READY;
                            end else if (cluster_sector_offset < rootdir_sectorcount - 1) begin
                                cluster_sector_offset = cluster_sector_offset + 8'd1;
                                read_sector_no <= rootdir_sector + cluster_sector_offset;
                            end else begin
                                filesystem_state <= READY;   // scanned the whole root dir
                            end
            LS_ROOT_FAT32 : if (~search_fat) begin
                                if (dir_end) begin
                                    filesystem_state <= READY;
                                end else if (cluster_sector_offset < (cluster_size - 1)) begin
                                    cluster_sector_offset = cluster_sector_offset + 8'd1;
                                    read_sector_no <= first_data_sector_no + (curr_cluster << cluster_shift) + cluster_sector_offset;
                                end else begin   // read FAT to get next root cluster
                                    search_fat <= 1'b1;
                                    cluster_sector_offset = 8'h0;
                                    read_sector_no <= first_fat_sector_no + curr_cluster_fat_no;
                                end
                            end else begin
                                search_fat <= 1'b0;
                                cluster_sector_offset = 8'h0;
                                if (target_cluster == 'h0FFF_FFFF || target_cluster == 'h0FFF_FFF8 ||
                                    target_cluster == 'hFFFF_FFFF || target_cluster < 2) begin
                                    filesystem_state <= READY;   // end of root chain
                                end else begin
                                    curr_cluster = target_cluster;
                                    read_sector_no <= first_data_sector_no + (curr_cluster << cluster_shift);
                                end
                            end
            READ_A_FILE  :  if (start_req) begin
                                playing <= 1'b0;                 // track switch at sector boundary
                                search_fat <= 1'b0;
                                filesystem_state <= READY;
                            end else if (fptr >= file_size) begin
                                playing <= 1'b0;
                                eof     <= 1'b1;
                                search_fat <= 1'b0;
                                filesystem_state <= READY;
                            end else if (~search_fat) begin
                                if (cluster_sector_offset < (cluster_size - 1)) begin
                                    cluster_sector_offset = cluster_sector_offset + 8'd1;
                                    read_sector_no <= first_data_sector_no + (curr_cluster << cluster_shift) + cluster_sector_offset;
                                end else begin   // read FAT to get next cluster
                                    search_fat <= 1'b1;
                                    cluster_sector_offset = 8'h0;
                                    read_sector_no <= first_fat_sector_no +
                                        ((filesystem == FAT16) ? {8'h0, curr_cluster_fat_no_fat16} : {7'h0, curr_cluster_fat_no});
                                end
                            end else begin
                                search_fat <= 1'b0;
                                cluster_sector_offset = 8'h0;
                                if (filesystem == FAT16) begin
                                    if (target_cluster_fat16 >= 16'hFFF0 || target_cluster_fat16 < 16'h2) begin
                                        playing <= 1'b0;
                                        eof     <= 1'b1;
                                        filesystem_state <= READY;   // chain ended before size — treat as EOF
                                    end else begin
                                        curr_cluster = {16'h0, target_cluster_fat16};
                                        read_sector_no <= first_data_sector_no + (curr_cluster << cluster_shift);
                                    end
                                end else begin
                                    if (target_cluster == 'h0FFF_FFFF || target_cluster == 'h0FFF_FFF8 ||
                                        target_cluster == 'hFFFF_FFFF || target_cluster < 2) begin
                                        playing <= 1'b0;
                                        eof     <= 1'b1;
                                        filesystem_state <= READY;
                                    end else begin
                                        curr_cluster = target_cluster;
                                        read_sector_no <= first_data_sector_no + (curr_cluster << cluster_shift);
                                    end
                                end
                            end
            default: ;
            endcase
        end else begin
            case (filesystem_state)
                RESET         : filesystem_state <= SEARCH_MBR;
                SEARCH_MBR    : begin read_start <= 1'b1; inflight <= 1'b1; end
                SEARCH_DBR    : begin read_start <= 1'b1; inflight <= 1'b1; end
                LS_ROOT_FAT16 : begin read_start <= 1'b1; inflight <= 1'b1; end
                LS_ROOT_FAT32 : begin read_start <= 1'b1; inflight <= 1'b1; end
                READY         : if (start_req) begin
                                    start_req <= 1'b0;
                                    curr_cluster = cluster_ram[req_idx];
                                    file_size <= size_ram[req_idx];
                                    cluster_sector_offset = 8'h0;
                                    read_sector_no <= first_data_sector_no + (cluster_ram[req_idx] << cluster_shift);
                                    load_track <= 1'b1;
                                    playing    <= 1'b1;
                                    filesystem_state <= READ_A_FILE;
                                end
                READ_A_FILE   : if (inflight || search_fat || sector_allow) begin
                                    read_start <= 1'b1;
                                    inflight   <= 1'b1;
                                end
                default: ;   // DONE: parked on filesystem error
            endcase
        end
    end
end

//----------------------------------------------------------------------------------------------------------------------
// FAT table entry capture (vendor logic)
//----------------------------------------------------------------------------------------------------------------------
always @(posedge clk or negedge rstn) begin
    if (!rstn) begin
        target_cluster <= 0;
        target_cluster_fat16 <= 16'h0;
    end else begin
        if (search_fat && rvalid) begin
            if (filesystem == FAT16) begin
                if (raddr[8:1] == curr_cluster_fat_offset_fat16)
                    target_cluster_fat16[8*raddr[0] +: 8] <= rdata;
            end else if (filesystem == FAT32) begin
                if (raddr[8:2] == curr_cluster_fat_offset)
                    target_cluster[8*raddr[1:0] +: 8] <= rdata;
            end
        end
    end
end

//----------------------------------------------------------------------------------------------------------------------
// file content output (vendor logic + track-switch fptr clear)
//----------------------------------------------------------------------------------------------------------------------
always @(posedge clk or negedge rstn) begin
    if (!rstn) begin
        fptr <= 0;
        {outen, outbyte} <= 0;
    end else begin
        if (load_track) begin
            fptr <= 0;
            {outen, outbyte} <= 0;
        end else if (rvalid && filesystem_state == READ_A_FILE && ~search_fat && fptr < file_size) begin
            fptr <= fptr + 1;
            {outen, outbyte} <= {1'b1, rdata};
        end else begin
            {outen, outbyte} <= 0;
        end
    end
end

endmodule
