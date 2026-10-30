/* Explicit runtime-window variant. Capacity must match selected physical ROM. */
OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {
    ROM (rx)  : ORIGIN = 0x80000000, LENGTH = DEFINED(__boot_rom_bytes) ? __boot_rom_bytes : 16K
    ILM (rx)  : ORIGIN = 0xA0000000, LENGTH = 64K
    DLM (rw)  : ORIGIN = 0xA0200100, LENGTH = 0xFF00
}
SECTIONS {
    .boot : { KEEP(*(.text.start)) . = ALIGN(16); } > ROM
    .text : {
        __ilm_start = .;
        KEEP(*(.text.ilm_entry))
        *(.text .text.*)
        . = ALIGN(16);
    } > ILM AT> ROM
    __ilm_load_start = LOADADDR(.text);
    .rodata : { *(.rodata .rodata.* .srodata .srodata.*) . = ALIGN(16); __ilm_end = .; } > ILM AT> ROM
    .data : {
        __data_start = .;
        KEEP(*(.data.startup_check))
        *(.data .data.* .sdata .sdata.*)
        . = ALIGN(16); __data_end = .;
    } > DLM AT> ROM
    __data_load_start = LOADADDR(.data);
    __image_end = LOADADDR(.data) + SIZEOF(.data);
    .bss (NOLOAD) : {
        __bss_start = .;
        KEEP(*(.bss.startup_check))
        *(.bss .bss.* .sbss .sbss.*) *(COMMON)
        . = ALIGN(16); __bss_end = .;
    } > DLM
    __stack_bottom = 0xA020C000;
    __stack_top = 0xA0210000;
    __heap_start = __bss_end;
    __heap_end = __heap_start; /* No allocator or implicit heap. */
    ASSERT(__ilm_end <= 0xA000FFFC, "ILM overlaps reserved last-word probe")
    ASSERT(__bss_end <= __stack_bottom, "DLM globals overlap reserved 16 KiB stack")
    ASSERT(LENGTH(ROM) == 16K || LENGTH(ROM) == 64K, "unsupported physical Boot ROM capacity")
    ASSERT(__image_end <= ORIGIN(ROM) + LENGTH(ROM), "cold image exceeds selected physical Boot ROM")
    ASSERT(LOADADDR(.rodata) - __ilm_load_start == ADDR(.rodata) - __ilm_start,
           "ILM load/run spans are not contiguous")
    /DISCARD/ : { *(.comment) *(.riscv.attributes) }
}
