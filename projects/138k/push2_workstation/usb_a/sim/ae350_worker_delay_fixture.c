/* Real ACL API requests and independent AVDTP wire expectations. No radio,
 * physical delay, security acceptance or PCM hardware acceptance is inferred. */
#define main classic_prior_main
#include "ae350_classic_fixture.c"
#undef main

static void hex(const char *label,const char *direction,const uint8_t *p,unsigned n) {
    printf("WIRE %s %s ",label,direction);
    for(unsigned i=0;i<n;i++)printf("%02x",p[i]);
    putchar('\n');
}
static unsigned nibble(char c) {
    CHECK((c>='0'&&c<='9')||(c>='a'&&c<='f'));
    return c<='9'?(unsigned)(c-'0'):(unsigned)(c-'a'+10);
}
static void expected(const uint8_t *p,unsigned n,const char *wire) {
    CHECK(strlen(wire)==2u*n);
    for(unsigned i=0;i<n;i++)CHECK(p[i]==16u*nibble(wire[2*i])+nibble(wire[2*i+1]));
}
static void wire_command(const char *label,unsigned signal,const uint8_t *parameters,unsigned n,
        const char *request,const char *reply) {
    uint8_t acl[280];struct a138_classic_tx tx={0};
    le(acl,0x2023);le(acl+2,n+6u);le(acl+4,n+2u);le(acl+6,0x41);
    acl[8]=0x10;acl[9]=(uint8_t)signal;memcpy(acl+10,parameters,n);
    expected(acl,n+10u,request);hex(label,"REQUEST",acl,n+10u);
    CHECK(a138_classic_acl(&s,1,9,acl,(uint16_t)(n+10u))==A138_CLASSIC_OK);
    CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK);
    expected(tx.data,tx.bytes,reply);hex(label,"RESPONSE",tx.data,tx.bytes);
    CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_OK);
}

int main(void) {
    uint8_t sep=4;
    static const uint8_t with_delay[]={4,8,1,0,7,6,0,0,0x21,0x15,2,53,8,0};
    static const uint8_t basic[]={4,8,1,0,7,6,0,0,0x21,0x15,2,53};
#ifdef A138_EXPECT_FROZEN_DELAY
    const char *all="232012000e007000120c0100070600003fff02350800";
    const char *no_facts="232008000400700013030831";
    const char *injected="23200600020070001203";
#else
    const char *all="232010000c007000120c0100070600003fff0235";
    const char *no_facts="232008000400700013030817";
    const char *injected=no_facts;
#endif
    reset();channel(1,0x70,672);
    CHECK(!s.delay_valid&&!s.clock_valid);
    wire_command("basic-capabilities",2,&sep,1,"2320070003004100100204",
        "232010000c00700012020100070600003fff0235");
    wire_command("all-capabilities-no-facts",12,&sep,1,"2320070003004100100c04",all);
    wire_command("select-delay-no-facts",3,with_delay,sizeof with_delay,
        "232014001000410010030408010007060000211502350800",no_facts);
    CHECK(s.state==A138_CLASSIC_IDLE&&!s.pending_config&&!s.delay_selected);
    /* Injecting clock/delay facts cannot turn an absent W provider into an
     * advertised service or authorize an unadvertised category selection. */
    CHECK(a138_classic_tick(&s,1,9,100)==A138_CLASSIC_OK);
    CHECK(a138_classic_delay_update(&s,1,9,123)==A138_CLASSIC_OK);
    CHECK(s.delay_valid&&s.clock_valid);
    wire_command("all-capabilities-injected-facts",12,&sep,1,"2320070003004100100c04",all);
    wire_command("select-delay-injected-facts",3,with_delay,sizeof with_delay,
        "232014001000410010030408010007060000211502350800",injected);
#ifdef A138_EXPECT_FROZEN_DELAY
    CHECK(s.state==A138_CLASSIC_CONFIGURED&&s.delay_selected);
#else
    CHECK(s.state==A138_CLASSIC_IDLE&&!s.pending_config&&!s.delay_selected);
#endif
    reset();channel(1,0x70,672);
    wire_command("ordinary-sbc-configuration",3,basic,sizeof basic,
        "232012000e0041001003040801000706000021150235","23200600020070001203");
    CHECK(s.state==A138_CLASSIC_CONFIGURED&&!s.delay_selected&&s.format.rate_hz==44100);
    wire_command("ordinary-sbc-get-configuration",4,&sep,1,"2320070003004100100404",
        "232010000c007000120401000706000021150235");
    /* Existing real-API path checks OPEN, media channel, START rejection until
     * explicit matching-rate readiness, then START acceptance. */
    reset();streaming();
    CHECK(s.state==A138_CLASSIC_STREAMING&&!s.delay_selected);
    printf("worker delay capability: %u checks passed; no hardware claim\n",checks);
    return 0;
}
