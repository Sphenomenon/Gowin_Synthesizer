# P13 共享 DDR 显示数据：阶段 4 Push 摘要读取

状态：P13 已完成 HDMI 共享 reader 与 Push 摘要 reader 的 RTL、仿真、综合/布局布线和 SRAM 下载；现作为 P14 的直接回退版本保留。Push 仍使用原 USB-A MMIO、帧请求和 512 B 屏幕包，未增加线协议或改变 MIDI 路径。

P13 在 P12 的 HDMI reader 基础上，把已提交显示快照压缩为 64 位摘要跨到 USB 48 MHz 域：frame sequence、effect mask/order、peak 摘要和 status 摘要。Push 屏幕在下一次既有 `frame_capture` 时锁存摘要；效果卡片状态使用共享 effect mask，其他模式/参数/灯光行为保持原实现。完整 waveform、李萨如和频谱数据仍由 HDMI reader 共享，Push 只取适合 960×160 屏幕的摘要，不复制 HDMI framebuffer。

## 构建与实现

构建目录：`results/build_20260915_005824_693914`。P10、P11 和 P12 结果目录均保留。`hdmi_display` 在完整 bank 提交后一拍发出摘要事件；顶层用 `gw138k_stream_cdc` 从 ddr_ui100 到 usb_48m；`push2_usb_a_control` 锁存数据后传给现有 `push2_surface_pixels`。USB-A 端点、固件、屏幕包格式和 Push MIDI 事件 FIFO 没有修改。

摘要位分配（低位优先）：

| 位 | 内容 |
|---:|---|
| 63:32 | 共享 metadata 的 display frame sequence |
| 31:23 | effect order[5:0] 与 effect mask[2:0] |
| 22:7 | 共享 waveform peak 摘要 |
| 6:0 | memory status 低 7 位 |

事件只在 reader `PUBLISH` 后延迟一拍产生；USB 域在下一帧请求前保留最近一次有效摘要。若没有有效共享摘要，Push 使用原有控制快照效果状态。

## 仿真

以下结果均为 RTL/稀疏 DDR 模型，不是实体屏幕验收：

- `results/build_20260915_005824_693914/p11_shared_011001_034385`：共享 reader 检查 descriptor、长度、版本、延迟响应、末尾 bank 头重试和缓存一致性，通过。
- `results/build_20260915_005824_693914/p11_shared_011001_037222`：HDMI 从共享缓存连续绘制 3 帧，覆盖 DDR 背压、双 bank 重载和启动无效 analysis；与 P10 首 3 帧 1,036,800 对像素对完全一致。
- `results/build_20260915_005824_693914/p11_shared_010924_373244`：writer、reader、frame writer、仲裁、framebuffer/P5 集成，通过 1,609,710 UI 周期、365 次共享写、365 次一致读。
- `results/build_20260915_005824_693914/p11_shared_011515_397368`：Push 摘要事件和 effect mask 锁存通过。

仿真覆盖 frame sequence 单调、提交前后 bank 一致、HDMI/共享 reader 同帧和 Push 摘要锁存；没有将数字模型写成实体 HDMI、Push 或耳机验收。

## 综合、布局布线与审计

最终 P&R：`results/build_20260915_005824_693914/Prj1/impl/pnr/Prj1.tr`。

| 项目 | 结果 |
|---|---:|
| setup 违例端点 | 0 |
| hold 违例端点 | 0 |
| 最差已报告 slack | +0.024 ns |
| Logic | 33,413 |
| Register | 24,923 |
| BSRAM | 254 |
| DSP | 42.5 |

`p13_routed_summary.json`：音频 48 kHz、既有音频/视频/USB 时钟和新 writer/bridge/reader 的 ddr_ui100 时钟/复位结构通过。`p13_usb_routed_summary.json`：USB PLL、事件 Gray CDC、既有 held snapshot CDC、USB PHY/pad 和 setup/hold 分项检查通过。新增 `u_display_push_cdc` 的 64 位 held-data、toggle 和 reset release 约束只作用于该 mailbox；主时钟路径未放宽。

完整旧审计仍失败且原样保留：历史 DDR reset 证据引用路径缺失，另有 `u_managed/effect_mask_sync_[0..2]_s0/RESET` 三个 stopped-clock reset 覆盖缺口。该结果见 `Prj1/check_existing.log`，没有把分项通过写成完整审计通过。

## SRAM 与实体验收边界

P13 位流：

- 文件：`results/build_20260915_005824_693914/Prj1/impl/pnr/Prj1.fs`
- SHA256：`894c51d40336fe86213adfddb3b151bc2c5d019b3cbd2e46a62acc0aa696539c`
- UserCode：`0x0000F002`
- 写前 UserCode：`0x0000C8A1`（P12）
- SRAM 记录：`../results/sram_20260915_011250_874114/result.json`
- Flash：未写

P13 曾替换板上 SRAM：写前读回 P12 `0x0000C8A1`，写入和写后读回 P13 `0x0000F002` 均通过；Flash 未写。当前板上是 P14 `0x00005610`，P12 位流仍保留在 `build_20260915_000749_501731`，P11/P10 也可回退。

实体验收需要确认：HDMI waveform、李萨如图、频谱图和效果卡片顺序/箭头/动画；Push 屏幕与灯光；耳机声音、P10 串行效果链和 P2 低音；以及按键到声音/画面的响应延迟。阶段 4 不测量这些项目就不宣布硬件通过。
