#ifndef GW138K_AUDIO_SERVICES_H
#define GW138K_AUDIO_SERVICES_H
#include <stdint.h>
#include <stddef.h>

/* Window offsets only. The AE350 physical base is deliberately not invented. */
enum {
    A138_ID=0x000, A138_VERSION=0x004, A138_CAPABILITIES=0x008,
    A138_SNAPSHOT=0x010, A138_SNAPSHOT_VALID=0x014, A138_STATE_BASE=0x020,
    A138_RECORD_ENABLE=0x080, A138_RECORD_STATUS=0x084, A138_RECORD_POP=0x088,
    A138_RECORD_SEQUENCE=0x08c, A138_RECORD_LEFT=0x090, A138_RECORD_RIGHT=0x094,
    A138_RECORD_RELEASE=0x098,
    A138_SCORE_ADDRESS=0x100, A138_SCORE_TIME=0x104, A138_SCORE_MASK=0x108,
    A138_SCORE_COMMIT=0x10c, A138_SCORE_LENGTH=0x110, A138_SCORE_START=0x114,
    A138_SCORE_STOP=0x118, A138_SCORE_STATUS=0x11c, A138_SCORE_CLEAR=0x120,
    A138_SCORE_LEDS=0x124, A138_SCORE_FRAME=0x128, A138_SCORE_LOADED=0x12c
};
typedef struct { uint32_t sequence; int32_t left, right; } a138_record;
typedef struct { uint32_t frame, led_mask; } a138_cue;

/* Caller owns serialization, bus fault handling and an uncached MMIO mapping. */
static inline void a138_fence(void) {
#ifdef __riscv
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#else
    __asm__ volatile ("" ::: "memory");
#endif
}
static inline uint32_t a138_read(uintptr_t base, uint32_t offset) {
    a138_fence();
    uint32_t value=*(volatile uint32_t *)(base+offset);
    a138_fence();
    return value;
}
static inline void a138_write(uintptr_t base, uint32_t offset, uint32_t value) {
    a138_fence();
    *(volatile uint32_t *)(base+offset)=value;
    a138_fence();
}
static inline int a138_probe(uintptr_t base) {
    return a138_read(base,A138_ID)==UINT32_C(0x41313338) &&
           a138_read(base,A138_VERSION)==UINT32_C(0x00010000) &&
           (a138_read(base,A138_CAPABILITIES)&7u)==7u;
}
static inline void a138_snapshot(uintptr_t base, uint32_t state[9]) {
    a138_write(base,A138_SNAPSHOT,1);
    for(size_t i=0;i<9;i++) state[i]=a138_read(base,A138_STATE_BASE+(uint32_t)i*4u);
}
/* Return 0 for empty, 1 for one complete frame. Resume an existing snapshot. */
static inline int a138_record_try_read(uintptr_t base, a138_record *record) {
    uint32_t status=a138_read(base,A138_RECORD_STATUS);
    if(!(status&1u)) {
        if(!(status&2u)) return 0;
        a138_write(base,A138_RECORD_POP,1);
    }
    record->sequence=a138_read(base,A138_RECORD_SEQUENCE);
    record->left=(int32_t)a138_read(base,A138_RECORD_LEFT);
    record->right=(int32_t)a138_read(base,A138_RECORD_RIGHT);
    a138_write(base,A138_RECORD_RELEASE,1);
    return 1;
}
/* Validate the entire input before clearing the previous upload; do not start. */
static inline int a138_score_load(uintptr_t base, const a138_cue *cues, size_t count) {
    if(!cues || count==0 || count>256) return 0;
    for(size_t i=1;i<count;i++) if(cues[i].frame<cues[i-1].frame) return 0;
    if(a138_read(base,A138_SCORE_STATUS)&1u) return 0;
    a138_write(base,A138_SCORE_CLEAR,1);
    for(size_t i=0;i<count;i++) {
        a138_write(base,A138_SCORE_ADDRESS,(uint32_t)i);
        a138_write(base,A138_SCORE_TIME,cues[i].frame);
        a138_write(base,A138_SCORE_MASK,cues[i].led_mask);
        a138_write(base,A138_SCORE_COMMIT,1);
    }
    a138_write(base,A138_SCORE_LENGTH,(uint32_t)count);
    return 1;
}
#endif
