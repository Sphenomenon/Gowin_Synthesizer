ENTRY(_start)
MEMORY {
  ROM (rx) : ORIGIN = 0x80000000, LENGTH = 16K
  RAM (rw) : ORIGIN = 0x00000200, LENGTH = 0x1e00
}
SECTIONS {
  .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) . = ALIGN(4); } > ROM
  .data : { . = ALIGN(4); __data_start = .; *(.data*) *(.sdata*) . = ALIGN(4); __data_end = .; } > RAM AT> ROM
  __data_load_start = LOADADDR(.data);
  .bss (NOLOAD) : { . = ALIGN(4); __bss_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); __bss_end = .; } > RAM
  ASSERT(__bss_end <= 0x1000, "UI globals leave less than 4KiB stack")
  /DISCARD/ : { *(.comment) *(.riscv.attributes) }
}
