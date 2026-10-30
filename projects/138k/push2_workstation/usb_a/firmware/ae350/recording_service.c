#include "recording_service.h"
#include "audio_services.h"
static int record_mmio_read(void *context,uint32_t offset,uint32_t *value) {
    *value=a138_read((uintptr_t)context,offset);return 1;
}
static int record_mmio_write(void *context,uint32_t offset,uint32_t value) {
    a138_write((uintptr_t)context,offset,value);return 1;
}
a138_record_bus a138_record_mmio_bus(uintptr_t base) {
    a138_record_bus b={(void *)base,record_mmio_read,record_mmio_write};return b;
}
static int valid(const a138_record_bus *b) { return b && b->read && b->write; }
static int stage_id(const a138_record_bus *b,uint64_t id) {
    return valid(b) && id && b->write(b->context,A138_REC_STAGE_ID_LOW,(uint32_t)id) &&
        b->write(b->context,A138_REC_STAGE_ID_HIGH,(uint32_t)(id>>32));
}
int a138_record_probe(const a138_record_bus *b) {
    uint32_t id,caps;
    return valid(b) && b->read(b->context,A138_REC_ID,&id) && b->read(b->context,A138_REC_CAPS,&caps) &&
        id==UINT32_C(0x52434401) && caps==UINT32_C(0x00010007);
}
int a138_record_command(const a138_record_bus *b,uint32_t command) {
    return valid(b) && command>=A138_REC_CREATE && command<=A138_REC_RELEASE_HEAD &&
        b->write(b->context,A138_REC_COMMAND,command);
}
int a138_record_create(const a138_record_bus *b,uint64_t id,uint32_t frames) {
    return frames && frames<=16384u && stage_id(b,id) &&
        b->write(b->context,A138_REC_LIMIT,frames) && a138_record_command(b,A138_REC_CREATE);
}
int a138_record_acquire(const a138_record_bus *b,uint64_t id) {
    return stage_id(b,id) && a138_record_command(b,A138_REC_ACQUIRE);
}
int a138_record_download(const a138_record_bus *b,uint32_t offset,uint32_t length) {
    return valid(b) && length && b->write(b->context,A138_REC_OFFSET,offset) &&
        b->write(b->context,A138_REC_LENGTH,length) && a138_record_command(b,A138_REC_DOWNLOAD);
}
int a138_record_poll(const a138_record_bus *b,a138_record_status *out) {
    uint32_t low,high,again,high_again,status; a138_record_status s={0};
    if(!valid(b) || !out || !b->read(b->context,A138_REC_OBJECT_LOW,&low) ||
        !b->read(b->context,A138_REC_OBJECT_HIGH,&high) || !b->read(b->context,A138_REC_STATUS,&status) ||
        !b->read(b->context,A138_REC_RATE,&s.rate_hz) || !b->read(b->context,A138_REC_EPOCH,&s.epoch) ||
        !b->read(b->context,A138_REC_FRAMES,&s.frames) || !b->read(b->context,A138_REC_COMMITTED,&s.committed) ||
        !b->read(b->context,A138_REC_OBJECT_LOW,&again) || !b->read(b->context,A138_REC_OBJECT_HIGH,&high_again) ||
        low!=again || high!=high_again) return 0;
    s.object_id=((uint64_t)high<<32)|low;s.state=status&15u;s.failure=(status>>4)&15u;
    *out=s;return 1;
}
int a138_record_read_head(const a138_record_bus *b,a138_record_head *out) {
    uint32_t status,again;a138_record_head h={0};
    if(!valid(b) || !out || !b->read(b->context,A138_REC_DATA_STATUS,&status) || !(status&128u)) return 0;
    for(uint32_t i=0;i<8u;i++)if(!b->read(b->context,A138_REC_DATA0+4u*i,&h.words[i])) return 0;
    if(!b->read(b->context,A138_REC_DATA_STATUS,&again) || again!=status) return 0;
    h.bytes=status&63u;h.last=(status>>6)&1u;*out=h;return 1;
}
#ifdef A138_BLE_BUSINESS
int a138_record_data_probe(const a138_record_bus *b) {
    uint32_t id,caps;
    return valid(b) && b->read(b->context,0,&id) && b->read(b->context,4,&caps) &&
        id==UINT32_C(0x52434402) && caps==UINT32_C(0x00301001);
}
int a138_record_data_poll(const a138_record_bus *b,a138_record_data_facts *out) {
    a138_record_data_facts f={0};uint32_t again,generation;
    if(!valid(b) || !out || !b->read(b->context,A138_DATA_GENERATION,&f.generation) ||
       !b->read(b->context,A138_DATA_OBJECT,&f.object_id) ||
       !b->read(b->context,A138_DATA_STATUS,&f.state) ||
       !b->read(b->context,A138_DATA_FRAMES,&f.frames) ||
       !b->read(b->context,A138_DATA_COMMITTED,&f.committed) ||
       !b->read(b->context,A138_DATA_CRC,&f.crc) ||
       !b->read(b->context,A138_DATA_REASON,&f.reason) ||
       !b->read(b->context,A138_DATA_TRANSFER,&f.transfer_id) ||
       !b->read(b->context,A138_DATA_OFFSET,&f.offset) ||
       !b->read(b->context,A138_DATA_TIME,&f.time_ms) ||
       !b->read(b->context,A138_DATA_ACCEPTED,&f.accepted_seq) ||
       !b->read(b->context,A138_DATA_APPLIED,&f.applied_seq) ||
       !b->read(b->context,A138_DATA_FIRST_MS,&f.first_ms) ||
       !b->read(b->context,A138_DATA_TERMINAL_MS,&f.terminal_ms) ||
       !b->read(b->context,A138_DATA_OBJECT,&again) ||
       !b->read(b->context,A138_DATA_GENERATION,&generation))return A138_DATA_IO;
    if(again!=f.object_id || generation!=f.generation)return A138_DATA_NONE;
    *out=f;return A138_DATA_OK;
}
int a138_record_data_submit(const a138_record_bus *b,const a138_record_data_command *c) {
    if(!valid(b) || !c || !c->sequence || !c->request_id || !c->nonce ||
       c->opcode>255 || c->length>16)return A138_DATA_IO;
    const uint32_t offsets[9]={A138_DATA_STAGE_SEQ,A138_REC_STAGE_ID_LOW,A138_DATA_STAGE_TRANSFER,
        A138_DATA_OPCODE,A138_DATA_LENGTH,A138_DATA_REQUEST,A138_DATA_NONCE_LOW,A138_DATA_NONCE_HIGH,0};
    const uint32_t values[8]={c->sequence,c->object_id,c->transfer_id,c->opcode,c->length,
        c->request_id,(uint32_t)c->nonce,(uint32_t)(c->nonce>>32)};
    for(unsigned i=0;i<8;i++)if(!b->write(b->context,offsets[i],values[i]))return A138_DATA_IO;
    for(unsigned i=0;i<4;i++) {
        uint32_t word=0;for(unsigned j=0;j<4;j++)word|=(uint32_t)c->payload[4*i+j]<<(8*j);
        if(!b->write(b->context,A138_DATA_PAYLOAD+4*i,word))return A138_DATA_IO;
    }
    return b->write(b->context,A138_REC_COMMAND,1) ? A138_DATA_OK:A138_DATA_UNCERTAIN;
}
int a138_record_data_result_read(const a138_record_bus *b,uint32_t seq,a138_record_data_result *out) {
    a138_record_data_result r={0};uint32_t applied,meta,again,word;
    if(!valid(b) || !seq || !out || !b->read(b->context,A138_DATA_APPLIED,&applied))return A138_DATA_IO;
    if(applied!=seq)return A138_DATA_NONE;
    if(!b->read(b->context,A138_DATA_RESULT_META,&meta))return A138_DATA_IO;
    r.sequence=seq;r.status=meta&255u;r.length=(meta>>8)&127u;
    if((meta>>15)!=0 || r.length>48)return A138_DATA_IO;
    for(unsigned i=0;i<12;i++) {
        if(!b->read(b->context,A138_DATA_RESULT_PAYLOAD+4*i,&word))return A138_DATA_IO;
        for(unsigned j=0;j<4;j++)r.payload[4*i+j]=(uint8_t)(word>>(8*j));
    }
    if(!b->read(b->context,A138_DATA_APPLIED,&again))return A138_DATA_IO;
    if(again!=seq)return A138_DATA_NONE;
    *out=r;return A138_DATA_OK;
}

#endif /* A138_BLE_BUSINESS: preserve existing default ROM composition. */
