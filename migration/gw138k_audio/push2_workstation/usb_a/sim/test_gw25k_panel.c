/* Offline execution of production firmware. Only USB, time and MMIO are mocked.
 * The fixture is the actual GW25K 124-byte FS composite descriptor. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static volatile uint32_t regs[64];
static unsigned generic_writes;
static volatile uint32_t *reg_at(unsigned off) {
    assert(off < sizeof regs && !(off & 3));
    if(off==0x54) generic_writes++;
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
static void wait_lights(unsigned ons,unsigned offs){
    unsigned limit=2000;
    while((note_on_count<ons || note_off_count<offs) && limit--)step();
    assert(limit);
}
static void assert_note(unsigned note,unsigned on){
    for(unsigned channel=0;channel<16;channel++)assert(notes[channel*128+note]==on);
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
    connect();assert(connected && mode==DEVICE_GW25K && regs[0]==3);
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
    assert(!gw.panel_out_toggle && !gw.panel_in_toggle && !gw.midi_out_toggle && !gw.hello && gw.initial_clear);
}
static void render_scene(const char *path){
    gw25k_reset();
    gw.scene[0]=(100u<<24)|(2u<<7)|5u;gw.scene[1]=(73u<<4)|(128u<<18);
    gw.scene[2]=(1u<<(48-36))|(1u<<(50-36));gw.scene[4]=60u|(100u<<7);
    gw.scene[5]=60u|(1u<<7)|(1u<<8)|(1u<<9)|(1u<<10)|(12u<<17)|(1u<<22);
    gw.scene[7]=(42u<<16)|7u;gw.scene[8]=3;gw_format_scene();
    assert(!strcmp(gw.line1,"NOTE 060  VEL 100  VOL 100  PATCH 2"));
    assert(!strcmp(gw.line2,"MOD 073  BEND 128  FX 1 0 1"));
    assert(!strcmp(gw.line3,"TRACK 02/12  STEP 00007/00042  MISS 00003"));
    FILE *f=fopen(path,"wb");assert(f);fprintf(f,"P6\n428 142\n255\n");
    for(unsigned y=0;y<142;y++)for(unsigned x=0;x<428;x++){
        unsigned pixel=gw_pixel(x,y);uint8_t rgb[3]={
            (uint8_t)((pixel>>11)*255u/31u),(uint8_t)(((pixel>>5)&63u)*255u/63u),(uint8_t)((pixel&31u)*255u/31u)};
        assert(fwrite(rgb,1,3,f)==3);
    }
    assert(!fclose(f));
}
int main(int argc,char **argv){
    if(argc==3 && !strcmp(argv[1],"--render")){render_scene(argv[2]);return 0;}
    if(argc==2 && !strcmp(argv[1],"--rtl")){
        rtl_bridge=1;out_nak_left=0;initialize();wait_frame(1);wait_quiet();
        device_manual=1;device_remote=0;device_redraw=1;
        unsigned before=now_ms;while(now_ms-before<200)step();assert(gw.manual);
        device_manual=0;frame_id=0;wait_frame(2);wait_quiet();
        printf("PASS production host + actual GW25K RTL endpoint: %u requests, %u full frames, HELLO/TILE/END/DRAWN/manual/resume\n",rtl_requests,complete_frames);
        return 0;
    }
    assert(sizeof gw25k_config==124);
    initialize();tile_busy_left=2;end_busy_left=2;
    wait_frame(1);
    assert(requests[1]==1 && requests[0x20]>1 && requests[0x21]>=3);
    assert(busy_retries==4 && max_out_packet==64 && largest_request>64);
    assert(partial_response_reads && duplicate_count && out_naks==2 && generic_writes && midi_polls>out_packets/4);
    assert(cc123_count>=16); /* reconnect clears every selectable channel */
    unsigned ons=note_on_count,offs=note_off_count;
    regs[0x60/4]=60 | (1u<<7) | (1u<<8) | (1u<<9);
    wait_lights(ons+16,offs);assert_note(60,1);
    ons=note_on_count;unsigned refresh_start=now_ms;
    while(now_ms-refresh_start<650)step();
    assert(note_on_count>=ons+16);assert_note(60,1); /* local channel/transpose may clear remote LEDs */
    ons=note_on_count;offs=note_off_count;
    must_release_note=60;new_target_note=61;
    regs[0x60/4]=61 | (1u<<7) | (1u<<8) | (1u<<9);
    wait_lights(ons+16,offs+16);assert_note(60,0);assert_note(61,1);
    must_release_note=new_target_note=128;
    offs=note_off_count;regs[0x60/4]=0;
    wait_lights(note_on_count,offs+16);assert_note(61,0);
    /* Score feedback preserves raw MIDI pitch rather than folding notes into
     * the 16 physical pads; only the keyboard's selected channel consumes it. */
    ons=note_on_count;offs=note_off_count;
    regs[0x60/4]=1u<<11;regs[0x64/4]=(1u<<(48-36))|(1u<<(63-36));
    wait_lights(ons+32,offs);assert_note(48,1);assert_note(63,1);
    offs=note_off_count;regs[0x60/4]=0;regs[0x64/4]=0;
    wait_lights(note_on_count,offs+32);assert_note(48,0);assert_note(63,0);
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
    printf("PASS GW25K production host: actual composite descriptor, PL FS fragmentation, independent DATA toggles, duplicate IN/OUT NAK, full RGB565 coverage, BUSY retry, MIDI interleave/output, manual/redraw, static heartbeat, 11 response faults (%u frames, %u tiles, %u MIDI polls)\n",complete_frames,tile_executions,midi_polls);
    return 0;
}
