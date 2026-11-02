// Verification host only. All MMIO goes through W endpoint, actual LCD RTL,
// M held-command CDC and original PCM1 owner; native CPU work costs zero time.
#include "Vtask3_phone_lcd_cosim.h"
#include "verilated.h"
#include "task3_phone_firmware_workload.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

struct Model {
    VerilatedContext context;
    Vtask3_phone_lcd_cosim top{&context};
    uint64_t ps=0,next_m=10000,next_w=3000,next_audio=6510,audio_edge=1;
    uint64_t w_half,mmio_reads=0,mmio_writes=0,max_mmio_ps=0,mmio_total_ps=0;
    uint64_t stall_begin=0,stall_end=0,mmio_errors=0,mmio_errors_after_underrun=0;
    uint32_t stall_record=0,stall_analysis=0,record_during_stall=0;
    bool w_rising=false,w_falling=false,accepted=false,stall_seen=false,stall_done=false;
    uint32_t accepted_value=0;bool accepted_error=false;
    explicit Model(unsigned half):w_half(half*1000) {top.eval();}
    void step() {
        uint64_t when=std::min({next_m,next_w,next_audio});
        ps=when;context.time(ps);w_rising=false;w_falling=false;accepted=false;
        if(stall_begin && ps>=stall_begin && !stall_seen) {
            top.analysis_stall_i=1;stall_seen=true;stall_record=top.record_received_o;stall_analysis=top.analysis_received_o;
        }
        if(stall_end && ps>=stall_end && !stall_done) {
            top.analysis_stall_i=0;stall_done=true;record_during_stall=top.record_received_o-stall_record;
        }
        if(when==next_m) {top.mclk_i=!top.mclk_i;next_m+=10000;}
        if(when==next_w) {
            w_rising=!top.wclk_i;w_falling=top.wclk_i;
            if(w_rising && (top.cpu_valid & top.cpu_ready)) {
                unsigned lane=(top.cpu_valid&2)?1:0;
                accepted=true;accepted_error=top.cpu_error&(1u<<lane);
                accepted_value=uint32_t(top.cpu_response>>(32*lane));
            }
            top.wclk_i=!top.wclk_i;next_w+=w_half;
        }
        if(when==next_audio) {
            top.audio_clk_i=!top.audio_clk_i;
            // Average 76.8MHz, alternating integer ps periods. No PLL/timing claim.
            next_audio=uint64_t((++audio_edge)*6510.416666666667+0.5);
        }
        top.eval();
        if(context.gotFinish())throw std::runtime_error("RTL stopped");
    }
    void until(uint64_t end) {while(ps<end)step();}
    void falling() {do {step();}while(!w_falling);}
    int bus(unsigned lane,bool write,uint32_t offset,uint32_t &value) {
        if(lane>1 || offset>4095)throw std::runtime_error("MMIO shape");
        if(lane)throw std::runtime_error("48k workload unexpectedly accesses clock stub");
        falling();top.cpu_valid=1u<<lane;top.cpu_write=write?1u<<lane:0;
        top.cpu_address=offset<<(12*lane);top.cpu_data=uint64_t(value)<<(32*lane);top.cpu_strobes=15u<<(4*lane);top.eval();
        uint64_t begin=ps;bool ok=false;
        while(ps-begin<20000000000ULL) {
            step();if(accepted){value=accepted_value;ok=!accepted_error;break;}
        }
        uint64_t elapsed=ps-begin;mmio_total_ps+=elapsed;max_mmio_ps=std::max(max_mmio_ps,elapsed);
        if(write)++mmio_writes;else ++mmio_reads;
        if(!ok) {
            ++mmio_errors;
            if(top.owner_failed_o && top.owner_failure_o==4)++mmio_errors_after_underrun;
            else throw std::runtime_error("MMIO failure without actual owner underrun");
        }
        falling();top.cpu_valid=0;top.cpu_write=0;top.eval();
        return ok;
    }
    static int rd(void *p,unsigned lane,uint32_t off,uint32_t *value) {
        uint32_t data=0;int ok=static_cast<Model*>(p)->bus(lane,false,off,data);
        if(ok)*value=data;return ok;
    }
    static int wr(void *p,unsigned lane,uint32_t off,uint32_t value) {return static_cast<Model*>(p)->bus(lane,true,off,value);}
    static uint32_t now(void *p) {return uint32_t(static_cast<Model*>(p)->ps/1000000000ULL);}
};

int main(int argc,char **argv) {
    if(argc!=6){std::cerr<<"usage: model W_half_ns concurrent inject_cap3 duration_ms report.json\n";return 2;}
    unsigned half=std::stoul(argv[1]);bool concurrent=std::stoi(argv[2]),inject=std::stoi(argv[3]);
    uint64_t duration_ms=std::stoul(argv[4]);Model m(half);auto &t=m.top;
    m.until(200000);t.reset_n=1;t.enable_i=1;t.eval();
    while(t.link_live_o!=3 && m.ps<5000000000ULL)m.step();
    if(t.link_live_o!=3)throw std::runtime_error("link boot timeout");
    m.falling();t.budget_i=1;t.eval();
    while(!t.phone_live_o && m.ps<8000000000ULL)m.step();
    if(!t.phone_live_o)throw std::runtime_error("phone negotiation timeout");
    m.falling();t.run_i=1;t.media_i=concurrent;t.analysis_start_i=concurrent;t.eval();
    m.until(m.ps+200000);t.analysis_start_i=0;t.eval();
    uint64_t begin=m.ps,end=begin+duration_ms*1000000000ULL;
    uint32_t start_ticks=t.sample_ticks_o;
    if(concurrent) {m.stall_begin=begin+5000000000ULL;m.stall_end=m.stall_begin+3960000000ULL;}
    task3_phone_callbacks callbacks{&m,Model::rd,Model::wr,Model::now};
    auto *work=task3_phone_workload_create(callbacks,44,55,1,48000,inject);
    if(!work)throw std::runtime_error("firmware fixture allocation");
    task3_phone_stats s{};uint64_t max_commit_ps=0,last_commit_ps=0,max_submit_ps=0;
    uint64_t first_commit_ps=0,first_selected_ps=0,first_failure_ps=0,first_ready_ps=0;
    uint32_t record_at_failure=0,analysis_at_failure=0,ticks_at_failure=0;
    uint64_t offered_blocks=0,maximum_offer_backlog=0;
    uint64_t prior_accepted=0;
    while(m.ps<end) {
        uint64_t before=m.ps;
        task3_phone_workload_snapshot(work,&s);
        // One external block every128/48000 seconds; no unbounded hidden queue.
        uint64_t due=uint64_t((m.ps-begin)*48000ULL/128ULL/1000000000000ULL)+1;
        uint64_t backlog=due-s.enqueued;maximum_offer_backlog=std::max(maximum_offer_backlog,backlog);
        offered_blocks=due;
        if(inject && s.enqueued<due)task3_phone_workload_enqueue128(work,8000,-6000);
        task3_phone_workload_pump(work);
        task3_phone_workload_snapshot(work,&s);
        max_submit_ps=std::max(max_submit_ps,m.ps-before);
        if(s.ready && !first_ready_ps)first_ready_ps=m.ps;
        if(s.accepted!=prior_accepted) {
            if(last_commit_ps)max_commit_ps=std::max(max_commit_ps,m.ps-last_commit_ps);
            if(!first_commit_ps)first_commit_ps=m.ps;
            last_commit_ps=m.ps;prior_accepted=s.accepted;
        }
        if(t.selected_o && !first_selected_ps)first_selected_ps=m.ps;
        if((s.fault||s.media_fault||t.owner_failed_o||t.fault_bits_o||m.mmio_errors) && !first_failure_ps) {
            first_failure_ps=m.ps;record_at_failure=t.record_received_o;
            analysis_at_failure=t.analysis_received_o;ticks_at_failure=t.sample_ticks_o;
        }
        // Continue clocks after a fenced firmware runtime so independent streams
        // and the audio sample schedule are observed through the entire window.
        if(m.ps==before || s.fault || s.media_fault)m.until(m.ps+1000000);
    }
    uint32_t ticks_before_cancel=t.sample_ticks_o;
    uint32_t owner_failure=t.owner_failure_o,owner_failed=t.owner_failed_o,selected=t.selected_o;
    uint32_t final_faults=t.fault_bits_o,nonzero=t.nonzero_o,queued=t.queued_phone_o;
    task3_phone_workload_cancel(work);
    uint64_t cancel_end=m.ps;m.until(m.ps+1000000000ULL);
    uint32_t ticks_after_cancel=t.sample_ticks_o;
    task3_phone_workload_destroy(work);
    std::ofstream o(argv[5]);
    o<<"{\n";
#define J(name,value) o<<"  \"" #name "\": "<<(value)<<",\n"
    J(W_half_ns,half);J(concurrent,concurrent);J(inject_cap3,inject);J(model_begin_ps,begin);J(model_elapsed_ps,m.ps-begin);
    J(offered_blocks,offered_blocks);J(maximum_offer_backlog_blocks,maximum_offer_backlog);J(enqueued_blocks,s.enqueued);J(accepted_blocks,s.accepted);
    J(passes,s.passes);J(pumps,s.pumps);J(media_polls,s.media_polls);J(submit_calls,s.submit_calls);J(rejected_submits,s.rejected_submits);J(uncertain_submits,s.uncertain_submits);
    J(firmware_fault,s.fault);J(media_fault,s.media_fault);J(firmware_fences,s.fences);J(adapter_armed,s.armed);J(adapter_ready,s.ready);J(adapter_pending,s.pending);
    J(observed_caps,s.observed_caps);J(max_window_writes_per_submit,s.max_window_writes_per_submit);J(window_writes,s.window_writes);J(pcm_reads,s.pcm_reads);J(pcm_writes,s.pcm_writes);
    J(clock_reads,s.clock_reads);J(clock_writes,s.clock_writes);J(local_hci_reads,s.local_hci_reads);J(local_hci_writes,s.local_hci_writes);
    J(mmio_reads,m.mmio_reads);J(mmio_writes,m.mmio_writes);J(mmio_errors,m.mmio_errors);J(max_mmio_ps,m.max_mmio_ps);J(mmio_total_ps,m.mmio_total_ps);
    J(mmio_errors_after_owner_underrun,m.mmio_errors_after_underrun);J(rejected_window_commands,t.rejected_window_commands_o);
    J(max_four_pass_pump_ps,max_submit_ps);J(first_ready_ps,first_ready_ps);J(first_commit_ps,first_commit_ps);J(first_selected_ps,first_selected_ps);J(first_failure_ps,first_failure_ps);J(max_commit_interval_ps,max_commit_ps);
    J(owner_failed,owner_failed);J(owner_failure,owner_failure);J(owner_selected,selected);J(owner_queued_frames,queued);J(exact_nonzero_stereo_outputs,nonzero);
    J(applied_window_words,t.applied_words_o);J(window_packets_accepted_by_transport,t.phone_blocks_o);J(analysis_received,t.analysis_received_o);J(record_received,t.record_received_o);J(max_analysis_external_offer_queue,t.max_analysis_queue_o);J(max_actual_TF_source_queue,t.max_tf_queue_o);J(max_record_source_queue,t.max_record_queue_o);
    J(stall_seen,m.stall_seen);J(stall_done,m.stall_done);J(record_frames_during_analysis_stall,m.record_during_stall);
    J(M_packets,t.m_packets_o);J(W_packets,t.w_packets_o);J(M_probe_results,t.m_probe_o);J(W_probe_results,t.w_probe_o);J(M_max_probe_RTT_cycles,t.m_rtt_o);J(W_max_probe_RTT_cycles,t.w_rtt_o);
    J(final_fault_bits,final_faults);J(malformed_packets,t.malformed_o);J(stale_packets,t.stale_o);
    J(record_at_first_failure,record_at_failure);J(analysis_at_first_failure,analysis_at_failure);J(ticks_at_first_failure,ticks_at_failure);
    J(sample_ticks,t.sample_ticks_o-start_ticks);J(ticks_before_cancel,ticks_before_cancel);J(ticks_after_cancel,ticks_after_cancel);J(cancel_end_ps,cancel_end);
    o<<"  \"hardware_tested\": false,\n  \"sustained_phone_audio_accepted\": false\n}\n";
    t.final();std::cout<<"MODEL_REPORT "<<argv[5]<<" accepted="<<s.accepted<<" owner_failure="<<owner_failure<<" nonzero="<<nonzero<<" faults="<<final_faults<<"\n";
    return 0;
}
