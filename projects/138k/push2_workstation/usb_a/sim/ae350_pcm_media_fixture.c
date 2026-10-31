/* Exact F806 C adapter, checked asynchronous model; no native RTL/board claim. */
#define main clock_fixture_main
#include "ae350_clock_service_host.c"
#undef main
#include "pcm_media.h"
struct pcm_model {
    uint32_t reg[0x200/4],data[4][128],written[4][4];
    unsigned accesses,writes,commands,last_command,fail_after_commit,mutate_at;
    uint32_t last_epoch,last_generation,last_stream;
};
static struct pcm_model p;
static model c;
static struct a138_pcm_media d;
static struct a138_runtime_media media;
static int pcm_rd(void *ctx,uint32_t off,uint32_t *v) {
    struct pcm_model *m=ctx;CHECK(!(off&3u)&&off<0x200u);++m->accesses;
    if(m->mutate_at==m->accesses)++m->reg[0x7c/4];
    *v=m->reg[off/4];return 1;
}
static int same_key(const struct pcm_model *m) {
    return m->reg[0x20/4]==m->reg[0x7c/4]&&m->reg[0x24/4]==m->reg[0x78/4]&&
        m->reg[0x28/4]==m->reg[0x80/4]&&m->reg[0x2c/4]==m->reg[0x70/4]&&m->reg[0x30/4]==m->reg[0x74/4];
}
static int pcm_wr(void *ctx,uint32_t off,uint32_t v) {
    struct pcm_model *m=ctx;CHECK(!(off&3u));++m->accesses;++m->writes;
    if(off>=0x800u&&off<0x1000u) {
        unsigned slot=(off-0x800u)/512u,frame=((off-0x800u)%512u)/4u;
        CHECK(m->reg[0x14/4]&(1u<<slot));m->data[slot][frame]=v;m->written[slot][frame/32u]|=1u<<(frame%32u);return 1;
    }
    if(off>=0x20u&&off<=0x3cu){m->reg[off/4]=v;return 1;}
    CHECK(off==0x40u&&v>=1u&&v<=5u&&m->reg[0x44/4]!=UINT32_MAX);
    ++m->commands;m->last_command=v;
    if(v==1u) {
        if(m->reg[0x20/4]!=m->reg[0x7c/4]||m->reg[0x24/4]!=m->reg[0x78/4]||
           m->reg[0x2c/4]!=m->reg[0x70/4]||m->reg[0x30/4]!=m->reg[0x74/4]||
           !m->reg[0x28/4]||(m->last_epoch==m->reg[0x20/4]&&m->last_generation==m->reg[0x24/4]&&
           m->reg[0x28/4]<=m->last_stream))return 1; /* APB completed; no acceptance ID. */
        m->last_epoch=m->reg[0x20/4];m->last_generation=m->reg[0x24/4];m->last_stream=m->reg[0x28/4];
        m->reg[0x80/4]=m->reg[0x28/4];m->reg[0x0c/4]=(m->reg[0x0c/4]&~8u)|1;
        m->reg[0x1c/4]=0;m->reg[0x14/4]=15;
    }else if(v==2u) {
        unsigned slot=m->reg[0x34/4],frames=m->reg[0x38/4];
        CHECK(same_key(m)&&slot<4u&&slot==(m->reg[0x1c/4]&3u)&&frames&&frames<=128u);
        CHECK(m->reg[0x3c/4]==m->reg[0x1c/4]&&(m->reg[0x14/4]&(1u<<slot)));
        for(unsigned i=0;i<frames;i++)CHECK(m->written[slot][i/32u]&(1u<<(i%32u)));
        memset(m->written[slot],0,sizeof m->written[slot]);m->reg[0x14/4]&=~(1u<<slot);
        ++m->reg[0x1c/4];m->reg[0x18/4]+=frames;if(m->reg[0x18/4]>=256u)m->reg[0x0c/4]|=4;
    }else if(v==3u) {CHECK(same_key(m)&&(m->reg[0x0c/4]&4u));m->reg[0x0c/4]|=16;}
    else if(v==5u){CHECK(same_key(m));m->reg[0x0c/4]&=~7u;m->reg[0x14/4]=15;}
    ++m->reg[0x44/4];return !m->fail_after_commit;
}
static void setup(uint32_t caps) {
    memset(&p,0,sizeof p);initialize(&c);
    p.reg[0]=0x50434d31;p.reg[1]=0x10000;p.reg[2]=caps;p.reg[3]=192;
    p.reg[0x14/4]=15;p.reg[0x64/4]=256;p.reg[0x70/4]=48000;p.reg[0x74/4]=100;
    p.reg[0x78/4]=9;p.reg[0x7c/4]=77;
    a138_pcm_media_init(&d,(struct a138_hci_bus){&p,pcm_rd,pcm_wr},bus_for(&c));media=a138_pcm_media_callbacks(&d);
}
static int poll_pcm(uint32_t rate,struct a138_runtime_audio_facts *facts) {
    p.accesses=0;clear_trace(&c);int r=media.poll(media.context,77,9,5,rate,facts);CHECK(p.accesses<=32u);return r;
}
static void arm(void) {
    struct a138_runtime_audio_facts f={0};CHECK(poll_pcm(48000,&f)==0&&d.armed&&p.commands==1&&p.last_command==1);
    CHECK(poll_pcm(48000,&f)==1&&f.ready&&f.drift_managed&&!f.delay_valid&&f.controller_epoch==77&&f.generation==9&&f.stream_epoch==5);
}
static enum a138_classic_submission block(unsigned channels) {
    int16_t pcm[256];for(unsigned i=0;i<256;i++)pcm[i]=(int16_t)((int)i*313-32768);
    struct a138_sbc_pcm decoded={.stream_epoch=5,.rate_hz=48000,.frames=128,.scalar_samples=(uint16_t)(128u*channels),.channels=(uint8_t)channels,.valid=1};
    struct a138_classic_frame frame={.link_epoch=9,.stream_epoch=5};
    unsigned before=p.reg[0x1c/4];
    enum a138_classic_submission result=A138_CLASSIC_REJECTED;
    for(unsigned i=0;i<8u;i++) {
        p.accesses=0;result=media.submit(media.context,77,9,5,&frame,pcm,&decoded);CHECK(p.accesses<=32u);
        if(result==A138_CLASSIC_UNCERTAIN)return result;
        if(i<7u)CHECK(result==A138_CLASSIC_REJECTED&&p.reg[0x1c/4]==before); /* partial writes aren't acceptance */
    }
    if(result==A138_CLASSIC_ACCEPTED) {
        unsigned slot=before&3u;for(unsigned i=0;i<128u;i++) {
            uint32_t left=(uint16_t)pcm[i*channels],right=(uint16_t)pcm[i*channels+(channels==2u)];
            CHECK(p.data[slot][i]==(left|(right<<16)));
        }
    }
    return result;
}
static void test_capability_gate(void) {
    struct a138_runtime_audio_facts f={0};
    for(unsigned caps=0x63;caps<=0x67;caps+=4u){setup(caps);CHECK(poll_pcm(44100,&f)==1&&!f.ready&&!f.drift_managed&&!p.writes&&!c.writes);}
    setup(0x6f);p.mutate_at=10;CHECK(poll_pcm(48000,&f)==0&&!p.writes&&!d.armed);
    setup(0x6f);p.mutate_at=11;CHECK(poll_pcm(48000,&f)==-1&&d.fault&&!d.armed&&!p.reg[0x44/4]);
    setup(0x7f);CHECK(poll_pcm(48000,&f)==-1&&d.fault&&!p.writes); /* delay ABI not invented */
}
static void test_blocks_and_selection(void) {
    setup(0x6f);arm();CHECK(block(2)==A138_CLASSIC_ACCEPTED&&p.reg[0x1c/4]==1);
    CHECK(block(1)==A138_CLASSIC_ACCEPTED&&p.reg[0x1c/4]==2&&p.reg[0x18/4]==256);
    struct a138_runtime_audio_facts f={0};CHECK(poll_pcm(48000,&f)==1&&f.ready&&p.last_command==3);
    unsigned commands=p.commands;CHECK(poll_pcm(48000,&f)==1&&f.ready&&p.commands==commands); /* pending source handoff doesn't revoke stream */
    p.reg[0x0c/4]=(p.reg[0x0c/4]&~16u)|2u;p.reg[0x4c/4]=1;
    CHECK(block(2)==A138_CLASSIC_ACCEPTED&&block(2)==A138_CLASSIC_ACCEPTED);
    unsigned writes=p.writes;CHECK(block(2)==A138_CLASSIC_REJECTED&&p.writes==writes); /* full slot never overwritten */
    p.reg[0x14/4]|=1;CHECK(block(2)==A138_CLASSIC_ACCEPTED&&p.reg[0x1c/4]==5);
    media.cancel(media.context,77,9,5);CHECK(!d.armed&&p.last_command==5);commands=p.commands;
    media.cancel(media.context,77,9,5);CHECK(p.commands==commands);
    setup(0x6f);arm();p.reg[0x80/4]=6;commands=p.commands;media.cancel(media.context,77,9,5);CHECK(p.commands==commands&&!d.armed);
}
static void test_uncertainty_and_rate(void) {
    setup(0x6f);arm();p.fail_after_commit=1;CHECK(block(2)==A138_CLASSIC_UNCERTAIN&&d.fault&&p.reg[0x1c/4]==1);
    unsigned commands=p.commands;CHECK(block(2)==A138_CLASSIC_UNCERTAIN&&p.commands==commands);
    setup(0x6f);struct a138_runtime_audio_facts f={0};c.registers[A138_CLK_STATUS/4]=9;
    CHECK(poll_pcm(44100,&f)==0&&!d.fault&&!c.writes&&!p.commands); /* busy before write is safe to poll */
    c.registers[A138_CLK_STATUS/4]=8;CHECK(poll_pcm(44100,&f)==0&&d.clock_pending&&c.writes==1&&!p.commands);
    CHECK(poll_pcm(44100,&f)==0&&!c.writes&&!p.commands);
    complete(&c,&d.clock_ticket,A138_CLK_RESULT_APPLIED);p.reg[0x70/4]=44100;p.reg[0x74/4]=101;
    CHECK(poll_pcm(44100,&f)==0&&d.armed&&!d.clock_pending&&p.commands==1);
    CHECK(poll_pcm(44100,&f)==1&&f.ready&&f.rate_hz==44100);
}
static void test_failed_old_owner_recovery(void) {
    struct a138_runtime_audio_facts f={0};
    for(unsigned changed_generation=0;changed_generation<2u;changed_generation++) {
        setup(0x6f);p.reg[0x0c/4]|=8u;p.last_epoch=77;p.last_generation=changed_generation?8:9;
        p.last_stream=changed_generation?20:4;p.reg[0x80/4]=p.last_stream;
        CHECK(poll_pcm(48000,&f)==0&&d.armed&&!d.fault&&p.reg[0x44/4]==1);
        CHECK(poll_pcm(48000,&f)==1&&f.ready&&p.last_generation==9&&p.last_stream==5);
        p.reg[0x0c/4]|=8u;CHECK(poll_pcm(48000,&f)==-1&&d.fault); /* failure of current owner */
    }
    for(unsigned retired_stream=5;retired_stream<=6u;retired_stream++) {
        setup(0x6f);p.reg[0x0c/4]|=8u;p.last_epoch=77;p.last_generation=9;
        p.last_stream=retired_stream;p.reg[0x80/4]=retired_stream;
        CHECK(poll_pcm(48000,&f)==-1&&d.fault&&!d.armed&&!p.reg[0x44/4]&&p.last_stream==retired_stream);
    }
}
int main(void) {
    CHECK(clock_fixture_main()==0);test_capability_gate();test_blocks_and_selection();test_uncertainty_and_rate();
    test_failed_old_owner_recovery();
    printf("PCM media adapter: %u checks passed; capabilities injected only, no native/physical/sustained proof\n",checks);return 0;
}
