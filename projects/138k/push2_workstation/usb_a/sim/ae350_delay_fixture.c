/* Real Classic API paths, independent protocol expectations, no hardware model. */
#define main classic_prior_main
#include "ae350_classic_fixture.c"
#undef main

static unsigned take_one(void) {
    struct a138_classic_tx tx={0},again={0}; unsigned n=0,total=0;
    do {
        CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK);
        CHECK(tx.bytes>=5 && tx.bytes<=s.tx_payload_limit+4u);
        CHECK(a138_classic_tx_peek(&s,&again)==A138_CLASSIC_OK && !memcmp(&tx,&again,sizeof tx));
        CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_REJECTED)==A138_CLASSIC_OK);
        CHECK(a138_classic_tx_peek(&s,&again)==A138_CLASSIC_OK && !memcmp(&tx,&again,sizeof tx));
        CHECK(little(tx.data)==(0x23u|(n ? 0x1000u : 0x2000u)));
        CHECK(little(tx.data+2)==tx.bytes-4u && n+tx.bytes-4u<=sizeof response);
        memcpy(response+n,tx.data+4,tx.bytes-4u); n+=tx.bytes-4u;
        if (!total) { CHECK(n>=4); total=little(response)+4u; CHECK(total<=sizeof response); }
        CHECK(n<=total);
        CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_OK);
    } while (n<total);
    return n;
}
static const uint8_t delay_config[]={4,0x8c,1,0,7,6,0,0,0x21,0x15,2,53,8,0};
static void send_configuration(void) {
    uint8_t b[2+sizeof delay_config]; b[0]=0x20; b[1]=3;
    memcpy(b+2,delay_config,sizeof delay_config);
    CHECK(pdu(0x41,b,sizeof b,7)==A138_CLASSIC_OK);
}
static void prepare(unsigned value,unsigned now,unsigned limit) {
    reset(); s.tx_payload_limit=(uint16_t)limit; channel(1,0x70,672);
    CHECK(a138_classic_tick(&s,1,9,now)==A138_CLASSIC_OK);
    CHECK(a138_classic_delay_update(&s,1,9,value)==A138_CLASSIC_OK);
    send_configuration();
    CHECK(s.state==A138_CLASSIC_IDLE && !s.delay_selected && s.pending_config);
    CHECK(take_one()==6 && response[4]==0x22 && response[5]==3);
    CHECK(s.state==A138_CLASSIC_CONFIGURED && s.delay_selected && s.remote_seid==0x8c);
    CHECK(s.delay_phase==A138_CLASSIC_DELAY_TX && !s.delay_sent);
}
static unsigned report(void) {
    unsigned label=s.delay_label,value=s.delay_value;
    CHECK(take_one()==9 && little(response)==5 && little(response+2)==0x70);
    CHECK(response[4]==label && response[5]==13 && response[6]==0x8c);
    CHECK(response[7]==value/256 && response[8]==value%256);
    CHECK(s.delay_phase==A138_CLASSIC_DELAY_WAIT && s.delay_sent);
    return label;
}
static enum a138_classic_result reply(unsigned label,unsigned type,unsigned signal,unsigned bytes) {
    uint8_t b[140]; memset(b,0,sizeof b); b[0]=(uint8_t)(label|type); b[1]=(uint8_t)signal;
    b[2]=0x31; return pdu(0x41,b,bytes,11);
}
static void accept(unsigned label) {
    CHECK(reply(label,2,13,2)==A138_CLASSIC_OK);
    CHECK(s.delay_phase==A138_CLASSIC_DELAY_COMPLETE && s.delay_reported_value==s.delay_value);
}
static void test_capabilities_and_configuration(void) {
    uint8_t sep=4,b[32];
    reset(); channel(1,0x70,672);
    CHECK(command(2,&sep,1)==16 && response[5]==2); /* Basic never leaks category8. */
    CHECK(command(12,&sep,1)==18 && response[5]==12 && response[16]==8 && response[17]==0);
    CHECK(command(3,delay_config,sizeof delay_config)==8 && response[4]==0x13 && response[6]==8 && response[7]==0x31);
    CHECK(s.state==A138_CLASSIC_IDLE && !s.pending_config && !s.delay_selected);
    CHECK(a138_classic_tick(&s,1,9,0)==A138_CLASSIC_OK);
    CHECK(command(3,delay_config,sizeof delay_config)==8 && !s.pending_config);
    CHECK(a138_classic_delay_update(&s,1,9,65536)==A138_CLASSIC_ARGUMENT && !s.delay_valid);
    CHECK(a138_classic_delay_update(&s,1,9,0)==A138_CLASSIC_OK && s.delay_valid);
    memcpy(b,delay_config,sizeof delay_config); b[13]=1; b[14]=0;
    CHECK(command(3,b,15)==8 && response[6]==8 && response[7]==0x18);
    memcpy(b,delay_config,sizeof delay_config); b[14]=8; b[15]=0;
    CHECK(command(3,b,16)==8 && response[6]==8 && response[7]==0x18);
    for (unsigned i=0;i<sizeof delay_config;++i) {
        /* Structurally complete truncated SetConfiguration must never queue a report. */
        CHECK(command(3,delay_config,i)>=6); CHECK(!s.delay_selected && !s.pending_config);
    }
    prepare(0x1234,100,4); unsigned label=report(); accept(label);
    CHECK(command(4,&sep,1)==18 && response[16]==8 && response[17]==0);
    CHECK(command(6,&sep,1)==6 && s.state==A138_CLASSIC_OPEN);
}
static void test_ordering_start_and_fragmented_reply(void) {
    uint8_t b[]={0x30,6,4},sep=4;
    prepare(0x1234,100,4);
    /* OPEN already queued while DelayReport is offered: output report must retire first. */
    CHECK(pdu(0x41,b,sizeof b,0)==A138_CLASSIC_OK && s.rx_complete);
    unsigned label=report();
    CHECK(s.state==A138_CLASSIC_CONFIGURED && s.pending_state==A138_CLASSIC_OPEN);
    CHECK(take_one()==6 && response[4]==0x32 && response[5]==6 && s.state==A138_CLASSIC_OPEN);
    channel(2,0x71,672); CHECK(a138_classic_audio_ready(&s,1,9,44100,1)==A138_CLASSIC_OK);
    CHECK(command(7,&sep,1)==8 && response[7]==0x31 && s.state==A138_CLASSIC_OPEN);
    /* Valid fragmented Accept uses the same message type/label on both fragments. */
    b[0]=(uint8_t)(label|4|2); b[1]=2; b[2]=13;
    CHECK(pdu(0x41,b,3,0)==A138_CLASSIC_OK && s.avdtp_active);
    b[0]=(uint8_t)(label|12|2);
    CHECK(pdu(0x41,b,1,0)==A138_CLASSIC_OK && s.delay_phase==A138_CLASSIC_DELAY_COMPLETE);
    CHECK(command(7,&sep,1)==6 && s.state==A138_CLASSIC_STREAMING);
    CHECK(a138_classic_delay_update(&s,1,9,0x1235)==A138_CLASSIC_OK);
    label=report(); accept(label);
    CHECK(s.state==A138_CLASSIC_STREAMING && s.ready); /* No sample clock authority. */
}
static void test_responses(void) {
    unsigned label;
    prepare(0,100,276); label=report();
    CHECK(reply(label^0x10,2,13,2)==A138_CLASSIC_MALFORMED && !s.fenced);
    CHECK(s.delay_phase==A138_CLASSIC_DELAY_WAIT); accept(label);
    CHECK(reply(label,2,13,2)==A138_CLASSIC_MALFORMED && !s.fenced);
    prepare(65535,100,276); label=report();
    CHECK(reply(label,2,12,2)==A138_CLASSIC_FENCED && s.delay_failure==A138_CLASSIC_DELAY_BAD_RESPONSE);
    prepare(0x1234,100,27); label=report();
    CHECK(reply(label,3,13,3)==A138_CLASSIC_FENCED && s.delay_failure==A138_CLASSIC_DELAY_REJECTED);
    prepare(0x1234,100,276); label=report();
    CHECK(reply(label,1,13,2)==A138_CLASSIC_FENCED && s.delay_failure==A138_CLASSIC_DELAY_REJECTED);
    for (unsigned n=3;n<135;++n) {
        prepare(0x1234,100,276); label=report();
        CHECK(reply(label,2,13,n)==A138_CLASSIC_FENCED && s.delay_failure==A138_CLASSIC_DELAY_BAD_RESPONSE);
    }
    prepare(1,100,276); label=report();
    uint8_t b[]={(uint8_t)(label|6),2,13};
    CHECK(pdu(0x41,b,3,0)==A138_CLASSIC_OK);
    b[0]=(uint8_t)(label|12); /* Wrong message type cannot complete a reply. */
    CHECK(pdu(0x41,b,1,0)==A138_CLASSIC_MALFORMED && s.delay_phase==A138_CLASSIC_DELAY_WAIT);
}
static void test_time_and_busy(void) {
    unsigned label; struct a138_classic_tx tx,again;
    prepare(1,100,4);
    CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK);
    CHECK(a138_classic_delay_update(&s,1,9,2)==A138_CLASSIC_BUSY && s.delay_value==1);
    CHECK(a138_classic_tick(&s,1,9,1099)==A138_CLASSIC_OK);
    CHECK(a138_classic_tx_peek(&s,&again)==A138_CLASSIC_OK && tx.token==again.token && tx.bytes==again.bytes && !memcmp(tx.data,again.data,tx.bytes));
    CHECK(a138_classic_tick(&s,1,9,1100)==A138_CLASSIC_FENCED && s.delay_failure==A138_CLASSIC_DELAY_TIMEOUT);
    prepare(1,100,276); label=report();
    CHECK(a138_classic_delay_update(&s,1,9,2)==A138_CLASSIC_BUSY && s.delay_value==1);
    CHECK(a138_classic_tick(&s,1,9,1099)==A138_CLASSIC_OK);
    CHECK(a138_classic_tick(&s,1,9,1100)==A138_CLASSIC_FENCED);
    CHECK(reply(label,2,13,2)==A138_CLASSIC_FENCED); /* Deadline dominates success. */
    prepare(1,0xfffffff0u,276); label=report();
    CHECK(a138_classic_tick(&s,1,9,0x20)==A138_CLASSIC_OK);
    CHECK(a138_classic_tick(&s,1,9,983)==A138_CLASSIC_OK);
    CHECK(a138_classic_tick(&s,1,9,984)==A138_CLASSIC_FENCED);
    prepare(1,100,276); report();
    CHECK(a138_classic_tick(&s,1,9,99)==A138_CLASSIC_FENCED && s.delay_failure==A138_CLASSIC_DELAY_CLOCK_REGRESSED);
    prepare(1,100,276); label=report();
    CHECK(a138_classic_tick(&s,1,9,1099)==A138_CLASSIC_OK); accept(label);
    CHECK(a138_classic_tick(&s,1,9,1100)==A138_CLASSIC_OK); /* Complete stops timer. */
}
static void test_cancel_and_label_exhaustion(void) {
    struct a138_classic_tx tx; uint8_t sep=4; unsigned label;
    prepare(1,100,4); CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK);
    CHECK(a138_classic_tick(&s,1,8,1000)==A138_CLASSIC_STALE && !s.fenced);
    CHECK(a138_classic_delay_update(&s,2,9,2)==A138_CLASSIC_STALE && s.delay_value==1);
    CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_UNCERTAIN)==A138_CLASSIC_FENCED && !s.tx_bytes);
    prepare(1,100,4); CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK);
    CHECK(a138_classic_cancel(&s,1,9)==A138_CLASSIC_OK && !s.delay_selected && !s.tx_bytes);
    CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_INACTIVE);
    CHECK(a138_classic_begin(&s,2,10,0x23,276)==A138_CLASSIC_OK && !s.delay_valid && !s.clock_valid);
    CHECK(a138_classic_tick(&s,1,9,1000)==A138_CLASSIC_STALE);
    prepare(1,100,276); label=report();
    CHECK(command(10,&sep,1)==6 && s.state==A138_CLASSIC_IDLE && !s.delay_selected);
    CHECK(reply(label,2,13,2)==A138_CLASSIC_MALFORMED && !s.fenced);
    CHECK(a138_classic_tick(&s,1,9,1100)==A138_CLASSIC_OK);
    prepare(1,100,276); report();
    static const uint8_t disconnect[]={5,4,0,0x23,0,0x13};
    CHECK(a138_classic_event(&s,1,9,disconnect,sizeof disconnect)==A138_CLASSIC_OK && !s.active && !s.delay_selected);
    prepare(1,100,276); label=report(); accept(label);
    for (unsigned i=1;i<16;++i) {
        CHECK(a138_classic_delay_update(&s,1,9,i+1)==A138_CLASSIC_OK);
        label=report(); CHECK(label==i*16);
        CHECK(reply(label^0x10,2,13,2)==A138_CLASSIC_MALFORMED && s.delay_phase==A138_CLASSIC_DELAY_WAIT);
        accept(label);
    }
    CHECK(s.delay_labels_used==16);
    CHECK(a138_classic_delay_update(&s,1,9,17)==A138_CLASSIC_FENCED && s.delay_failure==A138_CLASSIC_DELAY_LABEL_EXHAUSTED);
}
int main(void) {
    test_capabilities_and_configuration(); test_ordering_start_and_fragmented_reply();
    test_responses(); test_time_and_busy(); test_cancel_and_label_exhaustion();
    printf("delay reporting source-stage: %u checks passed; object=%zu, no hardware delay claim\n",checks,sizeof s);
    return 0;
}
