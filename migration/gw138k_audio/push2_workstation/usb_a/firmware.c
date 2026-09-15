/* Based on the board-accepted 8FC3 Full-Speed Push surface firmware.
 * USB transactions and per-endpoint PID rules are retained. MIDI is forwarded
 * through backpressured MMIO, before servicing any display or light traffic.
 */
#include <stdint.h>
#include "minlibc.h"
#include "usb_core.h"
#include "usb_hw.h"
#ifndef MMIO
#define MMIO(off) (*(volatile uint32_t *)(0x02000200u+(off)))
#endif
static struct usb_device dev;
static uint8_t txbuf[512],rxbuf[512];
static unsigned toggles[3],frames,errors;
static uint8_t in_pid=PID_DATA0;
static int connected;
static uint32_t last_in_reply;
struct screen_state {
    uint32_t control,options,held_lo,held_hi,note_velocity;
};
static struct screen_state displayed_state;
static int displayed_state_valid;
static uint32_t last_frame_complete;
#define SCREEN_KEEPALIVE_MS 1000u
static void disconnect(void) {
    connected=0;
    displayed_state_valid=0;
    // Existing RTL releases held notes and resets LED/display initialization.
    // Audio, HDMI, DDR and AE350 continue running throughout reconnection.
    MMIO(0x00)=0;
}
static void poll_midi(void) {
    if(!connected)return;
    uint8_t pid=0;
    int n=usbhw_transfer_in(PID_IN,dev.address,2,&pid,rxbuf,sizeof rxbuf);
    uint32_t now=usbhw_timer_now();
    // NAK means a live device with no MIDI pending. Do not treat silence or a
    // brief USB EOP/SE0 as disconnection. Missing replies for 50 ms reconnect.
    if(n==USB_RES_NAK || (n>=0 && (pid==PID_DATA0 || pid==PID_DATA1)))last_in_reply=now;
    else if((uint32_t)(now-last_in_reply)>=50)disconnect();
    if(n<0 || pid!=in_pid)return;
    in_pid=in_pid==PID_DATA0?PID_DATA1:PID_DATA0;
    for(int i=0;i+3<n;i+=4)
        MMIO(0x04)=(uint32_t)rxbuf[i]|((uint32_t)rxbuf[i+1]<<8)|
                   ((uint32_t)rxbuf[i+2]<<16)|((uint32_t)rxbuf[i+3]<<24);
}
static int send(unsigned ep,uint8_t *data,unsigned n) {
    int r=USB_RES_TIMEOUT;
    for(unsigned retry=0;retry<1000;retry++) {
        if(!connected)return 0;
        r=usbhw_transfer_out(PID_OUT,dev.address,ep,1,toggles[ep]?PID_DATA1:PID_DATA0,data,n);
        if(r==USB_RES_OK) {toggles[ep]^=1;return 1;}
        if(r==USB_RES_STALL)break;
        if(r!=USB_RES_NAK && retry>=2)break;
        // No recursive OUT calls: RX words go directly to the audio queue.
        poll_midi();delay(1);
    }
    MMIO(0x34)=++errors;return 0;
}
static void lights(void) {
    if(!connected)return;
    uint32_t status=MMIO(0x40);
    if(!(status>>31))return;
    unsigned n=status&1023;
    uint8_t data[16];
    if(n>sizeof data)return;
    MMIO(0x48)=0;
    for(unsigned i=0;i<n;i++)data[i]=MMIO(0x4c);
    if(send(2,data,n))MMIO(0x44)=1;
}
static int screen_changed(void) {
    struct screen_state next;
    next.control=MMIO(0x10);
    next.options=MMIO(0x14);
    next.held_lo=MMIO(0x1c);
    next.held_hi=MMIO(0x20);
    next.note_velocity=MMIO(0x24);
    int changed=!displayed_state_valid ||
        next.control!=displayed_state.control ||
        next.options!=displayed_state.options ||
        next.held_lo!=displayed_state.held_lo ||
        next.held_hi!=displayed_state.held_hi ||
        next.note_velocity!=displayed_state.note_velocity;
    if(changed) {
        displayed_state=next;
        displayed_state_valid=1;
    }
    return changed;
}
static int screen_due(void) {
    return screen_changed() ||
        (uint32_t)(usbhw_timer_now()-last_frame_complete)>=SCREEN_KEEPALIVE_MS;
}
static int frame(void) {
    uint8_t h[16]={0xff,0xcc,0xaa,0x88};
    MMIO(0x08)=1;
    if(!send(1,h,16))return 0;
    for(unsigned packet=0;packet<640;packet++) {
        for(unsigned i=0;i<256;i++) {
            uint16_t p=MMIO(0x2c);
            txbuf[i*2]=(p&255)^0xe7;
            txbuf[i*2+1]=(p>>8)^((i&1)?0xff:0xf3);
        }
        // A complete FS display frame takes hundreds of milliseconds.  Poll
        // MIDI every four packets so pad pressure is serviced throughout the
        // transfer instead of waiting for the next frame boundary.
        if ((packet & 3u)==3u) poll_midi();
        if ((packet & 31u)==31u) lights();
        if(!send(1,txbuf,512))return 0;
    }
    lights();
    last_frame_complete=usbhw_timer_now();
    MMIO(0x30)=++frames;return 1;
}
static void connect(void) {
    disconnect();
    usbhw_hub_enable(1,0);
    while(!usbhw_hub_device_detected())delay(100);
    delay(100);
    if(!usbhw_hub_device_detected())return;
    usbhw_reset();
    if(!usb_configure_device(&dev,1)){delay(250);return;}
    // Observed Push 2 FS fallback: PID 9999, zero advertised interfaces,
    // working EP1 OUT display and EP2 IN/OUT MIDI. Do not reject this quirk.
    if(dev.vid!=0x2982 || (dev.pid!=0x9999 && dev.pid!=0x1967)){delay(250);return;}
    toggles[1]=toggles[2]=0;
    in_pid=PID_DATA0;
    last_in_reply=usbhw_timer_now();connected=1;
    MMIO(0x00)=1;
    // Let the existing RTL scheduler send Live/brightness/strip setup first.
    for(unsigned i=0;i<100 && connected;i++){poll_midi();lights();delay(1);}
}
int main(void) {
    reg_uart_clkdiv=417;
    usbhw_init(0x02000100);
    for(;;) {
        if(!connected){connect();continue;}
        // The exact Push display transport is a 327696-byte full frame.  Do
        // not monopolize the FS bus by retransmitting an unchanged image.
        // With a stable UI this loop polls MIDI at about 1 kHz; a state change
        // schedules one fresh frame while the four-packet polls keep input
        // responsive during that transfer.
        poll_midi();
        lights();
        // Push blanks its display after two seconds without a complete frame.
        // A one-second keepalive preserves a static UI while state changes
        // still schedule a frame immediately when the display link is idle.
        if(screen_due()) {
            if(!frame()) {
                displayed_state_valid=0;
                for(unsigned i=0;i<100 && connected;i++){poll_midi();lights();delay(1);}
            }
        } else delay(1);
    }
}
