// Exercise the production firmware with deterministic USB transfer results.
// The real Vex/MMIO/RTL path is covered by tb_cpu_audio and tb_mmio separately.
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
static volatile uint32_t regs[32];
#define MMIO(off) regs[(off)/4]
#define main production_main
#include "../firmware.c"
#undef main

static uint32_t now_ms;
static int present=1,enumeration_ok=1,reset_count,configure_count,detect_count;
static int appear_after,rx_result=USB_RES_NAK;
static uint8_t rx_pid=PID_DATA0;
static uint32_t midi_word=0x643c9009;
static int out_naks,out_stall,out_calls,rx_calls,wire_toggle[3];
static unsigned headers,blocks;
static int disconnect_on_block;

void delay(int ms){assert(ms>=0);now_ms+=(uint32_t)ms;if(appear_after && now_ms>=(uint32_t)appear_after)present=1;}
t_time usbhw_timer_now(void){return now_ms;}
void usbhw_init(uint32_t base){assert(base==0x02000100);}
void usbhw_hub_enable(int full_speed,int sof){assert(full_speed==1 && sof==0);}
int usbhw_hub_device_detected(void){detect_count++;return present;}
int usbhw_reset(void){assert(!MMIO(0));reset_count++;wire_toggle[1]=wire_toggle[2]=0;return 0;}
int usb_configure_device(struct usb_device *d,int address){
    assert(!MMIO(0));configure_count++;d->address=address;d->vid=0x2982;d->pid=0x9999;return enumeration_ok;
}
int usbhw_transfer_in(uint8_t token,int address,int ep,uint8_t *pid,uint8_t *buf,int size){
    assert(token==PID_IN && address==1 && ep==2 && size==512);rx_calls++;now_ms++;
    *pid=rx_pid;
    if(rx_result==4)for(int i=0;i<4;i++)buf[i]=midi_word>>(8*i);
    return rx_result;
}
int usbhw_transfer_out(uint8_t token,int address,int ep,int handshake,uint8_t pid,uint8_t *buf,int n){
    assert(connected && token==PID_OUT && address==1 && (ep==1 || ep==2) && handshake);
    assert(pid==(wire_toggle[ep]?PID_DATA1:PID_DATA0));out_calls++;now_ms++;
    if(out_naks){out_naks--;return USB_RES_NAK;}
    if(out_stall)return USB_RES_STALL;
    if(disconnect_on_block && blocks>=(unsigned)disconnect_on_block){rx_result=USB_RES_TIMEOUT;return USB_RES_TIMEOUT;}
    if(ep==1){
        if(n==16){assert(buf[0]==0xff && buf[1]==0xcc && buf[2]==0xaa && buf[3]==0x88);headers++;}
        else {assert(n==512);blocks++;}
    }
    wire_toggle[ep]^=1;return USB_RES_OK;
}
int main(void){
    // Startup may wait for a device, then configure the observed zero-interface
    // PID9999 quirk. A failed enumeration must return for a later retry.
    connected=0;present=0;appear_after=300;enumeration_ok=0;
    connect();assert(!connected && !MMIO(0) && reset_count==1);
    enumeration_ok=1;connect();assert(connected && MMIO(0)==1 && reset_count==2);
    assert(configure_count==2 && detect_count>=5 && in_pid==PID_DATA0);
    assert(!toggles[1] && !toggles[2]);
    // A silent MIDI device NAKs indefinitely without being disconnected.
    for(int i=0;i<2000;i++){delay(2);poll_midi();assert(connected);}
    // A brief timeout is tolerated; duplicates refresh liveness but are not
    // redelivered. A fresh DATA1 packet is still accepted afterward.
    rx_result=4;rx_pid=PID_DATA0;poll_midi();assert(MMIO(4)==midi_word && in_pid==PID_DATA1);
    MMIO(4)=0;poll_midi();assert(!MMIO(4) && in_pid==PID_DATA1);
    rx_result=USB_RES_TIMEOUT;delay(20);poll_midi();assert(connected);
    rx_result=4;rx_pid=PID_DATA1;midi_word=0x003c8008;poll_midi();assert(MMIO(4)==midi_word);
    rx_result=USB_RES_NAK;
    uint8_t data[4]={9,0x90,60,122};
    out_naks=2;int before=rx_calls;assert(send(2,data,4));
    assert(out_calls==3 && rx_calls-before==2 && toggles[2]==1);
    out_stall=1;assert(!send(2,data,4) && toggles[2]==1 && connected);out_stall=0;
    // OUT failure alone cannot suppress MIDI; NAK retry exhaustion is not a
    // missing IN reply. No screen/LED ACK is invented.
    out_naks=1000;assert(!send(2,data,4) && connected && toggles[2]==1);
    assert(out_naks==0);
    // Lost device releases session state after 50ms, even across timer wrap.
    now_ms=0xfffffff0u;last_in_reply=now_ms;rx_result=USB_RES_TIMEOUT;
    for(int i=0;i<49;i++){poll_midi();assert(connected);}
    poll_midi();assert(!connected && !MMIO(0));
    before=rx_calls;poll_midi();assert(rx_calls==before);assert(!send(2,data,4));
    // Replug at any old PID state resets BOTH OUT endpoint toggles and MIDI IN.
    toggles[1]=toggles[2]=1;in_pid=PID_DATA1;rx_result=USB_RES_NAK;
    connect();assert(connected && !toggles[1] && !toggles[2] && in_pid==PID_DATA0);
    rx_result=4;rx_pid=PID_DATA0;midi_word=0x643d9009;poll_midi();assert(MMIO(4)==midi_word);
    rx_result=USB_RES_NAK;
    headers=blocks=0;assert(frame());assert(headers==1 && blocks==640 && frames==1 && MMIO(0x30)==1);
    assert(toggles[1]==1); // 641 ACKs on endpoint 1, endpoint 2 remains DATA0.
    assert(send(2,data,4) && toggles[2]==1);
    // Unplug during a screen frame, then start a fresh header after reconnect.
    disconnect_on_block=blocks+7;assert(!frame());
    for(int i=0;i<60 && connected;i++)poll_midi();assert(!connected && frames==1);
    disconnect_on_block=0;rx_result=USB_RES_NAK;connect();
    headers=blocks=0;assert(frame());assert(headers==1 && blocks==640 && frames==2);
    assert(MMIO(0x30)==2 && reset_count==4);
    // The screen scheduler sends the first snapshot, suppresses an unchanged
    // 327696-byte frame, and notices the next UI state change.
    displayed_state_valid=0;
    assert(screen_changed());
    assert(!screen_changed());
    MMIO(0x24)=0x00002244;
    assert(screen_changed());
    assert(!screen_changed());
    puts("PASS production USB firmware: hotplug/toggles, MIDI during frame, 640-packet frame, event-driven screen state");
    return 0;
}
