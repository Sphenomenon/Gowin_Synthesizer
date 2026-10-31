#include "hci_transport.h"
#include <string.h>
enum { ID=0,CAPS=4,STATUS=8,EPOCH=12,TX_EPOCH=16,TX_GENERATION=20,TX_TOKEN=24,
    TX_META=28,BEGIN=32,COMMIT=36,TX_BYTE=40,TX_STATE=44,TX_ACK=48,
    TX_COUNT=56,RX_RELEASE_EPOCH=60,RX_STATUS=64,RX_EPOCH=68,
    RX_GENERATION=72,RX_TICKET=76,RX_META=80,RX_HANDLE=84,RX_TOKEN=88,
    RX_INDEX=92,RX_BYTE=96,RX_RELEASE=100,LIMIT=112,TIME_MS=120 };
static void barrier(void) {
#ifdef __riscv
    __asm__ volatile("fence iorw, iorw" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}
static int hci_mmio_read(void *p,uint32_t off,uint32_t *v) {
    barrier();*v=*(volatile uint32_t *)((uintptr_t)p+off);barrier();return 1;
}
static int hci_mmio_write(void *p,uint32_t off,uint32_t v) {
    barrier();*(volatile uint32_t *)((uintptr_t)p+off)=v;barrier();return 1;
}
struct a138_hci_bus a138_hci_mmio_bus(uintptr_t base) {
    return (struct a138_hci_bus){(void *)base,hci_mmio_read,hci_mmio_write};
}
static int read_reg(struct a138_hci_transport *t,uint32_t off,uint32_t *v) {
    if(!t->bus.read(t->bus.context,off,v)){t->fault=A138_HCI_FAULT_IO;return 0;}return 1;
}
static int write_reg(struct a138_hci_transport *t,uint32_t off,uint32_t v) {
    if(!t->bus.write(t->bus.context,off,v)){t->fault=A138_HCI_FAULT_IO;return 0;}return 1;
}
void a138_hci_init(struct a138_hci_transport *t,struct a138_hci_bus bus) {
    if(t){memset(t,0,sizeof *t);t->bus=bus;
        if(!bus.read||!bus.write)t->fault=A138_HCI_FAULT_IO;}
}
int a138_hci_offer(struct a138_hci_transport *t,uint8_t type,uint32_t generation,
        uint32_t token,const uint8_t *data,uint16_t bytes) {
    if(!t||t->fault||!t->ready||t->tx_phase||!token||!data||bytes>A138_HCI_BYTES||
       (type!=A138_HCI_COMMAND&&type!=A138_HCI_ACL)||
       (type==A138_HCI_COMMAND&&(bytes<3u||bytes>25u))||
       (type==A138_HCI_ACL&&(bytes<4u||!generation||bytes>t->br_limit+4u)))return 0;
    if(t->next_token==UINT32_MAX){t->fault=A138_HCI_FAULT_TOKEN;return 0;}
    t->tx_token=++t->next_token;t->source_token=token;t->tx_generation=generation;
    t->tx_type=type;t->tx_bytes=bytes;t->tx_offset=0;t->tx_phase=1;
    t->accepted=t->transport_done=t->response_done=t->rejected=t->uncertain=0;
    memcpy(t->tx,data,bytes);return 1;
}
static void tx_step(struct a138_hci_transport *t) {
    uint32_t state;
    if(!t->tx_phase)return;
    if(t->tx_phase==1u) {
        if(!read_reg(t,TX_STATE,&state))return;
        if(state!=0u){t->fault=A138_HCI_FAULT_DESCRIPTOR;return;}
        if(!write_reg(t,BEGIN,1)||!write_reg(t,TX_EPOCH,t->epoch)||
           !write_reg(t,TX_GENERATION,t->tx_generation)||!write_reg(t,TX_TOKEN,t->tx_token)||
           !write_reg(t,TX_META,(uint32_t)t->tx_bytes<<16|t->tx_type))return;
        t->tx_phase=2;return;
    }
    if(t->tx_phase==2u) {
        unsigned n=t->tx_bytes-t->tx_offset;if(n>A138_HCI_SLICE)n=A138_HCI_SLICE;
        for(unsigned i=0;i<n;i++)if(!write_reg(t,TX_BYTE,t->tx[t->tx_offset++]))return;
        if(t->tx_offset==t->tx_bytes) {
            uint32_t count;
            if(!read_reg(t,TX_COUNT,&count))return;
            if(count!=t->tx_bytes){t->fault=A138_HCI_FAULT_DESCRIPTOR;return;}
            /* A failed COMMIT may already be irreversible: never retry it. */
            if(!write_reg(t,COMMIT,1)){t->uncertain=1;return;}
            t->tx_phase=3;
        }
        return;
    }
    if(!read_reg(t,TX_STATE,&state))return;
    unsigned phase=state&15u;
    if(state&~UINT32_C(0x70f)){t->fault=A138_HCI_FAULT_DESCRIPTOR;return;}
    if(phase==3u||phase==4u) {
        if(!(state&512u)||(phase==4u&&!(state&1024u))){t->fault=A138_HCI_FAULT_DESCRIPTOR;return;}
        t->accepted=1;
        if(phase==4u)t->transport_done=1;
        if(t->tx_type==A138_HCI_ACL)t->response_done=1;
    }else if(phase==5u) {
        if(t->accepted||(state&1536u)){t->fault=A138_HCI_FAULT_DESCRIPTOR;return;}
        t->rejected=1;
    }else if(phase==6u){t->uncertain=1;t->fault=A138_HCI_FAULT_UNCERTAIN;}
    else if(phase!=2u||t->accepted){t->fault=A138_HCI_FAULT_DESCRIPTOR;}
}
static int rx_identity(struct a138_hci_transport *t,uint32_t epoch,uint32_t ticket) {
    uint32_t status,e,k;
    if(!read_reg(t,RX_STATUS,&status)||!read_reg(t,RX_EPOCH,&e)||!read_reg(t,RX_TICKET,&k))return 0;
    if(!(status&256u)||e!=epoch||k!=ticket){t->fault=A138_HCI_FAULT_DESCRIPTOR;return 0;}return 1;
}
static int rx_retirement(struct a138_hci_transport *t) {
    uint32_t v;
    if(!read_reg(t,RX_HANDLE,&v))return 0;
    if(v&~UINT32_C(0x10fff)||(v&4095u)!=t->rx.handle||
       (t->rx.retired&&!(v&65536u))){t->fault=A138_HCI_FAULT_DESCRIPTOR;return 0;}
    t->rx.retired=(uint8_t)((v>>16)&1u);return 1;
}
static void rx_step(struct a138_hci_transport *t) {
    struct a138_hci_rx *r=&t->rx;uint32_t v,meta;
    if(t->rx_phase==2u){
        if(rx_identity(t,r->epoch,r->ticket))(void)rx_retirement(t);
        return;
    }
    if(!t->rx_phase) {
        if(!read_reg(t,RX_STATUS,&v)||!(v&256u))return;
        if(!read_reg(t,RX_EPOCH,&r->epoch)||!read_reg(t,RX_GENERATION,&r->generation)||
           !read_reg(t,RX_TICKET,&r->ticket)||!read_reg(t,RX_META,&meta)||
           !read_reg(t,RX_HANDLE,&v)||!read_reg(t,RX_TOKEN,&r->token))return;
        r->type=(uint8_t)(meta&15u);r->owner=(uint8_t)((meta>>8)&3u);
        r->response=(uint8_t)((meta>>10)&1u);r->bytes=(uint16_t)((meta>>16)&511u);
        r->handle=(uint16_t)(v&4095u);r->retired=(uint8_t)((v>>16)&1u);
        if(r->epoch!=t->epoch||!r->ticket||meta&~UINT32_C(0x1ff070f)||v&~UINT32_C(0x10fff)||
           (r->type!=A138_HCI_ACL&&r->type!=A138_HCI_EVENT)||r->bytes<2u||r->bytes>A138_HCI_BYTES||
           (r->type==A138_HCI_ACL&&(r->bytes<4u||r->response||r->token||!r->generation))||
           (r->response&&(r->type!=A138_HCI_EVENT||r->owner!=2u||!r->token))||
           (!r->response&&r->token)) {t->fault=A138_HCI_FAULT_DESCRIPTOR;return;}
        if(!rx_identity(t,r->epoch,r->ticket))return;
        t->rx_offset=0;t->rx_phase=1;return;
    }
    unsigned n=r->bytes-t->rx_offset;if(n>A138_HCI_SLICE)n=A138_HCI_SLICE;
    for(unsigned i=0;i<n;i++) {
        if(!write_reg(t,RX_INDEX,t->rx_offset)||!read_reg(t,RX_BYTE,&v))return;
        if(v>255u){t->fault=A138_HCI_FAULT_DESCRIPTOR;return;}
        r->data[t->rx_offset++]=(uint8_t)v;
    }
    if(t->rx_offset==r->bytes&&rx_identity(t,r->epoch,r->ticket)&&rx_retirement(t))t->rx_phase=2;
}
void a138_hci_step(struct a138_hci_transport *t) {
    uint32_t status,e,limits,id,caps;
    if(!t||t->fault)return;
    if(!read_reg(t,TIME_MS,&t->now_ms)||!read_reg(t,STATUS,&status)||!read_reg(t,EPOCH,&e))return;
    t->available=(uint8_t)((status>>4)&1u);
    if(status&6u){t->fault=A138_HCI_FAULT_HARDWARE;return;}
    if(!(status&1u)){if(t->ready)t->fault=A138_HCI_FAULT_IDENTITY;return;}
    if(!e||(t->ready&&t->epoch!=e)){t->fault=A138_HCI_FAULT_IDENTITY;return;}
    if(!t->ready) {
        if(!read_reg(t,ID,&id)||!read_reg(t,CAPS,&caps)||!read_reg(t,LIMIT,&limits))return;
        if(id!=UINT32_C(0x48434931)||caps!=UINT32_C(0x01040114)||
           (limits&65535u)<4u||(limits&65535u)>276u||(limits>>16)>276u) {
            t->fault=A138_HCI_FAULT_IDENTITY;return;
        }
        t->epoch=e;t->br_limit=(uint16_t)limits;t->le_limit=(uint16_t)(limits>>16);t->ready=1;
    }
    tx_step(t);if(!t->fault)rx_step(t);
}
int a138_hci_response_delivered(struct a138_hci_transport *t,uint32_t token) {
    if(!t||t->fault||!t->accepted||t->tx_type!=A138_HCI_COMMAND||
       t->tx_token!=token||t->response_done)return 0;
    t->response_done=1;return 1;
}
int a138_hci_tx_retire(struct a138_hci_transport *t) {
    if(!t||t->fault||!t->tx_phase||(!t->rejected&&!(t->accepted&&t->transport_done&&t->response_done)))return 0;
    if(!write_reg(t,TX_ACK,t->tx_token))return 0;
    memset(t->tx,0,sizeof t->tx);t->tx_phase=0;
    t->accepted=t->transport_done=t->response_done=t->rejected=t->uncertain=0;
    return 1;
}
const struct a138_hci_rx *a138_hci_rx_peek(const struct a138_hci_transport *t) {
    return t&&!t->fault&&t->rx_phase==2u?&t->rx:0;
}
int a138_hci_rx_release(struct a138_hci_transport *t,uint32_t e,uint32_t ticket) {
    if(!t||t->fault||t->rx_phase!=2u||t->rx.epoch!=e||t->rx.ticket!=ticket)return 0;
    if(!rx_identity(t,e,ticket)||!write_reg(t,RX_RELEASE_EPOCH,e)||!write_reg(t,RX_RELEASE,ticket))return 0;
    memset(&t->rx,0,sizeof t->rx);t->rx_phase=0;return 1;
}
