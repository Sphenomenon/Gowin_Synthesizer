/* Bounded BR/EDR Basic-mode sink source-stage. See CLASSIC_SOURCE_STAGE.md.
 * Wire constants checked against Bluetooth Core 6.0 / A2DP 1.4 and the
 * Apache-2.0 Zephyr host headers listed in the provenance document. No upstream
 * implementation or HCI transport/credit engine is embedded here.
 */
#include "classic_service.h"
#include <string.h>
#define NO_STATE 255u
#define SDP_CID 0x40u
#define SIGNAL_CID 0x41u
#define MEDIA_CID 0x42u
#define SIGNALING 1u
#define SEP 4u /* SEID 1 encoded in bits 7:2. */

static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0] | (uint16_t)p[1] << 8); }
static uint16_t be16(const uint8_t *p) { return (uint16_t)((uint16_t)p[0] << 8 | p[1]); }
static uint32_t be32(const uint8_t *p) { return (uint32_t)be16(p) << 16 | be16(p+2); }
static void putle(uint8_t *p, uint16_t n) { p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8); }
static void putbe(uint8_t *p, uint16_t n) { p[0]=(uint8_t)(n>>8); p[1]=(uint8_t)n; }
static void put32(uint8_t *p, uint32_t n) { putbe(p,(uint16_t)(n>>16)); putbe(p+2,(uint16_t)n); }
static void silence(struct a138_classic_service *s) {
    s->frame_head=0; s->frame_count=0; s->fragment_active=0;
    s->sequence_valid=0; s->ssrc_valid=0;
    if (s->stream_epoch == UINT32_MAX) s->fenced=1;
    else ++s->stream_epoch;
}
static enum a138_classic_result fence(struct a138_classic_service *s) {
    silence(s); s->fenced=1; s->tx_bytes=0; s->rx_bytes=0;
    s->rx_complete=0; s->offered=0; s->avdtp_active=0;
    s->delay_selected=0; s->delay_phase=A138_CLASSIC_DELAY_NONE; s->tx_is_delay=0;
    return A138_CLASSIC_FENCED;
}
static enum a138_classic_result identity(struct a138_classic_service *s, uint32_t e, uint32_t g) {
    if (!s) return A138_CLASSIC_ARGUMENT;
    if (e!=s->link_epoch || g!=s->generation) return A138_CLASSIC_STALE;
    if (!s->active) return A138_CLASSIC_INACTIVE;
    if (s->fenced) return A138_CLASSIC_FENCED;
    return A138_CLASSIC_OK;
}
void a138_classic_init(struct a138_classic_service *s) { if (s) memset(s,0,sizeof *s); }
enum a138_classic_result a138_classic_begin(struct a138_classic_service *s,
        uint32_t e, uint32_t g, uint16_t h, uint16_t limit) {
    uint32_t stream, token;
    if (!s || !e || !g || h>0x0effu || limit<4u || limit>276u) return A138_CLASSIC_ARGUMENT;
    if (e<=s->link_epoch) return A138_CLASSIC_STALE;
    stream=s->stream_epoch; token=s->next_token;
    memset(s,0,sizeof *s); s->stream_epoch=stream; s->next_token=token;
    s->link_epoch=e; s->generation=g; s->handle=h; s->active=1; s->tx_payload_limit=limit;
    s->next_id=1; s->pending_state=NO_STATE; silence(s);
    return s->fenced ? A138_CLASSIC_FENCED : A138_CLASSIC_OK;
}
enum a138_classic_result a138_classic_cancel(struct a138_classic_service *s,uint32_t e,uint32_t g) {
    enum a138_classic_result r=identity(s,e,g);
    if (r!=A138_CLASSIC_OK && r!=A138_CLASSIC_FENCED) return r;
    silence(s); s->active=0; s->rx_bytes=0; s->rx_complete=0;
    s->tx_bytes=0; s->offered=0; s->avdtp_active=0; s->ready=0;
    s->delay_selected=0; s->delay_phase=A138_CLASSIC_DELAY_NONE; s->tx_is_delay=0;
    return A138_CLASSIC_OK;
}
enum a138_classic_result a138_classic_security(struct a138_classic_service *s,uint32_t e,uint32_t g,uint8_t secure) {
    enum a138_classic_result r=identity(s,e,g);
    if(r!=A138_CLASSIC_OK&&!(r==A138_CLASSIC_FENCED&&!secure))return r;
    if(secure>1u)return A138_CLASSIC_ARGUMENT;
    if(!secure&&s->security_ready){
        silence(s);memset(&s->channel[1],0,2u*sizeof s->channel[0]);
        s->ready=0;s->state=A138_CLASSIC_IDLE;s->pending_state=NO_STATE;
        s->tx_bytes=0;s->offered=0;s->rx_complete=0;s->rx_bytes=0;s->avdtp_active=0;
        s->delay_selected=0;s->delay_phase=A138_CLASSIC_DELAY_NONE;s->tx_is_delay=0;
    }
    s->security_ready=secure;return s->fenced?A138_CLASSIC_FENCED:A138_CLASSIC_OK;
}
enum a138_classic_result a138_classic_event(struct a138_classic_service *s,
        uint32_t e,uint32_t g,const uint8_t *p,uint16_t n) {
    enum a138_classic_result r=identity(s,e,g);
    if (r!=A138_CLASSIC_OK) return r;
    if (!p || n<2u || (uint16_t)(p[1]+2u)!=n) return A138_CLASSIC_MALFORMED;
    if (p[0]==5u) {
        if (n!=6u) return A138_CLASSIC_MALFORMED;
        if (p[2]==0u && le16(p+3)==s->handle) return a138_classic_cancel(s,e,g);
    }
    return A138_CLASSIC_OK;
}
static int start_tx(struct a138_classic_service *s,uint16_t cid) {
    if (s->tx_bytes) return 0;
    s->tx_is_delay=0;
    s->tx_bytes=4; s->tx_offset=0; putle(s->tx+2,cid); return 1;
}
static int append(struct a138_classic_service *s,const uint8_t *p,uint16_t n) {
    if ((uint32_t)s->tx_bytes+n>sizeof s->tx) { fence(s); return 0; }
    memcpy(s->tx+s->tx_bytes,p,n); s->tx_bytes=(uint16_t)(s->tx_bytes+n);
    putle(s->tx,(uint16_t)(s->tx_bytes-4u)); return 1;
}
static int sig(struct a138_classic_service *s,uint8_t code,uint8_t id,const uint8_t *p,uint16_t n) {
    uint8_t h[4];
    if ((uint32_t)s->tx_bytes+n+4u>52u) { fence(s); return 0; }
    h[0]=code; h[1]=id; putle(h+2,n);
    return append(s,h,4) && append(s,p,n);
}
static uint8_t next_id(struct a138_classic_service *s) {
    uint8_t id=s->next_id++; if (!s->next_id) s->next_id=1; return id;
}
static int channel_index(uint16_t cid) { return cid>=SDP_CID && cid<=MEDIA_CID ? (int)(cid-SDP_CID) : -1; }
static int channel_open(const struct a138_classic_service *s,unsigned i) {
    const struct a138_classic_channel *c=&s->channel[i];
    return c->allocated && c->local_config && c->remote_config;
}
static void drop_channel(struct a138_classic_service *s,unsigned i) {
    memset(&s->channel[i],0,sizeof s->channel[i]);
    if (i) { silence(s); s->ready=0; s->avdtp_active=0; }
    if (i==1u) {
        s->state=A138_CLASSIC_IDLE; memset(&s->channel[2],0,sizeof s->channel[2]);
        s->delay_selected=0; s->delay_phase=A138_CLASSIC_DELAY_NONE; s->remote_seid=0;
    }
    if (i==2u && s->state>A138_CLASSIC_CONFIGURED) s->state=A138_CLASSIC_CONFIGURED;
}
static enum a138_classic_result delay_fail(struct a138_classic_service *s,uint8_t reason) {
    s->delay_failure=reason; return fence(s);
}
static enum a138_classic_result delay_schedule(struct a138_classic_service *s) {
    uint8_t p[5];
    if (!s->delay_selected || s->delay_phase!=A138_CLASSIC_DELAY_QUEUED || s->tx_bytes)
        return A138_CLASSIC_OK;
    if (s->delay_labels_used>=16u) return delay_fail(s,A138_CLASSIC_DELAY_LABEL_EXHAUSTED);
    s->delay_label=(uint8_t)(s->delay_labels_used++<<4);
    p[0]=s->delay_label; p[1]=13; p[2]=s->remote_seid; putbe(p+3,s->delay_value);
    if (!start_tx(s,s->channel[1].remote_cid) || !append(s,p,sizeof p)) return fence(s);
    s->tx_is_delay=1; s->delay_phase=A138_CLASSIC_DELAY_TX; s->delay_started_ms=s->clock_ms;
    return A138_CLASSIC_OK;
}
static enum a138_classic_result signaling(struct a138_classic_service *s,const uint8_t *p,uint16_t n) {
    uint16_t off=0;
    /* Validate the entire command envelope before applying any command. */
    while (off<n) {
        uint16_t len;
        if (n-off<4 || !p[off+1]) return A138_CLASSIC_MALFORMED;
        len=le16(p+off+2);
        if ((uint32_t)off+4u+len>n) return A138_CLASSIC_MALFORMED;
        off=(uint16_t)(off+4u+len);
    }
    start_tx(s,SIGNALING); off=0;
    while (off<n && !s->fenced) {
        uint8_t code=p[off],id=p[off+1],out[80];
        uint16_t len=le16(p+off+2); const uint8_t *v=p+off+4;
        int i;
        switch (code) {
        case 2: { /* Connection Request; both SDP and AVDTP are Basic mode. */
            uint16_t psm,scid,result=0; struct a138_classic_channel *c=0;
            if (len!=4u) goto malformed;
            psm=le16(v); scid=le16(v+2); i=-1;
            if (psm==1u) i=0;
            else if (psm==25u) {
                i=s->channel[1].allocated ? 2 : 1;
                if(!s->security_ready){result=3;s->security_violation=1;}
            }
            else result=2; /* PSM not supported. */
            if (scid<0x40u) result=6; /* Invalid source CID. */
            if (!result) {
                unsigned j;
                for (j=0;j<3u;++j) if (s->channel[j].allocated && s->channel[j].remote_cid==scid) {
                    /* A retransmitted request for its existing PSM is
                     * idempotent; cross-PSM CID aliasing is never accepted. */
                    if ((psm==1u)!=(j==0u) || s->channel[j].connection_id!=id) result=7;
                    i=(int)j; break;
                }
                c=&s->channel[i];
                if ((!c->allocated && i==2 && s->state!=A138_CLASSIC_OPEN) ||
                    (c->allocated && c->remote_cid!=scid)) result=4;
            }
            putle(out,result ? 0u : (uint16_t)(SDP_CID+i)); putle(out+2,scid);
            putle(out+4,result); putle(out+6,0); sig(s,3,id,out,8);
            if (!result && !c->allocated) {
                c->allocated=1; c->remote_cid=scid; c->peer_mtu=672; c->connection_id=id;
                c->config_id=next_id(s);
                putle(out,scid); putle(out+2,0); out[4]=1; out[5]=2;
                putle(out+6,A138_CLASSIC_MTU); sig(s,4,c->config_id,out,8);
            }
            break;
        }
        case 4: { /* Configuration Request: MTU is peer's receive capability. */
            uint16_t pos=4,peer_mtu=672,result=0,outbytes=6; uint8_t seen_mtu=0;
            if (len<4u) goto malformed;
            i=channel_index(le16(v));
            if (i<0 || !s->channel[i].allocated) goto invalid_cid;
            if (le16(v+2)!=0u) { result=2; } /* Continuation not supported in this bounded stage. */
            while (pos<len) {
                uint8_t kind,sz;
                if (len-pos<2) goto malformed;
                kind=v[pos]; sz=v[pos+1];
                if ((uint32_t)pos+2u+sz>len) goto malformed;
                if ((kind&0x7fu)==1u) {
                    if (sz!=2u || seen_mtu++) goto malformed;
                    peer_mtu=le16(v+pos+2);
                    if (peer_mtu<48u) result=1;
                } else if ((kind&0x7fu)==2u) {
                    if (sz!=2u) goto malformed; /* Flush timeout is accepted. */
                } else if (!(kind&0x80u)) {
                    result=3;
                    if (outbytes+2u+sz>sizeof out) goto malformed;
                    memcpy(out+outbytes,v+pos,2u+sz); outbytes=(uint16_t)(outbytes+2u+sz);
                }
                pos=(uint16_t)(pos+2u+sz);
            }
            putle(out,s->channel[i].remote_cid); putle(out+2,0); putle(out+4,result);
            if (result==1u) { out[6]=1; out[7]=2; putle(out+8,672); outbytes=10; }
            if (!result) { s->channel[i].peer_mtu=peer_mtu; s->channel[i].remote_config=1; }
            sig(s,5,id,out,outbytes); break;
        }
        case 5: { /* Configuration Response to our request. */
            uint16_t pos=6; uint8_t supported=1;
            if (len<6u) goto malformed;
            i=channel_index(le16(v));
            if (i<0 || !s->channel[i].allocated || id!=s->channel[i].config_id) goto malformed;
            while (pos<len) {
                uint8_t kind,sz;
                if (len-pos<2) goto malformed;
                kind=v[pos]; sz=v[pos+1];
                if ((uint32_t)pos+2u+sz>len) goto malformed;
                if ((kind&0x7fu)==1u) {
                    if (sz!=2u) goto malformed;
                    if (le16(v+pos+2)!=A138_CLASSIC_MTU) supported=0;
                } else if (!(kind&0x80u)) supported=0;
                pos=(uint16_t)(pos+2u+sz);
            }
            if (le16(v+2)!=0u || le16(v+4)!=0u || !supported) { drop_channel(s,(unsigned)i); break; }
            s->channel[i].local_config=1; break;
        }
        case 6:
            if (len!=4u) goto malformed;
            i=channel_index(le16(v));
            if (i<0 || !s->channel[i].allocated || le16(v+2)!=s->channel[i].remote_cid) goto invalid_cid;
            sig(s,7,id,v,4); drop_channel(s,(unsigned)i); break;
        case 8: /* Echo Request */
            sig(s,9,id,v,len); break;
        case 10: /* Information Request */
            if (len!=2u) goto malformed;
            memcpy(out,v,2); putle(out+2,0);
            if (le16(v)==2u) { memset(out+4,0,4); sig(s,11,id,out,8); }
            else if (le16(v)==3u) { memset(out+4,0,8); out[4]=2; sig(s,11,id,out,12); }
            else { putle(out+2,1); sig(s,11,id,out,4); }
            break;
        case 1: case 3: case 7: case 9: case 11: break; /* No locally initiated request of these types. */
        default: putle(out,0); sig(s,1,id,out,2); break;
        }
        off=(uint16_t)(off+4u+len); continue;
invalid_cid:
        putle(out,2); putle(out+2,len>=2u ? le16(v) : 0u); putle(out+4,len>=4u ? le16(v+2) : 0u);
        sig(s,1,id,out,6); off=(uint16_t)(off+4u+len); continue;
malformed:
        return fence(s); /* Partial control response must never escape. */
    }
    if (s->tx_bytes==4u) s->tx_bytes=0;
    return s->fenced ? A138_CLASSIC_FENCED : A138_CLASSIC_OK;
}

/* One Audio Sink SDP record, searched by every UUID it contains. */
struct sdp_attr { uint16_t id; uint8_t bytes; const uint8_t *data; };
static const uint8_t attr_handle[]={0x0a,0,1,0,1};
static const uint8_t attr_class[]={0x35,3,0x19,0x11,0x0b};
static const uint8_t attr_protocol[]={0x35,16,0x35,6,0x19,1,0,0x09,0,25,0x35,6,0x19,0,25,0x09,1,3};
static const uint8_t attr_browse[]={0x35,3,0x19,0x10,2};
static const uint8_t attr_profile[]={0x35,8,0x35,6,0x19,0x11,0x0d,0x09,1,4};
static const uint8_t attr_name[]={0x25,22,'1','3','8','K',' ','e','x','p','e','r','i','m','e','n','t','a','l',' ','s','i','n','k'};
static const uint8_t attr_features[]={0x09,0,1};
static const struct sdp_attr attributes[]={
    {0, sizeof attr_handle,attr_handle}, {1,sizeof attr_class,attr_class},
    {4,sizeof attr_protocol,attr_protocol}, {5,sizeof attr_browse,attr_browse},
    {9,sizeof attr_profile,attr_profile}, {0x100,sizeof attr_name,attr_name},
    {0x311,sizeof attr_features,attr_features}
};
/* Return sequence payload/length and exact consumed element size. */
static int sequence(const uint8_t *p,uint16_t n,const uint8_t **v,uint16_t *len,uint16_t *used) {
    uint32_t bytes; uint16_t h;
    if (!n) return 0;
    if (p[0]==0x35u && n>=2u) { bytes=p[1]; h=2; }
    else if (p[0]==0x36u && n>=3u) { bytes=be16(p+1); h=3; }
    else if (p[0]==0x37u && n>=5u) { bytes=be32(p+1); h=5; }
    else return 0;
    if (bytes>(uint32_t)n-h) return 0;
    *v=p+h; *len=(uint16_t)bytes; *used=(uint16_t)(bytes+h); return 1;
}
static int same_bytes(const uint8_t *a,const uint8_t *b,uint16_t n) {
    uint16_t i; for (i=0;i<n;++i) if (a[i]!=b[i]) return 0; return 1;
}
static int known_uuid(uint32_t u) { return u==0x110bu || u==0x110du || u==0x1002u || u==0x0100u || u==25u; }
static int search_pattern(const uint8_t *p,uint16_t n,uint16_t *used,int *match) {
    const uint8_t *v; uint16_t len,off=0; unsigned count=0;
    static const uint8_t base[]={0,0,0x10,0,0x80,0,0,0x80,0x5f,0x9b,0x34,0xfb};
    if (!sequence(p,n,&v,&len,used)) return 0;
    *match=1;
    while (off<len) {
        uint32_t u;
        if (v[off]==0x19u && len-off>=3) { u=be16(v+off+1); off=(uint16_t)(off+3); }
        else if (v[off]==0x1au && len-off>=5) { u=be32(v+off+1); off=(uint16_t)(off+5); }
        else if (v[off]==0x1cu && len-off>=17) {
            u=be32(v+off+1);
            if (!same_bytes(v+off+5,base,sizeof base)) *match=0;
            off=(uint16_t)(off+17);
        } else return 0;
        if (!known_uuid(u)) *match=0;
        if (++count>12u) return 0;
    }
    return count!=0u;
}
static int attr_selected(const uint8_t *p,uint16_t n,uint16_t id) {
    uint16_t off=0; int selected=0;
    while (off<n) {
        uint16_t low,high;
        if (p[off]==0x09u && n-off>=3) { low=high=be16(p+off+1); off=(uint16_t)(off+3); }
        else if (p[off]==0x0au && n-off>=5) { low=be16(p+off+1); high=be16(p+off+3); off=(uint16_t)(off+5); }
        else return -1;
        if (low>high) return -1;
        if (low<=id && id<=high) selected=1;
    }
    return n ? selected : -1;
}
static uint32_t query_hash(const uint8_t *p,uint16_t n) {
    uint32_t h=2166136261u; uint16_t i;
    for (i=0;i<n;++i) h=(h^p[i])*16777619u;
    return h;
}
static int continuation(const uint8_t *p,uint16_t n,uint32_t hash,uint16_t total,uint16_t *offset) {
    if (n==1u && p[0]==0u) { *offset=0; return 1; }
    if (n==7u && p[0]==6u && be32(p+3)==hash && be16(p+1)<total) {
        *offset=be16(p+1); return 1;
    }
    return 0;
}
static enum a138_classic_result sdp_error(struct a138_classic_service *s,const uint8_t *p,uint16_t error) {
    uint8_t out[7]={1,0,0,0,2,0,0};
    out[1]=p[1]; out[2]=p[2]; putbe(out+5,error);
    start_tx(s,s->channel[0].remote_cid); append(s,out,sizeof out); return A138_CLASSIC_OK;
}
static enum a138_classic_result sdp(struct a138_classic_service *s,const uint8_t *p,uint16_t n) {
    uint8_t record[192],out[210]; const uint8_t *v,*ids; uint16_t pos=5,used,idslen,maxbytes,total,offset,chunk,sz=0;
    uint32_t hash; unsigned i; int match=1,search;
    if (n<5u) return A138_CLASSIC_MALFORMED;
    if ((uint32_t)be16(p+3)+5u!=n) return sdp_error(s,p,4);
    if (p[0]==2u) { /* ServiceSearchRequest, at most one record. */
        if (!search_pattern(p+pos,(uint16_t)(n-pos),&used,&match)) return sdp_error(s,p,3);
        pos=(uint16_t)(pos+used);
        if (n-pos<3 || !be16(p+pos)) return sdp_error(s,p,3);
        pos=(uint16_t)(pos+2);
        if (n-pos!=1u || p[pos]) return sdp_error(s,p,5);
        out[0]=3; out[1]=p[1]; out[2]=p[2]; putbe(out+3,match ? 9u : 5u);
        putbe(out+5,match ? 1u : 0u); putbe(out+7,match ? 1u : 0u);
        if (match) { put32(out+9,0x10001u); out[13]=0; sz=14; }
        else { out[9]=0; sz=10; }
        start_tx(s,s->channel[0].remote_cid); append(s,out,sz); return A138_CLASSIC_OK;
    }
    search=p[0]==6u;
    if (search) {
        if (!search_pattern(p+pos,(uint16_t)(n-pos),&used,&match)) return sdp_error(s,p,3);
        pos=(uint16_t)(pos+used);
    } else if (p[0]==4u) {
        if (n-pos<4) return sdp_error(s,p,3);
        if (be32(p+pos)!=0x10001u) return sdp_error(s,p,2);
        pos=(uint16_t)(pos+4);
    } else return sdp_error(s,p,3);
    if (n-pos<2) return sdp_error(s,p,3);
    maxbytes=be16(p+pos); pos=(uint16_t)(pos+2);
    if (maxbytes<7u || !sequence(p+pos,(uint16_t)(n-pos),&ids,&idslen,&used)) return sdp_error(s,p,3);
    pos=(uint16_t)(pos+used);
    if (attr_selected(ids,idslen,0)<0) return sdp_error(s,p,3);
    sz=(uint16_t)(search ? 4u : 2u);
    if (match) for (i=0;i<sizeof attributes/sizeof attributes[0];++i) {
        const struct sdp_attr *a=&attributes[i];
        if (!attr_selected(ids,idslen,a->id)) continue;
        record[sz++]=0x09; putbe(record+sz,a->id); sz=(uint16_t)(sz+2);
        memcpy(record+sz,a->data,a->bytes); sz=(uint16_t)(sz+a->bytes);
    }
    if (search) {
        record[0]=0x35; record[1]=(uint8_t)(match ? sz-2u : 0u);
        if (match) { record[2]=0x35; record[3]=(uint8_t)(sz-4u); }
        else sz=2;
    } else { record[0]=0x35; record[1]=(uint8_t)(sz-2u); }
    total=sz; hash=query_hash(p+5,(uint16_t)(pos-5u))^p[0];
    if (!continuation(p+pos,(uint16_t)(n-pos),hash,total,&offset)) return sdp_error(s,p,5);
    chunk=(uint16_t)(total-offset);
    if (chunk>maxbytes) chunk=maxbytes;
    if (chunk>s->channel[0].peer_mtu-14u) chunk=(uint16_t)(s->channel[0].peer_mtu-14u);
    out[0]=(uint8_t)(search ? 7 : 5); out[1]=p[1]; out[2]=p[2]; putbe(out+5,chunk);
    memcpy(out+7,record+offset,chunk); sz=(uint16_t)(7u+chunk);
    if (offset+chunk<total) {
        out[sz++]=6; putbe(out+sz,(uint16_t)(offset+chunk)); sz=(uint16_t)(sz+2);
        put32(out+sz,hash); sz=(uint16_t)(sz+4);
    } else out[sz++]=0;
    putbe(out+3,(uint16_t)(sz-5)); start_tx(s,s->channel[0].remote_cid); append(s,out,sz);
    (void)v; return A138_CLASSIC_OK;
}

static int onebit(uint8_t v) { return v && !(v&(v-1u)); }
static int codec_format(const uint8_t *c,struct a138_classic_format *f) {
    uint8_t rate=c[0]&0xf0u,mode=c[0]&15u,blocks=c[1]&0xf0u,sub=c[1]&12u,alloc=c[1]&3u;
    if (!onebit(rate) || !(rate&0x30u) || !onebit(mode) || !onebit(blocks) || !onebit(sub) || !onebit(alloc) ||
        c[2]<2u || c[3]>53u || c[2]>c[3]) return 0;
    f->rate_hz=rate==0x20u ? 44100u : 48000u;
    f->mode=(uint8_t)(mode==8u ? 0u : mode==4u ? 1u : mode==2u ? 2u : 3u);
    f->blocks=(uint8_t)(blocks==0x80u ? 4u : blocks==0x40u ? 8u : blocks==0x20u ? 12u : 16u);
    f->subbands=(uint8_t)(sub==8u ? 4u : 8u); f->allocation=(uint8_t)(alloc==2u);
    f->min_bitpool=c[2]; f->max_bitpool=c[3]; return 1;
}
static int avdtp_reply(struct a138_classic_service *s,uint8_t label,uint8_t signal,uint8_t type,
        const uint8_t *p,uint16_t n) {
    uint8_t h[2]; h[0]=(uint8_t)(label|type); h[1]=signal;
    start_tx(s,s->channel[1].remote_cid); return append(s,h,2) && append(s,p,n);
}
static enum a138_classic_result avdtp_command(struct a138_classic_service *s,uint8_t label,
        uint8_t signal,const uint8_t *p,uint16_t n) {
    uint8_t out[16]={0},error=0,category=0; uint16_t bytes=0; uint8_t state=s->state;
    static const uint8_t caps[]={1,0,7,6,0,0,0x3f,0xff,2,53};
    switch (signal) {
    case 1: /* Discover one audio sink SEP. */
        if (n) { error=0x11; break; }
        out[0]=(uint8_t)(SEP|(state!=A138_CLASSIC_IDLE ? 2u : 0u)); out[1]=8; bytes=2; break;
    case 2: case 12: case 4:
        if (n!=1u) { error=0x11; break; }
        if (p[0]!=SEP) { error=0x12; break; }
        if (signal==4u && state==A138_CLASSIC_IDLE) { error=0x14; break; }
        memcpy(out,caps,sizeof caps); bytes=sizeof caps;
        if (signal==4u) memcpy(out+6,s->codec,4);
        /* DelayReporting is not a basic GetCapabilities service. */
        if (signal==12u || (signal==4u && s->delay_selected)) {
            out[bytes++]=8; out[bytes++]=0;
        }
        break;
    case 3: { /* SetConfiguration: transport, bounded SBC, optional peer delay. */
        uint16_t off=2; uint8_t seen=0; struct a138_classic_format format;
        if (n<2u) { error=0x11; break; }
        if (p[0]!=SEP || !p[1] || (p[1]&3u) || p[1]>0xf8u) { error=0x12; break; }
        if (state!=A138_CLASSIC_IDLE) { error=0x13; break; }
        while (off<n) {
            uint8_t cat,len;
            if (n-off<2) { error=0x11; break; }
            cat=p[off]; len=p[off+1]; category=cat;
            if ((uint32_t)off+2u+len>n) { error=0x11; break; }
            if (cat==1u) {
                if (len || (seen&1u)) { error=0x18; break; } seen|=1;
            } else if (cat==7u) {
                if (len!=6u || (seen&2u) || p[off+2] || p[off+3] || !codec_format(p+off+4,&format)) {
                    error=0x29; break;
                }
                memcpy(s->pending_codec,p+off+4,4); seen|=2;
            } else if (cat==8u) {
                if (len || (seen&4u)) { error=0x18; break; }
                if (!s->clock_valid || !s->delay_valid) { error=0x31; break; }
                seen|=4;
            } else { error=0x17; break; }
            off=(uint16_t)(off+2u+len);
        }
        if (!error && (seen&3u)!=3u) { category=(uint8_t)(seen&1u ? 7 : 1); error=0x1a; }
        if (!error) {
            s->pending_config=1; s->pending_state=A138_CLASSIC_CONFIGURED;
            s->pending_delay_selected=(seen&4u)!=0; s->pending_remote_seid=p[1];
        }
        break;
    }
    case 6: case 7: case 8: case 9: case 10:
        if (n!=1u) { error=0x11; break; }
        if (p[0]!=SEP) { error=0x12; break; }
        if (signal==6u && state==A138_CLASSIC_CONFIGURED && !s->channel[2].allocated &&
            (!s->delay_selected || s->delay_sent)) s->pending_state=A138_CLASSIC_OPEN;
        else if (signal==7u && state==A138_CLASSIC_OPEN && channel_open(s,2) && s->ready &&
                 (!s->delay_selected || s->delay_phase==A138_CLASSIC_DELAY_COMPLETE)) s->pending_state=A138_CLASSIC_STREAMING;
        else if (signal==9u && state==A138_CLASSIC_STREAMING) s->pending_state=A138_CLASSIC_OPEN;
        else if (signal==8u && (state==A138_CLASSIC_OPEN || state==A138_CLASSIC_STREAMING)) s->pending_state=A138_CLASSIC_IDLE;
        else if (signal==10u) s->pending_state=A138_CLASSIC_IDLE;
        else error=0x31;
        break;
    case 5: error=0x29; category=7; break; /* Reconfigure not offered. */
    case 11: case 13: error=0x19; break; /* SNK initiates DelayReport; no SRC role. */
    default: avdtp_reply(s,label,signal,1,out,0); return A138_CLASSIC_OK;
    }
    if (error) {
        bytes=0;
        if (signal==3u || signal==5u) out[bytes++]=category;
        else if (signal==7u || signal==9u) out[bytes++]=SEP;
        out[bytes++]=error; avdtp_reply(s,label,signal,3,out,bytes);
    } else avdtp_reply(s,label,signal,2,out,bytes);
    return s->fenced ? A138_CLASSIC_FENCED : A138_CLASSIC_OK;
}
static enum a138_classic_result avdtp_message(struct a138_classic_service *s,uint8_t label,
        uint8_t signal,uint8_t message_type,const uint8_t *p,uint16_t n) {
    if (!message_type) return avdtp_command(s,label,signal,p,n);
    if (s->delay_phase!=A138_CLASSIC_DELAY_WAIT || label!=s->delay_label)
        return A138_CLASSIC_MALFORMED;
    if (signal!=13u) return delay_fail(s,A138_CLASSIC_DELAY_BAD_RESPONSE);
    if (message_type==1u || message_type==3u) {
        if ((message_type==1u && n) || (message_type==3u && n!=1u))
            return delay_fail(s,A138_CLASSIC_DELAY_BAD_RESPONSE);
        return delay_fail(s,A138_CLASSIC_DELAY_REJECTED);
    }
    if (message_type!=2u || n) return delay_fail(s,A138_CLASSIC_DELAY_BAD_RESPONSE);
    s->delay_reported_value=s->delay_value; s->delay_phase=A138_CLASSIC_DELAY_COMPLETE;
    return A138_CLASSIC_OK;
}
static enum a138_classic_result avdtp(struct a138_classic_service *s,const uint8_t *p,uint16_t n) {
    uint8_t type,label,signal,message_type; uint16_t skip;
    if (!n) return A138_CLASSIC_MALFORMED;
    type=(p[0]>>2)&3u; label=p[0]&0xf0u;
    message_type=p[0]&3u;
    if (!type) {
        s->avdtp_active=0;
        if (n<2u || (p[1]&0xc0u)) return A138_CLASSIC_MALFORMED;
        return avdtp_message(s,label,p[1],message_type,p+2,(uint16_t)(n-2));
    }
    if (type==1u) {
        s->avdtp_active=0;
        if (n<3u || p[1]<2u || (p[2]&0xc0u)) return A138_CLASSIC_MALFORMED;
        s->avdtp_label=label; s->avdtp_signal=p[2]; s->avdtp_packets=p[1]; s->avdtp_seen=1;
        s->avdtp_message_type=message_type;
        s->avdtp_bytes=0; s->avdtp_active=1; skip=3;
    } else {
        if (!s->avdtp_active || s->avdtp_label!=label || s->avdtp_message_type!=message_type)
            return A138_CLASSIC_MALFORMED;
        ++s->avdtp_seen; skip=1;
        if ((type==3u)!=(s->avdtp_seen==s->avdtp_packets)) { s->avdtp_active=0; return A138_CLASSIC_MALFORMED; }
    }
    if ((uint32_t)s->avdtp_bytes+n-skip>sizeof s->avdtp) { s->avdtp_active=0; return A138_CLASSIC_MALFORMED; }
    memcpy(s->avdtp+s->avdtp_bytes,p+skip,n-skip); s->avdtp_bytes=(uint16_t)(s->avdtp_bytes+n-skip);
    if (type!=3u) return A138_CLASSIC_OK;
    signal=s->avdtp_signal; s->avdtp_active=0;
    return avdtp_message(s,label,signal,message_type,s->avdtp,s->avdtp_bytes);
}
static uint16_t sbc_bytes(const struct a138_classic_service *s,const uint8_t *p,uint16_t n) {
    const struct a138_classic_format *f=&s->format;
    uint8_t blocks,sub,mode,alloc; uint16_t bytes,audio;
    if (n<4u || p[0]!=0x9cu) return 0;
    blocks=(uint8_t)(4u+4u*((p[1]>>4)&3u)); sub=(uint8_t)(p[1]&1u ? 8u : 4u);
    mode=(p[1]>>2)&3u; alloc=(p[1]>>1)&1u;
    if ((p[1]>>6)!=(f->rate_hz==44100u ? 2u : 3u) || blocks!=f->blocks || sub!=f->subbands ||
        mode!=f->mode || alloc!=f->allocation || p[2]<f->min_bitpool || p[2]>f->max_bitpool) return 0;
    bytes=(uint16_t)(4u+(4u*sub*(mode ? 2u : 1u))/8u);
    audio=(uint16_t)(blocks*p[2]*(mode==1u ? 2u : 1u)+(mode==3u ? sub : 0u));
    bytes=(uint16_t)(bytes+(audio+7u)/8u);
    return bytes<=n && bytes<=A138_CLASSIC_FRAME_BYTES ? bytes : 0;
}
static void frame_push(struct a138_classic_service *s,const uint8_t *p,uint16_t n,uint16_t seq,uint32_t time) {
    struct a138_classic_frame *f=&s->frame[(s->frame_head+s->frame_count)%A138_CLASSIC_FRAMES];
    f->link_epoch=s->link_epoch; f->stream_epoch=s->stream_epoch; f->sequence=seq;
    f->timestamp=time; f->format=s->format; f->bytes=n; memcpy(f->data,p,n); ++s->frame_count;
}
static enum a138_classic_result media_drop(struct a138_classic_service *s) {
    uint16_t seq=s->sequence; uint32_t ssrc=s->ssrc;
    uint8_t sv=s->sequence_valid,ss=s->ssrc_valid;
    ++s->media_dropped; silence(s);
    s->sequence=seq; s->ssrc=ssrc; s->sequence_valid=sv; s->ssrc_valid=ss;
    return s->fenced ? A138_CLASSIC_FENCED : A138_CLASSIC_DROPPED;
}
static enum a138_classic_result media(struct a138_classic_service *s,const uint8_t *p,uint16_t n) {
    uint16_t off,end=n,seq,lengths[15],pos; uint32_t time,ssrc; uint8_t count,flags,i;
    if (s->state!=A138_CLASSIC_STREAMING || !s->ready) return media_drop(s);
    /* A2DP1.4 SBC requires dynamic PT, M=0 and X=0. */
    if (n<13u || (p[0]>>6)!=2u || (p[0]&0x10u) || (p[1]&0x80u) || (p[1]&0x7fu)<96u) return media_drop(s);
    off=(uint16_t)(12u+4u*(p[0]&15u));
    if (off>=n) return media_drop(s);
    if (p[0]&0x20u) {
        uint8_t pad=p[n-1];
        if (!pad || pad>=n-off) return media_drop(s);
        end=(uint16_t)(n-pad);
    }
    seq=be16(p+2); time=be32(p+4); ssrc=be32(p+8);
    if (s->ssrc_valid && ssrc!=s->ssrc) return media_drop(s);
    if (s->sequence_valid) {
        uint16_t delta=(uint16_t)(seq-s->sequence);
        if (!delta || delta>0x8000u) { ++s->media_dropped; return A138_CLASSIC_DROPPED; }
        if (delta!=1u) {
            ++s->sequence_gaps; silence(s);
            if (s->fenced) return A138_CLASSIC_FENCED;
        }
    }
    s->sequence=seq; s->sequence_valid=1; s->ssrc=ssrc; s->ssrc_valid=1;
    flags=p[off++]; count=flags&15u;
    if (end<=off) return media_drop(s);
    if (flags&0x10u) return media_drop(s);
    if (flags&0x80u) { /* One fragmented SBC frame, bounded to 224 bytes. */
        uint8_t start=flags&0x40u,last=flags&0x20u;
        if (!count || (start && last) || (last!=(count==1u ? 0x20u : 0u))) return media_drop(s);
        if (start) {
            if (s->fragment_active || count<2u) return media_drop(s);
            s->fragment_active=1; s->fragment_bytes=0;
            s->fragment_remaining=count; s->fragment_packet_bytes=n;
            s->fragment_timestamp=time; s->fragment_sequence=seq;
        } else if (!s->fragment_active || count!=s->fragment_remaining ||
                   time!=s->fragment_timestamp || (!last && n!=s->fragment_packet_bytes)) return media_drop(s);
        --s->fragment_remaining;
        if ((uint32_t)s->fragment_bytes+end-off>sizeof s->fragment) return media_drop(s);
        memcpy(s->fragment+s->fragment_bytes,p+off,end-off); s->fragment_bytes=(uint16_t)(s->fragment_bytes+end-off);
        if (!last) return A138_CLASSIC_OK;
        s->fragment_active=0;
        if (s->frame_count==A138_CLASSIC_FRAMES || sbc_bytes(s,s->fragment,s->fragment_bytes)!=s->fragment_bytes) return media_drop(s);
        frame_push(s,s->fragment,s->fragment_bytes,s->fragment_sequence,s->fragment_timestamp); return A138_CLASSIC_OK;
    }
    if ((flags&0x60u) || !count || s->fragment_active) return media_drop(s);
    pos=off;
    for (i=0;i<count;++i) {
        uint16_t len=sbc_bytes(s,p+pos,(uint16_t)(end-pos));
        if (!len) return media_drop(s);
        lengths[i]=len; pos=(uint16_t)(pos+len);
    }
    if (pos!=end || count>A138_CLASSIC_FRAMES-s->frame_count) return media_drop(s);
    for (i=0;i<count;++i) {
        frame_push(s,p+off,lengths[i],seq,time); off=(uint16_t)(off+lengths[i]);
        time+=(uint32_t)s->format.blocks*s->format.subbands;
    }
    return A138_CLASSIC_OK;
}

static enum a138_classic_result dispatch(struct a138_classic_service *s) {
    uint16_t n,cid; int i; enum a138_classic_result r;
    if (!s->rx_complete || s->tx_bytes) return A138_CLASSIC_OK;
    n=le16(s->rx); cid=le16(s->rx+2); s->rx_complete=0;
    if (cid==SIGNALING) r=n<=48u ? signaling(s,s->rx+4,n) : A138_CLASSIC_MALFORMED;
    else {
        i=channel_index(cid);
        if (i<0 || !channel_open(s,(unsigned)i)) r=A138_CLASSIC_MALFORMED;
        else if (i==0) r=sdp(s,s->rx+4,n);
        else if (i==1) r=avdtp(s,s->rx+4,n);
        else r=media(s,s->rx+4,n);
    }
    s->rx_bytes=0; s->rx_total=0;
    if (r==A138_CLASSIC_MALFORMED) ++s->malformed;
    return r;
}
enum a138_classic_result a138_classic_acl(struct a138_classic_service *s,uint32_t e,uint32_t g,
        const uint8_t *p,uint16_t n) {
    uint16_t hp,bytes; uint8_t pb; enum a138_classic_result r=identity(s,e,g);
    if (r!=A138_CLASSIC_OK) return r;
    if (!p || n<4u || n>A138_CLASSIC_ACL_BYTES) return A138_CLASSIC_ARGUMENT;
    hp=le16(p); bytes=le16(p+2); pb=(hp>>12)&3u;
    if ((hp&0x0fffu)!=s->handle) return A138_CLASSIC_STALE;
    if (s->rx_complete) return A138_CLASSIC_BUSY;
    if ((hp&0xc000u) || bytes!=n-4u || !bytes) goto malformed;
    if (pb==2u) { /* BR/EDR controller-to-host first automatically-flushable. */
        if (s->rx_bytes || bytes<4u || le16(p+4)>A138_CLASSIC_MTU) goto malformed;
        s->rx_total=(uint16_t)(le16(p+4)+4u);
    } else if (pb==1u) {
        if (!s->rx_bytes) goto malformed;
    } else goto malformed; /* PB=0 reserved C->H; PB=3 no BR/EDR use here. */
    if ((uint32_t)s->rx_bytes+bytes>s->rx_total) goto malformed;
    memcpy(s->rx+s->rx_bytes,p+4,bytes); s->rx_bytes=(uint16_t)(s->rx_bytes+bytes);
    if (s->rx_bytes==s->rx_total) { s->rx_complete=1; return dispatch(s); }
    return A138_CLASSIC_OK;
malformed:
    s->rx_bytes=0; s->rx_total=0; ++s->malformed; silence(s);
    return s->fenced ? A138_CLASSIC_FENCED : A138_CLASSIC_MALFORMED;
}
enum a138_classic_result a138_classic_tx_peek(struct a138_classic_service *s,struct a138_classic_tx *out) {
    uint16_t bytes; enum a138_classic_result r;
    if (!s || !out) return A138_CLASSIC_ARGUMENT;
    r=identity(s,s->link_epoch,s->generation); if (r!=A138_CLASSIC_OK) return r;
    if (!s->tx_bytes) return A138_CLASSIC_EMPTY;
    if (!s->offered) {
        if (s->next_token==UINT32_MAX) return fence(s);
        s->offered_token=++s->next_token; s->offered=1;
        bytes=(uint16_t)(s->tx_bytes-s->tx_offset); if (bytes>s->tx_payload_limit) bytes=s->tx_payload_limit;
        s->tx_offered=bytes;
    }
    out->link_epoch=s->link_epoch; out->generation=s->generation; out->token=s->offered_token;
    out->bytes=(uint16_t)(s->tx_offered+4u);
    putle(out->data,(uint16_t)(s->handle|(s->tx_offset ? 0x1000u : 0x2000u)));
    putle(out->data+2,s->tx_offered); memcpy(out->data+4,s->tx+s->tx_offset,s->tx_offered);
    return A138_CLASSIC_OK;
}
enum a138_classic_result a138_classic_tx_result(struct a138_classic_service *s,uint32_t e,uint32_t g,
        uint32_t token,enum a138_classic_submission result) {
    enum a138_classic_result r=identity(s,e,g); uint8_t next;
    if (r!=A138_CLASSIC_OK) return r;
    if (!s->offered || token!=s->offered_token) return A138_CLASSIC_STALE;
    if ((unsigned)result>A138_CLASSIC_UNCERTAIN) return A138_CLASSIC_ARGUMENT;
    if (result==A138_CLASSIC_UNCERTAIN) return fence(s);
    if (result==A138_CLASSIC_REJECTED) return A138_CLASSIC_OK;
    s->tx_offset=(uint16_t)(s->tx_offset+s->tx_offered); s->offered=0;
    if (s->tx_offset<s->tx_bytes) return A138_CLASSIC_OK;
    s->tx_bytes=0; s->tx_offset=0;
    if (s->tx_is_delay) {
        s->tx_is_delay=0; s->delay_sent=1;
        s->delay_phase=A138_CLASSIC_DELAY_WAIT; s->delay_started_ms=s->clock_ms;
        return dispatch(s);
    }
    if (s->pending_config) {
        memcpy(s->codec,s->pending_codec,4); codec_format(s->codec,&s->format);
        s->pending_config=0; s->ready=0;
        s->delay_selected=s->pending_delay_selected; s->remote_seid=s->pending_remote_seid;
        s->delay_sent=0; s->delay_failure=0;
        s->delay_phase=s->delay_selected ? A138_CLASSIC_DELAY_QUEUED : A138_CLASSIC_DELAY_NONE;
    }
    next=s->pending_state; s->pending_state=NO_STATE;
    if (next!=NO_STATE) {
        silence(s); s->state=next;
        if (next==A138_CLASSIC_IDLE) {
            s->ready=0; s->delay_selected=0; s->delay_phase=A138_CLASSIC_DELAY_NONE; s->remote_seid=0;
        }
    }
    if (s->fenced) return A138_CLASSIC_FENCED;
    r=delay_schedule(s); if (r!=A138_CLASSIC_OK) return r;
    return dispatch(s);
}
enum a138_classic_result a138_classic_tick(struct a138_classic_service *s,uint32_t e,uint32_t g,
        uint32_t now) {
    enum a138_classic_result r=identity(s,e,g); if (r!=A138_CLASSIC_OK) return r;
    if (s->clock_valid && (uint32_t)(now-s->clock_ms)>=0x80000000u)
        return delay_fail(s,A138_CLASSIC_DELAY_CLOCK_REGRESSED);
    s->clock_ms=now; s->clock_valid=1;
    if ((s->delay_phase==A138_CLASSIC_DELAY_TX || s->delay_phase==A138_CLASSIC_DELAY_WAIT) &&
        (uint32_t)(now-s->delay_started_ms)>=A138_CLASSIC_DELAY_TIMEOUT_MS)
        return delay_fail(s,A138_CLASSIC_DELAY_TIMEOUT);
    return A138_CLASSIC_OK;
}
enum a138_classic_result a138_classic_delay_update(struct a138_classic_service *s,uint32_t e,uint32_t g,
        uint32_t delay) {
    enum a138_classic_result r=identity(s,e,g); if (r!=A138_CLASSIC_OK) return r;
    if (delay>UINT16_MAX) return A138_CLASSIC_ARGUMENT;
    if (s->delay_valid && s->delay_value==delay) return A138_CLASSIC_OK;
    if (s->delay_selected && (s->tx_bytes || s->rx_complete || s->delay_phase!=A138_CLASSIC_DELAY_COMPLETE))
        return A138_CLASSIC_BUSY;
    s->delay_value=(uint16_t)delay; s->delay_valid=1;
    if (s->delay_selected) s->delay_phase=A138_CLASSIC_DELAY_QUEUED;
    return delay_schedule(s);
}
enum a138_classic_result a138_classic_audio_ready(struct a138_classic_service *s,uint32_t e,uint32_t g,
        uint32_t rate,uint8_t ready) {
    enum a138_classic_result r=identity(s,e,g); if (r!=A138_CLASSIC_OK) return r;
    if (ready>1u || rate!=s->format.rate_hz || s->state==A138_CLASSIC_IDLE) return A138_CLASSIC_ARGUMENT;
    if (!ready && s->pending_state==A138_CLASSIC_STREAMING) return fence(s);
    if (!ready && s->state==A138_CLASSIC_STREAMING) { silence(s); s->state=A138_CLASSIC_OPEN; }
    s->ready=ready; return s->fenced ? A138_CLASSIC_FENCED : A138_CLASSIC_OK;
}
enum a138_classic_result a138_classic_frame_pop(struct a138_classic_service *s,struct a138_classic_frame *out) {
    enum a138_classic_result r;
    if (!s || !out) return A138_CLASSIC_ARGUMENT;
    r=identity(s,s->link_epoch,s->generation); if (r!=A138_CLASSIC_OK) return r;
    if(!s->security_ready)return A138_CLASSIC_EMPTY;
    if (!s->frame_count) return A138_CLASSIC_EMPTY;
    *out=s->frame[s->frame_head]; s->frame_head=(uint8_t)((s->frame_head+1u)%A138_CLASSIC_FRAMES); --s->frame_count;
    return A138_CLASSIC_OK;
}
