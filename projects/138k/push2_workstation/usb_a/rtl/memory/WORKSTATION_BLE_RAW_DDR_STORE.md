# BLE raw short-recording DDR store

This is an unselected storage component. The existing BLE business endpoint
continues to own recording IDs, object states, operation tasks, CRC, replay,
transfer references, codec and wire formats. The store neither manufactures a
second business object nor supplies PCM to the audio schedule.

`BASE_APP` is a native 32-bit-word DDR address, aligned to eight words. The
integrator must bind a separately recorded 64 KiB suballocation in the recording
pool authority, disjoint from the existing CPU R00 store. Capacity is at most
16,384 stereo PCM32 frames. No absolute allocation is introduced here.

All control, capture and cache ports use `clk_i` (50 MHz in the workstation).
DDR slot/native/read ports use `memory_clk_i`. `rst_ni` must assert jointly with
the owner8 mux and native ledger; local release is synchronized in both domains.
Independent one-sided reset is unsupported. A common reset may rearm only when
the surrounding controller/ledger has also fenced any old physical response.

Start/clear/close/fetch use valid/ready. A request held high is accepted once and
must go low before another acceptance. Clear has priority over other control
requests and immediately fences capture/cache on acceptance. There is one
immutable command descriptor crossing with a request/ACK toggle. A clear may be
queued behind an in-flight descriptor; its separate cancel toggle stops further
fetch reads, but never cancels a published native command or forgets a read.

Start is accepted only from the raw empty, drained state. Accepted capture
indices are zero-based, consecutive and below capacity. `capture_ready_o` is
storage credit, not a request to stop audio: a capture event without credit,
with the wrong index or beyond capacity marks a sticky object fault, closes
admission, and drains the already accepted prefix. An explicit close excludes
capture on the same edge and drains the final partial burst. The FIFO payload
is exactly65 bits: `{kind,index[31:0],pcm[31:0]}`; kind0 is a frame and kind1 is an
ordered close marker whose index is the final accepted-frame count. Descriptor
start/clear/fetch are separate and do not require more FIFO kinds.

Capture can begin immediately after start acceptance without waiting for
`start_done_o`. START proves that the previous epoch's immutable FIFO event
target was consumed and native operations retired. New epoch FIFO data may
already be visible when the memory side receives START, including when its
clock was paused after the control-side start handshake.

FIFO write/read event counters use the same modulo pointer width as the bounded
FIFO. Clear carries an immutable final write-event target, so an apparently
empty FIFO whose pointer has not crossed yet cannot produce a false drain.
No per-object FIFO reset is used. A completed clear has consumed every earlier
frame/marker and retired all already published native operations before a new
start is admitted. This also fences old close markers.

The internal native bridge distinguishes local slot acceptance from actual
native acceptance. Published command fields remain stable until native accept.
Writes pack eight PCM32 frames in increasing byte order; mask bit1 preserves a
byte, including every unused byte of the final partial burst. Committed counts
advance only on native acceptance. There is at most one read outstanding and
the read response may arrive with, or after, its native acceptance. A same-edge
response uses the still-published command identity; a response with no accepted
read owner is a protocol fault.

`accepted_frames_o` is local to the control clock. Committed count, drained and
memory fault status return in immutable snapshots, not independent bit
synchronizers. `drained_o` requires the ordered close/clear target, FIFO, pack,
published command, outstanding read and response mailbox all to be retired.

Object faults can be cleared after real drain. Native protocol/transport fault,
command timeout and read timeout quarantine the channel until common reset.
Published commands and read ownership survive timeout and clear requests;
late completion is consumed/discarded without rearming the channel. No new
generation is admitted while native ownership remains unknown. Generation is
32-bit, increments for accepted start/clear and never wraps; exhaustion
quarantines the channel. The final accepted start/clear completes once even if
its valid remains high; only a distinct later request triggers exhaustion.

Fetch is admitted only for a closed/drained successful prefix. Offset/length
are bytes; length is1..8112 and the non-wrapping range must fit committed data.
DMA covers complete first/last32-byte beats, at most8160 bytes. One immutable
256-bit response mailbox is acknowledged only after the control side has
written its eight words to cache (or discarded a fenced response).

The cache is8 KiB, implemented as four16-bit native SDP blocks: two depth banks
and two parallel halfwords. `sample_addr_i` is the existing absolute frame
address. `sample_word_o` returns the selected PCM32 word after one control clock;
invalid cache/out-of-window addresses return zero. Only complete fetch success
publishes `cache_valid_o`; new fetch, clear, fault or generation change withdraws
it. A canceled/old response cannot publish or overwrite a valid new cache.

Offline tests are component evidence. Production selection, complete CDC/reset
and RAM data timing, net BSRAM/CLS benefit, P&R, BLE end-to-end acceptance and
hardware remain separate work.

Run `python3 sim/test_ble_raw_ddr_store.py --output <new-directory>` from
`usb_a/` (or use the full path). It exercises both FIFO implementations and two
memory clock ratios, rejects five behavior mutations, and checks the exact
reviewed Verilator warning inventory. The shared FIFO's RAM style attribute
and unused large-branch `full` wire account for two warnings. The reset-release
vectors each account for one synchronous/asynchronous-use warning: bit0 shifts
synchronously and bit1 drives the local reset. These reviews do not establish
physical CDC/reset timing or implementation RAM mappings.
