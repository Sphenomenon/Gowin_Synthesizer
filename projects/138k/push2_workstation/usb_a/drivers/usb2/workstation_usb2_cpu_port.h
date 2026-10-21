#ifndef WORKSTATION_USB2_CPU_PORT_H
#define WORKSTATION_USB2_CPU_PORT_H

#include "workstation_usb2_host.h"

void workstation_usb2_cpu_io(struct workstation_usb2_io *io);
uint32_t workstation_usb2_cpu_fault(void);
uint32_t workstation_usb2_cpu_fault_address(void);
void workstation_usb2_cpu_clear_fault(void);

#endif
