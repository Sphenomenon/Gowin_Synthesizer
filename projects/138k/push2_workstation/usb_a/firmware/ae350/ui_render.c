// Glyph data retained from the original ACX720 controls.c.
// Logical 960x540 UI expands 2x into a 1920x1080 RGB565 DDR page.
#include "ui_render.h"
static const uint8_t font[][7]={
 {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
 {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
 {14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
 {14,17,17,15,1,1,14},
 {14,17,17,31,17,17,17},{30,17,17,30,17,17,30},{15,16,16,16,16,16,15},
 {30,17,17,17,17,17,30},{31,16,16,30,16,16,31},{31,16,16,30,16,16,16},
 {15,16,16,19,17,17,15},{17,17,17,31,17,17,17},{14,4,4,4,4,4,14},
 {7,2,2,2,2,18,12},{17,18,20,24,20,18,17},{16,16,16,16,16,16,31},
 {17,27,21,21,17,17,17},{17,25,21,19,17,17,17},{14,17,17,17,17,17,14},
 {30,17,17,30,16,16,16},{14,17,17,17,21,18,13},{30,17,17,30,20,18,17},
 {15,16,16,14,1,1,30},{31,4,4,4,4,4,4},{17,17,17,17,17,17,14},
 {17,17,17,17,17,10,4},{17,17,17,21,21,21,10},{17,17,10,4,10,17,17},
 {17,17,10,4,4,4,4},{31,1,2,4,8,16,31}
};

typedef struct {volatile uint32_t*frame;unsigned first,end;} surface;
// Keep the clip/store loop shared: inlining it at each glyph/card call site
// exceeds the existing 16 KiB cold-start image when recording APIs are linked.
static __attribute__((noinline)) void rect(surface*f,unsigned x,unsigned y,unsigned w,unsigned h,uint16_t color) {
 unsigned first=y*2u,end=first+h*2u;
 if(first<f->first)first=f->first;
 if(end>f->end)end=f->end;
 if(first>=end)return;
 uint32_t pair=(uint32_t)color|((uint32_t)color<<16);
 volatile uint32_t*row=f->frame+first*UI_FRAME_WORDS_PER_ROW+x;
 for(unsigned j=first;j<end;j++,row+=UI_FRAME_WORDS_PER_ROW)for(unsigned i=0;i<w;i++)row[i]=pair;
}
static __attribute__((noinline)) void text(surface*f,unsigned x,unsigned y,const char*s,unsigned scale,uint16_t color) {
 for(;*s;s++,x+=6u*scale){unsigned c=(unsigned char)*s,index;
  if(c>='A'&&c<='Z')index=c-'A'+10;else if(c>='0'&&c<='9')index=c-'0';else continue;
  for(unsigned j=0;j<7;j++)for(unsigned i=0;i<5;i++)if(font[index][j]&(16u>>i))rect(f,x+i*scale,y+j*scale,scale,scale,color);
 }
}
#ifndef A138_SINGLE_BLE_RECORDING
static const char*const modes[]={"A 32 X 1","B 32 X 4","C 4 X 32","D BLUETOOTH"};
static const char*const sounds[]={"FLUTE","STRINGS","TRUMPET","MARIMBA","PIANO"};
#endif
static const char*const routes[]={"STEREO","LEFT ONLY","RIGHT ONLY","MUTE"};
static const char*const effects[]={"DELAY","CHORUS","REVERB","VIBR","GLIDE","SNAP","BEND","MUTE"};
static void number(surface*f,unsigned x,unsigned y,unsigned value,unsigned scale) {
 if(value>999)value=999;
 char s[4]={(char)('0'+value/100),(char)('0'+value/10%10),(char)('0'+value%10),0};
 text(f,x,y,s,scale,0xffff);
}
static const char*rate(const ui_model*m) {
 return !(m->clock_actual&2u)?"CLOCK WAIT":(m->clock_actual&0x34u)?"CLOCK CHANGE":(m->clock_actual&1u)?"44100 HZ":"48000 HZ";
}
static void clock_label(surface*f,const ui_model*m) {
 rect(f,210,8,168,24,0x0883);text(f,210,12,rate(m),2,0x4e17);
}
static void card(surface*f,const ui_model*m,unsigned k) {
 unsigned x=32+220*k;rect(f,x,36,208,40,0x1127);
#ifdef A138_SINGLE_BLE_RECORDING
 static const char*const labels[]={"SOURCE","CRUSH","DRIVE","SEND"};
 text(f,x+8,40,labels[k],1,0x94b4);
 if(k)number(f,x+8,54,m->d_depths[k-1],2);
 else text(f,x+8,54,"D BLUETOOTH",2,0xffff);
#else
 text(f,x+8,40,k==0?"MODE":k==1?"SOUND":k==2?"ROUTE":"LOCAL KEY HOLD",1,0x94b4);
 text(f,x+8,54,k==0?modes[m->mode&3u]:k==1?(m->sound<5?sounds[m->sound]:"UNKNOWN"):k==2?routes[m->route&3u]:(m->gate?"PLAY":"RELEASE"),2,0xffff);
#endif
}
static void effect(surface*f,const ui_model*m,unsigned k) {
#ifdef A138_SINGLE_BLE_RECORDING
 unsigned x=32+176*k,on=k<3?((m->sw>>k)&1u):0;
 rect(f,x,426,168,28,on?0x2650:0x1127);
 text(f,x+6,430,k<3?effects[k]:k==3?"MASTER VOLUME PERCENT":"OUTPUT",1,0xffff);
 if(k==3)number(f,x+6,444,m->volume*100u/32768u,1);
 else text(f,x+6,444,k<3?(on?"ON":"OFF"):routes[m->route&3u],1,on?0x4e17:0x94b4);
#else
 unsigned x=32+112*k,on=(m->sw>>k)&1u;rect(f,x,426,104,28,on?0x2650:0x1127);
 text(f,x+6,430,effects[k],1,0xffff);text(f,x+6,444,k==5?(on?"DONE":"READY"):(on?"ON":"OFF"),1,on?0x4e17:0x94b4);
#endif
}
static void chain_card(surface*f,const ui_model*m,unsigned k) {
 unsigned id=(m->effect_order>>(k*2u))&3u;
 unsigned x=32+256*k,on=id<3?((m->sw>>id)&1u):0;
 rect(f,x,474,240,40,on?0x2650:0x1127);
 text(f,x+8,480,id<3?effects[id]:"BYPASS",2,0xffff);
 text(f,x+8,500,on?"ON":"OFF",1,on?0x4e17:0x94b4);
}
static inline void white(surface*f,const ui_model*m,unsigned k) {
 unsigned x=ui_white_x(k),w=ui_white_x(k+1)-x,n=ui_notes[k],on=ui_active(m,n);
 rect(f,x+1,474,w-2,60,on?0x4e17:0xdf3c);rect(f,x+1,531,w-2,3,on?0x2650:0x94b4);
 char label[3]={"CDEFGAB"[k%7],(char)('4'+(n-60)/12),0};text(f,x+w/2-9,521,label,1,0x1127);
}
static inline void black(surface*f,const ui_model*m,unsigned k) {
 unsigned x=ui_white_x(k)-18,n=ui_notes[k]-1,on=ui_active(m,n);
 rect(f,x,474,36,37,on?0x2650:0x2148);rect(f,x+3,507,30,2,on?0x4e17:0x4aab);
}
static void headline(surface*f,const ui_model*m,unsigned touch) {
#ifdef A138_SINGLE_BLE_RECORDING
 (void)touch;rect(f,380,8,560,24,0x0883);
 text(f,380,10,m->pc_faults?"AUDIO OR INPUT ERROR":"D BLUETOOTH   25K CONTROL   LIVE ANALYSIS",1,0x94b4);
#else
 rect(f,380,8,560,24,0x0883);text(f,380,10,(m->pc_faults&255u)?"PC MIDI INPUT ERROR":(m->pc_faults&1024u)?"VOICE LIMIT REACHED":m->pc_faults?"AUDIO OR INPUT ERROR":touch?"TOUCH READY":"PC MIDI 115200   TOUCH NOT CONNECTED",1,0x94b4);
 char count[3]={(char)('0'+m->voices/10),(char)('0'+m->voices%10),0};text(f,380,22,"ACTIVE",1,0x4e17);text(f,425,22,count,1,0xffff);
 text(f,470,22,"VOLUME PERCENT",1,0x4e17);number(f,560,22,m->volume*100u/32768u,1);
#endif
}
static void render(surface*f,const ui_model*m,unsigned touch) {
 for(unsigned i=f->first*UI_FRAME_WORDS_PER_ROW;i<f->end*UI_FRAME_WORDS_PER_ROW;i++)f->frame[i]=0x08830883u;
 text(f,32,10,"AUDIO LAB",3,0xffff);clock_label(f,m);headline(f,m,touch);
 for(unsigned k=0;k<4;k++)card(f,m,k);
 // Live analysis rows 160..831 are composed by scanout from the current RTL
 // analysis page, including waveform, dual spectrum, image and level bars.
 for(unsigned k=0;k<
#ifdef A138_SINGLE_BLE_RECORDING
 5
#else
 8
#endif
 ;k++)effect(f,m,k);
 // The former performance keyboard occupied the HDMI bottom edge. Replace it
 // with the three-stage serial audio chain and its live switch states.
 text(f,32,463,"EFFECT CHAIN   INPUT TO STAGE 1 TO STAGE 2 TO STAGE 3 TO OUTPUT",1,0x94b4);
 for(unsigned k=0;k<3;k++)chain_card(f,m,k);
}
static void patch(surface*f,const ui_model*old,const ui_model*next,unsigned ot,unsigned nt) {
 if(old->clock_actual!=next->clock_actual)clock_label(f,next);
 if(ot!=nt||old->voices!=next->voices||old->pc_faults!=next->pc_faults||old->volume!=next->volume)headline(f,next,nt);
#ifdef A138_SINGLE_BLE_RECORDING
 for(unsigned k=0;k<3;k++)if(old->d_depths[k]!=next->d_depths[k])card(f,next,k+1);
 for(unsigned k=0;k<3;k++)if((old->sw^next->sw)&(1u<<k))effect(f,next,k);
 if(old->volume!=next->volume)effect(f,next,3);
 if(old->route!=next->route)effect(f,next,4);
#else
 if(old->mode!=next->mode)card(f,next,0);
 if(old->sound!=next->sound)card(f,next,1);
 if(old->route!=next->route)card(f,next,2);
 if(old->gate!=next->gate)card(f,next,3);
 for(unsigned k=0;k<8;k++)if((old->sw^next->sw)&(1u<<k))effect(f,next,k);
#endif
 for(unsigned k=0;k<3;k++)if(old->sw!=next->sw||old->effect_order!=next->effect_order)chain_card(f,next,k);
 // Keyboard repaint is intentionally removed with the old performance panel.
}
void ui_render_rows(volatile uint32_t*f,const ui_model*m,unsigned touch,unsigned first,unsigned count) {
 if(first>=UI_FRAME_ROWS || !count)return;
 if(count>UI_FRAME_ROWS-first)count=UI_FRAME_ROWS-first;
 surface s={f,first,first+count};render(&s,m,touch);
}
void ui_patch_rows(volatile uint32_t*f,const ui_model*old,const ui_model*next,unsigned ot,unsigned nt,unsigned first,unsigned count) {
 if(first>=UI_FRAME_ROWS || !count)return;
 if(count>UI_FRAME_ROWS-first)count=UI_FRAME_ROWS-first;
 surface s={f,first,first+count};patch(&s,old,next,ot,nt);
}
void ui_render(volatile uint32_t*f,const ui_model*m,unsigned touch) {
 ui_render_rows(f,m,touch,0,UI_FRAME_ROWS);
}
void ui_patch(volatile uint32_t*f,const ui_model*old,const ui_model*next,unsigned ot,unsigned nt) {
 ui_patch_rows(f,old,next,ot,nt,0,UI_FRAME_ROWS);
}
