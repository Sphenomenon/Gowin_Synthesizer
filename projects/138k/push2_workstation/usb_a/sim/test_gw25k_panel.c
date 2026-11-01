/* Offline execution of production firmware. Only USB, time and MMIO are mocked.
 * The fixture is the actual GW25K 124-byte FS composite descriptor. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static volatile uint32_t regs[64];
static unsigned generic_writes,score_reads;
#ifdef WORKSTATION_WORKER_DEMO
static uint32_t worker_capture[4096];
static unsigned worker_capture_count,worker_capture_pending,worker_capture_enabled;
static FILE *worker_trace;
static unsigned worker_defer_checkpoint;
static void worker_capture_flush(void){
    if(worker_capture_pending){
        assert(worker_capture_count<sizeof worker_capture/sizeof worker_capture[0]);
        uint32_t value=regs[0x54/4];worker_capture[worker_capture_count++]=value;
        if(worker_trace)fprintf(worker_trace,"0 54 %x 0 0 0 0\n",value);
        worker_capture_pending=0;
    }
}
#endif
static volatile uint32_t *reg_at(unsigned off) {
#ifdef WORKSTATION_WORKER_DEMO
    worker_capture_flush();
    if(worker_capture_enabled && off==0x54)worker_capture_pending=1;
#endif
    assert(off < sizeof regs && !(off & 3));
    if(off==0x54) generic_writes++;
    if(off>=0x60 && off<=0x6c) score_reads++;
    return regs+off/4;
}
int usbhw_transfer_out_preloaded(uint8_t,int,int,int,uint8_t,int);
#define MMIO(off) (*reg_at(off))
#define main production_main
#include "../firmware.c"
#undef main

static uint32_t now_ms;
static unsigned descriptor_calls, midi_polls, out_packets, max_out_packet;
static unsigned requests[256], complete_frames, tile_executions, busy_retries;
static unsigned largest_request, largest_response_read, partial_response_reads;
static uint8_t device_out_pid[3], device_in_pid[3];
static uint8_t request_bytes[528], response_bytes[1024];
static unsigned request_used, response_used, response_pos;
static uint32_t device_session, frame_id;
static unsigned control_sequence, display_sequence, device_manual, device_remote, device_redraw;
static unsigned tile_busy_left, end_busy_left, busy_length;
static uint8_t busy_request[528];
static unsigned fragmented_reads=1, inject_midi=1;
static uint32_t last_request_ms, last_health_ms, maximum_health_gap;
static uint32_t last_midi_poll_ms, maximum_midi_gap;
static uint8_t coverage[428*142], notes[16*128];
static unsigned note_on_count, note_off_count, cc123_count;
static unsigned fault, fault_injected, dropped_responses, uncertain_out;
static unsigned packet_in_request, uncertain_injected;
static unsigned duplicate_pending,duplicate_length,duplicate_count,out_nak_left=2,out_naks;
static uint8_t duplicate_data[64],duplicate_pid,nak_packet[64];
static unsigned nak_length;
static unsigned lost_ack_pending,lost_ack_length,lost_ack_duplicates;
static uint8_t lost_ack_data[64],lost_ack_pid;
static unsigned prolonged_ack_loss,reset_calls;
static uint32_t ack_loss_until;
static unsigned must_release_note=128,new_target_note=128;
static const uint8_t gw25k_config[]={
    0x09,0x02,0x7c,0x00,0x03,0x01,0x00,0x80,0x32,
    0x09,0x04,0x00,0x00,0x00,0x01,0x01,0x00,0x00,
    0x09,0x24,0x01,0x00,0x01,0x09,0x00,0x01,0x01,
    0x09,0x04,0x01,0x00,0x02,0x01,0x03,0x00,0x00,
    0x07,0x24,0x01,0x00,0x01,0x41,0x00,
    0x06,0x24,0x02,0x01,0x01,0x00,0x06,0x24,0x02,0x02,0x04,0x00,
    0x09,0x24,0x03,0x01,0x03,0x01,0x04,0x01,0x00,
    0x09,0x24,0x03,0x02,0x02,0x01,0x01,0x01,0x00,
    0x09,0x05,0x01,0x02,0x40,0x00,0x00,0x00,0x00,0x05,0x25,0x01,0x01,0x01,
    0x09,0x05,0x81,0x02,0x40,0x00,0x00,0x00,0x00,0x05,0x25,0x01,0x01,0x03,
    0x09,0x04,0x02,0x00,0x02,0xff,0x00,0x00,0x00,
    0x07,0x05,0x02,0x02,0x40,0x00,0x00,0x07,0x05,0x82,0x02,0x40,0x00,0x00
};
static uint8_t configuration_fixture[256];
static unsigned configuration_size;
static uint16_t fixture_vid=0xfb9a,fixture_pid=0xfb9b;
static unsigned rtl_bridge,rtl_requests;
static uint16_t rd16(const uint8_t *p){return p[0]|((unsigned)p[1]<<8);}
static uint32_t rd32(const uint8_t *p){return rd16(p)|((uint32_t)rd16(p+2)<<16);}
static void wr16(uint8_t *p,unsigned n){p[0]=n;p[1]=n>>8;}
static void wr32(uint8_t *p,uint32_t n){wr16(p,n);wr16(p+2,n>>16);}
static uint16_t crc16(const uint8_t *p,unsigned n){
    uint16_t c=0xffff;
    for(unsigned i=0;i<n;i++){
        c^=(uint16_t)p[i]<<8;
        for(unsigned b=0;b<8;b++)c=(c&0x8000)?(c<<1)^0x1021:c<<1;
    }
    return c;
}
static unsigned flags(void){return device_manual|(device_remote<<1)|(device_redraw<<2);}
static void reply(const uint8_t *r,unsigned type,unsigned length,unsigned status,unsigned page,uint32_t frame){
    assert(response_pos==response_used);
    memcpy(response_bytes,r,16);response_bytes[3]=type;
    memcpy(response_bytes+10,r+8,2);wr16(response_bytes+12,length);
    response_bytes[15]=1;
    memset(response_bytes+16,0,length);
    if(length==8){response_bytes[16]=status;response_bytes[17]=flags();wr16(response_bytes+18,page);wr32(response_bytes+20,frame);}
    response_pos=0;response_used=16+length;
    if(fault && !fault_injected && r[3]==0x02){
        fault_injected=1;
        switch(fault){
            case 1:response_bytes[0]^=1;break;
            case 2:response_bytes[8]^=1;break;
            case 3:response_bytes[14]^=2;break;
            case 4:response_bytes[4]^=1;break;
            case 5:response_bytes[16]=9;break;
            case 6:response_used=19;break; /* incomplete status */
            case 7:response_used=0;dropped_responses++;break;
            case 8:response_bytes[10]^=1;break;
            case 9:wr16(response_bytes+12,513);break;
            case 10:response_bytes[14]|=0x80;break;
            case 11:response_bytes[2]=2;break;
            default:assert(0);
        }
    }
}
static void model_request(const uint8_t *r,unsigned n){
    assert(r[0]=='P' && r[1]=='L' && r[2]==1 && rd32(r+4));
    assert(rd16(r+10)==0 && !(r[14]&~7) && (r[14]&1));
    assert(n==16+rd16(r+12) && rd16(r+12)<=512);
    unsigned type=r[3], seq=rd16(r+8), channel=(r[14]>>1)&3;
    unsigned length=rd16(r+12),page=0,status=0;
    uint32_t frame=0;
    requests[type]++;if(n>largest_request)largest_request=n;
    if(type==1){
        assert(channel==0 && !length);
        assert(!device_session || rd32(r+4)!=device_session);
        device_session=rd32(r+4);control_sequence=(seq+1)&65535;display_sequence=0;
        device_remote=0;device_redraw=1;busy_length=0;frame_id=0;
        memset(coverage,0,sizeof coverage);
        reply(r,0x81,12,0,0,0);
        wr16(response_bytes+16,428);wr16(response_bytes+18,142);
        response_bytes[20]=1;wr16(response_bytes+22,248);wr16(response_bytes+24,512);wr16(response_bytes+26,250);
        return;
    }
    assert(rd32(r+4)==device_session);
    assert(seq==(channel?display_sequence:control_sequence));
    if(type==2){
        assert(channel==0 && !length);
        if(last_health_ms && now_ms-last_health_ms>maximum_health_gap)maximum_health_gap=now_ms-last_health_ms;
        last_health_ms=now_ms;control_sequence=(seq+1)&65535;
        reply(r,0x82,8,0,0,0);return;
    }
    assert(channel==1 && (type==0x20 || type==0x21));
    page=rd16(r+16);frame=rd32(r+20);
    assert(!rd16(r+18));
    unsigned *busy=type==0x20?&tile_busy_left:&end_busy_left;
    if(busy_length){assert(n==busy_length && !memcmp(r,busy_request,n));busy_retries++;}
    if(*busy){
        (*busy)--;memcpy(busy_request,r,n);busy_length=n;
        reply(r,0xa0,8,2,page,frame);return;
    }
    busy_length=0;
    if(device_manual){
        display_sequence=(seq+1)&65535;reply(r,0xa0,8,1,page,frame);return;
    }
    if(type==0x20){
        unsigned x=rd16(r+24),y=rd16(r+26),w=rd16(r+28),h=rd16(r+30);
        assert(w && h && w*h<=248 && x+w<=428 && y+h<=142 && length==16+2*w*h);
        if(frame_id!=frame){frame_id=frame;memset(coverage,0,sizeof coverage);}
        for(unsigned row=0;row<h;row++)for(unsigned col=0;col<w;col++){
            unsigned pos=(y+row)*428+x+col;
            assert(!coverage[pos]);coverage[pos]=1;
        }
        tile_executions++;device_remote=1;
        display_sequence=(seq+1)&65535;reply(r,0xa0,8,status,page,frame);
    }else{
        assert(length==8 && frame==frame_id);
        for(unsigned i=0;i<sizeof coverage;i++)assert(coverage[i]);
        complete_frames++;device_redraw=0;
        display_sequence=(seq+1)&65535;reply(r,0xa1,8,0,page,frame);
    }
}
static void process_request(const uint8_t *r,unsigned n){
    model_request(r,n);
    if(!rtl_bridge)return;
    printf("PL %u ",device_manual);
    for(unsigned i=0;i<n;i++)printf("%02x",r[i]);
    putchar('\n');fflush(stdout);
    char line[4096];assert(fgets(line,sizeof line,stdin));
    size_t length=strcspn(line,"\r\n");assert(!(length&1) && length/2<=64);
    uint8_t actual[64];
    for(unsigned i=0;i<length/2;i++){unsigned v;assert(sscanf(line+2*i,"%2x",&v)==1);actual[i]=(uint8_t)v;}
    assert(length/2==response_used);
    /* Credit is instantaneous tile-buffer availability, unlike the model's
     * permissive one-credit mock. Every other response byte must agree. */
    for(unsigned i=0;i<response_used;i++)if(i!=15)assert(actual[i]==response_bytes[i]);
    memcpy(response_bytes,actual,response_used);rtl_requests++;
}
void delay(int ms){assert(ms>=0);now_ms+=(uint32_t)ms;}
t_time usbhw_timer_now(void){return now_ms;}
void usbhw_init(uint32_t base){assert(base==0x02000100);}
void usbhw_hub_enable(int fs,int sof){assert(fs==1 && sof==0);}
int usbhw_hub_device_detected(void){return 1;}
int usbhw_reset(void){
    reset_calls++;
    device_out_pid[1]=device_out_pid[2]=device_in_pid[1]=device_in_pid[2]=PID_DATA0;
    request_used=response_used=response_pos=duplicate_pending=lost_ack_pending=packet_in_request=0;
    device_session=frame_id=0;device_manual=device_remote=0;device_redraw=1;
    memset(coverage,0,sizeof coverage);memset(notes,0,sizeof notes);return 0;
}
int usb_configure_device(struct usb_device *d,int address){d->address=address;d->vid=fixture_vid;d->pid=fixture_pid;return 1;}
int usb_get_descriptor(struct usb_device *d,uint16_t type,uint16_t index,uint8_t *buf,uint16_t length){
    assert(d==&dev && type==DESC_CONFIGURATION && index==0);descriptor_calls++;
    unsigned n=length<configuration_size?length:configuration_size;memcpy(buf,configuration_fixture,n);return n;
}
int usb_send_control_write(struct usb_device *d,uint8_t type,uint8_t req,uint16_t value,uint16_t index,uint16_t n,uint8_t *data){
    (void)d;(void)type;(void)req;(void)value;(void)index;(void)n;(void)data;assert(0);return 0;
}
int usbhw_transfer_out(uint8_t token,int address,int ep,int handshake,uint8_t pid,uint8_t *buf,int n){
    assert(token==PID_OUT && address==1 && (ep==1 || ep==2) && handshake==1);
    assert(n>=0 && n<=64);
    out_packets++;if((unsigned)n>max_out_packet)max_out_packet=n;now_ms++;
    /* Raw host retries keep the old DATA PID. A device that accepted data but
     * whose ACK was lost acknowledges the duplicate without consuming it. */
    if(ep==2 && lost_ack_pending && pid==lost_ack_pid){
        assert((unsigned)n==lost_ack_length && !memcmp(buf,lost_ack_data,n));
        if(prolonged_ack_loss && now_ms<ack_loss_until)return USB_RES_TIMEOUT;
        lost_ack_pending=0;lost_ack_duplicates++;return USB_RES_OK;
    }
    assert(pid==device_out_pid[ep]);
    if(ep==1){
        assert(!(n&3));
        for(int i=0;i<n;i+=4){
            unsigned cin=buf[i]&15,status=buf[i+1],note=buf[i+2],v=buf[i+3],ch=status&15;
            assert(cin==(status>>4) && note<128 && v<128);
            if(cin==9 && v){
                if(note==new_target_note)for(unsigned c=0;c<16;c++)assert(!notes[c*128+must_release_note]);
                notes[ch*128+note]=1;note_on_count++;
            }
            else if(cin==8 || cin==9){notes[ch*128+note]=0;note_off_count++;}
            else if(cin==11 && (note==120 || note==123)){
                memset(notes+ch*128,0,128);if(note==123)cc123_count++;
            }
        }
    }else{
        if(request_used && now_ms-last_request_ms>=100){request_used=0;packet_in_request=0;}
        assert(response_pos==response_used); /* strict single outstanding request */
        if(out_nak_left && packet_in_request==1 && request_bytes[3]==0x20){
            if(nak_length)assert((unsigned)n==nak_length && !memcmp(buf,nak_packet,n));
            else{nak_length=n;memcpy(nak_packet,buf,n);}
            out_nak_left--;out_naks++;return USB_RES_NAK;
        }
        if(nak_length){assert((unsigned)n==nak_length && !memcmp(buf,nak_packet,n));nak_length=0;}
        assert(request_used+(unsigned)n<=sizeof request_bytes);
        memcpy(request_bytes+request_used,buf,n);request_used+=n;packet_in_request++;last_request_ms=now_ms;
        if(uncertain_out && !uncertain_injected && packet_in_request==3){
            uncertain_injected=1;lost_ack_pending=1;lost_ack_pid=pid;lost_ack_length=n;
            memcpy(lost_ack_data,buf,n);device_out_pid[ep]=pid==PID_DATA0?PID_DATA1:PID_DATA0;
            ack_loss_until=now_ms+180u;
            return USB_RES_TIMEOUT; /* device accepted data, ACK was lost */
        }
        if(request_used>=16){
            unsigned expected=request_bytes[0]=='M'?16:16+rd16(request_bytes+12);
            if(request_used==expected){
                if(request_bytes[0]=='M'){
                    assert(request_bytes[1]=='K' && crc16(request_bytes,14)==rd16(request_bytes+14));
                    assert(response_pos==response_used);memcpy(response_bytes,request_bytes,16);
                    response_bytes[3]|=0x80;wr32(response_bytes+6,0);wr32(response_bytes+10,0);
                    wr16(response_bytes+14,crc16(response_bytes,14));response_pos=0;response_used=16;
                }else process_request(request_bytes,request_used);
                request_used=0;packet_in_request=0;
            }
        }
    }
    device_out_pid[ep]=pid==PID_DATA0?PID_DATA1:PID_DATA0;return USB_RES_OK;
}
int usbhw_transfer_out_preloaded(uint8_t token,int address,int ep,int handshake,uint8_t pid,int n){
    (void)token;(void)address;(void)ep;(void)handshake;(void)pid;(void)n;assert(0);return USB_RES_TIMEOUT;
}
int usbhw_transfer_in(uint8_t token,int address,int ep,uint8_t *pid,uint8_t *buf,int size){
    assert(token==PID_IN && address==1 && (ep==1 || ep==2) && size==64);now_ms++;
    if(ep==1){
        midi_polls++;
        if(last_midi_poll_ms && now_ms-last_midi_poll_ms>maximum_midi_gap)maximum_midi_gap=now_ms-last_midi_poll_ms;
        last_midi_poll_ms=now_ms;
        if(!inject_midi || midi_polls%7)return USB_RES_NAK;
        const uint8_t midi[]={9,0x90,60,100};memcpy(buf,midi,4);*pid=device_in_pid[1];
        device_in_pid[1]=*pid==PID_DATA0?PID_DATA1:PID_DATA0;return 4;
    }
    if(duplicate_pending){
        duplicate_pending=0;memcpy(buf,duplicate_data,duplicate_length);*pid=duplicate_pid;
        duplicate_count++;return duplicate_length;
    }
    if(response_pos==response_used)return USB_RES_NAK;
    unsigned n=response_used-response_pos;
    if(n>(unsigned)size)n=size;
    if(fragmented_reads){unsigned cap=1+(response_pos%7);if(n>cap)n=cap;}
    if(n<response_used-response_pos)partial_response_reads++;
    if(n>largest_response_read)largest_response_read=n;
    memcpy(buf,response_bytes+response_pos,n);
    if(!response_pos){
        memcpy(duplicate_data,buf,n);duplicate_length=n;duplicate_pid=device_in_pid[2];duplicate_pending=1;
    }
    response_pos+=n;*pid=device_in_pid[2];
    device_in_pid[2]=*pid==PID_DATA0?PID_DATA1:PID_DATA0;return n;
}

/* Scenario entry points are below the mock so each test exercises the exact
 * production connect/service functions rather than a parallel PL encoder. */
static void step(void){if(!connected)connect();poll_midi();gw25k_service();delay(1);}
static void wait_frame(unsigned desired){
    unsigned limit=200000;
    while(complete_frames<desired && limit--)step();
    assert(limit && connected && mode==DEVICE_GW25K);
}
static void wait_quiet(void){
    unsigned previous=tile_executions,quiet_since=now_ms,limit=200000;
    while(now_ms-quiet_since<200 && limit--){
        step();
        if(tile_executions!=previous){previous=tile_executions;quiet_since=now_ms;}
    }
    assert(limit);
}
static void partial_frame_health(unsigned minimum_tiles){
    unsigned limit=100000;
    while((tile_executions<minimum_tiles || !gw.drawing || gw.active>=0 ||
           now_ms-gw.last_health<10u) && limit--)step();
    assert(limit && gw.tile_y>0);
}
static void initialize(void){
    memset((void*)regs,0,sizeof regs);memset(notes,0,sizeof notes);
    memcpy(configuration_fixture,gw25k_config,sizeof gw25k_config);configuration_size=sizeof gw25k_config;
    fixture_vid=0xfb9a;fixture_pid=0xfb9b;
    device_out_pid[1]=device_out_pid[2]=PID_DATA0;
    device_in_pid[1]=device_in_pid[2]=PID_DATA0;
    connect();assert(connected && mode==DEVICE_GW25K && regs[0]==7);
    assert(midi_in_ep==1 && midi_in_size==64);
}
static void fixture(void){
    memcpy(configuration_fixture,gw25k_config,sizeof gw25k_config);configuration_size=sizeof gw25k_config;
    fixture_vid=0xfb9a;fixture_pid=0xfb9b;
}
static void generic_fallback(void){
    connect();assert(connected && mode==DEVICE_MIDI && regs[0]==3);
    unsigned before=out_packets;gw25k_service();assert(out_packets==before);
}
static void descriptor_tests(void){
    fixture();fixture_vid=0xfb9b;generic_fallback();
    fixture();fixture_pid=0xfb9a;generic_fallback();
    fixture();configuration_fixture[106]=3;generic_fallback(); /* HID, not vendor */
    fixture();configuration_fixture[104]=1;generic_fallback(); /* alt1 not selected */
    fixture();configuration_fixture[112]=1;generic_fallback(); /* collision with MIDI OUT */
    fixture();configuration_fixture[119]=0x81;generic_fallback(); /* collision with MIDI IN */
    fixture();configuration_fixture[113]=3;generic_fallback(); /* interrupt, not bulk */
    fixture();configuration_fixture[120]=3;generic_fallback();
    fixture();configuration_fixture[114]=0;configuration_fixture[115]=2;generic_fallback(); /* HS512 on FS host */
    fixture();configuration_fixture[121]=0;configuration_fixture[122]=2;generic_fallback();
    fixture();configuration_fixture[114]=0;generic_fallback(); /* MPS0 */
    fixture();configuration_fixture[112]|=0x70;generic_fallback(); /* reserved EP bits */
    fixture();configuration_fixture[119]|=0x70;generic_fallback();
    fixture();configuration_fixture[76]=3;generic_fallback(); /* MIDI OUT is not bulk */
    fixture();configuration_fixture[110]=0;connect();assert(!connected); /* malformed suffix */
    fixture();configuration_size=101;configuration_fixture[2]=101;configuration_fixture[4]=2;generic_fallback();
    fixture();connect();assert(connected && mode==DEVICE_GW25K);
    assert(!gw.panel_out_toggle && !gw.panel_in_toggle && !gw.hello);
}
/* Verify meanings against the established RTL MMIO layout, including the
 * lossy fields. No raw Program/14-bit bend is invented by the renderer. */
static void scene_tests(void){
    static const char *tones[]={"FLUTE  ","STRINGS","BRASS  ","MARIMBA","PIANO  "};
    gw25k_reset();memset((void*)regs,0,sizeof regs);
    regs[0x10/4]=0x80000000u|(2u<<3);
    regs[0x14/4]=128u<<18;
    regs[0x24/4]=60u|(100u<<7);
    gw_scene(gw.scene);gw_format_scene();
    assert(!strcmp(gw.line1,"NOTE 060  VEL 100  GAIN 127  TONE FLUTE  "));
    assert(!strcmp(gw.line2,"MOD 000  BEND IDX 128  FX DCR 000"));
    assert(!strcmp(gw.line3,"MODE C  ACTIVE 000  OUT STEREO"));
    assert(!strcmp(gw.line4,"GLIDE 000  SUSTAIN OFF"));
    for(unsigned cc=0;cc<128;cc++){
        unsigned volume=cc==127?32768u:cc*256u;
        for(unsigned expression=0;expression<2;expression++){
            unsigned gain=expression?volume/2u:volume;
            char expected[4];snprintf(expected,sizeof expected,"%03u",gain>=32768u?127u:gain/256u);
            gw.scene[0]=gain<<16;gw_format_scene();assert(!memcmp(gw.line1+24,expected,3));
        }
    }
    for(unsigned profile=0;profile<8;profile++){
        gw.scene[0]=profile<<7;gw_format_scene();
        assert(!strcmp(gw.line1+34,profile<5?tones[profile]:"UNKNOWN"));
    }
    for(unsigned mode=0;mode<4;mode++){
        gw.scene[0]=mode<<3;gw_format_scene();assert(gw.line3[5]==(char)(mode<3?'A'+mode:'?'));
    }
    static const char *routes[]={"STEREO","LEFT  ","RIGHT ","MUTED "};
    for(unsigned active=0;active<64;active++)for(unsigned route=0;route<4;route++){
        char expected[4];snprintf(expected,sizeof expected,"%03u",active);
        gw.scene[0]=(active<<10)|(route<<5);gw_format_scene();
        assert(!memcmp(gw.line3+15,expected,3) && !strcmp(gw.line3+24,routes[route]));
    }
    for(unsigned glide=0;glide<128;glide++)for(unsigned sustain=0;sustain<2;sustain++){
        char expected[4];snprintf(expected,sizeof expected,"%03u",glide);
        gw.scene[1]=(glide<<11)|(sustain<<3);gw_format_scene();
        assert(!memcmp(gw.line4+6,expected,3) && !memcmp(gw.line4+19,sustain?"ON ":"OFF",3));
    }
    for(unsigned bend=0;bend<256;bend++){
        char expected[4];snprintf(expected,sizeof expected,"%03u",bend);
        gw.scene[1]=(bend<<18)|(127u<<4);gw_format_scene();
        assert(!memcmp(gw.line2+18,expected,3) && !memcmp(gw.line2+4,"127",3));
    }
    for(unsigned mask=0;mask<8;mask++){
        gw.scene[0]=mask;gw_format_scene();
        for(unsigned bit=0;bit<3;bit++)assert(gw.line2[30+bit]==(char)('0'+((mask>>bit)&1u)));
    }
    for(unsigned key=0;key<16;key++){
        gw.scene[2]=1u<<(48u+key-36u);gw.scene[3]=0;
        for(unsigned k=0;k<16;k++)assert(gw_pixel(7u+k*26u,110)==(k==key?0xffff:0x2945));
    }
    /* A NoteOff/velocity-zero update clears the last-event velocity; the
     * held keyboard is read separately from the audio snapshot. */
    gw.scene[4]=63;gw_format_scene();assert(!memcmp(gw.line1+5,"063",3));
    assert(!memcmp(gw.line1+14,"000",3));
    /* A whole PL frame, including regenerated tiles, must use the original
     * snapshot. A state change is visible only when the next frame starts. */
    gw.drawing=0;gw_prepare_display();
    uint32_t original[9];memcpy(original,gw.scene,sizeof original);
    char status3[sizeof gw.line3],status4[sizeof gw.line4];
    memcpy(status3,gw.line3,sizeof status3);memcpy(status4,gw.line4,sizeof status4);
    uint8_t first_tile[528];unsigned tile_length=gw.transaction[1].length;
    memcpy(first_tile,gw.transaction[1].data,tile_length);
    regs[0x10/4]=(64u<<24)|(4u<<7)|(17u<<10)|(3u<<5)|7u;
    regs[0x14/4]=(255u<<18)|(73u<<4)|(91u<<11)|8u;
    regs[0x1c/4]=1u<<27;regs[0x20/4]=0xffffffffu;regs[0x24/4]=63;
    gw_prepare_display();assert(!memcmp(original,gw.scene,sizeof original));
    assert(!memcmp(status3,gw.line3,sizeof status3) && !memcmp(status4,gw.line4,sizeof status4));
    assert(gw.transaction[1].length==tile_length && !memcmp(first_tile,gw.transaction[1].data,tile_length));
    gw.tile_y=GW_HEIGHT;gw_prepare_display();
    assert(gw.transaction[1].type==GW_END && !memcmp(original,gw.scene,sizeof original));
    gw.drawing=0;gw_prepare_display();
    assert(gw.scene[0]==regs[0x10/4] && gw.scene[1]==regs[0x14/4]);
    assert(gw.scene[2]==regs[0x1c/4] && gw.scene[3]==regs[0x20/4] && gw.scene[4]==63);
    for(unsigned i=5;i<9;i++)assert(!gw.scene[i]);
    assert(!memcmp(gw.line1+24,"064",3) && !strcmp(gw.line1+34,"PIANO  "));
    assert(!strcmp(gw.line2,"MOD 073  BEND IDX 255  FX DCR 111"));
    assert(!strcmp(gw.line3,"MODE A  ACTIVE 017  OUT MUTED "));
    assert(!strcmp(gw.line4,"GLIDE 091  SUSTAIN ON "));
    printf("PASS GW25K scene: effective gain/CC11, five profiles, committed ABC, bend index 0..255, effective DCR mask, 16 held keys, last-event release, immutable frame/next-frame refresh, 64 active-count encodings, four output routes, glide 0..127 and sustain\n");
}
static void refresh_scene_tests(void){
    static const unsigned offsets[]={0x10,0x10,0x10,0x10,0x14,0x14,0x1c,0x20,0x24,0x10,0x10,0x14,0x14};
    static const uint32_t values[]={0x80000010u,0x40000210u,0x40000208u,0x4000020du,
        255u<<18,(128u<<18)|(73u<<4),1u<<12,1u<<3,60u|(100u<<7),
        0x4000020du|(2u<<10),0x4000020du|(2u<<10)|(3u<<5),
        (128u<<18)|(73u<<4)|(91u<<11),(128u<<18)|(73u<<4)|(91u<<11)|8u};
    /* Independently change gain/profile/mode/FX, bend/modulation, both held
     * words and last note/velocity through the real service loop. Each stable
     * change needs one complete frame, with no periodic idle redraw. */
    for(unsigned i=0;i<sizeof offsets/sizeof offsets[0];i++){
        wait_quiet();unsigned frames=complete_frames;
        assert(regs[offsets[i]/4]!=values[i]);regs[offsets[i]/4]=values[i];
        wait_frame(frames+1);wait_quiet();assert(complete_frames==frames+1);
        assert(gw.scene[0]==regs[0x10/4] && gw.scene[1]==regs[0x14/4]);
        assert(gw.scene[2]==regs[0x1c/4] && gw.scene[3]==regs[0x20/4] && gw.scene[4]==regs[0x24/4]);
    }
    assert(!score_reads && !note_on_count && !note_off_count && !cc123_count);
    printf("PASS GW25K refresh: 13 independent MMIO changes each trigger one complete frame; stable state only heartbeats\n");
}
static void render_scene(const char *path){
    gw25k_reset();
    gw.scene[0]=(100u<<24)|(2u<<7)|(2u<<3)|(2u<<10)|5u;gw.scene[1]=(73u<<4)|(128u<<18)|(73u<<11)|8u;
    gw.scene[2]=(1u<<(48-36))|(1u<<(50-36));gw.scene[4]=60u|(100u<<7);
    gw.scene[5]=60u|(1u<<7)|(1u<<8)|(1u<<9)|(1u<<10)|(12u<<17)|(1u<<22);
    gw.scene[7]=(42u<<16)|7u;gw.scene[8]=3;gw_format_scene();
    assert(!strcmp(gw.line1,"NOTE 060  VEL 100  GAIN 100  TONE BRASS  "));
    assert(!strcmp(gw.line2,"MOD 073  BEND IDX 128  FX DCR 101"));
    assert(!strcmp(gw.line3,"MODE C  ACTIVE 002  OUT STEREO"));
    assert(!strcmp(gw.line4,"GLIDE 073  SUSTAIN ON "));
    gw.scene[0]=0x80000000u;gw_format_scene();
    assert(!strncmp(gw.line1+24,"127",3));
    gw.scene[0]=(100u<<24)|(2u<<7)|(2u<<3)|(2u<<10)|5u;gw_format_scene();
    FILE *f=fopen(path,"wb");assert(f);fprintf(f,"P6\n428 142\n255\n");
    for(unsigned y=0;y<142;y++)for(unsigned x=0;x<428;x++){
        unsigned pixel=gw_pixel(x,y);uint8_t rgb[3]={
            (uint8_t)((pixel>>11)*255u/31u),(uint8_t)(((pixel>>5)&63u)*255u/63u),(uint8_t)((pixel&31u)*255u/31u)};
        assert(fwrite(rgb,1,3,f)==3);
    }
    assert(!fclose(f));
}
static void audio_feedback_test(const char *path){
    FILE *f=fopen(path,"r");assert(f);
    unsigned id,control,options,note_velocity,mode,active,route,glide,sustain,rows=0;
    static const char *routes[]={"STEREO","LEFT  ","RIGHT ","MUTED "};
    initialize();inject_midi=0;unsigned baseline_writes=generic_writes;
    for(;;){
        int n=fscanf(f,"%u %x %x %x %u %u %u %u %u",&id,&control,&options,&note_velocity,
                     &mode,&active,&route,&glide,&sustain);
        if(n==EOF)break;
        assert(n==9 && id==rows && mode<3 && active<64 && route<4 && glide<128 && sustain<2);
        wait_quiet();unsigned frames=complete_frames;
        regs[0x10/4]=control;regs[0x14/4]=options;regs[0x24/4]=note_velocity;
        gw.dirty=1;wait_frame(frames+1);wait_quiet();
        char expected3[sizeof gw.line3],expected4[sizeof gw.line4];
        snprintf(expected3,sizeof expected3,"MODE %c  ACTIVE %03u  OUT %s",'A'+mode,active,routes[route]);
        snprintf(expected4,sizeof expected4,"GLIDE %03u  SUSTAIN %s",glide,sustain?"ON ":"OFF");
        assert(!strcmp(gw.line3,expected3) && !strcmp(gw.line4,expected4));
        assert(gw.scene[0]==control && gw.scene[1]==options);
        assert(generic_writes==baseline_writes && !score_reads && !requests[0x10]);
        printf("RTL FEEDBACK %02u: %s / %s\n",id,gw.line3,gw.line4);rows++;
    }
    fclose(f);assert(rows==12);
    printf("PASS production Host consumes 12 real RTL feedback captures: committed mode, release-tail voices, four audio routes, glide, sustain, reconnect defaults; no input echo\n");
}
#ifdef WORKSTATION_WORKER_DEMO
static void worker_state(unsigned crush,unsigned drive,unsigned send,unsigned mask){
    if(worker_trace && !worker_defer_checkpoint)fprintf(worker_trace,"1 0 0 %x %x %x %x\n",crush,drive,send,mask);
}
static void worker_connection(void){
    if(worker_trace)fprintf(worker_trace,"0 0 %x 0 0 0 0\n",regs[0]);
    worker_state(0,0,0,0);
}
static void worker_midi(unsigned key,unsigned down,unsigned crush,unsigned drive,unsigned send,unsigned mask,unsigned emit){
    uint8_t p[4]={down?9:8,down?0x90:0x80,(uint8_t)(48+key),down?100:0};
    unsigned before=generic_writes,captured=worker_capture_count;forward_midi(p);worker_capture_flush();
    assert(generic_writes==before+emit && worker_capture_count==captured+emit);
    if(emit==4){
        const unsigned cc[]={20,21,22,81},value[]={crush,drive,send,mask};
        for(unsigned i=0;i<4;i++)assert(worker_capture[captured+i]==((2u<<14)|(cc[i]<<7)|value[i]));
    }else if(emit==1)assert(key==15 && down && worker_capture[captured]==((2u<<14)|(7u<<7)|127u));
    else assert(!emit);
    worker_state(crush,drive,send,mask);
}
static void worker_panic(unsigned cc){
    const uint8_t p[]={11,0xb0,(uint8_t)cc,0};unsigned before=generic_writes;
    forward_midi(p);worker_capture_flush();assert(generic_writes==before+1);
    assert(regs[0x54/4]==((2u<<14)|(120u<<7)) && !worker_keys);
    worker_state(0,0,0,0);
}
static void worker_demo_tests(void){
    static const unsigned pad_mask[]={0,0,0,1,2,4,7,0,1,2,3,4,5,6,7,0};
    initialize();inject_midi=0;worker_capture_enabled=1;worker_connection();
    for(unsigned key=0;key<16;key++){
        unsigned c=key==0?100:0,d=key==1?100:0,s=key==2?100:0;
        worker_midi(key,1,c,d,s,pad_mask[key],key==15?1:4);
        worker_midi(key,1,c,d,s,pad_mask[key],0);
        worker_midi(key,0,0,0,0,0,key==15?0:4);
        worker_midi(key,0,0,0,0,0,0);
    }
    /* Independent explicit overlapping masks: releasing a contributor cannot
     * remove the same effect requested by another still-held key. */
    worker_midi(3,1,0,0,0,1,4);worker_midi(4,1,0,0,0,3,4);
    worker_midi(8,1,0,0,0,3,4);worker_midi(3,0,0,0,0,3,4);
    worker_midi(4,0,0,0,0,1,4);worker_midi(8,0,0,0,0,0,4);
    worker_midi(0,1,100,0,0,0,4);worker_midi(1,1,100,100,0,0,4);
    worker_midi(2,1,100,100,100,0,4);worker_midi(6,1,100,100,100,7,4);
    worker_midi(7,1,0,0,0,0,4);worker_midi(0,0,0,0,0,0,4);
    worker_midi(9,1,0,0,0,0,4);worker_midi(7,0,0,100,100,7,4);
    worker_midi(6,0,0,100,100,2,4);worker_midi(9,0,0,100,100,0,4);
    worker_midi(1,0,0,0,100,0,4);worker_midi(2,0,0,0,0,0,4);
    /* Velocity-zero NoteOn is also a release on the unchanged MIDI wire. */
    worker_midi(5,1,0,0,0,4,4);
    const uint8_t zero_on[]={9,0x90,53,0};unsigned zero_before=generic_writes;
    forward_midi(zero_on);worker_capture_flush();assert(generic_writes==zero_before+4);
    assert(regs[0x54/4]==((2u<<14)|(81u<<7)));worker_state(0,0,0,0);
    for(unsigned cc=120;cc<=123;cc+=3){
        worker_midi(0,1,100,0,0,0,4);worker_midi(6,1,100,0,0,7,4);
        worker_panic(cc);assert(worker_blocked_keys==((1u<<0)|(1u<<6)));
        worker_midi(0,1,0,0,0,0,0); // a held retransmission cannot undo PANIC
        worker_midi(4,1,0,0,0,2,4);
        worker_midi(0,0,0,0,0,2,0);worker_midi(6,0,0,0,0,2,0);
        worker_midi(4,0,0,0,0,0,4);assert(!worker_blocked_keys);
    }
    worker_defer_checkpoint=1;
    worker_midi(0,1,100,0,0,0,4);worker_midi(14,1,100,0,0,7,4);
    disconnect();worker_defer_checkpoint=0;worker_connection();assert(!worker_keys && !worker_blocked_keys);
    connect();worker_connection();worker_midi(14,0,0,0,0,0,0);
    worker_midi(0,1,100,0,0,0,4);worker_midi(0,0,0,0,0,0,4);
    if(worker_trace)fprintf(worker_trace,"2 0 1 0 0 0 0\n");
    worker_midi(1,1,0,100,0,0,4);worker_midi(1,0,0,0,0,0,4);
    worker_midi(14,1,0,0,0,7,4);worker_midi(14,0,0,0,0,0,4);
    if(worker_trace)fprintf(worker_trace,"2 0 0 0 0 0 0\n");
    worker_capture_enabled=0;
    unsigned before=generic_writes;
    const uint8_t program[]={12,0xc0,73,0},mode_cc[]={11,0xb0,89,1},outside[]={9,0x90,47,100};
    forward_midi(program);forward_midi(mode_cc);forward_midi(outside);assert(generic_writes==before);
    const uint8_t volume[]={11,0xb0,7,73};forward_midi(volume);
    assert(regs[0x54/4]==((2u<<14)|(7u<<7)|73u));
    /* Press state is interaction bookkeeping only: no UI echo before actual
     * audio feedback. A late commit changes the following complete PL frame. */
    regs[0x10/4]=0x80000000u|(3u<<3)|5u;
    regs[0x14/4]=17u|(64u<<7)|(101u<<14);
    wait_frame(1);wait_quiet();
    assert(!strcmp(gw.line1,"D STREAM  GAIN 127  OUT STEREO"));
    assert(!strcmp(gw.line2,"CRUSH 017 DRIVE 064 SEND 101"));
    assert(!strcmp(gw.line3,"FX DCR 101  TOUCH A-C HOLD"));
    worker_capture_enabled=1;FILE *saved_trace=worker_trace;worker_trace=NULL;
    worker_midi(0,1,100,0,0,0,4);worker_capture_enabled=0;worker_trace=saved_trace;
    unsigned frames_before=complete_frames;wait_quiet();assert(complete_frames==frames_before);
    assert(!strcmp(gw.line2,"CRUSH 017 DRIVE 064 SEND 101"));
    regs[0x14/4]=100u|(64u<<7)|(101u<<14);
    wait_frame(frames_before+1);wait_quiet();
    assert(!strcmp(gw.line2,"CRUSH 100 DRIVE 064 SEND 101"));
    disconnect();assert(!worker_keys && !worker_blocked_keys);connect();
    fixture();fixture_vid=0x2982;fixture_pid=0x1967;connect();
    assert(!connected && mode==DEVICE_NONE && !regs[0]);
    fixture();fixture_vid=1;connect();assert(!connected && mode==DEVICE_NONE);
    assert(!score_reads && !note_on_count && !note_off_count && !cc123_count);
    printf("PASS W-DEMO USB: 16 touch mappings, all momentary effects, overlapping masks/dry restore, duplicate and zero-velocity release, PANIC held-key fence, reconnect, committed feedback and PL frames\n");
}
#endif
int main(int argc,char **argv){
#ifdef WORKSTATION_WORKER_DEMO
    if(argc==1 || (argc==3 && !strcmp(argv[1],"--worker-touch-trace"))){
        if(argc==3){worker_trace=fopen(argv[2],"w");assert(worker_trace);}
        worker_demo_tests();
        if(worker_trace)assert(!fclose(worker_trace));
        return 0;
    }
#endif
    if(argc==3 && !strcmp(argv[1],"--render")){render_scene(argv[2]);return 0;}
    if(argc==3 && !strcmp(argv[1],"--audio-feedback")){audio_feedback_test(argv[2]);return 0;}
    if(argc==2 && !strcmp(argv[1],"--rtl")){
        rtl_bridge=1;out_nak_left=0;initialize();wait_frame(1);wait_quiet();
        device_manual=1;device_remote=0;device_redraw=1;
        unsigned before=now_ms;while(now_ms-before<200)step();assert(gw.manual);
        device_manual=0;frame_id=0;wait_frame(2);wait_quiet();
        printf("PASS production host + actual GW25K RTL endpoint: %u requests, %u full frames, HELLO/TILE/END/DRAWN/manual/resume\n",rtl_requests,complete_frames);
        return 0;
    }
    scene_tests();
    assert(sizeof gw25k_config==124);
    initialize();tile_busy_left=2;end_busy_left=2;
    wait_frame(1);
    assert(requests[1]==1 && requests[0x20]>1 && requests[0x21]>=3);
    assert(busy_retries==4 && max_out_packet==64 && largest_request>64);
    assert(partial_response_reads && duplicate_count && out_naks==2 && generic_writes && midi_polls>out_packets/4);
    /* Push score changes must neither read score MMIO nor produce MIDI OUT
     * feedback on the GW25K target. PL and incoming performance remain live. */
    assert(!note_on_count && !note_off_count && !cc123_count && !score_reads);
    refresh_scene_tests();
    unsigned before_score=tile_executions;
    regs[0x60/4]=60 | (1u<<7) | (1u<<8) | (1u<<9);
    regs[0x64/4]=(1u<<(48-36))|(1u<<(63-36));
    regs[0x68/4]=0x12345678;regs[0x6c/4]=3;
    unsigned score_start=now_ms;while(now_ms-score_start<650)step();
    assert(!note_on_count && !note_off_count && !cc123_count && !score_reads);
    assert(tile_executions==before_score);
    wait_quiet();
    unsigned tiles=tile_executions,heartbeats=requests[2],before=now_ms;
    while(now_ms-before<500)step();
    assert(requests[2]>heartbeats && tile_executions==tiles);
    /* The adversarial 1..7-byte USB packets include duplicated DATA and use
     * milliseconds per transaction. Never interleave a HEALTH inside an
     * outstanding PL request; even this schedule must stay below 250 ms. */
    assert(maximum_health_gap<=150);
    assert(maximum_midi_gap<=10); /* display work never monopolizes MIDI */
    /* Manual settings must stop pixels, but keep the session alive. Releasing
     * the manual page invalidates the previous canvas and requires every pixel. */
    device_manual=1;device_remote=0;device_redraw=1;
    before=now_ms;while(now_ms-before<200)step();
    tiles=tile_executions;heartbeats=requests[2];
    before=now_ms;while(now_ms-before<200)step();
    assert(tile_executions==tiles && requests[2]>heartbeats);
    device_manual=0;frame_id=0;wait_frame(complete_frames+1);
    assert(tile_executions>tiles);
    /* A local-page override halfway through a frame invalidates its partial
     * canvas. Resuming must begin a new frame at (0,0), not continue the tail. */
    wait_quiet();tiles=tile_executions;regs[0x14/4]++;
    partial_frame_health(tiles+10);device_manual=1;device_remote=0;device_redraw=1;
    before=now_ms;while(!gw.manual && now_ms-before<300)step();
    assert(gw.manual && !gw.drawing && !gw.transaction[1].used);
    tiles=tile_executions;before=now_ms;while(now_ms-before<200)step();assert(tiles==tile_executions);
    device_manual=0;frame_id=0;wait_frame(complete_frames+1);
    /* A remote canvas lost without a manual gesture needs the same restart. */
    wait_quiet();tiles=tile_executions;regs[0x14/4]++;
    partial_frame_health(tiles+10);device_remote=0;device_redraw=1;
    wait_frame(complete_frames+1);
    /* Malformed/truncated/absent responses must abandon the session; no bytes
     * from the old response may be mistaken for a matching current reply. */
    for(unsigned f=1;f<=11;f++){
        fault=f;fault_injected=0;unsigned hellos=requests[1];before=now_ms;
        while((requests[1]==hellos || !fault_injected) && now_ms-before<4000)step();
        assert(fault_injected && requests[1]>hellos);
        fault=0;frame_id=0;wait_frame(complete_frames+1);
    }
    /* A raw USB host knows the exact DATA PID boundary. A lost ACK must retry
     * the same fragment/PID; the USB receiver deduplicates it, preserving the
     * current PL session and every subsequent tile's byte offset. */
    wait_quiet();
    uncertain_out=1;uncertain_injected=0;
    unsigned hellos=requests[1],desired=complete_frames+1;regs[0x14/4]++;
    wait_frame(desired);
    assert(uncertain_injected && lost_ack_duplicates==1 && requests[1]==hellos);
    uncertain_out=0;
    /* Repeatedly missing ACKs leave the endpoint toggle outcome unknown.
     * Re-enumeration must reset both USB PIDs and the incomplete PL stream;
     * the old session's unsent tail must never reach the fresh parser. */
    wait_quiet();uncertain_out=1;uncertain_injected=0;prolonged_ack_loss=1;
    hellos=requests[1];unsigned resets=reset_calls;desired=complete_frames+1;
    regs[0x14/4]++;wait_frame(desired);
    assert(uncertain_injected && reset_calls>resets && requests[1]>hellos);
    uncertain_out=prolonged_ack_loss=0;
    descriptor_tests();
    printf("PASS GW25K production host: actual composite descriptor, PL FS fragmentation, independent DATA toggles, duplicate IN/OUT NAK, full RGB565 coverage, BUSY retry, MIDI interleave/no score feedback, manual/redraw, static heartbeat, 11 response faults (%u frames, %u tiles, %u MIDI polls)\n",complete_frames,tile_executions,midi_polls);
    return 0;
}
