#include "Vae350_ble_business_cosim.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <functional>
extern "C" {
#include "ble_business_owner.h"
}
static uint32_t crc(const std::vector<uint8_t>& v) {
    uint32_t c=~0u;for(uint8_t b:v){c^=b;for(int k=0;k<8;k++)c=(c>>1)^((c&1)?0xedb88320u:0);}return ~c;
}
static void put(std::vector<uint8_t>& v,uint32_t n){for(int i=0;i<4;i++)v.push_back(uint8_t(n>>(8*i)));}
static uint32_t word(const std::vector<uint8_t>& v,size_t i){return uint32_t(v.at(i))|(uint32_t(v.at(i+1))<<8)|(uint32_t(v.at(i+2))<<16)|(uint32_t(v.at(i+3))<<24);}
struct Harness {
    VerilatedContext context;
    Vae350_ble_business_cosim dut{&context};
    a138_ble_business_owner owner{};
    struct Bus {Harness *h;uint32_t base;};
    Bus mb{this,0},data{this,0x100};
    uint32_t next_id=1;
    bool service_enabled=true,lose_submit_ack=false,drop_submit=false,lose_complete_ack=false,drop_complete=false,drop_complete_tear=false,completion_dropped=false,inject_observe_tear=false,allow_fault=false,trace=true;
    unsigned paused_pumps=0;
    unsigned checks=0;bool fragment_seen=false;
    Harness() {
        dut.clk=0;dut.resetn=0;dut.owner_resetn=0;dut.enable=1;dut.pcm_run=1;dut.pstrb=15;
        cycle(20);dut.resetn=1;dut.owner_resetn=1;cycle(40);
        a138_business_bus m{&mb,rd,wr};a138_record_bus d{&data,rd,wr};
        a138_ble_business_init(&owner,m,d);
    }
    void cycle(unsigned count=1) {
        for(unsigned k=0;k<count;k++)for(unsigned ns=0;ns<20;ns++) {
            dut.clk=(ns>=10);context.timeInc(1);dut.eval();if(dut.fragment_done)fragment_seen=true;
        }
    }
    void check(bool value,const char *name) {
        checks++;if(!value){std::fprintf(stderr,"FAIL %s time=%llu owner_fault=%u phase=%u state=%u frames=%u\n",name,(unsigned long long)context.time(),owner.fault,owner.phase,dut.record_state,dut.frames);std::fprintf(stderr,"facts flags=%x id=%u seq=%u accepted=%u applied=%u\n",owner.facts.state,owner.facts.object_id,owner.command_sequence,owner.facts.accepted_seq,owner.facts.applied_seq);std::exit(1);}
    }
    bool access(uint32_t address,bool write,uint32_t &value) {
        dut.psel=1;dut.penable=0;dut.pwrite=write;dut.paddr=address;dut.pwdata=value;cycle();
        dut.penable=1;bool done=false,error=false;
        for(unsigned k=0;k<200;k++){dut.eval();bool ready=dut.pready;bool e=dut.pslverr;uint32_t v=dut.prdata;cycle();if(ready){done=true;error=e;value=v;break;}}
        dut.psel=0;dut.penable=0;cycle(2);
        if(!done){check(false,"APB finite completion");}
        return !error;
    }
    static int rd(void *p,uint32_t offset,uint32_t *value) {
        Bus *b=static_cast<Bus*>(p);uint32_t v=0;bool ok=b->h->access(b->base+offset,false,v);
        if(ok && b->base==0 && offset==A138_BM_STATE && b->h->owner.phase==3 && b->h->inject_observe_tear){b->h->inject_observe_tear=false;b->h->dut.enable=0;b->h->cycle(12);}
        if(ok)*value=v;else std::fprintf(stderr,"read error %x value %x\n",b->base+offset,v);return ok;
    }
    static int wr(void *p,uint32_t offset,uint32_t value) {
        Bus *b=static_cast<Bus*>(p);
        if(b->base==0x100 && offset==8 && b->h->drop_submit){b->h->drop_submit=false;b->h->dut.test_time_bias+=1001;return 0;}
        if(b->base==0 && offset==A138_BM_COMMAND && value==A138_BM_COMPLETE && b->h->drop_complete){b->h->drop_complete=false;b->h->dut.test_time_bias+=1001;return 0;}
        if(b->base==0 && offset==A138_BM_COMMAND && value==A138_BM_COMPLETE && b->h->drop_complete_tear){b->h->drop_complete_tear=false;b->h->completion_dropped=true;return 0;}
        bool ok=b->h->access(b->base+offset,true,value);
        if(ok && b->base==0 && offset==A138_BM_COMMAND && value==A138_BM_COMPLETE && b->h->lose_complete_ack){b->h->lose_complete_ack=false;return 0;}
        if(!ok)std::fprintf(stderr,"write error %x value %x\n",b->base+offset,value);
        if(ok && b->base==0x100 && offset==8 && b->h->lose_submit_ack){b->h->lose_submit_ack=false;return 0;}return ok;
    }
    void pump() {
#ifndef GOLDEN
        if(paused_pumps){paused_pumps--;return;}
        if(service_enabled)a138_ble_business_pump(&owner);
#endif
    }
    void until(const std::function<bool()>& predicate,const char *name,unsigned limit=50000) {
        for(unsigned k=0;k<limit;k++) {
            if(predicate()){checks++;return;}
            cycle();if(k%64==0)pump();
            if(owner.fault && !allow_fault)check(false,"C owner stayed operational");
        }
        check(false,name);
    }
    std::vector<uint8_t> command(uint8_t opcode,std::vector<uint8_t> payload={},uint32_t id=0,uint64_t nonce=UINT64_C(0x9abcdef012345678),bool corrupt=false) {
        if(!id)id=next_id++;
        std::vector<uint8_t> request{opcode,0,uint8_t(payload.size()),0};put(request,id);
        put(request,uint32_t(nonce));put(request,uint32_t(nonce>>32));
        request.insert(request.end(),payload.begin(),payload.end());put(request,crc(request));
        if(corrupt)request.back()^=1;
        uint8_t ordinal=0;
        for(size_t offset=0;offset<request.size();offset+=14,ordinal++) {
            size_t n=std::min<size_t>(14,request.size()-offset);
            std::vector<uint8_t> frag{0xb1,0x34,0x12,ordinal,uint8_t((offset==0?1:0)|(offset+n==request.size()?2:0)),uint8_t(n)};
            frag.insert(frag.end(),request.begin()+offset,request.begin()+offset+n);
            for(size_t j=0;j<frag.size();j++){dut.fragment_write=1;dut.fragment_addr=j;dut.fragment_data=frag[j];cycle();}
            dut.fragment_write=0;fragment_seen=false;dut.fragment_length=frag.size();dut.fragment_start=1;cycle();dut.fragment_start=0;
            until([&]{return fragment_seen || completion_dropped || (allow_fault && owner.fault);},"fragment/CPU completion");
            if(completion_dropped || (allow_fault && owner.fault))return {};
            check(dut.fragment_error==0,"ATT fragment error zero");cycle(2);
        }
        if(corrupt){cycle(4000);check(!dut.response_valid,"CRC reject produces no reply");return {};}
        until([&]{return dut.response_valid;},"wire response");
        std::vector<uint8_t> reply;
        for(unsigned i=0;i<dut.response_length;i++){dut.response_addr=i;dut.eval();reply.push_back(dut.response_data);}
        check(reply.size()>=20 && reply[0]==opcode && word(reply,4)==id,"wire identity");
        std::vector<uint8_t> content(reply.begin(),reply.end()-4);
        check(crc(content)==word(reply,reply.size()-4),"wire response CRC");
        if(trace){std::printf("WIRE ");for(uint8_t b:reply)std::printf("%02x",b);std::printf("\n");}
        dut.response_consume=1;cycle();dut.response_consume=0;cycle(2);return reply;
    }
    std::vector<uint8_t> object() {std::vector<uint8_t> p;put(p,0x55667788);put(p,0x11223344);put(p,1);return p;}
    void run() {
        std::vector<uint8_t> p;put(p,1);auto hello=command(1,p);check(hello[1]==0,"HELLO unchanged");cycle(4096);
        #ifndef GOLDEN
        for(int k=0;k<8;k++)pump();check(owner.opened && !owner.fault,"real C OPEN");
#endif
        p.clear();put(p,1);put(p,0);lose_submit_ack=true;lose_complete_ack=true;
        auto start=command(0x20,p);check(start[1]==1 && word(start,16)==1 && word(start,20)==1,"C allocated START task/object");
        auto replay=command(0x20,p,word(start,4));check(replay==start,"exact START replay unchanged");
#ifndef GOLDEN
        check(owner.object_counter==1 && owner.operation_counter==1 && owner.command_sequence==1,"START replay bypasses C allocation and physical submit");
#endif
        until([&]{return dut.frames>=16;},"real physical capture");dut.pcm_run=0;cycle(12);
        auto stop=command(0x21,object());check(stop[1]==1 && word(stop,16)==2,"C STOP task");
        until([&]{return dut.record_state==4;},"native drained READY");pump();
        p.clear();put(p,1);auto task=command(4,p);check(task[1]==0 && task[25]==2,"C START completed after actual frame");
        p.clear();put(p,2);task=command(4,p);check(task[25]==2,"C STOP completed after native drain");
        p.clear();put(p,0);auto info=command(0x22,p);check(info[28]==4 && word(info,36)==16,"immutable object descriptor");
        uint32_t object_crc=word(info,48);std::vector<uint8_t> pcm;for(int k=0;k<16;k++){pcm.push_back(0x11);pcm.push_back(0x11);pcm.push_back(0x22);pcm.push_back(0x22);}
        check(crc(pcm)==object_crc,"CRC of actual DDR PCM");
        p=object();put(p,0);auto open=command(0x30,p);check(open[1]==0 && word(open,16)==1,"C transfer ID allocation");
        p.clear();put(p,1);put(p,0);p.push_back(64);p.push_back(0);p.push_back(0);p.push_back(0);
        auto read=command(0x31,p);check(read[1]==0,"retained download policy read");
        check(dut.transfer_valid && dut.transfer_length==112,"actual transfer block");
        std::vector<uint8_t> block;for(unsigned i=0;i<dut.transfer_length;i++){dut.transfer_addr=i;cycle(2);block.push_back(dut.transfer_data);}
        check(std::vector<uint8_t>(block.begin()+44,block.end()-4)==pcm,"DDR bytes delivered through real wire engine");
        check(word(block,40)==object_crc,"block PCM CRC");
        std::printf("BLOCK ");for(uint8_t b:block)std::printf("%02x",b);std::printf("\n");
        dut.transfer_consume=1;cycle();dut.transfer_consume=0;cycle(2);
        auto read_replay=command(0x31,p,word(read,4));check(read_replay==read,"exact READ replay response");
        check(dut.transfer_valid && dut.transfer_length==112,"READ replay rebuilds data");
        std::vector<uint8_t> replay_block;for(unsigned i=0;i<dut.transfer_length;i++){dut.transfer_addr=i;cycle(2);replay_block.push_back(dut.transfer_data);}
        check(replay_block==block,"READ replay exact PCM block");
#ifndef GOLDEN
        check(owner.command_sequence==4,"READ replay bypasses C primitive descriptor");
#endif
        dut.transfer_consume=1;cycle();dut.transfer_consume=0;cycle(2);
        p.clear();put(p,1);put(p,64);put(p,object_crc);auto ack=command(0x32,p);check(ack[1]==0,"retained ACK policy");
        p.clear();put(p,1);put(p,object_crc);auto close=command(0x33,p);check(close[1]==0,"C close command");
        const uint8_t modes[]={0x36,0x37,0x38,0x39,0x3b,0x3c,0x3d,0x40};
        uint32_t transfer=1;
        for(uint8_t mode:modes){p=object();put(p,0);auto opened=command(mode,p);check(opened[1]==0 && word(opened,16)==++transfer,"all transfer OPEN modes C allocated");
            p.clear();put(p,transfer);auto cancel=command(0x34,p);check(cancel[1]==0,"C transfer CANCEL");}
        p={};auto bad=command(0x20,p);check(bad[1]==0x81,"bad START shape");
        p.assign(17,0);bad=command(0x7f,p);check(bad[1]==0x80,"unknown overlength stays unknown");
        bad=command(0x20,p);check(bad[1]==0x81,"known overlength rejected before C");
        p.clear();put(p,99);bad=command(0x22,p);check(bad[1]==0x88,"wrong object query");
        p.clear();put(p,0);bad=command(0x22,p,0,7);check(bad[1]==0x85,"wrong nonce rejected before C");
#ifndef GOLDEN
        uint32_t sequence=owner.command_sequence;
#endif
        command(0x22,p,0,UINT64_C(0x9abcdef012345678),true);
#ifndef GOLDEN
        check(owner.command_sequence==sequence,"CRC reject bypasses C physical descriptor");
#endif
        auto clear=command(0x23,object());check(clear[1]==0 && dut.object_id==0,"actual raw CLEAR completion");
#ifndef GOLDEN
        check(owner.object_counter==1 && owner.operation_counter==2 && owner.transfer_counter==9,"C sole identity counters");
#endif
        std::printf("PASS real C/APB/parser/raw-DDR owner: %u checks; context bytes=%zu\n",checks,sizeof owner);
    }
#ifndef GOLDEN
    void run_torn_completion() {
        trace=false;std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);for(int k=0;k<8;k++)pump();
        drop_complete_tear=true;p.clear();put(p,1);put(p,0);command(0x20,p);
        check(owner.phase==3 && !owner.fault,"uncertain COMPLETE enters exact-key observation");
        inject_observe_tear=true;pump();check(owner.phase==3 && !owner.fault,"actual APB state tear stays OBSERVE");
        check(owner.command_sequence==1 && owner.operation_counter==1 && owner.object_counter==1,"torn observation cannot redispatch accepted business");
        pump();check(owner.phase==0 && !owner.fault,"stable local result resolves torn observation");
        for(unsigned k=0;k<30;k++)pump();check(owner.command_sequence==1,"same claimed ticket never resubmits after torn observe");
        std::printf("PASS actual APB torn COMPLETE observation: %u checks\n",checks);
    }
    void run_uncertain_completion() {
        trace=false;std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);for(int k=0;k<8;k++)pump();
        drop_complete=true;allow_fault=true;p.clear();put(p,1);put(p,0);command(0x20,p);
        check(owner.fault==A138_OWNER_COMPLETE_UNOBSERVED,"uncommitted COMPLETE reaches finite exact-key observation fence");
        check(owner.command_sequence==1 && owner.facts.accepted_seq==1 && owner.object_counter==1 && owner.operation_counter==1,"uncommitted COMPLETE preserves accepted physical task and IDs without replay");
        uint32_t before=dut.frames;cycle(5000);check(dut.frames>before,"COMPLETE observation loss cannot stop capture schedule");
        dut.seal_hold=1;dut.seal_request=1;cycle();dut.seal_request=0;
        until([&]{return dut.seal_done;},"hardware seals after CPU COMPLETE observation fault");
        check(dut.record_state==4 && dut.object_id==1,"COMPLETE observation fault preserves sealable object");
        std::printf("PASS uncommitted uncertain completion: %u checks\n",checks);
    }
    void run_zero_frame() {
        trace=false;std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);for(int k=0;k<8;k++)pump();
        dut.pcm_run=0;p.clear();put(p,1);put(p,0);auto started=command(0x20,p);
        check(started[1]==1 && dut.record_state==1 && dut.frames==0,"START pending after actual raw accept before first PCM");
        p.clear();put(p,1);auto task=command(4,p);check(task[25]==1,"START task stays pending before real frame");
        service_enabled=false;dut.seal_hold=1;dut.seal_request=1;cycle();dut.seal_request=0;
        until([&]{return dut.seal_done;},"zero-frame seal native empty prefix");check(dut.record_state==4 && dut.frames==0,"zero-frame object retains actual identity");
        service_enabled=true;pump();p.clear();put(p,1);task=command(4,p);
        check(task[25]==3 && task[26]==0x83,"zero-frame START fails after physical terminal seal");
        std::printf("PASS zero-frame START/seal: %u checks\n",checks);
    }
    void run_crc_phase(unsigned phase) {
        trace=false;std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);for(int k=0;k<8;k++)pump();
        p.clear();put(p,1);put(p,0);command(0x20,p);service_enabled=false;
        until([&]{return dut.capture_phase==phase;},"real CRC byte phase");
        dut.seal_hold=1;dut.seal_request=1;cycle();dut.seal_request=0;
        until([&]{return dut.seal_done;},"seal waits complete stereo CRC and native tail");
        check(dut.record_state==4 && dut.frames>0 && !dut.seal_failed,"CRC-phase seal READY");
        std::vector<uint8_t> pcm;for(unsigned k=0;k<dut.frames;k++){pcm.push_back(0x11);pcm.push_back(0x11);pcm.push_back(0x22);pcm.push_back(0x22);}
        uint32_t value=0;check(access(0x134,false,value) && value==crc(pcm),"CRC includes all and only sealed frames");
        check(access(0x130,false,value) && value==dut.frames,"seal native committed count equals complete prefix");
        service_enabled=true;pump();check(!owner.fault && owner.tasks[0].state==2,"slow C observes real first frame after CRC seal");
        std::printf("PASS CRC phase %u: %u checks\n",phase,checks);
    }
    void run_uncertain() {
        trace=false;std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);for(int k=0;k<8;k++)pump();
        drop_submit=true;allow_fault=true;p.clear();put(p,1);put(p,0);command(0x20,p);
        check(owner.fault==A138_OWNER_SUBMIT_UNOBSERVED,"uncommitted uncertain descriptor reaches finite observation fence");
        check(owner.command_sequence==1 && owner.facts.accepted_seq==0 && owner.facts.applied_seq==0,"uncommitted uncertain seq never blindly retried");
        for(int k=0;k<100;k++)pump();check(dut.record_state==0 && dut.object_id==0 && owner.object_counter==0,"uncommitted uncertain fence preserves no-object state");
        std::printf("PASS uncommitted uncertain descriptor: %u checks\n",checks);
    }
    void run_edges() {
        trace=false;std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);for(int k=0;k<8;k++)pump();
        uint32_t bad=0x100;check(!access(0x160,true,bad),"APB opcode reserved bits rejected");bad=17;check(!access(0x164,true,bad),"APB length range rejected");
        for(uint32_t i=1;i<=8;i++) {
            p.clear();put(p,1);put(p,1);auto started=command(0x20,p);check(started[1]==1 && word(started,16)==i,"eight C task slots filled");
            until([&]{return dut.record_state==4;},"capacity-one actual READY");pump();
            p.clear();put(p,i);auto task=command(4,p);check(task[25]==2,"capacity-one START task succeeds");
            check(owner.tasks[(i-1)&7].time_ms==owner.facts.first_ms,"actual first-frame timestamp retained");
            p=object();p[8]=uint8_t(i);auto cleared=command(0x23,p);check(cleared[1]==0,"capacity-one CLEAR");
        }
        p.clear();put(p,1);put(p,1);auto full=command(0x20,p);check(full[1]==0x82 && owner.operation_counter==8 && owner.object_counter==8,"full task retention rejects without ID reuse");
        dut.test_time_bias=60001;for(int k=0;k<3;k++)pump();
        paused_pumps=8;auto started=command(0x20,p);check(started[1]==1 && word(started,16)==9,"expired slot reused with next monotonic ID after slow CPU");
        until([&]{return dut.record_state==4;},"ninth actual READY");pump();p=object();p[8]=9;command(0x23,p);
        owner.object_counter=UINT32_MAX;p.clear();put(p,1);put(p,1);auto exhausted=command(0x20,p);check(exhausted[1]==0x82 && dut.object_id==0,"object ID exhaustion fails closed");owner.object_counter=9;
        owner.operation_counter=UINT32_MAX;exhausted=command(0x20,p);check(exhausted[1]==0x82 && dut.object_id==0,"operation ID exhaustion fails closed");owner.operation_counter=9;
        // Retire the remaining seven slots by advancing only the documented elapsed-ms input.
        dut.test_time_bias=120002;for(int k=0;k<3;k++)pump();
        p.clear();put(p,1);put(p,0);started=command(0x20,p);check(started[1]==1,"autonomous-seal object START");
        until([&]{return dut.frames>=3;},"PCM continues before CPU pause");service_enabled=false;
        uint32_t before=dut.frames;cycle(5000);check(dut.frames>before,"capture schedule advances while CPU service paused");
        dut.seal_hold=1;dut.seal_request=1;cycle();dut.seal_request=0;
        until([&]{return dut.seal_done;},"actual autonomous media seal while CPU off");check(dut.record_state==4 && !dut.seal_failed,"autonomous seal is native READY");
        service_enabled=true;pump();check(!owner.fault,"slow CPU catches physical seal");
        owner.transfer_counter=UINT32_MAX;p=object();p[8]=10;put(p,0);auto x=command(0x30,p);check(x[1]==0x82,"transfer ID exhaustion fails closed");
        dut.enable=0;cycle(30);dut.enable=1;cycle(30);next_id=1;p.clear();put(p,1);command(1,p);
        for(int k=0;k<8;k++)pump();p.clear();put(p,0);auto retained=command(0x22,p);
        check(retained[1]==0 && word(retained,24)==10 && owner.object_counter==10,"reconnect preserves physical object and C identity sequence");
        dut.owner_resetn=0;cycle(20);dut.owner_resetn=1;cycle(40);pump();
        check(owner.fault==A138_OWNER_OBSERVER_LOST,"CPU observer reset fences C owner");
        uint32_t flags=0;check(access(0x10c,false,flags) && (flags&(1u<<9)),"physical service observer loss sticky");
        check(dut.record_state==4 && dut.object_id==10,"CPU observer reset preserves actual sealed object");
        std::printf("PASS additional real C boundaries: %u checks\n",checks);
    }
#endif
};
int main(int argc,char **argv){Verilated::commandArgs(argc,argv);Harness h;h.run();
#ifndef GOLDEN
Harness edges;edges.run_edges();Harness uncertain;uncertain.run_uncertain();Harness completion;completion.run_uncertain_completion();Harness torn;torn.run_torn_completion();Harness empty;empty.run_zero_frame();
for(unsigned phase=2;phase<=5;phase++){Harness crcphase;crcphase.run_crc_phase(phase);}
#endif
}
