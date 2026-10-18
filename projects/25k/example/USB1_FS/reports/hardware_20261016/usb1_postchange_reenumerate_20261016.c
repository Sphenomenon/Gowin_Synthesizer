#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static int number(io_service_t service, CFStringRef key, uint32_t *value) {
    CFTypeRef obj = IORegistryEntryCreateCFProperty(service, key, NULL, 0);
    int ok = obj && CFGetTypeID(obj) == CFNumberGetTypeID()
        && CFNumberGetValue(obj, kCFNumberSInt32Type, value);
    if (obj) CFRelease(obj);
    return ok;
}

int main(int argc, char **argv) {
    int perform = argc == 2 && strcmp(argv[1], "--reenumerate") == 0;
    if (argc != 2 || (!perform && strcmp(argv[1], "--inspect") != 0)) {
        fprintf(stderr, "Use --inspect or --reenumerate for the fixed USB1 MIDI target.\n");
        return 2;
    }
    io_iterator_t iter = IO_OBJECT_NULL;
    kern_return_t kr = IOServiceGetMatchingServices(kIOMainPortDefault,
        IOServiceMatching("IOUSBHostDevice"), &iter);
    if (kr != KERN_SUCCESS) return 3;
    io_service_t service, target = IO_OBJECT_NULL;
    unsigned matches = 0;
    while ((service = IOIteratorNext(iter))) {
        uint32_t vid = 0, pid = 0, location = 0;
        if (number(service, CFSTR("idVendor"), &vid)
            && number(service, CFSTR("idProduct"), &pid)
            && number(service, CFSTR("locationID"), &location)
            && vid == 0x1209 && pid == 0x0001 && location == 0x01113200) {
            CFTypeRef name = IORegistryEntryCreateCFProperty(service,
                CFSTR("kUSBProductString"), NULL, 0);
            int expected = name && CFGetTypeID(name) == CFStringGetTypeID()
                && CFStringCompare(name, CFSTR("Primer 25K MIDI"), 0) == kCFCompareEqualTo;
            if (name) CFRelease(name);
            if (expected) {
                matches++;
                if (!target) { target = service; IOObjectRetain(target); }
            }
        }
        IOObjectRelease(service);
    }
    IOObjectRelease(iter);
    if (matches != 1) {
        fprintf(stderr, "Refusing: expected one fixed USB1 target; found %u.\n", matches);
        if (target) IOObjectRelease(target);
        return 4;
    }
    uint64_t rid = 0;
    IORegistryEntryGetRegistryEntryID(target, &rid);
    printf("Target Primer 25K MIDI 1209:0001 location=0x01113200 registry_id=%" PRIu64 "\n", rid);
    if (!perform) { IOObjectRelease(target); return 0; }
    IOCFPlugInInterface **plugin = NULL;
    SInt32 score = 0;
    kr = IOCreatePlugInInterfaceForService(target, kIOUSBDeviceUserClientTypeID,
        kIOCFPlugInInterfaceID, &plugin, &score);
    IOObjectRelease(target);
    if (kr != kIOReturnSuccess || !plugin) {
        fprintf(stderr, "Create USB plugin failed 0x%08x\n", kr); return 5;
    }
    IOUSBDeviceInterface187 **device = NULL;
    HRESULT hr = (*plugin)->QueryInterface(plugin,
        CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID187), (LPVOID *)&device);
    (*plugin)->Release(plugin);
    if (hr || !device) {
        fprintf(stderr, "Query USB interface failed 0x%08x\n", (unsigned)hr); return 6;
    }
    UInt16 vid = 0, pid = 0;
    UInt32 location = 0;
    kr = (*device)->GetDeviceVendor(device, &vid);
    if (kr == kIOReturnSuccess) kr = (*device)->GetDeviceProduct(device, &pid);
    if (kr == kIOReturnSuccess) kr = (*device)->GetLocationID(device, &location);
    if (kr != kIOReturnSuccess || vid != 0x1209 || pid != 1 || location != 0x01113200) {
        fprintf(stderr, "Interface target identity changed; refusing.\n");
        (*device)->Release(device); return 7;
    }
    kr = (*device)->USBDeviceOpen(device);
    printf("USBDeviceOpen: 0x%08x\n", kr);
    if (kr != kIOReturnSuccess) { (*device)->Release(device); return 8; }
    kr = (*device)->USBDeviceReEnumerate(device, 0);
    printf("USBDeviceReEnumerate options=0: 0x%08x\n", kr);
    (*device)->USBDeviceClose(device);
    (*device)->Release(device);
    return kr == kIOReturnSuccess ? 0 : 9;
}
