#include "classic_service.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Poison the unused receive tail in sanitizer runs: reading stale bytes
 * beyond the current PDU is a bug even inside the fixed-capacity object. */
#if defined(__has_feature)
# if __has_feature(address_sanitizer)
#  define CLASSIC_ASAN 1
# endif
#endif
#if defined(__SANITIZE_ADDRESS__)
# define CLASSIC_ASAN 1
#endif
#ifdef CLASSIC_ASAN
extern void __asan_poison_memory_region(const volatile void *,size_t);
extern void __asan_unpoison_memory_region(const volatile void *,size_t);
#endif
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"check %u line %u: %s\n",checks,__LINE__,#x); exit(1); } } while (0)
static struct a138_classic_service s;
static uint8_t response[700];
static void le(uint8_t *p,unsigned n) { p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8); }
static void be(uint8_t *p,unsigned n) { p[0]=(uint8_t)(n>>8); p[1]=(uint8_t)n; }
static unsigned little(const uint8_t *p) { return p[0]+256u*p[1]; }
static unsigned big(const uint8_t *p) { return 256u*p[0]+p[1]; }
static void reset(void) {
    a138_classic_init(&s); CHECK(a138_classic_begin(&s,1,9,0x23,276)==A138_CLASSIC_OK);
}
static enum a138_classic_result pdu(unsigned cid,const uint8_t *p,unsigned n,unsigned fragment) {
    uint8_t data[680],acl[280]; unsigned off=0,total=n+4;
    enum a138_classic_result r=A138_CLASSIC_OK;
    le(data,n); le(data+2,cid); memcpy(data+4,p,n);
    if (!fragment || fragment>276) fragment=276;
    while (off<total) {
        unsigned chunk=total-off; if (chunk>fragment) chunk=fragment;
        le(acl,0x23|(off ? 0x1000 : 0x2000)); le(acl+2,chunk); memcpy(acl+4,data+off,chunk);
        #ifdef CLASSIC_ASAN
        __asan_poison_memory_region(s.rx+total,sizeof s.rx-total);
#endif
        r=a138_classic_acl(&s,1,9,acl,(uint16_t)(chunk+4));
#ifdef CLASSIC_ASAN
        __asan_unpoison_memory_region(s.rx,sizeof s.rx);
#endif
        if (r!=A138_CLASSIC_OK) return r;
        off+=chunk;
    }
    return r;
}
static unsigned drain(void) {
    struct a138_classic_tx tx={0},again={0}; unsigned n=0;
    while (a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK) {
        CHECK(tx.bytes<=s.tx_payload_limit+4u && tx.bytes>=5 && tx.link_epoch==1 && tx.generation==9);
        CHECK(a138_classic_tx_peek(&s,&again)==A138_CLASSIC_OK);
        CHECK(!memcmp(&tx,&again,sizeof tx));
        CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_REJECTED)==A138_CLASSIC_OK);
        CHECK(a138_classic_tx_peek(&s,&again)==A138_CLASSIC_OK && !memcmp(&tx,&again,sizeof tx));
        CHECK(little(tx.data)==(0x23u|(n ? 0x1000u : 0x2000u)));
        CHECK(little(tx.data+2)==tx.bytes-4u && n+tx.bytes-4u<=sizeof response);
        memcpy(response+n,tx.data+4,tx.bytes-4u); n+=tx.bytes-4u;
        CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_OK);
        CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_STALE);
    }
    if (n) CHECK(little(response)==n-4u);
    return n;
}
static void channel(unsigned idx,unsigned remote,unsigned mtu) {
    uint8_t b[16]; unsigned local=0x40+idx,id;
    b[0]=2; b[1]=50; le(b+2,4); le(b+4,idx ? 25 : 1); le(b+6,remote);
    CHECK(pdu(1,b,8,0)==A138_CLASSIC_OK); CHECK(drain()==28);
    CHECK(response[4]==3 && response[5]==50 && little(response+8)==local && little(response+10)==remote);
    CHECK(response[16]==4 && little(response+20)==remote && little(response+26)==672);
    id=response[17];
    b[0]=4; b[1]=51; le(b+2,8); le(b+4,local); le(b+6,0); b[8]=1; b[9]=2; le(b+10,mtu);
    CHECK(pdu(1,b,12,7)==A138_CLASSIC_OK); CHECK(drain()==14);
    CHECK(response[4]==5 && little(response+8)==remote && little(response+12)==0);
    b[0]=5; b[1]=(uint8_t)id; le(b+2,6); le(b+4,local); le(b+6,0); le(b+8,0);
    CHECK(pdu(1,b,10,0)==A138_CLASSIC_OK); CHECK(drain()==0);
    CHECK(s.channel[idx].local_config && s.channel[idx].remote_config && s.channel[idx].peer_mtu==mtu);
}
static unsigned command(unsigned signal,const uint8_t *p,unsigned n) {
    uint8_t b[140]; b[0]=0x10; b[1]=(uint8_t)signal; memcpy(b+2,p,n);
    CHECK(pdu(0x41,b,n+2,0)==A138_CLASSIC_OK); return drain();
}
static void configured(void) {
    static const uint8_t config[]={4,8,1,0,7,6,0,0,0x21,0x15,2,53};
    uint8_t sep=4,b[14]; channel(1,0x70,672);
    CHECK(command(1,&sep,0)==8 && response[4]==0x12 && response[5]==1 && response[6]==4 && response[7]==8);
    CHECK(command(2,&sep,1)==16 && response[12]==0x3f && response[13]==0xff && response[15]==53);
    b[0]=0x20; b[1]=3; memcpy(b+2,config,sizeof config);
    CHECK(pdu(0x41,b,sizeof b,0)==A138_CLASSIC_OK);
    CHECK(s.state==A138_CLASSIC_IDLE && s.pending_config && !s.ready);
    CHECK(drain()==6 && response[4]==0x22 && response[5]==3);
    CHECK(s.state==A138_CLASSIC_CONFIGURED && s.format.rate_hz==44100 && s.format.mode==3 && s.format.blocks==16 && s.format.subbands==8);
    CHECK(command(4,&sep,1)==16 && !memcmp(response+12,config+8,4));
}
static void streaming(void) {
    uint8_t sep=4; configured();
    CHECK(command(6,&sep,1)==6 && s.state==A138_CLASSIC_OPEN);
    channel(2,0x71,672);
    CHECK(command(7,&sep,1)==8 && response[4]==0x13 && response[6]==4 && response[7]==0x31 && s.state==A138_CLASSIC_OPEN);
    CHECK(a138_classic_audio_ready(&s,1,9,48000,1)==A138_CLASSIC_ARGUMENT);
    CHECK(a138_classic_audio_ready(&s,1,9,44100,1)==A138_CLASSIC_OK);
    CHECK(command(7,&sep,1)==6 && response[4]==0x12 && s.state==A138_CLASSIC_STREAMING);
}
static unsigned make_frame(uint8_t *p) {
    /* 44.1 kHz, 16 blocks, joint stereo, loudness, 8 subbands, bitpool 35;
     * CRC/payload here test framing only. Real decoder vectors tested below. */
    memset(p,0,83); p[0]=0x9c; p[1]=0xbd; p[2]=35; return 83;
}
static unsigned rtp(uint8_t *p,unsigned seq,unsigned flags,const uint8_t *audio,unsigned n) {
    memset(p,0,13); p[0]=0x80; p[1]=96; be(p+2,seq); p[7]=20; p[11]=5; p[12]=(uint8_t)flags;
    memcpy(p+13,audio,n); return n+13;
}
static void test_media(void) {
    uint8_t f[224],b[672],sep=4; unsigned n,len,epoch; struct a138_classic_frame out;
    reset(); streaming(); len=make_frame(f); epoch=s.stream_epoch;
    n=rtp(b,65535,1,f,len); CHECK(pdu(0x42,b,n,17)==A138_CLASSIC_OK);
    CHECK(a138_classic_frame_pop(&s,&out)==A138_CLASSIC_OK && out.bytes==len && out.sequence==65535 && out.stream_epoch==epoch && !memcmp(out.data,f,len));
    CHECK(a138_classic_frame_pop(&s,&out)==A138_CLASSIC_EMPTY);
    n=rtp(b,0,1,f,len); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK);
    CHECK(a138_classic_frame_pop(&s,&out)==A138_CLASSIC_OK && out.stream_epoch==epoch);
    CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED && s.frame_count==0 && s.stream_epoch==epoch); /* duplicate */
    n=rtp(b,3,1,f,len); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK && s.sequence_gaps==1 && s.stream_epoch>epoch);
    epoch=s.stream_epoch; CHECK(a138_classic_frame_pop(&s,&out)==A138_CLASSIC_OK && out.stream_epoch==epoch);
    n=rtp(b,2,1,f,len); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED && !s.frame_count); /* reorder */
    n=rtp(b,4,2,f,len); memcpy(b+n,f,len); n+=len;
    CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK && s.frame_count==2);
    CHECK(a138_classic_frame_pop(&s,&out)==A138_CLASSIC_OK && out.timestamp==20);
    CHECK(a138_classic_frame_pop(&s,&out)==A138_CLASSIC_OK && out.timestamp==148);
    /* 3,2,1 fragmented SBC, equal nonfinal packet sizes and same timestamp. */
    n=rtp(b,5,0xc3,f,30); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK && !s.frame_count);
    n=rtp(b,6,0x82,f+30,30); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK && !s.frame_count);
    n=rtp(b,7,0xa1,f+60,len-60); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK);
    CHECK(a138_classic_frame_pop(&s,&out)==A138_CLASSIC_OK && out.sequence==5 && out.bytes==len && !memcmp(out.data,f,len));
    n=rtp(b,8,0xc3,f,30); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK);
    n=rtp(b,9,0xa1,f+30,len-30); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED && !s.frame_count && !s.fragment_active);
    n=rtp(b,10,1,f,len); b[12]|=0x10; CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED);
    n=rtp(b,11,1,f,len); b[1]=0x80|96; CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED); /* marker */
    n=rtp(b,11,1,f,len); b[0]|=0x10; CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED); /* extension */
    n=rtp(b,11,1,f,len); b[1]=95; CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED); /* static PT */
    /* Four frame bound: overflow clears all old frames, never blocks audio. */
    for (unsigned i=11;i<15;++i) { n=rtp(b,i,1,f,len); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK); }
    CHECK(s.frame_count==4); epoch=s.stream_epoch;
    n=rtp(b,15,1,f,len); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED && !s.frame_count && s.stream_epoch>epoch);
    n=rtp(b,16,1,f,len); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK);
    CHECK(command(9,&sep,1)==6 && s.state==A138_CLASSIC_OPEN && !s.frame_count);
    CHECK(command(7,&sep,1)==6 && s.state==A138_CLASSIC_STREAMING);
    CHECK(a138_classic_audio_ready(&s,1,9,44100,0)==A138_CLASSIC_OK && s.state==A138_CLASSIC_OPEN);
    CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_DROPPED && !s.frame_count);
}
static void test_sdp(void) {
    uint8_t req[64],joined[200],cont[7]; unsigned bytes=0,n,part=0; reset(); channel(0,0x60,48);
    /* Search Audio Sink; transaction 0x1234. */
    static const uint8_t search[]={2,0x12,0x34,0,8,0x35,3,0x19,0x11,0x0b,0,1,0};
    CHECK(pdu(0x40,search,sizeof search,0)==A138_CLASSIC_OK && drain()==18);
    CHECK(response[4]==3 && big(response+9)==1 && big(response+11)==1 && big(response+13)==1 && big(response+15)==1 && response[17]==0);
    /* ServiceSearchAttributeRequest with a maximum chunk of 17; vary TID on
     * every continuation, as real clients do. */
    static const uint8_t query[]={6,0,1,0,15,0x35,3,0x19,0x11,0x0b,0,17,0x35,5,0x0a,0,0,0xff,0xff,0};
    memcpy(req,query,sizeof query); n=sizeof query;
    do {
        CHECK(pdu(0x40,req,n,9)==A138_CLASSIC_OK); CHECK(drain()>12);
        CHECK(response[4]==7 && big(response+7)==little(response)-5);
        unsigned chunk=big(response+9); CHECK(chunk<=17 && bytes+chunk<=sizeof joined);
        memcpy(joined+bytes,response+11,chunk); bytes+=chunk;
        unsigned pos=11+chunk; CHECK(response[pos]==0 || response[pos]==6);
        if (!response[pos]) break;
        memcpy(cont,response+pos,7); memcpy(req,query,sizeof query);
        req[2]=(uint8_t)(++part+1); memcpy(req+19,cont,7); n=26; be(req+3,n-5);
        CHECK(part<20);
    } while (1);
    CHECK(bytes>90 && joined[0]==0x35 && joined[1]==bytes-2 && joined[2]==0x35 && joined[3]==bytes-4);
    /* Every returned attribute is encoded once, in order; record has protocol
     * PSM0x19 and AVDTP1.3, profile A2DP1.4, and the Audio Sink service class. */
    static const uint8_t prefix[]={0x35,0,0x35,0,0x09,0,0,0x0a,0,1,0,1,0x09,0,1,0x35,3,0x19,0x11,0x0b};
    CHECK(!memcmp(joined+4,prefix+4,sizeof prefix-4));
    req[25]^=1; CHECK(pdu(0x40,req,n,0)==A138_CLASSIC_OK && drain()==11 && response[4]==1 && big(response+9)==5);
    /* Unsupported search UUID produces an empty list. */
    memcpy(req,query,sizeof query); req[9]=0x0a;
    CHECK(pdu(0x40,req,sizeof query,0)==A138_CLASSIC_OK && drain()==14 && response[11]==0x35 && response[12]==0);
    /* ServiceAttributeRequest of exactly ServiceClassIDList, no outer record list. */
    static const uint8_t attr[]={4,0,8,0,12,0,1,0,1,0,40,0x35,3,0x09,0,1,0};
    CHECK(pdu(0x40,attr,sizeof attr,0)==A138_CLASSIC_OK && drain()==22);
    CHECK(response[4]==5 && response[11]==0x35 && response[12]==8 && response[13]==0x09 && response[17]==3);
}
static void test_lifecycle(void) {
    struct a138_classic_tx tx; uint8_t b[64],acl[280],sep=4; unsigned epoch;
    reset(); channel(1,0x70,672);
    b[0]=0x10; b[1]=1; CHECK(pdu(0x41,b,2,0)==A138_CLASSIC_OK);
    CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK); epoch=s.stream_epoch;
    CHECK(a138_classic_tx_result(&s,1,8,tx.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_STALE);
    CHECK(a138_classic_tx_result(&s,1,9,tx.token,(enum a138_classic_submission)-1)==A138_CLASSIC_ARGUMENT);
    CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_UNCERTAIN)==A138_CLASSIC_FENCED);
    CHECK(s.stream_epoch>epoch && !s.tx_bytes && !s.frame_count);
    CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_FENCED);
    CHECK(a138_classic_begin(&s,1,10,0x23,276)==A138_CLASSIC_STALE);
    CHECK(a138_classic_begin(&s,2,10,0x23,276)==A138_CLASSIC_OK && !s.fenced);
    le(acl,0x2023); le(acl+2,4); le(acl+4,0); le(acl+6,1);
    CHECK(a138_classic_acl(&s,1,9,acl,8)==A138_CLASSIC_STALE);
    CHECK(a138_classic_cancel(&s,2,10)==A138_CLASSIC_OK && !s.active);
    reset(); streaming();
    static const uint8_t wrong[]={5,4,0,0x24,0,0x13},disconnect[]={5,4,0,0x23,0,0x13};
    CHECK(a138_classic_event(&s,1,9,wrong,sizeof wrong)==A138_CLASSIC_OK && s.active);
    CHECK(a138_classic_event(&s,1,9,disconnect,sizeof disconnect)==A138_CLASSIC_OK && !s.active && !s.frame_count);
    CHECK(a138_classic_frame_pop(&s,(struct a138_classic_frame *)b)==A138_CLASSIC_INACTIVE);
    reset(); configured(); CHECK(command(6,&sep,1)==6); channel(2,0x71,672);
    CHECK(a138_classic_audio_ready(&s,1,9,44100,1)==A138_CLASSIC_OK);
    b[0]=0x10; b[1]=7; b[2]=4; CHECK(pdu(0x41,b,3,0)==A138_CLASSIC_OK && s.state==A138_CLASSIC_OPEN);
    CHECK(a138_classic_audio_ready(&s,1,9,44100,0)==A138_CLASSIC_FENCED);
}
static void test_tx_limits(void) {
    uint8_t saved[200]; unsigned bytes;
    static const uint8_t query[]={6,0,1,0,15,0x35,3,0x19,0x11,0x0b,2,0xa0,0x35,5,0x0a,0,0,0xff,0xff,0};
    reset(); channel(0,0x60,672);
    CHECK(pdu(0x40,query,sizeof query,0)==A138_CLASSIC_OK); bytes=drain(); CHECK(bytes>100 && bytes<sizeof saved);
    memcpy(saved,response,bytes);
    a138_classic_init(&s); CHECK(a138_classic_begin(&s,1,9,0x23,27)==A138_CLASSIC_OK);
    channel(0,0x60,672);
    CHECK(pdu(0x40,query,sizeof query,0)==A138_CLASSIC_OK);
    CHECK(drain()==bytes && !memcmp(saved,response,bytes));
    a138_classic_init(&s); CHECK(a138_classic_begin(&s,1,9,0x23,3)==A138_CLASSIC_ARGUMENT);
    CHECK(a138_classic_begin(&s,1,9,0x23,277)==A138_CLASSIC_ARGUMENT);
}
static void test_sdp_lengths(void) {
    static const uint32_t sizes[]={0,1,672,673,65535,65536,0xfffffffbu,0xfffffffcu,0xfffffffdu,0xfffffffeu,0xffffffffu};
    uint8_t req[32];
    reset(); channel(0,0x60,672);
    for (unsigned i=0;i<sizeof sizes/sizeof sizes[0];++i) {
        for (unsigned where=0;where<2;++where) {
            memset(req,0,sizeof req); req[0]=6; req[2]=1;
            unsigned pos=5;
            if (where) { req[pos++]=0x35; req[pos++]=3; req[pos++]=0x19; req[pos++]=0x11; req[pos++]=0x0b; req[pos++]=0; req[pos++]=40; }
            req[pos++]=0x37;
            req[pos++]=(uint8_t)(sizes[i]>>24); req[pos++]=(uint8_t)(sizes[i]>>16);
            req[pos++]=(uint8_t)(sizes[i]>>8); req[pos++]=(uint8_t)sizes[i];
            /* Deliberately truncated sequence: this is an actual received PDU. */
            be(req+3,pos-5);
            CHECK(pdu(0x40,req,pos,0)==A138_CLASSIC_OK && drain()==11 && response[4]==1 && big(response+9)==3);
        }
    }
}
static void test_config_response_options(void) {
    uint8_t b[20]; unsigned id;
    for (unsigned variant=0;variant<4;++variant) {
        reset(); static const uint8_t conn[]={2,1,4,0,1,0,0x60,0};
        CHECK(pdu(1,conn,sizeof conn,0)==A138_CLASSIC_OK && drain()==28); id=s.channel[0].config_id;
        memset(b,0,sizeof b); b[0]=5; b[1]=(uint8_t)id; le(b+2,10); le(b+4,0x40);
        b[10]=1; b[11]=2; le(b+12,variant==1 ? 335 : 672);
        if (variant==2) b[11]=3; /* Truncated option envelope fences. */
        if (variant==3) b[10]=4; /* Unoffered mandatory flow-control option. */
        enum a138_classic_result r=pdu(1,b,14,0);
        if (variant==2) CHECK(r==A138_CLASSIC_FENCED && !s.channel[0].local_config);
        else if (variant) CHECK(r==A138_CLASSIC_OK && !s.channel[0].allocated);
        else CHECK(r==A138_CLASSIC_OK && s.channel[0].local_config);
    }
}
static void test_protocol_fuzz(void) {
    uint8_t b[160]; unsigned rng=0xc1a551c;
    for (unsigned protocol=0;protocol<2;++protocol) {
        reset(); channel(protocol,protocol ? 0x70 : 0x60,672);
        for (unsigned t=0;t<2000;++t) {
            unsigned n=protocol ? 2+t%127 : 5+t%124;
            for (unsigned j=0;j<n;++j) { rng=rng*1664525u+1013904223u; b[j]=(uint8_t)(rng>>24); }
            if (protocol) { b[0]&=0xfcu; b[1]=(uint8_t)(1+t%13); }
            else { b[0]=(uint8_t)(t%3==0 ? 2 : t%3==1 ? 4 : 6); be(b+3,n-5); }
            enum a138_classic_result r=pdu(protocol ? 0x41 : 0x40,b,n,23+t%41);
            CHECK(r==A138_CLASSIC_OK || r==A138_CLASSIC_MALFORMED);
            (void)drain();
            CHECK(!s.fenced && s.rx_bytes<=sizeof s.rx && s.tx_bytes<=sizeof s.tx && s.frame_count<=4);
        }
    }
}
static void test_epoch_exhaustion(void) {
    uint8_t b[128],f[224]; struct a138_classic_frame frame;
    reset(); streaming(); unsigned len=make_frame(f),n=rtp(b,0,1,f,len);
    CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_OK);
    s.stream_epoch=UINT32_MAX;
    n=rtp(b,2,1,f,len); CHECK(pdu(0x42,b,n,0)==A138_CLASSIC_FENCED && !s.frame_count);
    CHECK(a138_classic_frame_pop(&s,&frame)==A138_CLASSIC_FENCED);
}
static void test_boundaries(void) {
    uint8_t b[672],acl[280]; struct a138_classic_tx tx; unsigned n;
    /* Every ACL split position across the same real connection request. */
    for (unsigned cut=4;cut<13;++cut) {
        reset(); static const uint8_t conn[]={2,1,4,0,1,0,0x60,0};
        CHECK(pdu(1,conn,sizeof conn,cut)==A138_CLASSIC_OK && drain()==28 && s.channel[0].allocated);
    }
    reset(); le(acl,0x1023); le(acl+2,1); acl[4]=0;
    CHECK(a138_classic_acl(&s,1,9,acl,5)==A138_CLASSIC_MALFORMED && !s.rx_bytes);
    le(acl,0x2023); le(acl+2,4); le(acl+4,673); le(acl+6,0x40);
    CHECK(a138_classic_acl(&s,1,9,acl,8)==A138_CLASSIC_MALFORMED && !s.rx_bytes);
    le(acl+4,672); CHECK(a138_classic_acl(&s,1,9,acl,8)==A138_CLASSIC_OK && s.rx_bytes==4);
    CHECK(a138_classic_acl(&s,1,9,acl,8)==A138_CLASSIC_MALFORMED && !s.rx_bytes); /* new start while incomplete */
    /* Complete second PDU retained while response awaits acceptance. Third PDU
     * is BUSY, consumes no bytes, and cannot overwrite the second. */
    static const uint8_t info[]={10,4,2,0,2,0};
    CHECK(pdu(1,info,sizeof info,0)==A138_CLASSIC_OK);
    CHECK(pdu(1,info,sizeof info,0)==A138_CLASSIC_OK && s.rx_complete);
    CHECK(pdu(1,info,sizeof info,0)==A138_CLASSIC_BUSY && s.rx_complete);
    CHECK(a138_classic_tx_peek(&s,&tx)==A138_CLASSIC_OK);
    CHECK(a138_classic_tx_result(&s,1,9,tx.token,A138_CLASSIC_ACCEPTED)==A138_CLASSIC_OK && !s.rx_complete && s.tx_bytes);
    CHECK(drain()==16);
    /* Two signaling commands in one PDU, exact bytes and independent IDs. */
    reset(); memcpy(b,info,6); memcpy(b+6,info,6); b[7]=5;
    CHECK(pdu(1,b,12,0)==A138_CLASSIC_OK && drain()==28 && response[5]==4 && response[17]==5);
    reset(); channel(0,0x60,672);
    static const uint8_t alias[]={2,10,4,0,25,0,0x60,0};
    CHECK(pdu(1,alias,sizeof alias,0)==A138_CLASSIC_OK && drain()==16 && little(response+12)==7 && !s.channel[1].allocated);
    static const uint8_t duplicate[]={2,50,4,0,1,0,0x60,0};
    CHECK(pdu(1,duplicate,sizeof duplicate,0)==A138_CLASSIC_OK && drain()==16 && little(response+12)==0);
    memcpy(b,duplicate,sizeof duplicate); b[1]=51;
    CHECK(pdu(1,b,sizeof duplicate,0)==A138_CLASSIC_OK && drain()==16 && little(response+12)==7);
    /* AVDTP fragmented SET_CONFIGURATION, stable label, packet count2. */
    reset(); channel(1,0x70,672);
    static const uint8_t start[]={0x14,2,3,4,8,1,0},end[]={0x1c,7,6,0,0,0x21,0x15,2,53};
    CHECK(pdu(0x41,start,sizeof start,0)==A138_CLASSIC_OK && !s.tx_bytes);
    CHECK(pdu(0x41,end,sizeof end,0)==A138_CLASSIC_OK && drain()==6 && s.state==A138_CLASSIC_CONFIGURED);
    reset(); channel(1,0x70,672);
    CHECK(pdu(0x41,start,sizeof start,0)==A138_CLASSIC_OK);
    b[0]=0x2c; memcpy(b+1,end+1,sizeof end-1);
    CHECK(pdu(0x41,b,sizeof end,0)==A138_CLASSIC_MALFORMED && s.state==A138_CLASSIC_IDLE);
    /* Arbitrary ACL bytes/lengths, deterministic bounded execution. */
    unsigned rng=0x1234567;
    for (unsigned t=0;t<5000;++t) {
        reset(); n=4+t%277;
        for (unsigned j=0;j<n;++j) { rng=rng*1664525u+1013904223u; acl[j]=(uint8_t)(rng>>24); }
        le(acl,0x23|((t%4)<<12)); le(acl+2,n-4);
        (void)a138_classic_acl(&s,1,9,acl,(uint16_t)n);
        CHECK(s.rx_bytes<=sizeof s.rx && s.tx_bytes<=sizeof s.tx && s.frame_count<=4);
    }
}
int main(void) {
    test_media(); test_sdp(); test_lifecycle(); test_tx_limits(); test_sdp_lengths(); test_config_response_options(); test_protocol_fuzz(); test_epoch_exhaustion(); test_boundaries();
    printf("classic source-stage: %u checks passed; object=%zu frame=%zu tx=%zu\n",checks,sizeof s,sizeof(struct a138_classic_frame),sizeof(struct a138_classic_tx));
    return 0;
}
