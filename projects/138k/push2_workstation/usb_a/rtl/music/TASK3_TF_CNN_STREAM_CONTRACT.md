# Task3 TF to W CNN logical stream

This is an unselected logical framework. It does not define LCD pins, cable
mapping, I/O directions, voltage, clock, serializer, measured throughput or
hardware acceptance. Existing M/W prepared candidates and their locks do not
select this framework. Model, DSP math and clock constraints are unchanged.

`workstation_task3_tf_analysis_source` owns the M analysis-pass lifecycle and a
256-frame queue. Connect its PCM input to a **dedicated offline TF decode pass**
on M's existing single file owner. The file cursor and decoder may pause while W
commits and computes each clip; they must resume at the next unconsumed PCM
frame. Playback and analysis select the single owner explicitly. Never AND
analysis credit into the basic DAC sample schedule. The stream currently
accepts 48 kHz stereo PCM16 only. The optional nonblocking observation mode is
one finite clip: congestion or a non-final clip ends with an explicit failure;
it cannot represent a continuous whole-file analysis while samples pass unseen.

A start fixes nonzero M boot, session, initial task and generation, and a clip
budget of 1..96,000 frames. The source sends a descriptor, indexed frames and a
CRC32 trailer. On the budget boundary it stops consuming the TF decoder, waits
for the validated W terminal, increments task/generation, and continues. Only
the real PCM LAST marks file completion. Empty/missing EOF or a blocked peer
reaches a finite watchdog failure; it is not fabricated as a successful file.
Identity counter wrap fails and requires a new session. No complete PCM clip is
buffered on M.

All ports use ordinary ready/valid handshakes. Payload fields are high to low:

| Logical transaction | Bits | Fields |
| --- | ---: | --- |
| Identity | 128 | boot32, session32, task32, generation32 |
| Descriptor | 200 | identity128, frame budget32, reserved CRC32=0, format8=1 |
| PCM | 192 | identity128, clip-local index32, `{right16,left16}` |
| Seal | 192 | identity128, actual frames32, CRC32 |
| Cancel | 128 | identity128 |
| Score | 167 | identity128, clip-local index32, note7 |
| Terminal | 164 | identity128, score count32, code4 |

CRC is IEEE reflected CRC32, initial all ones, final inversion, bytes from low
to high within each PCM word. Descriptor/frame/seal must preserve order in one
bounded transport lane. Score/terminal must preserve order in another. Cancel
and link fencing have a separate bounded control path. These are internal
transactions, not a new USB PL, BLE or physical LCD wire contract.

`workstation_task3_cnn_stream_w` validates peer boot/session and maps wire
generation to a W-local monotonic service generation. It holds current frames
while the real CNN task starts. It accepts a seal only after its indicated
frames have actually reached the task input. It instantiates the maintained
`workstation_cnn_task_service` with `DEFERRED_SEAL_ENABLE=1`. The parameter's
default is zero and retains the existing descriptor-CRC behavior. In deferred
mode a seal must match identity, exact accepted frame count and the accumulated
input CRC. Every payload write still requires actual native commitment; the
complete committed clip is read back and CRC checked before any CNN PCM is
replayed. The real model loader/CQT/CNN/Viterbi and restart drain are retained.
This work adds no second recording object or DDR allocation.

M's `workstation_task3_score_commit_m` checks each complete ordered clip and
accumulates notes across clips in a bounded 2,048-note song image. It publishes
no note to Push until the actual file-final successful terminal. Capacity,
sequence or terminal-count failure discards the image and reports failure.
Whole-song completion and Push publication are distinct: the source finishes
after the final validated terminal; `analysis_done_o` becomes true only after
Push has accepted the complete image. This coarse clip concatenation has no
cross-window CNN context stitching and requires musical quality validation.

Link loss, transport fault, cancel and PANIC fence the active worker and clear
M's unpublished score. Connect local source failure to the score collector's
cancel input. W drops aborted results and drains the actual task; it cannot
admit another task before that terminal. The memory service still requires the
documented common client/controller reset after fatal transport/calibration
loss. Reconnection is not that reset. Physical link and ready signals must stay
false until separately validated; this framework does not enable LCD IO.
