/* Test-only Vex firmware: exercise the real CPU bus and audio boundary offline. */
#include <stdint.h>
#define REG(o) (*(volatile uint32_t *)(0x02000200u+(o)))
static void midi(unsigned cin,unsigned a,unsigned b){REG(4)=cin|(cin<<12)|(a<<16)|(b<<24);}
static void button(unsigned cc){midi(11,cc,127);midi(11,cc,0);}
static void phase(unsigned n){REG(0x30)=n;for(volatile unsigned i=0;i<10000;i++);}
int main(void){
    REG(0)=1;
    button(102);button(105);button(20);button(21);button(22);
    midi(11,72,63);midi(11,73,63);midi(14,1,65);midi(9,60,100);phase(1);
    button(26);phase(2);button(24);phase(3);button(25);phase(4);
    // The existing engine commits mode changes only after all release tails.
    midi(9,60,0);while(REG(0x10)&0xfc00u);
    button(23);button(103);phase(5);button(104);phase(6);
    button(102);
    for(unsigned i=0;i<5;i++){button(105+i);phase(10+i);}
    midi(9,60,0);button(27);phase(20);
    // Confirm MMIO read response alignment and the same live state as the UI.
    if((REG(0x10)&0x7f)!=7 || ((REG(0x10)>>7)&7)!=4 ||
       REG(0x1c)!=0 || REG(0x20)!=0 || REG(0x3c)<20)REG(0x34)=0xbad;
    else REG(0x34)=0x600d;
    phase(21);for(;;);
}
