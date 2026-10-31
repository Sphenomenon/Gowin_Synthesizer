/* Explicit experiment only. Existing profiles do not select this linker. */
OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {
    ROM_LOAD (rx) : ORIGIN = 0x80000000, LENGTH = 64K
    ROM_COLD (rx) : ORIGIN = 0x80010000, LENGTH = 64K
    ILM (rx) : ORIGIN = 0xA0000000, LENGTH = 64K
    DLM (rw) : ORIGIN = 0xA0200100, LENGTH = 0xFF00
}
SECTIONS {
    .boot : { KEEP(*(.text.start)) . = ALIGN(16); } > ROM_LOAD
    .rom_text : {
        __rom_text_start = .;
        *classic_service.o(.text .text.*)
        /* Explicit runtime-owner objects only; absent in the budget profile.
         * Security command policy is cold, keeping decoder/transport in ILM. */
        *classic_security.o(.text .text.*)
        *ui_render.o(.text .text.*)
        . = ALIGN(16); __rom_text_end = .;
    } > ROM_COLD
    .text : {
        __ilm_start = .;
        KEEP(*(.text.ilm_entry))
        *(.text .text.*)
        . = ALIGN(16);
    } > ILM AT> ROM_LOAD
    __ilm_load_start = LOADADDR(.text);
    .rodata : { *(.rodata .rodata.* .srodata .srodata.*) . = ALIGN(16); __ilm_end = .; } > ILM AT> ROM_LOAD
    .data : {
        __data_start = .; KEEP(*(.data.startup_check))
        *(.data .data.* .sdata .sdata.*)
        . = ALIGN(16); __data_end = .;
    } > DLM AT> ROM_LOAD
    __data_load_start = LOADADDR(.data);
    __data_image_end = LOADADDR(.data) + SIZEOF(.data);
    __image_end = MAX(__data_image_end, __rom_text_end);
    .bss (NOLOAD) : {
        __bss_start = .; KEEP(*(.bss.startup_check))
        *(.bss .bss.* .sbss .sbss.*) *(COMMON)
        . = ALIGN(16); __bss_end = .;
    } > DLM
    __stack_bottom = 0xA020C000;
    __stack_top = 0xA0210000;
    __heap_start = __bss_end;
    __heap_end = __heap_start;
    ASSERT(DEFINED(__boot_rom_bytes) && __boot_rom_bytes == 128K, "split requires explicit physical 128 KiB ROM")
    ASSERT(__ilm_end <= 0xA000FFFC, "ILM overlaps reserved last-word probe")
    ASSERT(__bss_end <= __stack_bottom, "DLM globals overlap reserved 16 KiB stack")
    ASSERT(__data_image_end <= ORIGIN(ROM_LOAD) + LENGTH(ROM_LOAD), "hot load bank overflow")
    ASSERT(__rom_text_start == 0x80010000 && __rom_text_end > __rom_text_start, "cold ROM bank missing")
    ASSERT(__image_end <= 0x80020000, "cold code exceeds physical 128 KiB ROM")
    ASSERT(LOADADDR(.rodata) - __ilm_load_start == ADDR(.rodata) - __ilm_start,
           "ILM load/run spans are not contiguous")
    /DISCARD/ : { *(.comment) *(.riscv.attributes) }
}
