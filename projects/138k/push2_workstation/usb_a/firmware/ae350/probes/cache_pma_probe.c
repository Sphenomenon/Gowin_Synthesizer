/* Explicit cache/PMA probe. See CACHE_PMA_PROBE.md for pinned sources,
 * address ownership, maintenance semantics and remaining hard-IP evidence. */
#include <stdint.h>
#define D ((volatile uint32_t *)0xf8000000u)
#define PAGE 0x1000u
#define ALIAS 0x4000u
#define BYTES 4096u
#define LINE 32u
#define READ(csr) ({uint32_t v;__asm__ volatile("csrr %0," #csr:"=r"(v)::"memory");v;})
#define WRITE(csr,v) __asm__ volatile("csrw " #csr ",%0"::"r"((uint32_t)(v)):"memory")
#define FENCE() __asm__ volatile("fence iorw,iorw":::"memory")
extern void cache_probe_trap(void);
extern uint32_t cache_page_call(void);
volatile uint32_t cache_saved_addrs[2],cache_pma_armed;
static const uint32_t cache_contract_words[3] __attribute__((used,section(".rodata.cache_contract")))={BYTES,PAGE,ALIAS};
static uint32_t saved_cfg[4],saved_addr[16];
static void command(uint32_t address,uint32_t op) {
    WRITE(0x7cb,address);WRITE(0x7cc,op);D[46]++;
}
static uint32_t addr_read(unsigned n) {
#define R(n,csr) case n:return READ(csr);
    switch(n) {
    R(0,0xbd0) R(1,0xbd1) R(2,0xbd2) R(3,0xbd3)
    R(4,0xbd4) R(5,0xbd5) R(6,0xbd6) R(7,0xbd7)
    R(8,0xbd8) R(9,0xbd9) R(10,0xbda) R(11,0xbdb)
    R(12,0xbdc) R(13,0xbdd) R(14,0xbde) R(15,0xbdf)
    default:return 0;
    }
#undef R
}
static uint32_t capacity(uint32_t cfg) {
    unsigned sets=cfg&7u,ways=((cfg>>3)&7u)+1u,line=(cfg>>6)&7u;
    if(sets>=7 || !line || line>5)return 0;
    return (1u<<(sets+6u)) * ways * (1u<<(line+2u));
}
static uint32_t pattern(unsigned n) {return 0x9357a100u ^ (n<<9) ^ n;}
static int equal(uint32_t expected,uint32_t actual,unsigned bit) {
    if(expected==actual)return 1;
    if(!D[7]) {D[52]=expected;D[53]=actual;}
    D[7]|=1u<<bit;return 0;
}
#define CHECK(e,a,b) do {if(!equal((e),(a),(b)))goto cleanup;}while(0)
void services_main(void) {
    uint32_t pc,sp,initial=0;int configured=0,cctl_ok=0;
    volatile uint32_t *cached=(volatile uint32_t *)PAGE,*shared=(volatile uint32_t *)ALIAS;
    __asm__ volatile("csrw mtvec,%0"::"r"((uintptr_t)cache_probe_trap):"memory");
    __asm__ volatile("auipc %0,0\nmv %1,sp":"=r"(pc),"=r"(sp));
    D[0]=0x43434831u;D[5]=0x43414331u;D[8]=1;D[11]=pc;D[12]=sp;
    D[16]=READ(0xfc0);D[17]=READ(0xfc1);D[18]=READ(0xfc2);
    initial=READ(0x7ca);D[19]=initial;D[22]=capacity(D[16]);D[23]=capacity(D[17]);
    D[24]=((D[16]&0x1ffu)<<16)|(D[17]&0x1ffu);
    volatile const uint32_t *layout=cache_contract_words;
    D[48]=layout[0];D[49]=layout[1];D[50]=layout[2];
    CHECK(0,initial&3u,0);
    /* Prefetch/write-around/coherence are outside this minimal test. */
    CHECK(0,initial&((3u<<9)|(3u<<13)|(1u<<19)),0);
    CHECK(32768u,D[22],1);CHECK(32768u,D[23],1);
    CHECK(0xdau,D[16]&0x1ffu,1);CHECK(0xdau,D[17]&0x1ffu,1);
    CHECK((1u<<30)|(1u<<16),D[18]&((1u<<30)|(1u<<16)),2);
    cctl_ok=1;D[54]=1;D[55]=1;D[8]=2;
    saved_cfg[0]=READ(0xbc0);saved_cfg[1]=READ(0xbc1);
    saved_cfg[2]=READ(0xbc2);saved_cfg[3]=READ(0xbc3);
    for(unsigned i=0;i<4;i++) {D[25+i]=saved_cfg[i];CHECK(0,saved_cfg[i],3);}
    for(unsigned i=0;i<16;i++)saved_addr[i]=addr_read(i);
    cache_saved_addrs[0]=saved_addr[0];cache_saved_addrs[1]=saved_addr[1];
    D[29]=saved_addr[0];D[30]=saved_addr[1];
    /* Cold loader has never enabled cache. Invalidate all D and every I index,
     * before altering attributes; no dirty shared data is discarded. */
    command(0,23);
    for(unsigned i=0;i<32768u;i+=LINE)command(i,24);
    FENCE();D[8]=3;
    /* Isolated PL scratch aliases, not DDR/UI/PCM or ILM/DLM. */
    for(unsigned i=0;i<BYTES/4;i++)shared[i]=pattern(i);
    shared[0]=0x01100513u;shared[1]=0x00008067u; /* addi a0,zero,17; ret */
    FENCE();
    cache_pma_armed=1;configured=1;
    WRITE(0xbd0,0x5ffu);WRITE(0xbd1,0x11ffu);
    WRITE(0xbc0,0x0f2fu);FENCE();
    D[31]=READ(0xbc0);D[32]=READ(0xbd0);D[33]=READ(0xbd1);
    CHECK(0x0f2fu,D[31],4);CHECK(0x5ffu,D[32],4);CHECK(0x11ffu,D[33],4);
    D[8]=4;WRITE(0x7ca,initial|3u);D[20]=READ(0x7ca);CHECK(initial|3u,D[20],5);
    FENCE();
    for(unsigned i=8;i<BYTES/4;i++) {CHECK(pattern(i),cached[i],6);cached[i]=~pattern(i);D[9]=i;}
    D[8]=5;D[34]=cached[8];D[35]=shared[8];
    CHECK(~pattern(8),D[34],7);CHECK(pattern(8),D[35],7);
    for(unsigned i=0;i<BYTES;i+=LINE)command(PAGE+i,1);
    FENCE();D[36]=shared[8];CHECK(~pattern(8),D[36],8);
    /* External agent publishes through the explicitly uncached alias. */
    D[8]=6;shared[8]=0x6789abcdu;FENCE();D[37]=shared[8];D[38]=cached[8];
    CHECK(0x6789abcdu,D[37],9);CHECK(~pattern(8),D[38],9);
    command(PAGE+32,0);FENCE();D[39]=cached[8];CHECK(0x6789abcdu,D[39],10);
    /* Actual instruction fetch from the PL page exercises I-cache, while the
     * controlling code and stack stay in uncached ILM/DLM. */
    D[8]=7;__asm__ volatile("fence.i":::"memory");
    D[40]=cache_page_call();CHECK(17,D[40],11);
    cached[0]=0x01d00513u;FENCE();CHECK(0x01100513u,shared[0],11);
    command(PAGE,1);FENCE();CHECK(0x01d00513u,shared[0],11);
    D[41]=cache_page_call();CHECK(17,D[41],11);
    command(PAGE,8);__asm__ volatile("fence.i":::"memory");
    D[42]=cache_page_call();CHECK(29,D[42],12);
    D[8]=8;D[43]=D[60];FENCE();D[44]=D[60];
    CHECK(D[43]+1u,D[44],13);
cleanup:
    D[8]=9;
    if(configured) {
        /* No further cached stores occur between writeback and disable. */
        for(unsigned i=0;i<BYTES;i+=LINE)command(PAGE+i,2);
        for(unsigned i=0;i<32768u;i+=LINE)command(i,24);
        FENCE();
    }
    /* All ordinary failures return cache off. A CSR/bus trap has a separate
     * stackless fail path which disables cache and revokes only our entries. */
    WRITE(0x7ca,initial&~3u);D[21]=READ(0x7ca);
    if(!equal(initial&~3u,D[21],14))goto halt;
    D[45]|=1;
    if(configured) {
        WRITE(0xbc0,0);FENCE();
        if(!equal(0,READ(0xbc0),14))goto halt;
        WRITE(0xbd0,saved_addr[0]);WRITE(0xbd1,saved_addr[1]);FENCE();
        for(unsigned i=0;i<16;i++)if(!equal(saved_addr[i],addr_read(i),14))goto halt;
        if(!equal(0,READ(0xbc1)|READ(0xbc2)|READ(0xbc3),14))goto halt;
        cache_pma_armed=0;D[45]|=2;
    }
    D[56]=configured?BYTES:0;D[57]=(uint32_t)cctl_ok;D[8]=10;
halt:
    D[6]=D[7]?0x4641494cu:0x50415353u;
    for(;;)D[10]++;
}
