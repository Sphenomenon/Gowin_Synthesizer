"""Explicit native raw BLE storage selection for the panel-off revision2 profile."""
POLICY = 'native_raw_ddr_v1'
SOURCES = (
    'rtl/memory/workstation_ble_raw_ddr_store.sv',
    'rtl/memory/workstation_recording_ddr_owner_mux.sv',
    'rtl/memory/workstation_recording_ddr_authority.sv',
)
DEPENDENCIES = (
    'rtl/memory/WORKSTATION_BLE_RAW_DDR_STORE.md',
    'rtl/memory/RECORDING_DDR_AUTHORITY_CONTRACT.md',
    'tools/workstation_bluetooth_ddr.py',
    'tools/workstation_ble_recording_policy.py',
)


def metadata():
    return dict(policy=POLICY, raw_store='recording_ble_store',
        business_owner='u_bluetooth/u_core/application/command_endpoint/recording',
        object_ids_tasks_crc_codec_transfer_owned_by_ble=True,
        capacity_frames=16384, capacity_bytes=65536, sample_rates_hz=[48000],
        format_extended=False, sample_word_latency_control_cycles=1,
        byte_base='PRJ1_DDR_RECORDING_BLE_BYTE_BASE', native_base='PRJ1_DDR_RECORDING_BLE_APP_BASE',
        address_authority='rtl/ddr_address_map.vh', cpu_window_disjoint=True,
        control_clock='clk_50m', native_clock='memory_clk',
        cache_bytes=8192, max_fetch_bytes=8112, fifo_address_bits=8,
        command_timeout_memory_cycles=10000, read_timeout_memory_cycles=10000,
        raw_drain_timeout_control_cycles=5000000,
        owner8_mux='recording_owner8', channel_authority='recording_authority',
        root_reset='reset_n', observed_ledger_reset='ddr_client_reset_n',
        memory_reset='recording_memory_reset_n_root_only_two_edge_local_release',
        local_reset_rearms_channel=False, registered_bridge_faults_only=True,
        net_resource_saving_proven=False, physical_cdc_accepted=False,
        synthesis=False, pnr=False, hardware_tested=False, deployment_allowed=False)
