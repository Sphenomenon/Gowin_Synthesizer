# Task3 W-media native memory component

`workstation_media_memory.sv` is an unselected composition, not a new accepted
W profile or a bitstream. It preserves the real maintained BIST, three-stage
memory reset release, status meanings, local slots, native command buffer and
read-owner tags. Owner5 is CNN/model traffic, owner6 is Delay, and owner8 is the
single raw recording store. Owners1/2/3/4/7 are tied idle. No display, framebuffer,
TF ring, CPU DDR window or retired R00 recording object is restored. There is
no address allocator or application/object authority here: clients still obey
the shared DDR map and their owning task/recording contracts.

Client valid and visible ready are both fenced until successful BIST. Return
valids are fenced on backend loss or native transport fault. The actual native
acceptance vector is distinct from local-slot and core-buffer admission; raw
STOP/seal must use actual owner8 native commitment. An unowned native return
stops native dispatch on the same edge and remains faulted until reset. These
new wrapper gates do not modify the old audio-only composition or arbiter.

Reset/calibration/PLL loss asynchronously closes the wrapper, including when
the memory clock stops. Safe reopening requires a **coherent controller/client
reset that discards all old native transactions**, calibration and BIST. The
untagged external DDR response bus cannot distinguish an old response from a
newly outstanding read. An old response arriving while the tag FIFO is empty
is detected and fenced; arbitrary late responses during a new read epoch are
not solved by local reset and must not be advertised as isolated by this block.
Higher-level recording epoch authority and CNN restart faults remain required.

There is no cancellation/close operation at this composition boundary. A task
owner first stops admitting work and waits for its native write commitments
and read returns. Source tests demonstrate that local admission, native
acceptance and completed reads remain distinct through independent command,
write-data and response stalls; they do not create a global drain authority.

The existing arbiter policy remains unchanged. Owner6 has strict priority over
recording at its queued-input boundary. Driving that boundary continuously
while bypassing the mandatory local slots can starve owner8. The actual local
slots insert bubbles, so the three-owner wrapper may permit progress under
loads where the bare core does not. Tests must report both observations and
must not mislabel a core-only saturation probe as actual wrapper starvation.
No general deadline follows from bounded storage, a finite simulation or
average DDR bandwidth. Actual CNN/Delay/recording offered load, maximum native
stall/return latency, task timeouts and routed clocks require a separate budget.

The component test uses real disjoint map addresses with a behavioral native
memory. It exercises BIST success/failure, simultaneous owners, masked writes,
response identity, local/core/native accounting, late returns, coherent reset
and stopped-clock loss. It does not run CNN, Delay DSP, the recording engine,
Bluetooth, LCD transport or a board, and establishes no whole-profile resource,
timing, CDC, audio deadline, SRAM or Flash acceptance.
