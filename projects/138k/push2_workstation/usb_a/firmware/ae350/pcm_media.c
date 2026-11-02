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
#ifdef A138_TASK3_PHONE_BATCH
/* Paired-v3 is a new explicit transport. The legacy register operations above
 * deliberately retain their original behavior and command-completion scope. */
enum { B_ID=0x100,B_VERSION=0x104,B_AVAILABLE=0x108,B_KEY=0x110,
    B_COMMAND=0x130,B_REPLY=0x140,B_REUSE=7 };
#define B_LIVE UINT32_C(0x04000000)
#define B_FULL UINT32_C(0x08000000)
#define B_ERROR UINT32_C(0x10000000)
#define B_VALID UINT32_C(0x20000000)
#define B_44100 UINT32_C(0x40000000)
#define B_CAP3 UINT32_C(0x80000000)
static int paired_available(struct a138_pcm_media *d) {
    uint32_t available,id,version;
    if(!d->paired_probed) {
        if(!pcm_read(d,B_ID,&id)||!pcm_read(d,B_VERSION,&version))return -1;
        if(id!=UINT32_C(0x50434d42)||version!=UINT32_C(0x10000)){d->fault=1;return -1;}
        d->paired_probed=1;
    }
    if(!pcm_read(d,B_AVAILABLE,&available))return -1;
    if(available>1u){d->fault=1;return -1;}
    if(!available) {
        d->paired_have_reply=d->paired_fresh=0;
        if(d->armed){d->fault=1;return -1;}
    }
    return (int)available;
}
static int paired_transaction(struct a138_pcm_media *d,unsigned opcode,
        uint32_t epoch,uint32_t generation,uint32_t stream,uint32_t rate,uint32_t physical) {
    uint32_t reply[8];
    if(d->fault||d->paired_next_request==UINT32_MAX||d->paired_capture==UINT32_MAX||
       (opcode!=0u&&(!d->paired_capture||d->paired_command_id==UINT32_MAX))) {
        d->fault=1;return 0;
    }
    /* All writes are private W intent until B_COMMAND. Its completion means
     * a matched real M response after the window applied-watermark barrier. */
    const uint32_t intent[8]={epoch,generation,stream,rate,physical,d->slot,
        opcode==COMMIT?d->frames:0u,d->next_sequence};
    for(unsigned i=0;i<8u;i++)if(!pcm_write(d,B_KEY+4u*i,intent[i]))return 0;
    if(!pcm_write(d,B_COMMAND,opcode))return 0;
    for(unsigned i=0;i<8u;i++)if(!pcm_read(d,B_REPLY+4u*i,&reply[i]))return 0;
    uint32_t flags=reply[7],command=d->paired_command_id;
    int bad=!reply[0]||reply[1]!=d->paired_next_request||!reply[5]||
        !(flags&B_VALID)||(flags&B_ERROR)||reply[3]>reply[2]||
        (d->paired_token&&reply[0]!=d->paired_token)||
        (d->paired_capture&&reply[5]<=d->paired_capture)||
        ((flags>>12)&1023u)>512u||
        (((flags>>22)&15u)!=0u&&!(flags&8u));
    if(d->paired_capture) {
        if(reply[3]<d->paired_applied_id)bad=1;
        if(opcode==0u) {if(reply[2]!=command)bad=1;}
        else if(command==UINT32_MAX||reply[2]!=command+1u)bad=1;
    }else if(opcode!=0u)bad=1; /* Always establish an actual baseline first. */
    if(opcode!=0u && !(flags&B_LIVE))bad=1;
    if(opcode>=ARM&&opcode<=SELECT_BT&&
       (reply[6]!=physical||((flags&B_44100)?44100u:48000u)!=rate))bad=1;
    if(opcode==ARM && (!(flags&B_FULL)||!(flags&1u)||reply[4]!=0u))bad=1;
    if(opcode==COMMIT && (!(flags&B_FULL)||!(flags&1u)||
        d->next_sequence==UINT32_MAX||reply[4]!=d->next_sequence+1u))bad=1;
    if(opcode==SELECT_BT && (!(flags&B_FULL)||!(flags&1u)))bad=1;
    if(bad){d->fault=1;d->paired_have_reply=d->paired_fresh=0;return 0;}
    /* Publish one complete validated capture, never a mixture of captures.
     * match flags refer to the exact requested full-width tuple above. */
    memcpy(d->paired_reply,reply,sizeof reply);d->paired_token=reply[0];
    d->paired_capture=reply[5];d->paired_command_id=reply[2];d->paired_applied_id=reply[3];
    ++d->paired_next_request;d->paired_have_reply=1;d->paired_reuse=0;d->paired_fresh=1;
    if(opcode==ARM)d->paired_pending_id=0;
    if(opcode==SELECT_BT||opcode==4u||opcode==CANCEL)
        d->paired_pending_id=reply[3]<reply[2]?reply[2]:0u;
    return 1;
}
static int paired_refresh(struct a138_pcm_media *d,uint32_t epoch,uint32_t generation,
        uint32_t stream,uint32_t rate,uint32_t physical) {
    return paired_transaction(d,0,epoch,generation,stream,rate,physical);
}
static void paired_cancel(void *context,uint32_t epoch,uint32_t generation,uint32_t stream) {
    struct a138_pcm_media *d=context;
    if(!d||!d->armed||d->epoch!=epoch||d->generation!=generation||d->stream!=stream)return;
    if(!d->fault&&paired_available(d)==1&&
       paired_refresh(d,epoch,generation,stream,d->rate,d->physical_epoch)) {
        uint32_t flags=d->paired_reply[7];
        /* A stale observer never cancels a replacement M owner. */
        if((flags&(B_LIVE|B_FULL))==(B_LIVE|B_FULL))
            (void)paired_transaction(d,CANCEL,epoch,generation,stream,d->rate,d->physical_epoch);
    }
    d->armed=d->writing=0;d->paired_have_reply=d->paired_fresh=0;
}
static int paired_poll(void *context,uint32_t epoch,uint32_t generation,uint32_t stream,
        uint32_t rate,struct a138_runtime_audio_facts *facts) {
    struct a138_pcm_media *d=context;
    if(!d||!facts||d->fault)return -1;
    *facts=(struct a138_runtime_audio_facts){0};
    if(!epoch||!generation||!stream||(rate!=44100u&&rate!=48000u))return 0;
    if(d->armed&&(d->epoch!=epoch||d->generation!=generation||d->stream!=stream||d->rate!=rate)) {
        paired_cancel(d,d->epoch,d->generation,d->stream);return d->fault?-1:0;
    }
    int available=paired_available(d);if(available<=0)return available;
    /* A single block has at most eight 16-frame submissions. Only its seven
     * intervening polls may reuse a capture. Idle/slot waits, history changes
     * and exhausted reuse always ask the actual M owner again. */
    if(!d->writing||!d->paired_have_reply||d->paired_pending_id||
       (d->paired_reply[7]&48u)||d->paired_reuse>=B_REUSE) {
        if(!paired_refresh(d,epoch,generation,stream,rate,d->armed?d->physical_epoch:0u))return -1;
    }else ++d->paired_reuse;
    uint32_t flags=d->paired_reply[7],actual=(flags&B_44100)?44100u:48000u;
    uint32_t physical=d->paired_reply[6];
    /* Requested epoch/generation are facts only after M compared actual live
     * full-width values. Stream is a fact only after the active full key matched. */
    if(flags&B_LIVE){facts->controller_epoch=epoch;facts->generation=generation;}
    facts->rate_hz=actual;if(flags&B_FULL)facts->stream_epoch=stream;
    if(!(flags&B_CAP3))return 1; /* Actual capability false: no owner command. */
    if(!(flags&B_LIVE)) {if(d->armed){d->fault=1;return -1;}return 0;}
    if(d->armed&&(flags&8u)){d->fault=1;return -1;}
    if((flags&192u)!=192u)return 0;
    if(!d->armed) {
        if(flags&(48u|2u))return 0;
        int clock=pcm_clock(d,rate,actual);if(clock<=0)return clock;
        if(actual!=rate||!physical)return 0;
        d->epoch=epoch;d->generation=generation;d->stream=stream;d->rate=rate;d->physical_epoch=physical;
        d->slot=0;d->next_sequence=0;d->frames=0;
        if(!paired_transaction(d,ARM,epoch,generation,stream,rate,physical))return -1;
        d->armed=1;d->writing=0;return 0;
    }
    if(!(flags&B_FULL)||actual!=d->rate||physical!=d->physical_epoch||!(flags&1u)) {
        d->fault=1;return -1;
    }
    if(d->paired_pending_id&&d->paired_applied_id>=d->paired_pending_id) {
        if(flags&48u)return 0;
        if(!(flags&2u)){d->fault=1;return -1;}
        d->paired_pending_id=0;
    }
    facts->ready=1;facts->drift_managed=1;
    if(!d->paired_pending_id&&!(flags&2u)&&(flags&4u)&&!(flags&48u)) {
        if(!paired_transaction(d,SELECT_BT,epoch,generation,stream,rate,physical))return -1;
    }
    return 1;
}
static enum a138_classic_submission paired_submit(void *context,uint32_t epoch,uint32_t generation,
        uint32_t stream,const struct a138_classic_frame *frame,const int16_t *pcm,
        const struct a138_sbc_pcm *decoded) {
    struct a138_pcm_media *d=context;
    if(!d||d->fault||!d->armed||epoch!=d->epoch||generation!=d->generation||stream!=d->stream||
       !frame||!pcm||!decoded||!decoded->valid||decoded->stream_epoch!=stream||decoded->rate_hz!=d->rate||
       frame->link_epoch!=generation||frame->stream_epoch!=stream||
       decoded->frames<1u||decoded->frames>128u||decoded->channels<1u||decoded->channels>2u||
       decoded->scalar_samples!=decoded->frames*decoded->channels||d->next_sequence==UINT32_MAX)
        return A138_CLASSIC_UNCERTAIN;
    if(!d->writing) {
        if(!d->paired_have_reply||!d->paired_fresh) {
            if(paired_available(d)!=1||!paired_refresh(d,epoch,generation,stream,d->rate,d->physical_epoch))
                return A138_CLASSIC_UNCERTAIN;
        }
        d->paired_fresh=0;uint32_t flags=d->paired_reply[7];
        if((flags&(B_LIVE|B_FULL|B_CAP3|B_VALID|1u))!=(B_LIVE|B_FULL|B_CAP3|B_VALID|1u)||
           (flags&(B_ERROR|8u))||d->paired_reply[6]!=d->physical_epoch||
           ((flags&B_44100)?44100u:48000u)!=d->rate||d->paired_reply[4]!=d->next_sequence) {
            d->fault=1;return A138_CLASSIC_UNCERTAIN;
        }
        if(!((flags>>8)&(1u<<d->slot))) {
            d->paired_have_reply=0;return A138_CLASSIC_REJECTED;
        }
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
    if(!paired_transaction(d,COMMIT,epoch,generation,stream,d->rate,d->physical_epoch))return A138_CLASSIC_UNCERTAIN;
    ++d->next_sequence;d->slot=(uint8_t)((d->slot+1u)&3u);d->writing=0;return A138_CLASSIC_ACCEPTED;
}
#endif
void a138_pcm_media_init(struct a138_pcm_media *d,struct a138_hci_bus bus,a138_clock_bus clock) {
    if(!d)return;
    memset(d,0,sizeof *d);d->bus=bus;d->clock=clock;
    if(!bus.read||!bus.write||!clock.read||!clock.write)d->fault=1;
}
#ifdef A138_TASK3_PHONE_BATCH
void a138_pcm_media_init_paired(struct a138_pcm_media *d,struct a138_hci_bus bus,a138_clock_bus clock) {
    a138_pcm_media_init(d,bus,clock);if(d)d->paired=1;
}
#endif
struct a138_runtime_media a138_pcm_media_callbacks(struct a138_pcm_media *d) {
#ifdef A138_TASK3_PHONE_BATCH
    if(d&&d->paired)return (struct a138_runtime_media){d,paired_poll,paired_submit,paired_cancel};
#endif
    return (struct a138_runtime_media){d,pcm_poll,pcm_submit,pcm_cancel};
}
