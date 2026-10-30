# TF direct ingress v1 source component — 2026-10-31

This unselected M03 foundation is based on source `4308339`. It implements
file-byte events -> 4096-byte same-clock FIFO/held byte -> maintained strict
real WAV kernel -> one-frame EOS lookbehind -> same-clock 4096-frame PCM FIFO
with 3072-frame prefill. It has no SD controller, file reader, DDR port, CDC,
source selector or clock generator. All current profiles, selected transport,
accepted/pinned inputs and immutable fixed18ed stage remain unchanged.

The API and failure contracts are maintained in
`rtl/tf_audio/WORKSTATION_TF_DIRECT_INGRESS_V1_CONTRACT.md`. File-owner coordination
uses the separately developed `workstation_tf_file_reader` ABI, documented in
its `storage/WORKSTATION_TF_FILE_READER_CONTRACT.md`; that owner is a distinct
parallel source delivery and is not instantiated or copied here. Its actual
track-applied/drained event starts this component, and its only SD owner supplies
admitted data-sector starts, file bytes, independent EOF and explicit errors.
A future composition must bring both deliveries together and validate their
actual SPI/FAT chain before selecting a new explicit profile.

Every data-sector launch reserves 512 bytes plus two pipeline positions. First
bytes follow the reservation edge; metadata is not PCM input. A real EOF after
the final file byte/FAT checks retires the unused final short-sector reservation.
The byte FIFO includes its held read byte within its 4096 budget. The PCM FIFO
includes its held head within its 4096 budget and stores only 33-bit
`{last,right,left}` items, with generation/rate held once per session. Pausing
preserves the exact next frame. Backpressure propagates to sector admission;
source violations and overflow fail closed. The explicit deadline event belongs
to the same file clock domain; it never blocks a sample clock. New start locks
only a snapshot of already committed output state and fails if file error is
already asserted. Cancel wins simultaneous start/error and invalidates locally.

The old `tf_wav_chunk_parser.v`, `tf_wav_pcm_decoder.v` and
`tf_audio_decoder_ip.v` remain byte-identical. Two versioned strict derivatives
retain their real PCM conversion/held-ready logic, with exact base/original/
derived hashes and reversible patches in the provenance manifest. This interface
checks complete RIFF/chunks/pads/frames and full PCM extensible GUID; zero-size
data means empty. Independent drained file EOF determines EOS; original
`eof_seen` is not used. Final PCM is marked after tail metadata, and local last
transfer prevents later sample requests becoming false underruns. Local drain
is not final I2S/physical completion.

Offline validation:

- 42 real-data cases cover 48 kHz/44.1 kHz x mono/stereo x 8/16/24/32-bit,
  fmt16/18/40, unknown and zero chunks, odd pads/data, tail metadata, empty data,
  one-frame/short/multiple-data files, empty/short/truncated/partial input,
  invalid codec/width/channel/GUID/RIFF size/rate and rate mismatch.
- Independent Python PCM oracle verifies every accepted pair and exact last.
  Full-cache tests cover held byte/PCM stability, high-water backpressure,
  initial prefill, pause retention, cancellation after actual playback and
  explicit restart through generation wrap. True cache exhaustion latches one
  failure; late bytes/EOF do not auto-recover. A new explicit session resumes
  the complete fresh oracle. Upstream errors, simultaneous start/error and
  cancel/start/error have separate cases.
- Eleven temporary behavioral mutants must fail their intended assertions,
  including sector reserve removal, bypassed held decoder byte, missing last,
  pause consumption, absent underrun latch, blocked short-file release,
  false post-tail underrun, overflow fence removal, start-error omission and
  rate mismatch admission and overflowing declared-chunk bounds. Overflow containment also uses explicit corrupted
  reservation-ledger injection; honest sector admission never overflows.
- Three unchanged legacy WAV regressions pass, exact derived-patch reconstruction
  passes, new source lint has zero warnings, and accepted source-boundary tests
  pass 17/17. Independent review reproduced the old overflowing-chunk false
  success and verified seven focused container/pad boundary cases against the
  fixed parser; its separate sealed receipt is bound by this source delivery.
  Final receipt binds fixture/source/vector/log hashes.

The source RAM hints request block RAM, with declared arrays totaling 20.5 KiB
before the separate FAT cache, small registers and future shallow tagged bridge.
No mapped RAM count, cost reduction, healthy-card 50 ms deficit budget, real-card
throughput or physical deadline claim is made. MP3/FLAC and SRC are not enabled.
Existing WAV mono/stereo 8/16/24/32-bit support remains available in both rates;
actual file rate must equal the session's committed-rate snapshot.

Run the reusable regression with a new external output directory:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_direct_ingress.py \
  --output <new-evidence-directory>
```

No prepare, synthesis, P&R, board, SRAM/Flash or push occurred in this isolated
source phase. M03 remains unfinished until explicit source selection, actual
single file-owner composition, zero TF-origin/owner4 DDR traces with a live
legacy nonzero control, shallow bridge/physical last association, same-candidate
resource/timing/CDC and hardware checks complete. Effects/real-time processing
and D random-access storage remain separate work. Rollback simply leaves this
unselected component unused; current source/deployment choices are unchanged.
