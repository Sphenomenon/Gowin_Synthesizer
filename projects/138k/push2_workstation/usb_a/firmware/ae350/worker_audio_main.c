/* Explicit W audio-only root. No framebuffer, graph UI, recorder, cue,
 * background DDR test, or synthetic audio command is linked into this image.
 * The PL sample schedule and USB/25K controls run independently of this pump. */
#include <stdint.h>
#include "classic_runtime.h"

#if !defined(A138_CLASSIC_RUNTIME) || !defined(A138_WORKER_AUDIO_ONLY)
#error "worker_audio_main requires the explicit audio-only Classic composition"
#endif

void services_main(void) {
    volatile uint32_t *const diagnostic=(volatile uint32_t *)UINT32_C(0xf8000000);
    uint32_t heartbeat=0;
    a138_classic_runtime_firmware_init();
    diagnostic[1]=UINT32_C(0x41554457); /* AUDW: pump entered, not radio acceptance. */
    for(;;) {
        uint32_t acl_header;
        uint16_t acl_status;
        a138_classic_runtime_firmware_pump();
        a138_classic_runtime_firmware_diagnostic(&acl_header,&acl_status);
        diagnostic[0]=acl_header;
        diagnostic[2]=(++heartbeat<<16)|acl_status;
    }
}
