/* External link/stack budget harness only. Not a transport implementation.
 * Volatile inputs keep real API paths live; never install this as production. */
#include "classic_service.h"
#include "sbc_decoder_service.h"

struct budget_pcm_slot { int16_t pcm[256]; struct a138_sbc_pcm result; };
struct a138_classic_service budget_classic;
struct a138_sbc_decoder budget_decoder;
struct a138_classic_frame budget_frame;
struct a138_classic_tx budget_tx;
struct budget_pcm_slot budget_pcm[4];
uint8_t budget_packet[A138_CLASSIC_ACL_BYTES];
volatile uint32_t budget_operation,budget_link_epoch,budget_generation,budget_rate;
volatile uint32_t budget_input_bytes,budget_status,budget_decode_status,budget_slot;
volatile uint32_t budget_now_ms,budget_delay_tenths_ms;

void a138_combined_budget_init(void) {
    a138_classic_init(&budget_classic);
    a138_sbc_init(&budget_decoder);
}

void a138_combined_budget_step(void) {
    uint32_t link=budget_link_epoch,generation=budget_generation;
    uint16_t bytes=(uint16_t)(budget_input_bytes % (sizeof budget_packet+1u));
    /* Model a caller-owned monotonic clock input, never a measured delay.
     * The real owner must invoke tick before other methods each service pass. */
    budget_status=a138_classic_tick(&budget_classic,link,generation,budget_now_ms);
    switch(budget_operation) {
    case 1: budget_status=a138_classic_begin(&budget_classic,link,generation,1,276);break;
    case 2: budget_status=a138_classic_event(&budget_classic,link,generation,budget_packet,bytes);break;
    case 3: budget_status=a138_classic_acl(&budget_classic,link,generation,budget_packet,bytes);break;
    case 4:
        budget_status=a138_classic_tx_peek(&budget_classic,&budget_tx);
        if(budget_status==A138_CLASSIC_OK)
            budget_status=a138_classic_tx_result(&budget_classic,link,generation,budget_tx.token,
                (enum a138_classic_submission)(budget_input_bytes % 3u));
        break;
    case 5: budget_status=a138_classic_audio_ready(&budget_classic,link,generation,budget_rate,1);break;
    case 6: budget_status=a138_classic_cancel(&budget_classic,link,generation);break;
    case 7: budget_decode_status=a138_sbc_cancel(&budget_decoder,budget_decoder.last_epoch);break;
    case 8: budget_status=a138_classic_delay_update(&budget_classic,link,generation,budget_delay_tenths_ms);break;
    default: break;
    }
    if(a138_classic_frame_pop(&budget_classic,&budget_frame)==A138_CLASSIC_OK) {
        struct a138_classic_format *f=&budget_frame.format;
        if(budget_decoder.last_epoch!=budget_frame.stream_epoch) {
            struct a138_sbc_format format={f->rate_hz,f->mode,f->subbands,f->blocks,
                f->allocation,f->min_bitpool,f->max_bitpool};
            budget_decode_status=a138_sbc_begin(&budget_decoder,budget_frame.stream_epoch,&format);
        }
        struct budget_pcm_slot *slot=&budget_pcm[budget_slot & 3u];
        budget_decode_status=a138_sbc_decode(&budget_decoder,budget_frame.stream_epoch,
            budget_frame.data,budget_frame.bytes,slot->pcm,256,&slot->result);
        if(budget_decode_status==A138_SBC_OK)budget_slot++;
    }
}
