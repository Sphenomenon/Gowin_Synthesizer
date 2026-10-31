"""Assess captured cache-PMA diagnostic words; never opens a serial port."""
from tools.decode_ae350_local_probe import frames

def assess(frame,manifest):
    w=frame['words']
    checks=dict(identity=frame['user_code']==int(manifest['user_code'],16),
        schema=w[0]==0x43434831 and w[5]==0x43414331,
        loader=w[1]==0x50415353,terminal=w[6]==0x50415353 and w[7]==0 and w[8]==10,
        initial_off=w[19]&3==0,enabled=w[20]==w[19]|3,restored_off=w[21]==w[19]&~3,
        initial_pma=w[25:29]==[0,0,0,0],
        geometry=w[22]==32768 and w[23]==32768 and w[24]==0x00da00da,
        attributes=w[31:34]==[0x0f2f,0x5ff,0x11ff],
        dirty_observed=w[34]==0x6ca84ef7 and w[35]==0x9357b108 and w[34]==w[36],
        shared_handoff=w[37]==0x6789abcd and w[38]==w[34] and w[39]==w[37],
        instruction_handoff=w[40:43]==[17,17,29],
        mmio_guard=w[44]==(w[43]+1)&0xffffffff,
        restore=w[45]==3,cctl_commands=w[46]==2308,layout=w[48:51]==[4096,0x1000,0x4000],
        no_trap=w[15]==0,features=w[54:58]==[1,1,4096,1],
        external_fault_absent=w[59]==0,fresh_snapshot=w[61]&31==15)
    return dict(sequence=frame['sequence'],checks=checks,cache_probe_checks_passed=all(checks.values()),
        failure_bits=w[7],phase=w[8],first_mismatch=dict(expected=w[52],actual=w[53]),
        trap=dict(cause=w[27],pc=w[28]),hardware_acceptance=False,
        interpretation='Requires exact candidate/JTAG/timing binding; checks cover one4KiB page, not32KiB full-way stress.')

def decode(data,manifest):
    if manifest.get('probe_program')!='cache-pma-v1':raise ValueError('explicit cache-PMA manifest required')
    accepted,rejected=frames(data)
    if not accepted:raise ValueError('no complete CRC-valid cache probe frame')
    observations=[assess(frame,manifest) for frame in accepted]
    return dict(identity=manifest['identity'],observations=observations,latest=observations[-1],rejected_frames=rejected)
