# P18 Push poly-aftertouch 与事件驱动屏幕候选

状态：P18 已完成源码、仿真、综合/布局布线和 SRAM 下载，等待用户实体压力与屏幕验收。P17 实测为压力变化基本不可见、Push 屏幕延迟接近一秒；P18 针对这两个现象修改，不改 HDMI、DDR 显示数据、C 模式 32 声部、P10 串行效果链或 P2 低音路径。

## 协议依据和改动

- Ableton 官方 `push-interface` 手册说明，Push 2 持续压力使用 channel pressure 或 poly key pressure，默认是 channel pressure；`Set Aftertouch Mode` 命令号为 `0x1E`，值 `1` 选择 poly key pressure。P18 在既有 Live mode、亮度和触摸条初始化之后显式发送该命令，使每个按住的 pad 都携带自己的 note 和连续压力值。
- mapper 继续接受手册规定的 CIN `0xA` poly key pressure 和 CIN `0xD` channel pressure。两者只更新已分配声部的 expression，不重触发或释放音符。未加入重复 Note-On 等未见于手册的猜测格式。
- Push 屏幕仍使用合法的 16 字节帧头和 640×512 字节像素数据。固件只在 control/options、held mask、note/velocity 变化时发送新整帧；UI 不变时不再循环占用 327,696 字节整帧。空闲循环每轮轮询 MIDI 并延时 1 ms；传帧期间每 4 个像素包轮询 MIDI、每 32 包服务灯光。
- 状态在传帧期间再次变化时，帧尾会检测到 dirty 状态并发送最新一帧。传输失败会使显示状态失效，连接仍在时下一轮重试。

本地工程没有找到可确认的 Push 白皮书副本。协议核对使用 Ableton 官方仓库 `push-interface` 的 `AbletonPush2MIDIDisplayInterface.asc`（commit `5eb352fe3da9d07891efb7447191c03a66d9fbdd`）和官方示例 `push2-display-with-juce`（commit `48e9be846bda686b97a0df7635d80e63a51a5e4b`），并对照本地已验收参考驱动 `migration/midi_device_reference/push2_usb_host/vendor/push2_display_tx.sv`。

## 屏幕刷新边界

官方手册规定，Push 2 收到完整像素数据后才显示新帧；其它帧头或数据长度为保留格式。屏幕内部以 60 fps 扫描并在新帧未到时重复旧帧。当前 J18 H13/G13 软件 PHY 是 12 Mbit/s Full-Speed；本地板测记录的首帧约 996 ms、后续整帧约 450 ms。

30 个完整帧每秒需要 `327696×30×8 = 78,647,040 bit/s` 的纯载荷，已经超过 12 Mbit/s，未计 USB 开销。因此 P18 实现的是每秒远高于 30 次的输入/状态轮询以及状态变化优先发帧，不能把它写成 30 个完整画面每秒。要达到 30 个完整画面每秒，需要 J18 上可用的 USB 2.0 High-Speed 物理层；当前源码和板测记录明确表明该高速电气路径尚未建立，本阶段没有改用 CH569。

## 仿真与回归

- `p18_aftertouch_init/simulation.log`：五个启动包按序完成，最后一包为 `Set Aftertouch Mode 0x1E, mode 1`。
- `p18_source_pressure/simulation.log`：poly pressure 0/127 和 channel pressure 23 都生成 kind 5 expression，held mask 保持，未重新分配音符。
- `production_usb_firmware_test.log`：热插拔、DATA toggle、帧中 MIDI、16 字节帧头加 640 个数据包，以及首次状态/不变状态/再次变化的事件驱动判断通过。
- `p11_shared_152131_942809/simulation.log`：Push 共享摘要和 effect-mask latch 通过。
- `cpu_audio_sim_152131_927170/simulation.log`：3696 个音频帧、3574 个非零帧，A/B/C、五音色、FX7、expression、路由、释放和精确 48 kHz 通过，无 audio fault。

以上是离线 RTL、固件和 CPU/音频模型结果，不代替实体 Push、HDMI 或耳机验收。

## 综合、布局布线与审计

构建目录：`results/build_20260915_150844_068302`，器件 `GW5AST-LV138PG484AC2/I1`。

| 项目 | 结果 |
|---|---:|
| setup 违例端点 | 0 |
| hold 违例端点 | 0 |
| 最差 setup slack | +0.048 ns |
| Logic | 33,760 |
| Register | 25,165 |
| BSRAM | 253 |
| DSP | 43.5 |

完整 routed audit 没有通过，原因仍是已有 `u_managed/effect_mask_sync_[0..2]_s0/RESET` stopped-clock reset 覆盖缺口。本轮没有修改或放宽该检查，不能把它记录成 audit pass。

## SRAM

- 位流：`results/build_20260915_150844_068302/Prj1/impl/pnr/Prj1.fs`
- SHA256：`b9ef014335aec28ac3f1272c128b710ca4cb8bfe87a93044c88d168eee5af72f`
- UserCode：`0x0000D914`
- 下载记录：`../results/sram_20260915_152806_287986/result.json`
- 写前读回 P17 `0x0000F123`，SRAM 写入通过，写后读回 `0x0000D914`。
- `fpga_flash_written` 为 `false`，Flash 未写。

## 实体验收

请在当前 P18 SRAM 上检查：

1. 按住同一 pad，压力从轻到重再变轻；耳机响度和 Push 的 velocity/pressure 数值应连续变化，不能重触发或串到其它持键。
2. 在 UI 稳定后按模式、音色、效果和路由键；状态变化应立即进入发送队列，可见新画面仍受约 450 ms 完整 FS 帧时间约束，但不应再等待一帧旧画面后接近一秒才更新。
3. Push 屏幕、灯光、HDMI 三种分析图、效果顺序/箭头/动画、C 模式多键、P10 效果链、P2 低音和耳机输出保持正常。

真实压力手感和输入到可见画面的延迟，以本次实体结果为准。
