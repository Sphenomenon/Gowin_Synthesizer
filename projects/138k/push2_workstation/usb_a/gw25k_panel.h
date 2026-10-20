/* PL local-v1 host; included after the unchanged Push implementation.
 * Each service step performs bounded USB work. No framebuffer or heap. */
#ifndef GW25K_PANEL_H
#define GW25K_PANEL_H
#define GW_WIDTH 428u
#define GW_HEIGHT 142u
#define GW_TILE_W 62u
#define GW_TILE_H 4u
#define GW_HELLO 1u
#define GW_HEALTH 2u
#define GW_TILE 0x20u
#define GW_END 0x21u
struct gw_transaction {
    uint8_t data[528],reply[64];
    unsigned length,position,received,type,used,reading;
    uint32_t started,busy_started,retry_at;
};
struct gw_panel_state {
    struct gw_transaction transaction[2];
    int active;
    uint16_t sequence[2];
    uint32_t session,last_health,recover_until,frame;
    unsigned recovering,hello,manual,dirty,drawing,tile_x,tile_y;
    unsigned panel_out_toggle,panel_in_toggle;
    uint32_t scene[9];
    char line1[44],line2[36],line3[42],line4[28];
};
/* The freestanding ROM links libgcc only. Volatile byte accesses keep
 * compiler loop-pattern transforms from reintroducing an unavailable libc. */
static void gw_copy(void *destination,const void *source,unsigned count) {
    volatile uint8_t *d=(volatile uint8_t *)destination;
    const volatile uint8_t *s=(const volatile uint8_t *)source;
    while(count--)*d++=*s++;
}
static void gw_zero(void *destination,unsigned count) {
    volatile uint8_t *d=(volatile uint8_t *)destination;while(count--)*d++=0;
}
static int gw_different(const void *left,const void *right,unsigned count) {
    const volatile uint8_t *a=(const volatile uint8_t *)left,*b=(const volatile uint8_t *)right;
    while(count--)if(*a++!=*b++)return 1;
    return 0;
}
static struct gw_panel_state gw;
static uint32_t gw_session_counter;
static unsigned gw_get16(const uint8_t *p){return p[0]|((unsigned)p[1]<<8);}
static uint32_t gw_get32(const uint8_t *p){return gw_get16(p)|((uint32_t)gw_get16(p+2)<<16);}
static void gw_put16(uint8_t *p,unsigned n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static void gw_put32(uint8_t *p,uint32_t n){gw_put16(p,n);gw_put16(p+2,n>>16);}
static int gw_due(uint32_t now,uint32_t deadline){return (int32_t)(now-deadline)>=0;}
static void gw25k_reset(void) {
    gw_zero(&gw,sizeof gw);gw.active=-1;gw.dirty=1;
    gw.session=++gw_session_counter;if(!gw.session)gw.session=++gw_session_counter;
}
static void gw_recover(void) {
    gw.transaction[0].used=gw.transaction[1].used=0;gw.active=-1;
    gw.hello=0;gw.drawing=0;gw.dirty=1;gw.recovering=1;
    gw.recover_until=(uint32_t)usbhw_timer_now()+110u;
    gw.session=++gw_session_counter;if(!gw.session)gw.session=++gw_session_counter;
    gw.sequence[0]=gw.sequence[1]=0;
    /* PL session reset preserves USB DATA toggles. Drain stale responses and
     * allow the device's 100 ms partial-frame parser to expire. */
}
static void gw_scene(uint32_t *s) {
    s[0]=MMIO(0x10);s[1]=MMIO(0x14);s[2]=MMIO(0x1c);s[3]=MMIO(0x20);
    s[4]=MMIO(0x24);s[5]=s[6]=s[7]=s[8]=0; /* Push-only score state */
}
/* Compact column font: ASCII 32..90, 5x7. */
static const uint8_t gw_font[59][5]={
 {0,0,0,0,0},{0,0,95,0,0},{0,7,0,7,0},{20,127,20,127,20},
 {36,42,127,42,18},{35,19,8,100,98},{54,73,85,34,80},{0,5,3,0,0},
 {0,28,34,65,0},{0,65,34,28,0},{20,8,62,8,20},{8,8,62,8,8},
 {0,80,48,0,0},{8,8,8,8,8},{0,96,96,0,0},{32,16,8,4,2},
 {62,81,73,69,62},{0,66,127,64,0},{66,97,81,73,70},{33,65,69,75,49},
 {24,20,18,127,16},{39,69,69,69,57},{60,74,73,73,48},{1,113,9,5,3},
 {54,73,73,73,54},{6,73,73,41,30},{0,54,54,0,0},{0,86,54,0,0},
 {8,20,34,65,0},{20,20,20,20,20},{0,65,34,20,8},{2,1,81,9,6},
 {50,73,121,65,62},{126,17,17,17,126},{127,73,73,73,54},{62,65,65,65,34},
 {127,65,65,34,28},{127,73,73,73,65},{127,9,9,9,1},{62,65,73,73,122},
 {127,8,8,8,127},{0,65,127,65,0},{32,64,65,63,1},{127,8,20,34,65},
 {127,64,64,64,64},{127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},
 {127,9,9,9,6},{62,65,81,33,94},{127,9,25,41,70},{70,73,73,73,49},
 {1,1,127,1,1},{63,64,64,64,63},{31,32,64,32,31},{63,64,56,64,63},
 {99,20,8,20,99},{7,8,112,8,7},{97,81,73,69,67}};
static int gw_text(unsigned x,unsigned y,unsigned left,unsigned top,const char *text,unsigned scale) {
    if(x<left || y<top || y>=top+7u*scale)return 0;
    unsigned col=(x-left)/scale,index=col/6u;col%=6u;
    for(unsigned i=0;i<index;i++)if(!text[i])return 0;
    unsigned c=(uint8_t)text[index];
    return c>=32 && c<=90 && col<5 && ((gw_font[c-32][col]>>((y-top)/scale))&1u);
}
static void gw_decimal(char *p,unsigned n,unsigned digits) {
    while(digits){p[--digits]=(char)('0'+n%10u);n/=10u;}
}
/* Existing MMIO reports effective gain (CC7 * expression), profile, committed
 * mode, effective FX mask and the 8-bit bend-table index. It does not report
 * the raw Program number, raw 14-bit bend or independent FX master state. */
static void gw_format_scene(void) {
    static const char tones[6][8]={"FLUTE  ","STRINGS","BRASS  ","MARIMBA","PIANO  ","UNKNOWN"};
    static const char routes[4][7]={"STEREO","LEFT  ","RIGHT ","MUTED "};
    const uint32_t *s=gw.scene;
    unsigned profile=(s[0]>>7)&7u,mode=(s[0]>>3)&3u;
    gw_copy(gw.line1,"NOTE 000  VEL 000  GAIN 000  TONE ",sizeof "NOTE 000  VEL 000  GAIN 000  TONE ");
    gw_decimal(gw.line1+5,s[4]&127u,3);gw_decimal(gw.line1+14,(s[4]>>7)&127u,3);
    gw_decimal(gw.line1+24,(s[0]>>16)>=32768u?127u:(s[0]>>24),3);
    gw_copy(gw.line1+34,tones[profile<5u?profile:5u],8);
    gw_copy(gw.line2,"MOD 000  BEND IDX 000  FX DCR 000",sizeof "MOD 000  BEND IDX 000  FX DCR 000");
    gw_decimal(gw.line2+4,(s[1]>>4)&127u,3);gw_decimal(gw.line2+18,(s[1]>>18)&255u,3);
    gw.line2[30]=(s[0]&1u)?'1':'0';gw.line2[31]=(s[0]&2u)?'1':'0';gw.line2[32]=(s[0]&4u)?'1':'0';
    /* ACTIVE is the actual allocated/non-idle voice count, including release
     * tails. It is neither the held-pad count nor a count of partials. */
    gw_copy(gw.line3,"MODE A  ACTIVE 000  OUT ",sizeof "MODE A  ACTIVE 000  OUT ");
    gw.line3[5]=mode<3u?(char)('A'+mode):'?';
    gw_decimal(gw.line3+15,(s[0]>>10)&63u,3);
    gw_copy(gw.line3+24,routes[(s[0]>>5)&3u],7);
    gw_copy(gw.line4,"GLIDE 000  SUSTAIN OFF",sizeof "GLIDE 000  SUSTAIN OFF");
    gw_decimal(gw.line4+6,(s[1]>>11)&127u,3);
    gw_copy(gw.line4+19,(s[1]&8u)?"ON ":"OFF",3);
}
static uint16_t gw_pixel(unsigned x,unsigned y) {
    const uint32_t *s=gw.scene;
    uint16_t color=y<21?0x18e3:0x0841;
    if(y==21 || y==100)color=0x2b8d;
    if(gw_text(x,y,8,4,"GOWIN SYNTH",2))return 0x7ffb;
    if(gw_text(x,y,302,7,"USB MIDI / PL",1))return 0xbdf7;
    if(gw_text(x,y,8,30,gw.line1,1))return 0xffff;
    if(gw_text(x,y,8,44,gw.line2,1))return 0xbdf7;
    if(gw_text(x,y,8,61,gw.line3,1))return 0x7ffb;
    if(gw_text(x,y,8,80,gw.line4,1))return 0xffe0;
    if(y>=106 && y<139 && x>=6 && x<422) {
        unsigned key=(x-6u)/26u,local=(x-6u)%26u,n=48u+key;
        unsigned held=n<68u?((s[2]>>(n-36u))&1u):((s[3]>>(n-68u))&1u);
        color=local==25?0x0841:held?0xffff:0x2945;
        char label[2]={(char)('A'+key),0};
        if(gw_text(x,y,6u+key*26u+10u,118,label,1))color=held?0x0000:0xbdf7;
    }
    return color;
}
static void gw_prepare(unsigned channel,unsigned type,unsigned payload) {
    struct gw_transaction *t=&gw.transaction[channel];
    gw_zero(t,sizeof *t);t->used=1;t->type=type;t->length=16u+payload;
    uint8_t *p=t->data;p[0]='P';p[1]='L';p[2]=1;p[3]=(uint8_t)type;
    gw_put32(p+4,gw.session);gw_put16(p+8,gw.sequence[channel]);
    gw_put16(p+12,payload);p[14]=(uint8_t)(1u|(channel<<1));
    t->started=t->busy_started=(uint32_t)usbhw_timer_now();
}
static void gw_prepare_display(void) {
    if(!gw.drawing) {
        gw_scene(gw.scene);gw_format_scene();gw.frame++;if(!gw.frame)gw.frame++;
        gw.tile_x=gw.tile_y=0;gw.drawing=1;gw.dirty=0;
    }
    if(gw.tile_y>=GW_HEIGHT) {
        gw_prepare(1,GW_END,8);gw_put32(gw.transaction[1].data+20,gw.frame);return;
    }
    unsigned width=GW_WIDTH-gw.tile_x,height=GW_HEIGHT-gw.tile_y;
    if(width>GW_TILE_W)width=GW_TILE_W;
    if(height>GW_TILE_H)height=GW_TILE_H;
    gw_prepare(1,GW_TILE,16u+width*height*2u);
    uint8_t *p=gw.transaction[1].data;
    gw_put32(p+20,gw.frame);gw_put16(p+24,gw.tile_x);gw_put16(p+26,gw.tile_y);
    gw_put16(p+28,width);gw_put16(p+30,height);
    for(unsigned row=0;row<height;row++)for(unsigned col=0;col<width;col++)
        gw_put16(p+32u+2u*(row*width+col),gw_pixel(gw.tile_x+col,gw.tile_y+row));
}
static void gw_response(unsigned channel) {
    struct gw_transaction *t=&gw.transaction[channel];uint8_t *p=t->reply;
    if(t->type==GW_HELLO) {
        if(p[3]!=0x81 || gw_get16(p+12)!=12 || gw_get16(p+16)!=GW_WIDTH || gw_get16(p+18)!=GW_HEIGHT ||
           p[20]!=1 || p[21] || gw_get16(p+22)<248 || gw_get16(p+24)!=512 || gw_get16(p+26)<250) {gw_recover();return;}
        gw.hello=1;gw.last_health=(uint32_t)usbhw_timer_now();
    } else {
        unsigned status=p[16],flags=p[17];
        unsigned expected=t->type==GW_HEALTH?0x82:t->type==GW_TILE?0xa0:0xa1;
        if(gw_get16(p+12)!=8 || status>2 || (flags&~7u) ||
           (p[3]!=expected && !(t->type==GW_END && p[3]==0xa0 && status!=0))) {gw_recover();return;}
        if(channel && (gw_get16(p+18)!=0 || gw_get32(p+20)!=gw.frame)){gw_recover();return;}
        unsigned was_manual=gw.manual;gw.manual=flags&1u;
        if(t->type==GW_HEALTH) {
            gw.last_health=(uint32_t)usbhw_timer_now();
            if(gw.manual || (!(flags&2u)&&gw.drawing&&(gw.tile_x||gw.tile_y))) {
                /* HEALTH may observe settings before another tile is sent.
                 * The device has discarded its canvas. A pending BUSY tile
                 * was not accepted and owns no sequence; replace it safely. */
                gw.transaction[1].used=0;gw.drawing=0;gw.dirty=1;
            }
            if((was_manual&&!gw.manual) || ((flags&4u)&&!gw.drawing) || (!(flags&2u)&&!gw.drawing))gw.dirty=1;
        }
        if(status==2) {
            if((uint32_t)(usbhw_timer_now()-t->busy_started)>=2000u){gw_recover();return;}
            t->position=t->received=t->reading=0;t->retry_at=(uint32_t)usbhw_timer_now()+1u;
            t->started=(uint32_t)usbhw_timer_now();gw.active=-1;return;
        }
        if(channel) {
            if(status==1 || gw.manual) {gw.drawing=0;gw.dirty=1;}
            else if(t->type==GW_END) {gw.drawing=0;}
            else {gw.tile_x+=GW_TILE_W;if(gw.tile_x>=GW_WIDTH){gw.tile_x=0;gw.tile_y+=GW_TILE_H;}}
        }
    }
    gw.sequence[channel]++;t->used=0;gw.active=-1;
}
static void gw_transfer(void) {
    unsigned channel=(unsigned)gw.active;struct gw_transaction *t=&gw.transaction[channel];
    uint32_t now=(uint32_t)usbhw_timer_now();
    if((uint32_t)(now-t->started)>=150u) {
        /* A final OUT may have reached the device without an ACK. Only a USB
         * reset can resynchronize its uncertain DATA toggle. */
        if(!t->reading)disconnect();else gw_recover();
        return;
    }
    if(!t->reading) {
        unsigned n=t->length-t->position;if(n>panel_out_size)n=panel_out_size;
        int result=usbhw_transfer_out(PID_OUT,dev.address,panel_out_ep,1,
            gw.panel_out_toggle?PID_DATA1:PID_DATA0,t->data+t->position,(int)n);
        if(result==USB_RES_OK) {gw.panel_out_toggle^=1;t->position+=n;if(t->position==t->length)t->reading=1;}
        else if(result==USB_RES_STALL)disconnect();
        /* Lost ACK and NAK both retain this exact fragment and DATA PID;
         * duplicate USB DATA is acknowledged without another append. */
        return;
    }
    uint8_t packet[64],pid=0;
    int n=usbhw_transfer_in(PID_IN,dev.address,panel_in_ep,&pid,packet,(int)panel_in_size);
    if(n==USB_RES_STALL){disconnect();return;}
    if(n<0)return;
    if((unsigned)n>panel_in_size || (pid!=PID_DATA0 && pid!=PID_DATA1)){gw_recover();return;}
    if(pid!=(gw.panel_in_toggle?PID_DATA1:PID_DATA0))return;
    gw.panel_in_toggle^=1;
    if(t->received+(unsigned)n>sizeof t->reply){gw_recover();return;}
    gw_copy(t->reply+t->received,packet,(unsigned)n);t->received+=(unsigned)n;
    if(t->received>=16) {
        uint8_t *p=t->reply;unsigned payload=gw_get16(p+12);
        if(p[0]!='P' || p[1]!='L' || p[2]!=1 || gw_get32(p+4)!=gw.session ||
           gw_get16(p+8)!=gw.sequence[channel] || gw_get16(p+10)!=gw.sequence[channel] ||
           p[14]!=(1u|(channel<<1)) || payload>12 || t->received>16u+payload) {gw_recover();return;}
        if(t->received==16u+payload)gw_response(channel);
    }
}
static void gw25k_service(void) {
    if(!connected || mode!=DEVICE_GW25K)return;
    uint32_t now=(uint32_t)usbhw_timer_now();
    if(gw.recovering) {
        uint8_t p[64],pid=0;
        int n=usbhw_transfer_in(PID_IN,dev.address,panel_in_ep,&pid,p,(int)panel_in_size);
        if(n==USB_RES_STALL){disconnect();return;}
        if(n>=0 && (pid==PID_DATA0 || pid==PID_DATA1) && pid==(gw.panel_in_toggle?PID_DATA1:PID_DATA0))gw.panel_in_toggle^=1;
        if(n==USB_RES_NAK && gw_due(now,gw.recover_until)){gw.recovering=0;gw.manual=0;}
        return;
    }
    if(gw.active>=0){gw_transfer();return;}
    if(!gw.hello) {gw_prepare(0,GW_HELLO,0);gw.active=0;}
    else if((uint32_t)(now-gw.last_health)>=(gw.drawing?10u:50u)) {
        gw_prepare(0,GW_HEALTH,0);gw.active=0;
    } else if(gw.transaction[1].used) {
        if(gw_due(now,gw.transaction[1].retry_at)){gw.transaction[1].started=now;gw.active=1;}
    } else if(!gw.manual) {
        uint32_t next[9];gw_scene(next);
        if(!gw.drawing && gw_different(next,gw.scene,sizeof next))gw.dirty=1;
        if(gw.drawing || gw.dirty){gw_prepare_display();gw.active=1;}
    }
    if(gw.active>=0)gw_transfer();
}
#endif
