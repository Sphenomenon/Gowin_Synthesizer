# Unselected direct TF ingress v1

`workstation_tf_direct_ingress_v1.sv` is an independent M03 source component.
No profile, top, accepted/pinned source policy or fixed18ed stage selects it.
It contains no SD controller, file reader, DDR client, CDC or sample-clock owner.
The current selected TF service still uses its existing DDR path. This component
has offline validation only; it does not establish M03 completion, a card service
budget, resource mapping, routed timing or hardware EOF success.

## Same-domain interface

All inputs, including `sample_request_i`, belong to the caller's same 50 MHz
file/decoder domain. `sample_request_i` is a qualified consumer deadline event:
the consumer needs the held head at that edge, and ordinarily asserts
`pcm_ready_i` at the same edge. It is not an asynchronous audio-domain tick.
Cross-domain deadlines and the shallow tagged PCM bridge need a separate CDC
contract and review. The module never generates, gates or waits a sample clock.

| Input/output | Contract |
|---|---|
| `start_i` | Actual file-owner `track_applied`, after all old transport bytes have drained. Lock external `generation_i` and `expected_rate_i` once and clear local storage/status. These are session snapshots of the existing authoritative committed state, not a new rate authority. Caller cancels if that committed context changes. |
| `cancel_i` | Immediately blocks admission/output, wins a simultaneous start, clears local queues and parser. Caller also stops the single file owner and waits its real cancelled/drained result before a new start. Late bytes while inactive are dropped. Explicit later start is the only failure recovery. |
| `data_sector_start_i` / `sector_allow_o` | Same-edge data-sector admission handshake. Sector start is at least one edge after track-applied/start; its first byte is at least one further edge later. Each sector has at most 512 file-byte events, at most one per clock. Launch reserves all 512 plus two pipeline-margin positions. Allow need not stay high during the sector. Metadata uses the file owner's separate path and never appears as file-byte events. |
| `file_byte_valid_i`, `file_byte_i` | Unbackpressured byte event from the already admitted sector. No new data sector overlaps an unretired reservation. |
| `file_eof_i` | Separate real file completion event, after its final byte and final FAT/EOC checks. It retires the unused reservation of a final partial sector; no padding bytes are invented. A zero-byte file may assert EOF with start, but is malformed WAV. |
| `file_error_i`, code | Sticky owner failure; simultaneous start fails before admission and code is preserved in `file_failure_code_o`. Does not become a fake EOF. |
| `pause_i` | Gates output transfer and deadline-failure checks without consuming the queued head or changing session identity. Decoder may fill bounded storage; the byte/sector side then backpressures. Resume uses the exact next frame and does not repeat prefill. |
| `pcm_valid_o/ready_i`, L/R, last | Held signed stereo PCM16 pair. Data/last remain stable while valid and not ready, except explicit pause/cancel/failure revocation. `last` belongs only to the final complete PCM pair of a validated file. |
| `prefill_ready_o` | Sticky local threshold qualification, independently of format-ready. Default 3072 queued frames, or a shorter nonempty file only after validated EOS and final frame insertion. |
| `decoded_eos_o` | Strict complete RIFF/chunk/frame/file EOF accepted and final PCM inserted, or valid empty data recognized. This is not decoder `eof_seen`, bridge drain or physical completion. |
| `local_tail_drained_o` | Last marked pair transferred to this same-domain consumer, or valid empty data. Later sample requests do not become false underruns. Downstream/physical completion is a separate protocol. |
| `empty_o` | Valid RIFF/WAVE with zero complete PCM frames. No fabricated last/PCM transfer; prefill/active remain false. |
| `active_o`, identity/format | Local prefilled live source eligibility. Identity is one held session snapshot; format is valid only in a live nonfailed session. No source selection or parameter write occurs here. |

The file ABI matches the independently maintained
`storage/WORKSTATION_TF_FILE_READER_CONTRACT.md`: one owner only, `track_applied`
before new data, `data_sector_start` with allow, metadata isolated, EOF independent
and stop draining before the next apply. A future composition must connect this
owner once, rather than instantiate another SD controller for this component.

## Bounded storage and failures

Default byte budget is 4096 bytes including the synchronous read-held byte.
`sector_allow_o` requires total used <= 4096-512-2 and no outstanding reservation.
The 512 reservation counts only file bytes; a full sector consumes it and real
EOF retires a short final sector. Errors/cancel revoke it. The file owner's
registered output pipeline is one cycle; margin two also covers the admission
edge. Byte overflow has an independent fail-closed check even if this ledger is
corrupted. Source events violating admission fail; they do not overwrite queued
old data and continue playing.

Default PCM FIFO budget is 4096 frames including its synchronous held head.
The RAM item is exactly 33 bits `{last,right16,left16}`. Generation/rate are
latched once for the whole session. One extra 32-bit lookbehind frame and the
kernel's held pair allow the actual last frame to be marked after tail metadata
and EOF; they are not hidden additional FIFO capacity. RAM arrays request
`ram_style=block`/`syn_ramstyle=block_ram`; these are source hints only. Declared
arrays total 20.5 KiB (4 KiB bytes + 16 KiB PCM + 0.5 KiB last bits), excluding
file-owner FAT cache, small registers and a future shallow CDC bridge. Only
actual synthesis/P&R may establish physical RAM count or net resource change.

| Local failure code | Meaning |
|---:|---|
| 1 | Upstream file failure; preserve its separate code |
| 2 | Missing/overlapping/unallowed sector reservation or byte after EOF |
| 3 | Actual byte storage overflow fence |
| 4 | Unsupported or malformed WAV, incomplete chunk/container/frame |
| 5 | Unsupported session rate or actual file rate differs from session snapshot |
| 6 | First true consumer deadline without a queued frame after prefill, outside pause and before local marked-tail transfer |

A failure latches once, invalidates output/admission and clears local queues.
Incoming events, card recovery, pause/resume and EOF cannot revive it. Cancel
retains the diagnostic; only explicit new start clears it. No output repeats an
old last frame or silently performs SRC. Only 48000 and 44100 Hz matching the
session snapshot are admitted. A downstream consumer that drains into its own
queue owns its later physical deadlines; this local deadline is not proof of
physical I2S continuity.

4096/3072 are initial source parameters, not a measured healthy-card deficit
bound. No 50 ms real-card guarantee or permanent-throughput claim is made. A
future selected source needs measured cumulative supply deficit/recovery,
startup/latency/resource budgets, clock/CDC/PLL/timing gates and board checks.

## Versioned strict WAV kernel and evidence

`storage/workstation_tf_wav_{chunk_parser,pcm_decoder}_v1.sv` are maintained
strict derivatives of the real existing kernels, with exact originals, hashes,
base commit and reversible unified patches in
`workstation_tf_direct_ingress.provenance.json` and `provenance/`.
The old parser, decoder and `tf_audio_decoder_ip.v` stay byte-identical and
remain selected by all current profiles. No MP3/FLAC implementation is enabled.

The conversion is the original signed PCM16 oracle: mono duplication, unsigned
8-bit offset, signed 16-bit, top 16 bits of 24/32-bit; PCM and PCM extensible
formats retain support. The strict version checks the full PCM GUID, RIFF size,
complete chunk/odd pads with widened declared-size/container bounds, valid fmt widths and full PCM frames. Zero-size `data`
is empty in v1; the legacy kernel's zero-size streaming convention remains in
its old interface. Unknown/zero chunks and tail metadata are not PCM. Multiple
complete data chunks in one RIFF remain supported. Separate drained file EOF
checks complete state and byte count; partial/short/truncated input fails.

`sim/tf_audio/run_workstation_tf_direct_ingress.py --output <new-directory>`
runs the actual maintained kernel with an independent Python byte/PCM oracle,
the unmodified legacy WAV regressions, source lint and behavioral mutants.
Coverage includes 48/44.1 kHz x mono/stereo x 8/16/24/32-bit, fmt16/18/40,
unknown odd chunks, odd data pad, tail metadata, empty/short/truncated files,
bounded held-ready backpressure, prefill, pause head retention, cancel/restart
through generation wrap, source errors, true exhausted-cache failure and recovery.
The overflow fence additionally has explicit reservation-ledger corruption
injection; honest admission stays within capacity. No test claims a whole
SD/SPI/FAT-to-I2S natural EOF hardware success or selected zero-DDR owner4 trace.
