#include "workstation_usb2_cpu_port.h"

static uint32_t cpu_read(uint32_t address)
{
    return *(volatile uint32_t *)(uintptr_t)address;
}

static void cpu_write(uint32_t address, uint32_t value)
{
    *(volatile uint32_t *)(uintptr_t)address = value;
}

uint32_t workstation_usb2_cpu_fault(void)
{
    return cpu_read(0x02000058u);
}

uint32_t workstation_usb2_cpu_fault_address(void)
{
    return cpu_read(0x0200005cu);
}

void workstation_usb2_cpu_clear_fault(void)
{
    cpu_write(0x02000058u, 15);
}

static int read32(void *context, uint32_t offset, uint32_t *value)
{
    *value = cpu_read((uint32_t)(uintptr_t)context + offset);
    return workstation_usb2_cpu_fault() ? -1 : 0;
}

static int write32(void *context, uint32_t offset, uint32_t value)
{
    cpu_write((uint32_t)(uintptr_t)context + offset, value);
    return workstation_usb2_cpu_fault() ? -1 : 0;
}

static uint32_t milliseconds(void *context)
{
    (void)context;
    return cpu_read(0x02000050u);
}

void workstation_usb2_cpu_io(struct workstation_usb2_io *io)
{
    io->context = (void *)(uintptr_t)0x02000100u;
    io->read32 = read32;
    io->write32 = write32;
    io->milliseconds = milliseconds;
}
