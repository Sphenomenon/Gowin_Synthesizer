#ifndef A138_CLASSIC_RUNTIME_H
#define A138_CLASSIC_RUNTIME_H
#include "hci_transport.h"
#include "classic_security.h"
#include "sbc_decoder_service.h"

/* Experimental actual cooperative CPU root. This composes the existing
 * owners; it does not own committed parameters, physical audio scheduling,
 * controller credits, UART/H5 or persistent storage. The firmware binding
 * default binding has no durable bond backend and remains fail-closed. W-DEMO
 * explicitly selects session-only SSP and the maintained physical media owner.
 */
enum { A138_RUNTIME_NO_FAULT,A138_RUNTIME_TRANSPORT_FAULT,
    A138_RUNTIME_SECURITY_FAULT,A138_RUNTIME_RESPONSE_FAULT,
    A138_RUNTIME_RX_TIMEOUT,A138_RUNTIME_MEDIA_FAULT,A138_RUNTIME_DECODE_FAULT };
struct a138_runtime_audio_facts {
    uint32_t controller_epoch,generation,stream_epoch,rate_hz,delay_tenths_ms;
    uint8_t ready,delay_valid,drift_managed;
};
struct a138_runtime_media {
    void *context;
    /* Actual bounded downstream owner, not inferred FIFO fill. poll returns1
     * only for a coherent exact-context snapshot,0 if not ready,-1 on fault.
     * It must revoke and flush accepted old PCM on generation/stream changes.
     * ready proves actual selected rate; drift_managed proves that downstream
     * clock recovery handles permanent phone/local frequency difference.
     * delay_valid binds measured stable baseband-to-presentation delay.
     */
    int (*poll)(void *,uint32_t,uint32_t,uint32_t,uint32_t,struct a138_runtime_audio_facts *);
    /* ACCEPTED requires an irreversible private copy of every PCM frame;
     * REJECTED consumes nothing; UNCERTAIN fences, never automatically retries.
     * No backend may block the actual audio sample schedule. */
    enum a138_classic_submission (*submit)(void *,uint32_t,uint32_t,uint32_t,
        const struct a138_classic_frame *,const int16_t *,const struct a138_sbc_pcm *);
    void (*cancel)(void *,uint32_t,uint32_t,uint32_t);
};
struct a138_classic_runtime {
    struct a138_hci_transport transport;
    struct a138_security security;
    struct a138_classic_service classic;
    struct a138_sbc_decoder decoder;
    struct a138_bond_store store;
    struct a138_runtime_media media;
    struct a138_classic_frame frame;
    struct a138_sbc_pcm decoded;
    int16_t pcm[A138_SBC_MAX_PCM_SAMPLES];
    uint32_t passes,rx_packets,rx_dropped,pcm_blocks,rx_wait_started,pcm_started;
    uint32_t observed_generation,observed_stream;
    uint32_t acl_header;
    uint16_t acl_diagnostic;
    uint8_t enabled,started,fault,fence_sent,accepted_notified,done_notified;
    uint8_t rx_waiting,pcm_pending,media_bound,session_only;
};
void a138_classic_runtime_init(struct a138_classic_runtime *,struct a138_hci_bus,
    const struct a138_bond_store *,const struct a138_runtime_media *);
/* W-DEMO only: explicit nonpersistent SSP policy, requiring a real complete
 * downstream media adapter. The default constructor still requires a durable
 * store and never silently falls back to volatile pairing. */
void a138_classic_runtime_init_session(struct a138_classic_runtime *,struct a138_hci_bus,
    const struct a138_runtime_media *);
/* One fixed transport slice, one RX dispatch, one security pump and at most
 * one SBC frame decode per pass. Tick is always before service observations.
 * Each downstream callback and bus access must itself be bounded. */
void a138_classic_runtime_step(struct a138_classic_runtime *);
/* Existing W diagnostic registers only. Header is the actual four HCI ACL
 * bytes in little-endian order, or CPU1 before the first ACL. Before any ACL,
 * an actual security close instead exposes its sticky D4/FC close_context.
 * Status is
 * [3:0] Classic result, [4] started, [5] active, [6] secure, [7] exact security
 * epoch/generation, [15:8] received packet count modulo256. BUSY retries do
 * not increment the count. Reading this snapshot has no transport effects. */
void a138_classic_runtime_diagnostic(const struct a138_classic_runtime *,uint32_t *,uint16_t *);
void a138_classic_runtime_firmware_init(void);
void a138_classic_runtime_firmware_pump(void);
void a138_classic_runtime_firmware_diagnostic(uint32_t *,uint16_t *);
#endif
