#include "recording_service.h"
#include "audio_services.h"
static int rd(void *context,uint32_t offset,uint32_t *value) {
    *value=a138_read((uintptr_t)context,offset);return 1;
}
static int wr(void *context,uint32_t offset,uint32_t value) {
    a138_write((uintptr_t)context,offset,value);return 1;
}
a138_record_bus a138_record_mmio_bus(uintptr_t base) {
    a138_record_bus b={(void *)base,rd,wr};return b;
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
