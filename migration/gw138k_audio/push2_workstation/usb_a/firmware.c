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
static uint8_t rxbuf[512];
static unsigned toggles[3],frames,out_errors;
// P138 has one 32-bit USB IN diagnostic word.  Keep four independent,
// saturating byte counters so a long idle NAK stream cannot wrap into a
// misleading zero: [31:24] disconnects, [23:16] NAKs,
// [15:8] duplicate DATA packets, [7:0] transfer/protocol errors.
static uint8_t in_naks,in_duplicates,in_errors,in_disconnects;
static uint8_t in_pid=PID_DATA0;
static int connected;
enum device_mode { DEVICE_NONE, DEVICE_PUSH, DEVICE_MIDI };
static enum device_mode mode;
static unsigned midi_in_ep,midi_in_size;
static uint32_t last_in_reply;
static void publish_in_diagnostics(void) {
    MMIO(0x58)=((uint32_t)in_disconnects<<24)|((uint32_t)in_naks<<16)|
               ((uint32_t)in_duplicates<<8)|in_errors;
}
static void bump_in_diagnostic(uint8_t *counter) {
    if(*counter!=255) {
        ++*counter;
        publish_in_diagnostics();
    }
}
struct screen_state {
    uint32_t control,options,held_lo,held_hi,note_velocity;
};
static struct screen_state displayed_state;
static int displayed_state_valid;
static uint32_t last_frame_complete;
#define SCREEN_KEEPALIVE_MS 1000u
static void disconnect(void) {
    connected=0;
    mode=DEVICE_NONE;
    displayed_state_valid=0;
    // Existing RTL releases held notes and resets LED/display initialization.
    // Audio, HDMI, DDR and AE350 continue running throughout reconnection.
    MMIO(0x00)=0;
}
// Keep the accepted Host/control-transfer implementation. Only walk the
// selected configuration here: usb_enumerate() loses alternate-setting IDs.
// Reserve one RX FIFO of padding because the old control reader copies a
// whole last packet before returning its length. Oversized replies are rejected.
#define MIDI_CONFIG_LIMIT 2048u
static uint8_t configuration[MIDI_CONFIG_LIMIT+512];
static unsigned le16(const uint8_t *p) {return p[0]|((unsigned)p[1]<<8);}
static int find_midi_in(void) {
    int n=usb_get_descriptor(&dev,DESC_CONFIGURATION,0,configuration,9);
    if(n!=9 || configuration[0]!=9 || configuration[1]!=DESC_CONFIGURATION)return 0;
    unsigned total=le16(configuration+2);
    if(total<9 || total>MIDI_CONFIG_LIMIT)return 0;
    n=usb_get_descriptor(&dev,DESC_CONFIGURATION,0,configuration,total);
    if(n!=(int)total || configuration[0]!=9 || configuration[1]!=DESC_CONFIGURATION ||
       le16(configuration+2)!=total)return 0;
    unsigned midi=0,version=0,number=0,alt=0,ep=0,size=0,chosen_number=0,chosen_alt=0;
    for(unsigned off=9;off<total;) {
        if(total-off<2)return 0;
        const uint8_t *d=configuration+off;
        unsigned len=d[0];
        if(len<2 || len>total-off)return 0;
        if(d[1]==DESC_INTERFACE) {
            if(len<9)return 0;
            // Audio / MIDIStreaming / MIDI 1.0, not HID or MIDI 2.0.
            midi=d[5]==1 && d[6]==3 && d[7]==0;
            version=0;number=d[2];alt=d[3];
        } else if(d[1]==0x24 && midi) {
            if(len<3)return 0;
            if(d[2]==1) {
                if(len<7)return 0;
                version=le16(d+3)==0x0100;
            }
        } else if(d[1]==DESC_ENDPOINT) {
            if(len<7)return 0;
            unsigned packet=le16(d+4);
            if(!ep && midi && version && (d[2]&0x80) && !(d[2]&0x70) &&
               (d[2]&15) && (d[3]&3)==ENDPOINT_TYPE_BULK &&
               (packet==8 || packet==16 || packet==32 || packet==64)) {
                ep=d[2]&15;size=packet;chosen_number=number;chosen_alt=alt;
            }
        }
        off+=len;
    }
    if(!ep)return 0;
    // Alt 0 is selected by SET_CONFIGURATION; other alts need only this
    // standard request. Never send Push/vendor initialization to generic MIDI.
    if(chosen_alt && !usb_send_control_write(&dev,REQREC_INTERFACE,REQ_SET_INTERFACE,
                                            chosen_alt,chosen_number,0,0))return 0;
    midi_in_ep=ep;midi_in_size=size;
    return 1;
}
static void forward_midi(const uint8_t *p) {
    if(mode==DEVICE_PUSH) {
        MMIO(0x04)=(uint32_t)p[0]|((uint32_t)p[1]<<8)|
                   ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
        return;
    }
    // Generic channel messages go straight to the workstation {kind,a,b}
    // queue. Preserve 0..127 notes/velocity and merge channels/cables into its
    // existing single instrument; no Push pad range, force curve or CC remap.
    unsigned cin=p[0]&15,a=p[2],b=p[3],kind;
    if(cin<8 || cin>14 || cin!=(p[1]>>4) || a>127 ||
       (cin!=12 && cin!=13 && b>127))return;
    switch(cin) {
        case 8:kind=0;break;
        case 9:kind=b?1:0;break;
        case 10:kind=5;break;
        case 11:kind=2;break;
        case 12:kind=3;b=0;break;
        case 14:kind=4;break;
        default:return; // channel pressure, SysEx/realtime: no core mapping
    }
    MMIO(0x54)=(kind<<14)|(a<<7)|b;
}
static void poll_midi(void) {
    if(!connected)return;
    uint8_t pid=0;
    int n=usbhw_transfer_in(PID_IN,dev.address,midi_in_ep,&pid,rxbuf,midi_in_size);
    uint32_t now=usbhw_timer_now();
    // NAK means a live device with no MIDI pending. Do not treat silence or a
    // brief USB EOP/SE0 as disconnection. Missing replies for 50 ms reconnect.
    if(n==USB_RES_NAK) {
        bump_in_diagnostic(&in_naks);
        last_in_reply=now;
        return;
    }
    if(n<0) {
        bump_in_diagnostic(&in_errors);
        if((uint32_t)(now-last_in_reply)>=50) {
            bump_in_diagnostic(&in_disconnects);
            disconnect();
        }
        return;
    }
    if(pid!=PID_DATA0 && pid!=PID_DATA1) {
        bump_in_diagnostic(&in_errors);
        if((uint32_t)(now-last_in_reply)>=50) {
            bump_in_diagnostic(&in_disconnects);
            disconnect();
        }
        return;
    }
    last_in_reply=now;
    if(pid!=in_pid) {
        bump_in_diagnostic(&in_duplicates);
        return;
    }
    in_pid=in_pid==PID_DATA0?PID_DATA1:PID_DATA0;
    if(n>(int)midi_in_size || (mode==DEVICE_MIDI && (n&3))) {
        bump_in_diagnostic(&in_errors);
        return;
    }
    for(int i=0;i+3<n;i+=4)forward_midi(rxbuf+i);
}
// screen_packet < 0 uses the ordinary byte buffer for headers and MIDI.
static int send_packet(unsigned ep,uint8_t *data,unsigned n,int screen_packet) {
    if(mode!=DEVICE_PUSH)return 0;
    int r=USB_RES_TIMEOUT;
    for(unsigned retry=0;retry<1000;retry++) {
        if(!connected)return 0;
        if(screen_packet>=0) {
            MMIO(0x28)=(unsigned)screen_packet<<8;
            // Blocking store: load 256 encoded pixels through the existing
            // USB register handshake, then return with the TX FIFO full.
            MMIO(0x50)=1;
            r=usbhw_transfer_out_preloaded(PID_OUT,dev.address,ep,1,toggles[ep]?PID_DATA1:PID_DATA0,n);
        } else {
            r=usbhw_transfer_out(PID_OUT,dev.address,ep,1,toggles[ep]?PID_DATA1:PID_DATA0,data,n);
        }
        if(r==USB_RES_OK) {toggles[ep]^=1;return 1;}
        if(r==USB_RES_STALL)break;
        if(r!=USB_RES_NAK && retry>=2)break;
        // No recursive OUT calls: RX words go directly to the audio queue.
        poll_midi();delay(1);
    }
    MMIO(0x34)=++out_errors;return 0;
}
static int send(unsigned ep,uint8_t *data,unsigned n) {
    return send_packet(ep,data,n,-1);
}
static void lights(void) {
    if(!connected || mode!=DEVICE_PUSH)return;
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
static int urgent_screen_changed(void) {
    if(!displayed_state_valid)return 1;
    return MMIO(0x10)!=displayed_state.control ||
        MMIO(0x14)!=displayed_state.options ||
        MMIO(0x1c)!=displayed_state.held_lo ||
        MMIO(0x20)!=displayed_state.held_hi;
}
static int screen_due(void) {
    return screen_changed() ||
        (uint32_t)(usbhw_timer_now()-last_frame_complete)>=SCREEN_KEEPALIVE_MS;
}
// Return 2 when a discrete UI change makes the partially transmitted frame
// stale. The caller starts again with the normal documented frame header;
// incomplete pixels never become visible on Push's double-buffered display.
static int frame(void) {
    if(!connected || mode!=DEVICE_PUSH)return 0;
    uint8_t h[16]={0xff,0xcc,0xaa,0x88};
    if(!displayed_state_valid)screen_changed();
    MMIO(0x08)=1;
    if(!send(1,h,16))return 0;
    for(unsigned packet=0;packet<640;packet++) {
        // A complete FS display frame takes hundreds of milliseconds.  Poll
        // MIDI every four packets so pad pressure is serviced throughout the
        // transfer instead of waiting for the next frame boundary.
        if ((packet & 3u)==3u) {
            poll_midi();
            if(urgent_screen_changed())return 2;
        }
        if ((packet & 31u)==31u) lights();
        if(!send_packet(1,0,512,(int)packet))return 0;
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
    if(dev.vid==0x2982 && (dev.pid==0x9999 || dev.pid==0x1967)) {
        mode=DEVICE_PUSH;midi_in_ep=2;midi_in_size=sizeof rxbuf;
    } else {
        if(!find_midi_in()){delay(250);return;}
        mode=DEVICE_MIDI;
    }
    toggles[1]=toggles[2]=0;
    in_pid=PID_DATA0;
    last_in_reply=usbhw_timer_now();connected=1;
    MMIO(0x00)=mode==DEVICE_PUSH?1:3; // bit 0 connected; bit 1 generic MIDI
    // Let the existing RTL scheduler send Live/brightness/strip setup first.
    if(mode==DEVICE_PUSH)
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
        if(mode!=DEVICE_PUSH){delay(1);continue;}
        lights();
        // Push blanks its display after two seconds without a complete frame.
        // A one-second keepalive preserves a static UI while state changes
        // still schedule a frame immediately when the display link is idle.
        if(screen_due()) {
            int frame_result=frame();
            if(frame_result==2) {
                displayed_state_valid=0;
            } else if(!frame_result) {
                displayed_state_valid=0;
                for(unsigned i=0;i<100 && connected;i++){poll_midi();lights();delay(1);}
            }
        } else delay(1);
    }
}
