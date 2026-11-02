/* Paired-v3 C adapter and real runtime smoke against a checked model.
 * Full M snapshot/executor/LCD/physical acceptance requires separate RTL tests.
 * Direct-adapter tests explicitly inject model cap3; runtime tests override
 * only returned flag31 through the workload fixture, preserving raw cap3=0. */
#include "task3_phone_firmware_workload.h"
#include "pcm_media.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}} while(0)
struct model {
    uint32_t intent[8],reply[8],active[5],written[4][4];
    uint32_t epoch,generation,physical,rate,token,request,capture,command,applied;
    uint32_t status,free_mask,queued,sequence,now,commands[6],window_writes,reads,writes;
    uint32_t next_mutation,fail_read,fail_commit,raw_cap3,available,apply_history,pending,pending_source;
};
static void initialize(struct model *m,unsigned cap3) {
    memset(m,0,sizeof *m);m->epoch=44;m->generation=55;m->physical=7;m->rate=48000;
    m->token=3;m->status=192;m->free_mask=15;m->raw_cap3=cap3;m->available=1;
}
static int live_match(const struct model *m) {
    return m->intent[0]==m->epoch&&m->intent[1]==m->generation;
}
static int full_match(const struct model *m) {
    for(unsigned i=0;i<5u;i++)if(m->active[i]!=m->intent[i])return 0;
    return 1;
}
static void capture(struct model *m) {
    if(m->pending&&m->apply_history) {
        m->status=(m->status&~(48u|2u))|(m->pending_source?2u:0u);
        m->applied=m->pending;m->pending=0;
    }
    m->reply[0]=m->token;m->reply[1]=m->request++;m->reply[2]=m->command;
    m->reply[3]=m->applied;m->reply[4]=m->sequence;m->reply[5]=++m->capture;
    m->reply[6]=m->physical;
    m->reply[7]=m->status|(m->free_mask<<8)|(m->queued<<12)|
        ((uint32_t)live_match(m)<<26)|((uint32_t)full_match(m)<<27)|(1u<<29)|
        ((uint32_t)(m->rate==44100u)<<30)|(m->raw_cap3<<31);
    switch(m->next_mutation) {
    case 0:break;
    case 1:m->reply[0]++;break;
    case 2:m->reply[1]++;break;
    case 3:m->reply[5]--;break;
    case 4:m->reply[7]&=~(1u<<29);break;
    case 5:m->reply[7]|=1u<<28;break;
    case 6:m->reply[2]--;break;
    case 7:m->reply[3]=m->reply[2]+1u;break;
    case 8:m->reply[7]=(m->reply[7]&~(1023u<<12))|(513u<<12);break;
    case 9:m->reply[7]|=1u<<22;break;
    case 10:m->reply[3]=0;break;
    case 11:m->reply[4]++;break;
    default:CHECK(0);
    }
    m->next_mutation=0;
}
static int rd(void *ctx,unsigned lane,uint32_t off,uint32_t *v) {
    struct model *m=ctx;CHECK(!lane);++m->reads;
    if(m->fail_read==off){m->fail_read=0;return 0;}
    if(off==0x100u)*v=UINT32_C(0x50434d42);
    else if(off==0x104u)*v=0x10000u;
    else if(off==0x108u)*v=m->available;
    else {CHECK(off>=0x140u&&off<=0x15cu&&!(off&3u));*v=m->reply[(off-0x140u)/4u];}
    return 1;
}
static int wr(void *ctx,unsigned lane,uint32_t off,uint32_t v) {
    struct model *m=ctx;CHECK(!lane&&!(off&3u));++m->writes;
    if(off>=0x800u&&off<0x1000u) {
        unsigned slot=(off-0x800u)/512u,index=((off-0x800u)%512u)/4u;
        if(!(m->status&1u)||m->active[0]!=m->epoch||m->active[1]!=m->generation||
           m->active[3]!=m->rate||m->active[4]!=m->physical||!(m->free_mask&(1u<<slot)))return 0;
        CHECK(v==UINT32_C(0xe8901f40));m->written[slot][index/32u]|=1u<<(index%32u);
        ++m->window_writes;return 1;
    }
    if(off>=0x110u&&off<=0x12cu){m->intent[(off-0x110u)/4u]=v;return 1;}
    CHECK(off==0x130u&&v<6u);++m->commands[v];
    if(v==1u) {
        CHECK(live_match(m)&&m->intent[3]==m->rate&&m->intent[4]==m->physical);
        CHECK(!(m->status&3u)&&m->intent[2]>m->active[2]);memcpy(m->active,m->intent,sizeof m->active);
        m->status=193;m->sequence=0;m->free_mask=15;m->queued=0;++m->command;
    }else if(v==2u) {
        unsigned slot=m->intent[5],frames=m->intent[6];
        CHECK(live_match(m)&&full_match(m)&&slot<4u&&frames>=1u&&frames<=128u);
        CHECK(m->intent[7]==m->sequence&&slot==(m->sequence&3u)&&(m->free_mask&(1u<<slot)));
        for(unsigned i=0;i<frames;i++)CHECK(m->written[slot][i/32u]&(1u<<(i%32u)));
        memset(m->written[slot],0,sizeof m->written[slot]);m->free_mask&=~(1u<<slot);
        m->queued+=frames;++m->sequence;++m->command;if(m->queued>=256u)m->status|=4u;
    }else if(v==3u) {
        CHECK(live_match(m)&&full_match(m)&&(m->status&4u)&&!(m->status&48u));
        ++m->command;m->pending=m->command;m->pending_source=1;m->status|=48u;
    }else if(v==5u) {
        CHECK(live_match(m)&&full_match(m));++m->command;
        if((m->status&2u)||m->pending) {
            m->status=192u|(m->status&2u)|48u;m->pending=m->command;m->pending_source=0;
        }else {m->status=192;m->applied=m->command;m->pending=0;}
        m->free_mask=15;m->queued=0;
    }else CHECK(v==0u);
    capture(m);return !(v==2u&&m->fail_commit);
}
static uint32_t now(void *ctx){return ((struct model *)ctx)->now;}
static int direct_read(void *p,uint32_t off,uint32_t *v){return rd(p,0,off,v);}
static int direct_write(void *p,uint32_t off,uint32_t v){return wr(p,0,off,v);}
static int no_clock_read(void *p,uint32_t off,uint32_t *v){(void)p;(void)off;(void)v;CHECK(0);return 0;}
static int no_clock_write(void *p,uint32_t off,uint32_t v){(void)p;(void)off;(void)v;CHECK(0);return 0;}
static struct a138_runtime_media setup(struct model *m,struct a138_pcm_media *d,unsigned cap3) {
    initialize(m,cap3);a138_pcm_media_init_paired(d,
        (struct a138_hci_bus){m,direct_read,direct_write},
        (a138_clock_bus){m,no_clock_read,no_clock_write});return a138_pcm_media_callbacks(d);
}
static int poll(struct a138_runtime_media *f,struct a138_runtime_audio_facts *facts) {
    return f->poll(f->context,44,55,1,48000,facts);
}
static void arm(struct model *m,struct a138_pcm_media *d,struct a138_runtime_media *f) {
    struct a138_runtime_audio_facts facts={0};CHECK(poll(f,&facts)==0&&d->armed&&!d->fault);
    CHECK(m->commands[1]==1&&d->physical_epoch==m->physical&&d->paired_command_id==m->command);
    CHECK(poll(f,&facts)==1&&facts.ready&&facts.drift_managed&&facts.controller_epoch==44&&
        facts.generation==55&&facts.stream_epoch==1&&facts.rate_hz==48000);
}
static enum a138_classic_submission slice(struct a138_runtime_media *f) {
    int16_t pcm[256];for(unsigned i=0;i<128;i++){pcm[2*i]=8000;pcm[2*i+1]=-6000;}
    struct a138_classic_frame frame={.link_epoch=55,.stream_epoch=1};
    struct a138_sbc_pcm decoded={.stream_epoch=1,.rate_hz=48000,.frames=128,
        .scalar_samples=256,.channels=2,.valid=1};
    return f->submit(f->context,44,55,1,&frame,pcm,&decoded);
}
static void block(struct model *m,struct a138_pcm_media *d,struct a138_runtime_media *f) {
    unsigned before=m->window_writes,commits=m->commands[2];
    for(unsigned i=0;i<8u;i++) {
        struct a138_runtime_audio_facts facts={0};CHECK(poll(f,&facts)==1&&facts.ready);
        CHECK(slice(f)==(i==7u?A138_CLASSIC_ACCEPTED:A138_CLASSIC_REJECTED));
        CHECK(m->commands[2]==commits+(i==7u));
    }
    CHECK(m->window_writes==before+128u&&!d->writing&&!d->fault);
}
static void test_protocol(void) {
    struct model m;struct a138_pcm_media d;struct a138_runtime_audio_facts facts;
    struct a138_runtime_media f=setup(&m,&d,0);
    for(unsigned i=0;i<16u;i++)CHECK(poll(&f,&facts)==1&&!facts.ready&&!facts.drift_managed);
    CHECK(!d.armed&&!m.commands[1]&&!m.commands[2]&&!m.commands[3]&&!m.window_writes);
    f=setup(&m,&d,1);m.epoch=45;CHECK(poll(&f,&facts)==0&&!facts.controller_epoch&&!facts.generation&&!facts.stream_epoch);
    for(unsigned mutation=2;mutation<=9u;mutation++) {
        f=setup(&m,&d,1);m.next_mutation=mutation;CHECK(poll(&f,&facts)==-1&&d.fault&&!m.commands[1]);
    }
    f=setup(&m,&d,1);arm(&m,&d,&f);m.next_mutation=1;CHECK(poll(&f,&facts)==-1&&d.fault);
    f=setup(&m,&d,1);arm(&m,&d,&f);m.fail_read=0x14cu;
    uint32_t prior=d.paired_capture;CHECK(poll(&f,&facts)==-1&&d.fault&&d.paired_capture==prior);
    f=setup(&m,&d,1);arm(&m,&d,&f);d.paired_next_request=UINT32_MAX;
    unsigned writes=m.writes;CHECK(poll(&f,&facts)==-1&&d.fault&&m.writes==writes);
    f=setup(&m,&d,1);arm(&m,&d,&f);m.capture=UINT32_MAX;CHECK(poll(&f,&facts)==-1&&d.fault);
    f=setup(&m,&d,1);arm(&m,&d,&f);m.generation++;
    CHECK(poll(&f,&facts)==-1&&d.fault&&!facts.generation);
    f=setup(&m,&d,1);arm(&m,&d,&f);m.physical++;
    CHECK(poll(&f,&facts)==-1&&d.fault);
    f=setup(&m,&d,1);arm(&m,&d,&f);m.available=0;
    CHECK(poll(&f,&facts)==-1&&d.fault&&!facts.ready);
    f=setup(&m,&d,1);arm(&m,&d,&f);m.generation++;
    f.cancel(f.context,44,55,1);CHECK(!d.armed&&!m.commands[5]);
}
static void test_cache_and_history(void) {
    struct model m;struct a138_pcm_media d;struct a138_runtime_audio_facts facts;
    struct a138_runtime_media f=setup(&m,&d,1);arm(&m,&d,&f);
    CHECK(slice(&f)==A138_CLASSIC_REJECTED);unsigned snapshots=m.commands[0];
    for(unsigned i=0;i<7u;i++)CHECK(poll(&f,&facts)==1&&facts.ready&&m.commands[0]==snapshots);
    CHECK(poll(&f,&facts)==1&&m.commands[0]==snapshots+1u);
    for(unsigned i=1;i<8u;i++){CHECK(poll(&f,&facts)==1);CHECK(slice(&f)==(i==7u?A138_CLASSIC_ACCEPTED:A138_CLASSIC_REJECTED));}
    CHECK(!d.fault&&d.paired_command_id==2u&&d.paired_applied_id==0u); /* COMMIT is accepted, not source-applied. */
    block(&m,&d,&f);CHECK(poll(&f,&facts)==1&&facts.ready&&m.commands[3]==1u&&d.paired_pending_id==4u);
    snapshots=m.commands[0];for(unsigned i=0;i<3u;i++)CHECK(poll(&f,&facts)==1&&m.commands[3]==1u);
    CHECK(m.commands[0]==snapshots+3u&&d.paired_pending_id==4u&&d.paired_applied_id==0u);
    m.apply_history=1;CHECK(poll(&f,&facts)==1&&!d.paired_pending_id&&d.paired_applied_id==4u&&(m.status&2u));
    m.next_mutation=10;CHECK(poll(&f,&facts)==-1&&d.fault); /* Applied ID cannot regress. */
    f=setup(&m,&d,1);arm(&m,&d,&f);block(&m,&d,&f);block(&m,&d,&f);
    CHECK(poll(&f,&facts)==1);m.apply_history=1;CHECK(poll(&f,&facts)==1&&(m.status&2u));
    m.apply_history=0;f.cancel(f.context,44,55,1);CHECK(!d.armed&&d.paired_pending_id);
    CHECK(f.poll(f.context,44,55,2,48000,&facts)==0&&!d.armed);
    m.apply_history=1;CHECK(f.poll(f.context,44,55,2,48000,&facts)==0&&d.armed&&!d.paired_pending_id);
    CHECK(f.poll(f.context,44,55,2,48000,&facts)==1&&facts.ready&&facts.stream_epoch==2u);
    f=setup(&m,&d,1);arm(&m,&d,&f);m.fail_commit=1u;
    for(unsigned i=0;i<8u;i++){CHECK(poll(&f,&facts)==1);CHECK(slice(&f)==(i==7u?A138_CLASSIC_UNCERTAIN:A138_CLASSIC_REJECTED));}
    CHECK(d.fault&&m.commands[2]==1u);CHECK(slice(&f)==A138_CLASSIC_UNCERTAIN&&m.commands[2]==1u);
    f=setup(&m,&d,1);arm(&m,&d,&f);
    for(unsigned i=0;i<8u;i++){CHECK(poll(&f,&facts)==1);if(i==7u)m.next_mutation=6;
        CHECK(slice(&f)==(i==7u?A138_CLASSIC_UNCERTAIN:A138_CLASSIC_REJECTED));}
    CHECK(d.fault&&m.commands[2]==1u); /* A completed bus is not a command-ID proof. */
}
static struct task3_phone_stats runtime_stats(struct task3_phone_workload *p) {
    struct task3_phone_stats s;task3_phone_workload_snapshot(p,&s);return s;
}
static struct task3_phone_workload *runtime_setup(struct model *m,unsigned inject) {
    initialize(m,0);struct task3_phone_workload *p=task3_phone_workload_create_paired(
        (struct task3_phone_callbacks){m,rd,wr,now},44,55,1,48000,inject);CHECK(p);return p;
}
static void test_runtime(void) {
    struct model m;struct task3_phone_workload *p=runtime_setup(&m,0);
    for(unsigned i=0;i<8u;i++)task3_phone_workload_pump(p);
    struct task3_phone_stats s=runtime_stats(p);
    CHECK(s.observed_caps==0x67u&&!s.ready&&!s.armed&&!s.fault&&!m.window_writes);
    CHECK(!m.commands[1]&&!m.commands[2]&&!m.commands[3]);task3_phone_workload_destroy(p);
    p=runtime_setup(&m,1);task3_phone_workload_pump(p);s=runtime_stats(p);CHECK(s.armed&&s.ready&&!s.fault);
    for(unsigned i=0;i<4u;i++) {
        CHECK(task3_phone_workload_enqueue128(p,8000,-6000));
        task3_phone_workload_pump(p);CHECK(runtime_stats(p).pending);
        task3_phone_workload_pump(p);CHECK(runtime_stats(p).accepted==i+1u&&!runtime_stats(p).fault);
    }
    CHECK(task3_phone_workload_enqueue128(p,8000,-6000));task3_phone_workload_pump(p);
    CHECK(runtime_stats(p).pending&&!runtime_stats(p).fault);
    m.now=99;task3_phone_workload_pump(p);CHECK(!runtime_stats(p).fault);
    m.now=100;task3_phone_workload_pump(p);s=runtime_stats(p);
    CHECK(s.fault==A138_RUNTIME_MEDIA_FAULT&&s.fences==1u&&!s.pending&&m.commands[5]==1u);
    unsigned writes=m.writes;task3_phone_workload_pump(p);CHECK(m.writes==writes);task3_phone_workload_destroy(p);
    p=runtime_setup(&m,1);task3_phone_workload_pump(p);m.fail_commit=1;
    CHECK(task3_phone_workload_enqueue128(p,8000,-6000));task3_phone_workload_pump(p);task3_phone_workload_pump(p);
    s=runtime_stats(p);CHECK(s.fault==A138_RUNTIME_MEDIA_FAULT&&s.uncertain_submits==1u&&m.commands[2]==1u&&s.fences==1u);
    writes=m.writes;task3_phone_workload_pump(p);CHECK(m.writes==writes);task3_phone_workload_destroy(p);
}
int main(void) {
    test_protocol();test_cache_and_history();test_runtime();
    printf("task3 paired phone firmware: %u checks passed; checked model, no RTL/CPU/RF acceptance\n",checks);
    return 0;
}
