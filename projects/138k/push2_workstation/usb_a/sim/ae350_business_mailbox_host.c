#include "business_mailbox.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {
    uint32_t registers[64],calls,fail_at,mutate_at,commands,change_at,change_word;
    int change_history;
    int fail_after_commit;
} model;
static model m;
static const a138_business_key key={UINT64_C(0x1122334455667788),7,11,42};
static void putkey(uint32_t offset,const a138_business_key *k) {
    uint32_t values[5]={k->ticket,k->owner,k->session,(uint32_t)k->boot_id,(uint32_t)(k->boot_id>>32)};
    for(uint32_t i=0;i<5;i++)m.registers[offset/4+i]=values[i];
}
static void reset_model(void) {
    memset(&m,0,sizeof m);
    m.registers[A138_BM_ID/4]=UINT32_C(0x424d4201);m.registers[A138_BM_CAPS/4]=UINT32_C(0x00401001);
    m.registers[A138_BM_STATE/4]=256|A138_BM_QUEUED;m.registers[A138_BM_OWNER/4]=key.owner;
    m.registers[A138_BM_SESSION/4]=key.session;m.registers[A138_BM_BOOT_LOW/4]=(uint32_t)key.boot_id;
    m.registers[A138_BM_BOOT_HIGH/4]=(uint32_t)(key.boot_id>>32);putkey(A138_BM_TICKET,&key);
    m.registers[A138_BM_REQUEST_ID/4]=123;m.registers[A138_BM_NONCE_LOW/4]=0xabcdef;
    m.registers[A138_BM_REQUEST_META/4]=0x00200003;m.registers[A138_BM_REQUEST_DATA0/4]=0x00332211;
    putkey(A138_BM_LAST_TICKET,&key);m.registers[A138_BM_LAST_META/4]=A138_BM_PENDING;
    m.registers[A138_BM_LAST_OPERATION/4]=77;
}
static int rd(void *context,uint32_t offset,uint32_t *out) {
    model *p=context;assert(offset%4==0 && offset<256);p->calls++;
    if(p->calls==p->mutate_at) { p->registers[A138_BM_TICKET/4]++;p->registers[A138_BM_OWNER/4]++; }
    if(p->calls==p->change_at) {
        uint32_t base=p->change_history ? A138_BM_LAST_TICKET : A138_BM_TICKET;
        p->registers[base/4+p->change_word]++;
    }
    if(p->calls==p->fail_at)return 0;
    *out=p->registers[offset/4];return 1;
}
static int wr(void *context,uint32_t offset,uint32_t value) {
    model *p=context;assert(offset%4==0 && offset<256);p->calls++;
    int failed=p->calls==p->fail_at;
    if(failed && !(p->fail_after_commit && offset==A138_BM_COMMAND))return 0;
    p->registers[offset/4]=value;
    if(offset==A138_BM_COMMAND) {
        p->commands++;
        if(value==A138_BM_CLAIM)p->registers[A138_BM_STATE/4]=256|A138_BM_CLAIMED;
        if(value==A138_BM_COMPLETE) {
            p->registers[A138_BM_STATE/4]=256|A138_BM_RESULT;putkey(A138_BM_LAST_TICKET,&key);
            p->registers[A138_BM_LAST_META/4]=p->registers[A138_BM_RESULT_META/4];
            p->registers[A138_BM_LAST_OPERATION/4]=p->registers[A138_BM_RESULT_OPERATION/4];
        }
    }
    return !failed;
}
static const a138_business_bus bus={&m,rd,wr};
typedef union { a138_business_key context;a138_business_request request;a138_business_observation observation; } output;
static int read_api(unsigned which,output *out) {
    if(which==0)return a138_business_context(&bus,&out->context);
    if(which==1)return a138_business_read_request(&bus,&out->request);
    return a138_business_observe(&bus,&key,&out->observation);
}
static void all_read_failures(void) {
    for(unsigned which=0;which<4;which++) {
        output out,before;reset_model();if(which==3)m.registers[A138_BM_STATE/4]=256;
        assert(read_api(which,&out)==A138_BM_OK);uint32_t count=m.calls;
        assert(count==(which==0 ? 8u : which==1 ? 21u : which==2 ? 15u : 28u));
        for(uint32_t at=1;at<=count;at++) {
            reset_model();if(which==3)m.registers[A138_BM_STATE/4]=256;
            m.fail_at=at;memset(&out,0xa5,sizeof out);before=out;
            assert(read_api(which,&out)==A138_BM_IO);assert(m.calls==at);
            assert(memcmp(&out,&before,sizeof out)==0);
        }
    }
}
static int key_api(unsigned which,const a138_business_key *k) {
    if(which==0)return a138_business_open(&bus,k);
    if(which==1)return a138_business_claim(&bus,k);
    if(which==2)return a138_business_abandon(&bus,k);
    return a138_business_close(&bus,k);
}
static void command_failures(void) {
    for(unsigned which=0;which<4;which++)for(uint32_t at=1;at<=6;at++) {
        reset_model();m.fail_at=at;m.fail_after_commit=1;
        a138_business_key k=key;if(which==0 || which==3)k.ticket=0;
        assert(key_api(which,&k)==(at==6 ? A138_BM_COMMIT_UNCERTAIN : A138_BM_IO));
        assert(m.calls==at && m.commands==(at==6));
        if(which==1 && at==6) {
            a138_business_observation out;
            m.fail_at=0;assert(a138_business_observe(&bus,&key,&out)==A138_BM_OK);
            assert(out.state==A138_BM_CLAIMED && out.phase==0 && out.operation_id==0);
        }
    }
    uint8_t bytes[64];for(uint32_t i=0;i<64;i++)bytes[i]=(uint8_t)(i*17+3);
    const a138_business_completion result={A138_BM_PENDING,1,77,64,bytes};
    for(uint32_t at=1;at<=24;at++) {
        reset_model();m.fail_at=at;m.fail_after_commit=1;
        assert(a138_business_complete(&bus,&key,&result)==(at==24 ? A138_BM_COMMIT_UNCERTAIN : A138_BM_IO));
        assert(m.calls==at && m.commands==(at==24));
        if(at==24) {
            a138_business_observation out;m.fail_at=0;
            assert(a138_business_observe(&bus,&key,&out)==A138_BM_OK);
            assert(out.state==A138_BM_RESULT && out.phase==A138_BM_PENDING && out.operation_id==77);
            m.registers[A138_BM_STATE/4]=256;
            assert(a138_business_observe(&bus,&key,&out)==A138_BM_OK);
            assert(out.state==A138_BM_PUBLISHED && out.phase==A138_BM_PENDING && out.operation_id==77);
            assert(m.commands==1); /* No retry or second business allocation. */
        }
    }
    reset_model();a138_business_completion short_result={A138_BM_APPLIED,0,0,5,bytes};
    assert(a138_business_complete(&bus,&key,&short_result)==A138_BM_OK);assert(m.calls==24 && m.commands==1);
    assert(m.registers[A138_BM_RESULT_DATA0/4]==UINT32_C(0x36251403));
    assert(m.registers[A138_BM_RESULT_DATA0/4+1]==bytes[4]);
    for(uint32_t i=2;i<16;i++)assert(m.registers[A138_BM_RESULT_DATA0/4+i]==0);
}
static void invalid_and_changed_reads(void) {
    uint8_t bytes[1]={0};a138_business_completion result={A138_BM_PENDING,0,1,1,bytes};
    for(unsigned which=0;which<6;which++) {
        a138_business_completion bad=result;reset_model();
        if(which==0)bad.phase=4;if(which==1)bad.operation_id=0;if(which==2)bad.length=65;
        if(which==3)bad.status=256;if(which==4)bad.payload=NULL;if(which==5)bad.phase=0;
        assert(a138_business_complete(&bus,&key,&bad)==A138_BM_INVALID);assert(m.calls==0);
    }
    for(unsigned which=0;which<3;which++) {
        output out,before;reset_model();m.mutate_at=which==0 ? 5 : which==1 ? 15 : 9;
        memset(&out,0x5a,sizeof out);before=out;assert(read_api(which,&out)==A138_BM_STALE);
        assert(memcmp(&out,&before,sizeof out)==0);
    }
    output out,before;reset_model();m.registers[A138_BM_STATE/4]=256;
    memset(&out,0x5a,sizeof out);before=out;assert(a138_business_read_request(&bus,&out.request)==A138_BM_NONE);
    assert(memcmp(&out,&before,sizeof out)==0);
    reset_model();m.registers[A138_BM_REQUEST_META/4]=0x00200011;
    assert(a138_business_read_request(&bus,&out.request)==A138_BM_INVALID);
    assert(memcmp(&out,&before,sizeof out)==0);
    reset_model();m.registers[A138_BM_STATE/4]=256;m.registers[A138_BM_LAST_TICKET/4]++;
    assert(a138_business_observe(&bus,&key,&out.observation)==A138_BM_NONE);
    assert(memcmp(&out,&before,sizeof out)==0);
    reset_model();m.registers[A138_BM_RESULT_META/4]=(A138_BM_OWNER_RESET<<24)|A138_BM_UNCERTAIN_PHASE;
    m.registers[A138_BM_RESULT_OPERATION/4]=88;m.registers[A138_BM_STATE/4]=256|A138_BM_RESULT;
    assert(a138_business_observe(&bus,&key,&out.observation)==A138_BM_OK);
    assert(out.observation.phase==A138_BM_UNCERTAIN_PHASE && out.observation.reason==A138_BM_OWNER_RESET &&
           out.observation.operation_id==88); /* Observer loss does not claim task cancellation. */
}
static void complete_key_snapshot_checks(void) {
    // A ticket and owner may repeat after common reset under a fresh boot ID.
    // Every component of the complete key must be rechecked, including history.
    for(unsigned branch=0;branch<3;branch++)for(uint32_t word=0;word<5;word++) {
        output out,before;reset_model();memset(&out,0xa5,sizeof out);before=out;
        if(branch==2)m.registers[A138_BM_STATE/4]=256;
        m.change_word=word;m.change_history=branch==2;
        m.change_at=branch==0 ? 8u : branch==1 ? 8u : 22u;
        int result=branch==0 ? a138_business_read_request(&bus,&out.request) :
                             a138_business_observe(&bus,&key,&out.observation);
        assert(result==A138_BM_STALE);assert(memcmp(&out,&before,sizeof out)==0);
    }
}
int main(void) {
    reset_model();assert(a138_business_probe(&bus)==A138_BM_OK && m.calls==2);
    all_read_failures();command_failures();invalid_and_changed_reads();complete_key_snapshot_checks();
    uint32_t mmio[64]={0};mmio[0]=UINT32_C(0x424d4201);mmio[1]=UINT32_C(0x00401001);
    a138_business_bus direct=a138_business_mmio_bus((uintptr_t)mmio);assert(a138_business_probe(&direct)==A138_BM_OK);
    puts("PASS business mailbox C API: bounded reads/writes, every callback failure, uncertain commit and preserved outputs");
    return 0;
}
