#include "recording_service.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint32_t registers[32], offsets[16], values[16];
    unsigned calls, fail, reads, writes;
    int change_identity, change_snapshot;
} model;

static int read_bus(void *context, uint32_t offset, uint32_t *value) {
    model *m = context;
    assert(m->calls < 16);
    m->offsets[m->calls++] = offset;
    ++m->reads;
    if (m->fail == m->calls) return 0;
    *value = m->registers[offset / 4];
    if (m->change_identity && m->reads == 9) ++*value;
    if (m->change_snapshot && m->reads == 10) *value ^= 64u;
    return 1;
}
static int write_bus(void *context, uint32_t offset, uint32_t value) {
    model *m = context;
    assert(m->calls < 16);
    m->offsets[m->calls] = offset;
    m->values[m->calls++] = value;
    ++m->writes;
    /* A failed transport is allowed to have committed the write. */
    m->registers[offset / 4] = value;
    return m->fail != m->calls;
}
static a138_record_bus bus(model *m) {
    a138_record_bus b = {m, read_bus, write_bus};
    return b;
}
int main(void) {
    model m = {0};
    a138_record_bus b = bus(&m);
    assert(!a138_record_create(&b, 0, 1));
    assert(!a138_record_create(&b, 1, 0));
    assert(!a138_record_create(&b, 1, 16385));
    assert(!a138_record_command(&b, 0));
    assert(!a138_record_download(&b, 0, 0));
    assert(m.calls == 0);
    assert(a138_record_create(&b, UINT64_C(0x123456789abcdef0), 16384));
    assert(m.calls == 4 && m.writes == 4 && !m.reads);
    assert(m.offsets[0] == A138_REC_STAGE_ID_LOW && m.values[0] == 0x9abcdef0u);
    assert(m.offsets[1] == A138_REC_STAGE_ID_HIGH && m.values[1] == 0x12345678u);
    assert(m.offsets[2] == A138_REC_LIMIT && m.values[2] == 16384);
    assert(m.offsets[3] == A138_REC_COMMAND && m.values[3] == A138_REC_CREATE);
    for (unsigned failure = 1; failure <= 4; ++failure) {
        memset(&m, 0, sizeof m); m.fail = failure;
        assert(!a138_record_create(&b, 1, 4));
        assert(m.calls == failure && m.writes == failure); /* no retry */
    }
    a138_record_status status, sentinel;
    memset(&sentinel, 0xa5, sizeof sentinel);
    for (unsigned failure = 1; failure <= 9; ++failure) {
        memset(&m, 0, sizeof m); m.fail = failure; status = sentinel;
        assert(!a138_record_poll(&b, &status));
        assert(m.calls == failure && !m.writes);
        assert(!memcmp(&status, &sentinel, sizeof status));
    }
    memset(&m, 0, sizeof m); status = sentinel;
    m.change_identity = 1;
    assert(!a138_record_poll(&b, &status));
    assert(m.calls == 9 && !memcmp(&status, &sentinel, sizeof status));
    memset(&m, 0, sizeof m);
    m.registers[A138_REC_OBJECT_LOW / 4] = 9;
    m.registers[A138_REC_OBJECT_HIGH / 4] = 2;
    m.registers[A138_REC_STATUS / 4] = 3;
    m.registers[A138_REC_RATE / 4] = 44100;
    m.registers[A138_REC_EPOCH / 4] = 81;
    assert(a138_record_poll(&b, &status));
    assert(m.calls == 9 && status.object_id == UINT64_C(0x200000009));
    assert(status.state == 3 && status.rate_hz == 44100 && status.epoch == 81);
    a138_record_head head, head_sentinel;
    memset(&head_sentinel, 0x5a, sizeof head_sentinel);
    for (unsigned failure = 1; failure <= 10; ++failure) {
        memset(&m, 0, sizeof m); m.fail = failure;
        m.registers[A138_REC_DATA_STATUS / 4] = 128u | 64u | 13u;
        head = head_sentinel;
        assert(!a138_record_read_head(&b, &head));
        assert(m.calls == failure && !m.writes);
        assert(!memcmp(&head, &head_sentinel, sizeof head));
    }
    memset(&m, 0, sizeof m); head = head_sentinel;
    assert(!a138_record_read_head(&b, &head) && m.calls == 1);
    assert(!memcmp(&head, &head_sentinel, sizeof head));
    memset(&m, 0, sizeof m); head = head_sentinel;
    m.registers[A138_REC_DATA_STATUS / 4] = 128u | 64u | 13u;
    m.change_snapshot = 1;
    assert(!a138_record_read_head(&b, &head));
    assert(m.calls == 10 && !memcmp(&head, &head_sentinel, sizeof head));
    m.calls = m.reads = 0; m.change_snapshot = 0;
    for (unsigned i = 0; i < 8; ++i) m.registers[A138_REC_DATA0 / 4 + i] = 0x12340000u + i;
    assert(a138_record_read_head(&b, &head) && m.calls == 10 && !m.writes);
    assert(head.bytes == 13 && head.last == 1);
    for (unsigned i = 0; i < 8; ++i) assert(head.words[i] == 0x12340000u + i);
    puts("PASS recording API bounded failures, preserved outputs, stable windows; no physical MMIO");
    return 0;
}
