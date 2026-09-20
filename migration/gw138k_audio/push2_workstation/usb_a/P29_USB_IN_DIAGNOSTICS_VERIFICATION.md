# P29 USB IN 错误诊断验证

## 最终离线候选

正式结果目录为 `results/build_20260918_120700_417729`，非约束综合输入与 `results/build_20260918_112747_221636` 完全一致。位流 UserCode 为 `0x00000029`，SHA256 为 `b43d9e981cde16d571caeeea1ca2ca7e2031c556202cab48fa95eed6e6940581`，大小 42,197,761 字节。

| 项目 | 结果 |
|---|---:|
| setup 违例 | 0 |
| hold 违例 | 0 |
| 最差 setup slack | +0.085 ns |
| 最小 pulse-width slack | +1.325 ns |
| Logic | 35,112 |
| Register | 25,734 |
| BSRAM | 253 |
| DSP | 43.5 |

音频 PLL 初始化路径最大值为 9.756 ns，端点为 RESET。完整 `usb_a_audit.json` 通过，包含既有音频、DDR、HDMI、AE350、USB CDC 与 effect-mask 检查，并新增 32 bit USB IN 诊断寄存器、48 MHz 时钟和 P138 word 6 位置证明。P28 已关闭的 `effect_mask_sync_[0..2]_s0/RESET` 缺口没有复现。

## 必要回归

- `generic_midi_122541_287010/verification.json`：通过。P138 解码测试核对 errors、duplicate、NAK、disconnect、饱和标记和 P28 旧占位值兼容；生产固件测试覆盖 Push/通用 MIDI 枚举、toggle、热插拔和错误计数；RTL 核对 240 个有序事件、12,772 个背压周期、MMIO 遥测、声音与释放，同时保留 Push 初始化、力度和连续压力。
- `cpu_audio_sim_122130_114898/verification.json`：通过。覆盖 A/B/C、五种音色、七种效果组合、颤音、滑音、弯音、路由、释放和 48 kHz PCM，共 3,817 帧，其中 3,430 帧非零，无音频故障。

这些结果只证明数字实现和回归，不能代替 Push、HDMI、耳机、通用 MIDI 或诊断计数的实体检查。

## 被拒绝的实现

`build_20260918_112747_221636` 和 `build_20260918_113944_614964` 的 setup/hold 都是 0/0，但音频 PLL RESET 初始化路径为 10.115 ns，未通过原 10 ns routed audit。`build_20260918_115421_872522` 试验局部 max-delay 后路径仍未改变，而且约束没有命中已报告数据路径；该试验已撤销。三个目录均保留为失败证据，未用于候选，也没有下载。

## 板端状态

按用户要求，本会话没有调用 programmer、没有执行 SRAM 下载或下载前后读回，也没有写 Flash。最后一次已知实体稳定版本仍是已验收 P28 `0x00000028`；另一个会话可能独立使用硬件，因此本记录不把它写成当前时刻读回值。P29 状态为“已构建并审计，未下载，未实体验收”。

## UserCode 冲突标注

本候选位流的 UserCode 为 `0x00000029`，与引导功能 P29A
（分支 `codex/post-p28-product-features`，2026-09-18 实体验收）相同。P29A 已在板上
占用 `0x00000029`；本诊断候选从未下载，属于离线状态。为避免“同号不同位流”，
若将来要下载 USB IN 诊断，必须用新的 UserCode（下一个可用值为 `0x0000002A`）
重新构建。此处不改写已构建位流和既有 usercode 记录，只在候选 JSON 中登记冲突。

