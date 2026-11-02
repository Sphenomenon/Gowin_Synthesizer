/* Simulation adapter, never a firmware/profile input. Include the maintained
 * runtime unchanged to execute its private runtime_pass with the exact worker
 * four-pass scheduling policy. No text extraction or generated implementation.
 * Pair this file with pcm_media.c and the normal runtime dependencies; do not
 * also compile classic_runtime.c as a separate translation unit. */
#include "task3_phone_firmware_workload.h"
#include <stdlib.h>
#ifndef A138_WORKER_AUDIO_ONLY
#error "This simulation adapter requires the actual worker audio-only policy"
#endif
#ifndef A138_SINGLE_BLE_RECORDING
#error "This simulation adapter requires the actual W single recording policy"
#endif
#include "../../firmware/ae350/classic_runtime.c"

struct task3_phone_workload {
    struct task3_phone_callbacks cb;
    struct a138_classic_runtime runtime;
    struct a138_pcm_media pcm;
    struct a138_runtime_media actual;
    struct task3_phone_stats stats;
    uint32_t epoch;
    int inject_cap3;
};
static int remote_read(struct task3_phone_workload *p,unsigned lane,uint32_t off,uint32_t *v) {
    if(lane)++p->stats.clock_reads;else ++p->stats.pcm_reads;
    if(!p->cb.read(p->cb.context,lane,off,v))return 0;
    if(!lane&&off==8u) {
        p->stats.observed_caps=*v;
        if(p->inject_cap3) {
            if(*v!=UINT32_C(0x67))return 0;
            *v|=8u;
        }
    }
    return 1;
}
static int pcm_read_callback(void *ctx,uint32_t off,uint32_t *v) {
    return remote_read(ctx,0,off,v);
}
static int clock_read_callback(void *ctx,uint32_t off,uint32_t *v) {
    return remote_read(ctx,1,off,v);
}
static int remote_write(struct task3_phone_workload *p,unsigned lane,uint32_t off,uint32_t v) {
    if(lane)++p->stats.clock_writes;
    else {++p->stats.pcm_writes;if(off>=0x800u&&off<0x1000u)++p->stats.window_writes;}
    return p->cb.write(p->cb.context,lane,off,v);
}
static int pcm_write_callback(void *ctx,uint32_t off,uint32_t v) {
    return remote_write(ctx,0,off,v);
}
static int clock_write_callback(void *ctx,uint32_t off,uint32_t v) {
    return remote_write(ctx,1,off,v);
}
/* Local W HCI is deliberately idle. It supplies only the pre-established
 * controller identity and modeled clock; no fabricated HCI audio packets,
 * controller credits, pairing or security acceptance are being tested. */
static int idle_hci_read(void *ctx,uint32_t off,uint32_t *v) {
    struct task3_phone_workload *p=ctx;++p->stats.local_hci_reads;
    switch(off) {
    case 0:*v=UINT32_C(0x48434931);break;
    case 4:*v=UINT32_C(0x01040114);break;
    case 8:*v=17u;break;
    case 12:*v=p->epoch;break;
    case 64:*v=0;break;
    case 112:*v=276u|(276u<<16);break;
    case 120:*v=p->cb.now_ms(p->cb.context);break;
    default:return 0;
    }
    return 1;
}
static int idle_hci_write(void *ctx,uint32_t off,uint32_t v) {
    struct task3_phone_workload *p=ctx;++p->stats.local_hci_writes;
    if(off!=124u||v!=p->epoch)return 0;
    ++p->stats.fences;return 1;
}
static int observed_poll(void *ctx,uint32_t e,uint32_t g,uint32_t s,uint32_t rate,
        struct a138_runtime_audio_facts *f) {
    struct task3_phone_workload *p=ctx;++p->stats.media_polls;
    return p->actual.poll(p->actual.context,e,g,s,rate,f);
}
static enum a138_classic_submission observed_submit(void *ctx,uint32_t e,uint32_t g,uint32_t s,
        const struct a138_classic_frame *frame,const int16_t *pcm,const struct a138_sbc_pcm *decoded) {
    struct task3_phone_workload *p=ctx;++p->stats.submit_calls;
    uint64_t before=p->stats.window_writes;
    enum a138_classic_submission result=p->actual.submit(p->actual.context,e,g,s,frame,pcm,decoded);
    uint32_t n=(uint32_t)(p->stats.window_writes-before);
    if(n>p->stats.max_window_writes_per_submit)p->stats.max_window_writes_per_submit=n;
    if(result==A138_CLASSIC_REJECTED)++p->stats.rejected_submits;
    if(result==A138_CLASSIC_UNCERTAIN)++p->stats.uncertain_submits;
    return result;
}
static void observed_cancel(void *ctx,uint32_t e,uint32_t g,uint32_t s) {
    struct task3_phone_workload *p=ctx;++p->stats.cancels;
    p->actual.cancel(p->actual.context,e,g,s);
}
struct task3_phone_workload *task3_phone_workload_create(struct task3_phone_callbacks cb,
        uint32_t epoch,uint32_t generation,uint32_t stream,uint32_t rate,int inject_cap3) {
    if(!cb.read||!cb.write||!cb.now_ms||!epoch||!generation||!stream||
       (rate!=44100u&&rate!=48000u))return 0;
    struct task3_phone_workload *p=calloc(1,sizeof *p);if(!p)return 0;
    p->cb=cb;p->epoch=epoch;p->inject_cap3=!!inject_cap3;
    a138_pcm_media_init(&p->pcm,(struct a138_hci_bus){p,pcm_read_callback,pcm_write_callback},
        (a138_clock_bus){p,clock_read_callback,clock_write_callback});
    p->actual=a138_pcm_media_callbacks(&p->pcm);
    struct a138_runtime_media media={p,observed_poll,observed_submit,observed_cancel};
    a138_classic_runtime_init_session(&p->runtime,
        (struct a138_hci_bus){p,idle_hci_read,idle_hci_write},&media);
    struct a138_classic_runtime *r=&p->runtime;
    /* Explicit fixture-only pre-established session. These assignments are
     * never evidence that actual radio authentication or AVDTP completed. */
    if(a138_classic_begin(&r->classic,generation,generation,0x23u,276u)!=A138_CLASSIC_OK||
       a138_classic_security(&r->classic,generation,generation,1)!=A138_CLASSIC_OK||
       a138_security_start_session(&r->security,epoch,276u,&r->classic)!=A138_SECURITY_OK) {
        free(p);return 0;
    }
    r->started=1;r->security.ready=1;r->security.active=1;r->security.secure=1;
    r->security.generation=generation;r->security.last_generation=generation;r->security.handle=0x23u;
    r->classic.stream_epoch=stream;r->classic.state=A138_CLASSIC_OPEN;
    r->classic.format=(struct a138_classic_format){rate,2,8,16,0,2,53};
    r->observed_generation=generation;r->observed_stream=stream;
    return p;
}
void task3_phone_workload_destroy(struct task3_phone_workload *p) {free(p);}
int task3_phone_workload_enqueue128(struct task3_phone_workload *p,int16_t left,int16_t right) {
    if(!p||p->runtime.fault||!p->pcm.armed||!p->runtime.classic.ready||p->runtime.pcm_pending)return 0;
    struct a138_classic_runtime *r=&p->runtime;
    r->frame=(struct a138_classic_frame){.link_epoch=r->classic.generation,
        .stream_epoch=r->classic.stream_epoch,.format=r->classic.format};
    r->decoded=(struct a138_sbc_pcm){.stream_epoch=r->classic.stream_epoch,
        .rate_hz=r->classic.format.rate_hz,.frames=128,.scalar_samples=256,.channels=2,.valid=1};
    for(unsigned i=0;i<128u;i++){r->pcm[2u*i]=left;r->pcm[2u*i+1u]=right;}
    r->pcm_pending=1;r->pcm_started=p->cb.now_ms(p->cb.context);++p->stats.enqueued;return 1;
}
void task3_phone_workload_pump(struct task3_phone_workload *p) {
    if(!p)return;
    ++p->stats.pumps;
    for(unsigned i=0;i<4u;i++)runtime_pass(&p->runtime,i==0u);
}
void task3_phone_workload_cancel(struct task3_phone_workload *p) {
    if(!p)return;
    struct a138_classic_runtime *r=&p->runtime;
    (void)a138_classic_security(&r->classic,r->classic.link_epoch,r->classic.generation,0);
    r->security.secure=0;r->security.active=0;
    task3_phone_workload_pump(p);
}
void task3_phone_workload_snapshot(const struct task3_phone_workload *p,struct task3_phone_stats *out) {
    if(!p||!out)return;
    *out=p->stats;out->passes=p->runtime.passes;out->accepted=p->runtime.pcm_blocks;
    out->fault=p->runtime.fault;out->media_fault=p->pcm.fault;out->armed=p->pcm.armed;
    out->ready=p->runtime.classic.ready;out->pending=p->runtime.pcm_pending;
    out->offset=p->pcm.offset;out->next_sequence=p->pcm.next_sequence;
}
