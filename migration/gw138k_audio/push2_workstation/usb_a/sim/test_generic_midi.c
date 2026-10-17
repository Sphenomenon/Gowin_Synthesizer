// Production firmware, mocked transport only; no USB or board access.
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
int usbhw_transfer_out_preloaded(uint8_t,int,int,int,uint8_t,int);
static volatile uint32_t regs[32];
static unsigned generic_writes,push_writes;
static volatile uint32_t *reg_at(unsigned off) {
    if(off==0x54)generic_writes++;
    if(off==4)push_writes++;
    return &regs[off/4];
}
#define MMIO(off) (*reg_at(off))
#define main production_main
#include "../firmware.c"
#undef main

static uint32_t now_ms;
static uint16_t fixture_vid=0xfb9a,fixture_pid=0xfb9b;
static uint8_t descriptor[256],payload[512],reply_pid=PID_DATA0;
static unsigned descriptor_size,descriptor_calls,control_calls,expected_alt,expected_interface;
static int descriptor_error,short_reply,control_ok=1,rx_result=USB_RES_NAK;
static unsigned expected_ep=1,expected_size=64,rx_calls,out_calls;
static const uint8_t g1_config[]={
    9,2,101,0,2,1,0,0x80,100,
    9,4,0,0,0,1,1,0,0, 9,0x24,1,0,1,9,0,1,1,
    9,4,1,0,2,1,3,0,0, 7,0x24,1,0,1,65,0,
    6,0x24,2,1,1,0, 6,0x24,2,2,2,0,
    9,0x24,3,1,3,1,2,1,0, 9,0x24,3,2,4,1,1,1,0,
    9,5,1,2,64,0,0,0,0, 5,0x25,1,1,1,
    9,5,0x81,2,64,0,0,0,0, 5,0x25,1,1,3
};
static void fixture(void) {
    memcpy(descriptor,g1_config,sizeof g1_config);descriptor_size=sizeof g1_config;
    descriptor_calls=control_calls=0;descriptor_error=short_reply=0;
    expected_alt=expected_interface=0;control_ok=1;rx_result=USB_RES_NAK;
    fixture_vid=0xfb9a;fixture_pid=0xfb9b;expected_ep=1;expected_size=64;
}
void delay(int ms){assert(ms>=0);now_ms+=(uint32_t)ms;}
t_time usbhw_timer_now(void){return now_ms;}
void usbhw_init(uint32_t base){assert(base==0x02000100);}
void usbhw_hub_enable(int fs,int sof){assert(fs==1 && sof==0);}
int usbhw_hub_device_detected(void){return 1;}
int usbhw_reset(void){assert(!regs[0]);return 0;}
int usb_configure_device(struct usb_device *d,int address){
    assert(!regs[0]);d->address=address;d->vid=fixture_vid;d->pid=fixture_pid;return 1;
}
int usb_get_descriptor(struct usb_device *d,uint16_t type,uint16_t index,uint8_t *buf,uint16_t length){
    assert(d==&dev && type==DESC_CONFIGURATION && index==0);descriptor_calls++;
    if(descriptor_error)return -1;
    unsigned n=length<descriptor_size?length:descriptor_size;
    if(short_reply && length>9)n--;
    memcpy(buf,descriptor,n);return (int)n;
}
int usb_send_control_write(struct usb_device *d,uint8_t type,uint8_t request,uint16_t value,uint16_t index,uint16_t length,uint8_t *data){
    assert(d==&dev && type==REQREC_INTERFACE && request==REQ_SET_INTERFACE);
    assert(value==expected_alt && index==expected_interface && length==0 && !data);
    control_calls++;return control_ok;
}
int usbhw_transfer_in(uint8_t token,int address,int ep,uint8_t *pid,uint8_t *buf,int size){
    assert(token==PID_IN && address==1 && ep==(int)expected_ep && size==(int)expected_size);
    rx_calls++;now_ms++;*pid=reply_pid;
    if(rx_result>0)memcpy(buf,payload,(unsigned)rx_result);
    return rx_result;
}
int usbhw_transfer_out(uint8_t token,int address,int ep,int handshake,uint8_t pid,uint8_t *buf,int n){
    (void)token;(void)address;(void)ep;(void)handshake;(void)pid;(void)buf;(void)n;
    assert(mode==DEVICE_PUSH);out_calls++;return USB_RES_OK;
}
int usbhw_transfer_out_preloaded(uint8_t token,int address,int ep,int handshake,uint8_t pid,int n){
    return usbhw_transfer_out(token,address,ep,handshake,pid,0,n);
}
static void rejected(void){connect();assert(!connected && mode==DEVICE_NONE && regs[0]==0);}
static void event(unsigned cin,unsigned status,unsigned a,unsigned b,int kind,unsigned out_b){
    uint8_t p[4]={(uint8_t)cin,(uint8_t)status,(uint8_t)a,(uint8_t)b};
    unsigned before=generic_writes;forward_midi(p);
    assert(generic_writes==before+(kind>=0));
    if(kind>=0)assert(regs[0x54/4]==((unsigned)kind<<14 | a<<7 | out_b));
}
int main(int argc,char **argv){
    fixture();assert(descriptor_size==101);connect();
    assert(connected && mode==DEVICE_MIDI && regs[0]==3 && descriptor_calls==2 && !control_calls);
    assert(midi_in_ep==1 && midi_in_size==64);
    // No Push output even if an old LED request is visible in the test MMIO.
    regs[0x40/4]=0x8000000c;lights();assert(!frame());
    assert(!send(2,payload,4) && !send_packet(1,0,512,0));
    regs[0x40/4]=0;assert(!out_calls);
    for(unsigned channel=0;channel<16;channel++) {
        event(0xf9,0x90|channel,0,2,1,2); // any cable/channel, low note, exact velocity
        event(9,0x90|channel,127,127,1,127);
        event(9,0x90|channel,12,0,0,0); // velocity zero is OFF, not bend reset
        event(8,0x80|channel,127,37,0,37);
    }
    for(unsigned a=0;a<128;a++)for(unsigned v=0;v<128;v++)
        event(9,0x90,a,v,v?1:0,v);
    event(11,0xb0,71,1,2,1); // ordinary CC71, never Push relative-volume remap
    event(11,0xb0,85,127,2,127); // not a Push Play command
    event(12,0xc0,40,255,3,0);event(14,0xe0,0,64,4,64);
    event(10,0xa0,127,2,5,2);
    event(13,0xd0,2,0,-1,0);event(4,0xf0,0,0,-1,0);
    event(9,0x80,60,1,-1,0);event(9,0x90,128,1,-1,0);event(9,0x90,60,128,-1,0);

    // Multiple events in a packet, short/full packets, duplicate DATA, ZLP,
    // malformed length and NAK: toggle and silence rules stay unchanged.
    for(unsigned i=0;i<64;i+=4){payload[i]=9;payload[i+1]=0x9f;payload[i+2]=100+i/4;payload[i+3]=2;}
    unsigned before=generic_writes;rx_result=64;reply_pid=PID_DATA0;poll_midi();
    assert(generic_writes==before+16 && in_pid==PID_DATA1);
    poll_midi();assert(generic_writes==before+16); // duplicate
    rx_result=8;reply_pid=PID_DATA1;poll_midi();assert(generic_writes==before+18);
    rx_result=0;reply_pid=PID_DATA0;poll_midi();assert(in_pid==PID_DATA1);
    rx_result=3;reply_pid=PID_DATA1;poll_midi();assert(generic_writes==before+18);
    rx_result=68;reply_pid=PID_DATA0;poll_midi();assert(generic_writes==before+18);
    rx_result=USB_RES_NAK;
    for(int i=0;i<2000;i++){delay(2);poll_midi();assert(connected);}
    now_ms=0xfffffff0u;last_in_reply=now_ms;rx_result=USB_RES_TIMEOUT;
    for(int i=0;i<49;i++){poll_midi();assert(connected);}
    poll_midi();assert(!connected && !regs[0]);
    assert(regs[0x58/4]==0x01ff0134u); // disconnect, saturated NAK, duplicate, errors

    // Different endpoint/size, alternate setting and interface number.
    fixture();descriptor[29]=6;descriptor[30]=1;descriptor[89]=0x87;descriptor[91]=32;
    expected_ep=7;expected_size=32;expected_alt=1;expected_interface=6;
    connect();assert(connected && control_calls==1 && midi_in_ep==7 && midi_in_size==32);
    poll_midi();control_ok=0;rejected();
    for(unsigned size=8;size<=64;size*=2){
        fixture();descriptor[91]=size;expected_size=size;connect();assert(connected);poll_midi();
    }
    // HID, audio streaming, MIDI2, no IN, interrupt IN, invalid FS MPS.
    fixture();descriptor[32]=3;rejected();
    fixture();descriptor[33]=2;rejected();
    fixture();descriptor[34]=2;rejected();
    fixture();descriptor[40]=2;rejected();
    fixture();descriptor[89]=1;rejected();
    fixture();descriptor[90]=3;rejected();
    fixture();descriptor[91]=0;rejected();
    fixture();descriptor[92]=2;rejected();
    fixture();descriptor[89]=0x80;rejected();
    fixture();descriptor[89]=0xf1;rejected();
    // Do not borrow an endpoint from a following unrelated interface.
    fixture();memcpy(descriptor+87,(uint8_t[]){9,4,2,0,1,3,0,0,0,7,5,0x83,2,64,0,0},16);
    descriptor_size=103;descriptor[2]=103;rejected();
    // Truncation, invalid lengths, fetch errors, including a malformed suffix
    // after an otherwise valid IN endpoint (must validate the whole walk).
    fixture();descriptor[9]=0;rejected();
    fixture();descriptor[9]=250;rejected();
    fixture();descriptor[36]=2;rejected();
    fixture();descriptor[96]=0;rejected();
    fixture();descriptor[2]=0xff;descriptor[3]=0xff;rejected();
    fixture();short_reply=1;rejected();
    fixture();descriptor_error=1;rejected();
    // Same PID with the wrong VID must not trigger the Push exception.
    fixture();fixture_pid=0x9999;descriptor[32]=3;rejected();
    for(unsigned i=0;i<2;i++){
        fixture();fixture_vid=0x2982;fixture_pid=i?0x1967:0x9999;
        descriptor_error=1;expected_ep=2;expected_size=512;
        connect();assert(connected && mode==DEVICE_PUSH && regs[0]==1 && !descriptor_calls);
        uint8_t note[4]={9,0x90,60,2};before=push_writes;forward_midi(note);
        assert(push_writes==before+1 && regs[1]==0x023c9009);
        assert(send(2,note,4));disconnect();
    }
    fixture();connect();assert(mode==DEVICE_MIDI && in_pid==PID_DATA0 && !toggles[1] && !toggles[2]);
    assert(out_calls==2); // only the two explicitly tested Push writes
    if(argc==2) {
        // Feed the production mapping results into the RTL/audio integration
        // test, instead of independently reimplementing the C conversion there.
        static const uint8_t notes[][4]={
            {9,0x90,24,2},{9,0x95,100,127},{0xf9,0x9f,127,1},{9,0x90,0,99},
            {8,0x80,24,37},{9,0x95,100,0},{8,0x8f,127,0},{9,0x90,0,0}
        };
        FILE *f=fopen(argv[1],"w");assert(f);
        for(unsigned i=0;i<sizeof notes/sizeof notes[0];i++) {
            forward_midi(notes[i]);fprintf(f,"%05x\n",(unsigned)regs[0x54/4]);
        }
        assert(fclose(f)==0);
    }
    puts("PASS generic firmware: both Push IDs, G1 descriptors, dynamic endpoint/MPS/alt, rejection bounds, 128x128 notes/velocity, channels/cables, no Push OUT, toggles/hotplug");
    return 0;
}
