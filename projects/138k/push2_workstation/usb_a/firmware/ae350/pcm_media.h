#ifndef A138_PCM_MEDIA_H
#define A138_PCM_MEDIA_H
#include "classic_runtime.h"
#include "audio_clock_service.h"
#define A138_PCM_BASE UINT32_C(0xf8060000)
/* Actual F806 bounded block-queue adapter. It never sets PL capability bits.
 * In particular implemented linear SRC(bit2) does not prove sustained/drift
 * readiness(bit3). Current PL bit3=0 leaves this adapter fail-closed, with no
 * ARM, rate request or source selection. DelayReporting remains unavailable.
 */
struct a138_pcm_media {
    struct a138_hci_bus bus;
    a138_clock_bus clock;
    a138_clock_ticket clock_ticket;
    uint32_t epoch,generation,stream,rate,physical_epoch,next_sequence;
    uint16_t offset,frames;
    uint8_t armed,slot,writing,fault,clock_pending;
};
void a138_pcm_media_init(struct a138_pcm_media *,struct a138_hci_bus,a138_clock_bus);
struct a138_runtime_media a138_pcm_media_callbacks(struct a138_pcm_media *);
#endif
