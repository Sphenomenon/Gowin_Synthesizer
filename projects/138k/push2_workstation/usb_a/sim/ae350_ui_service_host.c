#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ui_main.c"
void reference_ui_render(volatile uint32_t*,const ui_model*,unsigned);
void reference_ui_patch(volatile uint32_t*,const ui_model*,const ui_model*,unsigned,unsigned);
enum { WORDS=UI_FRAME_ROWS*UI_FRAME_WORDS_PER_ROW };
volatile uint32_t ui_host_diagnostic[8];
static uint32_t pixels[2][WORDS],saved[WORDS],gold[WORDS],before_back[WORDS];
static unsigned reads,writes,fences,checks,steps,max_io,publications,frame_counter,voices;
static unsigned ui_staged=0x10000000u,ui_front=0x10000000u,ui_pending,ui_visible,ui_next_visible,ui_presented,ui_commits;
static unsigned ui_touch_status,ui_touch_xy,ui_touch_sequence;
static unsigned audio[128],record_enabled,record_valid,record_count,record_index;
static a138_record records[1100],record_head;
static unsigned event_count,events[256],token_results[32],result_count;
static FILE *transcript;
static const uint32_t *expected_publication;
static unsigned expected_page,allow_publish,touch_torn,audio_torn;
static void input_touch(unsigned,unsigned,unsigned,unsigned);
static void require(int ok,const char*why) {
 checks++;if(!ok){fprintf(stderr,"FAIL %s step=%u checks=%u\n",why,steps,checks);exit(1);}
}
void ui_host_fail(uint32_t code) {fprintf(stderr,"firmware fail %08x\n",code);exit(1);}
void ui_host_fence(void) {fences++;}
static void frame_commit(void) {
 fprintf(transcript,"F\n");
 if(ui_pending){ui_front=ui_staged;ui_visible=ui_next_visible;ui_pending=0;ui_presented=1;ui_commits++;}
}
static unsigned ui_response(unsigned off) {
 switch(off) {
 case 0:return 0x55493338u;case 4:return ui_pending|(ui_visible<<1)|(ui_presented<<2);
 case 8:return ui_front;case 12:return ui_commits;case 16:return ui_staged;case 24:return ui_next_visible;
 case 32:return ui_touch_status;case 36:return ui_touch_xy;case 40:return ui_touch_sequence;
 default:require(0,"unknown UI read");return 0;
 }
}
uint32_t ui_host_read(uintptr_t base,uint32_t off) {
 reads++;
 if(base==UI_BASE){unsigned value=ui_response(off);fprintf(transcript,"R %x %x\n",off,value);if(off==40&&touch_torn)input_touch(ui_touch_status&1u,ui_touch_status>>1,ui_touch_xy&65535u,ui_touch_xy>>16);return value;}
 require(base==AUDIO_BASE && off/4<128,"unknown audio read");
 if(off==A138_RECORD_STATUS)return record_valid|(record_count?2u:0u);
 if(off==A138_RECORD_SEQUENCE)return record_head.sequence;
 if(off==A138_RECORD_LEFT)return (uint32_t)record_head.left;
 if(off==A138_RECORD_RIGHT)return (uint32_t)record_head.right;
 unsigned value=audio[off/4];if(off==0x1a0 && audio_torn)audio[off/4]++;return value;
}
void ui_host_write(uintptr_t base,uint32_t off,uint32_t value) {
 writes++;
 if(base==UI_BASE) {
  require(!ui_pending,"write while real publication pending");
  if(off==16){require(value==0x10000000u||value==0x10400000u,"invalid UI base");ui_staged=value;}
  else if(off==24){require(value<2,"invalid visibility");ui_next_visible=value;}
  else if(off==20){
   require(value==1,"invalid present command");
   if(expected_publication) {
    require(allow_publish,"publication before final slice");
    require(ui_staged==page_base(expected_page),"wrong frozen publication page");
    require(!memcmp(pixels[expected_page],expected_publication,sizeof(gold)),"published page differs from independent historical pixels");
   }
   ui_pending=1;publications++;
  } else require(0,"unknown UI write");
  fprintf(transcript,"W %x %x\n",off,value);return;
 }
 require(base==AUDIO_BASE && off/4<128,"unknown audio write");
 if(off==A138_SNAPSHOT){audio[A138_STATE_BASE/4]=voices;audio[A138_STATE_BASE/4+1]=frame_counter;return;}
 if(off==A138_RECORD_ENABLE){record_enabled=value;return;}
 if(off==A138_RECORD_POP){require(record_count && !record_valid,"invalid record POP");record_head=records[record_index++];record_count--;record_valid=1;return;}
 if(off==A138_RECORD_RELEASE){require(record_valid,"invalid record RELEASE");record_valid=0;return;}
 if(off==0x180){require(event_count<256,"event log capacity");events[event_count++]=value;return;}
 if(off==0x1a8 && (value&192u)){require(result_count<32,"result log capacity");token_results[result_count++]=value;}
 audio[off/4]=value;
}
static void input_touch(unsigned attached,unsigned down,unsigned x,unsigned y) {
 ui_touch_status=attached|(down<<1);ui_touch_xy=x|(y<<16);ui_touch_sequence++;
 fprintf(transcript,"I %x %x\n",ui_touch_status,ui_touch_xy);
}
static void init_runtime(ui_runtime*r) {
 fprintf(transcript,"Z\n");ui_staged=ui_front=0x10000000u;ui_pending=ui_visible=ui_next_visible=ui_presented=ui_commits=0;
 ui_touch_status=ui_touch_xy=ui_touch_sequence=0;expected_publication=0;touch_torn=audio_torn=0;
 *r=(ui_runtime){.valid={1,1},.revision=1,.shown=1};ui_init(&r->model);
 for(unsigned p=0;p<2;p++){r->frame[p]=pixels[p];r->pages[p]=r->model;ui_render(pixels[p],&r->model,0);}
 memset(audio,0,sizeof(audio));audio[0x1a0/4]=1;runtime_flags=0;
}
static void arm_oracle(const ui_model*m,unsigned touch,unsigned page) {
 reference_ui_render(gold,m,touch);expected_publication=gold;expected_page=page;allow_publish=0;
}
static void render_job(ui_draw_job*j,ui_runtime*r) {
 unsigned old_front=r->front;memcpy(saved,pixels[old_front],sizeof(saved));
 while(!j->present.active) {
  unsigned before=reads+writes,first=j->row*UI_FRAME_WORDS_PER_ROW,end=(j->row+UI_SLICE_ROWS)*UI_FRAME_WORDS_PER_ROW;
  memcpy(before_back,pixels[j->page],sizeof(before_back));allow_publish=j->row+UI_SLICE_ROWS>=UI_FRAME_ROWS;
  require(draw_step(j,r->frame,r->pages,r->page_touch,r->valid,&r->front,&r->shown)>=0,"draw step failed");
  require(reads+writes-before<=5,"draw step exceeded MMIO bound");
  require(!memcmp(before_back,pixels[j->page],first*sizeof(uint32_t)) && !memcmp(before_back+end,pixels[j->page]+end,(WORDS-end)*sizeof(uint32_t)),"draw step wrote outside its two rows");
  require(!memcmp(saved,pixels[old_front],sizeof(saved)),"drawing dirtied front page");steps++;
 }
}
static void finish_job(ui_draw_job*j,ui_runtime*r) {
 unsigned p=publications;for(unsigned n=0;n<30;n++) {
  unsigned before=reads+writes;require(draw_step(j,r->frame,r->pages,r->page_touch,r->valid,&r->front,&r->shown)==0,"publication retired without real commit");
  require(reads+writes-before==1 && publications==p,"publication poll resubmitted or did more work");
  require(page_base(r->front)==ui_front,"software front changed before real acknowledgement");steps++;
 }
 frame_counter+=200000;frame_commit(); // Slow CPU: hardware commits without a CPU poll.
 require(draw_step(j,r->frame,r->pages,r->page_touch,r->valid,&r->front,&r->shown)==1,"real publication ACK missing");steps++;
}
static void drawing_cases(void) {
 ui_runtime r;init_runtime(&r);ui_model a=r.model,b=r.model;a.mode=1;a.sound=2;a.sw=7;b.mode=2;b.route=2;b.voices=19;b.sw=255;
 require(draw_begin(&r.drawing,r.front,r.pages,r.page_touch,r.valid,&a,0,2)==0,"begin A");arm_oracle(&a,0,1);
 for(unsigned n=0;n<7;n++)require(draw_step(&r.drawing,r.frame,r.pages,r.page_touch,r.valid,&r.front,&r.shown)==0,"early slice");
 a=b; // Mutation of caller model must not mutate the frozen job.
 render_job(&r.drawing,&r);finish_job(&r.drawing,&r);require(r.front==1&&r.shown==2,"first commit identity");
 require(draw_begin(&r.drawing,r.front,r.pages,r.page_touch,r.valid,&b,1,3)==0,"begin B");arm_oracle(&b,1,0);
 for(unsigned n=0;n<37;n++)draw_step(&r.drawing,r.frame,r.pages,r.page_touch,r.valid,&r.front,&r.shown);
 draw_cancel(&r.drawing,r.valid);require(!r.drawing.active && !r.valid[0] && r.front==1,"partial cancel reused dirty cache");
 b.sound=4;require(draw_begin(&r.drawing,r.front,r.pages,r.page_touch,r.valid,&b,1,4)==0 && r.drawing.full,"cancel did not require full redraw");
 arm_oracle(&b,1,0);render_job(&r.drawing,&r);draw_cancel(&r.drawing,r.valid);
 require(r.drawing.active && r.drawing.present.active && r.drawing.cancelled,"accepted publication pretended cancelled");
 finish_job(&r.drawing,&r);require(r.front==0 && r.shown==2,"cancelled accepted job advanced shown revision");
 require(draw_begin(&r.drawing,r.front,r.pages,r.page_touch,r.valid,&b,1,4)==0,"post-cancel redraw missing");
 arm_oracle(&b,1,1);render_job(&r.drawing,&r);finish_job(&r.drawing,&r);require(r.shown==4,"latest update lost after cancel");
 expected_publication=0;
}
static void capture_cases(void) {
 ui_capture_job c={0};result_count=0;record_count=7;record_index=0;record_valid=0;
 for(unsigned n=0;n<1100;n++)records[n]=(a138_record){.sequence=n+90,.left=(int)n*13,.right=-(int)n*17};
 capture_request(&c,1);capture_step(&c);require(c.token==1 && !record_enabled && !result_count,"capture start published result");
 for(unsigned n=0;n<8;n++){unsigned before=reads+writes;capture_step(&c);require(reads+writes-before<=6,"capture drain not bounded");}
 require(c.state==2 && record_enabled && !record_count,"old capture did not drain");
 capture_request(&c,2);capture_request(&c,3); // latest request retained behind immutable token1
 for(unsigned n=0;n<25;n++){unsigned before=reads+writes;capture_step(&c);require(reads+writes-before==1 && !result_count,"capture wait blocked/published early");}
 record_count=9;record_index=0;
 while(c.state){unsigned before=reads+writes;capture_step(&c);require(reads+writes-before<=6,"capture finish not bounded");}
 require(result_count==1 && (token_results[0]&255u)==65 && ((token_results[0]>>8)&255u)==4,"capture token/count mixed");
 require(c.pending && c.pending_token==3,"new capture request lost");capture_step(&c);require(c.token==3,"latest capture did not start");
 c.state=2;c.timeout=1;record_count=0;capture_step(&c);capture_step(&c);
 require((token_results[1]&255u)==131 && !record_enabled,"capture timeout did not fail closed");
 c=(ui_capture_job){.state=1,.token=4,.left=2,.timeout=5};record_count=3;record_index=0;
 capture_step(&c);capture_step(&c);capture_step(&c);require((token_results[2]&255u)==132,"capture drain bound did not fail");record_count=record_valid=0;
}
static void control_cases(void) {
 ui_control_job c={0};ui_model old,next,gate;ui_init(&old);next=old;next.mode=1;next.gate=1;
 event_count=0;voices=4;frame_counter=0xfffffff0u;control_submit(&c,&old,&next);
 require(control_step(&c)==0 && event_count==1 && events[0]==((2u<<14)|(123u<<7)),"mode release did not start alone");
 gate=old;gate.gate=1;gate.note=67;control_submit(&c,&old,&gate);
 require(c.target.mode==1 && c.target.note==67,"new gate erased waiting mode request");
 for(unsigned n=0;n<40;n++){unsigned before=reads+writes;frame_counter+=100;require(control_step(&c)==0 && reads+writes-before==10 && event_count==1,"release step waited or emitted early command");}
 control_panic(&c);voices=0;require(control_step(&c)==1 && !c.active,"release real completion did not retire");
 for(unsigned n=0;n<event_count;n++)require((events[n]>>14)!=1,"PANIC resurrected queued Note On");
 c=(ui_control_job){0};event_count=0;voices=2;control_submit(&c,&old,&next);control_step(&c);frame_counter+=48000;
 require(control_step(&c)==-1 && event_count==1,"release deadline/wrap failed");voices=0;
}
static void service_loop_cases(void) {
 ui_runtime r;init_runtime(&r);r.front=(ui_front==0x10400000u);r.sequence=ui_touch_sequence;r.capture.seen=0;
 // All page bytes initially equal, including the currently published page.
 ui_model a=r.model,b=r.model;a.mode=1;a.sound=2;a.sw=5;a.voices=7;b.mode=2;b.route=1;b.sound=4;b.sw=3;b.voices=11;
 audio[0x184/4]=(a.mode<<3)|(a.sound<<7)|(a.route<<5)|(a.voices<<10)|(a.sw&7u);
 unsigned target_publications=publications+1;arm_oracle(&a,0,r.front^1u);memcpy(saved,pixels[r.front],sizeof(saved));
 for(unsigned n=0;n<UI_FRAME_ROWS/UI_SLICE_ROWS;n++) {
  unsigned before=reads+writes;
  if(n==20){audio[0x184/4]=(b.mode<<3)|(b.sound<<7)|(b.route<<5)|(b.voices<<10)|(b.sw&7u);audio[0x1a0/4]++;}
  allow_publish=n+1==UI_FRAME_ROWS/UI_SLICE_ROWS;
  ui_service_step(&r);unsigned io=reads+writes-before;if(io>max_io)max_io=io;
  require(io<=50,"actual service iteration MMIO work exceeded bound");require(!memcmp(saved,pixels[r.front],sizeof(saved)),"actual iteration dirtied front");steps++;
 }
 require(publications==target_publications && r.drawing.target.mode==a.mode && r.revision!=r.drawing.revision,"new model mixed into active job/lost revision");
 frame_counter+=1000000;frame_commit();ui_service_step(&r); // retires A; B starts next iteration
 arm_oracle(&b,0,r.front^1u);allow_publish=0;target_publications=publications+1;
 for(unsigned n=0;n<UI_FRAME_ROWS/UI_SLICE_ROWS;n++){allow_publish=n+1==UI_FRAME_ROWS/UI_SLICE_ROWS;ui_service_step(&r);steps++;}
 require(publications==target_publications,"latest model did not get follow-up job");frame_commit();ui_service_step(&r);
 require(r.shown==r.revision && !r.drawing.active && !memcmp(pixels[r.front],gold,sizeof(gold)),"latest model never became coherent front");
 // Torn touch sampling still services a pending draw/capture on each iteration.
 input_touch(1,0,0,0);expected_publication=0;r.revision++;r.capture=(ui_capture_job){.state=2,.token=5,.timeout=1000};
 touch_torn=1;for(unsigned n=0;n<100;n++){ui_service_step(&r);steps++;}touch_torn=0;
 require(r.drawing.active && r.drawing.row==200 && r.capture.timeout==900,"torn input starved bounded jobs");
 draw_cancel(&r.drawing,r.valid);r.capture.state=0;
 // A PANIC already visible in the committed snapshot revokes a queued local
 // Note On before the same actual service iteration is allowed to apply it.
 for(unsigned tear=1;tear<=3;tear++) {
  init_runtime(&r);event_count=0;voices=1;ui_model request=r.model;request.mode=1;request.gate=1;
  control_submit(&r.control,&r.model,&request);control_step(&r.control);voices=0;
  require(draw_begin(&r.drawing,r.front,r.pages,r.page_touch,r.valid,&request,0,9)==0,"PANIC partial draw setup");
  draw_step(&r.drawing,r.frame,r.pages,r.page_touch,r.valid,&r.front,&r.shown);
  audio[0x188/4]=1u<<22;touch_torn=tear&1u;audio_torn=tear>>1;
  ui_service_step(&r);touch_torn=audio_torn=0;steps++;
  for(unsigned n=0;n<event_count;n++)require((events[n]>>14)!=1,"actual iteration resurrected queued Note On after observed PANIC");
  require(r.model.panic_epoch==1 && !r.control.active,"actual iteration did not observe PANIC before release completion");
  require(r.revision==2 && r.drawing.active && r.drawing.revision==2 && r.drawing.target.panic_epoch==1 && !r.model.gate,"torn PANIC lost model revision/redraw");
  require(r.drawing.full && r.drawing.row==UI_SLICE_ROWS && !r.valid[1],"PANIC reused partial back cache");
 }
}
int main(int argc,char**argv) {
 require(argc==2,"transcript path missing");transcript=fopen(argv[1],"w");require(transcript!=0,"transcript open");
 drawing_cases();capture_cases();control_cases();service_loop_cases();fclose(transcript);
 printf("PASS ui_service checks=%u steps=%u publications=%u max_iteration_MMIO=%u fences=%u capture_results=%u actual_ui_main=1\n",checks,steps,publications,max_io,fences,result_count);return 0;
}
