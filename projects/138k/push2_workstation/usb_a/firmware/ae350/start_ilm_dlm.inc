// Explicit cold-ROM loader; see LOCAL_MEMORY.md for CSR sources and limits.
// No stack or local-memory load is used until configuration and writes pass.
.option norvc
.option norelax
.section .text.start,"ax",@progbits
.global _start
.type _start,@function
_start:
    csrw mie, zero
    li s0, 0xf8000000
    la t0, local_trap
    csrw mtvec, t0
    li t0, 0x43505531
    sw t0, 0(s0)
    // A previous debugger/cache-enabled boot is not a supported cold entry.
    csrr t0, 0x7ca
    andi t0, t0, 3
    li s1, 1
    bnez t0, local_fail
    csrr t0, 0xfc0
    csrr t1, 0xfc1
    li s1, 2
    srli t2, t0, 12
    andi t2, t2, 7
    beqz t2, local_fail
    srli t2, t1, 12
    andi t2, t2, 7
    beqz t2, local_fail
    // LMSZ=7 encodes 1<<(9+7) bytes. Reject smaller or different geometry.
    srli t0, t0, 15
    andi t0, t0, 31
    li t2, 7
    bne t0, t2, local_fail
    srli t1, t1, 15
    andi t1, t1, 31
    bne t1, t2, local_fail
    // Only change documented IEN/DEN. Preserve base/ECC/other control bits.
    csrr t0, 0x7c0
    ori t0, t0, 1
    csrw 0x7c0, t0
    csrr t1, 0x7c0
    li s1, 3
    bne t0, t1, local_fail
    csrr t0, 0x7c1
    ori t0, t0, 1
    csrw 0x7c1, t0
    csrr t1, 0x7c1
    bne t0, t1, local_fail
    fence iorw, iorw
    // Initialize and independently read every word before any local reads.
    // This is a RAM access test, not evidence that ECC has been enabled.
    li t0, 0xa0000000
    li t1, 0xa0010000
    li s1, 4
1:  sw zero, 0(t0)
    lw t2, 0(t0)
    bnez t2, local_fail
    addi t0, t0, 4
    bltu t0, t1, 1b
    li t0, 0xa0200000
    li t1, 0xa0210000
2:  sw zero, 0(t0)
    lw t2, 0(t0)
    bnez t2, local_fail
    addi t0, t0, 4
    bltu t0, t1, 2b
    // DLM byte lanes and last word; ILM last word is reserved by the linker.
    li t0, 0xa0200000
    li t1, 0x12345678
    sw t1, 0(t0)
    li t1, 0x55
    sb t1, 1(t0)
    lw t2, 0(t0)
    li t1, 0x12345578
    bne t1, t2, local_fail
    li t0, 0xa020fffc
    li t1, 0x76543210
    sw t1, 0(t0)
    lw t2, 0(t0)
    bne t1, t2, local_fail
    li t0, 0xa000fffc
    sw t1, 0(t0)
    lw t2, 0(t0)
    bne t1, t2, local_fail
    // Linker-bounded, word-aligned ROM->ILM copy including its final word.
    la t0, __ilm_load_start
    la t1, __ilm_start
    la t2, __ilm_end
    li s1, 5
.global local_copy_ilm
local_copy_ilm:
3:  bgeu t1, t2, 4f
    lw t3, 0(t0)
    sw t3, 0(t1)
    lw t4, 0(t1)
    bne t3, t4, local_fail
    addi t0, t0, 4
    addi t1, t1, 4
    j 3b
4:  la t0, __data_load_start
    la t1, __data_start
    la t2, __data_end
    li s1, 6
.global local_copy_data
local_copy_data:
5:  bgeu t1, t2, 6f
    lw t3, 0(t0)
    sw t3, 0(t1)
    lw t4, 0(t1)
    bne t3, t4, local_fail
    addi t0, t0, 4
    addi t1, t1, 4
    j 5b
6:  la t1, __bss_start
    la t2, __bss_end
.global local_clear_bss
local_clear_bss:
7:  bgeu t1, t2, 8f
    sw zero, 0(t1)
    lw t3, 0(t1)
    bnez t3, local_fail
    addi t1, t1, 4
    j 7b
8:  la t0, __stack_bottom
    la t1, __stack_top
    li t2, 0xa55a55a5
9:  sw t2, 0(t0)
    addi t0, t0, 4
    bltu t0, t1, 9b
    la sp, __stack_top
    fence iorw, iorw
    fence.i
    la t0, local_memory_entry
.global local_enter_ilm
local_enter_ilm:
    jr t0
.global local_fail
local_fail:
    sw s1, 8(s0)
    li t0, 0x4641494c
    sw t0, 4(s0)
.global local_halt
local_halt:
    j local_halt
.balign 4
.global local_trap
local_trap:
    li s0, 0xf8000000
    csrr t0, mcause
    sw t0, 12(s0)
    csrr t0, mepc
    sw t0, 16(s0)
    li s1, 0x80
    j local_fail
.size _start, .-_start

.section .text.ilm_entry,"ax",@progbits
.global local_memory_entry
.type local_memory_entry,@function
local_memory_entry:
    // Executed only after copy and fence.i, while the trap remains in ROM.
    li s1, 7
    la t0, local_data_probe
    lw t1, 0(t0)
    li t2, 0x494c4d31
    bne t1, t2, local_entry_fail
    la t0, local_bss_probe
    lw t1, 0(t0)
    bnez t1, local_entry_fail
    la t0, __stack_top
    bne sp, t0, local_entry_fail
    addi sp, sp, -16
    sw t2, 0(sp)
    lw t1, 0(sp)
    bne t1, t2, local_entry_fail
    addi sp, sp, 16
    li t0, 0x50415353
    sw t0, 4(s0)
    call services_main
    tail local_halt
local_entry_fail:
    tail local_fail
.size local_memory_entry, .-local_memory_entry
.section .data.startup_check,"aw",@progbits
.global local_data_probe
local_data_probe: .word 0x494c4d31
.section .bss.startup_check,"aw",@nobits
.global local_bss_probe
local_bss_probe: .space 4
