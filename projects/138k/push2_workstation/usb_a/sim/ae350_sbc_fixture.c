#include "sbc_decoder_service.h"
#include "a138_sbc_arithmetic.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)

static struct a138_sbc_format format_of(const uint8_t *f) {
    struct a138_sbc_format r = {
        .rate_hz = (f[1] >> 6) == 2 ? 44100u : 48000u,
        .mode = (f[1] >> 2) & 3u,
        .subbands = f[1] & 1u ? 8u : 4u,
        .blocks = 4u + 4u * ((f[1] >> 4) & 3u),
        .allocation = (f[1] >> 1) & 1u, .min_bitpool = 2, .max_bitpool = 53
    };
    return r;
}

static unsigned frame_size(const uint8_t *f) {
    unsigned mode = (f[1] >> 2) & 3u, channels = mode ? 2u : 1u;
    unsigned subbands = f[1] & 1u ? 8u : 4u, blocks = 4u + 4u * ((f[1] >> 4) & 3u);
    return 4u + subbands * channels / 2u +
        (blocks * f[2] * (mode < 2u ? channels : 1u) + (mode == 3u ? subbands : 0u) + 7u) / 8u;
}

static uint8_t frame_crc(const uint8_t *frame) {
    unsigned mode = (frame[1] >> 2) & 3u, channels = mode ? 2u : 1u;
    unsigned subbands = frame[1] & 1u ? 8u : 4u;
    unsigned bits = 16u + 4u * subbands * channels + (mode == 3u ? subbands : 0u);
    uint8_t crc = 0x0f;
    for (unsigned i = 0; i < bits; ++i) {
        unsigned index = i < 16u ? i / 8u + 1u : (i - 16u) / 8u + 4u;
        unsigned bit = (frame[index] >> (7u - (i % 8u))) & 1u;
        unsigned feedback = (crc >> 7) ^ bit;
        crc <<= 1;
        if (feedback) crc ^= 0x1d;
    }
    return crc;
}

static void payload_checks(const uint8_t *first, unsigned bytes) {
    struct a138_sbc_decoder d;
    struct a138_sbc_format f = format_of(first);
    struct a138_sbc_pcm result;
    uint8_t frame[224];
    struct { uint32_t before; int16_t samples[256]; uint32_t after; } pcm = {.before=0x12345678, .after=0xabcdef01};
    uint32_t random = 0x13579bdf;
    a138_sbc_init(&d);
    CHECK(frame_crc(first) == first[3]);
    for (unsigned n = 0; n < 128u; ++n) {
        CHECK(a138_sbc_begin(&d, n + 1u, &f) == A138_SBC_OK);
        memcpy(frame, first, 4);
        for (unsigned i = 4; i < bytes; ++i) {
            random = random * 1664525u + 1013904223u;
            frame[i] = n % 4u == 0u ? 0xffu : n % 4u == 1u ? 0u : random >> 24;
        }
        frame[3] = frame_crc(frame);
        CHECK(a138_sbc_decode(&d, n + 1u, frame, bytes, pcm.samples, 256, &result) == A138_SBC_OK);
        CHECK(result.valid && result.stream_epoch == n + 1u);
        CHECK(pcm.before == 0x12345678 && pcm.after == 0xabcdef01);
    }
}

static void boundary_checks(const uint8_t *frame, unsigned bytes) {
    struct a138_sbc_decoder d;
    struct a138_sbc_format f = format_of(frame), bad = f;
    struct a138_sbc_pcm result;
    int16_t a[256], b[256];
    uint8_t corrupt[224];
    a138_sbc_init(&d);
    CHECK(a138_sbc_begin(&d, 0, &f) == A138_SBC_ARGUMENT);
    bad.max_bitpool = 54;
    CHECK(a138_sbc_begin(&d, 1, &bad) == A138_SBC_ARGUMENT);
    CHECK(a138_sbc_begin(&d, 1, &f) == A138_SBC_OK);
    CHECK(a138_sbc_decode(&d, 0, frame, bytes, a, 256, &result) == A138_SBC_STALE);
    CHECK(!result.valid && d.active);
    CHECK(a138_sbc_decode(&d, 1, frame, bytes, a, 0, &result) == A138_SBC_ARGUMENT);
    CHECK(!result.valid && d.active);
    CHECK(a138_sbc_decode(&d, 1, frame, bytes, a, 256, &result) == A138_SBC_OK);
    CHECK(result.valid && result.stream_epoch == 1 && result.scalar_samples <= 256);
    unsigned samples = result.scalar_samples;
    for (unsigned i = 0; i < 4; ++i)
        CHECK(a138_sbc_decode(&d, 1, frame, bytes, b, 256, &result) == A138_SBC_OK);
    CHECK(a138_sbc_cancel(&d, 1) == A138_SBC_OK);
    CHECK(a138_sbc_decode(&d, 1, frame, bytes, b, 256, &result) == A138_SBC_INACTIVE);
    CHECK(!result.valid);
    CHECK(a138_sbc_begin(&d, 1, &f) == A138_SBC_STALE);
    CHECK(a138_sbc_begin(&d, 2, &f) == A138_SBC_OK);
    CHECK(a138_sbc_cancel(&d, 1) == A138_SBC_STALE);
    CHECK(d.active);
    CHECK(a138_sbc_decode(&d, 2, frame, bytes, b, 256, &result) == A138_SBC_OK);
    CHECK(!memcmp(a, b, samples * sizeof *a));
    CHECK(a138_sbc_decode(&d, 2, frame, bytes - 1u, b, 256, &result) == A138_SBC_FRAME);
    CHECK(!result.valid && !d.active);
    CHECK(a138_sbc_begin(&d, 3, &f) == A138_SBC_OK);
    memcpy(corrupt, frame, bytes); corrupt[3] ^= 128;
    CHECK(a138_sbc_decode(&d, 3, corrupt, bytes, b, 256, &result) == A138_SBC_CODEC);
    CHECK(!result.valid && !d.active);
    CHECK(a138_sbc_begin(&d, 4, &f) == A138_SBC_OK);
    memcpy(corrupt, frame, bytes); corrupt[1] ^= 64;
    CHECK(a138_sbc_decode(&d, 4, corrupt, bytes, b, 256, &result) == A138_SBC_FORMAT);
    CHECK(!result.valid && !d.active);
    CHECK(a138_sbc_begin(&d, UINT32_MAX, &f) == A138_SBC_OK);
    CHECK(a138_sbc_cancel(&d, UINT32_MAX) == A138_SBC_OK);
    CHECK(a138_sbc_begin(&d, 1, &f) == A138_SBC_STALE);
    CHECK(a138_sbc_begin(&d, UINT32_MAX, &f) == A138_SBC_STALE);
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    FILE *in = fopen(argv[1], "rb"), *out = fopen(argv[2], "wb");
    CHECK(in && out);
    const int32_t multipliers[] = {INT32_MIN, INT32_MIN + 1, -1, 0, 1, INT32_MAX};
    const int64_t operands[] = {-(1LL<<39), -(1LL<<32)-1, -(1LL<<32), -1, 0, 1,
                               (1LL<<32)-1, 1LL<<32, (1LL<<39)-1};
    for (unsigned i = 0; i < sizeof multipliers / sizeof *multipliers; ++i)
        for (unsigned j = 0; j < sizeof operands / sizeof *operands; ++j) {
            __int128 product = (__int128)multipliers[i] * operands[j];
            __int128 divisor = (__int128)1 << 32;
            int64_t reference = product / divisor;
            if (product < 0 && product % divisor) --reference;
            CHECK(a138_sbc_mul32x64_hi(multipliers[i], operands[j]) == reference);
        }
    struct a138_sbc_decoder d;
    a138_sbc_init(&d);
    struct { uint32_t before; int16_t samples[256]; uint32_t after; } pcm = {.before=0x12345678, .after=0xabcdef01};
    uint8_t data[224];
    unsigned frames = 0, samples = 0;
    for (;;) {
        size_t n = fread(data, 1, 4, in);
        if (!n) break;
        CHECK(n == 4);
        unsigned bytes = frame_size(data);
        CHECK(bytes <= sizeof data && bytes >= 4);
        CHECK(fread(data + 4, 1, bytes - 4, in) == bytes - 4);
        if (!frames) {
            boundary_checks(data, bytes);
            payload_checks(data, bytes);
            struct a138_sbc_format format = format_of(data);
            CHECK(a138_sbc_begin(&d, 10, &format) == A138_SBC_OK);
        }
        struct a138_sbc_pcm result;
        CHECK(a138_sbc_decode(&d, 10, data, bytes, pcm.samples, 256, &result) == A138_SBC_OK);
        CHECK(result.valid && result.stream_epoch == 10 && result.rate_hz == d.format.rate_hz);
        CHECK(result.frames == d.format.blocks * d.format.subbands);
        CHECK(result.scalar_samples == result.frames * result.channels);
        CHECK(pcm.before == 0x12345678 && pcm.after == 0xabcdef01);
        CHECK(fwrite(pcm.samples, 2, result.scalar_samples, out) == result.scalar_samples);
        ++frames; samples += result.scalar_samples;
    }
    CHECK(frames && !ferror(in));
    CHECK(!fclose(in) && !fclose(out));
    fprintf(stderr, "PASS checks=%u frames=%u samples=%u context=%zu\n", checks, frames, samples, sizeof d);
    return 0;
}
