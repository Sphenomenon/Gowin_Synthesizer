# TF simulation references

`workstation_tf_runtime_dma_pre_occupancy.sv` is the byte-exact maintained DMA at commit `47a7ab2`, SHA256 `bc1dcfad79af5777c27d7bfa65ae3b397ce103ca0a992b938027201877119752`. It is simulation-only. The equivalence runner pins its bytes, renames only the reference module in a temporary output, and compares the maintained implementation's public outputs and unchanged state every half-cycle. Production compilation consumes only the maintained RTL.

`workstation_tf_runtime_service_before_failure_factor.sv` is the complete service consumed by M11, SHA256 `c42dc0bbe4919adf86275388239f52ccf63d6670b30c2bdf362ebea5bcb0b483`. `run_tf_failure_factor_equivalence.py` pins these bytes, verifies that reversing only the reviewed combinational rewrite reconstructs the full file, and renames only the reference module for parallel real-path simulations. The fixture is not a production input.
