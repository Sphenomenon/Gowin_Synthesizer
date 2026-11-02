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
#ifdef A138_TASK3_PHONE_BATCH
    /* Explicit paired-v3 state. Legacy init/callbacks never use this path.
     * The reply is published only after all eight words pass identity checks.
     * Accepted command ID and source-history applied ID are separate facts. */
    uint32_t paired_reply[8],paired_token,paired_next_request,paired_capture;
    uint32_t paired_command_id,paired_applied_id,paired_pending_id;
    uint8_t paired,paired_probed,paired_have_reply,paired_reuse,paired_fresh;
#endif
};
void a138_pcm_media_init(struct a138_pcm_media *,struct a138_hci_bus,a138_clock_bus);
#ifdef A138_TASK3_PHONE_BATCH
/* Explicit paired phone-batch-v3 virtual page (0x100..0x15c). This never
 * selects the path for existing single-board/default callers. The M owner
 * supplies actual capability and full-context match facts; no local grant. */
void a138_pcm_media_init_paired(struct a138_pcm_media *,struct a138_hci_bus,a138_clock_bus);
#endif
struct a138_runtime_media a138_pcm_media_callbacks(struct a138_pcm_media *);
#endif
