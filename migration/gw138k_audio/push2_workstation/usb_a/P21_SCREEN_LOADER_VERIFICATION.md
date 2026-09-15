# P21 Push 屏幕硬件装包

2026-09-15：P21 已完成源码、固件、定向仿真、完整 CPU/音频回归、综合布局、SRAM 下载和用户实体验收。屏幕操作延迟由 P20 约 0.6 秒降至约 0.35 秒；画面、连续压力、Push 灯光、HDMI、耳机和效果链均通过。

## 源码核对与可达到的延迟

当前构建仍采用 `usb_fs_phy`、48 MHz USB 时钟以及 H13/G13 的 J18 Full-Speed 链路。固件每帧发送 16 字节帧头和 640 个 512 字节像素包，包含每行 128 字节填充。旧路径有两次 CPU 搬运：`frame()` 从像素 MMIO 读数据、XOR 并存入暂存数组；`usbhw_transfer_out()` 再逐字节把数组写入 USB FIFO。

本地官方资料 `migration/midi_device_reference/ableton_push2_20260911_005756/AbletonPush2MIDIDisplayInterface.asc` 的 Display Interface Protocol、Pixel Data 和 Frame Buffering 段明确要求完整帧才显示。公开格式没有区域地址、局部提交或压缩帧命令。

传输下限：`327696 × 8 ÷ 12000000 = 0.218464 秒`，还不含 token、ACK、bit stuffing、MIDI、软件调度和显示扫描。200 ms 因而不能作为当前完整帧/12 Mbit/s 链路的可保证目标。P21 的 0.25–0.3 秒仅为低重试、离散单次操作下的完整帧估计，不能写成实体交互测量或持续压力显示延迟。已有 HS 尝试与原板供电限制见 `migration/midi_device_reference/push2_usb_host/docs/HS_ATTEMPT.md`；达到严格 200 ms 需另行完成更快物理链路，不能仅提高轮询次数。

## 改动

- 新增 `push2_screen_packet_loader`，用现有像素 MMIO 和 USB 寄存器握手装载 256 个像素；使用既有 512 字节 TX FIFO，没有增加 framebuffer 或 RAM。
- `0x02000228` 写入像素起始索引；`0x02000250` 为阻塞装包命令，完成 512 字节写入才向 CPU 返回。索引每次重试都回到同一包起点。
- `build.py` 在新构建副本中拆开原 USB 驱动的缓冲区装载与事务提交，`usbhw_transfer_out_preloaded()` 复用原 token、返回状态和响应检查。冻结来源和旧结果未改。
- USB CPU 在一个装包命令期间等待约 37 µs，然后继续事务和 MIDI 轮询；音频异步事件 FIFO、48 kHz 样本处理以及原 USB PID/ACK 规则保持原路径。
- 效果元数据和其它 UI 字段一样在帧请求时锁存，防止 NAK 重新生成包时有效载荷改变。下一帧继续采纳最新共享 DDR 元数据。
- P20 力度映射原样保留。P19 保活和 P20 离散状态变化时的旧帧重启仍生效。

## 仿真

最终构建目录：`results/build_20260915_195400_727173`。

`screen_loader_sim_200329_423575`：

- 使用真实 `usbh_core` 寄存器流水线与 TX FIFO，逐字节比较首包、行尾填充包、带等待的重放包以及最后一包。
- 正常每包 1793 个 48 MHz 周期，约 37.35 µs；640 包装载合计约 23.91 ms。像素端等待时仍保持 256 像素/512 字节与相同字节内容。
- 生产固件热插拔、DATA toggle、帧中 MIDI、完整帧、保活、旧帧重启通过；NAK 两次后第三次 ACK 的各次重装均保持同一像素起点和未 ACK 的 PID。

完整 Vex CPU/音频仿真 `cpu_audio_sim_200329_446100` 增加了实际 CPU 发起阻塞装包、检查 FIFO 512 字节及像素索引推进，并验证共享效果摘要更新不会改变正在发送帧的效果 mask。3818 个音频帧、3696 个非零帧，A/B/C、五音色、FX7、expression、路由、释放和精确 48 kHz 通过，无 audio fault。这是数字仿真，不是实体 Push、HDMI 或耳机验收。

复现：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py --prepare-only
python3 migration/gw138k_audio/push2_workstation/usb_a/sim/run_screen_loader.py <新构建目录>
python3 migration/gw138k_audio/push2_workstation/usb_a/sim/run.py <新构建目录>
```

## 综合与布局布线

最终构建目录 `results/build_20260915_195400_727173`，Gowin 返回 0，构建输入未变化。器件 `GW5AST-LV138PG484AC2/I1`。

| 项目 | P21 | 相对 P20 |
|---|---:|---:|
| setup 违例端点 | 0 | 0 |
| hold 违例端点 | 0 | 0 |
| 最差 setup slack | +0.010 ns | -0.237 ns |
| Logic | 33,830 | -463 |
| Register | 25,192 | +27 |
| BSRAM | 253 | 0 |
| DSP | 43.5 | 0 |

新增逻辑处于原 USB 48 MHz 域，未新增 CDC。完整 routed audit 仍因已有 `u_managed/effect_mask_sync_[0..2]_s0/RESET` stopped-clock reset 覆盖缺口而未通过；没有把该缺口写成通过。

## SRAM 与实体验收

位流：`results/build_20260915_195400_727173/Prj1/impl/pnr/Prj1.fs`，SHA256 `77a4a62e8e0323c94f4c58b73e9de0b1142a5fa612966c4c7f86de3a346fb039`，UserCode `0x0000D14C`。下载记录：`../results/sram_20260915_200446_106517/result.json`。写前读回 P20 `0x0000F9B7`、SRAM 写入、写后 P21 读回均通过，`fpga_flash_written` 为 `false`。

下载后的 5 秒 UART 只读窗口没有收到完整遥测记录，CRC 错误为 0，因此不把它写作板端数字通过或失败。用户随后完成实体检查：操作到画面约 0.35 秒，画面正常；连续压力、Push 灯光、HDMI、耳机和效果链均正常。P21 的延迟改善和完整回归验收通过。

0.2 秒目标没有达到。当前 12 Mbit/s 链路发送文档要求的完整帧，仅像素载荷下限就是 218.464 ms；本轮保留实测约 0.35 秒的结论，不把理论估计写成 0.2 秒通过。

P10 原 SHA256 `dd80b9009241836b3266b6407aa1a36cf8973d0b660d239e2e0f1fe8e0e4f793` 已再次核对，旧结果目录未修改。
