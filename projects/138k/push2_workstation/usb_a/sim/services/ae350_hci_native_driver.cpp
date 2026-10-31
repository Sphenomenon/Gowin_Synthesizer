#include "Vworkstation_hci_native_cosim.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <vector>
extern "C" {
#include "hci_transport.h"
}
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"check %u line%d: %s\n",checks,__LINE__,#x);std::exit(1);}}while(0)
struct Simulator {
    Vworkstation_hci_native_cosim top;
    std::deque<std::vector<unsigned char>> events;
    std::vector<std::vector<unsigned char>> packets;
    std::vector<unsigned> types;
    unsigned rx_at=0,rx_phase=0,clocks=0,maximum_apb_wait=0;
    bool automatic=true;
    void receive(const std::vector<unsigned char>&p,unsigned type=4) {
        CHECK(type==4||type==2);std::vector<unsigned char> tagged=p;
        tagged.insert(tagged.begin(),static_cast<unsigned char>(type));events.push_back(tagged);
    }
    void captured() {
        std::vector<unsigned char> p;
        for(unsigned i=0;i<top.packet_length_o;i++){top.packet_address_i=i;top.eval();p.push_back(top.packet_data_o);}
        packets.push_back(p);types.push_back(top.packet_type_o);
        if(top.packet_type_o!=1||p.size()<3)return;
        unsigned op=p[0]|(unsigned(p[1])<<8);
        if(op==0x0c35)return;
        if(op==0x1005)receive({14,11,1,5,16,0,64,0,0,4,0,0,0});
        else if(op==0x2002)receive({14,7,1,2,32,0,27,0,1});
        else if(op==0x0c33||op==0x0c31)receive({14,4,1,p[0],p[1],0});
        else if(automatic) {
            if(op==0x0409)receive({15,4,0,1,p[0],p[1]});
            else if(op==0x1003)receive({14,12,1,p[0],p[1],0,0,0,0,0,0,0,8,128});
            else receive({14,4,1,p[0],p[1],0});
        }
    }
    void tick() {
        top.clk_i=0;top.rx_write_i=0;top.rx_valid_i=0;
        if(!events.empty()&&top.reset_ni) {
            auto &p=events.front();top.rx_type_i=p[0];top.rx_length_i=p.size()-1;
            if(rx_phase==0){top.rx_write_i=1;top.rx_write_address_i=rx_at;top.rx_write_data_i=p[rx_at+1];}
            else top.rx_valid_i=1;
        }
        top.eval();bool consumed=top.rx_valid_i&&top.rx_consume_o;
        bool drove_write=top.rx_write_i,drove_valid=top.rx_valid_i;
        top.clk_i=1;top.eval();++clocks;
        if(top.packet_copied_o)captured();
        if(!events.empty()&&top.reset_ni) {
            if(drove_write){if(++rx_at==events.front().size()-1)rx_phase=1;}
            else if(drove_valid&&(consumed||top.rx_consume_o)){events.pop_front();rx_at=rx_phase=0;}
        }
        CHECK(clocks<200000u);
    }
    void reset() {
        top.reset_ni=0;top.observer_reset_ni=0;top.command_valid_i=0;top.rx_valid_i=0;
        top.rx_write_i=0;top.hold_transport_i=0;
        for(unsigned i=0;i<4;i++)tick();top.reset_ni=top.observer_reset_ni=1;
        for(unsigned i=0;!top.ready_o&&i<10000;i++){tick();CHECK(!top.fault_o);}
        CHECK(top.ready_o&&top.epoch_o==0x44332211u&&packets.size()==4);
        CHECK(top.br_available_o==4&&top.le_available_o==1&&top.host_budget_o==4);
    }
    bool access(bool write,unsigned off,unsigned &data) {
        top.command_valid_i=1;top.command_write_i=write;top.command_address_i=0x200u+off;top.command_data_i=data;
        unsigned waited=0;
        for(;;){
            top.clk_i=0;top.eval();
            bool ready=top.command_ready_o,error=top.response_error_o;unsigned result=top.response_data_o;
            tick();++waited;
            if(ready){data=result;top.command_valid_i=0;top.clk_i=0;top.eval();
                if(waited>maximum_apb_wait)maximum_apb_wait=waited;CHECK(waited<=8u);return !error;}
            CHECK(waited<8u);
        }
    }
};
static int rd(void *p,uint32_t off,uint32_t *v){unsigned x=0;bool ok=static_cast<Simulator *>(p)->access(false,off,x);*v=x;return ok;}
static int wr(void *p,uint32_t off,uint32_t v){unsigned x=v;return static_cast<Simulator *>(p)->access(true,off,x);}
static void step(struct a138_hci_transport &t,Simulator &s){a138_hci_step(&t);CHECK(!t.fault&&!s.top.fault_o);}
static void wait_head(struct a138_hci_transport &t,Simulator &s) {
    for(unsigned i=0;!a138_hci_rx_peek(&t)&&i<200u;i++)step(t,s);
    CHECK(a138_hci_rx_peek(&t));
}
static void release(struct a138_hci_transport &t){auto p=a138_hci_rx_peek(&t);CHECK(p&&a138_hci_rx_release(&t,p->epoch,p->ticket));}
static void complete(struct a138_hci_transport&t,Simulator&s) {
    for(unsigned i=0;!t.transport_done&&i<200u;i++)step(t,s);
    CHECK(t.accepted&&t.transport_done&&t.response_done&&a138_hci_tx_retire(&t));
}
int main(int argc,char **argv) {
    Verilated::commandArgs(argc,argv);Simulator s;s.reset();
    struct a138_hci_transport t;a138_hci_init(&t,{&s,rd,wr});step(t,s);
    CHECK(t.ready&&t.available&&t.br_limit==64&&t.le_limit==27);
    s.top.hold_transport_i=1;unsigned char cmd[3]={3,16,0};
    CHECK(a138_hci_offer(&t,1,0,1,cmd,3));cmd[0]=0xff;
    wait_head(t,s);auto head=a138_hci_rx_peek(&t);
    CHECK(t.accepted&&!t.transport_done&&head->response&&head->owner==2&&head->token==t.tx_token);
    CHECK(head->bytes==14&&head->data[3]==3&&head->data[12]==8&&head->data[13]==128);
    CHECK(s.packets.back()==std::vector<unsigned char>({3,16,0}));
    CHECK(!a138_hci_tx_retire(&t)&&a138_hci_response_delivered(&t,head->token));release(t);
    CHECK(!a138_hci_tx_retire(&t));s.top.hold_transport_i=0;complete(t,s);
    s.automatic=false;unsigned char cmd2[4]={0x56,0x0c,1,1};CHECK(a138_hci_offer(&t,1,0,1,cmd2,4)&&t.tx_token==2);
    for(unsigned i=0;!t.transport_done&&i<200u;i++)step(t,s);
    CHECK(t.accepted&&t.transport_done&&!t.response_done&&!a138_hci_tx_retire(&t));
    s.receive({14,4,1,0x56,0x0c,0});wait_head(t,s);head=a138_hci_rx_peek(&t);
    CHECK(head->token==2&&a138_hci_response_delivered(&t,head->token));release(t);complete(t,s);
    s.automatic=true;
    s.receive({4,10,1,2,3,4,5,6,0,0,0,1});wait_head(t,s);head=a138_hci_rx_peek(&t);CHECK(head->data[0]==4&&head->generation==0);release(t);
    unsigned char accept[10]={9,4,7,1,2,3,4,5,6,1};CHECK(a138_hci_offer(&t,1,0,2,accept,10));
    wait_head(t,s);head=a138_hci_rx_peek(&t);CHECK(head->data[0]==15&&a138_hci_response_delivered(&t,head->token));release(t);complete(t,s);
    s.receive({3,11,0,0x23,0,1,2,3,4,5,6,1,0});wait_head(t,s);head=a138_hci_rx_peek(&t);
    unsigned generation=head->generation;CHECK(head->data[0]==3&&generation&&s.top.classic_ready_o);release(t);
    s.receive({0x23,0x20,8,0,4,0,0x40,0,1,2,3,4},2);wait_head(t,s);head=a138_hci_rx_peek(&t);
    CHECK(head->type==2&&head->generation==generation&&head->bytes==12&&!head->retired);
    unsigned ticket=head->ticket;
    for(unsigned i=0;s.top.host_budget_o!=4&&i<500u;i++)s.tick();
    CHECK(s.top.host_budget_o==4&&a138_hci_rx_peek(&t)->ticket==ticket); /* held CPU copy is not physical credit */
    s.receive({5,4,0,0x23,0,0x13});for(unsigned i=0;i<300u;i++)s.tick();step(t,s);head=a138_hci_rx_peek(&t);
    CHECK(head->ticket==ticket&&head->retired);release(t);wait_head(t,s);head=a138_hci_rx_peek(&t);CHECK(head->data[0]==5&&head->generation==generation);release(t);
    CHECK(wr(&s,124,t.epoch));for(unsigned i=0;i<5u;i++)s.tick();CHECK(s.top.fenced_o&&!s.top.fault_o);
    CHECK(s.top.br_available_o==4&&s.top.le_available_o==1&&s.top.host_budget_o==4);
    std::printf("actual C/native HCI RTL: %u checks passed, %u clocks, maxAPBwait%u; outer H5 RAM fixture, no board\n",checks,s.clocks,s.maximum_apb_wait);
}
