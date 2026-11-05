"""Local W native-fault consumer proofs; never complete CDC/PLL acceptance."""
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_recording_phase1_cdc import complete_closure


def require(condition, message):
    if not condition:
        raise ValueError('task3 W fault boundary: ' + message)


def audit(n, *, cnn_control=False):
    g = Graph(n)
    tags = sorted(p for p in g.regs if p.startswith('u_task3_media/memory/u_arbiter/')
                  and '/g_recording.tags[' in p)
    require(len(tags) == 128, 'recording tag register inventory changed')
    require(all(n.pin(p, 'CLK') == 'memory_clk' for p in tags), 'tag clock net changed')
    closure = complete_closure(n, g, tags)

    def chain(scope, stem):
        first, last = [g.register(scope, stem, bit) for bit in (0, 1)]
        require(n.pin(first, 'CLK') == n.pin(last, 'CLK') == 'clk_50m', 'control clock changed')
        require(n.pin(first, 'CE') in g.high and n.pin(last, 'CE') in g.high,
                'synchronizer enable is gated')
        require(n.pin(first, 'CLEAR') == n.pin(last, 'CLEAR'), 'synchronizer reset differs')
        require(n.pin(last, 'D') == n.pin(first, 'Q'), 'synchronizer stages disconnected')
        first_closure = complete_closure(n, g, [first])
        require(first_closure['ff_endpoints'] == {last + '/D': 'clk_50m'} and
                not first_closure['primitive_endpoints'] and not first_closure['top_output_endpoints'],
                'first synchronizer stage has another consumer')
        require(first + '/D' in closure['ff_endpoints'], 'native fault disconnected from first stage')
        return dict(first=first, last=last, first_stage_complete_closure=first_closure,
                    final_stage_complete_closure=complete_closure(n, g, [last]),
                    direct_clock_and_ungated_CE=True)

    recording = chain('u_task3_media', 'ready_control')
    ble = 'u_bluetooth/u_core/application/command_endpoint/recording/'
    require(not any(p.startswith(ble) for p in closure['ff_endpoints']),
            'native tags still bypass synchronization into BLE recording')
    cnn = None
    if cnn_control:
        cnn = chain('u_task3_media/cnn_stream', 'transport_fault_control')
        core = 'u_task3_media/cnn_stream/task_service/cnn/u_basic_pitch/'
        require(not any(p.startswith(core) for collection in ('ff_endpoints', 'primitive_endpoints')
                        for p in closure[collection]),
                'native tags still bypass synchronization into CNN core')
    return dict(scope='Recording tag combinational closure to BLE recording and optional CNN core only',
                recording_tag_FFs=tags, native_clock_net='memory_clk', recording_ready=recording,
                CNN_fault_control=cnn, native_tag_complete_closure=closure,
                direct_tag_to_BLE_recording_absent=True,
                direct_tag_to_CNN_core_absent=True if cnn_control else None,
                other_native_status_sources_proven=False, complete_CDC_accepted=False,
                routed_timing_verified=False, hardware_tested=False)
