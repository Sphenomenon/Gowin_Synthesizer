.option norvc
.section .text.start,"ax",@progbits
.global _start
_start:
    csrw mie, zero
    la t0, trap
    csrw mtvec, t0
    li sp, 0x2000
    li s0, 0xf8000000
    li t0, 0x43505531
    sw t0, 0(s0)
    // Exercise byte lanes, stack/data RAM and an independent readback.
    li t0, 0x100
    li t1, 0x12345678
    sw t1, 0(t0)
    lw t2, 0(t0)
    bne t1, t2, fail
    li t1, 0x55
    sb t1, 1(t0)
    li t1, 0x12345578
    lw t2, 0(t0)
    bne t1, t2, fail
    li t1, 0x76543210
    sw t1, 4(t0)
    lw t2, 4(t0)
    bne t1, t2, fail
    li t0, 0x50415353
    sw t0, 4(s0)
    la t0, __data_load_start
    la t1, __data_start
    la t2, __data_end
1:  bgeu t1, t2, 2f
    lw t3, 0(t0)
    sw t3, 0(t1)
    addi t0, t0, 4
    addi t1, t1, 4
    j 1b
2:  la t1, __bss_start
    la t2, __bss_end
3:  bgeu t1, t2, 4f
    sw zero, 0(t1)
    addi t1, t1, 4
    j 3b
4:
    call services_main
    j halt
fail:
    li t0, 0x4641494c
    sw t0, 4(s0)
    j fail
.balign 4
trap:
    csrr t0, mcause
    sw t0, 12(s0)
    csrr t0, mepc
    sw t0, 16(s0)
halt:
    j halt
