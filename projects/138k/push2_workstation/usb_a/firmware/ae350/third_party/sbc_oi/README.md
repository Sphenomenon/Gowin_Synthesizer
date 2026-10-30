# Apache SBC decoder source-stage

This decoder is **not selected** by the maintained firmware builder or any
workstation profile. It is a reusable, bounded CPU decoder for B04; it does not
implement HCI, A2DP session negotiation, compressed queues, DMA, sample-rate
conversion, PCM publication, or a real-time audio schedule.

`upstream/` preserves the decoder files, README and content register from
[`zephyrproject-rtos/libsbc`](https://github.com/zephyrproject-rtos/libsbc) revision
`8e1beda02acb8972e29e6edbb423f7cafe16e445`, the revision pinned by the examined
Zephyr tree. Its content register identifies Android source revision
`6b3bed846fb38036e23e70b18c07be2fa1c0aaaf`. Each source retains its Android/OI
copyright and Apache-2.0 notice. The standard Apache license text is retained in
`LICENSE.Apache-2.0`. No encoder or BTstack/BlueZ implementation is vendored.
`upstream_manifest.json` binds the exact 32 retrieved input files.

`tools/prepare_ae350_sbc.py` verifies the complete inventory and every original
hash before copying the decoder to a new output directory. Adaptations use exact
anchors and counts and fail on drift. The output records original/adapted hashes,
the adapter identity and each change. The original vendor bytes never change.

The separate port fixes zero-bit reads that shift by 32, the 4-subband joint
stereo first half-byte read, and negative signed shifts. It also widens transform
and window sums, uses a 32-by-64 multiply helper, and saturates joint subband and
filter-state narrowing. These defenses are necessary for valid CRC packets with
extreme scale factors; passing ordinary music vectors alone did not expose the
overflow. `a138_sbc_arithmetic.h` is first-party adaptation code. The target must
have 32-bit `int` and arithmetic signed right shift; compile-time checks enforce
these assumptions. Floating point and heap allocation are not used.

The bounded service in `../../sbc_decoder_service.h/.c` accepts one complete
negotiated SBC frame per call: 44.1/48 kHz, mono/dual/stereo/joint, 4/8 subbands,
4/8/12/16 blocks, loudness/SNR allocation and bitpool 2..53. Its maximum is
224 compressed bytes and 256 interleaved signed 16-bit scalar samples (512
bytes). The caller must choose a supported configuration during AVDTP and
reassemble RTP/SBC fragmentation before invoking this API. It must not assume
that an HCI packet, L2CAP PDU, RTP packet and SBC frame have the same boundary.

The caller owns one CPU-local decoder object. `begin` clears synthesis history
and requires a strictly greater nonzero epoch; cancellation closes the current
epoch. Frame/codec failure closes that stream. Short output capacity can be
retried without consuming the frame. A stale descriptor never decodes. The
result becomes valid only after the whole frame succeeds. Epoch exhaustion
fails closed. Reinitialization/CPU reset still requires an external transport
fence; this service cannot retire hardware-owned queue descriptors by itself.
The caller must serialize these calls and keep input, output and result buffers
separate. PCM may be published only after `OK` and `result.valid`.

From the repository root:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_sbc_decoder.py \
  --output /tmp/ae350-sbc-new
```

The runner uses 11 checked-in independent BlueZ reference cases, ASan/UBSan,
history/cancel/epoch/format/CRC guards, valid-CRC extreme/random payloads, source
and behavior mutants, and an RV32 standalone incremental link. An optional
`--reference-root <vectors-v1>` includes the external 42-case research corpus.
Reference PCM is generated from first-party stimuli; no LGPL codec source or
BTstack code is shipped. These are regression vectors, not Bluetooth SIG
qualification vectors or phone interoperability evidence.

The incremental link uses function/data sections and section GC. It does not
prove complete firmware fit, a full call-chain stack bound, cycle deadlines or
physical memory cost. No production compiler policy changes with this stage.

Before selection, retain this checked-source policy and complete the single HCI
owner, BR/EDR session stack, shared ACL credits, bounded DMA queues, A03/A06 rate
policy, long-term clock-drift handling, complete firmware budget and real phone
tests. Submit the narrowly scoped decoder fixes upstream or pin a reviewed
patched upstream revision; retire this temporary adapter only after the same
regressions pass with that revision. See the dated B04 report for current scope.
