# Maintained TF file owner, first unselected stage

`workstation_tf_file_reader.sv` is an opt-in maintained GPL-3.0-only derivative of the unchanged `tang_mp3/sd/tf_sd_file_reader.v`. It instantiates exactly one unchanged `workstation_tf_sd_sector_reader` and its maintained SPI session. No build profile selects this owner. The provenance JSON describes every exact reversible edit; reconstruction is a verifier, never a production source generator. Original license, notices, vendor files, baselines and selected profiles remain unchanged.

This stage owns card/volume discovery, one playlist, track selection and file-byte transport. It has no DDR client, FAT cache, WAV decoder or PCM buffer. These component facts do not prove a no-DDR workstation profile, streaming throughput, M03 completion, routed timing or hardware acceptance. Actual sector CRC bytes are drained and **not validated**, preserving the known transport limitation.

## Ports and synchronous events

All non-SPI signals use `clk` (intended 50 MHz). `rstn` asynchronously cancels the whole owner, resets the actual SPI transport and invalidates playlist/session state. Card reinitialization and directory scan run after reset release; playback requires a new explicit `track_start`. There is one card owner and at most one outstanding CMD17.

| Signal | Contract |
|---|---|
| `scan_done`, `track_count[4:0]` | Valid playlist, 0..16 entries. Names are space-padded `NNNNNNNN.EEE`, 12 bytes/track, synchronous one-cycle read. Unpopulated names are not valid; addresses 192..255 return zero. |
| `track_index[3:0]`, `track_start` | Pulse requests that track/restarts it. While busy the latest request is retained; an active sector finishes before the new track applies. The old track's bytes remain old-session bytes until `track_applied`. No new data-sector launch occurs while a request is pending. |
| `track_applied` | One-cycle pulse when a valid selection applies. Clears the old file position. It occurs only after prior SPI payload and CRC have drained, and no old byte may appear after it. A downstream session owner uses this event to latch its own generation/rate and clear its byte path. |
| `sector_allow`, `data_sector_start` | Same-edge handshake before a **file data** sector launch. `data_sector_start` is combinational fire, gated by current allowance, state, outstanding transport and stop/request conditions. The first reservation is at least one clock edge after `track_applied`; application and reservation never coincide. Reserve a full **512 bytes** on that edge, even for a short final sector. Allowance may fall afterwards; the accepted sector still completes. No additional sector can launch without another handshake. Metadata never reserves file space. |
| `outen`, `outbyte[7:0]` | At most one byte/clock; only accepted file data, bounded by directory file size. Internal output registration is one stage; `outen` is additionally fenced immediately by `rstn`, stop and sticky error. No boot, FAT, directory, probe, CRC or beyond-file padding bytes appear here. The consumer must retain the full reservation; there is no per-byte ready. |
| `eof` | One-cycle **natural success only**, after all advertised file bytes and the final FAT EOC check. It is later than the last `outen`, never combined with a last byte. For a valid empty file, `track_applied` and `eof` occur together with zero data requests. Cancel/error never emit EOF. |
| `stop` | Level cancellation/hold, with priority over simultaneous start. From assertion onward no further output byte is valid. An already launched sector drains payload and CRC; new data/probe reads are blocked. Mount metadata can finish so stop cannot corrupt discovery. |
| `cancelled` | One-cycle acknowledgement after cancellation reaches a drained READY boundary. Held stop does not repeat the pulse. Requests during stop are discarded; release does not restart playback. A later explicit start may reuse the playlist. Whole-owner cancellation/recovery uses `rstn`. |
| `sector_busy` | Actual outstanding sector/probe; not PCM activity or consumer readiness. |
| `file_error`, `file_error_code[3:0]` | Sticky terminal failure, never EOF. Stops playback, fences output and resets/holds the underlying transport so it cannot replay or leak late bytes. Recovery requires whole-owner `rstn`, reinitialization/scan, then explicit selection. No automatic retry/replay. |

On a live track switch, downstream must keep the previous generation until `track_applied`; it must not clear early merely because it sent `track_start`. For immediate cancellation it asserts stop and cancels its own queued session at the same application edge. Error invalidates the downstream session and buffered data. Byte buffering and PCM scheduling remain separate owners; none of these operations may stop the audio sample clock.

## Supported volume and chain boundary

The bounded parser supports a superfloppy DBR at LBA0 or the **first primary MBR entry only**, types 04/06/0E (FAT16) or 0B/0C (FAT32), nonzero LBA/length with checked 32-bit geometry. An invalid LBA0/partition/DBR fails; it never searches successive sectors for a coincidental signature. BPB volume length must fit its MBR partition.

Sector size is 512. Sectors/cluster is a power of two in 1..128; reserved sectors and FAT size are nonzero; one or two FATs are supported, reading the first. FAT16 uses 4085..65518 data clusters and a nonempty fixed root. FAT32 uses at least 65525 clusters with usable indices below reserved `0x0ffffff0`; FAT32 root-entry count and BPB total16 are zero, version/extended flags are zero (mirrored FAT, no alternate active-FAT selection). Data geometry and FAT entry capacity must cover the declared volume. These checks deliberately reject FAT12, GPT, extended/logical partitions, non-512 sectors and unsupported BPBs.

FAT16 fixed-root sectors use `ceil(root_entries/16)` and a distinct 16-bit sector cursor. Entries beyond a partial last sector's declared count are ignored. FAT32 follows the actual root chain. `MAX_ROOT_SECTORS` (default 4096) bounds both scans and catches unterminated/cyclic root chains; reaching the declared FAT16 end or any valid FAT32 EOC completes an otherwise valid scan. The parser retains ordinary archive-file (`0x20`) 8.3 entries matching the uppercase extension, skipping directories/LFN/deleted entries, and keeps up to 16 names/selections.

FAT16 indices mask the directory high word; FAT32 indices/entries mask the reserved high four bits. EOC is the **whole** interval `fff8..ffff` / `0ffffff8..0fffffff`. Free/reserved/bad/out-of-volume indices fail. Nonempty selections need a valid first cluster and file size within the volume's cluster capacity. Valid zero-byte files require cluster zero and have no data read; invalid selections do not become EOF.

File chains in this first stage must contain **exactly `ceil(file_size / cluster_bytes)` clusters and terminate in EOC there**. A fragmented next cluster is always read from FAT; adjacency is never assumed. Early EOC fails. At the logical last cluster an additional metadata FAT read must establish EOC before success; an overallocated/cyclic chain fails instead of producing false EOF. A corrupt chain may have delivered a prefix before detection; the owner reports failure and the consumer invalidates that session. The fixed file size bounds this walk without a visited-array or a general filesystem implementation. FAT changes between reads are not made atomic, and CRC validation is still absent.

## Failure and watchdog codes

| Code | Meaning |
|---:|---|
| 1 | Native transport `read_error` or FAULT, including missing token/R1/command failure. |
| 2 | Bounded initialization/outstanding-transaction watchdog. |
| 3 | Invalid LBA0/MBR/first partition. |
| 4 | Invalid or unsupported DBR/BPB/geometry. |
| 5 | Invalid first/next cluster, size beyond volume, free/reserved/bad/out-of-volume chain. |
| 6 | EOC before the declared file length. |
| 7 | Root scan budget exhausted. |
| 8 | Unpopulated/out-of-range track selection, including an empty playlist. |
| 9 | Last logical cluster still points to another valid cluster (overlong/cyclic chain). |

There is no physical card-detect input. The idle probe establishes transport responsiveness, not card identity/CID; an unobserved fast card swap is not identified, and changing media requires explicit reset. A removal after a payload token may deliver unvalidated filler until the next failed command because CRC checking remains absent. The unchanged idle/prolonged-pause probe reads LBA0 without exposing metadata as file bytes. Removal on an active/probe read yields transport failure. A missing card or initialization that never reaches IDLE is bounded by `WATCHDOG_CLOCKS` (default 250000000 clocks = 5 s at 50 MHz). Paused READY/valid data allowance waits do not consume that watchdog; they may be held indefinitely. These are failure deadlines, not continuous-audio buffering or card-throughput guarantees.

## Reproduction and next integration

Run `sim/tf_audio/run_workstation_tf_file_reader_wire.py --output <new-directory>`. It checks exact forward/reverse GPL derivation and locked sector/session/original identities, then uses real SPI commands/edges, sparse FAT16/FAT32 superfloppy/MBR images, fragmented clusters, names and file-byte oracles. It exercises sector reservation, metadata isolation, final partial sectors, switching, stop/late payload, reset/reinitialization, malformed volumes/chains, transport failure, initialization timeout and meaningful source faults. No DUT register force/deposit or session stub is used. The existing native sector wire regression remains an independent source/transport guard.

The next direct-ingress owner consumes the public events above and adds bounded byte storage, actual WAV parsing, PCM prefill and session cancellation. It must not instantiate a second SD driver. Profile selection, FAT caching, cumulative card-deficit measurement, no-DDR integration, ordered output EOS, actual CDC/reset/RAM mapping, synthesis/P&R and hardware qualification remain separate gates.
