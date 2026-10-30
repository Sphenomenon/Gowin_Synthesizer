#include "business_mailbox.h"
#include "audio_services.h"
static int business_mmio_read(void *context,uint32_t offset,uint32_t *value) {
    *value=a138_read((uintptr_t)context,offset);return 1;
}
static int business_mmio_write(void *context,uint32_t offset,uint32_t value) {
    a138_write((uintptr_t)context,offset,value);return 1;
}
a138_business_bus a138_business_mmio_bus(uintptr_t base) {
    a138_business_bus bus={(void *)base,business_mmio_read,business_mmio_write};return bus;
}
static int valid(const a138_business_bus *bus) { return bus && bus->read && bus->write; }
static int key_valid(const a138_business_key *key) { return key && key->boot_id && key->owner; }
static int read_key(const a138_business_bus *bus,uint32_t offset,a138_business_key *key) {
    uint32_t low,high;
    return bus->read(bus->context,offset,&key->ticket) &&
        bus->read(bus->context,offset+4,&key->owner) &&
        bus->read(bus->context,offset+8,&key->session) &&
        bus->read(bus->context,offset+12,&low) && bus->read(bus->context,offset+16,&high) &&
        (key->boot_id=((uint64_t)high<<32)|low,1);
}
static int same_key(const a138_business_key *a,const a138_business_key *b) {
    return a->ticket==b->ticket && a->owner==b->owner && a->session==b->session && a->boot_id==b->boot_id;
}
static int stage_key(const a138_business_bus *bus,const a138_business_key *key) {
    const uint32_t values[5]={key->ticket,key->owner,key->session,(uint32_t)key->boot_id,(uint32_t)(key->boot_id>>32)};
    for(uint32_t i=0;i<5;i++)if(!bus->write(bus->context,A138_BM_KEY_TICKET+i*4,values[i]))return A138_BM_IO;
    return A138_BM_OK;
}
static int commit(const a138_business_bus *bus,uint32_t command) {
    return bus->write(bus->context,A138_BM_COMMAND,command) ? A138_BM_OK : A138_BM_COMMIT_UNCERTAIN;
}
static int key_command(const a138_business_bus *bus,const a138_business_key *key,uint32_t command,int context) {
    if(!valid(bus) || !key_valid(key) || (context ? key->ticket!=0 : key->ticket==0))return A138_BM_INVALID;
    int result=stage_key(bus,key);return result==A138_BM_OK ? commit(bus,command) : result;
}
int a138_business_probe(const a138_business_bus *bus) {
    uint32_t id,caps;
    if(!valid(bus))return A138_BM_INVALID;
    if(!bus->read(bus->context,A138_BM_ID,&id) || !bus->read(bus->context,A138_BM_CAPS,&caps))return A138_BM_IO;
    return id==UINT32_C(0x424d4201) && caps==UINT32_C(0x00401001) ? A138_BM_OK : A138_BM_INVALID;
}
int a138_business_context(const a138_business_bus *bus,a138_business_key *out) {
    a138_business_key key={0};uint32_t low,high,owner,session,again_low,again_high;
    if(!valid(bus) || !out)return A138_BM_INVALID;
    if(!bus->read(bus->context,A138_BM_OWNER,&key.owner) ||
       !bus->read(bus->context,A138_BM_BOOT_LOW,&low) || !bus->read(bus->context,A138_BM_BOOT_HIGH,&high) ||
       !bus->read(bus->context,A138_BM_SESSION,&key.session) || !bus->read(bus->context,A138_BM_OWNER,&owner) ||
       !bus->read(bus->context,A138_BM_SESSION,&session) || !bus->read(bus->context,A138_BM_BOOT_LOW,&again_low) ||
       !bus->read(bus->context,A138_BM_BOOT_HIGH,&again_high))return A138_BM_IO;
    key.boot_id=((uint64_t)high<<32)|low;
    if(!key_valid(&key) || owner!=key.owner || session!=key.session || low!=again_low || high!=again_high)return A138_BM_STALE;
    *out=key;return A138_BM_OK;
}
int a138_business_read_request(const a138_business_bus *bus,a138_business_request *out) {
    a138_business_request request={0};a138_business_key again_key={0};uint32_t state,meta,low,high,word,state_again,owner;
    if(!valid(bus) || !out)return A138_BM_INVALID;
    if(!bus->read(bus->context,A138_BM_STATE,&state))return A138_BM_IO;
    if((state&3u)!=A138_BM_QUEUED && (state&3u)!=A138_BM_CLAIMED)return A138_BM_NONE;
    if(!read_key(bus,A138_BM_TICKET,&request.key) || !bus->read(bus->context,A138_BM_REQUEST_ID,&request.request_id) ||
       !bus->read(bus->context,A138_BM_NONCE_LOW,&low) || !bus->read(bus->context,A138_BM_NONCE_HIGH,&high) ||
       !bus->read(bus->context,A138_BM_REQUEST_META,&meta))return A138_BM_IO;
    request.nonce=((uint64_t)high<<32)|low;request.opcode=(meta>>16)&255u;request.length=meta&65535u;
    if((meta>>24)!=0 || request.length>16 || !request.request_id || !request.nonce ||
       !key_valid(&request.key) || !request.key.ticket || !request.key.session)return A138_BM_INVALID;
    for(uint32_t i=0;i<4;i++) {
        if(!bus->read(bus->context,A138_BM_REQUEST_DATA0+i*4,&word))return A138_BM_IO;
        for(uint32_t j=0;j<4;j++)request.payload[i*4+j]=(uint8_t)(word>>(j*8));
    }
    if(!read_key(bus,A138_BM_TICKET,&again_key) || !bus->read(bus->context,A138_BM_STATE,&state_again) ||
       !bus->read(bus->context,A138_BM_OWNER,&owner))return A138_BM_IO;
    if(!same_key(&again_key,&request.key) || state!=state_again || owner!=request.key.owner || !(state_again&256u))return A138_BM_STALE;
    *out=request;return A138_BM_OK;
}
int a138_business_open(const a138_business_bus *bus,const a138_business_key *key) { return key_command(bus,key,A138_BM_OPEN,1); }
int a138_business_claim(const a138_business_bus *bus,const a138_business_key *key) { return key_command(bus,key,A138_BM_CLAIM,0); }
int a138_business_abandon(const a138_business_bus *bus,const a138_business_key *key) { return key_command(bus,key,A138_BM_ABANDON,0); }
int a138_business_close(const a138_business_bus *bus,const a138_business_key *key) { return key_command(bus,key,A138_BM_CLOSE,1); }
int a138_business_complete(const a138_business_bus *bus,const a138_business_key *key,const a138_business_completion *result) {
    if(!valid(bus) || !key_valid(key) || !key->ticket || !result || result->phase<A138_BM_PENDING ||
       result->phase>A138_BM_FAILED || result->status>255 || result->length>64 ||
       (result->length && !result->payload) || (result->phase==A138_BM_PENDING && !result->operation_id))return A138_BM_INVALID;
    int staged=stage_key(bus,key);if(staged!=A138_BM_OK)return staged;
    if(!bus->write(bus->context,A138_BM_RESULT_META,result->phase|(result->status<<8)|(result->length<<16)) ||
       !bus->write(bus->context,A138_BM_RESULT_OPERATION,result->operation_id))return A138_BM_IO;
    for(uint32_t i=0;i<16;i++) {
        uint32_t word=0;
        for(uint32_t j=0;j<4;j++)if(i*4+j<result->length)word|=(uint32_t)result->payload[i*4+j]<<(j*8);
        if(!bus->write(bus->context,A138_BM_RESULT_DATA0+i*4,word))return A138_BM_IO;
    }
    return commit(bus,A138_BM_COMPLETE);
}
int a138_business_observe(const a138_business_bus *bus,const a138_business_key *key,a138_business_observation *out) {
    a138_business_key observed={0},again_key={0};a138_business_observation observation={0};uint32_t meta,meta_again,state;
    if(!valid(bus) || !key_valid(key) || !key->ticket || !out)return A138_BM_INVALID;
    if(!bus->read(bus->context,A138_BM_STATE,&state) || !read_key(bus,A138_BM_TICKET,&observed) ||
       !bus->read(bus->context,A138_BM_RESULT_META,&meta) || !bus->read(bus->context,A138_BM_RESULT_OPERATION,&observation.operation_id) ||
       !read_key(bus,A138_BM_TICKET,&again_key) || !bus->read(bus->context,A138_BM_STATE,&observation.state) ||
       !bus->read(bus->context,A138_BM_RESULT_META,&meta_again))return A138_BM_IO;
    if(!same_key(&again_key,&observed) || state!=observation.state || meta!=meta_again)return A138_BM_STALE;
    observation.state&=3u;
    if(observation.state!=A138_BM_EMPTY && same_key(&observed,key)) {
        if(observation.state!=A138_BM_RESULT) { meta=0;observation.operation_id=0; }
    } else {
        if(!read_key(bus,A138_BM_LAST_TICKET,&observed) || !bus->read(bus->context,A138_BM_LAST_META,&meta) ||
           !bus->read(bus->context,A138_BM_LAST_OPERATION,&observation.operation_id) ||
           !read_key(bus,A138_BM_LAST_TICKET,&again_key) || !bus->read(bus->context,A138_BM_LAST_META,&meta_again))return A138_BM_IO;
        if(!same_key(&again_key,&observed) || meta!=meta_again)return A138_BM_STALE;
        if(!same_key(&observed,key))return A138_BM_NONE;
        observation.state=A138_BM_PUBLISHED;
    }
    observation.phase=meta&255u;observation.status=(meta>>8)&255u;observation.length=(meta>>16)&255u;
    observation.reason=meta>>24;*out=observation;return A138_BM_OK;
}
