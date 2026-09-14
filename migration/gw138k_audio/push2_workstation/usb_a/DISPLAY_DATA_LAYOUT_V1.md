# Shared display data layout v1

This is the step-1 design artifact for the current P10 USB-A build. It is not connected to the P10 RTL yet.
All addresses below use the native DDR user address unit: one 32-bit word. Every payload starts on an 8-word (32-byte BL8) boundary.

## Commit/control record

The existing P5 compatibility metadata remains reserved at `0x00200000` (`0x01000000` byte address). The v1 control record will use that same single 256-bit beat when the writer is changed; the current P10 writer is left untouched.

| word bits | field | value/meaning |
|---|---|---|
| 31:0 | magic | `0x44535032` (`DSP2`) |
| 39:32 | version_minor | `0` |
| 47:40 | version_major | `1` |
| 55:48 | descriptor_words | `32` (four 8-word descriptors) |
| 63:56 | committed_bank | `0` or `1` |
| 95:64 | frame_sequence | monotonically increasing display frame |
| 127:96 | commit_sequence | even value means committed/stable |
| 159:128 | descriptor_base_word | `0x00200008` or `0x00200048` |
| 191:160 | flags | block-valid and source-status bits |
| 255:192 | reserved | zero in v1 |

The control record is written last. A consumer reads it, selects the indicated descriptor bank, then reads descriptors and payloads from that bank. The writer never modifies the committed bank.

## Descriptor tables

Two descriptor tables are reserved:

- bank 0: word `0x00200008` (byte `0x01000020`)
- bank 1: word `0x00200048` (byte `0x01000240`)

Each table has four descriptors, one 256-bit BL8 beat (8 words) per descriptor. Descriptor `i` starts at `descriptor_base_word + i*8`.

| word index | field |
|---:|---|
| 0 | block type, format, flags |
| 1 | frame sequence for this block |
| 2 | source sequence (capture/analysis sequence) |
| 3 | valid length in logical elements |
| 4 | payload base, native DDR word address |
| 5 | payload length, native DDR words |
| 6 | sample rate in Hz, or zero for non-sampled data |
| 7 | window/trigger information |

The descriptor word 0 uses: bits 7:0 block type, 15:8 format, 31:16 flags. Word 7 uses: bits 15:0 window length, bits 23:16 trigger mode, bits 31:24 trigger timeout exponent. Remaining descriptor bits are reserved by the table format.

Block types and formats:

| type | name | format | valid length | payload per bank |
|---:|---|---|---:|---:|
| `1` | waveform | signed Q1.31 mono, 32-bit words | 512 samples | 512 words |
| `2` | lissajous | packed 1-bit MID/SIDE bitmap, row-major 256×256 | 65,536 pixels | 2,048 words |
| `3` | spectrum | interleaved `L8,R8` per column | 512 columns | 256 words |
| `4` | effect metadata | 8×32-bit words, P5-compatible fields | 8 words | 8 words |

## Payload addresses

Payload bank 0 starts at word `0x00210000` (byte `0x01080000`); bank 1 starts at word `0x00220000` (byte `0x01100000`). Bank stride is `0x00010000` words, leaving alignment and future expansion space.

| block | bank-relative offset | bank 0 word address | bank 1 word address |
|---|---:|---:|---:|
| waveform | `0x0000` | `0x00210000` | `0x00220000` |
| lissajous | `0x0200` | `0x00210200` | `0x00220200` |
| spectrum | `0x0A00` | `0x00210A00` | `0x00220A00` |
| effect metadata | `0x0B00` | `0x00210B00` | `0x00220B00` |

The payload ranges do not overlap the two 4 MiB RGB565 frame banks (`0x00000000` and `0x00100000`) or the existing P5 metadata/control area (`0x00200000` onward). The current startup BIST range ends at word `0x001FFFFF`; the new display-data area is intentionally above that range and must not be described as BIST-covered until the BIST policy is updated.

## Read/write interface

The future display-data writer uses the existing memory UI clock and DDR arbiter style:

- `write_valid`, `write_ready`, `write_addr[28:0]`, `write_data[255:0]`
- requests are held until `write_ready`
- payload and descriptor writes target the inactive bank
- the control/commit beat is issued last
- no ready/backpressure signal crosses into the audio clock domain

Each consumer uses a read-only request/response interface:

- `read_valid`, `read_ready`, `read_addr[28:0]`
- `read_rsp_valid`, `read_rsp_data[255:0]`
- consumer captures one committed control record, then does not change bank until the next commit

A consumer that sees an odd `commit_sequence`, an invalid magic/version, or a block-valid flag cleared keeps its previous committed bank. No consumer is allowed to infer a payload address from an old fixed constant.

## Compatibility and scope

This layout does not change the existing Push USB-A packet protocol, HDMI TMDS path, audio clocks, effect chain, or P10 bitstream. It defines only the shared DDR data contract. The next implementation step will add a writer for these four blocks while the current HDMI raster output remains unchanged.
