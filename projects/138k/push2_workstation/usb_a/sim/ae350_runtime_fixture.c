/* Exact source CPU composition against an asynchronous checked-MMIO model.
 * This model is not the native RTL, a durable key backend or physical audio. */
#include "classic_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"check %u line%d: %s\n",checks,__LINE__,#x);exit(1);}}while(0)
struct model {
    uint32_t epoch,now,status,caps,state,tx_epoch,generation,token,meta,count;
    uint32_t released_epoch,rx_ticket,rx_generation,rx_token,rx_meta,rx_handle,rx_index;
    uint32_t acked,last_token,fences,operations,maximum_operations,fail_write,failed;
    uint16_t rx_bytes;
    uint8_t tx[280],rx[280],present,response_done;
};
static struct model m;
static struct a138_classic_runtime r;
static const uint8_t local_address[6]={0x21,0x43,0x65,0x87,0xa9,0xcb};
static unsigned media_mode,submits,cancels,media_polls;
static uint8_t submitted_pcm[512];
static void op(void){++m.operations;}
static int rd(void *unused,uint32_t off,uint32_t *v) {
    (void)unused;op();
    switch(off) {
    case 0:*v=0x48434931;break;case 4:*v=m.caps;break;case 8:*v=m.status;break;case 12:*v=m.epoch;break;
    case 44:*v=m.state|((m.state==3||m.state==4)?512u:0u)|(m.state==4?1024u:0u)|(m.response_done?256u:0u);break;
    case 56:*v=m.count;break;case 64:*v=m.present?257u:0u;break;case 68:*v=m.present?m.epoch:0;break;
    case 72:*v=m.rx_generation;break;case 76:*v=m.present?m.rx_ticket:0;break;case 80:*v=m.rx_meta;break;
    case 84:*v=m.rx_handle;break;case 88:*v=m.rx_token;break;
    case 96:CHECK(m.present&&m.rx_index<m.rx_bytes);*v=m.rx[m.rx_index];break;
    case 112:*v=276u|(276u<<16);break;case 120:*v=m.now;break;
    default:CHECK(0);return 0;
    }return 1;
}
static int wr(void *unused,uint32_t off,uint32_t v) {
    (void)unused;op();
    if(m.fail_write==off+1u&&!m.failed){m.failed=1;return 0;}
    switch(off) {
    case 32:CHECK(v==1&&m.state==0);m.state=1;m.count=0;m.response_done=0;break;
    case 16:m.tx_epoch=v;break;case 20:m.generation=v;break;case 24:m.token=v;break;case 28:m.meta=v;break;
    case 40:CHECK(m.state==1&&m.count<280&&v<256);m.tx[m.count++]=(uint8_t)v;break;
    case 36:CHECK(v==1&&m.state==1&&m.tx_epoch==m.epoch&&m.token>m.last_token&&m.count==(m.meta>>16));m.state=2;m.last_token=m.token;break;
    case 48:CHECK(v==m.token&&(m.state==5||(m.state==4&&m.response_done)));m.state=0;m.response_done=0;++m.acked;break;
    case 60:m.released_epoch=v;break;case 92:CHECK(m.present&&v<m.rx_bytes);m.rx_index=v;break;
    case 100:CHECK(m.present&&v==m.rx_ticket&&m.released_epoch==m.epoch);m.present=0;break;
    case 124:CHECK(v==m.epoch&&v);++m.fences;m.status|=4u;break;
    default:CHECK(0);return 0;
    }return 1;
}
static struct a138_hci_bus bus(void){return(struct a138_hci_bus){0,rd,wr};}
static enum a138_bond_result load(void *c,const uint8_t p[6],struct a138_bond *b){(void)c;(void)p;(void)b;return A138_BOND_ERROR;}
static enum a138_bond_result replace(void *c,const struct a138_bond*b,uint32_t rev){(void)c;(void)b;(void)rev;return A138_BOND_ERROR;}
static enum a138_bond_result remove_bond(void*c,const uint8_t p[6],uint32_t rev){(void)c;(void)p;(void)rev;return A138_BOND_ERROR;}
static int poll_media(void *c,uint32_t epoch,uint32_t g,uint32_t stream,uint32_t rate,struct a138_runtime_audio_facts *f) {
    (void)c;CHECK(epoch==77);++media_polls;*f=(struct a138_runtime_audio_facts){epoch,g,stream,rate,0,1,0,1};
    if(media_mode==3)f->generation++;
    if(media_mode==4)f->drift_managed=0;
    return media_mode==5?-1:1;
}
static enum a138_classic_submission submit_media(void*c,uint32_t epoch,uint32_t g,uint32_t stream,
        const struct a138_classic_frame *frame,const int16_t *pcm,const struct a138_sbc_pcm *decoded) {
    (void)c;++submits;CHECK(epoch==77&&g==r.classic.generation&&stream==r.classic.stream_epoch);
    CHECK(frame->stream_epoch==stream&&decoded->valid&&decoded->stream_epoch==stream);
    memcpy(submitted_pcm,pcm,decoded->scalar_samples*2u);
    return media_mode==1?A138_CLASSIC_REJECTED:media_mode==2?A138_CLASSIC_UNCERTAIN:A138_CLASSIC_ACCEPTED;
}
static void cancel_media(void*c,uint32_t epoch,uint32_t g,uint32_t stream){(void)c;CHECK(epoch==77&&g&&stream);++cancels;}
static void reset(unsigned enabled,unsigned media) {
    memset(&m,0,sizeof m);m.epoch=77;m.status=17;m.caps=0x01040114;
    media_mode=submits=cancels=media_polls=0;memset(submitted_pcm,0,sizeof submitted_pcm);
    struct a138_bond_store store={0,load,replace,remove_bond};
    struct a138_runtime_media output={0,poll_media,submit_media,cancel_media};
    a138_classic_runtime_init(&r,bus(),enabled?&store:0,media?&output:0);
}
static void step(void) {
    m.operations=0;a138_classic_runtime_step(&r);
    if(m.operations>m.maximum_operations)m.maximum_operations=m.operations;
    CHECK(m.operations<=64u);
}
static void rx(uint8_t type,uint32_t generation,uint8_t response,const uint8_t *p,unsigned bytes) {
    CHECK(!m.present&&bytes<=280&&bytes>=2);m.present=1;++m.rx_ticket;
    m.rx_generation=generation;m.rx_token=response?m.token:0;m.rx_meta=type|(2u<<8)|((uint32_t)response<<10)|(bytes<<16);
    m.rx_handle=0x23;m.rx_bytes=(uint16_t)bytes;memcpy(m.rx,p,bytes);
    if(response)m.response_done=1;
}
static void pending(unsigned opcode) {
    for(unsigned i=0;m.state!=2&&i<40u;i++){step();if(r.fault)fprintf(stderr,"pendingop%x state%u runtimefault%u transportfault%u securityfailure%u\n",opcode,m.state,r.fault,r.transport.fault,r.security.failure);CHECK(!r.fault);}
    CHECK(m.state==2&&m.tx[0]==(opcode&255u)&&m.tx[1]==(opcode>>8));
    CHECK(!r.transport.accepted&&!r.security.queue[r.security.head].accepted);
}
static void response(unsigned opcode,unsigned early_done,const uint8_t *extra,unsigned bytes) {
    uint8_t event[32]={14,0,1,0,0,0};event[1]=(uint8_t)(4u+bytes);event[3]=(uint8_t)opcode;event[4]=(uint8_t)(opcode>>8);
    if(bytes)memcpy(event+6,extra,bytes);
    m.state=early_done?4:3;step();CHECK(r.transport.accepted&&!r.fault);
    unsigned ack=m.acked;rx(4,0,1,event,bytes+6u);
    for(unsigned i=0;m.present&&i<30u;i++){step();CHECK(!r.fault);}
    CHECK(!m.present);
    if(!early_done){CHECK(m.acked==ack&&r.transport.tx_phase);m.state=4;step();}
    CHECK(m.acked==ack+1u&&!r.fault);
}
static void startup_before_identity(void) {
    uint8_t f[10]={0};pending(0x1003);f[6]=8;f[7]=128;response(0x1003,0,f,8);
    pending(0x0c56);response(0x0c56,1,0,0);
    pending(0x1004);memset(f,0,sizeof f);f[0]=f[1]=f[2]=1;response(0x1004,0,f,10);
    if(r.session_only){pending(0x0c24);CHECK(m.tx[3]==0x14&&m.tx[4]==4&&m.tx[5]==0x24);response(0x0c24,1,0,0);}
    pending(0x0c1a);CHECK(m.tx[3]==(r.session_only?3:2));response(0x0c1a,1,0,0);
    CHECK(r.security.ready==!r.session_only&&r.started&&!r.security.secure&&!r.security.local_address_valid);
    if(!r.session_only)CHECK(r.transport.next_token==4u);
    else CHECK(r.transport.next_token>=5u&&r.transport.next_token<=6u);
}
static void startup(void) {
    uint8_t scan=3;startup_before_identity();
    if(r.session_only){
        pending(0x1009);CHECK(m.count==3&&!r.security.ready);response(0x1009,0,local_address,6);
        CHECK(r.security.local_address_valid&&!r.security.ready&&!memcmp(r.security.local_address,local_address,6));
        pending(0x0c19);CHECK(m.count==3&&!r.security.ready);response(0x0c19,1,&scan,1);
        CHECK(r.security.ready&&r.transport.next_token==7u);
    }
}
static void reset_session(void){
    reset(0,1);struct a138_runtime_media output={0,poll_media,submit_media,cancel_media};
    a138_classic_runtime_init_session(&r,bus(),&output);
}
static void test_session_startup(void){
    reset(0,1);struct a138_runtime_media output={0,poll_media,submit_media,cancel_media};
    a138_classic_runtime_init_session(&r,bus(),0);
    for(unsigned i=0;i<20;i++)step();CHECK(!r.enabled&&!r.started&&!m.token);
    a138_classic_runtime_init_session(&r,bus(),&output);
    CHECK(r.enabled&&r.session_only&&!r.store.load&&!r.store.replace_atomic&&!r.store.delete_atomic);
    startup();CHECK(r.security.session_only&&!r.security.store.load&&!r.security.secure);
}
static void test_missing_backend_and_identity(void) {
    reset(0,0);for(unsigned i=0;i<100u;i++)step();CHECK(r.transport.ready&&!r.started&&!r.enabled&&!m.count&&!m.token);
    uint8_t harmless[2]={1,0};rx(4,0,0,harmless,2);for(unsigned i=0;i<3u;i++)step();CHECK(!m.present&&r.rx_dropped==1&&!m.count);
    reset(1,0);m.caps^=1;step();CHECK(r.fault&&m.fences==0);
    reset(0,0);step();m.epoch=78;step();CHECK(r.fault&&m.fences==0);step();CHECK(m.fences==0);
}
static void test_startup_and_ordering(void) {
    reset(1,0);startup();CHECK(m.maximum_operations<=64u&&m.acked==4);
    uint8_t request[12]={4,10,1,2,3,4,5,6,0,0,0,1};m.status=1;rx(4,0,0,request,12);
    for(unsigned i=0;m.present&&i<5u;i++)step();pending(0x040a);CHECK(m.tx[9]==0x0d); /* actual capacity false */
    reset(1,0);pending(0x1003);m.state=3;step();uint8_t wrong[14]={14,12,1,3,16,0,0,0,0,0,0,0,8,128};
    rx(4,0,1,wrong,14);m.rx_token++;for(unsigned i=0;!r.fault&&i<5u;i++)step();CHECK(r.fault==A138_RUNTIME_RESPONSE_FAULT&&m.fences==1&&!m.acked);
    CHECK(r.security.local_step==0&&!r.security.queue[r.security.head].response_done); /* wrong receipt never consumed */
    reset(1,0);pending(0x1003);m.now=1000;step();CHECK(r.fault==A138_RUNTIME_SECURITY_FAULT&&m.fences==1&&!m.acked);
}
static void test_transport_private_copy_and_faults(void) {
    struct a138_hci_transport t;uint8_t packet[280];for(unsigned i=0;i<280u;i++)packet[i]=(uint8_t)i;
    reset(0,0);a138_hci_init(&t,bus());a138_hci_step(&t);CHECK(t.ready);
    CHECK(a138_hci_offer(&t,2,9,1,packet,280));memset(packet,0xee,280);
    for(unsigned i=0;i<24u&&m.state!=2;i++){m.operations=0;a138_hci_step(&t);CHECK(!t.fault);}
    CHECK(m.count==280&&m.state==2);for(unsigned i=0;i<280u;i++)CHECK(m.tx[i]==(uint8_t)i);
    m.state=4;m.response_done=1;a138_hci_step(&t);CHECK(t.accepted&&t.transport_done&&a138_hci_tx_retire(&t));
    uint8_t cmd[3]={3,16,0};CHECK(a138_hci_offer(&t,1,0,1,cmd,3)&&t.tx_token==2); /* independent producer token1 */
    a138_hci_step(&t);m.fail_write=37;a138_hci_step(&t);CHECK(t.fault==A138_HCI_FAULT_IO&&t.uncertain);
    unsigned count=m.count;a138_hci_step(&t);CHECK(m.count==count&&!a138_hci_offer(&t,1,0,2,cmd,3));
    reset(0,0);a138_hci_init(&t,bus());a138_hci_step(&t);CHECK(a138_hci_offer(&t,1,0,1,cmd,3));
    a138_hci_step(&t);a138_hci_step(&t);m.state=6;a138_hci_step(&t);CHECK(t.uncertain&&t.fault&&!a138_hci_tx_retire(&t));
    reset(0,0);a138_hci_init(&t,bus());a138_hci_step(&t);CHECK(a138_hci_offer(&t,1,0,1,cmd,3));
    a138_hci_step(&t);a138_hci_step(&t);m.state=4;a138_hci_step(&t);CHECK(t.transport_done&&!a138_hci_tx_retire(&t)&&!m.acked);
    reset(0,0);a138_hci_init(&t,bus());a138_hci_step(&t);t.next_token=UINT32_MAX;CHECK(!a138_hci_offer(&t,1,0,1,cmd,3)&&t.fault);
    reset(0,0);a138_hci_init(&t,bus());a138_hci_step(&t);uint8_t event[257]={1,255};for(unsigned i=2;i<257u;i++)event[i]=(uint8_t)i;
    rx(4,0,0,event,257);for(unsigned i=0;i<24u&&!a138_hci_rx_peek(&t);i++)a138_hci_step(&t);
    const struct a138_hci_rx *head=a138_hci_rx_peek(&t);CHECK(head&&head->bytes==257&&!memcmp(head->data,event,257));
    m.rx_handle|=65536u;a138_hci_step(&t);head=a138_hci_rx_peek(&t);CHECK(head&&head->retired);
    CHECK(!a138_hci_rx_release(&t,77,head->ticket+1u)&&m.present);CHECK(a138_hci_rx_release(&t,77,head->ticket)&&!m.present);
    rx(4,0,0,event,257);a138_hci_step(&t);m.rx_ticket++;for(unsigned i=0;i<24u&&!t.fault;i++)a138_hci_step(&t);CHECK(t.fault==A138_HCI_FAULT_DESCRIPTOR&&!a138_hci_rx_peek(&t));
}
static void inject_frame(const uint8_t *data,unsigned bytes) {
    CHECK(bytes>=4u&&bytes<=224u&&data[0]==0x9c);
    struct a138_classic_service *c=&r.classic;
    CHECK(a138_classic_begin(c,9,9,0x23,276)==A138_CLASSIC_OK);
    CHECK(a138_classic_security(c,9,9,1)==A138_CLASSIC_OK);
    r.security.active=1;r.security.generation=9;r.security.handle=0x23;r.security.secure=1;
    c->state=A138_CLASSIC_STREAMING;c->format=(struct a138_classic_format){
        (data[1]>>6)==2?44100u:48000u,(data[1]>>2)&3u,data[1]&1u?8u:4u,
        4u+4u*((data[1]>>4)&3u),(data[1]>>1)&1u,2,53};
    c->frame_count=1;c->frame[0]=(struct a138_classic_frame){.link_epoch=9,.stream_epoch=c->stream_epoch,.format=c->format,.bytes=(uint16_t)bytes};
    memcpy(c->frame[0].data,data,bytes);
}
static void test_acl_diagnostic(void) {
    uint32_t header;uint16_t status;
    uint8_t info[14]={0x23,0,10,0,6,0,1,0,10,2,2,0,2,0};
    reset(0,0);a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(header==UINT32_C(0x43505531)&&status==0);
    r.security.close_context=UINT32_C(0xd463c418);
    a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(header==UINT32_C(0xd463c418)&&status==0);
    rx(2,9,0,info,sizeof info);
    for(unsigned i=0;m.present&&i<10u;i++)step();
    a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(!m.present&&r.rx_dropped==1&&header==UINT32_C(0x000a0023));
    CHECK(status==(256u|A138_CLASSIC_INACTIVE));

    reset(1,0);startup();
    CHECK(a138_classic_begin(&r.classic,9,9,0x23,276)==A138_CLASSIC_OK);
    r.security.active=1;r.security.generation=9;r.security.handle=0x23;
    rx(2,9,0,info,sizeof info); /* Invalid controller PB0 is observed, not accepted. */
    for(unsigned i=0;m.present&&i<10u;i++)step();
    a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(!m.present&&!r.fault&&r.classic.malformed==1&&!r.classic.tx_bytes);
    CHECK(header==UINT32_C(0x000a0023)&&status==(256u|0xb0u|A138_CLASSIC_MALFORMED));

    info[1]=0x20;rx(2,9,0,info,sizeof info);
    r.classic.rx_complete=1;
    for(unsigned i=0;!r.rx_waiting&&i<10u;i++)step();
    CHECK(m.present&&r.rx_waiting&&!r.fault);
    step();a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(header==UINT32_C(0x000a2023)&&status==(512u|0xb0u|A138_CLASSIC_BUSY));
    r.classic.rx_complete=0;
    step();a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(!m.present&&!r.fault&&!r.rx_waiting&&status==(512u|0xb0u|A138_CLASSIC_OK));
    CHECK(r.classic.tx_bytes&&r.transport.tx_phase); /* Valid InfoRequest still produces a response. */
}
static void test_local_identity_diagnostic(void) {
    uint32_t header;uint16_t status;uint8_t scan=3;
    reset_session();startup_before_identity();
    a138_classic_runtime_diagnostic(&r,&header,&status);CHECK(header==UINT32_C(0x43505531)&&status==0);
    pending(0x1009);response(0x1009,0,local_address,6);
    a138_classic_runtime_diagnostic(&r,&header,&status);CHECK(header==UINT32_C(0x43505531)&&status==0);
    pending(0x0c19);a138_classic_runtime_diagnostic(&r,&header,&status);CHECK(header==UINT32_C(0x43505531));
    response(0x0c19,1,&scan,1);CHECK(r.security.ready);
    unsigned operations=m.operations;uint32_t token=m.token;
    a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(header==UINT32_C(0x87654321)&&status==0xcba9u&&m.operations==operations&&m.token==token);
    r.security.local_address_valid=0;a138_classic_runtime_diagnostic(&r,&header,&status);CHECK(header==UINT32_C(0x43505531));
    r.security.local_address_valid=1;r.security.ready=0;
    a138_classic_runtime_diagnostic(&r,&header,&status);CHECK(header==UINT32_C(0x43505531));
    r.security.ready=1;r.security.session_only=0;
    a138_classic_runtime_diagnostic(&r,&header,&status);CHECK(header==UINT32_C(0x43505531));
    r.security.session_only=1;r.security.close_context=UINT32_C(0xd463c418);
    a138_classic_runtime_diagnostic(&r,&header,&status);CHECK(header==UINT32_C(0xd463c418)&&status==0);
    uint8_t info[14]={0x23,0,10,0,6,0,1,0,10,2,2,0,2,0};
    rx(2,9,0,info,sizeof info);for(unsigned i=0;m.present&&i<10u;i++)step();
    a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK(!m.present&&!r.fault&&header==UINT32_C(0x000a0023)&&status==r.acl_diagnostic);
    /* A fault must never look like a valid local address, close or old ACL. */
    r.fault=A138_RUNTIME_RESPONSE_FAULT;r.transport.fault=A138_HCI_FAULT_DESCRIPTOR;r.security.failure=5;
    operations=m.operations;
    a138_classic_runtime_diagnostic(&r,&header,&status);
    CHECK((header&UINT32_C(0xff000000))==UINT32_C(0xfc000000));
    CHECK(((header>>16)&255u)==A138_RUNTIME_RESPONSE_FAULT&&((header>>8)&255u)==A138_HCI_FAULT_DESCRIPTOR&&(header&255u)==5u);
    CHECK(status==r.acl_diagnostic&&m.operations==operations);
    operations=m.operations;a138_classic_runtime_diagnostic(&r,0,&status);a138_classic_runtime_diagnostic(&r,&header,0);
    CHECK(m.operations==operations&&header>>24==0xfcu);
    a138_classic_runtime_diagnostic(0,&header,&status);CHECK(header==UINT32_C(0x43505531)&&status==0);
}
static void test_actual_decoder_and_media(const uint8_t *data,unsigned bytes,FILE *pcm) {
    reset(1,1);startup();inject_frame(data,bytes);step();CHECK(r.pcm_pending&&r.decoded.valid&&r.classic.ready&&submits==0);
    unsigned samples=r.decoded.scalar_samples;step();CHECK(!r.pcm_pending&&r.pcm_blocks==1&&submits==1&&!r.fault);
    CHECK(fwrite(submitted_pcm,2,samples,pcm)==samples);
    r.classic.stream_epoch++;step();CHECK(cancels==1&&!r.decoder.active&&!r.pcm_pending);
    reset(1,1);startup();inject_frame(data,bytes);media_mode=4;step();CHECK(!r.classic.ready&&!r.pcm_pending&&submits==0);
    reset(1,1);startup();inject_frame(data,bytes);media_mode=3;step();CHECK(!r.classic.ready&&!r.pcm_pending&&submits==0);
    reset(1,1);startup();inject_frame(data,bytes);media_mode=1;step();CHECK(r.pcm_pending);uint8_t saved[512];memcpy(saved,r.pcm,512);
    step();CHECK(r.pcm_pending&&!memcmp(saved,r.pcm,512));m.now=100;step();CHECK(r.fault==A138_RUNTIME_MEDIA_FAULT&&m.fences==1&&cancels==1);
    reset(1,1);startup();inject_frame(data,bytes);media_mode=2;step();step();CHECK(r.fault==A138_RUNTIME_MEDIA_FAULT&&m.fences==1&&submits==1);
    reset(1,0);startup();inject_frame(data,bytes);step();CHECK(!r.classic.ready&&!r.pcm_pending&&r.classic.frame_count==1);
}
int main(int argc,char **argv) {
    CHECK(argc==3);uint8_t frame[224];FILE *in=fopen(argv[1],"rb");CHECK(in);unsigned bytes=(unsigned)fread(frame,1,sizeof frame,in);CHECK(!ferror(in)&&fclose(in)==0);
    unsigned mode=(frame[1]>>2)&3u,sub=frame[1]&1u?8u:4u,blocks=4u+4u*((frame[1]>>4)&3u);
    unsigned bits=blocks*frame[2]*(mode<2u?(mode?2u:1u):1u)+(mode==3u?sub:0u);
    bytes=4u+sub*(mode?2u:1u)/2u+(bits+7u)/8u;
    test_missing_backend_and_identity();test_startup_and_ordering();test_transport_private_copy_and_faults();test_session_startup();test_acl_diagnostic();test_local_identity_diagnostic();
    FILE *pcm=fopen(argv[2],"wb");CHECK(pcm);test_actual_decoder_and_media(frame,bytes,pcm);CHECK(fclose(pcm)==0);
    printf("classic runtime: %u checks passed; native RTL, durable store, phone and physical media absent\n",checks);return 0;
}
