# Recording normal-seal crossing

`workstation_recording_seal_bridge` carries one normal-seal transaction from the
control clock to the recording service's memory clock. It does not own the
recording object, frame acceptance, DDR drain, or sample-rate decision. The media
owner must wait for actual success or failure before requesting a rate switch;
held notes remain outside this channel. See [media stop policy](MEDIA_STOP_POLICY.md).

Both domains asynchronously assert the common controller reset. Each has two
`ASYNC_REG` release FFs clocked locally; all its functional FFs remain reset until
that domain's second release FF rises. A stopped clock cannot release its domain.
Only common reset cancels this channel and clears its tokens, pending state,
hold, ready, terminal and failure detail. CPU observer reset is absent: losing a
CPU observer cannot cancel a backend seal or discard the recording object.

The memory domain registers `destination_ready_i && !destination_pending &&
!hold_sync` in `destination_ready`. Only this publisher Q enters the source's
two-stage ready synchronizer. The source does not sample a combinational mixture
of a raw backend reset/ready and bridge hold/pending state. A pulse not captured
by the memory domain is not published. This is a synchronized status observation,
not a reservation: if the backend loses readiness before request arrival, the
bridge sends no backend request and returns failure 11 without retry.

The caller observes `ready_o`, then registers request and hold together. Acceptance
uses synchronized ready and no source pending; it deliberately does not use
`ready_o`, whose local hold mask would reject that same request. Acceptance
toggles the request token once, clears old failure detail, and registers source
hold. Source pending retains hold even if the caller withdraws its hold. The
registered hold crosses two memory-clock FFs alongside the request token; the
backend request is a single memory-clock pulse. No second request is accepted
while source pending.

The bridge ignores a terminal left over at the registered request delivery edge.
After delivery, the first real backend done/failed publishes a result token and
stable failure payload. Failed takes priority if both terminal inputs assert.
Success carries failure code zero. Source pending clears only when its two-stage
result synchronizer observes that new token. Done/failed pulse once in the source
domain; failure detail persists until a new acceptance or common reset. The
source hold may remain for an extra local cycle while the previous pending value
retires, then follows caller hold. The memory registered ready and source ready
synchronizer must subsequently observe backend rearm before a new transaction.

Run `python3 sim/test_workstation_recording_seal_bridge.py` for the phase/reset,
ready-publisher, hold, token, terminal and negative controls. The real recording
runtime regression is `python3 sim/services/run_workstation_recording_runtime.py
--output <new-directory>`; its observer-reset case holds an actual DDR drain open
and checks that the bridge still returns the real immutable-object terminal.
These are offline RTL checks. They do not prove metastability behavior, actual
mapped/reset fanout, payload data flight, routed setup/hold/recovery/removal, or
full-workstation and hardware acceptance. New source needs a new prepare and
synthesis seal; previous candidate CDC or physical evidence does not transfer.
