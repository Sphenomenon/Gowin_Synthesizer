    .section .text.cache_probe_trap,"ax",@progbits
    .balign 4
    .global cache_probe_trap
cache_probe_trap:
    li t1,0xf8000000
    csrr t0,mcause
    sw t0,108(t1)
    csrr t0,mepc
    sw t0,112(t1)
    lw t0,60(t1)
    addi t0,t0,1
    sw t0,60(t1)
    li t0,0x80000000
    sw t0,28(t1)
    li t0,0x80
    sw t0,32(t1)
    // Never treat an unsupported CSR/control write as a successful operation.
    // Loader has already established MCACHE_CTL availability. Dirty test-page
    // data is discarded on this terminal trap path and is never published.
    csrr t0,0x7ca
    andi t0,t0,-4
    csrw 0x7ca,t0
    csrr t0,0x7ca
    sw t0,84(t1)
    andi t0,t0,3
    bnez t0,cache_probe_halt
    la t2,cache_pma_armed
    lw t0,0(t2)
    beqz t0,1f
    csrw 0xbc0,zero
    la t2,cache_saved_addrs
    lw t0,0(t2)
    csrw 0xbd0,t0
    lw t0,4(t2)
    csrw 0xbd1,t0
1:  li t0,0x4641494c
    sw t0,24(t1)
    .global cache_probe_halt
cache_probe_halt:
    j cache_probe_halt

    .balign 4
    .global cache_page_call
    .type cache_page_call,@function
cache_page_call:
    addi sp,sp,-16
    sw ra,12(sp)
    lui t0,1
    jalr ra,t0,0
    lw ra,12(sp)
    addi sp,sp,16
    ret
    .size cache_page_call,.-cache_page_call
