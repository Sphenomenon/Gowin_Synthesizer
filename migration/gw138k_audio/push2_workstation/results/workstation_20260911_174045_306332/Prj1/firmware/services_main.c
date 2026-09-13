/* First full-system firmware: exercise actual APB services, then poll status.
 * No external commands, sound generation, GUI or Flash writes. */
#include "audio_services.h"
#define AUDIO_BASE UINT32_C(0xf8010000)
static volatile uint32_t *const diagnostic=(volatile uint32_t *)UINT32_C(0xf8000000);
static void event(unsigned kind,unsigned a,unsigned b) {
    a138_write(AUDIO_BASE,0x180,(kind<<14)|(a<<7)|b);
}
static void fail(uint32_t reason) {
    diagnostic[1]=reason;
    for(;;) { __asm__ volatile("nop"); }
}
void services_main(void) {
    uint32_t state[9],heartbeat=0;
    a138_record frame;
    const a138_cue cues[2]={{4,0x55},{16,0}};
    if(!a138_probe(AUDIO_BASE) || !(a138_read(AUDIO_BASE,A138_CAPABILITIES)&8u)) fail(0xBAD00001);
    a138_snapshot(AUDIO_BASE,state);
    for(unsigned i=2;i<9;i++) if(state[i]) fail(0xBAD00100+i);
    if(!a138_score_load(AUDIO_BASE,cues,2)) fail(0xBAD00002);
    a138_write(AUDIO_BASE,A138_SCORE_START,1);
    unsigned timeout=10000;
    while(!(a138_read(AUDIO_BASE,A138_SCORE_STATUS)&2u) && --timeout) {}
    if(!timeout || a138_read(AUDIO_BASE,A138_SCORE_LEDS)!=0) fail(0xBAD00003);
    a138_write(AUDIO_BASE,A138_RECORD_ENABLE,1);
    timeout=10000;
    while(!(a138_read(AUDIO_BASE,A138_RECORD_STATUS)&2u) && --timeout) {}
    a138_write(AUDIO_BASE,A138_RECORD_ENABLE,0);
    if(!timeout || !a138_record_try_read(AUDIO_BASE,&frame)) fail(0xBAD00004);
    /* The current physical setup has no MIDI input: verify a complete silent
     * stereo frame. Later note-injection firmware has a separate acceptance. */
    if(frame.left || frame.right) fail(0xBAD00005);
    // Drain the brief silent capture before starting a distinct CPU note test.
    while(a138_record_try_read(AUDIO_BASE,&frame)) {}
    event(2,80,0); event(3,73,0); event(2,81,7); event(4,0,64);
    event(1,60,100);
    a138_snapshot(AUDIO_BASE,state);
    uint32_t begin=state[1];
    do { a138_snapshot(AUDIO_BASE,state); } while((uint32_t)(state[1]-begin)<256u);
    if(!state[0]) fail(0xBAD00006);
    a138_write(AUDIO_BASE,A138_RECORD_ENABLE,1);
    timeout=10000;
    while(!(a138_read(AUDIO_BASE,A138_RECORD_STATUS)&2u) && --timeout) {}
    a138_write(AUDIO_BASE,A138_RECORD_ENABLE,0);
    if(!timeout || !a138_record_try_read(AUDIO_BASE,&frame) || (!frame.left && !frame.right)) fail(0xBAD00007);
    event(2,123,0);
    a138_snapshot(AUDIO_BASE,state);begin=state[1];
    while(state[0] && (uint32_t)(state[1]-begin)<48000u) a138_snapshot(AUDIO_BASE,state);
    if(state[0]) fail(0xBAD00008);
    diagnostic[1]=0x50415353;
    for(;;) {
        a138_snapshot(AUDIO_BASE,state);
        for(unsigned i=2;i<9;i++) if(state[i]) fail(0xBAD00200+i);
        diagnostic[2]=++heartbeat;
        for(volatile unsigned delay=0;delay<1000;delay++) {}
    }
}
