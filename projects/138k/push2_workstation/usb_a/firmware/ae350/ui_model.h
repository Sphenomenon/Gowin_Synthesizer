#ifndef GW138K_UI_MODEL_H
#define GW138K_UI_MODEL_H
#include <stdint.h>
typedef struct {
 unsigned mode,sound,route,gate,sw,note,keyboard,old_down,panic_epoch,panic_latched;
 uint32_t held[4];unsigned voices,pc_faults;
 /* Read-only observations. Requests still pass through the control owner. */
 unsigned volume,effect_order,clock_actual,d_depths[3];
} ui_model;
enum { UI_CHANGED=1,UI_ANALYSIS=2 };
static const unsigned ui_notes[15]={60,62,64,65,67,69,71,72,74,76,77,79,81,83,84};
static inline unsigned ui_black(unsigned note) {
 unsigned k=note%12;return k==1||k==3||k==6||k==8||k==10;
}
static inline unsigned ui_white_x(unsigned i) {return 32u+i*880u/15u;}
static inline int ui_hit(unsigned x,unsigned y) {
 if(x<32||x>=912||y<474||y>=534)return -1;
 if(y<511)for(unsigned i=1;i<15;i++)if(ui_notes[i]-ui_notes[i-1]==2) {
   unsigned center=ui_white_x(i);if(x>=center-18&&x<center+18)return (int)ui_notes[i]-1;
 }
 for(unsigned i=0;i<15;i++)if(x<ui_white_x(i+1))return (int)ui_notes[i];
 return -1;
}
static inline void ui_init(ui_model*m) {*m=(ui_model){.note=60,.effect_order=0x24
#ifdef A138_SINGLE_BLE_RECORDING
 ,.mode=3
#endif
 };}
static inline unsigned ui_touch(ui_model*m,unsigned x,unsigned y,unsigned down) {
#ifdef A138_SINGLE_BLE_RECORDING
 /* W's 25K is the control surface. HDMI consumes the committed D snapshot;
  * the retired local synth keyboard/mode controls cannot create requests. */
 (void)x;(void)y;m->old_down=!!down;return 0;
#else
 unsigned result=0;int hit=ui_hit(x,y);
 if(m->panic_latched) {m->old_down=!!down;if(!down)m->panic_latched=0;return 0;}
 if(down&&hit>=0) {
  if(!m->gate||m->note!=(unsigned)hit)result|=UI_CHANGED;
  m->note=(unsigned)hit;m->gate=1;m->keyboard=1;
 } else {
  if(m->keyboard){m->gate=0;m->keyboard=0;result|=UI_CHANGED;}
  if(down&&!m->old_down&&x>=32&&x<912) {
   if(y>=36&&y<76) {
    switch((x-32)/220){case 0:m->mode=(m->mode+1)%3;break;case 1:m->sound=(m->sound+1)%5;break;case 2:m->route=(m->route+1)%4;m->sw=(m->sw&127u)|(m->route==3?128u:0);break;case 3:m->gate^=1;break;}
    result|=UI_CHANGED;
   } else if(y>=426&&y<454) {unsigned k=(x-32)/112;if(k<8){m->sw^=1u<<k;if(k==7)m->route=(m->sw&128u)?3:0;result|=UI_CHANGED;}}
  }
 }
 m->old_down=!!down;return result;
#endif
}
static inline unsigned ui_panic(ui_model*m,unsigned epoch) {
 if(m->panic_epoch==epoch)return 0;
 m->panic_epoch=epoch;m->gate=0;m->keyboard=0;m->panic_latched=m->old_down;
 return UI_CHANGED;
}
static inline unsigned ui_active(const ui_model*m,unsigned note) {
 return ((m->held[note/32]>>(note%32))&1u)||(m->gate&&m->note==note);
}
static inline uint32_t ui_request(const ui_model*m) {return m->mode|(m->sound<<4)|(m->route<<8)|(m->gate<<12)|(m->sw<<16)|(m->note<<24);}
#endif
