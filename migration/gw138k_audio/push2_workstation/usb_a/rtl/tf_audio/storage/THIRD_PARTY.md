# TF/FAT32 reader source

The low-level SPI/FAT implementation in this directory is vendored from
[`WangXuan95/FPGA-SDcard-Reader-SPI`](https://github.com/WangXuan95/FPGA-SDcard-Reader-SPI),
commit `75ef453` (2023-09-14). That repository is GPL-3.0; the corresponding
license text is kept in [`GPL-3.0.txt`](GPL-3.0.txt). The three files beginning
with `third_party_` remain separately attributable and carry SPDX headers.

The Tang Mega 138K integration changes only the FAT32 directory start-cluster
capture from 16 to 32 bits and adds the `file_size_o` status output. The new
[`tf_audio_file_reader.v`](tf_audio_file_reader.v) is project code: it maps the
31005 dock's SPI-compatible SDIO nets and probes MP3/RIFF-WAVE/FLAC signatures
while preserving the raw file-byte stream.

## Decoder sources

The MP3 and WAV datapath is adapted from
[`kami4ka/tang_mp3_player`](https://github.com/kami4ka/tang_mp3_player),
commit `7b0c43c` (2026-08-06), GPL-3.0. The repository is a pure-RTL
MPEG-1 Layer III player for Tang hardware and includes the verified MP3 core,
PCM granule drain, WAV parser, byte FIFO and an improved FAT16/FAT32 reader.
The copied RTL is under [`tang_mp3/`](tang_mp3/); the SPI module names are
prefixed `tf_` so it can coexist with the earlier single-file reader.
The upstream license is preserved at [`tang_mp3/LICENSE`](tang_mp3/LICENSE).

Project adapters are [`tf_mp3_pcm_decoder.v`](tf_mp3_pcm_decoder.v),
[`tf_wav_pcm_decoder.v`](tf_wav_pcm_decoder.v), and
[`tf_sd_audio_pcm_player.v`](tf_sd_audio_pcm_player.v). The last one selects
`AUDIO_KIND=1, FILE_EXT="MP3"` or `AUDIO_KIND=2, FILE_EXT="WAV"`, starts the
first matching root-directory file, and exposes a stereo PCM16 ready/valid
stream. The stream can feed a sample pacer/DAC directly or a BRAM/DDR writer.
WAV support is 8/16/24/32-bit mono or stereo PCM. The header is parsed by the
project-owned [`tf_wav_chunk_parser.v`](tf_wav_chunk_parser.v), which walks the
real RIFF chunk list (`LIST`/`fact`/`JUNK`/unknown chunks, 16/18/40-byte
`fmt `, odd-size alignment) instead of the vendored `wav_parser`'s fixed
44-byte offsets; `tang_mp3/audio/wav_parser.v` is retained but no longer used by
the WAV path. Non-PCM streams and >2 channels are reported as unsupported.

For FLAC, the integration also reviewed the open candidates
[`nayannair/flacFPGA`](https://github.com/nayannair/flacFPGA) and
[`xavieran/fLaCPGA`](https://github.com/xavieran/fLaCPGA). They do not provide
a complete, integrated FLAC container/frame decoder: the former stops at
fixed-subframe building blocks and synthesis-only verification, while the
latter is primarily an encoder/software project. No complete permissively
licensed FLAC RTL source was found for a safe drop-in. The project-owned
[`tf_flac_pcm_decoder.v`](tf_flac_pcm_decoder.v) therefore implements and
tests a deliberately bounded hardware subset: native FLAC metadata,
fixed-block frames, mono/independent stereo, constant/verbatim/fixed-predictor
subframes and Rice methods 0/1. LPC, variable-block frames, side/mid stereo,
wasted bits and Rice escape coding report unsupported instead of producing
unverified PCM. CRC fields are parsed but are not yet validated.

The original single-file wrapper remains useful for SD bring-up; its selected
file is a synthesis parameter (default `SONG.WAV`) and must be an 8.3 short
name in the FAT32 root directory. The playlist player scans all matching 8.3
extensions in the root directory, but subdirectories and runtime track
selection are still follow-up control work.
