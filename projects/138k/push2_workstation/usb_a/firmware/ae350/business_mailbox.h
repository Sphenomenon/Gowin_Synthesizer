#ifndef GW138K_BUSINESS_MAILBOX_H
#define GW138K_BUSINESS_MAILBOX_H
#include <stdint.h>
#include <stddef.h>
/* Relative window only: S1a allocates no physical APB page. */
enum {
    A138_BM_ID=0x000,A138_BM_CAPS=0x004,A138_BM_STATE=0x008,A138_BM_OWNER=0x00c,
    A138_BM_BOOT_LOW=0x010,A138_BM_BOOT_HIGH=0x014,A138_BM_SESSION=0x018,
    A138_BM_TICKET=0x01c,A138_BM_SLOT_OWNER=0x020,A138_BM_SLOT_SESSION=0x024,
    A138_BM_SLOT_BOOT_LOW=0x028,A138_BM_SLOT_BOOT_HIGH=0x02c,A138_BM_REQUEST_ID=0x030,
    A138_BM_NONCE_LOW=0x034,A138_BM_NONCE_HIGH=0x038,A138_BM_REQUEST_META=0x03c,
    A138_BM_REQUEST_DATA0=0x040,A138_BM_AGE=0x050,A138_BM_ADMITTED=0x054,
    A138_BM_REJECTED_COUNT=0x058,A138_BM_TIMEOUT_COUNT=0x05c,A138_BM_STALE_COUNT=0x060,
    A138_BM_ABANDONED_COUNT=0x064,A138_BM_LAST_REASON=0x068,
    A138_BM_KEY_TICKET=0x080,A138_BM_KEY_OWNER=0x084,A138_BM_KEY_SESSION=0x088,
    A138_BM_KEY_BOOT_LOW=0x08c,A138_BM_KEY_BOOT_HIGH=0x090,A138_BM_RESULT_META=0x094,
    A138_BM_RESULT_OPERATION=0x098,A138_BM_RESULT_DATA0=0x09c,A138_BM_COMMAND=0x0dc,
    A138_BM_LAST_TICKET=0x0e0,A138_BM_LAST_OWNER=0x0e4,A138_BM_LAST_SESSION=0x0e8,
    A138_BM_LAST_BOOT_LOW=0x0ec,A138_BM_LAST_BOOT_HIGH=0x0f0,A138_BM_LAST_META=0x0f4,
    A138_BM_LAST_OPERATION=0x0f8
};
enum { A138_BM_OPEN=1,A138_BM_CLAIM=2,A138_BM_COMPLETE=3,A138_BM_ABANDON=4,A138_BM_CLOSE=5 };
enum { A138_BM_EMPTY=0,A138_BM_QUEUED=1,A138_BM_CLAIMED=2,A138_BM_RESULT=3,A138_BM_PUBLISHED=4 };
enum { A138_BM_PENDING=1,A138_BM_APPLIED=2,A138_BM_FAILED=3,
       A138_BM_LOCAL_REJECTED=4,A138_BM_UNCERTAIN_PHASE=5 };
enum { A138_BM_LOCAL_CANCEL=1,A138_BM_OWNER_RESET=2,A138_BM_SESSION_LOST=3,
       A138_BM_TIMEOUT=4,A138_BM_OWNER_CLOSE=5,A138_BM_BOOT_CHANGED=6 };
enum { A138_BM_OK=1,A138_BM_NONE=0,A138_BM_IO=-1,A138_BM_INVALID=-2,
       A138_BM_STALE=-3,A138_BM_COMMIT_UNCERTAIN=-4 };
typedef struct {
    void *context;
    int (*read)(void *,uint32_t,uint32_t *);
    int (*write)(void *,uint32_t,uint32_t);
} a138_business_bus;
typedef struct { uint64_t boot_id;uint32_t owner,session,ticket; } a138_business_key;
typedef struct {
    a138_business_key key;
    uint64_t nonce;
    uint32_t request_id,opcode,length;
    uint8_t payload[16];
} a138_business_request;
typedef struct { uint32_t phase,status,operation_id,length;const uint8_t *payload; } a138_business_completion;
typedef struct { uint32_t state,phase,status,length,reason,operation_id; } a138_business_observation;
/* Single caller, uncached MMIO with fences. Callbacks return nonzero only for a
 * successful access; zero means failure and may follow a committed write.
 * A bus reset/discontinuity must abort the in-flight API call: callbacks and
 * split 32-bit reads cannot establish a snapshot across arbitrary common resets.
 * Complete slot/publication keys are checked before publishing read outputs.
 * No retry, wait loop, task allocation
 * or wire encoding. CLAIM is not business acceptance. PENDING publication means
 * the sole owner has already reserved operation_id. APPLIED means verified fact.
 * A final command write callback can fail after committing: return UNCERTAIN,
 * observe the exact key, then query the task owner; never resubmit blindly.
 * ABANDON/CLOSE and hardware local results abandon observation only. A claimed
 * task can continue after reset/timeout/disconnect, including before an ID was
 * visible. NONE/IO/STALE leave output structs untouched. Historical publication
 * is a delivery fact, not proof that a background operation completed. */
/* Direct volatile MMIO cannot recover/report slave errors or reset interruption.
 * Production needs an ACK/error-aware bridge and a defined CPU fault policy. */
a138_business_bus a138_business_mmio_bus(uintptr_t base);
int a138_business_probe(const a138_business_bus *bus);
int a138_business_context(const a138_business_bus *bus,a138_business_key *out);
int a138_business_read_request(const a138_business_bus *bus,a138_business_request *out);
int a138_business_open(const a138_business_bus *bus,const a138_business_key *context);
int a138_business_claim(const a138_business_bus *bus,const a138_business_key *key);
int a138_business_complete(const a138_business_bus *bus,const a138_business_key *key,
                           const a138_business_completion *completion);
int a138_business_abandon(const a138_business_bus *bus,const a138_business_key *key);
int a138_business_close(const a138_business_bus *bus,const a138_business_key *context);
int a138_business_observe(const a138_business_bus *bus,const a138_business_key *key,
                         a138_business_observation *out);
#endif
