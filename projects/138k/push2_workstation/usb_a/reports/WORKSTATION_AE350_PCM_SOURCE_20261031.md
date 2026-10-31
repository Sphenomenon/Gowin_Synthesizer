# AE350 PCM ingress source stage v1

The explicit candidate connects decoded stereo PCM16 blocks through the native
compute queue/selector/SRC, existing PCM mixer/effects, sole final master volume
and physical I2S serializer. It does not enable an accepted profile or operate
a board. ABI and lifecycle policy are in `rtl/audio/AE350_PCM_INGRESS_CONTRACT.md`;
`tools/workstation_ae350_pcm.py` inventories opt-in sources and composition.
A fresh locked candidate must merge the HCI wrapper ports, select the macro and
complete physical CDC/resource/timing and hardware acceptance.

No DDR allocation, event-format change, replacement parameter owner or physical
clock-rate owner is introduced. CPU-interface reset retires Bluetooth while
preserving notes/common parameters and the sample schedule. Held PL epoch/
generation captures after ready settlement; ready asynchronously closes the
source. Configuration retains priority over source-history requests.

## Verification

- Owner:8 tests PASS. Complete/partial publication, immutable slots, stale-key
  rejection, CPU/session/physical/TF retirement, pending history cancellation/
  timeout quarantine, zero/one/two consumption, full queue backpressure,
  simultaneous commit/consume, identity limits, partial/history reset, drift.
- Four actual RTL drift runs each576000 output frames at44100/48000 and
  source±2000ppm with bounded block jitter. Signed stereo interpolation and
  consumption are checked independently on every output. Negative offset queue
  min134/max384, final step16743662, consumed574923; positive min211/max398,
  step16810770, consumed577117. Drift1152frames exceeds512-frame queue capacity.
- CDC/serializer:2 tests PASS. Bundle settlement and asynchronous revoke/reset;
  both-rate full-current-frame completion, cached/late discard, continued zero
  slot schedule, guarded resumption, actual pins/completed-tap equality.
- Enabled full-runtime APB/CDC/DSP/official GW5A DCS/I2S simulation:PASS.
  Actual decoded PCM, actual chorus, source histories, real APB in-flight CPU
  reset, generation/stale cancellation, MIDI/parameter retention, TF and both
  rates. Exact physical metrics are retained in delivery `runtime/run.log`.
- Existing disabled runtime_audio:20192 checked frames PASS, both-rate wet/FDN,
  14config ACKs,12switch applies, deliberate faults and retained rendering/CDC.
- Existing disabled runtime_controlled nonzero epoch:1078 physical/observed
  frames PASS, real APB/UART/USB, FFT/display/lifecycle and switch policy.
- Current-workstation source regression:17PASS. Original serializer:1PASS.
- Narrow owner Verilator lint:PASS. No enabled full-runtime warning names the
  new owner or modified runtime/serializer/fixture. Unmodified dependency
  warnings remain visible in retained logs. `git diff --check`:PASS.

Simulation uses ideal asynchronous clocks and ordered functional owner6 DDR.
It is source verification, not synthesis, routed CDC or hardware acceptance.
Intentional serial hold creates zero/error slots and ordinary underrun counts
while preserving physical clock and slot sequence.

CAPS remains0x67: adaptive SRC implemented, sustained/full-system-budget and
measured-total-delay capabilities false. Isolated drift evidence cannot set
sustained capability. Real HCI/SBC pump budgets, physical timing/resources,
source capability acceptance, actual audio/FFT/record tap equivalence and
hardware evidence remain separate work. Queue delay is real queued input
frames; DSP/output delay remains unknown.

The source-ready origin and actual boot-ID/Classic generation mux endpoints
are enumerated in the ABI contract. Published comparison tuples are not data
sources. Fresh netlist endpoint coverage and propagation bounds must precede
physical acceptance. No blanket false paths or relaxed clocks are added.

Rollback omits the opt-in macro/parameter and retains the original legacy PCM
and TF paths, validated by the disabled regressions. Frozen baselines and
accepted profile locks are untouched. The external delivery freezes source
patch/commit, input closure, logs and a hash verifier; changed release inputs
require a new candidate identity.
