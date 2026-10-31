/* Exercise actual MMIO decoding and rendered pixels, including W mode 3. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ui_main.c"
#include "ui_render.c"
volatile uint32_t ui_host_diagnostic[8];
enum { WORDS=UI_FRAME_ROWS*UI_FRAME_WORDS_PER_ROW, GUARD=32 };
static uint32_t store[WORDS+2*GUARD],full[WORDS],saved[WORDS];
static uint32_t *const frame=store+GUARD;
static unsigned audio[128],clock_actual=2,clock_epoch=7,audio_torn,clock_torn,epoch_torn,clock_reads,checks,pixels;
static void require(int ok,const char *why){checks++;if(!ok){fprintf(stderr,"FAIL %s checks=%u\n",why,checks);exit(1);}}
void ui_host_fail(uint32_t reason){fprintf(stderr,"firmware fail %x\n",reason);exit(1);}
void ui_host_fence(void){}
uint32_t ui_host_read(uintptr_t base,uint32_t off){
 if(base==A138_CLOCK_BASE){
  if(off==A138_CLK_ACTUAL){clock_reads++;return clock_actual^((clock_torn&&!(clock_reads&1u))?1u:0u);}
  require(off==A138_CLK_SNAPSHOT_EPOCH,"unexpected clock read");return clock_epoch+(epoch_torn&&!(clock_reads&1u));
 }
 require(base==AUDIO_BASE&&off<sizeof(audio),"unexpected source read");
 unsigned v=audio[off/4];if(audio_torn&&off==0x1a0)audio[off/4]++;return v;
}
void ui_host_write(uintptr_t base,uint32_t off,uint32_t value){
 require(base==AUDIO_BASE&&off==0x180,"unexpected write from UI truth test");
 unsigned kind=value>>14,cc=(value>>7)&127u;
#ifdef A138_SINGLE_BLE_RECORDING
 require(kind==2 && (cc==7||cc==11||cc==81||cc==1||cc==5||cc==83),"W emitted retired synth request");
#else
 (void)kind;(void)cc;
#endif
}
#ifdef A138_SINGLE_BLE_RECORDING
int a138_ble_record_firmware_submit(uint32_t opcode,uint32_t limit){(void)opcode;(void)limit;return 0;}
int a138_ble_record_firmware_poll(a138_ble_local_record_result*r){(void)r;return 0;}
int a138_ble_record_firmware_facts(a138_record_data_facts*f){(void)f;return 0;}
#endif
static void guards(void){for(unsigned n=0;n<GUARD;n++)require(store[n]==0xdeadbeefu&&frame[WORDS+n]==0xdeadbeefu,"frame guard");}
static void decode(void){
 ui_model m;ui_init(&m);clock_reads=0;
 audio[0x184/4]=(32768u<<16)|(32u<<10)|(7u<<7)|(2u<<5)|(3u<<3)|5u;
 audio[0x188/4]=(3u<<22)|1048576u;audio[0x18c/4]=1u|(64u<<7)|(127u<<14);
 audio[0x1a0/4]=9;audio[0x1b8/4]=0x1d2;audio[0x190/4]=0x12345678;
 require(read_model(&m)!=0,"committed observation ignored");
 require(m.mode==3&&m.sound==7&&m.route==2&&m.voices==32&&m.volume==32768,"state layout");
 require(m.effect_order==0x12&&m.panic_epoch==3&&m.held[0]==0x12345678,"effect/order/panic/notes layout");
 require(m.clock_actual==2,"actual 48000 clock");
#ifdef A138_SINGLE_BLE_RECORDING
 require(m.d_depths[0]==1&&m.d_depths[1]==64&&m.d_depths[2]==127&&m.sw==5,"D depths use committed options only");
 ui_model touch_before=m;ui_touch(&m,40,50,1);ui_touch(&m,260,50,1);ui_touch(&m,400,500,1);
 require(m.mode==touch_before.mode&&m.sound==touch_before.sound&&!m.gate&&!m.keyboard,"W retains phantom local synth controls");
 ui_control_job c={0};control_submit(&c,0,&m);require(control_step(&c)==1,"bounded W control");
#endif
 clock_actual=3;clock_reads=0;require(read_model(&m)!=0&&m.clock_actual==3,"physical 44100 ignored");
 clock_torn=1;clock_reads=0;read_model(&m);require(m.clock_actual==0,"torn rate presented as valid");clock_torn=0;
 epoch_torn=1;clock_reads=0;read_model(&m);require(m.clock_actual==0,"torn epoch presented as valid");epoch_torn=0;
 clock_actual=0x22;clock_reads=0;read_model(&m);require(!strcmp(rate(&m),"CLOCK CHANGE"),"faulted actual clock claimed valid");
 clock_actual=2;clock_reads=0;read_model(&m);
 ui_model before=m;audio[0x1b8/4]=0x124;audio[0x184/4]=0;audio[0x18c/4]=0;audio[0x188/4]=4u<<22;audio_torn=1;
 read_model(&m);audio_torn=0;
 require(m.panic_epoch==4&&!m.gate&&m.mode==before.mode&&m.volume==before.volume&&m.effect_order==before.effect_order,"torn parameter snapshot mixed states or hid PANIC");
#ifdef A138_SINGLE_BLE_RECORDING
 require(!memcmp(m.d_depths,before.d_depths,sizeof(m.d_depths)),"torn D depths");
#endif
}
/* Independent digit glyphs check displayed depth/volume values, not only a
 * model struct. Every RGB565 pair in each expected glyph cell is checked. */
static void digits(unsigned x,unsigned y,unsigned value){
 static const unsigned glyph[10][7]={{14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},{30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},{14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},{14,17,17,15,1,1,14}};
 for(unsigned k=0;k<3;k++){
  unsigned digit=k==0?value/100:k==1?value/10%10:value%10;
  for(unsigned row=0;row<7;row++)for(unsigned col=0;col<5;col++)for(unsigned dy=0;dy<4;dy++)for(unsigned dx=0;dx<2;dx++){
   uint32_t expect=(glyph[digit][row]&(16u>>col))?0xffffffffu:0x11271127u;
   require(frame[(y*2+row*4+dy)*960+x+k*12+col*2+dx]==expect,"displayed committed numeric value");pixels++;
  }
 }
}
static void rendering(void){
 for(unsigned k=0;k<WORDS+2*GUARD;k++)store[k]=0xdeadbeefu;
 ui_model old,next;ui_init(&old);old.mode=3;old.sound=7;old.clock_actual=2;old.volume=32768;old.sw=5;
 old.d_depths[0]=1;old.d_depths[1]=64;old.d_depths[2]=127;
 ui_render(frame,&old,0);guards();
#ifdef A138_SINGLE_BLE_RECORDING
 digits(260,54,1);digits(480,54,64);digits(700,54,127);
#endif
 for(unsigned k=0;k<24;k++){
  next=old;next.mode=k&3u;next.sound=k%8;next.route=k%4;next.sw=(k*37)&255;next.volume=(k*1423)%32769;
  next.clock_actual=k%3==0?0:2u|(k&1u);next.effect_order=(k&1u)?0x12:0x3e;
  for(unsigned j=0;j<3;j++)next.d_depths[j]=(k*17+j*33)%128;
  memcpy(saved,frame,sizeof(saved));ui_render(full,&next,k&1u);
  for(unsigned row=0;row<UI_FRAME_ROWS;row+=2)ui_patch_rows(frame,&old,&next,(k+1)&1u,k&1u,row,2);
  require(!memcmp(frame,full,sizeof(full)),"patch differs from full render");
  require(!memcmp(frame+160*960,saved+160*960,(832-160)*960*sizeof(uint32_t)),"UI patch covers live wave/XY/spectrum rows");
  guards();old=next;
 }
 old.mode=~0u;old.sound=~0u;old.route=~0u;ui_render(frame,&old,0);guards();
}
int main(void){decode();rendering();printf("PASS ui_truth checks=%u pixel_values=%u role=%s actual_ui_main=1 analysis_rows_preserved=672\n",checks,pixels,
#ifdef A138_SINGLE_BLE_RECORDING
 "W"
#else
 "M"
#endif
 );return 0;}
