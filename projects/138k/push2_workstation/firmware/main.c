/* Push 2 USB Host bridge. USB runs on the CH569 CPU, not in FPGA RTL.
 * Hardware USB transactions / PHY initialization come from WCH's CH569 SDK.
 * Native HSPI16 request/reply transport; UART pins are not driven.
 */
#include "CH56x_common.h"
#include "CH56x_host_hs.h"
#include "midi_descriptor.h"

__attribute__((aligned(16), section(".DMADATA"))) UINT8 endpRXbuff[4096];
__attribute__((aligned(16), section(".DMADATA"))) UINT8 endpTXbuff[4096];
static uint8_t descriptor[4096];
static uint8_t ep0_mps = 8;
static uint16_t device_vid,device_pid;
static push_profile_t profile;
static const uint8_t cin_length[16] = {0,0,2,3,3,1,2,3,3,3,3,3,2,2,3,1};

void *memcpy(void *dst, const void *src, size_t n)
{
    uint8_t *d = dst; const uint8_t *s = src;
    while (n--) *d++ = *s++;
    return dst;
}
void *memset(void *dst, int v, size_t n)
{
    uint8_t *d = dst;
    while (n--) *d++ = v;
    return dst;
}
static void putc_uart(char c) { (void)c; }
static void msg(const char *s) { while (*s) putc_uart(*s++); }
static void hex(unsigned v, unsigned digits)
{
    while (digits--) putc_uart("0123456789ABCDEF"[(v >> (digits*4)) & 15]);
}
static void field(const char *key, unsigned v, unsigned digits)
{ msg(key); hex(v, digits); }
static void status(const char *state)
{
    msg(state);
    field(" ctrl=", R8_USB_CTRL, 2);
    field(" mis=", R8_USB_MIS_ST, 2);
    field(" speed=", R8_USB_SPD_TYPE, 2);
    field(" flags=", R8_USB_INT_FG, 2);
    field(" ist=", R8_USB_INT_ST, 2);
    msg("\r\n");
}
static void dump(const char *label, const uint8_t *d, unsigned n)
{
    for (unsigned p = 0; p < n; p += 32) {
        msg(label); field(" offset=", p, 4); msg(" bytes=");
        for (unsigned j = p; j < n && j < p+32; j++) { hex(d[j], 2); putc_uart(' '); }
        msg("\r\n");
    }
}
/* Fixed aligned DMA buffers; copy only checked lengths into the caller's buffer.
 * Supports descriptor IN and no-data standard requests used by this probe.
 * Every call restores RX/TX DMA, so control and bulk polling cannot alias.
 */
static uint8_t control(uint8_t type, uint8_t request, uint16_t value,
                       uint16_t index, uint16_t count, uint8_t *out, uint16_t *got)
{
    uint8_t result, toggle = 8;
    uint16_t total = 0;
    if (got) *got = 0;
    if (count > sizeof descriptor || (count && (!(type & 128) || !out)))
        return ERR_USB_BUF_OVER;
    const uint8_t setup[8] = {type, request, value, value >> 8,
                             index, index >> 8, count, count >> 8};
    memcpy(endpTXbuff, setup, 8);
    R32_UH_TX_DMA = (UINT32)endpTXbuff;
    R32_UH_RX_DMA = (UINT32)endpRXbuff;
    R16_UH_RX_MAX_LEN = ep0_mps;
    R16_UH_TX_LEN = 8;
    DelayUs(100);
    result = USBHS_Transact(USB_PID_SETUP << 4, 0, 1000);
    if (result) return result;
    while (total < count) {
        DelayUs(100);
        result = USBHS_Transact(USB_PID_IN << 4, toggle, 1000);
        if (result) return result;
        uint16_t n = R16_USB_RX_LEN;
        if (n > ep0_mps || n > count-total) return ERR_USB_BUF_OVER;
        memcpy(out+total, endpRXbuff, n);
        total += n; toggle ^= 8;
        if (n < ep0_mps) break;
    }
    if (got) *got = total;
    DelayUs(100);
    R16_UH_TX_LEN = 0;
    result = USBHS_Transact((count ? USB_PID_OUT : USB_PID_IN) << 4, 8, 1000);
    if (result) return result;
    if (!count && R16_USB_RX_LEN) return ERR_USB_BUF_OVER;
    return 0;
}
static uint8_t get_descriptor(uint16_t value, uint16_t count, uint16_t *got)
{ return control(0x80, 6, value, 0, count, descriptor, got); }
static uint8_t enumerate(midi_input_t *midi)
{
    uint8_t ret, configurations;
    uint16_t n;
    ep0_mps = 8;
    R8_USB_DEV_AD = 0;
    SetBusReset();
    DelayMs(20); /* USB reset recovery before SETUP. */
    R8_USB_INT_FG = 0xff;
    status("RESET");
    ret = get_descriptor(0x0100, 8, &n);
    if (ret) { field("DEV8 error=", ret, 2); msg("\r\n"); return ret; }
    if (n != 8 || descriptor[0] != 18 || descriptor[1] != 1) return ERR_USB_BUF_OVER;
    ep0_mps = descriptor[7];
    if (ep0_mps != 8 && ep0_mps != 16 && ep0_mps != 32 && ep0_mps != 64)
        return ERR_USB_BUF_OVER;
    ret = get_descriptor(0x0100, 18, &n);
    if (ret || n != 18) return ret ? ret : ERR_USB_BUF_OVER;
    dump("DEVICE", descriptor, n);
    field("VID=", descriptor[8] | descriptor[9]<<8, 4);
    field(" PID=", descriptor[10] | descriptor[11]<<8, 4);
    field(" EP0=", ep0_mps, 2); msg("\r\n");
    device_vid=descriptor[8]|descriptor[9]<<8; device_pid=descriptor[10]|descriptor[11]<<8;
    if(device_vid!=0x2982 || device_pid!=0x1967 || (R8_USB_SPD_TYPE&RB_USBSPEED_MASK)!=UST_HS) return ERR_USB_UNSUPPORT;
    configurations = descriptor[17];
    ret = control(0, 5, 8, 0, 0, 0, 0);
    if (ret) return ret;
    R8_USB_DEV_AD = 8;
    DelayMs(10);
    for (unsigned cfg = 0; cfg < configurations && cfg < 8; cfg++) {
        ret = get_descriptor(0x0200 | cfg, 9, &n);
        if (ret || n != 9) return ret ? ret : ERR_USB_BUF_OVER;
        uint16_t length = descriptor[2] | descriptor[3]<<8;
        if (length < 9 || length > sizeof descriptor) return ERR_USB_BUF_OVER;
        ret = get_descriptor(0x0200 | cfg, length, &n);
        if (ret || n != length) return ret ? ret : ERR_USB_BUF_OVER;
        dump("CONFIG", descriptor, n);
        int parsed = midi_find_input(descriptor, n, midi);
        if (parsed < 0) return ERR_USB_BUF_OVER;
        if (!parsed) continue;
        if(push_find_outputs(descriptor,n,&profile)!=1) return ERR_USB_UNSUPPORT;
        if ((R8_USB_SPD_TYPE & RB_USBSPEED_MASK) == UST_FS && midi->max_packet > 64)
            return ERR_USB_BUF_OVER;
        ret = control(0, 9, midi->configuration, 0, 0, 0, 0);
        if (ret) return ret;
        DelayMs(10);
        field("MIDI_READY interface=", midi->interface_number, 2);
        field(" ep=", midi->endpoint, 2);
        field(" mps=", midi->max_packet, 4); msg("\r\n");
        return 0;
    }
    msg("NO_MIDI_INTERFACE\r\n");
    return ERR_USB_UNSUPPORT;
}

#include "host_bridge.inc"
