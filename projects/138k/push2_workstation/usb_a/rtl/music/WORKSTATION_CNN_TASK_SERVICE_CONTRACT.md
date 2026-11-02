# Task3 W CNN task component

The explicit task3 W media candidate profiles select this component; accepted
single-board and task2 W21 profiles retain their own source policies. It owns a
bounded offline analysis clip and the maintained real Basic Pitch pipeline;
it does not supply the basic performance sample clock or access M's TF card.
LCD framing, electrical validation and transport capability negotiation are
outside this internal ready/valid boundary.

## Ownership and limits

`workstation_cnn_task_service` accepts one descriptor at a time. `start_ready_o`
requires W media BIST/backend readiness, the actual model loader's DONE/CRC
state, and the drain/restart link's readiness. Only format 1, stereo S16LE at
48 kHz, is currently accepted. A nonzero task ID and strictly increasing,
nonzero generation fence reuse within a common reset. Generation wrap needs
a fresh boot/session; the transport envelope must bind these fields to the
negotiated boot/session rather than interpreting them as globally unique.

The first capacity is 96,000 frames, or 2 seconds. The DDR address authority
reserves `0x31100000..0x311fffff` for the W CNN PCM pool, of which only
`0x31100000..0x3115dbff` is accessible clip data. It is distinct from both
the model/feature allocations and the single CPU/BLE recording object.
It is not yet a whole-song streaming analysis implementation.

Ingress has one 8-frame packing register and one in-flight BL8 command.
The two depth-4 asynchronous FIFOs carry a 318-bit command and a 257-bit
completion; the owner still permits only one staging transaction in flight.
The final write masks bytes outside the actual clip. An accepted PCM frame
advances `accepted_frames_o`; only an actual owner5 native write acceptance
advances `committed_frames_o`. Queue admission is not a storage commit.

The service first checks the input CRC32, then rereads the committed clip
and checks the DDR readback CRC before issuing PCM to the real resampler,
CQT, six CNN layers and Viterbi. CRC uses the actual little-endian four
bytes per stereo frame and polynomial `0xedb88320`. `seal_valid_o` is a
one-clock pulse after readback verification, with identity and frame counts
held on the task outputs. A readback failure cannot issue analysis PCM.

This task explicitly enables `BOUNDED_EOF_PADDING` in the maintained link
and pipeline. Padding inserts the next zero only while the frontend is
drained. It therefore completes the final partial window without leaving
padding behind that could start another zero window. Genuine queued PCM
and resampler history still cross ordinary window restarts. This parameter
defaults to 0 in the existing link/pipeline, preserving their old behavior.
Task success waits for the actual final-window and Viterbi score completion.

`CNN_USE_DDR_SIGNAL` and `CNN_USE_DDR_CQT_COEFF` default to 1 and propagate
through the maintained link to its existing pipeline storage branches. The
explicit signal-BSRAM profile selects 0/1; the CQT-BSRAM profile selects 0/0.
Front coefficients remain in DDR, `USE_ALL_DDR` remains 0, and state, plane,
weights and features remain external. These controls change memory placement;
they do not select a different model, arithmetic, inference graph or clock.
Each local configuration needs independent equivalence, resource and timing
evidence. The unchanged default does not refresh old source locks; use the
original source commit and immutable candidate to reproduce an older profile.

`workstation_cnn_ddr_broker` serializes staging and the real CNN DDR16 port
onto native owner5 of `workstation_media_memory`. It holds the selected
command through local queue admission and acknowledges its producer only
on `native_accept[5]`. Reads hold their owner until the actual read return.
When both producers remain ready, the producer preference rotates after
each completed write/read. Owner6 Delay and owner8 recording remain in the
maintained media-memory composition, with their existing arbitration.
This component establishes no global memory service-time bound for them.

## Task results, cancellation and failures

Scores use ready/valid, with note, task ID, generation and zero-based ordinal
held until accepted. Consumers may stage a partial score, but may publish a
complete guidance object only after a matching success terminal. On cancel
they discard all staged results from that generation. The first inference
result is additionally latched in `first_result_*` for diagnostics; it is
not an independent authoritative parameter or complete-score object.

Matching cancellation fences PCM and score valid/ready combinationally.
The owner then waits for both the actual outstanding staging write/read
completion and the maintained CNN link's FIFO/native-read/write drain.
Only then can a terminal release the task. Late cancellations with an older
generation cannot cancel a new task. No cancellation flush pretends that
an admitted but uncommitted DDR write has completed.
M's PANIC, TF selection cancellation and link-session retirement map to
matching task cancellation at the transport adapter; M executes its local
PANIC without waiting for this component's drain acknowledgement.

Terminal codes are 0 success, 1 cancelled, 2 ingress identity/index or
transport-declared clip loss, 4 input CRC mismatch, 5 DDR readback CRC
mismatch, 6 total task timeout, and 15 native/backend/restart fault. Code 3
is reserved for length failure; invalid descriptor length/format/identity
is currently rejected before allocation with `rejection_code_o=3`.
Terminal ID, generation, counts and code remain stable until acknowledged.

The default native/drain timeout is 50,000,000 memory/source clocks,
respectively; total task budget is 3,600,000,000 source clocks. The test uses
smaller explicit budgets. These are finite fault detection limits, not a
promised inference time. LCD clip loss/overflow asserts `ingress_fault_i`
to fail and drain that task; ordinary LCD disconnection does not assert
the native media bus's `transport_fault_i`. A source cannot hold a clip indefinitely without
reaching the total timeout.

Unowned/late native events, native timeout, transport fault, memory reset or
calibration loss after initial readiness quarantine this owner. The terminal
can report code 15 before a safe drain because memory state is no longer
trusted; it cannot open another task. Recovery requires coherent common
reset of the service, both FIFO domains, media clients/controller and all
old native transactions, followed by BIST and actual model revalidation.
Merely restoring ready, a local CPU reset or acknowledging a terminal does
not recover a quarantined owner. The native response bus carries no epoch;
arbitrary pre-reset returns overlapping new reads cannot be recognized by
this interface.

## Evidence boundary

The task runners boot the complete unchanged 52,239-word model via actual
read-only SPI, validate payload and DDR readback CRC `AF01A61B`, and use
the actual CQT/CNN/Viterbi with behavioral native DDR and real media queues.
The historical lifecycle probe uses a checked simulation copy with dimensions
2048/2. The selected W runner instead consumes immutable prepared RTL without
an overlay: WIN44100, FRAMES8, nine octaves, hop22050/4, tile16 and coarse
guidance. The native link's unselected dimension defaults remain43844/172.
The [selected-W report](../../reports/DUAL138K_TASK3_W_SELECTED_CNN_20261102.json)
records the complete 96,000-frame task, real six-layer results and cancellation
replay. Its 4Hz feature cadence does not imply real-time inference throughput.
Local-memory configurations require their own cross-configuration results;
the historical DDR result cannot validate them.

These are lifecycle and memory integration checks. Musical accuracy,
whole-song completion, physical timing, actual LCD throughput, board latency,
SRAM deployment and Flash acceptance remain separate. The current W firmware
has a diagnostic task entry, with no automatic TF/LCD producer; LCD-ready is
fixed down. No model/vendor or frozen baseline bytes are edited.
