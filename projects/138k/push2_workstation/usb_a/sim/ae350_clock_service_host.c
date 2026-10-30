/* Checked bus model for the maintained C client. No physical MMIO is used. */
#include "audio_clock_service.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(A138_CLOCK_BASE==UINT32_C(0xf8030000),"dedicated APB page");
_Static_assert(A138_CLK_COMMAND_ID==0x10 && A138_CLK_RESULT_ID==0x18 &&
               A138_CLK_EXPECTED_EPOCH==0x28 && A138_CLK_ACTUAL==0x2c &&
               A138_CLK_SNAPSHOT_EPOCH==0x30 && A138_CLK_REQUEST_CONTEXT==0x58,"correlation ABI");
_Static_assert(A138_CLK_CAP_MEDIA_POLICY==16 && A138_CLK_MEDIA_STATUS==0x60 &&
               A138_CLK_MEDIA_TIMEOUT==0x64 && A138_CLK_MEDIA_FAILURE==0x68,"media register ABI");
_Static_assert(A138_CLK_MEDIA_HOLD==1 && A138_CLK_MEDIA_PENDING==2 &&
               A138_CLK_MEDIA_COMPLETED==4 && A138_CLK_MEDIA_FAILED==8 &&
               A138_CLK_MEDIA_ENABLED==16 && A138_CLK_MEDIA_BACKEND_READY==32,"media status ABI");
_Static_assert(A138_CLK_BUS_MEDIA_NOT_READY==14 && A138_CLK_RESULT_MEDIA_FAILED==8 &&
               A138_CLK_RESULT_MEDIA_TIMEOUT==9 && A138_CLK_RESULT_MEDIA_GATE==10,"media result ABI");
_Static_assert(A138_CLK_MEDIA_REASON_RECORD_SEAL==9 && A138_CLK_MEDIA_REASON_BLE_SEAL==10,"seal reason ABI");

enum { REGISTER_WORDS=0x6c/4, MAX_ACCESSES=32 };
typedef struct {
    uint32_t registers[REGISTER_WORDS], epoch, offsets[MAX_ACCESSES];
    unsigned accesses, writes, snapshots, fail_at, mutate_at, media_stops;
    uint32_t mutate_offset, mutate_value;
    int reject, fail_after_commit;
} model;
static unsigned checks;
#define CHECK(expr) do { ++checks; if(!(expr)) { \
    fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#expr); exit(1); } } while(0)

static void initialize(model *m) {
    memset(m,0,sizeof(*m));
    m->registers[A138_CLK_ID/4]=UINT32_C(0x434c4b01);
    m->registers[A138_CLK_CAPABILITIES/4]=UINT32_C(0x0001001f);
    m->registers[A138_CLK_STATUS/4]=8;
    m->registers[A138_CLK_ACTUAL/4]=2|8;
    m->registers[A138_CLK_MEDIA_STATUS/4]=A138_CLK_MEDIA_ENABLED|A138_CLK_MEDIA_BACKEND_READY;
    m->registers[A138_CLK_COMMAND_ID/4]=7;
    m->epoch=100;
}
static int access(model *m,uint32_t offset) {
    CHECK((offset&3u)==0 && offset<0x6c && m->accesses<MAX_ACCESSES);
    m->offsets[m->accesses++]=offset;
    if(m->accesses==m->mutate_at)m->registers[m->mutate_offset/4]=m->mutate_value;
    return m->accesses!=m->fail_at;
}
static int read_register(void *context,uint32_t offset,uint32_t *value) {
    model *m=context;
    if(!access(m,offset))return 0;
    *value=m->registers[offset/4];
    if(offset==A138_CLK_ACTUAL) {
        m->registers[A138_CLK_SNAPSHOT_EPOCH/4]=m->epoch;
        ++m->snapshots;
    }
    return 1;
}
static int write_register(void *context,uint32_t offset,uint32_t value) {
    model *m=context;
    int success=access(m,offset);
    if(!success && !m->fail_after_commit)return 0;
    CHECK(offset==A138_CLK_COMMAND && value<=A138_CLK_RECOVER);
    ++m->writes;
    if(!m->reject) {
        uint32_t before=m->registers[A138_CLK_COMMAND_ID/4];
        uint32_t old_rate=m->registers[A138_CLK_ACTUAL/4]&1u;
        uint32_t rate=value==A138_CLK_RECOVER ? old_rate:value;
        uint32_t epoch=m->epoch;
        if(value==A138_CLK_RECOVER || rate!=old_rate) {
            epoch=epoch==UINT32_MAX ? 1u:epoch+1u;
            ++m->media_stops;
        }
        m->registers[A138_CLK_COMMAND_ID/4]=before==UINT32_MAX ? 1u:before+1u;
        m->registers[A138_CLK_EXPECTED_EPOCH/4]=epoch;
        m->registers[A138_CLK_REQUEST_CONTEXT/4]=rate|(value==A138_CLK_RECOVER ? 2u:0u);
        m->registers[A138_CLK_STATUS/4]=8|1;
    }
    return success;
}
static a138_clock_bus bus_for(model *m) {
    return (a138_clock_bus){m,read_register,write_register};
}
static a138_clock_ticket sentinel_ticket(void) {
    return (a138_clock_ticket){900,800,48000};
}
static a138_clock_status sentinel_status(void) {
    a138_clock_status s;
    memset(&s,0x5a,sizeof(s));
    return s;
}
static void clear_trace(model *m) {
    m->accesses=m->writes=m->snapshots=0;
    m->fail_at=m->mutate_at=0;
}
static a138_clock_ticket submitted(model *m,uint32_t operation) {
    a138_clock_ticket t=sentinel_ticket();
    a138_clock_bus bus=bus_for(m);
    CHECK(a138_clock_submit(&bus,operation,&t)==A138_CLK_SUBMITTED);
    CHECK(m->accesses==9 && m->writes==1);
    return t;
}
static void complete(model *m,const a138_clock_ticket *t,uint32_t result) {
    m->registers[A138_CLK_COMMAND_ID/4]=t->command_id;
    m->registers[A138_CLK_STATUS/4]=8;
    m->registers[A138_CLK_RESULT_ID/4]=t->command_id;
    m->registers[A138_CLK_RESULT_CODE/4]=result;
    m->registers[A138_CLK_RESULT_DETAIL/4]=0x1234;
    m->registers[A138_CLK_ACTUAL/4]=(t->expected_rate_hz==44100u ? 1u:0u)|2u|8u;
    m->epoch=t->expected_epoch;
    clear_trace(m);
}
static a138_clock_result poll(model *m,const a138_clock_ticket *t,a138_clock_status *s) {
    a138_clock_bus bus=bus_for(m);
    a138_clock_ticket original=*t;
    a138_clock_result result=a138_clock_poll(&bus,t,s);
    CHECK(memcmp(t,&original,sizeof(original))==0);
    CHECK(m->writes==0 && m->accesses<=11);
    return result;
}

static void test_probe_and_admission(void) {
    model m;
    a138_clock_bus raw=a138_clock_mmio_bus(0);
    CHECK(raw.context==NULL && raw.read && raw.write);
    initialize(&m);
    a138_clock_bus b=bus_for(&m);
    a138_clock_ticket t=sentinel_ticket(),original=t;
    CHECK(a138_clock_probe(&b)==A138_CLK_SUBMITTED && m.accesses==2 && m.writes==0);
    for(unsigned variant=0;variant<3;++variant) {
        initialize(&m);
        if(variant==0)m.registers[A138_CLK_ID/4]=0;
        if(variant==1)m.registers[A138_CLK_CAPABILITIES/4]&=~A138_CLK_CAP_MEDIA_POLICY;
        if(variant==2)m.registers[A138_CLK_CAPABILITIES/4]|=2u<<16;
        CHECK(a138_clock_submit(&b,A138_CLK_44100,&t)==A138_CLK_UNSUPPORTED);
        CHECK(m.writes==0 && memcmp(&t,&original,sizeof(t))==0);
    }
    for(unsigned variant=0;variant<3;++variant) {
        initialize(&m);
        m.registers[A138_CLK_STATUS/4]=variant==0 ? 0u:variant==1 ? 24u:9u;
        CHECK(a138_clock_submit(&b,A138_CLK_44100,&t)==(variant==2 ? A138_CLK_PENDING:A138_CLK_UNARMED));
        CHECK(m.accesses==3 && m.writes==0 && memcmp(&t,&original,sizeof(t))==0);
    }
    initialize(&m);
    CHECK(a138_clock_submit(&b,3,&t)==A138_CLK_INVALID && m.accesses==0);
    CHECK(a138_clock_submit(&b,0,NULL)==A138_CLK_INVALID && m.accesses==0);
    CHECK(a138_clock_probe(NULL)==A138_CLK_INVALID);
    a138_clock_bus invalid={&m,NULL,write_register};
    CHECK(a138_clock_probe(&invalid)==A138_CLK_INVALID);
}
static void test_ticket_and_commit_failures(void) {
    model m;
    for(uint32_t operation=0;operation<=2;++operation) {
        initialize(&m);
        if(operation==2)m.registers[A138_CLK_ACTUAL/4]|=1;
        a138_clock_ticket t=submitted(&m,operation);
        CHECK(t.command_id==8 && t.expected_epoch==(operation ? 101u:100u));
        CHECK(t.expected_rate_hz==(operation ? 44100u:48000u));
        CHECK(m.media_stops==(operation ? 1u:0u));
    }
    initialize(&m);
    m.registers[A138_CLK_COMMAND_ID/4]=UINT32_MAX;m.epoch=UINT32_MAX;
    a138_clock_ticket wrapped=submitted(&m,A138_CLK_44100);
    CHECK(wrapped.command_id==1 && wrapped.expected_epoch==1);
    for(unsigned variant=0;variant<3;++variant) {
        initialize(&m);
        a138_clock_bus b=bus_for(&m);
        a138_clock_ticket t=sentinel_ticket(),original=t;
        if(variant==0)m.reject=1;
        else { m.mutate_at=variant==1 ? 9u:8u;
            m.mutate_offset=variant==1 ? A138_CLK_COMMAND_ID:A138_CLK_REQUEST_CONTEXT;
            m.mutate_value=variant==1 ? 99u:2u; }
        CHECK(a138_clock_submit(&b,A138_CLK_44100,&t)==A138_CLK_REJECTED);
        CHECK(memcmp(&t,&original,sizeof(t))==0 && m.writes==1);
    }
    for(unsigned failure=1;failure<=9;++failure) {
        initialize(&m);m.fail_at=failure;
        a138_clock_bus b=bus_for(&m);
        a138_clock_ticket t=sentinel_ticket(),original=t;
        CHECK(a138_clock_submit(&b,A138_CLK_44100,&t)==A138_CLK_IO_ERROR);
        CHECK(m.accesses==failure && memcmp(&t,&original,sizeof(t))==0);
    }
    initialize(&m);m.fail_at=5;m.fail_after_commit=1;
    a138_clock_bus b=bus_for(&m);
    a138_clock_ticket t=sentinel_ticket(),original=t;
    CHECK(a138_clock_submit(&b,A138_CLK_44100,&t)==A138_CLK_IO_ERROR);
    CHECK(m.registers[A138_CLK_COMMAND_ID/4]==8 && m.writes==1 && memcmp(&t,&original,sizeof(t))==0);
}
static void test_result_and_actual_snapshot(void) {
    model m;
    initialize(&m);
    a138_clock_ticket t=submitted(&m,A138_CLK_44100);
    clear_trace(&m);
    a138_clock_status s=sentinel_status();
    CHECK(poll(&m,&t,&s)==A138_CLK_PENDING && s.phase==1 && s.result_id==0);
    complete(&m,&t,A138_CLK_RESULT_APPLIED);
    m.registers[A138_CLK_SNAPSHOT_EPOCH/4]=0xdead;
    CHECK(poll(&m,&t,&s)==A138_CLK_APPLIED && m.accesses==11 && m.snapshots==1);
    CHECK(s.actual_epoch==101 && s.actual_rate_hz==44100 && s.command_id==8 && s.result_id==8);
    CHECK(m.offsets[7]==A138_CLK_ACTUAL && m.offsets[8]==A138_CLK_SNAPSHOT_EPOCH);
    for(uint32_t code=2;code<=10;++code) {
        complete(&m,&t,code);
        m.registers[A138_CLK_MEDIA_STATUS/4]=A138_CLK_MEDIA_ENABLED|A138_CLK_MEDIA_FAILED;
        m.registers[A138_CLK_MEDIA_FAILURE/4]=9;
        CHECK(poll(&m,&t,&s)==A138_CLK_FAILED);
        CHECK(s.result_code==code && s.detail==0x1234 && s.media_failure==9);
    }
    for(uint32_t reason=0;reason<=10;++reason) {
        complete(&m,&t,reason ? A138_CLK_RESULT_MEDIA_FAILED:A138_CLK_RESULT_MEDIA_TIMEOUT);
        m.registers[A138_CLK_MEDIA_FAILURE/4]=reason;
        CHECK(poll(&m,&t,&s)==A138_CLK_FAILED && s.media_failure==reason);
    }
    for(unsigned variant=0;variant<6;++variant) {
        complete(&m,&t,A138_CLK_RESULT_APPLIED);
        if(variant==0)m.registers[A138_CLK_ACTUAL/4]&=~2u;
        if(variant==1)m.registers[A138_CLK_ACTUAL/4]|=4u;
        if(variant==2)m.registers[A138_CLK_ACTUAL/4]|=16u;
        if(variant==3)m.registers[A138_CLK_ACTUAL/4]|=32u;
        if(variant==4)m.registers[A138_CLK_ACTUAL/4]^=1u;
        if(variant==5)++m.epoch;
        CHECK(poll(&m,&t,&s)==A138_CLK_CONTEXT_LOST);
    }
    complete(&m,&t,A138_CLK_RESULT_APPLIED);m.registers[A138_CLK_STATUS/4]|=1;
    CHECK(poll(&m,&t,&s)==A138_CLK_PENDING);
}
static void test_poll_failures_and_id_brackets(void) {
    model m;
    initialize(&m);
    a138_clock_ticket t=submitted(&m,A138_CLK_44100);
    for(unsigned failure=1;failure<=11;++failure) {
        complete(&m,&t,A138_CLK_RESULT_APPLIED);m.fail_at=failure;
        a138_clock_status s=sentinel_status(),original=s;
        CHECK(poll(&m,&t,&s)==A138_CLK_IO_ERROR && m.accesses==failure);
        CHECK(memcmp(&s,&original,sizeof(s))==0);
    }
    for(unsigned variant=0;variant<4;++variant) {
        complete(&m,&t,A138_CLK_RESULT_APPLIED);
        if(variant==0)m.registers[A138_CLK_COMMAND_ID/4]=0;
        if(variant==1) {m.mutate_at=11;m.mutate_offset=A138_CLK_COMMAND_ID;m.mutate_value=9;}
        if(variant==2) {m.registers[A138_CLK_RESULT_ID/4]=7;m.mutate_at=10;
            m.mutate_offset=A138_CLK_RESULT_ID;m.mutate_value=8;}
        if(variant==3) {m.mutate_at=10;m.mutate_offset=A138_CLK_RESULT_ID;m.mutate_value=9;}
        a138_clock_status s=sentinel_status(),original=s;
        CHECK(poll(&m,&t,&s)==(variant<2 ? A138_CLK_SUPERSEDED:A138_CLK_PENDING));
        CHECK(memcmp(&s,&original,sizeof(s))==0);
    }
    clear_trace(&m);
    a138_clock_status s=sentinel_status();
    a138_clock_ticket invalid={0,1,48000};
    CHECK(poll(&m,&invalid,&s)==A138_CLK_INVALID && m.accesses==0);
    invalid.command_id=8;invalid.expected_rate_hz=123;
    CHECK(poll(&m,&invalid,&s)==A138_CLK_INVALID && m.accesses==0);
}
int main(void) {
    test_probe_and_admission();
    test_ticket_and_commit_failures();
    test_result_and_actual_snapshot();
    test_poll_failures_and_id_brackets();
    printf("PASS ae350_clock_service_host checks=%u submit_max=9 poll_max=11\n",checks);
    return 0;
}
