/* AE350 UI uses uncached DDR and explicit ownership of two 4 MiB pages.
 * Physical touch is not fitted; the same input model is exercised by self-test.
 * REC is a bounded PCM snapshot, not continuous file recording. */
#include "firmware_checks.h"
#include "ui_render.h"
#define UI_BASE UINT32_C(0xf8020000)
static unsigned heartbeat,runtime_flags;
static volatile a138_record captured[4];
static void beat(void) { diagnostic[2]=++heartbeat; }
static void idle_audio(void) {
    uint32_t s[9];a138_snapshot(AUDIO_BASE,s);
    runtime_flags=0;
    for(unsigned i=2;i<9;i++)if(s[i])runtime_flags|=1u<<(i+6);
    beat();
}
static uint32_t ur(unsigned off) {return a138_read(UI_BASE,off);}
static void uw(unsigned off,uint32_t value) {a138_write(UI_BASE,off,value);}
static void present(unsigned page,unsigned visible) {
    uint32_t base=UINT32_C(0x10000000)+page*UINT32_C(0x00400000);
    unsigned commits=ur(12);
    uw(16,base);uw(24,visible);uw(20,1);
    unsigned timeout=100000;
    while((ur(4)&1u) && --timeout) {beat();}
    if(!timeout || ur(8)!=base || ((ur(4)>>1)&1u)!=visible || ur(12)!=commits+1u) fail(0xbad03001);
}
static void release_note(void) {
    uint32_t s[9];event(2,123,0);a138_snapshot(AUDIO_BASE,s);
    unsigned begin=s[1];
    while(s[0] && (uint32_t)(s[1]-begin)<48000u) a138_snapshot(AUDIO_BASE,s);
    if(s[0]) fail(0xbad03002);
}
static unsigned snap_completed;
static void capture_pcm(unsigned token) {
    a138_record r;
    a138_write(AUDIO_BASE,0x1a8,token); // busy: old result no longer valid
    a138_write(AUDIO_BASE,A138_RECORD_ENABLE,0);
    unsigned drain=1024;
    while(drain && a138_record_try_read(AUDIO_BASE,&r))drain--;
    unsigned count=0,timeout=10000;
    if(drain) {
        a138_write(AUDIO_BASE,A138_RECORD_ENABLE,1);
        while(!(a138_read(AUDIO_BASE,A138_RECORD_STATUS)&2u) && --timeout)beat();
        a138_write(AUDIO_BASE,A138_RECORD_ENABLE,0);
        drain=1024;
        while(drain && a138_record_try_read(AUDIO_BASE,&r)) {
            if(count<4)captured[count++]=r;
            drain--;
        }
    }
    a138_write(AUDIO_BASE,0x1ac,count?captured[0].sequence:0);
    a138_write(AUDIO_BASE,0x1b0,count?(uint32_t)captured[0].left:0);
    a138_write(AUDIO_BASE,0x1b4,count?(uint32_t)captured[0].right:0);
    snap_completed=(snap_completed+1u)&65535u;
    unsigned error=!timeout||!count||!drain;
    a138_write(AUDIO_BASE,0x1a8,(snap_completed<<16)|(count<<8)|(error?128u:64u)|token);
}
static void apply_model(const ui_model*old,const ui_model*m) {
 static const unsigned programs[5]={73,40,56,12,0};
 unsigned mode_changed=!old||old->mode!=m->mode;
 unsigned retrigger=!old||mode_changed||old->note!=m->note||old->gate!=m->gate;
 if(mode_changed)release_note();else if(retrigger&&old&&old->gate)event(0,old->note,0);
 if(mode_changed)event(2,80,m->mode);
 if(!old||old->sound!=m->sound)event(3,programs[m->sound],0);
 unsigned changed=old?(old->sw^m->sw):255;
 if(changed&7u)event(2,81,m->sw&7u);
 if(changed&8u)event(2,1,(m->sw&8u)?80:0);
 if(changed&16u)event(2,5,(m->sw&16u)?64:0);
 if(changed&64u)event(4,0,(m->sw&64u)?80:64);
 if(!old) {event(2,7,100);event(2,11,127);}
 if(!old||old->route!=m->route||(changed&128u))event(2,82,m->route);
 if(retrigger&&m->gate)event(1,m->note,100);
 if((changed&m->sw)&32u)event(2,83,127);
}
static int read_model(ui_model*m) {
 unsigned sequence=a138_read(AUDIO_BASE,0x1a0),state=a138_read(AUDIO_BASE,0x184),options=a138_read(AUDIO_BASE,0x18c);
 uint32_t held[4];for(unsigned k=0;k<4;k++)held[k]=a138_read(AUDIO_BASE,0x190+k*4);
 if(sequence!=a138_read(AUDIO_BASE,0x1a0))return 0;
 unsigned faults=a138_read(AUDIO_BASE,0x1a4)|runtime_flags;
 unsigned snap=a138_read(AUDIO_BASE,0x1a8);
 unsigned sw=((snap&64u)&&((snap&63u)==(options>>26))?32u:0)|(state&7u)|((options&3u)<<3)|((options&4u)<<4)|(((state>>5)&3u)==3?128u:0);
 unsigned changed=m->pc_faults!=faults||m->mode!=((state>>3)&3u)||m->sound!=((state>>7)&7u)||m->route!=((state>>5)&3u)||m->sw!=sw||m->voices!=((state>>10)&63u);
 m->pc_faults=faults;m->mode=(state>>3)&3u;m->sound=(state>>7)&7u;m->route=(state>>5)&3u;m->sw=sw;m->voices=(state>>10)&63u;
 for(unsigned k=0;k<4;k++){changed|=m->held[k]!=held[k];m->held[k]=held[k];}
 return (int)changed;
}
static void model_check(void) {
 ui_model t;ui_init(&t);if(ui_request(&t)!=0x3c000000u)fail(0xbad03100);
 ui_touch(&t,40,50,1);ui_touch(&t,0,0,0);if(t.mode!=1)fail(0xbad03101);
 ui_touch(&t,260,50,1);ui_touch(&t,0,0,0);if(t.sound!=1)fail(0xbad03102);
 for(unsigned k=0;k<15;k++){ui_touch(&t,ui_white_x(k)+25,526,1);if(!t.gate||t.note!=ui_notes[k])fail(0xbad03103);}
 ui_touch(&t,0,0,0);if(t.gate)fail(0xbad03104);
 for(unsigned k=1;k<15;k++)if(ui_notes[k]-ui_notes[k-1]==2){ui_touch(&t,ui_white_x(k),480,1);if(t.note!=ui_notes[k]-1)fail(0xbad03105);}
 ui_touch(&t,0,0,1);if(t.gate)fail(0xbad03106);
}
void services_main(void) {
    diagnostic[1]=0x55494259; // UIBY: self-test/drawing, not yet PASS
    ddr_checks();audio_checks();model_check();
    if(ur(0)!=0x55493338u || (ur(4)&7u) || ur(32)) fail(0xbad03200);
    ui_model model,pages[2];ui_init(&model);apply_model(0,&model);
    unsigned touch=0,page_touch[2]={0,0};
    volatile uint32_t *frame[2]={(volatile uint32_t *)0x10000000u,(volatile uint32_t *)0x10400000u};
    for(unsigned p=0;p<2;p++) {
        pages[p]=model;ui_render(frame[p],&model,touch);a138_fence();beat();
        if(frame[p][0]!=0x08830883u || frame[p][1036799]!=0x08830883u || frame[p][72*960+32]!=0x11271127u) fail(0xbad03201+p);
    }
    // Exercise real publication of both pages and analysis, at frame boundaries.
    present(0,1);present(1,1);present(1,0);present(0,1);
    if(ur(12)!=4) fail(0xbad03203);
    diagnostic[5]=0x55490000u|((ur(12)&255u)<<8)|((ur(4)&7u)<<4)|3u;
    diagnostic[1]=0x50415353;
    unsigned front=0,sequence=ur(40),snap_seen=a138_read(AUDIO_BASE,0x18c)>>26;
    for(;;) {
        idle_audio();
        unsigned snap_request=a138_read(AUDIO_BASE,0x18c)>>26;
        if(snap_request!=snap_seen) {capture_pcm(snap_request);snap_seen=snap_request;}
        diagnostic[5]=0x55490000u|((ur(12)&255u)<<8)|((ur(4)&7u)<<4)|3u;
        unsigned seq=ur(40),status=ur(32),xy=ur(36);
        if(seq!=ur(40))continue;
        unsigned attached=status&1u;
        unsigned changed=(unsigned)read_model(&model);
        ui_model old=model;unsigned touched=0;
        if(seq!=sequence){sequence=seq;touched=ui_touch(&model,xy&65535u,xy>>16,(status>>1)&1u)&UI_CHANGED;}
        if(!attached && touch && model.gate) {model.gate=0;model.keyboard=0;touched=1;}
        if(touched)apply_model(&old,&model);
        changed|=touched;
        if(changed || attached!=touch) {
            unsigned back=front^1u;
            ui_patch(frame[back],&pages[back],&model,page_touch[back],attached);
            a138_fence();pages[back]=model;page_touch[back]=attached;
            present(back,1);front=back;touch=attached;
        }
    }
}
