#define main workstation_main
#include "firmware.c"
#undef main

int main(void) {
    unsigned previous_status=~0u;
    reg_uart_clkdiv=417;
    usbhw_init(0x02000100);
    uart_printf("USB1 FS identify build %x\n",MMIO(0x7c));
    for(;;) {
        if(!connected)connect();
        unsigned status=(unsigned)mode | (connected?0x100u:0) | (gw.hello?0x200u:0);
        MMIO(0x70)=connected?((uint32_t)dev.pid<<16)|dev.vid:0;
        MMIO(0x74)=status;
        if(status!=previous_status) {
            uart_printf("USB1 status %x identity %x midi %d\n",status,MMIO(0x70),MMIO(0x78));
            previous_status=status;
        }
        if(!connected)continue;
        poll_midi();
        if(connected&&mode==DEVICE_GW25K)gw25k_service();
        delay(1);
    }
}
