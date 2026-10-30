/* AE350 UI uses uncached DDR and explicit ownership of two 4 MiB pages.
 * Physical touch is not fitted; the same input model is exercised by self-test.
 * REC is a bounded PCM snapshot, not continuous file recording. */
#include "firmware_checks.h"
#include "ui_render.h"
#ifdef A138_BLE_BUSINESS
#include "ble_business_owner.h"
#endif
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
/* These are request/job caches, not another owner of committed parameters.
 * Every runtime step has a fixed work limit; only real MMIO completion retires
 * a publication, release or capture operation. */
enum { UI_SLICE_ROWS=2,UI_POLL_LIMIT=100000,CAPTURE_LIMIT=1024 };
typedef struct {unsigned active,page,visible,commits,left;} ui_present_job;
typedef struct {
 ui_model base,target;unsigned active,initial,releasing,begin;
} ui_control_job;
typedef struct {
 unsigned state,token,pending,pending_token,seen,count,left,timeout,error;
} ui_capture_job;
typedef struct {
 ui_model old,target;unsigned active,page,row,old_touch,touch,revision,cancelled,full;
 ui_present_job present;
} ui_draw_job;
typedef struct {
 ui_model model,pages[2];ui_control_job control;ui_capture_job capture;ui_draw_job drawing;
 volatile uint32_t *frame[2];unsigned touch,page_touch[2],valid[2],front,sequence,revision,shown;
} ui_runtime;
static unsigned page_base(unsigned page) {return UINT32_C(0x10000000)+page*UINT32_C(0x00400000);}
static int present_begin(ui_present_job*j,unsigned page,unsigned visible) {
 if(j->active || page>1 || visible>1 || (ur(4)&1u))return -1;
 *j=(ui_present_job){.active=1,.page=page,.visible=visible,.commits=ur(12),.left=UI_POLL_LIMIT};
 uw(16,page_base(page));uw(24,visible);uw(20,1);return 0;
}
/* One poll, never a wait loop. An accepted publication cannot be cancelled. */
static int present_step(ui_present_job*j) {
 if(!j->active)return 1;
 unsigned status=ur(4);
 if(status&1u)return --j->left?0:-1;
 if(ur(8)!=page_base(j->page) || ((status>>1)&1u)!=j->visible || ur(12)!=j->commits+1u)return -1;
 j->active=0;return 1;
}
static void control_submit(ui_control_job*j,const ui_model*old,const ui_model*m) {
 if(!j->active) {
  *j=(ui_control_job){.target=*m,.active=1,.initial=!old};
  if(old)j->base=*old;
 } else if(old) {
  /* Merge only explicit changed request fields. A new gate request must not
   * erase a mode command still waiting for release with old HW feedback. */
  if(old->mode!=m->mode)j->target.mode=m->mode;
  if(old->sound!=m->sound)j->target.sound=m->sound;
  if(old->route!=m->route)j->target.route=m->route;
  if(old->note!=m->note)j->target.note=m->note;
  if(old->gate!=m->gate)j->target.gate=m->gate;
  unsigned changed=old->sw^m->sw;
  j->target.sw=(j->target.sw&~changed)|(m->sw&changed);
 }
}
static void control_panic(ui_control_job*j) {
 // PANIC already belongs to the PL event owner. Revoke a queued local Note On.
 if(j->active)j->target.gate=0;
}
static int control_step(ui_control_job*j) {
 if(!j->active)return 1;
 const ui_model*old=j->initial?0:&j->base;const ui_model*m=&j->target;
 unsigned mode_changed=!old||old->mode!=m->mode;
 if((mode_changed || j->releasing) && j->releasing!=2) {
  uint32_t state[9];
  if(!j->releasing) {event(2,123,0);a138_snapshot(AUDIO_BASE,state);j->begin=state[1];j->releasing=1;return 0;}
  a138_snapshot(AUDIO_BASE,state);
  if(state[0])return (uint32_t)(state[1]-j->begin)<48000u?0:-1;
  j->releasing=2;
 }
 static const unsigned programs[5]={73,40,56,12,0};
 unsigned retrigger=!old||mode_changed||j->releasing||old->note!=m->note||old->gate!=m->gate;
 if(!j->releasing && retrigger && old && old->gate)event(0,old->note,0);
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
 j->active=0;return 1;
}
static unsigned snap_completed;
static void capture_request(ui_capture_job*j,unsigned token) {
 if(token!=j->seen){j->seen=token;j->pending=1;j->pending_token=token;}
}
static void capture_step(ui_capture_job*j) {
 a138_record r;
 if(!j->state) {
  if(!j->pending)return;
  j->token=j->pending_token;j->pending=0;j->count=0;j->left=CAPTURE_LIMIT;j->timeout=10000;j->error=0;j->state=1;
  a138_write(AUDIO_BASE,0x1a8,j->token);a138_write(AUDIO_BASE,A138_RECORD_ENABLE,0);return;
 }
 if(j->state==1 || j->state==3) {
  if(a138_record_try_read(AUDIO_BASE,&r)) {
   if(j->state==3 && j->count<4)captured[j->count++]=r;
   if(!--j->left){j->error=1;j->state=4;}
   return;
  }
  if(j->state==1){a138_write(AUDIO_BASE,A138_RECORD_ENABLE,1);j->state=2;}
  else j->state=4;
  return;
 }
 if(j->state==2) {
  if(a138_read(AUDIO_BASE,A138_RECORD_STATUS)&2u) {a138_write(AUDIO_BASE,A138_RECORD_ENABLE,0);j->left=CAPTURE_LIMIT;j->state=3;}
  else if(!--j->timeout){a138_write(AUDIO_BASE,A138_RECORD_ENABLE,0);j->error=1;j->state=4;}
  return;
 }
 a138_write(AUDIO_BASE,0x1ac,j->count?captured[0].sequence:0);
 a138_write(AUDIO_BASE,0x1b0,j->count?(uint32_t)captured[0].left:0);
 a138_write(AUDIO_BASE,0x1b4,j->count?(uint32_t)captured[0].right:0);
 snap_completed=(snap_completed+1u)&65535u;
 a138_write(AUDIO_BASE,0x1a8,(snap_completed<<16)|(j->count<<8)|((j->error||!j->count)?128u:64u)|j->token);
 j->state=0;
}
static int draw_begin(ui_draw_job*j,unsigned front,const ui_model*pages,const unsigned*page_touch,
 const unsigned*valid,const ui_model*m,unsigned touch,unsigned revision) {
 if(j->active || (ur(4)&1u) || ur(8)!=page_base(front))return -1;
 unsigned back=front^1u;
 *j=(ui_draw_job){.old=pages[back],.target=*m,.active=1,.page=back,.old_touch=page_touch[back],
  .touch=touch,.revision=revision,.full=!valid[back]};return 0;
}
static void draw_cancel(ui_draw_job*j,unsigned*valid) {
 if(!j->active)return;
 if(j->present.active)j->cancelled=1; // retire the real accepted request first
 else {valid[j->page]=0;j->active=0;}
}
static int draw_step(ui_draw_job*j,volatile uint32_t*const*frame,ui_model*pages,
 unsigned*page_touch,unsigned*valid,unsigned*front,unsigned*shown) {
 if(!j->active)return 1;
 if(j->present.active) {
  int result=present_step(&j->present);if(result<=0)return result;
  *front=j->page;if(!j->cancelled)*shown=j->revision;
  j->active=0;return 1;
 }
 if(j->full)ui_render_rows(frame[j->page],&j->target,j->touch,j->row,UI_SLICE_ROWS);
 else ui_patch_rows(frame[j->page],&j->old,&j->target,j->old_touch,j->touch,j->row,UI_SLICE_ROWS);
 j->row+=UI_SLICE_ROWS;
 if(j->row>=UI_FRAME_ROWS) {
  a138_fence();pages[j->page]=j->target;page_touch[j->page]=j->touch;valid[j->page]=1;
  if(present_begin(&j->present,j->page,1)<0)return -1;
 }
 return 0;
}
static int read_model(ui_model*m) {
 unsigned sequence=a138_read(AUDIO_BASE,0x1a0),state=a138_read(AUDIO_BASE,0x184),pitch=a138_read(AUDIO_BASE,0x188),options=a138_read(AUDIO_BASE,0x18c);
 uint32_t held[4];for(unsigned k=0;k<4;k++)held[k]=a138_read(AUDIO_BASE,0x190+k*4);
 // PANIC epoch is one atomic register fact. Other model fields still require
 // a coherent snapshot, but a torn snapshot must not hide an observed PANIC.
 unsigned changed=ui_panic(m,pitch>>22);
 if(sequence!=a138_read(AUDIO_BASE,0x1a0))return (int)changed;
 unsigned faults=a138_read(AUDIO_BASE,0x1a4)|runtime_flags;
 unsigned snap=a138_read(AUDIO_BASE,0x1a8);
 unsigned sw=((snap&64u)&&((snap&63u)==(options>>26))?32u:0)|(state&7u)|((options&3u)<<3)|((options&4u)<<4)|(((state>>5)&3u)==3?128u:0);
 changed|=(m->pc_faults!=faults)||m->mode!=((state>>3)&3u)||m->sound!=((state>>7)&7u)||m->route!=((state>>5)&3u)||m->sw!=sw||m->voices!=((state>>10)&63u);
 m->pc_faults=faults;m->mode=(state>>3)&3u;m->sound=(state>>7)&7u;m->route=(state>>5)&3u;m->sw=sw;m->voices=(state>>10)&63u;
 for(unsigned k=0;k<4;k++){changed|=m->held[k]!=held[k];m->held[k]=held[k];}
 return (int)changed;
}
static void ui_service_step(ui_runtime*r) {
        idle_audio();
#ifdef A138_BLE_BUSINESS
        a138_ble_business_firmware_pump();
#endif
        capture_request(&r->capture,a138_read(AUDIO_BASE,0x18c)>>26);capture_step(&r->capture);
        diagnostic[5]=0x55490000u|((ur(12)&255u)<<8)|((ur(4)&7u)<<4)|3u;
        unsigned panic=r->model.panic_epoch,changed=(unsigned)read_model(&r->model);
        if(r->model.panic_epoch!=panic){control_panic(&r->control);draw_cancel(&r->drawing,r->valid);}
        unsigned seq=ur(40),status=ur(32),xy=ur(36);
        // A torn touch read postpones only input handling, never other jobs.
        if(seq==ur(40)) {
            unsigned attached=status&1u;
            ui_model old=r->model;unsigned touched=0;
            if(seq!=r->sequence){r->sequence=seq;touched=ui_touch(&r->model,xy&65535u,xy>>16,(status>>1)&1u)&UI_CHANGED;}
            if(!attached && r->touch && r->model.gate) {r->model.gate=0;r->model.keyboard=0;touched=1;}
            if(touched)control_submit(&r->control,&old,&r->model);
            changed|=touched || attached!=r->touch;r->touch=attached;
        }
        if(changed)r->revision++;
        if(control_step(&r->control)<0)fail(0xbad03002);
        if(!r->drawing.active && r->revision!=r->shown)
            if(draw_begin(&r->drawing,r->front,r->pages,r->page_touch,r->valid,&r->model,r->touch,r->revision)<0)fail(0xbad03001);
        if(draw_step(&r->drawing,r->frame,r->pages,r->page_touch,r->valid,&r->front,&r->shown)<0)fail(0xbad03001);
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
    // Reload a visible LED-only guide after the short service self-test.  It
    // remains stopped until Push Play (CC85) and never creates note/PCM data.
    static const a138_cue guide[9]={{0,0x0000000f},{24000,0x000000f0},
        {48000,0x00000f00},{72000,0x0000f000},{96000,0x000f0000},
        {120000,0x00f00000},{144000,0x0f000000},{168000,0xf0000000},
        {192000,0}};
    if(!a138_score_load(AUDIO_BASE,guide,9))fail(0xbad03107);
    if(ur(0)!=0x55493338u || (ur(4)&7u) || ur(32)) fail(0xbad03200);
    ui_runtime runtime={.valid={1,1},.revision=1,.shown=1,
        .frame={(volatile uint32_t *)0x10000000u,(volatile uint32_t *)0x10400000u}};
    ui_init(&runtime.model);control_submit(&runtime.control,0,&runtime.model);
#ifdef A138_BLE_BUSINESS
    a138_ble_business_firmware_init();
#endif
    // Startup self-tests retain their existing acceptance. Service waits below
    // yield background work on every poll/slice; runtime has no wait loops.
    while(runtime.control.active) {
        idle_audio();
#ifdef A138_BLE_BUSINESS
        a138_ble_business_firmware_pump();
#endif
        if(control_step(&runtime.control)<0)fail(0xbad03002);
    }
    for(unsigned p=0;p<2;p++) {
        runtime.pages[p]=runtime.model;
        for(unsigned row=0;row<UI_FRAME_ROWS;row+=UI_SLICE_ROWS) {
            ui_render_rows(runtime.frame[p],&runtime.model,runtime.touch,row,UI_SLICE_ROWS);idle_audio();
#ifdef A138_BLE_BUSINESS
            a138_ble_business_firmware_pump();
#endif
        }
        a138_fence();beat();
        if(runtime.frame[p][0]!=0x08830883u || runtime.frame[p][1036799]!=0x08830883u || runtime.frame[p][72*960+32]!=0x11271127u) fail(0xbad03201+p);
    }
    // Exercise real publication of both pages and analysis, at frame boundaries.
    static const unsigned startup_page[4]={0,1,1,0},startup_visible[4]={1,1,0,1};
    for(unsigned n=0;n<4;n++) {
        ui_present_job job={0};if(present_begin(&job,startup_page[n],startup_visible[n])<0)fail(0xbad03001);
        while(job.active) {
            idle_audio();
#ifdef A138_BLE_BUSINESS
            a138_ble_business_firmware_pump();
#endif
            if(present_step(&job)<0)fail(0xbad03001);
        }
    }
    if(ur(12)!=4) fail(0xbad03203);
    diagnostic[5]=0x55490000u|((ur(12)&255u)<<8)|((ur(4)&7u)<<4)|3u;
    diagnostic[1]=0x50415353;
    runtime.sequence=ur(40);runtime.capture.seen=a138_read(AUDIO_BASE,0x18c)>>26;
    for(;;)ui_service_step(&runtime);
}
