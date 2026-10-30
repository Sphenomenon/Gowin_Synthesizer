#ifndef GW138K_AUDIO_CLOCK_SERVICE_H
#define GW138K_AUDIO_CLOCK_SERVICE_H
#include <stdint.h>
#include <stddef.h>

/* Dedicated native-runtime APB page; UI and audio keep their existing pages. */
#define A138_CLOCK_BASE UINT32_C(0xf8030000)
enum {
    A138_CLK_ID=0x00, A138_CLK_CAPABILITIES=0x04, A138_CLK_COMMAND=0x08,
    A138_CLK_STATUS=0x0c, A138_CLK_COMMAND_ID=0x10, A138_CLK_OPERATION=0x14,
    A138_CLK_RESULT_ID=0x18, A138_CLK_RESULT_CODE=0x1c, A138_CLK_RESULT_DETAIL=0x20,
    A138_CLK_BASE_EPOCH=0x24, A138_CLK_EXPECTED_EPOCH=0x28,
    A138_CLK_ACTUAL=0x2c, A138_CLK_SNAPSHOT_EPOCH=0x30,
    A138_CLK_LAST_BUS_REJECT=0x4c, A138_CLK_REQUEST_CONTEXT=0x58,
    A138_CLK_MEDIA_STATUS=0x60, A138_CLK_MEDIA_TIMEOUT=0x64,
    A138_CLK_MEDIA_FAILURE=0x68
};
enum { A138_CLK_48000=0, A138_CLK_44100=1, A138_CLK_RECOVER=2 };
enum {
    A138_CLK_RESULT_NONE=0, A138_CLK_RESULT_APPLIED=1,
    A138_CLK_RESULT_CORE_REJECT=2, A138_CLK_RESULT_POLICY_REJECT=3,
    A138_CLK_RESULT_CORE_FAILED=4, A138_CLK_RESULT_ACCEPT_TIMEOUT=5,
    A138_CLK_RESULT_APPLY_TIMEOUT=6, A138_CLK_RESULT_CONTEXT_MISMATCH=7,
    A138_CLK_RESULT_MEDIA_FAILED=8, A138_CLK_RESULT_MEDIA_TIMEOUT=9,
    A138_CLK_RESULT_MEDIA_GATE=10
};
enum {
    A138_CLK_CAP_MEDIA_POLICY=1u<<4, A138_CLK_BUS_MEDIA_NOT_READY=14,
    A138_CLK_MEDIA_HOLD=1u<<0, A138_CLK_MEDIA_PENDING=1u<<1,
    A138_CLK_MEDIA_COMPLETED=1u<<2, A138_CLK_MEDIA_FAILED=1u<<3,
    A138_CLK_MEDIA_ENABLED=1u<<4, A138_CLK_MEDIA_BACKEND_READY=1u<<5
};
/* MEDIA_FAILURE keeps TF reasons 1..8; additional categories identify local
 * or BLE seal failure and backend admission failure. BLE detail has its own
 * owner. Admission failure requires a new caller decision, without retries. */
enum {
    A138_CLK_MEDIA_REASON_RECORD_SEAL=9,
    A138_CLK_MEDIA_REASON_BLE_SEAL=10,
    A138_CLK_MEDIA_REASON_BACKEND_ADMISSION=11
};
typedef enum {
    A138_CLK_IO_ERROR=-5, A138_CLK_INVALID=-4, A138_CLK_UNSUPPORTED=-3,
    A138_CLK_UNARMED=-2, A138_CLK_REJECTED=-1,
    A138_CLK_PENDING=0, A138_CLK_SUBMITTED=1, A138_CLK_APPLIED=2,
    A138_CLK_FAILED=3, A138_CLK_SUPERSEDED=4, A138_CLK_CONTEXT_LOST=5
} a138_clock_result;

/* Return nonzero only for a completed, error-free bus access. One caller owns
 * the page and serializes all access. Probe/submit/poll perform at most 2/9/11
 * accesses, with no retry or wait loop. Call poll once per service turn.
 * Callbacks must themselves have a transport timeout. A failed write can have
 * committed: do not automatically retry it. Discard tickets on CPU observer
 * reset; reset/wrap ID reuse is not a persistent session fence. */
typedef struct {
    void *context;
    int (*read)(void *, uint32_t offset, uint32_t *value);
    int (*write)(void *, uint32_t offset, uint32_t value);
} a138_clock_bus;
typedef struct {
    uint32_t command_id, expected_epoch, expected_rate_hz;
} a138_clock_ticket;
typedef struct {
    uint32_t phase, result_code, detail, media_status, media_failure;
    uint32_t actual_rate_hz, actual_epoch;
    uint32_t command_id, result_id;
} a138_clock_status;

/* Raw uncached MMIO adapter uses existing I/O fences. A platform bus-fault
 * handler is still required for physical APB faults; checked transports may
 * instead return zero from read/write. No board action happens on creation. */
a138_clock_bus a138_clock_mmio_bus(uintptr_t base);
/* Probe returns SUBMITTED for the supported v1 media-policy ABI. It performs
 * no write. All unsuccessful submissions leave the caller's ticket intact.
 * Poll preserves status on I/O failure or an unstable ID bracket. Result
 * fields describe this ticket only when its result_id matches command_id. */
a138_clock_result a138_clock_probe(const a138_clock_bus *bus);
a138_clock_result a138_clock_submit(const a138_clock_bus *bus, uint32_t operation,
                                    a138_clock_ticket *ticket);
a138_clock_result a138_clock_poll(const a138_clock_bus *bus,
                                  const a138_clock_ticket *ticket,
                                  a138_clock_status *status);
#endif
