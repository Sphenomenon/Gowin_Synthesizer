#include <stdint.h>
#include "probe_payload.h"

#define D ((volatile uint32_t *)0xF8000000u)
extern uint32_t __ilm_end, __bss_end, __stack_bottom, __stack_top;
extern void probe_trap(void);
volatile uint32_t probe_expected_pc;
static volatile uint32_t accumulator;
const uint32_t probe_payload[8192] __attribute__((aligned(16),section(".rodata.probe_payload"))) = {
#include "probe_payload.inc"
};

/* Only these precise instructions permit the stackless probe trap to resume.
 * a0/a1 and t0/t1 are caller-clobbered and explicitly visible to GCC here. */
#define READER(name, number) \
static __attribute__((noinline)) uint64_t name(void) { \
    register uint32_t value __asm__("a0"); \
    register uint32_t valid __asm__("a1"); \
    __asm__ volatile("li a1,1\nla t0,1f\nla t1,probe_expected_pc\nsw t0,0(t1)\n" \
        "1: csrr a0," #number "\nla t0,probe_expected_pc\nsw zero,0(t0)" \
        : "=r"(value),"=r"(valid) : : "t0","t1","t2","t3","memory"); \
    return ((uint64_t)valid<<32)|value; \
}
READER(micm,0xfc0) READER(mdcm,0xfc1) READER(mmsc,0xfc2)
READER(milmb,0x7c0) READER(mdlmb,0x7c1) READER(mcache,0x7ca)
READER(misa,0x301) READER(inhibit,0x320) READER(counteren,0x306)
READER(pmacfg0,0xbc0) READER(pmacfg1,0xbc1) READER(pmacfg2,0xbc2) READER(pmacfg3,0xbc3)
READER(cyclelo,0xb00) READER(cyclehi,0xb80)
READER(instlo,0xb02) READER(insthi,0xb82)

static uint32_t crc_payload(void) {
    volatile const uint32_t *p=probe_payload;
    uint32_t crc=0xffffffffu;
    for(uint32_t i=0;i<8192;i++) {
        uint32_t word=p[i];
        for(unsigned byte=0;byte<4;byte++) {
            crc^=word&255u;word>>=8;
            for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);
        }
        if(!(i&255u))D[9]=i;
    }
    D[9]=8192;return ~crc;
}
static uint32_t pattern(uintptr_t p) {return (uint32_t)p^0x9e3779b9u;}
static void fill(uintptr_t begin,uintptr_t end) {
    for(uintptr_t p=begin;p<end;p+=4)*(volatile uint32_t *)p=pattern(p);
}
static unsigned check(uintptr_t begin,uintptr_t end) {
    unsigned errors=0;
    for(uintptr_t p=begin;p<end;p+=4) {
        uint32_t got=*(volatile uint32_t *)p;
        if(got!=pattern(p)) {
            if(!D[42]) {D[39]=(uint32_t)p;D[40]=pattern(p);D[41]=got;}
            D[42]++;errors++;
        }
    }
    return errors;
}
static int cycles(uint64_t *out) {
    for(unsigned retry=0;retry<4;retry++) {
        uint64_t h1=cyclehi(),l=cyclelo(),h2=cyclehi();
        if((h1>>32)!=1 || (l>>32)!=1 || (h2>>32)!=1)return 0;
        if((uint32_t)h1==(uint32_t)h2) {*out=((uint64_t)(uint32_t)h1<<32)|(uint32_t)l;return 1;}
    }
    return 0;
}
static int instructions(uint64_t *out) {
    for(unsigned retry=0;retry<4;retry++) {
        uint64_t h1=insthi(),l=instlo(),h2=insthi();
        if((h1>>32)!=1 || (l>>32)!=1 || (h2>>32)!=1)return 0;
        if((uint32_t)h1==(uint32_t)h2) {*out=((uint64_t)(uint32_t)h1<<32)|(uint32_t)l;return 1;}
    }
    return 0;
}
static void wide(unsigned offset,uint64_t value) {D[offset]=(uint32_t)value;D[offset+1]=(uint32_t)(value>>32);}
#define SAMPLE(index, getter) do {uint64_t r=getter();D[index]=(uint32_t)r;if((r>>32)==1)D[14]|=1u<<((index)-16);} while(0)
void services_main(void) {
    __asm__ volatile("csrw mtvec,%0" : : "r"((uintptr_t)probe_trap) : "memory");
    uint32_t pc,sp;__asm__ volatile("auipc %0,0\nmv %1,sp" : "=r"(pc),"=r"(sp));
    D[0]=0x50524231u;D[5]=1;D[8]=1;D[11]=pc;D[12]=sp;D[13]=(uint32_t)&__stack_top;
    D[31]=(uint32_t)(uintptr_t)probe_trap;
    D[8]=2;
    SAMPLE(16,micm);SAMPLE(17,mdcm);SAMPLE(18,mmsc);SAMPLE(19,milmb);SAMPLE(20,mdlmb);
    SAMPLE(21,mcache);SAMPLE(22,misa);SAMPLE(23,inhibit);SAMPLE(24,counteren);
    if(D[18]&(1u<<30)) {SAMPLE(25,pmacfg0);SAMPLE(26,pmacfg1);SAMPLE(27,pmacfg2);SAMPLE(28,pmacfg3);}
    D[8]=3;D[32]=crc_payload();D[33]=PROBE_PAYLOAD_CRC;
    D[34]=*(volatile const uint32_t *)&probe_payload[0];
    D[35]=*(volatile const uint32_t *)&probe_payload[8191];D[36]=8192;
    if(D[32]!=PROBE_PAYLOAD_CRC || D[34]!=PROBE_PAYLOAD_FIRST || D[35]!=PROBE_PAYLOAD_LAST)D[7]|=1;
    uintptr_t dlm=((uintptr_t)&__bss_end+255u)&~(uintptr_t)255u;
    if(dlm<0xa0201000u)dlm=0xa0201000u;
    uintptr_t dlm_end=(uintptr_t)&__stack_bottom-256u;
    uintptr_t ilm=((uintptr_t)&__ilm_end+255u)&~(uintptr_t)255u;
    uintptr_t ilm_end=0xa000fffcu;
    D[8]=4;D[37]=(uint32_t)((dlm_end-dlm)/4u);D[38]=(uint32_t)((ilm_end-ilm)/4u);
    fill(dlm,dlm_end);fill(ilm,ilm_end);
    __asm__ volatile("fence iorw,iorw" ::: "memory");
    D[8]=5;
    if(check(dlm,dlm_end) | check(ilm,ilm_end))D[7]|=2;
    D[8]=6;
    uint64_t c0=0,c1=0,i0=0,i1=0;
    int ca=cycles(&c0),ia=instructions(&i0);
    for(unsigned k=0;k<4096;k++) {
        __asm__ volatile(".rept 8\naddi zero,zero,0\n.endr" ::: "memory");
        accumulator+=k;
    }
    int cb=cycles(&c1),ib=instructions(&i1);
    wide(44,c0);wide(46,c1);wide(48,c1-c0);wide(50,i0);wide(52,i1);wide(54,i1-i0);
    D[56]=(uint32_t)ca|((uint32_t)cb<<1)|((uint32_t)ia<<2)|((uint32_t)ib<<3);
    D[57]=4096;
    uintptr_t bottom=(uintptr_t)&__stack_bottom,top=(uintptr_t)&__stack_top;
    while(bottom<top && *(volatile uint32_t *)bottom==0xa55a55a5u)bottom+=4;
    D[43]=(uint32_t)(top-bottom);
    D[8]=7;D[6]=D[7] ? 0x4641494cu:0x50415353u;
    for(;;) {D[10]++;__asm__ volatile("auipc %0,0\nmv %1,sp" : "=r"(pc),"=r"(sp));D[11]=pc;D[12]=sp;}
}
