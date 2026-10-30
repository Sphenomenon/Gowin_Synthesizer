#ifndef A138_SBC_ARITHMETIC_H
#define A138_SBC_ARITHMETIC_H
#include <stdint.h>

/* The portable port uses wider transform/window sums and explicit saturation.
 * Input subband samples are int32; every transform intermediate stays far below
 * int64 range. Arithmetic right shift is required and checked for the target.
 */
_Static_assert((-1 >> 1) == -1, "SBC requires arithmetic signed right shift");

static inline int16_t a138_sbc_clip16(int64_t x) {
    return x < -32768 ? -32768 : x > 32767 ? 32767 : (int16_t)x;
}

static inline int32_t a138_sbc_clip32(int64_t x) {
    return x < INT32_MIN ? INT32_MIN : x > INT32_MAX ? INT32_MAX : (int32_t)x;
}

/* floor((u * v) / 2^32), without a 96-bit temporary. Here |v| < 2^40,
 * u is int32 and the nonnegative low limb is at most UINT32_MAX. Thus its
 * signed 64-bit product fits, and the high-limb product is much smaller.
 */
static inline int64_t a138_sbc_mul32x64_hi(int32_t u, int64_t v) {
    return (int64_t)u * (v >> 32) + (((int64_t)u * (uint32_t)v) >> 32);
}
#endif
