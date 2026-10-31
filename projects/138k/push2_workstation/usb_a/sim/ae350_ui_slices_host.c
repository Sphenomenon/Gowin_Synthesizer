#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ui_render.h"

void reference_ui_render(volatile uint32_t *,const ui_model *,unsigned);
void reference_ui_patch(volatile uint32_t *,const ui_model *,const ui_model *,unsigned,unsigned);
enum { WORDS=UI_FRAME_ROWS*UI_FRAME_WORDS_PER_ROW, GUARD=32 };
static uint32_t expected[WORDS],actual_store[WORDS+2*GUARD],before[WORDS];
static uint32_t *const actual=actual_store+GUARD;
static unsigned comparisons,slices;
static void require(int ok,const char *why) {
    if(!ok){fprintf(stderr,"FAIL %s after %u slices\n",why,slices);exit(1);}
}
static void guards(void) {
    for(unsigned i=0;i<GUARD;i++)require(actual_store[i]==0xdeadbeefu && actual[WORDS+i]==0xdeadbeefu,"page guard overwritten");
}
static void compare(void) {
    require(!memcmp(expected,actual,sizeof(expected)),"full render pixel oracle differs");guards();comparisons++;
}
static void seed(ui_model *m,unsigned k) {
    ui_init(m);m->mode=k%3;m->sound=k%5;m->route=k%4;m->gate=k&1;
    m->sw=(k*73u)&255u;m->voices=(k*7u)%33u;
    m->pc_faults=k%4==0?0:k%4==1?1:k%4==2?1024:512;
    m->volume=(k*2593u)%32769u;m->effect_order=(k&1u)?0x12:0x24;m->clock_actual=(k%3==0)?0:(2u|(k&1u));
}
static void sliced_render(const ui_model *m,unsigned touch,unsigned stride) {
    for(unsigned y=0;y<UI_FRAME_ROWS;y+=stride){ui_render_rows(actual,m,touch,y,stride);slices++;guards();}
}
static void sliced_patch(const ui_model *old,const ui_model *next,unsigned ot,unsigned nt,unsigned stride) {
    for(unsigned y=0;y<UI_FRAME_ROWS;y+=stride){ui_patch_rows(actual,old,next,ot,nt,y,stride);slices++;guards();}
}
int main(void) {
    for(unsigned i=0;i<WORDS+2*GUARD;i++)actual_store[i]=0xdeadbeefu;
    for(unsigned k=0;k<12;k++) {
        ui_model m,next;seed(&m,k);seed(&next,k+1);
        reference_ui_render(expected,&m,k&1);ui_render(actual,&m,k&1);compare();
        for(unsigned i=0;i<WORDS;i++)actual[i]=0x76543210u;
        sliced_render(&m,k&1,k%3==0?2:k%3==1?7:31);compare();
        reference_ui_render(expected,&next,(k+1)&1);
        sliced_patch(&m,&next,k&1,(k+1)&1,k%2?2:17);compare();
        ui_patch(actual,&next,&m,(k+1)&1,k&1);
        reference_ui_render(expected,&m,k&1);compare();
    }
    /* Keep every word outside the requested physical rows intact, including
     * odd row/glyph boundaries, bottom clamping and unsigned overflow inputs. */
    const unsigned ranges[][2]={{0,0},{0,1},{1,1},{15,2},{71,3},{151,11},{319,2},
        {831,1},{851,3},{927,2},{1027,2},{1079,1},{1079,UINT_MAX},{1080,1},{UINT_MAX,UINT_MAX}};
    ui_model m,n;seed(&m,7);seed(&n,8);
    for(unsigned k=0;k<sizeof(ranges)/sizeof(ranges[0]);k++) {
        unsigned first=ranges[k][0],count=ranges[k][1];
        unsigned end=first<UI_FRAME_ROWS?first+(count>UI_FRAME_ROWS-first?UI_FRAME_ROWS-first:count):0;
        for(unsigned patch=0;patch<2;patch++) {
            reference_ui_render(before,&m,1);memcpy(actual,before,sizeof(before));
            if(patch){memcpy(expected,before,sizeof(expected));reference_ui_render(expected,&n,0);ui_patch_rows(actual,&m,&n,1,0,first,count);}
            else{reference_ui_render(expected,&n,0);ui_render_rows(actual,&n,0,first,count);}
            slices++;
            for(unsigned i=0;i<WORDS;i++) {
                unsigned y=i/UI_FRAME_WORDS_PER_ROW;
                require(actual[i]==(first<=y && y<end?expected[i]:before[i]),"slice modified a different row or missed a pixel");
            }
            guards();comparisons++;
        }
    }
    printf("PASS ui_slices comparisons=%u slices=%u models=12 ranges=15 words_per_page=%u\n",comparisons,slices,WORDS);
    return 0;
}
