# Proposed OPEN_SECOND0x40 (not yet released)

OPEN_SECOND40 explicitly permits codec0 RAW, codec10 first-order/k9 and
codec11 second-order/k5. The16-byte request,24-byte response, PCM limit,
B3 max8160/64fragments and decoded identity/CRC/range/ACK fields match3d.
Use distinct READ_SECOND41 and ACK_READ_SECOND42. Their payloads match3e/3f.
The successful DATA reserved low byte identifies0/10/11; high byte remains0.

For each stereo channel maintain last_sample and last_delta, initially0 for
each block. delta=(sample-last_sample) mod2^16;
second_delta=(delta-last_delta) mod2^16. Treat second_delta as signed16,
zigzag it, encode with Rice k5. Same bounded15-one escape to unsigned16,
MSB-first and canonical escape/zero final padding as codec10.
Decoder predictor=(2*last_sample-before_sample) mod2^16, initially0;
add signed decoded residual mod2^16. No dictionary or tone-specific state.

Count both candidate byte lengths; choose11 only when shorter than10;
choose RAW when neither is strictly shorter than decoded PCM. Tie uses10,
so old3d/3e/3f remain bit-identical even inside40. Old31/35 remain RAW.
Codec11 requires active40 + pending41/42 on both FPGA and APP.
Cached41/42 replay requires active40 and sufficient current limit; downgrade
rejects8d without DATA/cursor/cache changes. Reopen40 recovers exact encoding.

APP probes40 before3d, only explicit80 permits downgrade. In a promised40
session, READ41/42 failures never silently fall back. Decode and validate
logicalCRC/PCMCRC/identity/range before positive receipt, then durablePCM
and checkpoint beforeACK. Negotiated RAW or10 are valid41/42 responses.
