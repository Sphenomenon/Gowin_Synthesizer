#include "pcm_media.h"
#include <string.h>
enum { ID=0,VERSION=4,CAPS=8,STATUS=12,FREE=20,EXPECTED_SEQUENCE=28,
    KEY_EPOCH=32,KEY_GENERATION=36,KEY_STREAM=40,KEY_RATE=44,KEY_PHYSICAL=48,
    SLOT=52,FRAMES=56,SEQUENCE=60,COMMAND=64,COMMAND_ID=68,ACTIVE_SOURCE=76,
    PREFILL=100,RATE=112,PHYSICAL_EPOCH=116,LIVE_GENERATION=120,LIVE_EPOCH=124,
    ACTIVE_STREAM=128,ARM=1,COMMIT=2,SELECT_BT=3,CANCEL=5,PCM_SLICE=16 };
static int pcm_read(struct a138_pcm_media *d,unsigned off,uint32_t *v) {
    if(!d->bus.read(d->bus.context,off,v)){d->fault=1;return 0;}return 1;
}
static int pcm_write(struct a138_pcm_media *d,unsigned off,uint32_t v) {
    if(!d->bus.write(d->bus.context,off,v)){d->fault=1;return 0;}return 1;
}
static int pcm_key(struct a138_pcm_media *d) {
    return pcm_write(d,KEY_EPOCH,d->epoch)&&pcm_write(d,KEY_GENERATION,d->generation)&&
        pcm_write(d,KEY_STREAM,d->stream)&&pcm_write(d,KEY_RATE,d->rate)&&
        pcm_write(d,KEY_PHYSICAL,d->physical_epoch);
}
static int pcm_command(struct a138_pcm_media *d,unsigned command) {
    uint32_t before,after;
    if(!pcm_read(d,COMMAND_ID,&before)||before==UINT32_MAX||
       !pcm_write(d,COMMAND,command)||!pcm_read(d,COMMAND_ID,&after)||after!=before+1u) {
        d->fault=1;return 0;
    }
    return 1;
}
static void pcm_cancel(void *context,uint32_t epoch,uint32_t generation,uint32_t stream) {
    struct a138_pcm_media *d=context;uint32_t e,g,s;
    if(!d||!d->armed||d->epoch!=epoch||d->generation!=generation||d->stream!=stream)return;
    /* A stale CPU context must never cancel a new owner. Actual PL loss has
     * already fenced/flushed the old queue independently of this callback. */
    if(!d->fault&&pcm_read(d,LIVE_EPOCH,&e)&&pcm_read(d,LIVE_GENERATION,&g)&&
       pcm_read(d,ACTIVE_STREAM,&s)&&e==epoch&&g==generation&&s==stream) {
        if(pcm_key(d))(void)pcm_command(d,CANCEL);
    }
    d->armed=d->writing=0;
}
static int pcm_clock(struct a138_pcm_media *d,uint32_t rate,uint32_t actual) {
    if(d->clock_pending) {
        a138_clock_status status={0};
        a138_clock_result r=a138_clock_poll(&d->clock,&d->clock_ticket,&status);
        if(r==A138_CLK_PENDING)return 0;
        if(r!=A138_CLK_APPLIED){d->fault=1;return -1;}
        d->clock_pending=0;
    }
    if(actual==rate)return 1;
    if(a138_clock_probe(&d->clock)!=A138_CLK_SUBMITTED){d->fault=1;return -1;}
    a138_clock_result submitted=a138_clock_submit(&d->clock,rate==44100u?A138_CLK_44100:A138_CLK_48000,&d->clock_ticket);
    if(submitted==A138_CLK_PENDING||submitted==A138_CLK_UNARMED)return 0; /* No command write occurred. */
    if(submitted!=A138_CLK_SUBMITTED){d->fault=1;return -1;}
    d->clock_pending=1;return 0;
}
static int pcm_poll(void *context,uint32_t epoch,uint32_t generation,uint32_t stream,
        uint32_t rate,struct a138_runtime_audio_facts *facts) {
    struct a138_pcm_media *d=context;uint32_t id,version,caps,status,e,g,physical,actual,s,prefill,source,e2,g2,p2;
    if(!d||!facts||d->fault)return -1;
    if(!pcm_read(d,ID,&id)||!pcm_read(d,VERSION,&version)||!pcm_read(d,CAPS,&caps)||
       !pcm_read(d,STATUS,&status)||!pcm_read(d,LIVE_EPOCH,&e)||!pcm_read(d,LIVE_GENERATION,&g)||
       !pcm_read(d,PHYSICAL_EPOCH,&physical)||!pcm_read(d,RATE,&actual)||!pcm_read(d,ACTIVE_STREAM,&s))return -1;
    if(!pcm_read(d,LIVE_EPOCH,&e2)||!pcm_read(d,LIVE_GENERATION,&g2)||!pcm_read(d,PHYSICAL_EPOCH,&p2))return -1;
    if(e!=e2||g!=g2||physical!=p2)return 0;
    if(id!=UINT32_C(0x50434d31)||version!=UINT32_C(0x10000)||(caps&UINT32_C(0x63))!=UINT32_C(0x63)||
       (caps&~UINT32_C(0x7f))||(caps&16u)||((caps&8u)&&!(caps&4u))){d->fault=1;return -1;}
    *facts=(struct a138_runtime_audio_facts){.controller_epoch=e,.generation=g,.stream_epoch=s,.rate_hz=actual};
    if(!(caps&8u))return 1; /* No sustained/drift acceptance: no side effects. */
    if(!epoch||!generation||!stream||e!=epoch||g!=generation||(rate!=44100u&&rate!=48000u))return 0;
    if(d->armed&&(d->epoch!=epoch||d->generation!=generation||d->stream!=stream||d->rate!=rate)) {
        pcm_cancel(d,d->epoch,d->generation,d->stream);return d->fault?-1:0;
    }
    /* A live armed stream failure fences this CPU observer. After observer
     * reconstruction, PL may retain an old owner's sticky failure: only PL's
     * full-key/strict-stream ARM validation may admit a fresh owner and clear
     * that failure. A rejected or uncertain ARM still faults this observer. */
    if(d->armed&&(status&8u)){d->fault=1;return -1;}
    if((status&192u)!=192u)return 0;
    if(!d->armed) {
        if(status&48u)return 0;
        if(!pcm_read(d,ACTIVE_SOURCE,&source))return -1;
        if(source!=0u)return 0;
        int clock=pcm_clock(d,rate,actual);if(clock<=0)return clock;
        /* Re-read the real physical context after a rate-ticket completion;
         * later changes are independently checked at actual ARM/COMMIT. */
        if(!pcm_read(d,RATE,&actual)||!pcm_read(d,PHYSICAL_EPOCH,&physical))return -1;
        if(actual!=rate||!physical)return 0;
        d->epoch=epoch;d->generation=generation;d->stream=stream;d->rate=rate;d->physical_epoch=physical;
        if(!pcm_key(d)||!pcm_command(d,ARM))return -1;
        d->armed=1;d->slot=0;d->next_sequence=0;d->writing=0;return 0;
    }
    if(e!=d->epoch||g!=d->generation||s!=d->stream||actual!=d->rate||physical!=d->physical_epoch||!(status&1u)) {
        d->fault=1;return -1;
    }
    facts->ready=1;facts->drift_managed=1;
    if(!(status&2u)&&(status&4u)&&!(status&48u)) {
        if(!pcm_read(d,PREFILL,&prefill)||prefill!=256u||!pcm_key(d)||!pcm_command(d,SELECT_BT))return -1;
    }
    return 1;
}
static enum a138_classic_submission pcm_submit(void *context,uint32_t epoch,uint32_t generation,
        uint32_t stream,const struct a138_classic_frame *frame,const int16_t *pcm,
        const struct a138_sbc_pcm *decoded) {
    struct a138_pcm_media *d=context;uint32_t free_mask,sequence;
    if(!d||d->fault||!d->armed||epoch!=d->epoch||generation!=d->generation||stream!=d->stream||
       !frame||!pcm||!decoded||!decoded->valid||decoded->stream_epoch!=stream||decoded->rate_hz!=d->rate||
       frame->link_epoch!=generation||frame->stream_epoch!=stream||
       decoded->frames<1u||decoded->frames>128u||decoded->channels<1u||decoded->channels>2u||
       decoded->scalar_samples!=decoded->frames*decoded->channels||d->next_sequence==UINT32_MAX)
        return A138_CLASSIC_UNCERTAIN;
    if(!d->writing) {
        if(!pcm_read(d,FREE,&free_mask)||!pcm_read(d,EXPECTED_SEQUENCE,&sequence))return A138_CLASSIC_UNCERTAIN;
        if(sequence!=d->next_sequence){d->fault=1;return A138_CLASSIC_UNCERTAIN;}
        if(!(free_mask&(1u<<d->slot)))return A138_CLASSIC_REJECTED;
        d->frames=decoded->frames;d->offset=0;d->writing=1;
    }else if(d->frames!=decoded->frames){d->fault=1;return A138_CLASSIC_UNCERTAIN;}
    unsigned n=d->frames-d->offset;if(n>PCM_SLICE)n=PCM_SLICE;
    for(unsigned i=0;i<n;i++) {
        unsigned at=d->offset,channels=decoded->channels;
        uint16_t left=(uint16_t)pcm[at*channels],right=(uint16_t)pcm[at*channels+(channels==2u)];
        if(!pcm_write(d,0x800u+(unsigned)d->slot*512u+at*4u,(uint32_t)left|((uint32_t)right<<16)))
            return A138_CLASSIC_UNCERTAIN;
        ++d->offset;
    }
    if(d->offset!=d->frames)return A138_CLASSIC_REJECTED;
    if(!pcm_key(d)||!pcm_write(d,SLOT,d->slot)||!pcm_write(d,FRAMES,d->frames)||
       !pcm_write(d,SEQUENCE,d->next_sequence)||!pcm_command(d,COMMIT))return A138_CLASSIC_UNCERTAIN;
    ++d->next_sequence;d->slot=(uint8_t)((d->slot+1u)&3u);d->writing=0;return A138_CLASSIC_ACCEPTED;
}
void a138_pcm_media_init(struct a138_pcm_media *d,struct a138_hci_bus bus,a138_clock_bus clock) {
    if(!d)return;
    memset(d,0,sizeof *d);d->bus=bus;d->clock=clock;
    if(!bus.read||!bus.write||!clock.read||!clock.write)d->fault=1;
}
struct a138_runtime_media a138_pcm_media_callbacks(struct a138_pcm_media *d) {
    return (struct a138_runtime_media){d,pcm_poll,pcm_submit,pcm_cancel};
}
