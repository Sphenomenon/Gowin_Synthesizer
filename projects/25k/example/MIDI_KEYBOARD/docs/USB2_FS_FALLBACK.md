# USB2 连接全速主机

25K USB2/USB3300 继续作为双速 Device；138K USB1 是 12 Mbit/s 的 FS Host。连接后整条总线使用 FS，不是两端分别运行 480/12 Mbit/s，也不是 USB1/USB2 端口之间的内部桥接。25K 不切换 `MIDI_USB1_FS`，不需要改接自身 USB1 数据口。

## 原有协议保持

标准 USB 枚举后，MIDIStreaming 的 OUT01/IN81 与 vendor 的 OUT02/IN82 均使用 64 字节最大包长。MIDI、MK、PL local-v1、HELLO/CAPS、会话/序号、CRC、BUSY、ACK 提交与 FIFO 背压继续遵守既有协议，见 [USB 接口](USB_PROFILE.md) 和 [PL 屏控](PANEL_DISPLAY_PROTOCOL.md)。138K 完整音频/参数 owner 不属于本次独立识别 top。

`midi_usb_hs_phy` 先发送设备 chirp；没有主机高速响应时回退 FS。2026-10-29 修正 FS 回退后的复位尾段处理：只有进入 FS 后观察到 J，才允许后续持续 SE0 再启动一轮速率协商。同一次主机复位尚未结束时保留 FS，并继续向设备核报告 bus reset；总线复位对地址、配置、toggle 和 FIFO 的清除不取消。高速协商与 HS suspend/resume 路径不改。

旧实现回退时已有连续 SE0 计数，会立即重新进入 WAIT_RST；如果主机在第二次 chirp 前结束复位，设备就停在 WAIT_RST，不响应枚举。因此，旧镜像的电脑端 HS 成功不能证明这条 FS 链路成功；需要使用修正后的新 25K 候选，不能把旧 DA 直接标成已兼容。

## 验证与复现

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb1.py
python3 projects/25k/example/MIDI_KEYBOARD/tools/run_checks.py
```

USB1 回归同时保留原来的两端软 PHY FS 测试，并加入真实 138K RV32I/生产 Host 固件、25K 原生 USB3300 boot/ULPI wrapper/双速设备核/PL endpoint 的混合链路。USB3300 是行为模型：寄存器、DIR/NXT/STP、字节流、FS NRZI/CRC 经数字 D+/D− 运行；设备 chirp 仅建模 NOPID/模式/线态控制，不模拟模拟电流驱动或高速波形。48 MHz、60 MHz、50 MHz 独立时钟和背压、无 FPGA 复位的拔插均被覆盖；LCD tile 完成仍由模型确认。

可用 `GW_USB1_EVIDENCE` 指定新的证据目录前缀。外部构建快照必须同时指定 `GW_USB1_PEER_SNAPSHOT`、`GW_USB1_PEER_MANIFEST`、`GW_USB1_PEER_MANIFEST_SHA256`，运行 `Usb1Tests.test_released_usb2_device_fallback_pair`；入口逐项校验源快照和配置头，拒绝把工作树当作实际烧录版本。旧 DA 的预期失败属于负向复现，不应计入新候选通过结果。

两板候选、资源和具体验证结果见 [2026-10-29 混合链路报告](../../../../138k/push2_workstation/usb_a/reports/USB1_HOST_USB2_25K_FS_20261029.md)。本页不授予 SRAM/Flash 操作权限。

## 接线前置条件

- 138K USB1 必须具备实际可用的 Host 角色/数据下拉；其 Type-C CC 和 VBUS 接法仍须核实，不能仅接 C-C 线就假定成立，见 [USB1 电气边界](../../../../138k/push2_workstation/usb_a/rtl/usb1/README.md#引脚和物理边界)。
- 25K USB2 使用 USB3300 内部受控 FS 端接/上拉；不要套用 25K USB1 软 PHY 的外加 D+ 上拉要求，更不要向 USB2 自行加电阻。
- 25K 的 USB3300 供电、60 MHz CLKOUT 启动和两板 VBUS 防反灌仍是独立物理门禁。没有稳定原生时钟，改协议或切换主机速度不能修复链路。
- 数字仿真、综合、P&R、板上枚举、实际演奏/显示、SRAM 下载和 Flash 固化是不同阶段；完整业务和原部署回退信息必须保留。
