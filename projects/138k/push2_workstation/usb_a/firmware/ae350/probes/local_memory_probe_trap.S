    .section .text.probe_trap,"ax",@progbits
    .balign 4
    .global probe_trap
probe_trap:
    csrr t0,mcause
    li t1,0xf8000000
    sw t0,116(t1)
    csrr t2,mepc
    sw t2,120(t1)
    lw t3,60(t1)
    addi t3,t3,1
    sw t3,60(t1)
    li t3,2
    bne t0,t3,probe_unexpected_trap
    la t0,probe_expected_pc
    lw t0,0(t0)
    bne t0,t2,probe_unexpected_trap
    addi t2,t2,4
    csrw mepc,t2
    li a0,0
    li a1,0
    mret
probe_unexpected_trap:
    li t0,0x4641494c
    sw t0,24(t1)
    li t0,0x80000080
    sw t0,32(t1)
    sw sp,48(t1)
    .global probe_halt
probe_halt:
    j probe_halt
