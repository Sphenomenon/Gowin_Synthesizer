`timescale 1ns/1ps
`default_nettype none
// SPDX-License-Identifier: GPL-3.0-only
// Maintained unselected adaptation. Original notices below are retained.
// Exact reversible changes: workstation_tf_file_reader.provenance.json.
// Contract: WORKSTATION_TF_FILE_READER_CONTRACT.md. CRC is drained, not checked.
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

module workstation_tf_file_reader #(
    parameter [23:0] EXT       = "WAV", // 8.3 extension to collect, upper case
    parameter SPI_CLK_DIV      = 100, // SPI divider during card init (270 kHz at 54 MHz)
    parameter SPI_CLK_DIV_FAST = 12,  // SPI divider during sector reads (2.25 MHz at 54 MHz)
                                      // Halved from 6 (4.5 MHz) to cut coupling into the
                                      // onboard PT8211: SPI activity was measurably the
                                      // source of an audible 2-3 Hz tick (see bringup log).
                                      // 2.25 MHz still moves ~281 KB/s, against 64 KB/s for
                                      // 32 kHz mono WAV and only 40 KB/s for 320 kbps MP3.
    parameter MAX_TRACKS       = 16,
    parameter [25:0] PROBE_INTERVAL_CYCLES = 26'd50_000_000,
    parameter integer TOKEN_WAIT_CLOCKS = 8320000,
    parameter integer WATCHDOG_CLOCKS = 250000000,
    parameter integer MAX_ROOT_SECTORS = 4096,
    parameter integer VERIFY_DATA_CRC = 0,
    parameter integer FAT_SECTOR_CACHE = 0
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
    output wire        sector_busy,
    output reg  [4:0]  track_count,
    // track control
    input  wire [3:0]  track_index,
    input  wire        track_start,       // latest request, apply at a drained sector boundary
    input  wire        stop,              // level hold; cancel wins a simultaneous start
    output reg         cancelled,
    output reg         track_applied,
    output wire        data_sector_start, // sector_allow handshake, reserves exactly 512 bytes
    output reg         file_error,
    output reg  [3:0]  file_error_code,
    output reg         playing,
    output reg         eof,               // 1-cycle pulse at end of track
    // flow control: high = consumer has room for a full 512-byte sector
    input  wire        sector_allow,
    // file content stream
    output wire        outen,
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

//----------------------------------------------------------------------------------------------------------------------
// sector reader (vendor, dual-rate SPI mod)
//----------------------------------------------------------------------------------------------------------------------
reg         read_start     = 1'b0;
reg  [31:0] read_sector_no = 0;
wire        read_done, read_error;
wire [1:0] read_error_code;
wire transport_rstn = rstn && !file_error;
initial begin
    if ((FAT_SECTOR_CACHE!=0 && FAT_SECTOR_CACHE!=1) ||
        (FAT_SECTOR_CACHE!=0 && VERIFY_DATA_CRC!=1))
        $fatal(1,"native FAT cache requires explicit CRC verification");
    if (MAX_TRACKS < 1 || MAX_TRACKS > 16 || MAX_ROOT_SECTORS < 1 || WATCHDOG_CLOCKS < 1)
        $fatal(1,"native TF file reader parameter range");
end
wire        rvalid;
wire [ 8:0] raddr;
wire [ 7:0] rdata;

workstation_tf_sd_sector_reader #(
    .SPI_CLK_DIV      ( SPI_CLK_DIV      ),
    .SPI_CLK_DIV_FAST ( SPI_CLK_DIV_FAST ),
    .TOKEN_WAIT_CLOCKS( TOKEN_WAIT_CLOCKS ),
    .VERIFY_DATA_CRC  ( VERIFY_DATA_CRC )
) u_sector_reader (
    .rstn      ( transport_rstn ),
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
    .read_error ( read_error     ),
    .read_error_code(read_error_code),
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
reg [15:0] total16, fat32_flags, fat32_version;
reg [31:0] total32, partition_sectors;
reg [7:0] partition_type;

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
            9'h013: total16[7:0]            <= rdata;
            9'h014: total16[15:8]           <= rdata;
            9'h020: total32[7:0]            <= rdata;
            9'h021: total32[15:8]           <= rdata;
            9'h022: total32[23:16]          <= rdata;
            9'h023: total32[31:24]          <= rdata;
            9'h028: fat32_flags[7:0]        <= rdata;
            9'h029: fat32_flags[15:8]       <= rdata;
            9'h02A: fat32_version[7:0]      <= rdata;
            9'h02B: fat32_version[15:8]     <= rdata;
            9'h1C2: partition_type          <= rdata;
            9'h1CA: partition_sectors[7:0]  <= rdata;
            9'h1CB: partition_sectors[15:8] <= rdata;
            9'h1CC: partition_sectors[23:16]<= rdata;
            9'h1CD: partition_sectors[31:24]<= rdata;
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
reg [15:0] rootdir_offset;
wire       parsing_root = (filesystem_state == LS_ROOT_FAT16 || filesystem_state == LS_ROOT_FAT32) && ~search_fat &&
    (filesystem_state != LS_ROOT_FAT16 || ({16'd0,rootdir_offset}*32'd16 + {28'd0,raddr[8:5]}) < {16'd0,rootdir_itemcount});

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
wire [31:0] ecluster_fs = (filesystem == FAT16) ? {16'h0, ecluster[15:0]} : {4'd0,ecluster[27:0]};

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
always @(posedge clk) name_rdata_r <= (name_raddr < 8'd192) ? name_ram[name_raddr] : 8'd0;
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
// Maintained owner: fixed first primary partition/superfloppy, bounded root,
// exact file length and terminal failures. No second SD controller or DDR.
//----------------------------------------------------------------------------------------------------------------------
reg start_req,stop_req,stop_q;
reg [3:0] req_idx;
reg [25:0] probe_timer;
reg probe_pending;
reg [31:0] probe_resume_sector;
reg [31:0] rootdir_sector, curr_cluster, file_size;
reg [15:0] rootdir_sectorcount;
reg [7:0] cluster_sector_offset,cluster_size;
reg [2:0] cluster_shift;
reg [31:0] first_fat_sector_no,first_data_sector_no,cluster_limit;
reg [31:0] root_sectors_scanned,watchdog;
reg [31:0] partition_limit;
reg partitioned,final_fat,inflight,load_track;
reg [31:0] target_cluster;
reg [15:0] target_cluster_fat16;
reg [31:0] fptr;
localparam [3:0] ERR_TRANSPORT=1,ERR_WATCHDOG=2,ERR_BOOT=3,ERR_BPB=4,
    ERR_CLUSTER=5,ERR_EARLY_EOC=6,ERR_ROOT_LIMIT=7,ERR_TRACK=8,ERR_CHAIN_LENGTH=9;

function [2:0] log2cs(input [7:0] v);
    case(v)
        128:log2cs=7;64:log2cs=6;32:log2cs=5;16:log2cs=4;
        8:log2cs=3;4:log2cs=2;2:log2cs=1;default:log2cs=0;
    endcase
endfunction
wire [31:0] total_sectors = total16 != 0 ? {16'd0,total16} : total32;
wire [16:0] root_round = ({1'b0,rootdir_itemcount}+17'd15)>>4;
wire [32:0] fat_span = number_of_fat == 2 ? {sectors_per_fat_w,1'b0} : {1'b0,sectors_per_fat_w};
wire [32:0] data_offset = {17'd0,resv_sectors}+fat_span+
    (filesystem_parsed==FAT16 ? {16'd0,root_round} : 33'd0);
wire [32:0] volume_end = {1'b0,read_sector_no}+{1'b0,total_sectors};
wire [31:0] parsed_clusters = (total_sectors-data_offset[31:0]) >> log2cs(sector_per_cluster);
wire [63:0] fat_bytes = {32'd0,sectors_per_fat_w} << 9;
wire [63:0] required_fat_bytes = ({32'd0,parsed_clusters}+64'd2) << (filesystem_parsed==FAT16 ? 1 : 2);
wire valid_geometry = bytes_per_sector==512 && sector_per_cluster!=0 &&
    (sector_per_cluster & (sector_per_cluster-8'd1))==0 &&
    resv_sectors!=0 && (number_of_fat==1 || number_of_fat==2) &&
    sectors_per_fat_w!=0 && total_sectors!=0 && !data_offset[32] &&
    data_offset < {1'b0,total_sectors} && !volume_end[32] &&
    (!partitioned || total_sectors<=partition_limit) && fat_bytes>=required_fat_bytes &&
    ((filesystem_parsed==FAT16 && rootdir_itemcount!=0 && parsed_clusters>=4085 && parsed_clusters<65519) ||
     (filesystem_parsed==FAT32 && rootdir_itemcount==0 && total16==0 &&
      fat32_flags==0 && fat32_version==0 && parsed_clusters>=65525 && parsed_clusters<32'h0fffffef &&
      root_cluster_w[27:0]>=2 && {4'd0,root_cluster_w[27:0]}<=parsed_clusters+1));
wire [31:0] next_cluster = filesystem==FAT16 ? {16'd0,target_cluster_fat16} : {4'd0,target_cluster[27:0]};
wire next_eoc = filesystem==FAT16 ? next_cluster>=32'hfff8 : next_cluster>=32'h0ffffff8;
wire next_valid = next_cluster>=2 && next_cluster<=cluster_limit &&
    (filesystem==FAT16 ? next_cluster<32'hfff0 : next_cluster<32'h0ffffff0);
wire [31:0] fat_sector = first_fat_sector_no + (curr_cluster >> (filesystem==FAT16 ? 8 : 7));
wire [31:0] cluster_sector = first_data_sector_no + ((curr_cluster-2) << cluster_shift);
wire [6:0] curr_cluster_fat_offset=curr_cluster[6:0];
wire [7:0] curr_cluster_fat_offset_fat16=curr_cluster[7:0];
wire stop_new = stop && !stop_q;
// Local FAT metadata lookup never fabricates a transport read_done. All fills
// use the single existing sector owner and require its real CRC-checked done.
wire cache_invalidate=stop || stop_req || track_start || start_req || file_error || read_error;
wire cache_hit,cache_lookup_valid;
wire [31:0] cache_lookup_data;
reg cache_lookup_pending,cache_lookup_done;
wire cache_lookup_request=FAT_SECTOR_CACHE!=0 && !cache_invalidate &&
    filesystem_state==READ_A_FILE && !inflight && !probe_pending && search_fat &&
    !cache_lookup_pending && !cache_lookup_done && card_stat==8 && cache_hit;
generate if(FAT_SECTOR_CACHE!=0)begin: g_fat_cache
    workstation_tf_fat_sector_cache_v1 cache(
        .clk_i(clk),.rst_ni(rstn),.invalidate_i(cache_invalidate),
        .fill_start_i(read_start && search_fat && !probe_pending && filesystem_state==READ_A_FILE),
        .fill_lba_i(read_sector_no),
        .fill_byte_valid_i(rvalid && search_fat && filesystem_state==READ_A_FILE && !probe_pending),
        .fill_byte_index_i(raddr),.fill_byte_i(rdata),.fill_done_i(read_done),
        .lookup_lba_i(read_sector_no),
        .lookup_word_i(filesystem==FAT16 ? curr_cluster[7:1] : curr_cluster[6:0]),
        .lookup_request_i(cache_lookup_request),.lookup_hit_o(cache_hit),
        .lookup_valid_o(cache_lookup_valid),.lookup_data_o(cache_lookup_data));
end else begin: g_no_fat_cache
    assign cache_hit=1'b0;
    assign cache_lookup_valid=1'b0;
    assign cache_lookup_data=32'd0;
end endgenerate
always @(posedge clk or negedge rstn)begin
    if(!rstn)begin cache_lookup_pending<=0;cache_lookup_done<=0;end
    else if(cache_invalidate)begin cache_lookup_pending<=0;cache_lookup_done<=0;end
    else begin
        cache_lookup_done<=cache_lookup_valid;
        if(cache_lookup_request)cache_lookup_pending<=1;
        if(cache_lookup_done)cache_lookup_pending<=0;
    end
end
assign scan_done=(filesystem_state==READY || filesystem_state==READ_A_FILE) && !ncopy_active && !file_error;
assign sector_busy=inflight || probe_pending || cache_lookup_pending;
// Same-edge synchronous handshake: no metadata read reserves file FIFO space.
assign data_sector_start = rstn && !file_error && filesystem_state==READ_A_FILE &&
    !inflight && !probe_pending && !search_fat && !track_applied && card_stat==8 &&
    sector_allow && !start_req && !track_start && !stop && !stop_req;

task fail(input [3:0] code);
    begin
        file_error<=1;file_error_code<=code;filesystem_state<=DONE;
        playing<=0;inflight<=0;probe_pending<=0;read_start<=0;
        search_fat<=0;start_req<=0;stop_req<=0;final_fat<=0;
    end
endtask

always @(posedge clk or negedge rstn) begin
    if(!rstn) begin
        read_start<=0;read_sector_no<=0;filesystem_state<=RESET;filesystem<=UNASSIGNED;
        search_fat<=0;cluster_size<=0;cluster_shift<=0;first_fat_sector_no<=0;
        first_data_sector_no<=0;cluster_limit<=0;curr_cluster<=0;cluster_sector_offset<=0;
        rootdir_sector<=0;rootdir_sectorcount<=0;rootdir_offset<=0;root_sectors_scanned<=0;
        file_size<=0;inflight<=0;playing<=0;eof<=0;load_track<=0;start_req<=0;req_idx<=0;
        probe_timer<=0;probe_pending<=0;probe_resume_sector<=0;stop_req<=0;stop_q<=0;
        cancelled<=0;track_applied<=0;file_error<=0;file_error_code<=0;watchdog<=0;
        partitioned<=0;partition_limit<=0;final_fat<=0;
    end else begin
        read_start<=0;eof<=0;load_track<=0;cancelled<=0;track_applied<=0;stop_q<=stop;
        if(track_start && !stop && !stop_req) begin start_req<=1;req_idx<=track_index;end
        if(stop_new) begin stop_req<=1;start_req<=0;end
        if((filesystem_state!=READY && filesystem_state!=READ_A_FILE) || probe_pending)
            probe_timer<=0;
        else if(probe_timer!=PROBE_INTERVAL_CYCLES) probe_timer<=probe_timer+1'b1;
        if(read_done || cache_lookup_done || !(inflight || (filesystem_state!=DONE && card_stat!=8))) watchdog<=0;
        else if(watchdog<WATCHDOG_CLOCKS) watchdog<=watchdog+1'b1;

        if(!file_error) begin
            if(read_error || card_stat==10) fail(ERR_TRANSPORT);
            else if(watchdog==WATCHDOG_CLOCKS && !read_done) fail(ERR_WATCHDOG);
            else if((stop_req || stop_new) &&
                    (filesystem_state==READY || filesystem_state==READ_A_FILE) &&
                    (!inflight || read_done)) begin
                inflight<=0;probe_pending<=0;playing<=0;start_req<=0;stop_req<=0;
                search_fat<=0;final_fat<=0;filesystem_state<=READY;cancelled<=1;
            end else if(read_done || cache_lookup_done) begin
                inflight<=0;
                if(probe_pending) begin probe_pending<=0;read_sector_no<=probe_resume_sector;end
                else case(filesystem_state)
                    SEARCH_MBR: begin
                        if(!is_boot_sector) fail(ERR_BOOT);
                        else if(is_dbr && valid_geometry) begin filesystem_state<=SEARCH_DBR;partitioned<=0;end
                        else if(dbr_sector_no!=0 && partition_sectors!=0 &&
                                ({1'b0,dbr_sector_no}+{1'b0,partition_sectors})<=33'h0ffffffff &&
                                (partition_type==4 || partition_type==6 || partition_type==14 ||
                                 partition_type==11 || partition_type==12)) begin
                            // MBR boot code may also begin with a JMP opcode.
                            read_sector_no<=dbr_sector_no;partition_limit<=partition_sectors;
                            partitioned<=1;filesystem_state<=SEARCH_DBR;
                        end else fail(is_dbr ? ERR_BPB : ERR_BOOT);
                    end
                    SEARCH_DBR: begin
                        if(!is_boot_sector || !is_dbr || !valid_geometry) fail(ERR_BPB);
                        else begin
                            filesystem<=filesystem_parsed;cluster_size<=sector_per_cluster;
                            cluster_shift<=log2cs(sector_per_cluster);
                            first_fat_sector_no<=read_sector_no+resv_sectors;
                            first_data_sector_no<=read_sector_no+data_offset[31:0];
                            cluster_limit<=parsed_clusters+1;cluster_sector_offset<=0;rootdir_offset<=0;
                            root_sectors_scanned<=0;
                            if(filesystem_parsed==FAT16) begin
                                rootdir_sectorcount<=root_round[15:0];
                                rootdir_sector<=read_sector_no+resv_sectors+fat_span[31:0];
                                read_sector_no<=read_sector_no+resv_sectors+fat_span[31:0];
                                filesystem_state<=LS_ROOT_FAT16;
                            end else begin
                                curr_cluster<={4'd0,root_cluster_w[27:0]};
                                read_sector_no<=read_sector_no+data_offset[31:0]+
                                    (({4'd0,root_cluster_w[27:0]}-2)<<log2cs(sector_per_cluster));
                                filesystem_state<=LS_ROOT_FAT32;
                            end
                        end
                    end
                    LS_ROOT_FAT16: begin
                        root_sectors_scanned<=root_sectors_scanned+1;
                        if(dir_end || rootdir_offset+1>=rootdir_sectorcount) filesystem_state<=READY;
                        else if(root_sectors_scanned+1>=MAX_ROOT_SECTORS) fail(ERR_ROOT_LIMIT);
                        else begin rootdir_offset<=rootdir_offset+1;read_sector_no<=rootdir_sector+rootdir_offset+1;end
                    end
                    LS_ROOT_FAT32: begin
                        if(!search_fat) begin
                            root_sectors_scanned<=root_sectors_scanned+1;
                            if(dir_end) filesystem_state<=READY;
                            else if(root_sectors_scanned+1>=MAX_ROOT_SECTORS) fail(ERR_ROOT_LIMIT);
                            else if(cluster_sector_offset+1<cluster_size) begin
                                cluster_sector_offset<=cluster_sector_offset+1;
                                read_sector_no<=cluster_sector+cluster_sector_offset+1;
                            end else begin search_fat<=1;cluster_sector_offset<=0;read_sector_no<=fat_sector;end
                        end else begin
                            search_fat<=0;cluster_sector_offset<=0;
                            if(next_eoc) filesystem_state<=READY;
                            else if(!next_valid) fail(ERR_CLUSTER);
                            else begin curr_cluster<=next_cluster;read_sector_no<=first_data_sector_no+((next_cluster-2)<<cluster_shift);end
                        end
                    end
                    READ_A_FILE: begin
                        if(start_req || track_start) begin playing<=0;search_fat<=0;final_fat<=0;filesystem_state<=READY;end
                        else if(search_fat) begin
                            search_fat<=0;cluster_sector_offset<=0;
                            if(final_fat) begin
                                final_fat<=0;
                                if(next_eoc) begin playing<=0;eof<=1;filesystem_state<=READY;end
                                else fail(next_valid ? ERR_CHAIN_LENGTH : ERR_CLUSTER);
                            end else if(next_eoc) fail(ERR_EARLY_EOC);
                            else if(!next_valid) fail(ERR_CLUSTER);
                            else begin curr_cluster<=next_cluster;read_sector_no<=first_data_sector_no+((next_cluster-2)<<cluster_shift);end
                        end else if(fptr>=file_size) begin
                            // Require EOC at the exact logical last cluster. A cyclic,
                            // overlong or stale chain must never masquerade as EOF.
                            search_fat<=1;final_fat<=1;read_sector_no<=fat_sector;
                        end else if(cluster_sector_offset+1<cluster_size) begin
                            cluster_sector_offset<=cluster_sector_offset+1;
                            read_sector_no<=cluster_sector+cluster_sector_offset+1;
                        end else begin search_fat<=1;cluster_sector_offset<=0;read_sector_no<=fat_sector;end
                    end
                    default:begin end
                endcase
            end else case(filesystem_state)
                RESET:filesystem_state<=SEARCH_MBR;
                SEARCH_MBR,SEARCH_DBR,LS_ROOT_FAT16,LS_ROOT_FAT32:
                    if(!inflight && card_stat==8) begin read_start<=1;inflight<=1;end
                READY:if(start_req && !track_start && !probe_pending && !stop && !stop_req && !ncopy_active) begin
                    start_req<=0;
                    if({1'b0,req_idx}>=track_count) fail(ERR_TRACK);
                    else if(size_ram[req_idx]==0) begin
                        if(cluster_ram[req_idx]!=0) fail(ERR_CLUSTER);
                        else begin track_applied<=1;eof<=1;playing<=0;end
                    end
                    else if(cluster_ram[req_idx]<2 || cluster_ram[req_idx]>cluster_limit ||
                            (filesystem==FAT16 ? cluster_ram[req_idx]>=32'hfff0 : cluster_ram[req_idx]>=32'h0ffffff0) ||
                            {32'd0,size_ram[req_idx]}>(({32'd0,cluster_limit}-64'd1) << (5'd9+{2'd0,cluster_shift}))) fail(ERR_CLUSTER);
                    else begin
                        curr_cluster<=cluster_ram[req_idx];file_size<=size_ram[req_idx];cluster_sector_offset<=0;
                        read_sector_no<=first_data_sector_no+((cluster_ram[req_idx]-2)<<cluster_shift);
                        load_track<=1;track_applied<=1;playing<=1;final_fat<=0;filesystem_state<=READ_A_FILE;
                    end
                end else if(!inflight && !probe_pending && !track_start && !stop && !stop_req &&
                            probe_timer==PROBE_INTERVAL_CYCLES && card_stat==8) begin
                    probe_resume_sector<=read_sector_no;read_sector_no<=0;read_start<=1;inflight<=1;probe_pending<=1;
                end
                READ_A_FILE:if(!inflight && (start_req || track_start) && !stop && !stop_req) begin
                    playing<=0;search_fat<=0;final_fat<=0;filesystem_state<=READY;
                end else if(!inflight && !cache_lookup_pending && !stop && !stop_req && !probe_pending && card_stat==8 &&
                            (search_fat || data_sector_start)) begin
                    if(!cache_lookup_request)begin read_start<=1;inflight<=1;end
                end
                else if(!inflight && !search_fat && !sector_allow && !stop && !stop_req &&
                        !probe_pending && probe_timer==PROBE_INTERVAL_CYCLES && card_stat==8) begin
                    probe_resume_sector<=read_sector_no;read_sector_no<=0;read_start<=1;inflight<=1;probe_pending<=1;
                end
                default:begin end
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
        if (cache_lookup_valid && !cache_invalidate) begin
            target_cluster <= cache_lookup_data;
            target_cluster_fat16 <= curr_cluster[0] ? cache_lookup_data[31:16] : cache_lookup_data[15:0];
        end else if (search_fat && rvalid) begin
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
reg outen_q;
assign outen=outen_q && rstn && !file_error && !stop && !stop_req;
always @(posedge clk or negedge rstn) begin
    if (!rstn) begin
        fptr <= 0;
        {outen_q, outbyte} <= 0;
    end else begin
        if (load_track) begin
            fptr <= 0;
            {outen_q, outbyte} <= 0;
        end else if (rvalid && filesystem_state == READ_A_FILE &&
                     !probe_pending && !file_error && !stop && !stop_req && ~search_fat && fptr < file_size) begin
            fptr <= fptr + 1;
            {outen_q, outbyte} <= {1'b1, rdata};
        end else begin
            {outen_q, outbyte} <= 0;
        end
    end
end

endmodule

`default_nettype wire
