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
    bool service_enabled=true,lose_submit_ack=false,drop_submit=false,lose_complete_ack=false,drop_complete=false,drop_complete_tear=false,completion_dropped=false,inject_observe_tear=false,disconnect_read_submit=false,allow_fault=false,trace=true;
    unsigned paused_pumps=0;
    unsigned checks=0;bool fragment_seen=false;
    Harness() {
        dut.clk=0;dut.resetn=0;dut.owner_resetn=0;dut.enable=1;dut.pcm_run=1;dut.pstrb=15;dut.test_att_limit=247;
        cycle(20);dut.resetn=1;dut.owner_resetn=1;cycle(40);
        a138_business_bus m{&mb,rd,wr};a138_record_bus d{&data,rd,wr};
        a138_ble_business_init(&owner,m,d);
    }
    void cycle(unsigned count=1) {
        for(unsigned k=0;k<count;k++)for(unsigned ns=0;ns<20;ns++) {
            dut.clk=(ns>=10);context.timeInc(1000);dut.eval();if(dut.fragment_done)fragment_seen=true;
        }
    }
    void check(bool value,const char *name) {
        checks++;if(!value){std::fprintf(stderr,"FAIL %s time=%llu owner_fault=%u phase=%u state=%u frames=%u\n",name,(unsigned long long)context.time(),owner.fault,owner.phase,dut.record_state,dut.frames);std::fprintf(stderr,"engine phase=%u codec=%u fetch=%x\n",dut.engine_phase,dut.codec_phase,dut.fetch_debug);std::fprintf(stderr,"facts flags=%x id=%u seq=%u accepted=%u applied=%u\n",owner.facts.state,owner.facts.object_id,owner.command_sequence,owner.facts.accepted_seq,owner.facts.applied_seq);std::exit(1);}
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
        if(b->base==0x100 && offset==8 && b->h->disconnect_read_submit) {
            b->h->disconnect_read_submit=false;b->h->dut.enable=0;b->h->cycle(4);
            bool ok=b->h->access(b->base+offset,true,value);b->h->completion_dropped=true;return ok;
        }
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
    void until(const std::function<bool()>& predicate,const char *name,unsigned limit=500000) {
        for(unsigned k=0;k<limit;k++) {
            if(predicate()){checks++;return;}
            cycle();if(k%64==0)pump();
            if(owner.fault && !allow_fault)check(false,"C owner stayed operational");
        }
        check(false,name);
    }
    std::vector<uint8_t> command(uint8_t opcode,std::vector<uint8_t> payload={},uint32_t id=0,uint64_t nonce=UINT64_C(0x9abcdef012345678),bool corrupt=false,unsigned expected_fragment_error=0) {
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
            if(expected_fragment_error){check(dut.fragment_error==expected_fragment_error,"original parser retains bounded DATA backpressure");return {};}
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
        auto read=command(0x31,p);check(read[1]==0,"C validated download read");
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
        check(owner.command_sequence==4,"READ replay validated by C and rebuilds via fresh physical descriptor");
#endif
        dut.transfer_consume=1;cycle();dut.transfer_consume=0;cycle(2);
        p.clear();put(p,1);put(p,64);put(p,object_crc);auto ack=command(0x32,p);check(ack[1]==0,"C ACK policy");
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
        dut.pcm_run=1;p.clear();put(p,1);put(p,1);check(command(0x20,p)[1]==1,"new object after actual CLEAR");
        until([&]{return dut.record_state==4;},"replacement actual object READY");
#ifndef GOLDEN
        uint32_t sequence_before_stale=owner.command_sequence;
#endif
        auto stale_replay=command(0x31,read_payload(1,0,64),word(read,4));check(stale_replay[1]==0x88,"cached READ cannot address a replacement object");
#ifndef GOLDEN
        check(owner.command_sequence==sequence_before_stale,"C rejects stale replay identity before any physical primitive");
#endif
        std::printf("PASS real C/APB/parser/raw-DDR owner: %u checks; context bytes=%zu\n",checks,sizeof owner);
    }
    std::vector<uint8_t> read_payload(uint32_t tid,uint32_t offset,unsigned length,uint32_t previous_crc=0,bool combined=false) {
        std::vector<uint8_t> p;put(p,tid);put(p,offset);put(p,length);if(combined)put(p,previous_crc);return p;
    }
    std::vector<uint8_t> transfer_block(unsigned codec_max=0) {
        check(dut.transfer_valid,"real physical DATA available");
        std::vector<uint8_t> block;for(unsigned i=0;i<dut.transfer_length;i++){dut.transfer_addr=i;cycle(2);block.push_back(dut.transfer_data);}
        check(block.size()>=48 && block[0]==0xd0,"DATA frame header");
        std::vector<uint8_t> message(block.begin(),block.end()-4);check(crc(message)==word(block,block.size()-4),"DATA complete wire CRC");
        check(block[38]<=codec_max && block[39]==0,"DATA codec allowed by exact READ opcode");
        if(trace){std::printf("BLOCK ");for(auto b:block)std::printf("%02x",b);std::printf("\n");}
        dut.transfer_consume=1;cycle();dut.transfer_consume=0;cycle(2);return block;
    }
#ifdef A138_SINGLE_BLE_RECORDING
    void run_local_recording() {
        trace=false;dut.enable=0;dut.pcm_run=0;cycle(64);for(int k=0;k<8;k++)pump();
        check(owner.bound && !owner.fault && !owner.opened,"sole owner binds without GATT session");
        check(a138_ble_record_local_submit(&owner,0x20,0)==1,"CPU START queues same owner");
        check(a138_ble_record_local_submit(&owner,0x20,0)==0,"CPU cannot overwrite queued request");
        a138_ble_local_record_result r{};
        for(int k=0;k<12;k++){pump();cycle(64);}
        check(a138_ble_record_local_poll(&owner,&r) && r.phase==A138_LOCAL_WAIT && !dut.frames,"CPU START cannot apply before a real complete frame");
        dut.pcm_run=1;
        until([&]{return a138_ble_record_local_poll(&owner,&r) && r.phase==A138_LOCAL_DONE;},"CPU START actual first-frame result");
        check(r.status==0 && r.object_id==1 && r.operation_id==1 && dut.frames>0,"CPU START applies after actual complete PCM");
        until([&]{return dut.frames>=8;},"CPU object captures without GATT");dut.pcm_run=0;cycle(12);pump();
        check(a138_ble_record_local_submit(&owner,0x21,0)==1,"CPU STOP queues same object");
        until([&]{return a138_ble_record_local_poll(&owner,&r) && r.token==2 && r.phase==A138_LOCAL_DONE;},"CPU STOP native committed READY");
        check(r.status==0 && r.object_id==1 && dut.record_state==4 && r.frames==r.committed,"CPU STOP cannot succeed before native drain");
        uint32_t frames=r.frames,record_crc=r.crc;
        dut.enable=1;cycle(64);std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);
        p.clear();put(p,0);auto info=command(0x22,p);
        check(info[1]==0 && word(info,24)==1 && info[28]==4 && word(info,36)==frames && word(info,48)==record_crc,"BLE GET sees CPU-created exact object and CRC");
        p=object();put(p,0);auto opened=command(0x30,p);check(opened[1]==0,"BLE opens CPU-created object");
        auto read=command(0x31,read_payload(1,0,frames*4));check(read[1]==0,"BLE downloads CPU-created object");
        auto block=transfer_block();std::vector<uint8_t> pcm(block.begin()+44,block.end()-4);
        check(pcm.size()==frames*4 && crc(pcm)==record_crc,"shared DDR bytes match actual recording CRC");
        p.clear();put(p,1);command(0x34,p);
        dut.enable=0;cycle(64);pump();
        check(a138_ble_record_local_submit(&owner,0x23,0)==1,"CPU CLEAR queues shared immutable object");
        until([&]{return a138_ble_record_local_poll(&owner,&r) && r.token==3 && r.phase==A138_LOCAL_DONE;},"CPU actual raw CLEAR");
        check(r.status==0 && r.object_id==1 && r.frames==frames && r.crc==record_crc && dut.object_id==0 && dut.record_state==0,"CPU CLEAR retires actual BLE object with immutable result");
        check(owner.object_counter==1 && owner.operation_counter==2 && owner.command_sequence==4,"CPU and BLE share exact ID/descriptor counters");
        check(a138_ble_record_local_submit(&owner,0x20,1)==1,"next CPU object queues after CLEAR");
        dut.pcm_run=1;
        until([&]{return dut.record_state==4;},"next actual object seals capacity");pump();
        check(dut.object_id==2 && owner.object_counter==2,"CPU replacement keeps monotonic BLE object identity");
        std::printf("PASS sole CPU/BLE recording object: %u checks\n",checks);
    }
#endif
    void run_download() {
        std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);
#ifndef GOLDEN
        for(int k=0;k<8;k++)pump();
#endif
        p.clear();put(p,1);put(p,1024);auto started=command(0x20,p);check(started[1]==1,"download fixture real object START");
        until([&]{return dut.record_state==4;},"1024 actual frames and native drain",1500000);pump();
        check(dut.frames==1024,"download object exact real capacity");
        p.clear();put(p,0);auto info=command(0x22,p);uint32_t object_crc=word(info,48);
        std::vector<uint8_t> pcm;for(unsigned k=0;k<1024;k++){pcm.push_back(0x11);pcm.push_back(0x11);pcm.push_back(0x22);pcm.push_back(0x22);}
        check(crc(pcm)==object_crc,"download immutable PCM CRC");
        p=object();put(p,0);auto opened=command(0x30,p);uint32_t tid=word(opened,16);check(opened[1]==0 && tid==1,"narrow OPEN starts C lease");
        auto bad=command(0x31,read_payload(tid,0,260));check(bad[1]==0x89,"narrow mode limit enforced by C");
        bad=command(0x31,read_payload(tid+1,0,64));check(bad[1]==0x8d,"READ transfer identity enforced");
        bad=command(0x31,read_payload(tid,4,64));check(bad[1]==0x89,"READ uses confirmed offset");
        p=read_payload(tid,0,64);p[10]=1;bad=command(0x31,p);check(bad[1]==0x81,"READ reserved bits rejected");
        bad=command(0x3e,read_payload(tid,0,64));check(bad[1]==0x8d,"lossless READ requires promised OPEN");
        auto first=command(0x31,read_payload(tid,0,256));auto first_block=transfer_block();uint32_t first_crc=word(first_block,40);
        check(word(first_block,32)==0 && first_block.size()==304,"narrow maximum real block");
        bad=command(0x31,read_payload(tid,0,64));check(bad[1]==0x82,"window one cannot skip pending ACK");
        p.clear();put(p,tid);put(p,256);put(p,first_crc^1);bad=command(0x32,p);check(bad[1]==0x8d,"ACK wrong CRC does not advance");
        p.clear();put(p,tid);put(p,252);put(p,first_crc);bad=command(0x32,p);check(bad[1]==0x8d,"ACK wrong next offset does not advance");
        lose_complete_ack=true;p.clear();put(p,tid);put(p,256);put(p,first_crc);auto ack=command(0x32,p);check(ack[1]==0,"C ACK commits real physical block CRC");
        auto duplicate=command(0x32,p);check(duplicate[1]==0,"fresh request duplicate ACK accepted idempotently");
        p.clear();put(p,tid);put(p,object_crc);bad=command(0x33,p);check(bad[1]==0x8d,"CLOSE before complete object rejected");
        auto read=command(0x31,read_payload(tid,256,64));
        bad=command(0x35,read_payload(tid,320,64,0,true),0,UINT64_C(0x9abcdef012345678),false,0x11);check(bad.empty(),"parser DATA backpressure prevents unconsumed-frame overwrite before C");
        auto block=transfer_block();uint32_t block_crc=word(block,40);
        bad=command(0x35,read_payload(tid,320,64,block_crc^1,true));check(bad[1]==0x8d,"combined ACK CRC checked before either mutation");
        bad=command(0x35,read_payload(tid,320,0,block_crc,true));check(bad[1]==0x89,"combined invalid next range cannot commit prior ACK");
#ifndef GOLDEN
        check(owner.transfer.offset==256 && owner.transfer.pending && owner.transfer.pending_offset==256,"failed combined request leaves C cursor and prior pending block intact");
#endif
        lose_submit_ack=true;lose_complete_ack=true;p=read_payload(tid,320,64,block_crc,true);auto combined=command(0x35,p);check(combined[1]==0,"combined ACK plus next READ accepted atomically");
        auto combined_block=transfer_block();uint32_t combined_crc=word(combined_block,40);
        auto replay=command(0x35,p,word(combined,4));check(replay==combined,"combined exact replay keeps cached response");
        check(transfer_block()==combined_block,"combined replay rebuilds exact physical frame");
        replay=command(0x31,read_payload(tid,0,256),word(first,4));check(replay==first,"older parser cache READ replay enters C with original object");
        check(transfer_block()==first_block,"older READ rebuild byte identical");
#ifndef GOLDEN
        check(owner.transfer.offset==320 && owner.transfer.pending_offset==320 && owner.transfer.pending_length==64,"replayed reads cannot roll back confirmed or pending C cursor");
#endif
        p.clear();put(p,tid);put(p,384);put(p,combined_crc);check(command(0x32,p)[1]==0,"ACK after old replay still confirms newest pending block");
        p.clear();put(p,tid);check(command(0x34,p)[1]==0,"CANCEL retires C policy lease");
        p=object();put(p,384);opened=command(0x36,p);tid=word(opened,16);check(tid==2,"resume OPEN allocates new monotonic transfer ID");
        check(command(0x31,read_payload(tid,384,460))[1]==0,"resume reads exact explicit confirmed offset");block=transfer_block();
        check(word(block,32)==384 && block.size()==508,"wide maximum block at resume offset");
        p.clear();put(p,tid);check(command(0x34,p)[1]==0,"resume CANCEL");
        p=object();put(p,4096);opened=command(0x30,p);tid=word(opened,16);p.clear();put(p,tid);put(p,object_crc);check(command(0x33,p)[1]==0,"EOF resume permits verified CLOSE without data");
        const uint8_t modes[]={0x37,0x38,0x39,0x3b,0x3c,0x3d,0x40};
        for(uint8_t mode:modes) {
            dut.test_att_limit=mode==0x3c ? 20:247;
            p=object();put(p,0);opened=command(mode,p);tid=word(opened,16);check(opened[1]==0,"each download transport mode opens");
            unsigned length=mode==0x3b ? 972:mode==0x3c ? 976:mode>=0x3d ? 4096:460;
            unsigned limit=mode==0x3b ? 972:mode==0x3c ? 976:mode>=0x3d ? 8112:460;
            check((word(opened,32)&65535u)==limit,"OPEN returns actual C-negotiated PCM limit");
            if(mode==0x3c)check(command(0x31,read_payload(tid,0,980))[1]==0x89,"extended limit uses original negotiated ATT budget");
            if(mode==0x3d)check(command(0x41,read_payload(tid,0,64))[1]==0x8d,"second-order requires explicit OPEN40");
            uint8_t rop=mode==0x40 ? 0x41:mode==0x3d ? 0x3e:0x31;
            p=read_payload(tid,0,length);read=command(rop,p);check(read[1]==0,"all mode READs complete real fetch and codec");
            check(dut.transfer_compact && dut.transfer_bulk==(mode!=0x37) && dut.transfer_direct==(mode==0x39 || mode>=0x3b),"C borrowed descriptor drives actual transport flags");
            block=transfer_block(mode==0x40?11:mode==0x3d?10:0);
            check(word(block,16)==tid && word(block,32)==0 && (word(block,36)&65535u)==length,"DATA borrowed IDs and raw PCM length");
            if(mode==0x40) {
                p.clear();put(p,tid);check(command(0x34,p)[1]==0,"close second-order session for downgrade");
                p=object();put(p,0);auto downgrade=command(0x36,p);uint32_t new_tid=word(downgrade,16);
                check(command(0x41,read_payload(tid,0,length),word(read,4))[1]==0x8d,"cached second replay rejects downgraded active mode");
                p.clear();put(p,new_tid);command(0x34,p);p=object();put(p,0);auto restore=command(0x40,p);new_tid=word(restore,16);
                replay=command(0x41,read_payload(tid,0,length),word(read,4));check(replay==read,"explicit reopen40 restores cached second replay");
                check(transfer_block(11)==block,"restored replay keeps original transfer identity and encoding");
#ifndef GOLDEN
                check(owner.transfer.id==new_tid && owner.transfer.offset==0 && !owner.transfer.pending,"replay of old transfer cannot create pending state in new C lease");
#endif
                tid=new_tid;
                check(command(0x31,read_payload(tid,0,64))[1]==0,"RAW READ remains RAW within OPEN40");block=transfer_block();
            }
            p.clear();put(p,tid);check(command(0x34,p)[1]==0,"all mode CANCELs complete without physical-policy state");
        }
        for(uint8_t mode:{uint8_t(0x3d),uint8_t(0x40)}) {
            p=object();put(p,0);opened=command(mode,p);tid=word(opened,16);
            uint8_t r=mode==0x40?0x41:0x3e,c=mode==0x40?0x42:0x3f;
            check(command(r,read_payload(tid,0,64))[1]==0,"lossless initial block for combined vector");block=transfer_block(mode==0x40?11:10);
            check(command(c,read_payload(tid,64,64,word(block,40),true))[1]==0,"lossless combined ACK/read is C managed");block=transfer_block(mode==0x40?11:10);
            p.clear();put(p,tid);command(0x34,p);
        }
        p=object();put(p,0);opened=command(0x30,p);tid=word(opened,16);
        p=read_payload(tid,0,64);read=command(0x31,p);block=transfer_block();
        service_enabled=false;dut.test_time_bias+=30001;cycle(64);service_enabled=true;pump();
        std::vector<uint8_t> q;put(q,tid);put(q,64);put(q,word(block,40));check(command(0x32,q)[1]==0x8d,"slow CPU catches elapsed 30-second transfer expiry");
        replay=command(0x31,p,word(read,4));check(replay==read,"raw cached READ replay after timeout remains protocol compatible");check(transfer_block()==block,"timeout replay rebuilds exact bytes without reopening");
#ifndef GOLDEN
        check(!owner.transfer.open && !owner.transfer.pending,"post-timeout replay cannot resurrect C transfer lease");
#endif
        dut.test_time_bias=0xfffff000u;cycle(4);p=object();put(p,0);opened=command(0x30,p);tid=word(opened,16);
        dut.test_time_bias+=30001u;cycle(4);pump();q.clear();put(q,tid);check(command(0x34,q)[1]==0x8d,"transfer timeout subtraction works across uint32 time wrap");
        p=object();put(p,0);opened=command(0x30,p);tid=word(opened,16);
        dut.enable=0;cycle(30);dut.enable=1;cycle(30);
        // Align the HELLO timestamp stimulus itself; firmware work may take
        // different elapsed time. No response bytes are normalized/excluded.
        uint32_t previous_ms=dut.elapsed_ms_o;
        for(unsigned k=0;k<50001 && dut.elapsed_ms_o==previous_ms;k++)cycle();
        check(dut.elapsed_ms_o!=previous_ms,"next real elapsed-ms boundary reached");
        dut.test_time_bias+=65536u-dut.elapsed_ms_o;cycle(2);
        next_id=1;p.clear();put(p,1);command(1,p);cycle(4096);
#ifndef GOLDEN
        for(int k=0;k<8;k++)pump();
#endif
        q.clear();put(q,tid);check(command(0x34,q)[1]==0x8d,"new protocol session retires prior C transfer lease");
        p=object();put(p,384);opened=command(0x30,p);check(opened[1]==0 && word(opened,16)==tid+1,"reconnect resumes immutable object with next C transfer ID");
        q.clear();put(q,word(opened,16));command(0x34,q);
        std::printf("PASS real download policy and replay vectors: %u checks\n",checks);
    }

#ifndef GOLDEN
    void run_read_disconnect() {
        trace=false;std::vector<uint8_t> p;put(p,1);command(1,p);cycle(4096);for(int k=0;k<8;k++)pump();
        p.clear();put(p,1);put(p,64);command(0x20,p);until([&]{return dut.record_state==4;},"disconnect fixture immutable object");
        p=object();put(p,0);auto opened=command(0x30,p);uint32_t tid=word(opened,16);
        command(0x31,read_payload(tid,0,64));auto block=transfer_block();
        check(owner.transfer.offset==0 && owner.transfer.pending && owner.transfer.pending_length==64,"prior block is solely pending in C");
        uint32_t seq=owner.command_sequence;
        disconnect_read_submit=true;command(0x35,read_payload(tid,64,64,word(block,40),true));
        for(int k=0;k<16;k++)pump();
        check(!owner.fault && owner.phase==0,"disconnect before physical READ admission finishes finitely");
        check(owner.command_sequence==seq+1 && owner.facts.applied_seq==seq+1,"disconnected primitive has one exact completion");
        check(owner.transfer.offset==0 && owner.transfer.pending_offset==0 && owner.transfer.pending_length==64,"transport receipt without physical READ admission cannot commit combined ACK");
        check(!dut.transfer_valid && dut.record_state==4 && dut.object_id==1,"disconnected READ cannot publish data or mutate object");
        std::printf("PASS read primitive disconnect admission: %u checks\n",checks);
    }
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
int main(int argc,char **argv){Verilated::commandArgs(argc,argv);Harness h;h.run();Harness download;download.run_download();
#ifndef GOLDEN
#ifdef A138_SINGLE_BLE_RECORDING
Harness local;local.run_local_recording();
#endif
Harness cut;cut.run_read_disconnect();Harness edges;edges.run_edges();Harness uncertain;uncertain.run_uncertain();Harness completion;completion.run_uncertain_completion();Harness torn;torn.run_torn_completion();Harness empty;empty.run_zero_frame();
for(unsigned phase=2;phase<=5;phase++){Harness crcphase;crcphase.run_crc_phase(phase);}
#endif
}
