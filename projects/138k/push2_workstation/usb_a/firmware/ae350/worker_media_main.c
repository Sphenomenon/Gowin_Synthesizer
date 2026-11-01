/* Explicit task3 W-media root: real Classic/HCI/SBC/PCM plus the one C/BLE
 * recording owner. No graph UI, framebuffer or R00 recording root is called.
 * Classic already performs a bounded business-owner pump; do not call it twice.
 */
#include <stdint.h>
#include "classic_runtime.h"
#include "ble_business_owner.h"

#if !defined(A138_CLASSIC_RUNTIME) || !defined(A138_WORKER_MEDIA) || \
    !defined(A138_BLE_BUSINESS) || !defined(A138_SINGLE_BLE_RECORDING)
#error "worker_media_main requires the explicit single-owner Classic W-media role"
#endif
#ifdef A138_WORKER_AUDIO_ONLY
#error "headless media must retain the C/BLE business owner"
#endif
#if A138_BLE_RECORD_CAPACITY_FRAMES != 2880000u
#error "task3 W-media requires the matching physical 60-second recording capacity"
#endif

void services_main(void) {
    volatile uint32_t *const diagnostic=(volatile uint32_t *)UINT32_C(0xf8000000);
    uint32_t heartbeat=0;
    a138_classic_runtime_firmware_init();
    diagnostic[1]=UINT32_C(0x4d454457); /* MEDW: pump entered, not hardware acceptance. */
    for(;;) {
        a138_classic_runtime_firmware_pump();
        diagnostic[2]=++heartbeat;
    }
}
