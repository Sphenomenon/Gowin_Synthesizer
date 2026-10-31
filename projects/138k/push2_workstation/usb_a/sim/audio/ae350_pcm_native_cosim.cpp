#include "Vae350_pcm_cosim.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
extern "C" {
#include "pcm_media.h"
}
struct Harness {
    VerilatedContext context;
    Vae350_pcm_cosim dut{&context};
    a138_pcm_media adapter{};
    a138_runtime_media media{};
    uint64_t scheduler_events=0;
    unsigned checks=0,reads=0,writes=0,window_writes=0,clock_reads=0,clock_writes=0,max_wait=0;
    bool inject_capability=false,inject_delay=false,reset_during_window=false,reset_observed=false;
    void check(bool v,const char *name) {
        ++checks;
        if(!v){std::fprintf(stderr,"FAIL %s t=%llu fault=%u armed=%u writing=%u seq=%u queue=%u commands=%u selected=%u failed=%u control=%x options=%x\n",name,(unsigned long long)context.time(),adapter.fault,adapter.armed,adapter.writing,adapter.next_sequence,dut.queue_count,dut.owner_commands,dut.stream_selected,dut.owner_failed,dut.control_debug,dut.options_debug);std::exit(1);}
    }
    void step() {
        if(!dut.eventsPending())check(false,"timed clocks pending");
        ++scheduler_events;
        context.time(dut.nextTimeSlot());dut.eval();
        if(reset_during_window&&dut.bus_enable&&dut.bus_write&&dut.bus_address>=0x800&&dut.command_pending) {
            reset_during_window=false;reset_observed=true;dut.cpu_reset_n=0;dut.bus_select=0;dut.bus_enable=0;dut.eval();
        }
    }
    void until(const std::function<bool()> &p,const char *name,uint64_t duration=UINT64_C(10000000000)) {
        uint64_t end=context.time()+duration;
        while(!p()&&context.time()<end)step();
        check(p(),name);
    }
    void edge(bool high) {
        if(bool(dut.peripheral_clk)==high)until([&]{return bool(dut.peripheral_clk)!=high;},"leave pclk edge");
        until([&]{return bool(dut.peripheral_clk)==high;},"pclk edge");
    }
    void settle(unsigned n=8) {for(unsigned k=0;k<n;k++)edge(false);}
    bool access(unsigned address,bool write,uint32_t &v,bool page=true) {
        edge(false);dut.bus_page=page;dut.bus_select=1;dut.bus_enable=0;dut.bus_write=write;dut.bus_address=address;dut.bus_data=v;dut.eval();
        edge(false);dut.bus_enable=1;dut.eval();
        bool ok=false,done=false;
        for(unsigned n=1;n<=10000;n++) {
            edge(true);
            if(reset_observed) {
                reset_observed=false;settle();dut.cpu_reset_n=1;dut.eval();settle();return false;
            }
            if(dut.bus_ready){done=true;ok=!dut.bus_error;v=dut.bus_result;if(n>max_wait)max_wait=n;break;}
        }
        check(done,"APB completes bounded");
        edge(false);dut.bus_select=0;dut.bus_enable=0;dut.eval();return ok;
    }
    static int rd(void *p,uint32_t off,uint32_t *v) {
        auto &h=*static_cast<Harness*>(p);++h.reads;uint32_t data=0;
        bool ok=h.access(off,false,data);
        if(ok&&off==8){h.check(data==0x67,"actual native default capability 0x67");if(h.inject_capability)data|=8;if(h.inject_delay)data|=16;}
        if(ok)*v=data;return ok;
    }
    static int wr(void *p,uint32_t off,uint32_t v) {
        auto &h=*static_cast<Harness*>(p);++h.writes;if(off>=0x800)++h.window_writes;return h.access(off,true,v);
    }
    static int clock_rd(void *p,uint32_t,uint32_t *){++static_cast<Harness*>(p)->clock_reads;return 0;}
    static int clock_wr(void *p,uint32_t,uint32_t){++static_cast<Harness*>(p)->clock_writes;return 0;}
    void initialize() {
        a138_hci_bus b{this,rd,wr};a138_clock_bus c{this,clock_rd,clock_wr};a138_pcm_media_init(&adapter,b,c);media=a138_pcm_media_callbacks(&adapter);
    }
    int poll(uint32_t stream,uint32_t rate,a138_runtime_audio_facts &f) {
        return media.poll(media.context,dut.session_epoch,dut.session_generation,stream,rate,&f);
    }
    void arm(uint32_t stream,uint32_t rate) {
        a138_runtime_audio_facts f{};
        until([&]{return dut.context_ready&&!dut.serial_held;},"actual context/histories ready");
        until([&]{(void)poll(stream,rate,f);return adapter.armed||adapter.fault;},"ARM completes after actual source history barrier");
        check(adapter.armed&&!adapter.fault,"real C ARM accepted");
        check(poll(stream,rate,f)==1&&f.ready&&f.drift_managed,"real C observes full-key owner");
    }
    a138_classic_submission slice(uint32_t stream,uint32_t rate,unsigned channels=2) {
        a138_classic_frame frame{};frame.link_epoch=dut.session_generation;frame.stream_epoch=stream;
        int16_t samples[256]{};for(unsigned i=0;i<128;i++){samples[i*channels]=8000;if(channels==2)samples[2*i+1]=-6000;}
        a138_sbc_pcm decoded{};decoded.valid=1;decoded.stream_epoch=stream;decoded.rate_hz=rate;decoded.frames=128;decoded.channels=channels;decoded.scalar_samples=128*channels;
        dut.expected_pcm_word=channels==2?0xe8901f40u:0x1f401f40u;dut.eval();
        unsigned before=window_writes;auto r=media.submit(media.context,dut.session_epoch,dut.session_generation,stream,&frame,samples,&decoded);
        check(window_writes-before<=16,"actual C bounded 16 stereo words per submit");return r;
    }
    void block(uint32_t stream,uint32_t rate,unsigned channels=2) {
        auto r=A138_CLASSIC_REJECTED;unsigned count=0;uint32_t before=dut.owner_commands;
        while(r==A138_CLASSIC_REJECTED&&count<100){r=slice(stream,rate,channels);count++;if(r==A138_CLASSIC_REJECTED)check(dut.owner_commands==before,"partial block never committed");}
        check(r==A138_CLASSIC_ACCEPTED&&count==8&&dut.owner_commands==before+1,"one full 128-frame block commits once");
    }
    void event(unsigned kind,unsigned address,unsigned value) {
        uint32_t v=(kind<<14)|(address<<7)|value;check(access(0x180,true,v,false),"real CPU event APB");
    }
    void frames(unsigned n,const std::function<void()> &pump={}) {
        unsigned target=dut.physical_count+n;
        while(dut.physical_count<target){if(pump)pump();else step();}
    }
    void feed(uint32_t stream,uint32_t rate,unsigned channels=2) {
        uint32_t mask=0;check(access(0x14,false,mask),"read actual free slots");
        if(mask&(1u<<adapter.slot))block(stream,rate,channels);else settle(8);
    }
    void select(uint32_t stream,uint32_t rate) {
        a138_runtime_audio_facts f{};check(poll(stream,rate,f)==1&&f.ready,"C selects prefilled source");
        until([&]{return dut.stream_selected&&!dut.serial_held;},"history/serial source handoff");
    }
    void cancel(uint32_t stream) {
        media.cancel(media.context,dut.session_epoch,dut.session_generation,stream);
        until([&]{return !dut.stream_selected&&!dut.serial_held;},"C cancel drains history/serial hold");
        check(!adapter.armed&&!adapter.writing&&dut.queue_count==0,"cancel reclaims complete and partial slots");
    }
    void run() {
        dut.cpu_reset_n=0;dut.session_ready=1;dut.session_epoch=11;dut.session_generation=22;dut.eval();settle();dut.cpu_reset_n=1;dut.eval();
        until([&]{return dut.context_ready;},"runtime startup ready");frames(3);initialize();
        for(unsigned rate:{44100u,48000u})for(unsigned i=0;i<3;i++){a138_runtime_audio_facts f{};check(poll(1,rate,f)==1&&!f.ready&&!f.drift_managed,"actual cap3 false fails closed");}
        check(writes==0&&clock_reads==0&&clock_writes==0&&dut.owner_commands==0,"cap3 false has no PCM/clock/source side effects");
        inject_delay=true;a138_runtime_audio_facts f{};check(poll(1,48000,f)==-1&&adapter.fault&&writes==0,"unknown total-delay capability fails closed");inject_delay=false;
        initialize();inject_capability=true; // Test-only read wrapper; native RTL capability remains 0x67.
        event(2,16,127);event(2,81,0);frames(280);arm(1,48000);
        for(unsigned k=0;k<4;k++)block(1,48000);
        unsigned oldwrites=writes,oldcommands=dut.owner_commands;check(slice(1,48000)==A138_CLASSIC_REJECTED&&writes==oldwrites&&dut.owner_commands==oldcommands,"full queue rejects without overwrite or command");
        select(1,48000);unsigned olddirect=dut.direct_count;frames(100,[&]{feed(1,48000);});check(dut.direct_count>=olddirect+32,"C PCM reaches actual effects/final volume/decoded I2S");
        event(2,7,64);unsigned oldhalf=dut.half_count;frames(100,[&]{feed(1,48000);});check(dut.half_count>=oldhalf+32,"unique master volume halves real C PCM once");event(2,7,127);
        event(1,60,100);frames(4,[&]{feed(1,48000);});event(2,81,2);unsigned oldwet=dut.effect_count;frames(640,[&]{feed(1,48000);});check(dut.effect_count>oldwet,"real C source traverses native chorus");
        uint32_t held[4];for(unsigned i=0;i<4;i++)held[i]=dut.held_snapshot[i];unsigned oldhistory=dut.history_count;
        cancel(1);for(unsigned i=0;i<4;i++)check(held[i]==dut.held_snapshot[i],"cancel preserves real held notes");check(dut.history_count>oldhistory,"cancel clears actual effect history");
        event(0,60,0);event(2,11,0);event(2,81,0);frames(8);arm(2,48000);check(slice(2,48000)==A138_CLASSIC_REJECTED&&adapter.writing,"partial C block held");cancel(2);
        oldwrites=writes;check(slice(2,48000)==A138_CLASSIC_UNCERTAIN&&writes==oldwrites,"cancelled old block cannot resume");
        arm(3,48000);for(unsigned k=0;k<4;k++)block(3,48000,1);select(3,48000);unsigned oldmono=dut.mono_count;frames(360,[&]{feed(3,48000,1);});check(dut.mono_count>=oldmono+32,"C mono expands exact stereo through I2S");
        oldwrites=writes;check(slice(2,48000)==A138_CLASSIC_UNCERTAIN&&writes==oldwrites,"wrong stream cannot alter partial/current block");
        reset_during_window=true;
        until([&]{uint32_t free=0;check(access(0x14,false,free),"free before injected CPU reset");return (free&(1u<<adapter.slot))!=0;},"slot before reset");
        check(slice(3,48000,1)==A138_CLASSIC_UNCERTAIN&&adapter.fault,"CPU reset during actual APB copy faults C observer");
        until([&]{return !dut.stream_selected&&!dut.serial_held;},"PL fences CPU reset without C cooperation");check(dut.owner_failed&&dut.queue_count==0,"CPU reset flushes PL queue");
        initialize();until([&]{(void)poll(3,48000,f);return adapter.fault||adapter.armed;},"retired stream rearm resolves after history barrier");check(adapter.fault&&!adapter.armed,"retired stream cannot rearm after CPU reset");initialize();arm(4,48000);for(unsigned k=0;k<4;k++)block(4,48000);select(4,48000);
        a138_pcm_media stale_adapter=adapter;auto stale_media=a138_pcm_media_callbacks(&stale_adapter);
        unsigned oldcancel=dut.cancel_epoch;dut.session_ready=0;dut.eval();until([&]{return !dut.stream_selected&&!dut.serial_held;},"HCI session revoke independent of CPU");check(dut.owner_failed&&dut.cancel_epoch>oldcancel&&dut.queue_count==0,"session revoke flushes old PCM");
        dut.session_generation=23;dut.session_epoch=12;dut.session_ready=1;dut.eval();settle(12);initialize();arm(1,48000);oldcommands=dut.owner_commands;
        stale_media.cancel(stale_media.context,11,22,4);check(dut.owner_commands==oldcommands&&adapter.armed&&!stale_adapter.armed,"old observer cancellation cannot affect new epoch/generation");cancel(1);
        dut.rate_request44=1;dut.rate_request=1;dut.eval();settle(2);dut.rate_request=0;dut.eval();until([&]{return dut.context_ready&&dut.context_rate&&!dut.serial_held;},"actual 44.1k context switch");initialize();arm(2,44100);for(unsigned k=0;k<4;k++)block(2,44100);select(2,44100);olddirect=dut.direct_count;frames(80,[&]{feed(2,44100);});check(dut.direct_count>=olddirect+32,"44.1k C PCM actual I2S path");cancel(2);
        check(clock_reads==0&&clock_writes==0,"same-rate owner never accesses clock callback");
        inject_capability=false;initialize();oldwrites=writes;oldcommands=dut.owner_commands;check(poll(3,48000,f)==1&&!f.ready&&writes==oldwrites&&dut.owner_commands==oldcommands,"native capability remains closed after all test scenarios");
        std::printf("PASS actual C PCM callbacks/APB/CDC/native DSP/one-volume/I2S: checks=%u scheduler_events=%llu reads=%u writes=%u window=%u frames=%u direct=%u half=%u mono=%u history=%u chorus=%u complete_blocks=%u complete_words=%u max_APB_wait=%u; test-only cap3 wrapper, native=0x67 cap3/4=false, no physical/cycles/phone acceptance\n",checks,(unsigned long long)scheduler_events,reads,writes,window_writes,dut.physical_count,dut.direct_count,dut.half_count,dut.mono_count,dut.history_count,dut.effect_count,dut.complete_block_count,dut.complete_word_count,max_wait);
    }
};
int main(int argc,char **argv){Verilated::commandArgs(argc,argv);Harness h;h.run();return 0;}
