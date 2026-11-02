/* One bounded CPU BR/EDR connection/security policy owner. Transport/credits
 * remain in the shared FPGA HCI owner. See CLASSIC_SECURITY_SOURCE_STAGE.md. */
#include "classic_security.h"
#include <string.h>

enum { P_NONE,P_ACCEPT,P_BASIC,P_HOST,P_AUTH,P_ENCRYPT,P_SIZE,P_STORE,P_SECURE };
enum { C_LOCAL_FEATURES=1,C_SSP,C_LOCAL_HOST,C_CLASS,C_SCAN,C_ACCEPT,C_REJECT,
    C_BASIC,C_HOST,C_AUTH,C_ENCRYPT,C_SIZE,C_KEY,C_KEY_NEG,C_IO,C_IO_NEG,
    C_CONFIRM,C_CONFIRM_NEG,C_PIN_NEG,C_PASSKEY_NEG,C_OOB_NEG,C_DISCONNECT,
    C_LOCAL_ADDRESS,C_READ_SCAN };
enum { F_PROTOCOL=1,F_TIMEOUT,F_UNCERTAIN,F_STORAGE,F_POLICY,F_CLOCK,F_CAPACITY };

static uint16_t le(const uint8_t *p) { return (uint16_t)(p[0]|(uint16_t)p[1]<<8); }
static void putle(uint8_t *p,uint16_t v) { p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8); }
static int same(const uint8_t *a,const uint8_t *b) { return memcmp(a,b,6)==0; }
static int good_peer(const uint8_t *p) {
    unsigned z=0,f=0;for(unsigned i=0;i<6u;++i){z+=p[i]==0u;f+=p[i]==255u;}return z!=6u&&f!=6u;
}
static void wipe(void *p,unsigned n) { volatile uint8_t *v=p;while(n--)*v++=0; }
static enum a138_security_result identity(struct a138_security *s,uint32_t e) {
    if(!s)return A138_SECURITY_ARGUMENT;
    if(!s->started||e!=s->epoch)return A138_SECURITY_STALE;
    return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
}
static void revoke(struct a138_security *s) {
    s->secure=0;
    if(s->session_only)wipe(s->bond.key,sizeof s->bond.key);
    if(s->active)(void)a138_classic_security(s->classic,s->generation,s->generation,0);
}
static enum a138_security_result fence(struct a138_security *s,uint8_t why) {
    revoke(s);s->fenced=1;s->ready=0;s->recovery_required=1;s->failure=why;
    /* Accepted bytes remain stable for the transport reader. The PL owner
     * must recover the controller; no command/credit refund is inferred. */
    return A138_SECURITY_FENCED;
}
static void close_link(struct a138_security *s,uint8_t why) {
    if(!s->active)return;
    revoke(s);if(!s->closing){
        if(!s->close_context)s->close_context=UINT32_C(0xd4000000)|((uint32_t)why<<18)|
            (s->remote_host?UINT32_C(1)<<17:0u)|(s->remote_basic?UINT32_C(1)<<16:0u)|
            (s->remote_io_seen?UINT32_C(1)<<15:0u)|(s->io_replied?UINT32_C(1)<<14:0u)|
            (s->io_pending?UINT32_C(1)<<13:0u)|(s->key_loaded?UINT32_C(1)<<12:0u)|
            ((uint32_t)s->phase<<8)|s->context_event;
        s->closing=1;s->close_cause=why;s->close_reason=why==0x13u?0x13u:0x05u;s->store_started_ms=s->clock_ms;
    }
}
#ifndef A138_SINGLE_BLE_RECORDING
static int valid_bond(const struct a138_bond *b,const uint8_t *peer) {
    return b->version==1u&&b->revision!=0u&&same(b->peer,peer)&&
        (b->type==4u||b->type==5u)&&b->minimum_size>=7u&&b->minimum_size<=16u;
}
#endif
static int enqueue(struct a138_security *s,uint8_t kind,uint16_t opcode,const uint8_t *p,uint8_t n) {
    struct a138_security_command *c;
    if(s->count==A138_SECURITY_QUEUE||s->next_token==UINT32_MAX||n>22u){fence(s,F_CAPACITY);return 0;}
    c=&s->queue[(s->head+s->count)%A138_SECURITY_QUEUE];memset(c,0,sizeof *c);
    c->epoch=s->epoch;c->generation=s->active?s->generation:0;c->token=++s->next_token;
    c->started_ms=s->clock_ms;c->kind=kind;c->opcode=opcode;c->bytes=(uint8_t)(n+3u);
    putle(c->data,opcode);c->data[2]=n;if(n)memcpy(c->data+3,p,n);++s->count;return 1;
}
static int address_reply(struct a138_security *s,uint8_t kind,uint16_t op,const uint8_t *peer) {
    ++s->negative_replies;return enqueue(s,kind,op,peer,6);
}
static void retire(struct a138_security *s) {
    struct a138_security_command *c;
    if(!s->count)return;
    c=&s->queue[s->head];
    if(c->accepted&&c->transport_done&&c->response_done){
        wipe(c,sizeof *c);s->head=(uint8_t)((s->head+1u)%A138_SECURITY_QUEUE);--s->count;
    }
}
static enum a138_security_result queue_handle(struct a138_security *s,uint8_t kind,uint16_t op,uint8_t extra) {
    uint8_t p[3];putle(p,s->handle);p[2]=extra;
    return enqueue(s,kind,op,p,(kind==C_ENCRYPT||kind==C_DISCONNECT)?3u:2u)?A138_SECURITY_OK:A138_SECURITY_FENCED;
}
void a138_security_init(struct a138_security *s){if(s)memset(s,0,sizeof *s);}
enum a138_security_result a138_security_start(struct a138_security *s,uint32_t e,uint16_t limit,
        struct a138_classic_service *classic,const struct a138_bond_store *store) {
#ifdef A138_SINGLE_BLE_RECORDING
    (void)s;(void)e;(void)limit;(void)classic;(void)store;
    return A138_SECURITY_ARGUMENT; /* W has no persistent-key backend. */
#else
    if(!s||!e||!classic||!store||!store->load||!store->replace_atomic||!store->delete_atomic||limit<4u||limit>276u)
        return A138_SECURITY_ARGUMENT;
    if(s->started)return A138_SECURITY_STALE;
    s->started=1;s->epoch=e;s->tx_limit=limit;s->classic=classic;s->store=*store;return A138_SECURITY_OK;
#endif
}
enum a138_security_result a138_security_start_session(struct a138_security *s,uint32_t e,uint16_t limit,
        struct a138_classic_service *classic) {
    if(!s||!e||!classic||limit<4u||limit>276u)return A138_SECURITY_ARGUMENT;
    if(s->started)return A138_SECURITY_STALE;
    memset(&s->store,0,sizeof s->store);
    s->session_only=1;s->started=1;s->epoch=e;s->tx_limit=limit;s->classic=classic;
    return A138_SECURITY_OK;
}
enum a138_security_result a138_security_tick(struct a138_security *s,uint32_t e,uint32_t now) {
    enum a138_security_result r=identity(s,e);if(r!=A138_SECURITY_OK)return r;
    s->context_event=0xf0;
    if(s->clock_valid&&(uint32_t)(now-s->clock_ms)>=0x80000000u)return fence(s,F_CLOCK);
    s->clock_ms=now;s->clock_valid=1;
    if(s->count&&(uint32_t)(now-s->queue[s->head].started_ms)>=A138_SECURITY_COMMAND_MS)return fence(s,F_TIMEOUT);
    if(s->request_pending&&(uint32_t)(now-s->link_started_ms)>=A138_SECURITY_LINK_MS)return fence(s,F_TIMEOUT);
    if(s->active&&!s->secure&&!s->closing&&
       (uint32_t)(now-s->link_started_ms)>=A138_SECURITY_LINK_MS)close_link(s,0x05);
    if(s->closing&&(uint32_t)(now-s->store_started_ms)>=5000u)return fence(s,F_TIMEOUT);
    if(s->io_pending&&(uint32_t)(now-s->io_started_ms)>=A138_SECURITY_COMMAND_MS){
        uint8_t p[7];memcpy(p,s->peer,6);p[6]=0x18;s->io_pending=0;
        enqueue(s,C_IO_NEG,0x0434,p,7);close_link(s,0x18);
    }
    if(s->active&&!s->closing&&
       a138_classic_tick(s->classic,s->generation,s->generation,now)==A138_CLASSIC_FENCED)close_link(s,0x05);
    return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
}
enum a138_security_result a138_security_pump(struct a138_security *s) {
    uint8_t p[9];
#ifndef A138_SINGLE_BLE_RECORDING
    enum a138_bond_result br;
#endif
    if(!s||!s->started)return A138_SECURITY_ARGUMENT;
    if(s->fenced)return A138_SECURITY_FENCED;
    s->context_event=0xf1;
    if(!s->clock_valid)return A138_SECURITY_BUSY;
    retire(s);
#ifndef A138_SINGLE_BLE_RECORDING
    if(s->forget_pending){
        if(s->forget_revision==0u){
            struct a138_bond b;memset(&b,0,sizeof b);
            br=s->store.load(s->store.context,s->forget_peer,&b);
            if(br==A138_BOND_MISSING){s->forget_pending=0;return A138_SECURITY_OK;}
            if(br!=A138_BOND_OK||!valid_bond(&b,s->forget_peer)){wipe(&b,sizeof b);return fence(s,F_STORAGE);}
            s->forget_revision=b.revision;wipe(&b,sizeof b);return A138_SECURITY_OK;
        }
        br=s->store.delete_atomic(s->store.context,s->forget_peer,s->forget_revision);
        if(br==A138_BOND_BUSY){
            if((uint32_t)(s->clock_ms-s->store_started_ms)>=A138_SECURITY_STORE_MS)return fence(s,F_STORAGE);
            return A138_SECURITY_BUSY;
        }
        if(br!=A138_BOND_OK)return fence(s,F_STORAGE);
        s->forget_pending=0;return A138_SECURITY_OK;
    }
    if(s->delete_pending){
        br=s->store.delete_atomic(s->store.context,s->peer,s->bond.revision);
        if(br==A138_BOND_BUSY){
            if((uint32_t)(s->clock_ms-s->store_started_ms)>=A138_SECURITY_STORE_MS)return fence(s,F_STORAGE);
            return A138_SECURITY_BUSY;
        }
        if(br!=A138_BOND_OK)return fence(s,F_STORAGE);
        s->delete_pending=0;wipe(&s->bond,sizeof s->bond);return A138_SECURITY_OK;
    }
#else
    if(!s->session_only||s->forget_pending||s->delete_pending)return fence(s,F_POLICY);
#endif
    if(s->closing){
        if(s->active&&!s->disconnect_queued&&s->count==0u&&
           (!s->classic->security_violation||s->classic->tx_bytes==0u||
            (uint32_t)(s->clock_ms-s->store_started_ms)>=100u)){
            s->disconnect_queued=1;return queue_handle(s,C_DISCONNECT,0x0406,s->close_reason);
        }
        return A138_SECURITY_OK;
    }
    if(s->count)return A138_SECURITY_OK;
    if(s->io_pending&&s->remote_basic&&s->remote_host&&(s->session_only||s->key_loaded)){
        memcpy(p,s->peer,6);p[6]=3;p[7]=0;p[8]=s->session_only?0:4;s->io_pending=0;
        enqueue(s,C_IO,0x042b,p,9);return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
    }
    if(!s->ready){
        switch(s->local_step){
        case 0:enqueue(s,C_LOCAL_FEATURES,0x1003,0,0);break;
        case 1:p[0]=1;enqueue(s,C_SSP,0x0c56,p,1);break;
        case 2:p[0]=1;enqueue(s,C_LOCAL_HOST,0x1004,p,1);break;
        case 3:
            if(s->session_only){p[0]=0x14;p[1]=0x04;p[2]=0x24;enqueue(s,C_CLASS,0x0c24,p,3);}
            else {p[0]=2;enqueue(s,C_SCAN,0x0c1a,p,1);} /* durable default: page scan only */
            break;
        case 4:
            if(!s->session_only)return fence(s,F_PROTOCOL);
            p[0]=3;enqueue(s,C_SCAN,0x0c1a,p,1);break;
        case 5:
            if(!s->session_only)return fence(s,F_PROTOCOL);
            enqueue(s,C_LOCAL_ADDRESS,0x1009,0,0);break;
        case 6:
            if(!s->session_only)return fence(s,F_PROTOCOL);
            enqueue(s,C_READ_SCAN,0x0c19,0,0);break;
        default:return fence(s,F_PROTOCOL);
        }
        return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
    }
    if(!s->active)return A138_SECURITY_OK;
    switch(s->phase){
    case P_BASIC:
        if(!s->requested){s->requested=1;return queue_handle(s,C_BASIC,0x041b,0);}
        if(s->remote_basic){s->phase=P_HOST;s->requested=0;}
        break;
    case P_HOST:
        if(!s->requested){putle(p,s->handle);p[2]=1;s->requested=1;enqueue(s,C_HOST,0x041c,p,3);}
        else if(s->remote_host){s->phase=P_AUTH;s->requested=0;}
        break;
    case P_AUTH:
        if(!s->requested){s->requested=1;
            if(!s->peer_auth_started)return queue_handle(s,C_AUTH,0x0411,0);}
        if(s->auth_done&&(s->key_used||s->new_key)){s->phase=P_ENCRYPT;s->requested=0;}
        break;
    case P_ENCRYPT:
        if(!s->requested){s->requested=1;return queue_handle(s,C_ENCRYPT,0x0413,1);}
        if(s->encrypted){s->phase=P_SIZE;s->requested=0;}
        break;
    case P_SIZE:
        if(!s->requested){s->requested=1;return queue_handle(s,C_SIZE,0x1408,0);}
        if(s->key_size){s->phase=P_STORE;s->store_started_ms=s->clock_ms;}
        break;
    case P_STORE:
        if(s->session_only){
            /* Encryption and its actual negotiated key size have completed.
             * Retain only the current link's minimum-size fact for refresh;
             * no revision or durable-key record is manufactured. */
            s->bond.minimum_size=s->key_size;s->bond.revision=0;
            wipe(s->bond.key,sizeof s->bond.key);s->new_key=0;
        }
#ifndef A138_SINGLE_BLE_RECORDING
        else if(s->new_key){
            struct a138_bond b=s->bond;
            if(b.revision==UINT32_MAX){wipe(&b,sizeof b);return fence(s,F_STORAGE);}
            b.version=1;b.minimum_size=s->key_size;++b.revision;
            br=s->store.replace_atomic(s->store.context,&b,s->bond.revision);
            if(br==A138_BOND_BUSY){wipe(&b,sizeof b);
                if((uint32_t)(s->clock_ms-s->store_started_ms)>=A138_SECURITY_STORE_MS)return fence(s,F_STORAGE);
                return A138_SECURITY_BUSY;
            }
            if(br!=A138_BOND_OK){wipe(&b,sizeof b);return fence(s,F_STORAGE);}
            s->bond=b;wipe(&b,sizeof b);s->new_key=0;
        }
#endif
        if(a138_classic_security(s->classic,s->generation,s->generation,1)!=A138_CLASSIC_OK)return fence(s,F_PROTOCOL);
        s->secure=1;s->phase=P_SECURE;break;
    default:break;
    }
    return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
}
enum a138_security_result a138_security_tx_peek(struct a138_security *s,struct a138_security_command *out) {
    if(!s||!out)return A138_SECURITY_ARGUMENT;
    if(s->fenced)return A138_SECURITY_FENCED;
    if(!s->count)return A138_SECURITY_EMPTY;
    if(s->queue[s->head].accepted)return A138_SECURITY_BUSY;
    *out=s->queue[s->head];return A138_SECURITY_OK;
}
enum a138_security_result a138_security_tx_result(struct a138_security *s,uint32_t e,uint32_t token,
        enum a138_classic_submission result) {
    enum a138_security_result r=identity(s,e);struct a138_security_command *c;
    if(r!=A138_SECURITY_OK)return r;
    if(!s->count)return A138_SECURITY_STALE;
    c=&s->queue[s->head];
    if(token!=c->token||c->accepted)return A138_SECURITY_STALE;
    if((unsigned)result>A138_CLASSIC_UNCERTAIN)return A138_SECURITY_ARGUMENT;
    if(result==A138_CLASSIC_UNCERTAIN)return fence(s,F_UNCERTAIN);
    if(result==A138_CLASSIC_ACCEPTED){
        c->accepted=1;
        if(c->kind==C_BASIC)s->basic_sent=1;
        if(c->kind==C_ACCEPT)s->accept_sent=1;
        if(c->kind==C_HOST)s->host_sent=1;
        if(c->kind==C_AUTH)s->auth_sent=1;
        if(c->kind==C_ENCRYPT)s->encrypt_sent=1;
        if(c->kind==C_KEY||c->kind==C_KEY_NEG)s->key_response_sent=1;
    }
    return A138_SECURITY_OK;
}
enum a138_security_result a138_security_transport_done(struct a138_security *s,uint32_t e,uint32_t token) {
    struct a138_security_command *c;
    if(!s||!s->started)return A138_SECURITY_ARGUMENT;
    if(e!=s->epoch||!s->count)return A138_SECURITY_STALE;
    c=&s->queue[s->head];
    if(c->token!=token||!c->accepted||c->transport_done)return A138_SECURITY_STALE;
    c->transport_done=1;retire(s);return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
}
static int async_kind(unsigned k) {
    return k==C_ACCEPT||k==C_REJECT||k==C_BASIC||k==C_HOST||k==C_AUTH||k==C_ENCRYPT||k==C_DISCONNECT;
}
enum a138_security_result a138_security_response(struct a138_security *s,uint32_t e,uint8_t owner,
        const uint8_t *p,uint16_t n) {
    enum a138_security_result r=identity(s,e);struct a138_security_command *c;uint16_t op;uint8_t status;
    if(r!=A138_SECURITY_OK)return r;
    if(owner!=2u)return A138_SECURITY_STALE;
    if(!p||n<2u||n!=(uint16_t)(p[1]+2u))return fence(s,F_PROTOCOL);
    s->context_event=p[0];
    if(!s->count)return fence(s,F_PROTOCOL);
    c=&s->queue[s->head];
    if(!c->accepted||c->response_done)return fence(s,F_PROTOCOL);
    if(p[0]==0x0fu&&n==6u){op=le(p+4);status=p[2];if(!async_kind(c->kind))return fence(s,F_PROTOCOL);}
    else if(p[0]==0x0eu&&n>=6u){op=le(p+3);status=p[5];if(async_kind(c->kind))return fence(s,F_PROTOCOL);}
    else return fence(s,F_PROTOCOL);
    if(op!=c->opcode)return fence(s,F_PROTOCOL);
    c->response_done=1;
    /* A matching late failure is no authority to close an already retired
     * generation either. Validate routing/kind/opcode first, then only retire. */
    if(c->generation&&(!s->active||c->generation!=s->generation)){retire(s);return A138_SECURITY_OK;}
    if(status){
        if(c->kind<=C_SCAN||c->kind==C_LOCAL_ADDRESS||c->kind==C_READ_SCAN)return fence(s,F_PROTOCOL);
        if(c->kind==C_ACCEPT){
            if(s->active)return fence(s,F_PROTOCOL);
            s->request_pending=0;s->accept_sent=0;s->phase=P_NONE;retire(s);return A138_SECURITY_OK;
        }
        if(c->kind==C_REJECT||c->kind==C_DISCONNECT)return fence(s,F_PROTOCOL);
        close_link(s,status);retire(s);return A138_SECURITY_OK;
    }
    switch(c->kind){
    case C_LOCAL_FEATURES:
        if(n!=14u||!(p[12]&8u)||!(p[13]&128u))return fence(s,F_POLICY);
        ++s->local_step;break;
    case C_SSP:if(n!=6u)return fence(s,F_PROTOCOL);++s->local_step;break;
    case C_LOCAL_HOST:
        if(n!=16u||p[6]!=1u||p[7]<1u||!(p[8]&1u)||(p[8]&8u))return fence(s,F_POLICY);
        ++s->local_step;break;
    case C_CLASS:if(n!=6u||!s->session_only)return fence(s,F_PROTOCOL);++s->local_step;break;
    case C_SCAN:
        if(n!=6u)return fence(s,F_PROTOCOL);
        if(s->session_only)++s->local_step;else s->ready=1;
        break;
    case C_LOCAL_ADDRESS:
        if(n!=12u||!s->session_only)return fence(s,F_PROTOCOL);
        if(!good_peer(p+6))return fence(s,F_POLICY);
        memcpy(s->local_address,p+6,6);s->local_address_valid=1;++s->local_step;break;
    case C_READ_SCAN:
        if(n!=7u||!s->session_only)return fence(s,F_PROTOCOL);
        if(!s->local_address_valid||p[6]!=3u)return fence(s,F_POLICY);
        s->ready=1;break;
    case C_SIZE:
        if(n!=9u||le(p+6)!=s->handle||p[8]<7u||p[8]>16u||
           ((s->bond.revision||s->session_only)&&p[8]<s->bond.minimum_size)){close_link(s,0x05);break;}
        s->key_size=p[8];break;
    case C_KEY:case C_KEY_NEG:case C_IO:case C_IO_NEG:case C_CONFIRM:case C_CONFIRM_NEG:
    case C_PIN_NEG:case C_PASSKEY_NEG:case C_OOB_NEG:
        if(n!=12u||!same(p+6,c->data+3))return fence(s,F_PROTOCOL);
        if(c->kind==C_IO)s->io_replied=1;
        if(c->kind==C_IO_NEG||c->kind==C_CONFIRM_NEG||c->kind==C_PIN_NEG||
           c->kind==C_PASSKEY_NEG||c->kind==C_OOB_NEG)
            if(s->active&&same(c->data+3,s->peer))close_link(s,0x18);
        break;
    default:break;
    }
    retire(s);return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
}
static enum a138_security_result stale(struct a138_security *s){++s->stale_events;return A138_SECURITY_STALE;}
static int peer_event(unsigned code) {
    return code==0x16u||code==0x17u||code==0x18u||code==0x31u||code==0x32u||
        code==0x33u||code==0x34u||code==0x35u||code==0x36u||code==0x3du;
}
enum a138_security_result a138_security_event(struct a138_security *s,uint32_t e,uint32_t g,uint8_t available,
        const uint8_t *p,uint16_t n) {
    enum a138_security_result r=identity(s,e);uint8_t code,b[22];
#ifndef A138_SINGLE_BLE_RECORDING
    enum a138_bond_result br;
#endif
    if(r!=A138_SECURITY_OK)return r;
    if(!p||n<2u||n!=(uint16_t)(p[1]+2u))return fence(s,F_PROTOCOL);
    code=p[0];
    s->context_event=code;
    if(code==0x10u||code==0x1au)return fence(s,F_PROTOCOL);
    if(code==4u){ /* Actual Connection Request, never invent accept on discovery. */
        if(n!=12u||!good_peer(p+2))return fence(s,F_PROTOCOL);
        if(s->request_pending&&same(p+2,s->peer))return stale(s);
        if(!s->ready||!available||s->active||s->request_pending||s->count||s->closing||
           s->delete_pending||s->forget_pending||p[11]!=1u){
            memcpy(b,p+2,6);b[6]=0x0d;enqueue(s,C_REJECT,0x040a,b,7);return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
        }
        memcpy(s->peer,p+2,6);s->request_pending=1;s->accept_sent=0;s->phase=P_ACCEPT;s->link_started_ms=s->clock_ms;
        memcpy(b,s->peer,6);b[6]=1;enqueue(s,C_ACCEPT,0x0409,b,7);return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
    }
    if(code==3u){
        if(n!=13u)return fence(s,F_PROTOCOL);
        if(p[2]){if(s->request_pending&&same(p+5,s->peer)){s->request_pending=0;s->phase=P_NONE;}return A138_SECURITY_OK;}
        if(!s->request_pending||!s->accept_sent||!same(p+5,s->peer)||p[11]!=1u||p[12]!=0u||
           le(p+3)>0x0effu||!g||g<=s->last_generation)return fence(s,F_PROTOCOL);
        s->request_pending=0;s->active=1;s->generation=g;s->last_generation=g;s->handle=le(p+3);
        s->phase=P_BASIC;s->requested=0;s->remote_basic=0;s->remote_host=0;s->auth_done=0;s->encrypted=0;
        s->key_size=0;s->key_loaded=0;s->key_used=0;s->new_key=0;s->io_replied=0;s->remote_io_seen=0;
        s->basic_sent=0;s->host_sent=0;s->auth_sent=0;s->encrypt_sent=0;
        s->peer_auth_started=0;s->key_response_sent=0;s->io_pending=0;
        s->closing=0;s->disconnect_queued=0;s->delete_pending=0;wipe(&s->bond,sizeof s->bond);
        return a138_classic_begin(s->classic,g,g,s->handle,s->tx_limit)==A138_CLASSIC_OK?A138_SECURITY_OK:fence(s,F_PROTOCOL);
    }
    if(code==5u){
        if(n!=6u)return fence(s,F_PROTOCOL);
        if(!s->active||g!=s->generation||le(p+3)!=s->handle)return stale(s);
        if(p[2])return A138_SECURITY_OK;
        revoke(s);(void)a138_classic_cancel(s->classic,g,g);s->active=0;s->closing=0;s->phase=P_NONE;
        s->requested=0;s->disconnect_queued=0;s->request_pending=0;
        s->io_pending=0;s->new_key=0;s->key_used=0;s->key_loaded=0;
        s->auth_done=0;s->encrypted=0;s->key_size=0;s->io_replied=0;s->remote_io_seen=0;
        s->peer_auth_started=0;s->key_response_sent=0;
        /* A failed-key revocation already requested must complete durably. */
        if(!s->delete_pending)wipe(&s->bond,sizeof s->bond);
        /* A common disconnect retires unsent commands for the old link. Only
         * the one actually accepted immutable transport slot may finish. */
        {uint8_t keep=s->count&&s->queue[s->head].accepted?1u:0u;
         for(unsigned i=keep;i<s->count;++i)wipe(&s->queue[(s->head+i)%A138_SECURITY_QUEUE],sizeof s->queue[0]);
         s->count=keep;}
        return A138_SECURITY_OK;
    }
    /* An old peer request must not create even a negative command for a new
     * or already retired context. Generation0 is only an unowned request. */
    if(!s->active){if(g!=0u)return stale(s);}
    else if(g!=s->generation)return stale(s);
    if(peer_event(code)){
        const uint8_t *peer=p+2;uint16_t expected=0;
        switch(code){case 0x16:case 0x17:case 0x31:case 0x34:case 0x35:expected=8;break;
        case 0x18:expected=25;break;case 0x32:expected=11;break;case 0x33:expected=12;break;
        case 0x36:expected=9;peer=p+3;break;case 0x3d:expected=16;break;default:break;}
        if(n!=expected)return fence(s,F_PROTOCOL);
        if(!s->active||g!=s->generation||!same(peer,s->peer)){
            if(code==0x17u)address_reply(s,C_KEY_NEG,0x040c,peer);
            else if(code==0x16u)address_reply(s,C_PIN_NEG,0x040e,peer);
            else if(code==0x31u){memcpy(b,peer,6);b[6]=0x18;enqueue(s,C_IO_NEG,0x0434,b,7);}
            else if(code==0x33u)address_reply(s,C_CONFIRM_NEG,0x042d,peer);
            else if(code==0x34u)address_reply(s,C_PASSKEY_NEG,0x042f,peer);
            else if(code==0x35u)address_reply(s,C_OOB_NEG,0x0433,peer);
            return stale(s);
        }
        if(code==0x17u){
            if((s->phase!=P_BASIC&&s->phase!=P_HOST&&s->phase!=P_AUTH)||s->closing){
                address_reply(s,C_KEY_NEG,0x040c,peer);return A138_SECURITY_OK;}
            s->peer_auth_started=1;
            if(s->key_loaded){close_link(s,0x05);address_reply(s,C_KEY_NEG,0x040c,peer);return A138_SECURITY_OK;}
            s->key_loaded=1;
            if(s->session_only){
                wipe(&s->bond,sizeof s->bond);memcpy(s->bond.peer,peer,6);
                address_reply(s,C_KEY_NEG,0x040c,peer);return A138_SECURITY_OK;
            }
#ifndef A138_SINGLE_BLE_RECORDING
            br=s->store.load(s->store.context,peer,&s->bond);
            if(br==A138_BOND_OK&&valid_bond(&s->bond,peer)){
                memcpy(b,peer,6);memcpy(b+6,s->bond.key,16);s->key_used=1;enqueue(s,C_KEY,0x040b,b,22);wipe(b,sizeof b);
            }else{
                if(br!=A138_BOND_MISSING){close_link(s,0x05);s->failure=F_STORAGE;}
                wipe(&s->bond,sizeof s->bond);memcpy(s->bond.peer,peer,6);address_reply(s,C_KEY_NEG,0x040c,peer);
            }
#else
            return fence(s,F_POLICY);
#endif
        }else if(code==0x31u){
            unsigned queued=0;
            for(unsigned j=0;j<s->count;++j)
                if(s->queue[(s->head+j)%A138_SECURITY_QUEUE].kind==C_IO)queued=1;
            if((s->phase!=P_BASIC&&s->phase!=P_HOST&&s->phase!=P_AUTH)||s->closing){
                memcpy(b,peer,6);b[6]=0x18;enqueue(s,C_IO_NEG,0x0434,b,7);close_link(s,0x18);
            }else{
                /* Incoming SSP can ask for IO before any host key lookup.
                 * Session-only has no reusable key; durable policy still waits
                 * for its actual backend lookup. A repeat preserves the first
                 * deadline and never queues a second IO reply. */
                s->peer_auth_started=1;
                if(s->io_pending||s->io_replied||queued)return A138_SECURITY_OK;
                if(!s->remote_basic||!s->remote_host||(!s->session_only&&!s->key_loaded)){
                    s->io_pending=1;s->io_started_ms=s->clock_ms;
                }else{memcpy(b,peer,6);b[6]=3;b[7]=0;b[8]=s->session_only?0:4;enqueue(s,C_IO,0x042b,b,9);}
            }
        }else if(code==0x32u){
            /* A phone can request MITM even when our NoInputNoOutput reply
             * selects Just Works. Session-only audio accepts that request,
             * but still requires the unauthenticated SSP key, successful
             * authentication, encryption and negotiated key size below.
             * Keep the durable-bond policy's stricter rejection unchanged. */
            if(p[8]>4u||p[9]>3u||p[10]>5u||(!s->session_only&&(p[10]&1u))){close_link(s,0x18);return A138_SECURITY_OK;}
            s->remote_io_seen=1;s->remote_auth=p[10];
        }else if(code==0x33u){
            uint32_t numeric=(uint32_t)le(p+8)|((uint32_t)le(p+10)<<16);
            if((s->phase==P_HOST||s->phase==P_AUTH)&&!s->closing&&s->io_replied&&s->remote_io_seen&&numeric<=999999u)
                enqueue(s,C_CONFIRM,0x042c,peer,6); /* JustWorks, no numeric comparison claimed. */
            else{address_reply(s,C_CONFIRM_NEG,0x042d,peer);close_link(s,0x18);}
        }else if(code==0x18u){
            if((s->phase!=P_HOST&&s->phase!=P_AUTH)||s->closing||(!s->session_only&&!s->key_loaded)||!s->io_replied||
               !s->remote_io_seen||p[24]!=4u||(s->bond.revision&&s->bond.type==5u)){
                close_link(s,0x05);return A138_SECURITY_OK;}
            if(s->new_key){if(s->bond.type!=p[24]||memcmp(s->bond.key,p+8,16)!=0)close_link(s,0x05);return A138_SECURITY_OK;}
            memcpy(s->bond.peer,peer,6);memcpy(s->bond.key,p+8,16);s->bond.type=p[24];s->new_key=1;s->key_used=0;
        }else if(code==0x36u){if(p[2])close_link(s,p[2]);}
        else if(code==0x16u){address_reply(s,C_PIN_NEG,0x040e,peer);close_link(s,0x18);}
        else if(code==0x34u){address_reply(s,C_PASSKEY_NEG,0x042f,peer);close_link(s,0x18);}
        else if(code==0x35u){address_reply(s,C_OOB_NEG,0x0433,peer);close_link(s,0x18);}
        /* RemoteHostSupportedFeatures is informational; the matching explicit
         * ReadRemoteExtendedFeatures completion remains the authority. */
        return s->fenced?A138_SECURITY_FENCED:A138_SECURITY_OK;
    }
    if(!s->active)return stale(s);
    if(code==0x0bu){
        if(n!=13u)return fence(s,F_PROTOCOL);
        if(le(p+3)!=s->handle)return stale(s);
        if(s->phase!=P_BASIC||!s->basic_sent||s->remote_basic)return stale(s);
        if(p[2]||!(p[11]&8u)||!(p[12]&128u))close_link(s,0x05);else s->remote_basic=1;
    }else if(code==0x23u){
        if(n!=15u)return fence(s,F_PROTOCOL);
        if(le(p+3)!=s->handle)return stale(s);
        if(s->phase!=P_HOST||!s->host_sent||s->remote_host)return stale(s);
        if(p[2]||p[5]!=1u||p[6]<1u||!(p[7]&1u))close_link(s,0x05);else s->remote_host=1;
    }else if(code==6u){
        if(n!=5u)return fence(s,F_PROTOCOL);
        if(le(p+3)!=s->handle)return stale(s);
        if((s->phase!=P_BASIC&&s->phase!=P_HOST&&s->phase!=P_AUTH)||s->auth_done||
           (!s->auth_sent&&!(s->peer_auth_started&&(s->key_response_sent||
             (s->session_only&&s->io_replied&&s->remote_io_seen)))))return stale(s);
        if(p[2]){
            if(s->key_used&&(p[2]==5u||p[2]==6u)){s->delete_pending=1;s->store_started_ms=s->clock_ms;}
            close_link(s,p[2]);
        }else s->auth_done=1;
    }else if(code==8u||code==0x59u){
        if(n!=(code==8u?6u:7u))return fence(s,F_PROTOCOL);
        if(le(p+3)!=s->handle)return stale(s);
        if(p[2]||p[5]!=1u){s->encrypted=0;close_link(s,0x05);}
        else if(s->phase==P_ENCRYPT&&s->encrypt_sent&&s->auth_done)s->encrypted=1;
        else return stale(s);
    }else if(code==0x30u){
        if(n!=5u)return fence(s,F_PROTOCOL);
        if(le(p+3)!=s->handle)return stale(s);
        if(p[2]||!s->secure){close_link(s,0x05);return A138_SECURITY_OK;}
        revoke(s);s->phase=P_SIZE;s->requested=0;s->key_size=0;s->link_started_ms=s->clock_ms;
    }else if(code==0x10u||code==0x1au)return fence(s,F_PROTOCOL);
    return A138_SECURITY_OK;
}
enum a138_classic_result a138_security_classic_acl(struct a138_security *s,uint32_t e,uint32_t g,
        const uint8_t *acl,uint16_t n) {
    enum a138_classic_result r;
    if(!s||!s->started)return A138_CLASSIC_ARGUMENT;
    s->context_event=0xf2;
    if(!s->active||e!=s->epoch||g!=s->generation)return A138_CLASSIC_STALE;
    if(s->fenced||s->closing)return A138_CLASSIC_FENCED;
    r=a138_classic_acl(s->classic,g,g,acl,n);
    if(s->classic->security_violation||r==A138_CLASSIC_FENCED)close_link(s,0x05);
    return r;
}
enum a138_security_result a138_security_forget(struct a138_security *s,uint32_t e,const uint8_t peer[6]) {
    enum a138_security_result r=identity(s,e);if(r!=A138_SECURITY_OK)return r;
    s->context_event=0xf3;
    if(!peer||!good_peer(peer))return A138_SECURITY_ARGUMENT;
    if(s->session_only){
        if(s->active&&same(peer,s->peer))close_link(s,0x13);
        return A138_SECURITY_OK;
    }
    if(s->forget_pending||s->delete_pending||s->new_key)return A138_SECURITY_BUSY;
    s->forget_pending=1;s->forget_revision=0;memcpy(s->forget_peer,peer,6);s->store_started_ms=s->clock_ms;
    if(s->active&&same(peer,s->peer))close_link(s,0x13);
    return A138_SECURITY_OK;
}
void a138_security_observer_reset(struct a138_security *s){if(s&&s->started)(void)fence(s,F_UNCERTAIN);}
