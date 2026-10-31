# TF DMA reference

`workstation_tf_runtime_dma_pre_occupancy.sv` is the byte-exact maintained DMA at commit `47a7ab2`, SHA256 `bc1dcfad79af5777c27d7bfa65ae3b397ce103ca0a992b938027201877119752`. It is simulation-only. The equivalence runner pins its bytes, renames only the reference module in a temporary output, and compares the maintained implementation's public outputs and unchanged state every half-cycle. Production compilation consumes only the maintained RTL.
