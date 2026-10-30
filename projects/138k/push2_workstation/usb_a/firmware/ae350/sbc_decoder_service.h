#ifndef A138_SBC_DECODER_SERVICE_H
#define A138_SBC_DECODER_SERVICE_H

#include <stdint.h>
#include "oi_codec_sbc.h"

#define A138_SBC_MAX_FRAME_BYTES 224u
#define A138_SBC_MAX_PCM_SAMPLES 256u

enum a138_sbc_status {
    A138_SBC_OK, A138_SBC_ARGUMENT, A138_SBC_STALE, A138_SBC_INACTIVE,
    A138_SBC_FORMAT, A138_SBC_FRAME, A138_SBC_CODEC
};

struct a138_sbc_format {
    uint32_t rate_hz;
    uint8_t mode;             /* SBC: mono=0, dual=1, stereo=2, joint=3. */
    uint8_t subbands;         /* 4 or 8. */
    uint8_t blocks;           /* 4, 8, 12 or 16. */
    uint8_t allocation;       /* loudness=0, SNR=1. */
    uint8_t min_bitpool;
    uint8_t max_bitpool;      /* This bounded port accepts at most 53. */
};

struct a138_sbc_pcm {
    uint32_t stream_epoch;
    uint32_t rate_hz;
    uint16_t frames;          /* PCM frames per channel, at most 128. */
    uint16_t scalar_samples;  /* Interleaved signed 16-bit samples. */
    uint8_t channels;
    uint8_t valid;            /* Set only after a complete successful decode. */
};

/* Caller owns this object in CPU-local memory; single cooperative CPU owner.
 * It contains no transport queue, DMA or MMIO state. Do not share it with RTL.
 */
struct a138_sbc_decoder {
    OI_CODEC_SBC_DECODER_CONTEXT codec;
    uint32_t workspace[CODEC_DATA_WORDS(2, SBC_CODEC_FAST_FILTER_BUFFERS)];
    struct a138_sbc_format format;
    uint32_t last_epoch;
    uint8_t active;
};

void a138_sbc_init(struct a138_sbc_decoder *decoder);
/* Epochs must strictly increase during this initialized object's lifetime.
 * Reinitialization/CPU reset requires the future transport owner to retire and
 * fence all queued descriptors before it can establish a new stream.
 */
enum a138_sbc_status a138_sbc_begin(struct a138_sbc_decoder *decoder,
                                   uint32_t stream_epoch,
                                   const struct a138_sbc_format *format);
enum a138_sbc_status a138_sbc_cancel(struct a138_sbc_decoder *decoder,
                                    uint32_t stream_epoch);
/* One complete SBC frame per call, no waits, heap or callbacks. Length and
 * negotiated format are checked before entering the decoder. The caller may
 * publish PCM only when return==OK and result.valid. Codec/frame failure
 * closes this stream; recovery needs a greater epoch and fresh history.
 * Input/output/result must be separate, valid non-overlapping buffers.
 */
enum a138_sbc_status a138_sbc_decode(struct a138_sbc_decoder *decoder,
                                    uint32_t stream_epoch,
                                    const uint8_t *frame, uint32_t frame_bytes,
                                    int16_t *pcm, uint32_t pcm_samples,
                                    struct a138_sbc_pcm *result);

#endif
