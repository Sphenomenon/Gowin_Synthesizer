#include "classic_security.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"check %u line %u: %s\n",checks,__LINE__,#x);exit(1);}}while(0)
static struct a138_classic_service classic;
static struct a138_security sec;
static const uint8_t peer[6]={1,2,3,4,5,6},other[6]={7,8,9,10,11,12};
static const uint8_t local_address[6]={0x21,0x43,0x65,0x87,0xa9,0xcb};
static struct a138_bond durable;
static unsigned present,loads,replaces,deletes,replace_busy,replace_error,delete_busy,delete_error,load_error,load_corrupt;
static uint32_t now,generation;
static unsigned order;
static void le(uint8_t *p,unsigned x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static unsigned little(const uint8_t *p){return p[0]+256u*p[1];}
static enum a138_bond_result load(void *ctx,const uint8_t p[6],struct a138_bond *b){
    CHECK(ctx==&durable);++loads;if(load_error)return A138_BOND_ERROR;
    if(!present||memcmp(p,durable.peer,6))return A138_BOND_MISSING;*b=durable;
    if(load_corrupt==1)b->peer[5]^=1;if(load_corrupt==2)b->type=3;
    if(load_corrupt==3)b->minimum_size=6;if(load_corrupt==4)b->version=2;
    return A138_BOND_OK;
}
static enum a138_bond_result replace(void *ctx,const struct a138_bond *b,uint32_t expected){
    CHECK(ctx==&durable);++replaces;
    if(replace_busy)return A138_BOND_BUSY;if(replace_error)return A138_BOND_ERROR;
    CHECK(expected==(present?durable.revision:0u)&&b->revision==expected+1u);
    durable=*b;present=1;return A138_BOND_OK;
}
static enum a138_bond_result delete(void *ctx,const uint8_t p[6],uint32_t expected){
    CHECK(ctx==&durable);++deletes;
    if(delete_busy)return A138_BOND_BUSY;if(delete_error)return A138_BOND_ERROR;
    CHECK(present&&memcmp(p,durable.peer,6)==0&&expected==durable.revision);
    memset(&durable,0,sizeof durable);present=0;return A138_BOND_OK;
}
static void pump(void){CHECK(a138_security_pump(&sec)==A138_SECURITY_OK);}
static void advance(unsigned ms){now+=ms;CHECK(a138_security_tick(&sec,77,now)==A138_SECURITY_OK);}
static void reset(unsigned known){
    struct a138_bond_store store={&durable,load,replace,delete};
    memset(&durable,0,sizeof durable);present=known;loads=replaces=deletes=0;
    replace_busy=replace_error=delete_busy=delete_error=load_error=load_corrupt=0;now=100;generation=1;
    if(known){durable.version=1;durable.revision=7;memcpy(durable.peer,peer,6);
        memset(durable.key,0x5a,16);durable.type=4;durable.minimum_size=16;}
    a138_classic_init(&classic);a138_security_init(&sec);
#ifndef A138_SINGLE_BLE_RECORDING
    CHECK(a138_security_start(&sec,77,276,&classic,&store)==A138_SECURITY_OK);
    CHECK(a138_security_start(&sec,77,276,&classic,&store)==A138_SECURITY_STALE);
#else
    (void)store;
    CHECK(a138_security_start(&sec,77,276,&classic,&store)==A138_SECURITY_ARGUMENT);
    CHECK(a138_security_start_session(&sec,77,276,&classic)==A138_SECURITY_OK);
    CHECK(a138_security_start_session(&sec,77,276,&classic)==A138_SECURITY_STALE);
#endif
    CHECK(a138_security_pump(&sec)==A138_SECURITY_BUSY);
    CHECK(a138_security_tick(&sec,78,now)==A138_SECURITY_STALE);
    CHECK(a138_security_tick(&sec,77,now)==A138_SECURITY_OK);
}
static struct a138_security_command take(unsigned op){
    struct a138_security_command c,again;CHECK(a138_security_tx_peek(&sec,&c)==A138_SECURITY_OK);
    CHECK(c.opcode==op&&little(c.data)==op&&c.data[2]==c.bytes-3u&&c.epoch==77);
    if(op==0x0406u)CHECK(c.data[5]==0x05u||c.data[5]==0x13u); /* valid Disconnect reason, not raw procedure status */
    CHECK(a138_security_tx_peek(&sec,&again)==A138_SECURITY_OK&&!memcmp(&c,&again,sizeof c));
    CHECK(a138_security_tx_result(&sec,78,c.token,A138_CLASSIC_ACCEPTED)==A138_SECURITY_STALE);
    CHECK(a138_security_tx_result(&sec,77,c.token+1u,A138_CLASSIC_ACCEPTED)==A138_SECURITY_STALE);
    CHECK(a138_security_tx_result(&sec,77,c.token,A138_CLASSIC_REJECTED)==A138_SECURITY_OK);
    CHECK(a138_security_tx_peek(&sec,&again)==A138_SECURITY_OK&&!memcmp(&c,&again,sizeof c));
    CHECK(a138_security_tx_result(&sec,77,c.token,A138_CLASSIC_ACCEPTED)==A138_SECURITY_OK);
    CHECK(a138_security_tx_result(&sec,77,c.token,A138_CLASSIC_ACCEPTED)==A138_SECURITY_STALE);
    CHECK(a138_security_tx_peek(&sec,&again)==A138_SECURITY_BUSY);return c;
}
static void respond(struct a138_security_command c,unsigned status,unsigned async,const uint8_t *extra,unsigned bytes){
    uint8_t b[80];unsigned n=async?6u:6u+bytes;memset(b,0,sizeof b);
    b[0]=async?15:14;b[1]=(uint8_t)(n-2u);
    if(async){b[2]=(uint8_t)status;b[3]=1;le(b+4,c.opcode);}else{b[2]=1;le(b+3,c.opcode);b[5]=(uint8_t)status;if(bytes)memcpy(b+6,extra,bytes);}
    CHECK(a138_security_response(&sec,77,1,b,(uint16_t)n)==A138_SECURITY_STALE);
    if(order++&1u)CHECK(a138_security_transport_done(&sec,77,c.token)==A138_SECURITY_OK);
    CHECK(a138_security_response(&sec,77,2,b,(uint16_t)n)==A138_SECURITY_OK);
    if(sec.count&&sec.queue[sec.head].token==c.token){
        CHECK(!memcmp(sec.queue[sec.head].data,c.data,c.bytes));
        CHECK(a138_security_transport_done(&sec,77,c.token)==A138_SECURITY_OK);
    }
    CHECK(a138_security_transport_done(&sec,77,c.token)==A138_SECURITY_STALE);
}
static void command(unsigned op,unsigned async,const uint8_t *extra,unsigned n){struct a138_security_command c=take(op);respond(c,0,async,extra,n);}
static void startup_before_identity(void){
    uint8_t f[10]={0};struct a138_security_command c;uint32_t before=sec.next_token;
    pump();c=take(0x1003);f[6]=8;f[7]=128;respond(c,0,0,f,8);CHECK(!sec.ready);
    pump();command(0x0c56,0,0,0);CHECK(!sec.ready);
    pump();memset(f,0,sizeof f);f[0]=1;f[1]=1;f[2]=1;command(0x1004,0,f,10);CHECK(!sec.ready);
    if(sec.session_only){pump();c=take(0x0c24);CHECK(c.bytes==6&&c.data[3]==0x14&&c.data[4]==4&&c.data[5]==0x24);respond(c,0,0,0,0);}
    pump();c=take(0x0c1a);CHECK(c.data[3]==(sec.session_only?3:2));respond(c,0,0,0,0);
    CHECK(!sec.active&&!sec.secure&&!sec.local_address_valid);
    CHECK(sec.ready==!sec.session_only);
    if(!sec.session_only)CHECK(sec.next_token==before+4u);
}
static void startup(void){
    uint8_t scan=3;
    startup_before_identity();
    if(sec.session_only){
        pump();struct a138_security_command c=take(0x1009);CHECK(c.bytes==3u);
        respond(c,0,0,local_address,6);CHECK(!sec.ready&&sec.local_address_valid&&!memcmp(sec.local_address,local_address,6));
        pump();c=take(0x0c19);CHECK(c.bytes==3u&&!sec.ready);
        respond(c,0,0,&scan,1);CHECK(sec.ready&&sec.local_address_valid);
    }
}
static enum a138_security_result event(const uint8_t *p,unsigned n){return a138_security_event(&sec,77,generation,1,p,(uint16_t)n);}
static void peer_event(unsigned code,const uint8_t *extra,unsigned n){
    uint8_t b[40];b[0]=(uint8_t)code;b[1]=(uint8_t)(6u+n);memcpy(b+2,peer,6);if(n)memcpy(b+8,extra,n);
    CHECK(event(b,n+8u)==A138_SECURITY_OK);
}
static void connect(void){
    uint8_t req[12]={4,10},con[13]={3,11};memcpy(req+2,peer,6);req[11]=1;
    CHECK(event(req,sizeof req)==A138_SECURITY_OK&&sec.request_pending);
    command(0x0409,1,0,0);con[2]=0;le(con+3,0x23);memcpy(con+5,peer,6);con[11]=1;
    CHECK(event(con,sizeof con)==A138_SECURITY_OK&&sec.active&&classic.active);
    CHECK(!classic.security_ready&&!sec.secure);
}
static void remote_features(void){
    uint8_t f[15]={11,11,0,0x23,0};
    pump();command(0x041b,1,0,0);f[11]=8;f[12]=128;CHECK(event(f,13)==A138_SECURITY_OK);
    pump();pump();command(0x041c,1,0,0);memset(f,0,sizeof f);f[0]=0x23;f[1]=13;f[3]=0x23;f[5]=1;f[6]=1;f[7]=1;
    CHECK(event(f,15)==A138_SECURITY_OK);pump();pump();command(0x0411,1,0,0);
    pump();CHECK(!sec.auth_done&&!sec.secure&&sec.count==0); /* status0 is not authentication */
}
static void pairing_exchange(void){
    uint8_t io[3]={1,0,4},numeric[4]={0x40,0xe2,1,0};struct a138_security_command c;
    peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(loads==(sec.session_only?0u:1u)&&!sec.key_used);
    peer_event(0x31,0,0);c=take(0x042b);CHECK(c.data[9]==3&&c.data[10]==0&&c.data[11]==(sec.session_only?0:4));respond(c,0,0,peer,6);
    peer_event(0x32,io,3);peer_event(0x33,numeric,4);command(0x042c,0,peer,6);
}
static void pair_key(void){
    uint8_t key[17];pairing_exchange();
    memset(key,0xa6,16);key[16]=4;peer_event(0x18,key,17);CHECK(sec.new_key&&!present&&!sec.secure);
    peer_event(0x18,key,17);CHECK(sec.new_key&&!sec.closing); /* exact duplicate is idempotent */
}
static void authenticated(void){uint8_t a[5]={6,3,0,0x23,0};CHECK(event(a,5)==A138_SECURITY_OK);pump();CHECK(!sec.secure);}
static void encrypt_and_size(unsigned size){
    uint8_t b[6]={8,4,0,0x23,0,1},extra[3]={0x23,0,0};
    pump();command(0x0413,1,0,0);pump();CHECK(!sec.encrypted&&!sec.secure);
    CHECK(event(b,6)==A138_SECURITY_OK);pump();pump();extra[2]=(uint8_t)size;command(0x1408,0,extra,3);pump();
}
static void known_key(void){struct a138_security_command c;unsigned before=loads;
    peer_event(0x17,0,0);c=take(0x040b);CHECK(c.bytes==25&&!memcmp(c.data+9,durable.key,16));respond(c,0,0,peer,6);
    CHECK(sec.key_used&&loads==before+1u);
}
static void secure_new(void){reset(0);startup();connect();remote_features();pair_key();authenticated();encrypt_and_size(16);pump();CHECK(sec.secure&&classic.security_ready&&present&&replaces==1);}
static void secure_known(void){reset(1);startup();connect();remote_features();known_key();authenticated();encrypt_and_size(16);pump();CHECK(sec.secure&&classic.security_ready&&replaces==0);}
static void disconnect(void){uint8_t b[6]={5,4,0,0x23,0,0x13};CHECK(event(b,6)==A138_SECURITY_OK&&!sec.active&&!classic.active&&!sec.secure);}
static unsigned connect_psm(unsigned psm){
    uint8_t acl[16]={0x23,0x20,12,0,8,0,1,0,2,0x22,4,0,0,0,0x70,0};le(acl+12,psm);
    CHECK(a138_security_classic_acl(&sec,77,generation,acl,sizeof acl)==A138_CLASSIC_OK);
    struct a138_classic_tx t;CHECK(a138_classic_tx_peek(&classic,&t)==A138_CLASSIC_OK);
    unsigned result=little(t.data+16);
    CHECK(a138_classic_tx_result(&classic,generation,generation,t.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_OK);return result;
}
static void test_real_gate_and_bonding(void){
    reset(0);startup();connect();CHECK(connect_psm(1)==0&&classic.channel[0].allocated&&!sec.secure); /* SDP exception */
    disconnect();++generation;connect();remote_features();pair_key();authenticated();encrypt_and_size(16);
    replace_busy=1;CHECK(a138_security_pump(&sec)==A138_SECURITY_BUSY&&!sec.secure&&!classic.security_ready&&!present);
    CHECK(a138_security_pump(&sec)==A138_SECURITY_BUSY&&!sec.secure);replace_busy=0;pump();
    CHECK(sec.secure&&classic.security_ready&&durable.version==1&&durable.revision==1&&durable.type==4&&durable.minimum_size==16);
    CHECK(connect_psm(25)==0&&classic.channel[1].allocated);disconnect();++generation;connect();remote_features();known_key();authenticated();encrypt_and_size(16);pump();
    CHECK(sec.secure&&replaces==3&&loads==2); /* two BUSY calls plus actual commit */
    secure_known();CHECK(connect_psm(25)==0);classic.frame_count=1;classic.state=A138_CLASSIC_STREAMING;classic.ready=1;
    uint8_t off[6]={8,4,0,0x23,0,0};CHECK(event(off,6)==A138_SECURITY_OK&&sec.closing&&!sec.secure&&!classic.security_ready&&!classic.frame_count&&!classic.channel[1].allocated);
}
static void test_early_access_and_async_failures(void){
    uint8_t b[6];
    reset(0);startup();connect();CHECK(connect_psm(25)==3&&!classic.channel[1].allocated&&classic.security_violation&&sec.closing);
    pump();command(0x0406,1,0,0);disconnect();
    for(unsigned fail=0;fail<4;++fail){
        reset(1);startup();connect();remote_features();known_key();
        if(fail==0){uint8_t a[5]={6,3,5,0x23,0};CHECK(event(a,5)==A138_SECURITY_OK&&sec.delete_pending);pump();CHECK(!present&&deletes==1);}
        else{authenticated();pump();command(0x0413,1,0,0);memset(b,0,sizeof b);b[0]=8;b[1]=4;b[3]=0x23;b[5]=1;
            if(fail==1)b[2]=5;if(fail==2)b[5]=0;
            CHECK(event(b,6)==A138_SECURITY_OK);
            if(fail==3){pump();pump();uint8_t x[3]={0x23,0,6};command(0x1408,0,x,3);}
        }
        CHECK(!sec.secure&&sec.closing&&!classic.security_ready);pump();command(0x0406,1,0,0);disconnect();
    }
    secure_known();uint8_t refresh[5]={0x30,3,0,0x23,0};CHECK(event(refresh,5)==A138_SECURITY_OK&&!sec.secure&&!classic.security_ready);
    pump();uint8_t x[3]={0x23,0,16};command(0x1408,0,x,3);pump();pump();CHECK(sec.secure);
    refresh[2]=5;CHECK(event(refresh,5)==A138_SECURITY_OK&&sec.closing&&!sec.secure);
}
static void test_store_failures_and_revocation(void){
    for(unsigned mode=0;mode<3;++mode){
        reset(0);startup();connect();remote_features();pair_key();authenticated();encrypt_and_size(16);
        if(mode==0)replace_error=1;else replace_busy=1;
        if(mode==0)CHECK(a138_security_pump(&sec)==A138_SECURITY_FENCED);
        else{CHECK(a138_security_pump(&sec)==A138_SECURITY_BUSY);advance(999);CHECK(a138_security_pump(&sec)==A138_SECURITY_BUSY);
             advance(1);CHECK(a138_security_pump(&sec)==A138_SECURITY_FENCED);}
        CHECK(!present&&!sec.secure&&!classic.security_ready&&sec.recovery_required);
    }
    secure_known();CHECK(a138_security_forget(&sec,77,peer)==A138_SECURITY_OK&&!sec.secure&&sec.closing);
    CHECK(a138_security_forget(&sec,77,peer)==A138_SECURITY_BUSY);pump();delete_busy=1;
    CHECK(a138_security_pump(&sec)==A138_SECURITY_BUSY&&present);delete_busy=0;pump();CHECK(!present&&!sec.forget_pending);pump();command(0x0406,1,0,0);disconnect();
    ++generation;connect();remote_features();peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(!sec.key_used);
    reset(1);startup();connect();remote_features();load_error=1;peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(sec.closing&&!sec.secure&&present);
}
static void test_identity_duplicates_and_bad_inputs(void){
    uint8_t req[12]={4,10},b[40];struct a138_security_command c;
    reset(0);memcpy(req+2,peer,6);req[11]=1;CHECK(event(req,12)==A138_SECURITY_OK);command(0x040a,1,0,0);CHECK(!sec.request_pending&&!sec.ready);
    startup();req[11]=2;CHECK(event(req,12)==A138_SECURITY_OK);command(0x040a,1,0,0);req[11]=1;
    CHECK(a138_security_event(&sec,77,generation,0,req,12)==A138_SECURITY_OK);command(0x040a,1,0,0);connect();remote_features();
    memset(b,0,sizeof b);b[0]=0x17;b[1]=6;memcpy(b+2,peer,6);
    CHECK(a138_security_event(&sec,77,generation-1,1,b,8)==A138_SECURITY_STALE&&sec.count==0&&!loads);
    memcpy(b+2,other,6);CHECK(event(b,8)==A138_SECURITY_STALE);command(0x040c,0,other,6);CHECK(!sec.closing&&!loads);
    pair_key();memset(b,0xa6,16);b[0]=0xa7;b[16]=4;peer_event(0x18,b,17);CHECK(sec.closing&&!present);
    for(unsigned type=0;type<9;++type){if(type==4)continue;
        reset(0);startup();connect();remote_features();pairing_exchange();memset(b,0xa6,16);b[16]=(uint8_t)type;peer_event(0x18,b,17);CHECK(sec.closing&&!sec.secure&&!present);}
    reset(0);startup();connect();remote_features();peer_event(0x17,0,0);command(0x040c,0,peer,6);peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(sec.closing&&loads==1);
    reset(0);startup();connect();remote_features();peer_event(0x16,0,0);command(0x040e,0,peer,6);CHECK(sec.closing); /* no fixed legacy PIN */
    reset(0);pump();c=take(0x1003);b[0]=15;b[1]=4;b[2]=0;b[3]=1;le(b+4,c.opcode);
    CHECK(a138_security_response(&sec,77,2,b,6)==A138_SECURITY_FENCED); /* status cannot finish sync capability */
    reset(0);pump();c=take(0x1003);memset(b,0,sizeof b);b[0]=14;b[1]=12;b[2]=1;le(b+3,c.opcode);
    CHECK(a138_security_response(&sec,77,2,b,14)==A138_SECURITY_FENCED); /* absent SSP capability */
    for(unsigned host=0;host<=9;host+=9){
        reset(0);pump();c=take(0x1003);memset(b,0,sizeof b);b[6]=8;b[7]=128;respond(c,0,0,b,8);
        pump();command(0x0c56,0,0,0);pump();c=take(0x1004);
        memset(b,0,sizeof b);b[0]=14;b[1]=14;b[2]=1;le(b+3,c.opcode);b[6]=1;b[7]=1;b[8]=(uint8_t)host;
        CHECK(a138_security_response(&sec,77,2,b,16)==A138_SECURITY_FENCED&&!sec.ready); /* SSP host missing / unsupported SC enabled */
    }
}
static void test_transport_deadlines_and_reset(void){
    struct a138_security_command c;uint8_t b[40]={0};
    reset(0);pump();CHECK(a138_security_tick(&sec,77,1099)==A138_SECURITY_OK);
    CHECK(a138_security_tick(&sec,77,1100)==A138_SECURITY_FENCED); /* quota/offer stall bounded */
    reset(0);pump();c=take(0x1003);b[0]=14;b[1]=12;b[2]=1;le(b+3,c.opcode);b[12]=8;b[13]=128;
    CHECK(a138_security_response(&sec,77,2,b,14)==A138_SECURITY_OK);CHECK(sec.count==1&&!memcmp(sec.queue[sec.head].data,c.data,c.bytes));
    CHECK(a138_security_response(&sec,77,2,b,14)==A138_SECURITY_FENCED); /* duplicate result before retirement */
    reset(0);pump();CHECK(a138_security_tx_peek(&sec,&c)==A138_SECURITY_OK);
    CHECK(a138_security_tx_result(&sec,77,c.token,A138_CLASSIC_UNCERTAIN)==A138_SECURITY_FENCED&&sec.recovery_required);
    reset(0);startup();connect();remote_features();pair_key();authenticated();pump();c=take(0x0413);
    disconnect();CHECK(sec.count==1&&!memcmp(sec.queue[sec.head].data,c.data,c.bytes));respond(c,0,1,0,0);CHECK(!sec.secure);
    ++generation;connect();CHECK(!classic.security_ready&&!sec.secure); /* same HCI handle, new PL generation */
    reset(0);startup();connect();remote_features();pair_key();authenticated();pump();c=take(0x0413);
    disconnect();respond(c,2,1,0,0);CHECK(!sec.closing&&!sec.active&&!sec.count);
    ++generation;connect();CHECK(sec.active&&!sec.closing); /* late failed old command cannot poison reconnect */
    reset(0);startup();connect();remote_features();pair_key();authenticated();pump(); /* encryption queued but not accepted */
    disconnect();CHECK(sec.count==0); /* stale unsent commands cannot cross reconnect */
    reset(0);startup();connect();remote_features();pair_key();disconnect();
    CHECK(!sec.new_key&&!sec.key_used&&!sec.key_loaded&&a138_security_forget(&sec,77,peer)==A138_SECURITY_OK);
    pump();CHECK(!sec.forget_pending); /* interrupted uncommitted pairing cannot block forget forever */
    secure_new();a138_security_observer_reset(&sec);CHECK(sec.fenced&&sec.recovery_required&&!sec.secure&&!classic.security_ready&&!classic.frame_count);
    reset(0);CHECK(a138_security_tick(&sec,77,99)==A138_SECURITY_FENCED);
    reset(0);CHECK(a138_security_tick(&sec,77,0xfffffff0u)==A138_SECURITY_FENCED);
    reset(0);sec.clock_ms=0xfffffff0u;CHECK(a138_security_tick(&sec,77,10)==A138_SECURITY_OK); /* forward wrap */
    uint8_t late_acl[16]={0x23,0x20,12,0,8,0,1,0,2,0x22,4,0,25,0,0x70,0};
    for(unsigned violated=0;violated<2;++violated){
        if(violated){reset(0);startup();connect();CHECK(connect_psm(25)==3);pump();command(0x0406,1,0,0);}
        else secure_known();
        disconnect();CHECK(a138_security_classic_acl(&sec,77,generation,late_acl,16)==A138_CLASSIC_STALE);
        CHECK(!sec.active&&!sec.closing&&!sec.count);++generation;connect();CHECK(sec.active&&!sec.closing);
    }
    secure_known();disconnect();uint8_t late_peer[12]={0};
    const uint8_t codes[]={0x16,0x17,0x31,0x33,0x34,0x35};
    for(unsigned i=0;i<sizeof codes;++i){
        unsigned bytes=codes[i]==0x33?12u:8u;late_peer[0]=codes[i];late_peer[1]=(uint8_t)(bytes-2u);memcpy(late_peer+2,peer,6);
        CHECK(event(late_peer,bytes)==A138_SECURITY_STALE&&!sec.count&&!sec.closing&&!sec.active);
    }
    late_peer[0]=0x17;late_peer[1]=6;
    CHECK(a138_security_event(&sec,77,0,1,late_peer,8)==A138_SECURITY_STALE);c=take(0x040c);respond(c,2,0,peer,6);
    CHECK(!sec.active&&!sec.closing&&!sec.count);++generation;connect();CHECK(sec.active);
}
static void test_policy_negative_matrix(void){
    uint8_t b[40]={0},req[12]={4,10},con[13]={3,11};struct a138_security_command c;
    reset(0);startup();memcpy(req+2,peer,6);req[11]=1;CHECK(event(req,12)==A138_SECURITY_OK);
    CHECK(event(req,12)==A138_SECURITY_STALE&&sec.count==1); /* no Reject races accepted duplicate */
    le(con+3,0x23);memcpy(con+5,peer,6);con[11]=1;
    CHECK(event(con,13)==A138_SECURITY_FENCED&&!classic.active); /* Accept was merely offered */
    reset(0);startup();CHECK(event(req,12)==A138_SECURITY_OK);c=take(0x0409);respond(c,0x0d,1,0,0);
    CHECK(!sec.request_pending&&!sec.closing&&!sec.active);connect();
    for(unsigned mode=0;mode<4;++mode){
        reset(1);startup();connect();remote_features();
        load_corrupt=mode+1;
        peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(sec.closing&&!sec.secure&&present);
    }
    reset(0);startup();connect();remote_features();pair_key();authenticated();encrypt_and_size(6);
    CHECK(sec.closing&&!sec.secure&&!present&&!replaces);
    reset(1);startup();connect();remote_features();known_key();authenticated();encrypt_and_size(15);
    CHECK(sec.closing&&!sec.secure&&present&&!replaces); /* forbid negotiated-size downgrade */
    reset(0);startup();connect();remote_features();peer_event(0x17,0,0);command(0x040c,0,peer,6);
    peer_event(0x31,0,0);command(0x042b,0,peer,6);uint8_t io[3]={1,0,5};peer_event(0x32,io,3);
    CHECK(sec.closing&&!sec.secure);pump();command(0x0406,1,0,0);disconnect(); /* NoIO cannot meet requested MITM */
    reset(0);startup();connect();remote_features();peer_event(0x17,0,0);command(0x040c,0,peer,6);
    peer_event(0x31,0,0);command(0x042b,0,peer,6);io[2]=4;peer_event(0x32,io,3);
    memset(b,255,4);peer_event(0x33,b,4);command(0x042d,0,peer,6);CHECK(sec.closing);
    for(unsigned code=0x34;code<=0x35;++code){
        reset(0);startup();connect();remote_features();peer_event(code,0,0);
        command(code==0x34?0x042f:0x0433,0,peer,6);CHECK(sec.closing);
    }
    reset(1);startup();connect();remote_features();known_key();
    uint8_t auth[5]={6,3,0,0x24,0};CHECK(event(auth,5)==A138_SECURITY_STALE&&!sec.auth_done);
    auth[3]=0x23;CHECK(a138_security_event(&sec,77,0,1,auth,5)==A138_SECURITY_STALE&&!sec.auth_done);
    authenticated();pump();command(0x0413,1,0,0);
    uint8_t enc[6]={8,4,0,0x24,0,1};CHECK(event(enc,6)==A138_SECURITY_STALE&&!sec.encrypted);
    reset(0);startup();connect();remote_features();
    CHECK(a138_security_tick(&sec,77,now+A138_SECURITY_LINK_MS)==A138_SECURITY_OK&&sec.closing&&!sec.secure);
    CHECK(a138_security_tick(&sec,77,now+A138_SECURITY_LINK_MS+5000u)==A138_SECURITY_FENCED);
    secure_known();delete_error=1;CHECK(a138_security_forget(&sec,77,peer)==A138_SECURITY_OK);pump();
    CHECK(a138_security_pump(&sec)==A138_SECURITY_FENCED&&present&&!sec.secure&&sec.recovery_required);
    reset(0);uint8_t hardware[3]={16,1,1};CHECK(event(hardware,3)==A138_SECURITY_FENCED);
    reset(1);startup();connect();remote_features();known_key();
    uint8_t lost[5]={6,3,6,0x23,0};CHECK(event(lost,5)==A138_SECURITY_OK&&sec.delete_pending);pump();pump();
    c=take(0x0406);CHECK(c.data[5]==5&&sec.close_cause==6&&!present);respond(c,0,1,0,0);disconnect();
    ++generation;connect();remote_features();peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(!sec.key_used); /* remote forgot key -> next actual link pairs */
}
static void test_valid_envelope_fuzz(void){
    struct a138_security saved;struct a138_classic_service saved_classic;uint8_t b[48];uint32_t random=0x138a350u;
    static const uint8_t codes[]={3,4,5,6,8,11,0x10,0x16,0x17,0x18,0x23,0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x3d,0x59};
    reset(0);startup();connect();remote_features();saved=sec;saved_classic=classic;
    for(unsigned i=0;i<4000;++i){
        sec=saved;classic=saved_classic;random=random*1664525u+1013904223u;unsigned n=2u+(random%44u);
        for(unsigned j=0;j<n;++j){random=random*1664525u+1013904223u;b[j]=(uint8_t)(random>>24);}
        b[0]=codes[i%(sizeof codes/sizeof codes[0])];b[1]=(uint8_t)(n-2u);if(n>=8u&&(i&1u))memcpy(b+2,peer,6);
        enum a138_security_result r=event(b,n);CHECK((unsigned)r<=A138_SECURITY_FENCED&&!sec.secure&&!classic.security_ready&&!replaces);
    }
}
static void test_peer_initiated_security_interleave(void){
    uint8_t basic[13]={11,11,0,0x23,0},host[15]={0x23,13,0,0x23,0,1,1,1};
    basic[11]=8;basic[12]=128;
    reset(1);startup();connect();pump();command(0x041b,1,0,0);
    known_key();authenticated();CHECK(sec.auth_done&&!sec.remote_basic&&!sec.secure);
    CHECK(event(basic,13)==A138_SECURITY_OK);pump();pump();command(0x041c,1,0,0);
    CHECK(event(host,15)==A138_SECURITY_OK);pump();pump();encrypt_and_size(16);pump();CHECK(sec.secure);
    reset(0);startup();connect();pump();command(0x041b,1,0,0);
    peer_event(0x17,0,0);command(0x040c,0,peer,6);peer_event(0x31,0,0);
    CHECK(sec.io_pending&&!sec.count&&!sec.io_replied);
    uint8_t io[3]={1,0,4};peer_event(0x32,io,3);
    CHECK(event(basic,13)==A138_SECURITY_OK);pump();pump();command(0x041c,1,0,0);
    CHECK(event(host,15)==A138_SECURITY_OK);pump();command(0x042b,0,peer,6);
    uint8_t numeric[4]={1,0,0,0},key[17];peer_event(0x33,numeric,4);command(0x042c,0,peer,6);
    memset(key,0x31,16);key[16]=4;peer_event(0x18,key,17);authenticated();pump();encrypt_and_size(16);pump();
    CHECK(sec.secure&&present&&replaces==1); /* no duplicate local AuthenticationRequested */
    reset(0);startup();connect();pump();command(0x041b,1,0,0);
    peer_event(0x17,0,0);command(0x040c,0,peer,6);peer_event(0x31,0,0);CHECK(sec.io_pending);
    advance(1000);CHECK(sec.closing&&!sec.io_pending);command(0x0434,0,peer,6);CHECK(!sec.secure);
}
static void reset_session(void){
    reset(0);
#ifndef A138_SINGLE_BLE_RECORDING
    a138_classic_init(&classic);a138_security_init(&sec);
    CHECK(a138_security_start_session(&sec,77,276,&classic)==A138_SECURITY_OK);
    CHECK(a138_security_tick(&sec,77,now)==A138_SECURITY_OK);
#endif
    CHECK(sec.session_only&&!sec.store.load&&!sec.store.replace_atomic&&!sec.store.delete_atomic);
}
static void test_session_local_identity(void){
    uint8_t b[24],extra[9],scan=3;
    for(unsigned which=0;which<2u;++which){
        for(unsigned bytes=0;bytes<9u;++bytes){
            if(bytes==(which?1u:6u))continue;
            reset_session();startup_before_identity();pump();
            struct a138_security_command c=take(0x1009);
            if(which){respond(c,0,0,local_address,6);CHECK(!sec.ready);pump();c=take(0x0c19);}
            memset(b,0,sizeof b);b[0]=14;b[1]=(uint8_t)(4u+bytes);b[2]=1;le(b+3,c.opcode);
            memcpy(b+6,local_address,6);if(which)b[6]=3;
            CHECK(a138_security_response(&sec,77,2,b,(uint16_t)(6u+bytes))==A138_SECURITY_FENCED);
            CHECK(sec.fenced&&!sec.ready&&!sec.secure);
        }
        for(unsigned failure=1;failure<=4u;++failure){
            reset_session();startup_before_identity();pump();struct a138_security_command c=take(0x1009);
            if(which){respond(c,0,0,local_address,6);pump();c=take(0x0c19);}
            unsigned n=which?7u:12u;memset(b,0,sizeof b);b[0]=14;b[1]=(uint8_t)(n-2u);b[2]=1;
            le(b+3,c.opcode);b[5]=(uint8_t)failure;memcpy(b+6,local_address,6);if(which)b[6]=3;
            CHECK(a138_security_response(&sec,77,2,b,(uint16_t)n)==A138_SECURITY_FENCED&&!sec.ready);
        }
        /* Wrong owner/epoch cannot consume the unique accepted command. */
        reset_session();startup_before_identity();pump();struct a138_security_command c=take(0x1009);
        if(which){respond(c,0,0,local_address,6);pump();c=take(0x0c19);}
        unsigned n=which?7u:12u;memset(b,0,sizeof b);b[0]=14;b[1]=(uint8_t)(n-2u);b[2]=1;
        le(b+3,c.opcode);memcpy(b+6,local_address,6);if(which)b[6]=3;
        CHECK(a138_security_response(&sec,78,2,b,(uint16_t)n)==A138_SECURITY_STALE);
        CHECK(a138_security_response(&sec,77,1,b,(uint16_t)n)==A138_SECURITY_STALE);
        CHECK(a138_security_transport_done(&sec,77,c.token+1u)==A138_SECURITY_STALE);
        CHECK(!sec.ready&&!sec.queue[sec.head].response_done&&!sec.queue[sec.head].transport_done);
        respond(c,0,0,which?&scan:local_address,which?1u:6u);CHECK(sec.ready==which);
    }
    for(unsigned fill=0;fill<2u;++fill){
        reset_session();startup_before_identity();pump();struct a138_security_command c=take(0x1009);
        memset(b,0,sizeof b);b[0]=14;b[1]=10;b[2]=1;le(b+3,c.opcode);memset(b+6,fill?255:0,6);
        CHECK(a138_security_response(&sec,77,2,b,12)==A138_SECURITY_FENCED&&!sec.local_address_valid&&!sec.ready);
    }
    for(unsigned value=0;value<256u;++value){
        if(value==3u)continue;
        reset_session();startup_before_identity();pump();command(0x1009,0,local_address,6);CHECK(!sec.ready);
        pump();struct a138_security_command c=take(0x0c19);
        memset(b,0,sizeof b);b[0]=14;b[1]=5;b[2]=1;le(b+3,c.opcode);b[6]=(uint8_t)value;
        CHECK(a138_security_response(&sec,77,2,b,7)==A138_SECURITY_FENCED&&!sec.ready);
    }
    reset_session();startup_before_identity();pump();command(0x1009,0,local_address,6);pump();
    struct a138_security_command c=take(0x0c19);sec.local_address_valid=0;
    memset(b,0,sizeof b);b[0]=14;b[1]=5;b[2]=1;le(b+3,c.opcode);b[6]=3;
    CHECK(a138_security_response(&sec,77,2,b,7)==A138_SECURITY_FENCED&&!sec.ready);
    /* Exact 48-bit identity is retained, including an interior zero byte. */
    reset_session();startup_before_identity();pump();memcpy(extra,local_address,6);extra[2]=0;
    command(0x1009,0,extra,6);CHECK(sec.local_address_valid&&!sec.ready&&!memcmp(sec.local_address,extra,6));
    pump();command(0x0c19,0,&scan,1);CHECK(sec.ready&&!loads&&!replaces&&!deletes);
}
static void erased_key(void){for(unsigned i=0;i<16;i++)CHECK(sec.bond.key[i]==0);}
static void early_io_features(void){
    uint8_t basic[13]={11,11,0,0x23,0},host[15]={0x23,13,0,0x23,0,1,1,1};
    basic[11]=8;basic[12]=128;
    pump();command(0x041b,1,0,0);CHECK(event(basic,13)==A138_SECURITY_OK);
    pump();pump();command(0x041c,1,0,0);CHECK(event(host,15)==A138_SECURITY_OK);pump();
}
static void test_io_before_key_request(void){
    for(unsigned mode=0;mode<3;++mode){
        uint8_t io[3]={1,0,3},numeric[4]={1,0,0,0},key[17],auth[5]={6,3,0,0x23,0};
        reset_session();startup();connect();
        peer_event(0x31,0,0);CHECK(sec.io_pending&&!sec.key_loaded&&!sec.closing&&sec.peer_auth_started);
        uint32_t deadline=sec.io_started_ms;advance(20);peer_event(0x31,0,0);
        CHECK(sec.io_pending&&sec.io_started_ms==deadline&&!sec.count&&!sec.closing);
        peer_event(0x32,io,3);early_io_features();CHECK(sec.count==1&&!sec.io_pending);
        unsigned count=sec.count;peer_event(0x31,0,0);CHECK(sec.count==count&&!sec.closing);
        command(0x042b,0,peer,6);CHECK(sec.io_replied);
        peer_event(0x31,0,0);CHECK(!sec.count&&!sec.closing); /* Already replied is idempotent too. */
        if(mode==1){peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(sec.key_loaded);}
        peer_event(0x33,numeric,4);command(0x042c,0,peer,6);
        /* A real success event may precede KeyNotify. It grants no audio;
         * P_AUTH still waits for the actual accepted type4 key below. */
        CHECK(event(auth,5)==A138_SECURITY_OK&&sec.auth_done&&!sec.secure&&!classic.security_ready);
        pump();pump();CHECK(!sec.count&&!sec.encrypt_sent&&!sec.new_key&&!sec.secure&&!classic.security_ready);
        memset(key,0xa6,16);key[16]=(uint8_t)(mode==2?5:4);peer_event(0x18,key,17);
        if(mode==2){
            CHECK(sec.closing&&!sec.secure&&!classic.security_ready&&!sec.new_key);
            CHECK((sec.close_context&UINT32_C(0xfc0000ff))==UINT32_C(0xd4000018));
            uint32_t first=sec.close_context;io[0]=5;peer_event(0x32,io,3);CHECK(sec.close_context==first);
            continue;
        }
        CHECK(sec.new_key&&!sec.secure&&!classic.security_ready&&!sec.auth_sent);
        pump();pump();encrypt_and_size(16);pump();
        CHECK(sec.secure&&classic.security_ready&&sec.auth_done&&sec.encrypted&&sec.key_size==16);
        CHECK(!loads&&!replaces&&!deletes&&!sec.close_context);erased_key();
    }
#ifndef A138_SINGLE_BLE_RECORDING
    /* A durable owner must actually query its backend even when peer SSP
     * starts with IO; request order does not manufacture a missing-key fact. */
    reset(0);startup();connect();peer_event(0x31,0,0);early_io_features();
    CHECK(sec.io_pending&&!sec.key_loaded&&!sec.count&&!loads&&!sec.closing);
    peer_event(0x31,0,0);CHECK(sec.io_pending&&!sec.count&&!sec.closing);
    peer_event(0x17,0,0);command(0x040c,0,peer,6);CHECK(loads==1&&sec.key_loaded);
    pump();command(0x042b,0,peer,6);CHECK(sec.io_replied&&!sec.io_pending&&!sec.secure);
#endif
}
static void test_session_phone_ssp(void){
    /* Xiaomi Civi 5 Pro HCI capture, 2026-11-02: DisplayYesNo, no OOB,
     * DedicatedBonding+MITM (01 00 03), after our NoIO/NoBonding reply.
     * Also cover the other valid MITM requests with the same Just Works
     * association; none may open AVDTP before authentication+encryption. */
    for(unsigned auth=1;auth<=5;auth+=2){
        uint8_t io[3]={1,0,(uint8_t)auth},numeric[4]={1,0,0,0},key[17];
        reset_session();startup();connect();remote_features();
        peer_event(0x17,0,0);command(0x040c,0,peer,6);
        peer_event(0x31,0,0);command(0x042b,0,peer,6);
        peer_event(0x32,io,3);CHECK(!sec.closing&&sec.remote_io_seen&&!sec.secure&&!classic.security_ready);
        peer_event(0x33,numeric,4);command(0x042c,0,peer,6);
        memset(key,0xa6,16);key[16]=4;peer_event(0x18,key,17);
        CHECK(!sec.secure&&!classic.security_ready&&!loads&&!replaces&&!deletes);
        authenticated();CHECK(!sec.secure&&!classic.security_ready);
        encrypt_and_size(16);pump();CHECK(sec.secure&&classic.security_ready);
        erased_key();CHECK(connect_psm(25)==0);disconnect();
    }
    /* Reserved peer fields remain invalid for session-only audio too. */
    for(unsigned field=0;field<3;++field){
        uint8_t io[3]={1,0,3};io[field]=(uint8_t)(field==0?5:field==1?4:6);
        reset_session();startup();connect();remote_features();
        peer_event(0x17,0,0);command(0x040c,0,peer,6);
        peer_event(0x31,0,0);command(0x042b,0,peer,6);peer_event(0x32,io,3);
        CHECK(sec.closing&&!sec.secure&&!classic.security_ready);
    }
}
static void test_session_only(void){
    reset_session();startup();connect();remote_features();pair_key();
    CHECK(!loads&&!replaces&&!deletes&&!sec.secure&&!classic.security_ready);
    authenticated();CHECK(!sec.secure);encrypt_and_size(16);pump();
    CHECK(sec.secure&&classic.security_ready&&!sec.new_key&&!present&&!sec.bond.revision);
    CHECK(sec.bond.minimum_size==16&&!loads&&!replaces&&!deletes);erased_key();
    CHECK(connect_psm(25)==0);disconnect();erased_key();CHECK(!sec.bond.minimum_size);
    ++generation;connect();remote_features();pair_key();authenticated();encrypt_and_size(16);pump();
    CHECK(sec.secure&&!loads&&!replaces&&!deletes);erased_key();
    CHECK(a138_security_forget(&sec,77,peer)==A138_SECURITY_OK&&sec.closing&&!sec.secure);
    CHECK(!sec.forget_pending&&!sec.delete_pending&&!loads&&!replaces&&!deletes);erased_key();
    reset_session();startup();connect();remote_features();pair_key();authenticated();encrypt_and_size(6);
    CHECK(sec.closing&&!sec.secure&&!classic.security_ready&&!loads&&!replaces&&!deletes);erased_key();
    reset_session();startup();connect();remote_features();pair_key();
    a138_security_observer_reset(&sec);CHECK(sec.fenced&&!sec.secure);erased_key();
    CHECK(!loads&&!replaces&&!deletes);
    /* Phone-initiated SSP may precede our explicit remote-feature result.
     * The deferred reply must use the same NoBonding policy. */
    reset_session();startup();connect();pump();command(0x041b,1,0,0);
    peer_event(0x17,0,0);command(0x040c,0,peer,6);peer_event(0x31,0,0);CHECK(sec.io_pending);
    uint8_t io[3]={1,0,0},basic[13]={11,11,0,0x23,0},host[15]={0x23,13,0,0x23,0,1,1,1};
    peer_event(0x32,io,3);basic[11]=8;basic[12]=128;CHECK(event(basic,13)==A138_SECURITY_OK);
    pump();pump();command(0x041c,1,0,0);CHECK(event(host,15)==A138_SECURITY_OK);pump();
    struct a138_security_command reply=take(0x042b);CHECK(reply.data[11]==0);respond(reply,0,0,peer,6);
    CHECK(!loads&&!replaces&&!deletes&&!sec.secure);
}
int main(void){
#ifndef A138_SINGLE_BLE_RECORDING
    test_real_gate_and_bonding();test_early_access_and_async_failures();test_store_failures_and_revocation();
    test_identity_duplicates_and_bad_inputs();test_transport_deadlines_and_reset();test_policy_negative_matrix();
    test_peer_initiated_security_interleave();test_valid_envelope_fuzz();
#endif
    test_session_only();
    test_io_before_key_request();
    test_session_phone_ssp();
    test_session_local_identity();
    printf("classic security source-stage: %u checks passed\n",checks);return 0;
}
