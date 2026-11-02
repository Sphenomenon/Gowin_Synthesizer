/* Adapter/API smoke against a checked model. Native RTL evidence belongs to
 * the separate LCD/PCM-owner cosimulation; this model is not its substitute. */
#include "task3_phone_firmware_workload.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}} while(0)
struct model {
    uint32_t reg[0x200u/4u],written[4][4],now,commands[6],expected_pcm;
    unsigned committed,fail_commit;
};
static int rd(void *ctx,unsigned lane,uint32_t off,uint32_t *v) {
    struct model *m=ctx;CHECK(!lane&&!(off&3u)&&off<sizeof m->reg);
    *v=m->reg[off/4u];return 1;
}
static int key(const struct model *m) {
    return m->reg[32/4]==m->reg[124/4]&&m->reg[36/4]==m->reg[120/4]&&
        m->reg[40/4]==m->reg[128/4]&&m->reg[44/4]==m->reg[112/4]&&
        m->reg[48/4]==m->reg[116/4];
}
static int wr(void *ctx,unsigned lane,uint32_t off,uint32_t v) {
    struct model *m=ctx;CHECK(!lane&&!(off&3u));
    if(off>=0x800u&&off<0x1000u) {
        unsigned slot=(off-0x800u)/512u,frame=((off-0x800u)%512u)/4u;
        CHECK(m->reg[20/4]&(1u<<slot));CHECK(v==m->expected_pcm);
        m->written[slot][frame/32u]|=1u<<(frame%32u);return 1;
    }
    if(off>=32u&&off<=60u){m->reg[off/4u]=v;return 1;}
    CHECK(off==64u&&v<6u);++m->commands[v];
    if(v==1u) {
        CHECK(m->reg[32/4]==m->reg[124/4]&&m->reg[36/4]==m->reg[120/4]);
        m->reg[128/4]=m->reg[40/4];CHECK(key(m));m->reg[12/4]|=1u;
    }else if(v==2u) {
        unsigned slot=m->reg[52/4];CHECK(slot<4u&&key(m));
        CHECK(m->reg[56/4]==128u&&m->reg[60/4]==m->committed);
        CHECK(m->reg[20/4]&(1u<<slot));
        for(unsigned i=0;i<4u;i++)CHECK(m->written[slot][i]==UINT32_MAX);
        memset(m->written[slot],0,sizeof m->written[slot]);
        m->reg[20/4]&=~(1u<<slot);m->reg[28/4]=++m->committed;
        if(m->committed>=2u)m->reg[12/4]|=4u;
    }else if(v==3u) {
        CHECK(key(m)&&m->committed>=2u);m->reg[12/4]|=2u;
    }else if(v==5u) {
        CHECK(key(m));m->reg[12/4]=192u;m->reg[20/4]=15u;
    }else CHECK(0);
    ++m->reg[68/4];
    return !(v==2u&&m->fail_commit);
}
static uint32_t now(void *ctx){return ((struct model *)ctx)->now;}
static struct task3_phone_workload *setup(struct model *m,int enabled) {
    memset(m,0,sizeof *m);m->reg[0]=UINT32_C(0x50434d31);m->reg[1]=0x10000u;
    m->reg[2]=0x67u;m->reg[3]=192u;m->reg[20/4]=15u;m->reg[100/4]=256u;
    m->reg[112/4]=48000u;m->reg[116/4]=7u;m->reg[120/4]=55u;m->reg[124/4]=44u;
    struct task3_phone_workload *p=task3_phone_workload_create(
        (struct task3_phone_callbacks){m,rd,wr,now},44u,55u,1u,48000u,enabled);
    CHECK(p);return p;
}
static struct task3_phone_stats stats(struct task3_phone_workload *p) {
    struct task3_phone_stats s;task3_phone_workload_snapshot(p,&s);return s;
}
static void block(struct task3_phone_workload *p,struct model *m) {
    m->expected_pcm=UINT32_C(0xe8901f40);
    CHECK(task3_phone_workload_enqueue128(p,8000,-6000));
    CHECK(!task3_phone_workload_enqueue128(p,1,2));
    unsigned selections=m->commands[3];
    struct task3_phone_stats before=stats(p);task3_phone_workload_pump(p);
    struct task3_phone_stats halfway=stats(p);
    CHECK(halfway.pending&&halfway.offset==64u&&halfway.accepted==before.accepted);
    task3_phone_workload_pump(p);struct task3_phone_stats after=stats(p);
    CHECK(!after.fault&&!after.pending&&after.accepted==before.accepted+1u);
    CHECK(after.submit_calls-before.submit_calls==8u);
    CHECK(after.window_writes-before.window_writes==128u&&after.max_window_writes_per_submit==16u);
    unsigned selected=m->commands[3]-selections;
    CHECK(after.pcm_reads-before.pcm_reads==100u+3u*selected);
    CHECK(after.pcm_writes-before.pcm_writes==137u+6u*selected);
}
int main(void) {
    struct model m;struct task3_phone_workload *p=setup(&m,0);
    for(unsigned i=0;i<8u;i++)task3_phone_workload_pump(p);
    struct task3_phone_stats s=stats(p);
    CHECK(s.passes==32u&&s.media_polls==32u&&s.pcm_reads==384u);
    CHECK(!s.fault&&!s.ready&&!s.armed&&!s.pcm_writes&&!s.clock_writes);
    CHECK(!task3_phone_workload_enqueue128(p,8000,-6000));task3_phone_workload_destroy(p);
    p=setup(&m,1);task3_phone_workload_pump(p);s=stats(p);
    CHECK(s.armed&&s.ready&&!s.fault&&m.commands[1]==1u&&s.observed_caps==0x67u);
    block(p,&m);block(p,&m);task3_phone_workload_pump(p);
    CHECK(m.commands[3]==1u&&stats(p).ready);
    task3_phone_workload_cancel(p);s=stats(p);
    CHECK(!s.armed&&!s.pending&&!s.ready&&m.commands[5]==1u&&!s.fault);
    task3_phone_workload_destroy(p);
    p=setup(&m,1);task3_phone_workload_pump(p);
    for(unsigned i=0;i<4u;i++)block(p,&m);
    CHECK(task3_phone_workload_enqueue128(p,8000,-6000));
    task3_phone_workload_pump(p);s=stats(p);CHECK(s.pending&&!s.fault&&s.accepted==4u);
    m.now=99u;task3_phone_workload_pump(p);CHECK(!stats(p).fault);
    m.now=100u;task3_phone_workload_pump(p);s=stats(p);
    CHECK(s.fault==5u&&!s.pending&&s.fences==1u&&m.commands[5]==1u);
    uint64_t writes=s.pcm_writes;task3_phone_workload_pump(p);
    CHECK(stats(p).pcm_writes==writes&&stats(p).fences==1u);task3_phone_workload_destroy(p);
    p=setup(&m,1);task3_phone_workload_pump(p);m.fail_commit=1u;m.expected_pcm=UINT32_C(0xe8901f40);
    CHECK(task3_phone_workload_enqueue128(p,8000,-6000));
    task3_phone_workload_pump(p);task3_phone_workload_pump(p);s=stats(p);
    CHECK(s.fault==5u&&s.media_fault&&s.uncertain_submits==1u&&m.commands[2]==1u&&s.fences==1u);
    writes=s.pcm_writes;for(unsigned i=0;i<4u;i++)task3_phone_workload_pump(p);
    CHECK(stats(p).pcm_writes==writes&&m.commands[2]==1u);task3_phone_workload_destroy(p);
    printf("task3 real phone firmware workload: %u checks passed; PCM-only checked model, no RTL/CPU/RF acceptance\n",checks);
    return 0;
}
