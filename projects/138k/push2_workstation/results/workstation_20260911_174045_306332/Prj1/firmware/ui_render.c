// Glyph data retained from the original ACX720 controls.c.
// Logical 800x480 UI expands 2x into a 1920x1080 RGB565 DDR page.
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

static void rect(volatile uint32_t*f,unsigned x,unsigned y,unsigned w,unsigned h,uint16_t color) {
 uint32_t pair=(uint32_t)color|((uint32_t)color<<16);volatile uint32_t*row=f+y*1920u+x;
 for(unsigned j=0;j<h*2u;j++,row+=960u)for(unsigned i=0;i<w;i++)row[i]=pair;
}
static void text(volatile uint32_t*f,unsigned x,unsigned y,const char*s,unsigned scale,uint16_t color) {
 for(;*s;s++,x+=6u*scale){unsigned c=(unsigned char)*s,index;
  if(c>='A'&&c<='Z')index=c-'A'+10;else if(c>='0'&&c<='9')index=c-'0';else continue;
  for(unsigned j=0;j<7;j++)for(unsigned i=0;i<5;i++)if(font[index][j]&(16u>>i))rect(f,x+i*scale,y+j*scale,scale,scale,color);
 }
}
static const char*const modes[]={"A 32 X 1","B 32 X 4","C 4 X 32"};
static const char*const sounds[]={"FLUTE","STRINGS","TRUMPET","MARIMBA","PIANO"};
static const char*const routes[]={"STEREO","LEFT ONLY","RIGHT ONLY","MUTE"};
static const char*const effects[]={"DELAY","CHORUS","REVERB","VIBR","GLIDE","SNAP","BEND","MUTE"};
static void card(volatile uint32_t*f,const ui_model*m,unsigned k) {
 unsigned x=32+220*k;rect(f,x,36,208,40,0x1127);
 text(f,x+8,40,k==0?"MODE":k==1?"SOUND":k==2?"ROUTE":"LOCAL KEY HOLD",1,0x94b4);
 text(f,x+8,54,k==0?modes[m->mode]:k==1?sounds[m->sound]:k==2?routes[m->route]:(m->gate?"PLAY":"RELEASE"),2,0xffff);
}
static void effect(volatile uint32_t*f,const ui_model*m,unsigned k) {
 unsigned x=32+112*k,on=(m->sw>>k)&1u;rect(f,x,426,104,28,on?0x2650:0x1127);
 text(f,x+6,430,effects[k],1,0xffff);text(f,x+6,444,k==5?(on?"DONE":"READY"):(on?"ON":"OFF"),1,on?0x4e17:0x94b4);
}
static void chain_card(volatile uint32_t*f,const ui_model*m,unsigned k) {
 static const char*const names[]={"DELAY","CHORUS","REVERB"};
 unsigned x=32+256*k,on=(m->sw>>k)&1u;
 rect(f,x,474,240,40,on?0x2650:0x1127);
 text(f,x+8,480,names[k],2,0xffff);
 text(f,x+8,500,on?"ON":"OFF",1,on?0x4e17:0x94b4);
}
static void white(volatile uint32_t*f,const ui_model*m,unsigned k) {
 unsigned x=ui_white_x(k),w=ui_white_x(k+1)-x,n=ui_notes[k],on=ui_active(m,n);
 rect(f,x+1,474,w-2,60,on?0x4e17:0xdf3c);rect(f,x+1,531,w-2,3,on?0x2650:0x94b4);
 char label[3]={"CDEFGAB"[k%7],(char)('4'+(n-60)/12),0};text(f,x+w/2-9,521,label,1,0x1127);
}
static void black(volatile uint32_t*f,const ui_model*m,unsigned k) {
 unsigned x=ui_white_x(k)-18,n=ui_notes[k]-1,on=ui_active(m,n);
 rect(f,x,474,36,37,on?0x2650:0x2148);rect(f,x+3,507,30,2,on?0x4e17:0x4aab);
}
static void headline(volatile uint32_t*f,const ui_model*m,unsigned touch) {
 rect(f,380,8,560,24,0x0883);text(f,380,10,(m->pc_faults&255u)?"PC MIDI INPUT ERROR":(m->pc_faults&1024u)?"VOICE LIMIT REACHED":m->pc_faults?"AUDIO OR INPUT ERROR":touch?"TOUCH READY":"PC MIDI 115200   TOUCH NOT CONNECTED",1,0x94b4);
 char count[3]={(char)('0'+m->voices/10),(char)('0'+m->voices%10),0};text(f,380,22,"ACTIVE",1,0x4e17);text(f,425,22,count,1,0xffff);
}
void ui_render(volatile uint32_t*f,const ui_model*m,unsigned touch) {
 for(unsigned i=0;i<1036800;i++)f[i]=0x08830883u;
 text(f,32,10,"AUDIO LAB",3,0xffff);text(f,210,12,"AE350 48K",2,0x4e17);headline(f,m,touch);
 for(unsigned k=0;k<4;k++)card(f,m,k);
 // Live analysis rows 160..831 are composed by scanout from the current RTL
 // analysis page, including waveform, dual spectrum, image and level bars.
 for(unsigned k=0;k<8;k++)effect(f,m,k);
 // The former performance keyboard occupied the HDMI bottom edge. Replace it
 // with the three-stage serial audio chain and its live switch states.
 text(f,32,463,"EFFECT CHAIN   DELAY -> CHORUS -> REVERB",1,0x94b4);
 for(unsigned k=0;k<3;k++)chain_card(f,m,k);
}
void ui_patch(volatile uint32_t*f,const ui_model*old,const ui_model*next,unsigned ot,unsigned nt) {
 if(ot!=nt||old->voices!=next->voices||old->pc_faults!=next->pc_faults)headline(f,next,nt);
 if(old->mode!=next->mode)card(f,next,0);
 if(old->sound!=next->sound)card(f,next,1);
 if(old->route!=next->route)card(f,next,2);
 if(old->gate!=next->gate)card(f,next,3);
 for(unsigned k=0;k<8;k++)if((old->sw^next->sw)&(1u<<k))effect(f,next,k);
 for(unsigned k=0;k<3;k++)if((old->sw^next->sw)&(1u<<k))chain_card(f,next,k);
 // Keyboard repaint is intentionally removed with the old performance panel.
}
