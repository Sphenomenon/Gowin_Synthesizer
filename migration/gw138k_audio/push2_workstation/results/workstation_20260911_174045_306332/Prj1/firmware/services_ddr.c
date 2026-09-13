/* Separate firmware entry for the external-DDR candidate. */
#define services_main audio_services_main
#include "services_main.c"
#undef services_main
void services_main(void) {
    volatile uint32_t *const ddr=(volatile uint32_t *)UINT32_C(0x10000000);
    volatile uint8_t *const bytes=(volatile uint8_t *)UINT32_C(0x10000000);
    volatile uint16_t *const halves=(volatile uint16_t *)UINT32_C(0x10000000);
    for(unsigned n=0;n<1024;n++) ddr[n]=UINT32_C(0x9e3779b9)*(n+1u)^UINT32_C(0xa3500000);
    a138_fence();
    for(unsigned n=0;n<1024;n++) if(ddr[n]!=(UINT32_C(0x9e3779b9)*(n+1u)^UINT32_C(0xa3500000))) fail(0xDDD00001);
    for(unsigned n=0;n<32;n++) bytes[n]=(uint8_t)(n^0x5a);
    for(unsigned n=0;n<8;n++) {
        uint32_t expected=0;
        for(unsigned lane=0;lane<4;lane++) expected|=((n*4u+lane)^0x5au)<<(lane*8u);
        if(ddr[n]!=expected) fail(0xDDD00002);
    }
    for(unsigned n=0;n<16;n++) halves[n]=(uint16_t)(0xaa00u+n);
    for(unsigned n=0;n<8;n++) if(ddr[n]!=((0xaa00u+n*2u)|((0xaa01u+n*2u)<<16))) fail(0xDDD00003);
    volatile uint32_t *const end=(volatile uint32_t *)UINT32_C(0x107ffffc);
    *end=UINT32_C(0x55aaff00);a138_fence();
    if(*end!=UINT32_C(0x55aaff00) || ddr[0]!=UINT32_C(0xaa01aa00)) fail(0xDDD00004);
    audio_services_main();
}
