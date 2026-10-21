#ifndef WORKSTATION_USB2_BACKEND_H
#define WORKSTATION_USB2_BACKEND_H

unsigned usbhw_native_high_speed(void);
unsigned usbhw_native_packet_limit(void);
int usbhw_native_allow_high_speed(unsigned allowed);

#endif
