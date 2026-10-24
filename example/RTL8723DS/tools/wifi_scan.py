#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# RTL8723D initialization adapted from Realtek's GPL v2 driver.
# See vendor/wifi/provenance.json and COPYING for sources and license.
"""Passive 2.4 GHz scan using the board RTL8723DS and SRAM SDIO/JTAG bridge."""
import argparse
import datetime
import hashlib
import json
import struct
import time
from pathlib import Path

from jtag_mpsse import Jtag
from wifi_sdio import Sdio

VENDOR = Path(__file__).resolve().parents[1]/'vendor/wifi'


class Wifi:
    def __init__(self, sdio, report):
        self.s = sdio
        self.report = report
        self.r = sdio.read
        self.w = sdio.write
        self.rx_counter = 0
        self.coex_saved = None
        self.h2c_box = 0
        self.tables = json.loads((VENDOR/'register_tables.json').read_text())

    def stage(self, name):
        self.report['stage'] = name
        print(name, flush=True)

    def mask(self, address, mask, value, size=1, local=False):
        old = self.r(address, size, local)
        self.w(address, (old & ~mask) | (value & mask), size, local)

    def poll(self, address, mask, expected, size=1, local=False, timeout=2):
        until = time.monotonic()+timeout
        while True:
            value = self.r(address, size, local)
            if value & mask == expected:
                return value
            if time.monotonic() > until:
                raise TimeoutError(f'reg {address:04x}={value:08x}, mask {mask:08x}, expected {expected:08x}')
            time.sleep(.001)

    def power_on(self):
        self.stage('power_on_cmd52')
        self.s.powered = False
        self.w(0x1c, 0)
        # rtl8723D_card_enable_flow: CARDDIS -> CARDEMU -> ACT, SDIO entries.
        self.mask(5, 0x88, 0)
        self.mask(0x86, 1, 0, local=True)
        self.poll(0x86, 2, 2, local=True)
        self.mask(5, 0x18, 0)
        self.mask(0x23, 0x10, 0)
        self.mask(0x20, 1, 1)
        self.mask(0x67, 0x10, 0)
        time.sleep(.001)
        self.mask(0, 0x20, 0)
        self.mask(5, 0x1c, 0)
        self.poll(6, 2, 2)
        self.mask(6, 1, 1)
        self.poll(5, 3, 0)
        self.mask(5, 0x80, 0)
        self.mask(5, 0x18, 0)
        self.mask(5, 1, 1)
        self.poll(5, 1, 0)
        for address, mask, value in [(0x10,0x40,0x40),(0x49,2,2),(0x63,2,2),
                                     (0x62,2,0),(0x58,1,1),(0x5a,2,2),(0x69,0x40,0x40)]:
            self.mask(address, mask, value)
        for address, value in [(0x1f,0),(0x77,0),(0x1f,7),(0x77,7)]:
            self.w(address, value)
        before = {a:self.r(a,4) for a in (0,4,0xf0)}
        self.s.powered = True
        self.stage('power_on_cmd53_check')
        after = {a:self.r(a,4) for a in before}
        if before != after:
            raise RuntimeError(f'CMD52/CMD53 register mismatch: {before} != {after}')
        self.report['cmd53_verified'] = True
        self.mask(4, 0x8000, 0x8000, 2)
        self.w(0x100, 0)
        self.w(0x100, self.r(0x100,2) | 0x63f, 2)
        # Read-back test scratch register, restore its exact prior value.
        original = self.r(0x1b8,4)
        for value in (0x12345678,0x87654321):
            self.w(0x1b8,value,4)
            if self.r(0x1b8,4)!=value:
                raise RuntimeError('CMD53 write/read scratch mismatch')
        self.w(0x1b8,original,4)
        self.report['cmd53_write_read_verified'] = True
        self.mask(0x38,0x800,0x800,2)
        self.mask(0x4c,0x800000,0x800000,4)
        self.mask(0x64,1,0)

    def reset_mcu(self):
        self.mask(0x1d,1,0)
        self.mask(3,4,0)
        self.mask(0x1d,1,1)
        self.mask(3,4,4)

    def calibration(self):
        self.stage('read_factory_calibration')
        # Read efuse only. The programming voltage and write strobe are never enabled.
        saved_access=self.r(0xcf)
        self.w(0xcf,0x69)
        self.mask(2,0x1000,0x1000,2)
        self.mask(8,0x22,0x22,2)
        self.mask(0x34,0x300,0,2) # Wi-Fi bank 0
        raw=bytearray();logical=bytearray([255]*512)
        def byte():
            address=len(raw)
            if address>=512:raise RuntimeError('Factory efuse packet boundary exceeds bank')
            self.w(0x31,address&255)
            self.mask(0x32,3,address>>8)
            self.mask(0x33,0x80,0)
            self.poll(0x33,0x80,0x80)
            value=self.r(0x30);raw.append(value)
            return value
        try:
            while True:
                header=byte()
                if header==255:break
                if header&31==15:
                    ext=byte();offset=((header>>5)&7)|((ext&0xf0)>>1);words=ext&15
                else:offset=header>>4;words=header&15
                for word in range(4):
                    if not words&(1<<word):
                        lo,hi=byte(),byte();position=offset*8+word*2
                        if position+1>=512:raise RuntimeError('Invalid factory efuse logical offset')
                        logical[position:position+2]=bytes([lo,hi])
        finally:self.w(0xcf,saved_access)
        self.crystal_cap=logical[0xb9]&63 if logical[0xb9]!=255 else 0x20
        self.antenna_aux=bool(logical[0xc3]&0x40) if logical[0xc3]!=255 else False
        self.report['factory_calibration']=dict(crystal_cap=self.crystal_cap,antenna='S0' if self.antenna_aux else 'S1',
            wifi_mac=':'.join(f'{b:02x}' for b in logical[0x11a:0x120]),raw_length=len(raw),logical_hex=logical.hex())

    def firmware(self):
        self.stage('firmware_download')
        image = (VENDOR/'rtl8723d_fw_nic.bin').read_bytes()
        provenance = json.loads((VENDOR/'provenance.json').read_text())
        if hashlib.sha256(image).hexdigest()!=provenance['firmware_sha256']:
            raise ValueError('Wi-Fi firmware hash mismatch')
        signature, _, version = struct.unpack_from('<HHH',image)
        if signature & 0xfff0 != 0x23d0:
            raise ValueError(f'Unexpected firmware signature {signature:04x}')
        payload = image[32:]
        self.report['firmware'] = dict(signature=f'{signature:04x}',version=version,length=len(payload),ready=False)
        self.w(0x4d0,0)
        if self.r(0x80)&0x80:
            self.w(0x80,0)
            self.reset_mcu()
        self.mask(3,4,4)
        self.mask(0x80,1,1)
        self.poll(0x80,1,1)
        self.mask(0x82,8,0)
        self.mask(0x80,4,4)  # W1C checksum report before writing a new image.
        for page, start in enumerate(range(0,len(payload),4096)):
            self.mask(0x82,7,page)
            block = payload[start:start+4096]
            # The vendor SDIO driver uses 32-bit writes to the paged MCU window.
            # Larger CMD53 bursts are validated separately before enabling them.
            for offset in range(0,len(block),4):
                value = block[offset:offset+4]
                self.s.cmd53(self.s.address(0x1000+offset), data=value)
            print(f'firmware page {page}: {start+len(block)}/{len(payload)}',flush=True)
        self.poll(0x80,4,4,timeout=3)
        self.mask(0x80,1,0)
        self.mask(0x80,0x42,2)
        self.reset_mcu()
        self.poll(0x80,0xc6,0xc6,timeout=3)
        self.report['firmware']['ready'] = True
        self.report['firmware']['mcufwdl'] = f'{self.r(0x80,4):08x}'

    def table(self, name, kind):
        self.stage('configure_'+name)
        for address, value in self.tables[name]:
            delays = {0xfe:.05,0xfd:.005,0xfc:.001,0xfb:.00005,0xfa:.000005,0xf9:.000001}
            if kind=='rf' and address in (0xfe,0xffe):
                time.sleep(.05)
            elif kind=='bb' and address in delays:
                time.sleep(delays[address])
            elif kind=='rf':
                self.rf_write(address,value)
            else:
                self.w(address,value,1 if kind=='mac' else 4)

    def h2c(self, command, payload):
        """Publish EXT before the main mailbox, then wait for firmware consumption."""
        payload=bytes(payload)
        if not 0<=command<=255 or len(payload)>7:
            raise ValueError('H2C requires an 8-bit command and at most 7 payload bytes')
        box=self.h2c_box
        self.poll(0x1cc,1<<box,0,timeout=2)
        data=bytes([command])+payload+bytes(7-len(payload))
        if len(payload)>3:
            self.w(0x1f0+box*4,int.from_bytes(data[4:8],'little'),4)
        self.w(0x1d0+box*4,int.from_bytes(data[:4],'little'),4)
        self.poll(0x1cc,1<<box,0,timeout=2)
        self.h2c_box=(box+1)%4

    def active_mode(self):
        self.stage('firmware_active_mode')
        # SET_PWR_MODE: active, RLBM=2, awake interval=4, AllON=0x0c.
        # Firmware-ready alone does not bring the receive RF out of power save.
        self.h2c(0x20,bytes([0,2,4,0,0x0c,0x40,0]))
        self.report['firmware_active_command_consumed']=True

    def rf_write(self,address,value,path=0):
        self.w(0x840+4*path, ((address & 255)<<20)|(value & 0xfffff),4)

    def rf_read(self,address,path=0):
        target = 0x824+8*path
        value = (self.r(target,4)&~0xff800000)|((address&255)<<23)|0x80000000
        self.w(target,value&~0x80000000,4)
        current = self.r(0x824,4)
        self.w(0x824,current&~0x80000000,4)
        self.w(0x824,current|0x80000000,4)
        time.sleep(.001)
        pi = self.r(0x820+8*path,4)&0x100
        return self.r((0x8b8 if pi else 0x8a0)+4*path,4)&0xfffff

    def phy(self):
        self.table('MAC_REG','mac')
        self.mask(2,0x2003,0x2003,2)
        self.w(0x1f,7)
        self.w(2,0xe3)
        self.w(0x25,0x80)
        self.table('PHY_REG','bb')
        self.table('AGC_TAB','bb')
        cap=getattr(self,'crystal_cap',0x20)
        self.mask(0x2c,0xfff000,(cap|(cap<<6))<<12,4)
        old_env = self.r(0x870,4)&0x10
        self.mask(0x860,0x100000,0x100000,4)
        self.mask(0x860,0x10,0x10,4)
        self.mask(0x824,0xc00,0,4)
        self.table('RadioA','rf')
        self.mask(0x870,0x10,old_env,4)
        self.mask(0x78,0x8010,0x8010,2)
        self.rf_channel = self.rf_read(0x18)
        if self.rf_channel in (0,0xfffff):
            raise RuntimeError(f'Invalid RF channel register {self.rf_channel:05x}')
        self.report['rf_channel_initial'] = f'{self.rf_channel:05x}'

    def receive_setup(self):
        self.stage('receive_setup')
        self.w(0x214,2)
        self.w(0x200,0x80e7020c,4) # 0xf7 pages, HQ12, LQ2, NQ2, public0xe7.
        for address in (0x424,0x425,0x45d,0x114,0x209):
            self.w(address,0xf8)
        self.mask(0x224,0x10000,0x10000,4)
        self.poll(0x224,0x10000,0,4)
        self.w(0x116,0x3f7f,2)
        self.w(0x104,0x11)
        self.w(0x60f,4)  # 32-byte PHY information
        self.mask(0x102,3,0) # no link, no ACK generation to captured packets
        self.w(0x608,0x7000200e,4) # broadcast/multicast, management, PHY; no BSSID filter
        self.w(0x620,0xffffffff,4);self.w(0x624,0xffffffff,4)
        self.w(0x6a0,0xffff,2);self.w(0x6a2,0,2);self.w(0x6a4,0,2)
        self.mask(0x10c,4,0) # disable RX DMA aggregation: one frame per FIFO request
        self.mask(0x290,2,0)
        self.w(0x280,0x0101,2)
        self.w(0x60c,0x18) # vendor RX packet/burst limit, 12 KiB
        self.w(0x4ca,0x0a0a,2)
        self.w(0x14,1,4,True) # RX request interrupt (polling still reads RX0_REQ_LEN)
        self.mask(0x800,0x3000000,0x3000000,4)
        self.w(0x4e,0x82)
        self.w(0,0,4,True) # SDIO TX/RX timer masking control
        self.w(0x550,0x1018,2) # disable TSF updates on both ports
        self.w(0x512,0)
        self.w(0x456,0x1c)
        self.w(0x522,0)
        self.mask(0x100,0xc0,0xc0) # vendor MAC TX/RX enable; host queues no TX frames
        self.mask(0x668,0x180,0,2)
        self.w(0x483,0)
        self.mask(0x800,1,0,4);self.mask(0x900,1,0,4)
        self.mask(0x954,0x0f080000,0x0a080000,4)
        self.scan_antenna()
        self.report['receive_registers'] = {f'{a:04x}':f'{self.r(a,4):08x}' for a in (0x100,0x608,0x800,0x870,0x948)}

    def coex_read(self, address):
        self.w(0x7c0,0x800f0000|address,4)
        self.poll(0x7c3,0x20,0x20)
        return self.r(0x7c8,4)

    def coex_write(self,address,value):
        self.poll(0x7c3,0x20,0x20)
        self.w(0x7c4,value,4)
        self.w(0x7c0,0xc00f0000|address,4)

    def scan_antenna(self):
        # Shared antenna grants must be initialized: their reset state is zero.
        # Retain both radio grants; the scan receives only and emits no probes.
        self.coex_saved = dict(registers={a:self.r(a,n) for a,n in [(0x67,1),(0x73,1),(0x948,2)]},
                               indirect={a:self.coex_read(a) for a in (0x38,0xa0,0xa4)})
        self.coex_write(0x38,(self.coex_saved['indirect'][0x38]&~0xff80)|0xff00)
        self.coex_write(0xa0,0xffff);self.coex_write(0xa4,0xffff)
        self.mask(0x67,0x80,0x80)
        self.mask(0x73,4,4)
        self.w(0x948,0x280 if getattr(self,'antenna_aux',False) else 0,2)
        self.report['coex_scan_grants']=f'{self.coex_read(0x38):08x}'

    def restore_antenna(self):
        if self.coex_saved is None:
            return
        for a,v in self.coex_saved['indirect'].items():self.coex_write(a,v)
        for a,v in self.coex_saved['registers'].items():self.w(a,v,2 if a==0x948 else 1)
        self.report['antenna_restored']=True

    def finish_scan(self):
        self.restore_antenna()
        # A fresh Wi-Fi MAC reset has no running PTA coexistence scheduler.
        # Hand the shared antenna back to BT (vendor WLAN_OFF ownership),
        # rather than leaving a powered receive MAC competing with BLE.
        self.mask(0x100,0xc0,0)
        grants=(self.coex_read(0x38)&~0xff80)|0xdd00 # BT high, WL low, LTE off
        self.coex_write(0x38,grants)
        self.mask(0x67,0x80,0)
        self.mask(0x73,4,0)
        self.report['scan_cleanup']=dict(mac_receive_enabled=False,antenna_owner='BT',
                                         coex_grants=f'{self.coex_read(0x38):08x}')

    def channel(self, channel):
        self.stage(f'channel_{channel}')
        value = (self.rf_channel&~0xfff)|0xc00|channel
        self.rf_write(0x18,value)
        self.rf_write(0x18,value,1)
        time.sleep(.02)
        actual = self.rf_read(0x18)
        if actual&255!=channel:
            raise RuntimeError(f'RF tune readback {actual:05x} != channel {channel}')

    def read_packet(self):
        size = self.r(0x1c,2,True)
        if not size:
            return None
        if size>2048:
            raise RuntimeError(f'RX FIFO frame {size} exceeds 2048-byte bridge buffer')
        # Vendor recv_entry rounds to 4 bytes before read_port's block rounding.
        transfer = (size+3)//4*4 if size<=512 else (size+511)//512*512
        data = self.s.cmd53(0xe000|(self.rx_counter&3), transfer)
        self.rx_counter+=1
        return data[:size]


def parse_beacon(data, tuned_channel):
    if len(data)<24:
        return None
    d0,d1,d2 = struct.unpack_from('<III',data)
    size = d0&0x3fff
    start = 24+((d0>>16)&15)*8+((d0>>24)&3)
    if d0&0xc000 or d2&(1<<28) or size<36 or start+size>len(data):
        return None
    frame = data[start:start+size]
    if frame[0] not in (0x80,0x50) or frame[1]&0x43:
        return None
    bssid = ':'.join(f'{b:02x}' for b in frame[16:22])
    capability = int.from_bytes(frame[34:36],'little')
    ies = {};pos=36
    while pos+2<=len(frame):
        tag,length=frame[pos:pos+2];pos+=2
        if pos+length>len(frame):
            return None
        ies.setdefault(tag,[]).append(frame[pos:pos+length]);pos+=length
    if 0 not in ies:
        return None
    ssid = ies[0][0]
    if len(ssid)>32:
        return None
    channel = ies.get(3,[bytes([tuned_channel])])[0]
    security = 'Open'
    if capability&16:
        security = 'Privacy'
    if 48 in ies:
        security = 'WPA2/RSN'
    elif any(v.startswith(b'\x00\x50\xf2\x01') for v in ies.get(221,[])):
        security = 'WPA'
    return dict(ssid=ssid.decode('utf-8',errors='replace'),ssid_hex=ssid.hex(),bssid=bssid,
                channel=channel[0] if channel else tuned_channel,security=security,
                frame_type='beacon' if frame[0]&0xfc==0x80 else 'probe_response')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--channels',default='1,6,11,2,3,4,5,7,8,9,10,12,13')
    parser.add_argument('--dwell',type=float,default=1)
    parser.add_argument('--stop-after',choices=['power','firmware','phy'])
    parser.add_argument('--location',type=int)
    args=parser.parse_args()
    channels=[int(s) for s in args.channels.split(',')]
    if any(c<1 or c>13 for c in channels) or args.dwell<=0:
        parser.error('channels must be 1..13 and dwell must be positive')
    report=dict(time=datetime.datetime.now().astimezone().isoformat(),passed=False,
                operation='RTL8723DS passive Wi-Fi scan',access_points=[],packets=0,scan_completed=False,
                raw_rx_packets=[])
    try:
        with Jtag(args.location) as jtag:
            sdio=Sdio(jtag)
            report['identity']=sdio.enumerate()
            wifi=Wifi(sdio,report)
            wifi.power_on()
            if args.stop_after!='power':
                wifi.calibration()
                wifi.firmware()
                if args.stop_after!='firmware':
                    wifi.phy()
                    if args.stop_after!='phy':
                        try:
                            wifi.receive_setup()
                            if wifi.antenna_aux:
                                raise RuntimeError('RX IQ calibration currently supports factory S1 only')
                            from wifi_iqk import calibrate_s1
                            calibrate_s1(wifi)
                            wifi.active_mode()
                            found={}
                            for channel in channels:
                                wifi.channel(channel)
                                until=time.monotonic()+args.dwell
                                while time.monotonic()<until:
                                    data=wifi.read_packet()
                                    if data is None:
                                        time.sleep(.01);continue
                                    report['packets']+=1
                                    if len(report['raw_rx_packets'])<64:
                                        report['raw_rx_packets'].append(data.hex())
                                    ap=parse_beacon(data,channel)
                                    if ap:
                                        first=ap['bssid'] not in found
                                        found[ap['bssid']]=ap
                                        report['access_points']=list(found.values())
                                        if first:print(json.dumps(ap,ensure_ascii=False),flush=True)
                            report['channels']=channels;report['scan_completed']=True
                        finally:
                            wifi.finish_scan()
            report['passed']=bool(args.stop_after) or bool(report['access_points'])
            report['status']=('initialization_passed' if args.stop_after else
                              'beacons_received' if report['passed'] else 'no_beacons_received')
    except Exception as error:
        report['error']=f'{type(error).__name__}: {error}'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
