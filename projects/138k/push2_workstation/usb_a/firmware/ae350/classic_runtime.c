#include "classic_runtime.h"
#ifndef A138_WORKER_AUDIO_ONLY
#include "ble_business_owner.h"
#endif
#include "pcm_media.h"
#include <string.h>

enum { RX_WAIT_MS=100,PCM_WAIT_MS=100,CLASSIC_FENCE=124 };
static void cancel_media(struct a138_classic_runtime *r) {
    if(r->media_bound&&r->media.cancel)
        r->media.cancel(r->media.context,r->transport.epoch,r->observed_generation,r->observed_stream);
    r->media_bound=0;r->pcm_pending=0;
    if(r->decoder.active)(void)a138_sbc_cancel(&r->decoder,r->decoder.last_epoch);
    memset(r->pcm,0,sizeof r->pcm);memset(&r->decoded,0,sizeof r->decoded);
}
static void fail_runtime(struct a138_classic_runtime *r,uint8_t why) {
    if(!r->fault)r->fault=why;
    if(r->started)a138_security_observer_reset(&r->security);
    cancel_media(r);
    /* An exact-epoch Classic fence only. It cannot reset the controller or
     * refund either shared physical packet ledger. A failed write is not
     * retried because its side effect may already have happened. */
    if(!r->fence_sent&&r->transport.epoch&&r->transport.fault!=A138_HCI_FAULT_IDENTITY) {
        r->fence_sent=1;
        (void)r->transport.bus.write(r->transport.bus.context,CLASSIC_FENCE,r->transport.epoch);
    }
}
void a138_classic_runtime_init(struct a138_classic_runtime *r,struct a138_hci_bus bus,
        const struct a138_bond_store *store,const struct a138_runtime_media *media) {
    if(!r)return;
    memset(r,0,sizeof *r);a138_hci_init(&r->transport,bus);
    a138_security_init(&r->security);a138_classic_init(&r->classic);a138_sbc_init(&r->decoder);
    if(store&&store->load&&store->replace_atomic&&store->delete_atomic) {
        r->store=*store;r->enabled=1;
    }
    if(media&&media->poll&&media->submit&&media->cancel)r->media=*media;
}
__attribute__((noinline))
void a138_classic_runtime_init_session(struct a138_classic_runtime *r,struct a138_hci_bus bus,
        const struct a138_runtime_media *media) {
    a138_classic_runtime_init(r,bus,0,media);
    if(r&&r->media.poll&&r->media.submit&&r->media.cancel){r->session_only=1;r->enabled=1;}
}
static void notify_tx(struct a138_classic_runtime *r) {
    struct a138_hci_transport *t=&r->transport;
    enum a138_security_result sr=A138_SECURITY_OK;
    enum a138_classic_result cr=A138_CLASSIC_OK;
    if(!t->tx_phase)return;
    if((t->accepted&&!r->accepted_notified)||t->rejected||t->uncertain) {
        enum a138_classic_submission result=t->uncertain?A138_CLASSIC_UNCERTAIN:
            t->rejected?A138_CLASSIC_REJECTED:A138_CLASSIC_ACCEPTED;
        if(t->tx_type==A138_HCI_COMMAND)
            sr=a138_security_tx_result(&r->security,t->epoch,t->source_token,result);
        else cr=a138_classic_tx_result(&r->classic,t->tx_generation,t->tx_generation,t->source_token,result);
        if(result==A138_CLASSIC_ACCEPTED)r->accepted_notified=1;
        if(sr!=A138_SECURITY_OK||(cr!=A138_CLASSIC_OK&&cr!=A138_CLASSIC_STALE&&cr!=A138_CLASSIC_INACTIVE)) {
            fail_runtime(r,A138_RUNTIME_SECURITY_FAULT);return;
        }
    }
    if(t->transport_done&&!r->done_notified) {
        if(t->tx_type==A138_HCI_COMMAND&&
           a138_security_transport_done(&r->security,t->epoch,t->source_token)!=A138_SECURITY_OK) {
            fail_runtime(r,A138_RUNTIME_RESPONSE_FAULT);return;
        }
        r->done_notified=1;
    }
}
static void rx_dispatch(struct a138_classic_runtime *r) {
    struct a138_hci_transport *t=&r->transport;
    const struct a138_hci_rx *p=a138_hci_rx_peek(t);
    if(!p)return;
    if(!r->started) {
        /* No durable backend means no scan/auth/security grants. Unexpected
         * copies can be discarded without changing hardware receive credits. */
        ++r->rx_dropped;
    }else if(p->response) {
        if(t->tx_type!=A138_HCI_COMMAND||!t->accepted||p->token!=t->tx_token||
           a138_security_response(&r->security,p->epoch,p->owner,p->data,p->bytes)!=A138_SECURITY_OK||
           !a138_hci_response_delivered(t,p->token)) {
            fail_runtime(r,A138_RUNTIME_RESPONSE_FAULT);return;
        }
    }else if(p->retired) {
        ++r->rx_dropped;
    }else if(p->type==A138_HCI_EVENT) {
        enum a138_security_result status=a138_security_event(&r->security,p->epoch,
            p->generation,t->available,p->data,p->bytes);
        if(status==A138_SECURITY_FENCED||status==A138_SECURITY_ARGUMENT||status==A138_SECURITY_MALFORMED) {
            fail_runtime(r,A138_RUNTIME_SECURITY_FAULT);return;
        }
    }else {
        enum a138_classic_result status=a138_security_classic_acl(&r->security,p->epoch,
            p->generation,p->data,p->bytes);
        if(status==A138_CLASSIC_BUSY) {
            if(!r->rx_waiting){r->rx_wait_started=t->now_ms;r->rx_waiting=1;}
            else if((uint32_t)(t->now_ms-r->rx_wait_started)>=RX_WAIT_MS)
                fail_runtime(r,A138_RUNTIME_RX_TIMEOUT);
            return;
        }
        if(status==A138_CLASSIC_FENCED){fail_runtime(r,A138_RUNTIME_SECURITY_FAULT);return;}
    }
    if(a138_hci_rx_release(t,p->epoch,p->ticket)){++r->rx_packets;r->rx_waiting=0;}
    else fail_runtime(r,A138_RUNTIME_TRANSPORT_FAULT);
}
static void offer_tx(struct a138_classic_runtime *r) {
    struct a138_hci_transport *t=&r->transport;
    if(t->tx_phase)return;
    struct a138_security_command command;
    if(a138_security_tx_peek(&r->security,&command)==A138_SECURITY_OK) {
        if(a138_hci_offer(t,A138_HCI_COMMAND,command.generation,command.token,command.data,command.bytes))
            r->accepted_notified=r->done_notified=0;
        return;
    }
    struct a138_classic_tx acl;
    if(a138_classic_tx_peek(&r->classic,&acl)==A138_CLASSIC_OK&&
       a138_hci_offer(t,A138_HCI_ACL,acl.generation,acl.token,acl.data,acl.bytes))
        r->accepted_notified=r->done_notified=0;
}
static void media_step(struct a138_classic_runtime *r,uint8_t allow_decode) {
    struct a138_classic_service *c=&r->classic;
    if(!c->active||!c->security_ready||c->generation!=r->observed_generation||
       c->stream_epoch!=r->observed_stream) {
        cancel_media(r);r->observed_generation=c->generation;r->observed_stream=c->stream_epoch;
    }
    if(!c->active||!c->security_ready||!r->media.poll)return;
    struct a138_runtime_audio_facts f={0};
    int result=r->media.poll(r->media.context,r->transport.epoch,c->generation,c->stream_epoch,c->format.rate_hz,&f);
    if(result<0){fail_runtime(r,A138_RUNTIME_MEDIA_FAULT);return;}
    if(!result||f.controller_epoch!=r->transport.epoch||f.generation!=c->generation||f.stream_epoch!=c->stream_epoch||
       f.rate_hz!=c->format.rate_hz||!f.ready||!f.drift_managed) {
        if(c->ready)(void)a138_classic_audio_ready(c,c->generation,c->generation,c->format.rate_hz,0);
        cancel_media(r);return;
    }
    r->media_bound=1;
    if(f.delay_valid) {
        enum a138_classic_result status=a138_classic_delay_update(c,c->generation,c->generation,f.delay_tenths_ms);
        if(status!=A138_CLASSIC_OK&&status!=A138_CLASSIC_BUSY){fail_runtime(r,A138_RUNTIME_MEDIA_FAULT);return;}
    }
    if(c->state!=A138_CLASSIC_IDLE&&
       a138_classic_audio_ready(c,c->generation,c->generation,f.rate_hz,1)!=A138_CLASSIC_OK) {
        fail_runtime(r,A138_RUNTIME_MEDIA_FAULT);return;
    }
    if(r->pcm_pending) {
        enum a138_classic_submission submitted=r->media.submit(r->media.context,r->transport.epoch,c->generation,
            c->stream_epoch,&r->frame,r->pcm,&r->decoded);
        if(submitted==A138_CLASSIC_ACCEPTED){r->pcm_pending=0;++r->pcm_blocks;}
        else if(submitted!=A138_CLASSIC_REJECTED||
            (uint32_t)(r->transport.now_ms-r->pcm_started)>=PCM_WAIT_MS)
            fail_runtime(r,A138_RUNTIME_MEDIA_FAULT);
        return;
    }
    if(!allow_decode||a138_classic_frame_pop(c,&r->frame)!=A138_CLASSIC_OK)return;
    const struct a138_classic_format *cf=&r->frame.format;
    if(r->decoder.last_epoch!=r->frame.stream_epoch) {
        struct a138_sbc_format format={cf->rate_hz,cf->mode,cf->subbands,cf->blocks,
            cf->allocation,cf->min_bitpool,cf->max_bitpool};
        if(a138_sbc_begin(&r->decoder,r->frame.stream_epoch,&format)!=A138_SBC_OK) {
            fail_runtime(r,A138_RUNTIME_DECODE_FAULT);return;
        }
    }
    if(a138_sbc_decode(&r->decoder,r->frame.stream_epoch,r->frame.data,r->frame.bytes,
        r->pcm,A138_SBC_MAX_PCM_SAMPLES,&r->decoded)!=A138_SBC_OK||!r->decoded.valid) {
        fail_runtime(r,A138_RUNTIME_DECODE_FAULT);return;
    }
    r->pcm_pending=1;r->pcm_started=r->transport.now_ms;
}
static void runtime_pass(struct a138_classic_runtime *r,uint8_t allow_decode) {
    if(!r||r->fault)return;
    ++r->passes;a138_hci_step(&r->transport);
    if(r->transport.fault){fail_runtime(r,A138_RUNTIME_TRANSPORT_FAULT);return;}
    if(!r->transport.ready)return;
    if(r->enabled&&!r->started) {
        enum a138_security_result started=r->session_only?
            a138_security_start_session(&r->security,r->transport.epoch,r->transport.br_limit,&r->classic):
            a138_security_start(&r->security,r->transport.epoch,r->transport.br_limit,&r->classic,&r->store);
        if(started!=A138_SECURITY_OK){fail_runtime(r,A138_RUNTIME_SECURITY_FAULT);return;}
        r->started=1;
    }
    if(r->started) {
        if(a138_security_tick(&r->security,r->transport.epoch,r->transport.now_ms)!=A138_SECURITY_OK) {
            fail_runtime(r,A138_RUNTIME_SECURITY_FAULT);return;
        }
        notify_tx(r);if(r->fault)return;
    }
    rx_dispatch(r);if(r->fault)return;
    if(r->started) {
        media_step(r,allow_decode);if(r->fault)return;
        if(a138_security_pump(&r->security)==A138_SECURITY_FENCED) {
            fail_runtime(r,A138_RUNTIME_SECURITY_FAULT);return;
        }
        if(r->transport.rejected||(r->transport.transport_done&&r->transport.response_done))
            if(!a138_hci_tx_retire(&r->transport)){fail_runtime(r,A138_RUNTIME_TRANSPORT_FAULT);return;}
        offer_tx(r);
    }
}
void a138_classic_runtime_step(struct a138_classic_runtime *r) {runtime_pass(r,1);}
/* Actual firmware root. W-DEMO explicitly uses NoBonding/session-only SSP;
 * other profiles retain the disabled durable-backend gate. Neither policy
 * fabricates physical audio, clock-recovery or presentation-delay facts. */
static struct a138_classic_runtime firmware_runtime;
static struct a138_pcm_media firmware_media;
/* These are unavailable-backend callbacks, not RAM persistence. They install a
 * bounded fail-closed target closure, while enabled remains explicitly zero. */
#ifndef A138_SINGLE_BLE_RECORDING
static enum a138_bond_result unavailable_load(void *p,const uint8_t peer[6],struct a138_bond *out) {
    (void)p;(void)peer;(void)out;return A138_BOND_ERROR;
}
static enum a138_bond_result unavailable_replace(void *p,const struct a138_bond *bond,uint32_t revision) {
    (void)p;(void)bond;(void)revision;return A138_BOND_ERROR;
}
static enum a138_bond_result unavailable_delete(void *p,const uint8_t peer[6],uint32_t revision) {
    (void)p;(void)peer;(void)revision;return A138_BOND_ERROR;
}
#endif
void a138_classic_runtime_firmware_init(void) {
#ifndef A138_SINGLE_BLE_RECORDING
    struct a138_bond_store unavailable={0,unavailable_load,unavailable_replace,unavailable_delete};
#endif
    a138_pcm_media_init(&firmware_media,a138_hci_mmio_bus(A138_PCM_BASE),a138_clock_mmio_bus(A138_CLOCK_BASE));
    struct a138_runtime_media media=a138_pcm_media_callbacks(&firmware_media);
#ifdef A138_SINGLE_BLE_RECORDING
    a138_classic_runtime_init_session(&firmware_runtime,a138_hci_mmio_bus(A138_HCI_BASE),&media);
#else
    a138_classic_runtime_init(&firmware_runtime,a138_hci_mmio_bus(A138_HCI_BASE),&unavailable,&media);
    firmware_runtime.enabled=0; /* No durable backend has been implemented. */
#endif
#ifndef A138_WORKER_AUDIO_ONLY
    a138_ble_business_firmware_init();
#endif
}
void a138_classic_runtime_firmware_pump(void) {
    /* Four fixed transport slices between UI jobs, one decode in total.
     * This is a work bound, not a measured CPU/DDR service-period guarantee. */
    for(unsigned i=0;i<4u;i++)runtime_pass(&firmware_runtime,i==0u);
#ifndef A138_WORKER_AUDIO_ONLY
    a138_ble_business_firmware_pump();
#endif
}
