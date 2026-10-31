  assign core_ce=(pending || sample_ce_i) && core_sample_ready && vec_ready && fx_ready &&
      !synth_joined && !vec_joined && !panic_accept && !native_clear && !runtime_config_block && !runtime_config_busy && !runtime_fault &&
      (!REQUEST_DRIVEN_RENDER || (RUNTIME_RATE_ENABLE ? runtime_quiescent : legacy_cancel_tail==0));
