/* Board HSPI16 DMA request/reply transport. USB is initially disabled.
 * Derived register setup: supplied CH569 HSPI RX/reverse bridge examples.
 * One FPGA request owns both buffers until this reply has completed.
 */
__attribute__((aligned(16),section(".DMADATA"))) static uint8_t request_buf[4096];
__attribute__((aligned(16),section(".DMADATA"))) static uint8_t reply_buf[544];
static uint8_t host_state, in_toggle, enum_error;
static uint32_t in_errors, hspi_errors, in_packets;
/* Diagnostic snapshot: high bit of reply byte22 distinguishes link errors. */
static uint8_t bridge_reason;
static uint32_t bridge_detail;
/* v7 fault-only register trace, rotating over six otherwise unused IN-count
 * values. Reply byte22 F8..FD identifies each word; never report these as counts. */
static uint32_t bridge_trace[6];
static uint8_t bridge_trace_index;
static midi_input_t midi;
static uint16_t le16(const uint8_t *p) {return p[0]|p[1]<<8;}
static void wr16(uint8_t *p,unsigned n) {p[0]=n;p[1]=n>>8;}
static void wr32(uint8_t *p,uint32_t n) {wr16(p,n);wr16(p+2,n>>16);}
static void hspi_init(void)
{
    /* PA6/HD0 no longer UART; old probe's remap must not drive the bus. */
    R8_UART0_IER=0;
    R8_PIN_ALTERNATE &= ~RB_PIN_UART0;
    R32_PA_DIR &= ~((1u<<0)|(1u<<1)|(1u<<2)|(1u<<3)|(1u<<4)|(1u<<5)|(1u<<6)|(1u<<17)|(1u<<18)|(1u<<19)|(1u<<22)|(1u<<23));
    R32_PB_DIR &= ~0x003fc000u;
    R32_PA_DIR |= (1u<<9)|(1u<<10)|(1u<<11)|(1u<<21);
    R8_HSPI_INT_EN=0;
    R8_HSPI_CTRL=RB_HSPI_ALL_CLR|RB_HSPI_TRX_RST;
    R8_HSPI_CFG=RB_HSPI_DAT16_MOD|RB_HSPI_DUALDMA|RB_HSPI_RX_TOG_EN;
    R8_HSPI_AUX=RB_HSPI_REQ_FT|RB_HSPI_TCK_MOD;
    R8_HSPI_TX_SC=0;R8_HSPI_RX_SC=0;
    R32_HSPI_UDF0=0x000ffff;
    R32_HSPI_UDF1=0x000ffff;
    R32_HSPI_RX_ADDR0=(UINT32)request_buf;
    R32_HSPI_RX_ADDR1=(UINT32)request_buf;
    R32_HSPI_TX_ADDR0=(UINT32)reply_buf;
    R32_HSPI_TX_ADDR1=(UINT32)reply_buf;
    R16_HSPI_DMA_LEN0=sizeof(reply_buf)-1;
    R16_HSPI_DMA_LEN1=sizeof(reply_buf)-1;
    R8_HSPI_INT_FLAG=0x0f;
    R8_HSPI_CTRL=RB_HSPI_ENABLE|RB_HSPI_DMA_EN;
}
/* WCH HSPI_BurstMode_UpDown_Switch keeps MODE fixed even when the DOWN
 * side transmits. SW_ACT starts a reply; it does not require resetting the
 * peripheral or flipping MODE. Keep DMA bank/packet state owned by hardware.
 * Both descriptors alias the same RX buffer because this protocol permits
 * exactly one request until its reply has completed. */
static void maintain_usb(void)
{
    if(!host_state) return;
    if(!(R8_USB_MIS_ST&RB_USB_ATTACH)) {
        if(host_state!=1) {USBHS_Host_Init(ENABLE);host_state=1;in_toggle=0;}
    } else if(host_state==1) {
        DelayMs(100);
        enum_error=enumerate(&midi);
        host_state=enum_error?3:2;
        in_toggle=0;
    }
}
static uint8_t do_out(void)
{
    unsigned n=le16(request_buf+10), ep=request_buf[7];
    if(host_state!=2 || request_buf[9]!=8 || (ep!=profile.display_out && ep!=profile.midi_out) ||
       !n || n>512 || (request_buf[8]!=0 && request_buf[8]!=8)) return 3;
    memcpy(endpTXbuff,request_buf+16,n);
    R32_UH_TX_DMA=(UINT32)endpTXbuff;R16_UH_TX_LEN=n;
    uint8_t ret=USBHS_Transact((USB_PID_OUT<<4)|ep,request_buf[8],0);
    if(!ret || ret==(ERR_USB_TRANSFER|USB_PID_ACK)) return 1;
    if(ret==(ERR_USB_TRANSFER|USB_PID_NAK)) return 2;
    if(ret==(ERR_USB_TRANSFER|USB_PID_STALL)) return 3;
    return 4;
}
static unsigned poll_midi(void)
{
    if(host_state!=2) return 0;
    R32_UH_RX_DMA=(UINT32)endpRXbuff;R16_UH_RX_MAX_LEN=midi.max_packet;
    uint8_t ret=USBHS_Transact((USB_PID_IN<<4)|(midi.endpoint&15),in_toggle,0);
    if(ret) {
        if(ret!=(ERR_USB_TRANSFER|USB_PID_NAK)) in_errors++;
        return 0;
    }
    in_toggle^=8;in_packets++;
    unsigned n=R16_USB_RX_LEN;
    if(n>512 || (n&3)) {in_errors++;return 0;}
    memcpy(reply_buf+32,endpRXbuff,n);return n;
}
int main(void)
{
    SystemInit(FREQ_SYS);Delay_Init(FREQ_SYS);
    USBHS_Host_Init(DISABLE);hspi_init();
    for(;;) {
        /* Host cannot start just because a PC cable is plugged into P1. */
        if(!(R8_HSPI_INT_FLAG&RB_HSPI_IF_R_DONE)) continue;
        uint8_t flags=R8_HSPI_INT_FLAG;
        uint32_t before_lengths=((uint32_t)R16_HSPI_RX_LEN0<<16)|R16_HSPI_RX_LEN1;
        uint32_t before_state=((uint32_t)R8_HSPI_RX_SC<<24)|((uint32_t)R8_HSPI_CFG<<16)|
            ((uint32_t)R8_HSPI_RTX_STATUS<<8)|flags;
        /* Match the supplied single-DMA reverse bridge's acknowledge-before-read
         * order. No subsequent request can arrive before this reply completes. */
        R8_HSPI_INT_FLAG=RB_HSPI_IF_R_DONE|RB_HSPI_IF_FIFO_OV;
        __asm__ volatile ("fence iorw, iorw" ::: "memory");
        DelayUs(1);
        uint32_t after_lengths=((uint32_t)R16_HSPI_RX_LEN0<<16)|R16_HSPI_RX_LEN1;
        /* Supplied CH569_HSPI_USB IRQ selects the completed bank opposite
         * RX_TOG, which now names the next bank. Always select, never accept
         * whichever stale register happens to match the application header. */
        unsigned length=(R8_HSPI_RX_SC&RB_HSPI_RX_TOG)?(after_lengths>>16):(after_lengths&65535);
        uint8_t hs=R8_HSPI_RTX_STATUS;
        memset(reply_buf,0,sizeof reply_buf);
        uint8_t response=0;
        int bootstrap=request_buf[13]==1;
        int valid=!(hs&RB_HSPI_CRC_ERR) && (!(hs&RB_HSPI_NUM_MIS) || bootstrap) && !(flags&RB_HSPI_IF_FIFO_OV) &&
            length>=16 && length<=528 && request_buf[0]=='P' && request_buf[1]=='2' &&
            request_buf[2]=='Q' && request_buf[3]=='1' && request_buf[12]==1 &&
            le16(request_buf+10)==length-16;
        if(!valid) {
            hspi_errors++;
            if(!bridge_reason) {
            bridge_reason=((hs&RB_HSPI_CRC_ERR)?1:0)|((hs&RB_HSPI_NUM_MIS)?2:0)|
                ((flags&RB_HSPI_IF_FIFO_OV)?4:0)|((length<16||length>528)?8:0)|
                ((request_buf[0]!='P'||request_buf[1]!='2'||request_buf[2]!='Q'||request_buf[3]!='1')?16:0)|
                ((request_buf[12]!=1)?32:0)|((le16(request_buf+10)!=length-16)?64:0);
            bridge_detail=(length<<16)|le16(request_buf+10);
            bridge_trace[0]=bridge_detail;
            bridge_trace[1]=before_lengths;
            bridge_trace[2]=after_lengths;
            DelayUs(10);
            bridge_trace[3]=((uint32_t)R16_HSPI_RX_LEN0<<16)|R16_HSPI_RX_LEN1;
            bridge_trace[4]=before_state;
            bridge_trace[5]=((uint32_t)R8_HSPI_RX_SC<<24)|((uint32_t)R8_HSPI_CFG<<16)|
                ((uint32_t)R8_HSPI_RTX_STATUS<<8)|R8_HSPI_INT_FLAG;
            bridge_trace_index=0;
            }
        }
        else {
            if(bootstrap) {
                R8_HSPI_RX_SC=(R8_HSPI_RX_SC&RB_HSPI_RX_TOG)|((request_buf[14]+1)&15);R8_HSPI_TX_SC=0;
                USBHS_Host_Init(DISABLE);host_state=0;enum_error=0;in_toggle=0;bridge_reason=0;bridge_detail=0;
            }
            if(request_buf[6]==2 && !host_state) {bridge_reason=0;bridge_detail=0;USBHS_Host_Init(ENABLE);host_state=1;}
            if(request_buf[6]==3) {USBHS_Host_Init(DISABLE);host_state=0;}
            maintain_usb();
            if(request_buf[6]==1) response=do_out();
        }
        unsigned n=valid?poll_midi():0;
        reply_buf[0]='P';reply_buf[1]='2';reply_buf[2]='R';reply_buf[3]='1';
        reply_buf[4]=request_buf[4];reply_buf[5]=request_buf[5];
        reply_buf[6]=response;reply_buf[7]=host_state;
        wr16(reply_buf+8,device_vid);wr16(reply_buf+10,device_pid);
        reply_buf[12]=8;reply_buf[13]=R8_USB_SPD_TYPE&RB_USBSPEED_MASK;
        reply_buf[14]=profile.display_out;reply_buf[15]=profile.midi_out;
        wr16(reply_buf+16,profile.display_mps);wr16(reply_buf+18,profile.midi_mps);
        wr16(reply_buf+20,n);reply_buf[22]=bridge_reason?(0xf8|bridge_trace_index):enum_error;reply_buf[23]=hspi_errors;
        wr32(reply_buf+24,bridge_reason?bridge_trace[bridge_trace_index]:in_errors);wr32(reply_buf+28,in_packets);
        if(bridge_reason && ++bridge_trace_index==6) bridge_trace_index=0;
        __asm__ volatile ("fence iorw, iorw" ::: "memory");
        R8_HSPI_INT_FLAG=RB_HSPI_IF_T_DONE;
        R8_HSPI_CTRL|=RB_HSPI_SW_ACT;
        while(!(R8_HSPI_INT_FLAG&RB_HSPI_IF_T_DONE)) {}
        R8_HSPI_INT_FLAG=RB_HSPI_IF_T_DONE;
        /* Let the FPGA receive pipeline drain before changing bus direction. */
        DelayUs(1);
    }
}
